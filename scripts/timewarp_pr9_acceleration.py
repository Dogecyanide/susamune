"""Screen one faster Quick encoder in a private actual-PPC fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

from timewarp_pool_ppc import ROOT, PoolPilot, sha
from timewarp_pr9_state_speed import compile_bench
from timewarp_replay_ppc import captured
from timewarp_shared_speed import capture_tree, timed
from timewarp_state_measure import quick_blocks


def stream(pilot, slot, packed):
    parts, offset = [], 0
    while offset < packed:
        row = pilot.command(6, slot, offset)
        assert row['raw'] == packed and row['packed']
        parts.append(pilot.read(pilot.OUTPUT, row['packed']))
        offset += row['packed']
    assert offset == packed
    return b''.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--acceleration', type=int, default=8, choices=(2, 4, 8))
    parser.add_argument('--stable-receipt', type=Path)
    parser.add_argument('--extra-pool', type=lambda x: int(x, 0), default=0)
    parser.add_argument('--capacity-only', action='store_true')
    parser.add_argument('--stage-tail', action='store_true')
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT/'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    commands_file = ROOT/'build/timewarp-online-checkpoint-19/console/compile_commands.json'
    input_file = ROOT/'build/timewarp-heap-gap-measure/receipt.json'
    prior_file = ROOT/'build/timewarp-pr9-state-speed-4/receipt.json'
    prior = json.loads(prior_file.read_text())
    assert prior['passed']
    inputs = json.loads(input_file.read_text())
    names = {
        'known-tight': inputs['known_capacity_failure']['names'],
        'pinna3': ['pinna3/slot'+str(n) for n in (1, 2, 3)],
        'mixed-heavy': ['pinna3/slot1', 'bianco5/slot3', 'noki1/slot1'],
    }
    groups = {name: [captured(inputs, n) for n in labels] for name, labels in names.items()}
    report = {'passed': False, 'scope': 'Game-free actual-PPC encode/replay/restore components '
        'using the shipped per-module optimization flags and existing bank capacities. '
        'Synthetic admission; excludes real Wii/game/cache/barrier latency.',
        'compile_commands_sha256': sha(commands_file), 'input_receipt_sha256': sha(input_file),
        'reused_pinna_baseline_receipt_sha256': sha(prior_file),
        'inputs': {name: [s['input'] for s in states] for name, states in groups.items()},
        'acceleration': args.acceleration, 'private_fixture_extra_pool': args.extra_pool,
        'stage_tail_geometry': args.stage_tail, 'variants': {}}
    commands = json.loads(commands_file.read_text())
    pilot = None
    try:
        candidate_name = 'acceleration'+str(args.acceleration)
        for name, acceleration in (('stable', 1), (candidate_name, args.acceleration)):
            if name == 'stable' and args.stable_receipt:
                previous = json.loads(args.stable_receipt.read_text())
                for key in ('compile_commands_sha256', 'input_receipt_sha256', 'inputs'):
                    assert previous[key] == report[key]
                report['variants']['stable'] = previous['variants']['stable']
                report['reused_stable_receipt_sha256'] = sha(args.stable_receipt)
                continue
            directory = folder/name; directory.mkdir()
            tree = directory/'tree'
            row = {'source_sha256': capture_tree(ROOT, tree), 'groups': {}}
            report['variants'][name] = row
            if acceleration == 1:
                relevant = [p for p in row['source_sha256'] if p.startswith('vendor/') or
                            p.startswith('include/susamune/state_') or
                            p.startswith('src/state_')]
                assert all(row['source_sha256'][p] == prior['variants']['current']['source_sha256'][p]
                           for p in relevant)
                row['groups']['pinna3'] = {k: prior['variants']['current'][k]
                                         for k in ('saves', 'loads', 'overwrites')}
                row['groups']['pinna3']['passed'] = True
            else:
                source = tree/'src/state_codec.cpp'
                text = source.read_text()
                old = 'noDict, noDictIssue, 1);'
                assert text.count(old) == 2
                source.write_text(text.replace(old, 'noDict, noDictIssue, '+str(acceleration)+');'))
                row['source_sha256']['src/state_codec.cpp'] = sha(source)
            dol, row['build'] = compile_bench(directory, tree, commands, args.extra_pool, args.stage_tail)
            pilot = PoolPilot(args.dolphin, directory, dol, row.setdefault('runtime', {}), 1)
            with pilot:
                for group, states in groups.items():
                    if args.capacity_only and group == 'pinna3':
                        continue
                    if name == 'stable' and group != 'mixed-heavy':
                        continue
                    result = {'passed': False, 'saves': [], 'loads': [], 'overwrites': []}
                    encoded_roots = []
                    row['groups'][group] = result
                    pilot.command(1)
                    try:
                        for operation, opcode in (('saves', 20), ('loads', 21), ('overwrites', 20)):
                            if args.capacity_only and operation == 'overwrites':
                                continue
                            if group == 'known-tight' and operation == 'overwrites':
                                continue
                            for slot, state in enumerate(states):
                                pilot.write(pilot.INPUT, state['raw'] if opcode == 20 else b'\xa7'*len(state['raw']))
                                measured = timed(pilot, opcode, slot, len(state['raw']) if opcode == 20 else 0)
                                assert pilot.read(pilot.INPUT, len(state['raw'])) == state['raw']
                                assert measured['raw'] == len(state['raw'])
                                assert measured['adler'] == zlib.adler32(state['raw'])
                                if opcode == 20:
                                    packed = stream(pilot, slot, measured['packed'])
                                    assert zlib.crc32(packed) == measured['crc']
                                    blocks = quick_blocks(packed, state['raw'])
                                    measured['independent_decode_exact'] = True
                                    measured['packed_sha256'] = hashlib.sha256(packed).hexdigest()
                                    measured['blocks'] = len(blocks)
                                    measured['original_packed_bytes'] = len(state['packed'])
                                    if operation == 'saves':
                                        encoded_roots.append(blocks)
                                        path = directory/(group+'-slot'+str(slot+1)+'.quick')
                                        path.write_bytes(packed)
                                        measured['packed_path'] = str(path)
                                measured['exact_input_or_decoded_bytes'] = True
                                result[operation].append(measured)
                        result['free_bytes'] = sum((0xff0000, 0x200000, 0xc2000, 0x13e000))-result['saves'][-1]['occupied']
                        def sharing(roots):
                            all_blocks = [block for blocks in roots for block in blocks]
                            unique = set(all_blocks)
                            aligned = lambda blocks: sum((len(b)+31)&~31 for b in blocks)
                            return {'aligned_all': aligned(all_blocks), 'aligned_unique': aligned(unique),
                                    'sharing_bytes': aligned(all_blocks)-aligned(unique), 'unique_blocks': len(unique)}
                        result['sharing'] = sharing(encoded_roots)
                        result['original_sharing'] = sharing([quick_blocks(s['packed'], s['raw']) for s in states])
                        result['bank_padding'] = result['saves'][-1]['occupied']-0x8000-result['sharing']['aligned_unique']
                        if args.stage_tail:
                            result['actual_free_bytes'] = result['free_bytes']+0x270000
                        if group == 'known-tight' and args.stage_tail:
                            candidate = captured(inputs, 'bianco5/slot3')
                            pilot.write(pilot.INPUT, candidate['raw'])
                            measured = timed(pilot, 20, 0, len(candidate['raw']))
                            assert pilot.read(pilot.INPUT, len(candidate['raw'])) == candidate['raw']
                            packed = stream(pilot, 0, measured['packed'])
                            quick_blocks(packed, candidate['raw'])
                            assert measured['crc'] == zlib.crc32(packed)
                            final = [candidate, *states[1:]]
                            measured['all_final_decodes'] = [pilot.decode(i, state, i == 0)
                                for i, state in enumerate(final)]
                            result['changed_overwrite'] = measured
                        result['canaries_intact'] = result['passed'] = True
                    except RuntimeError as error:
                        result['error'] = str(error)
                    print(json.dumps({'variant': name, 'set': group, **result}), flush=True)
                    if group == 'known-tight' and not result['passed']:
                        break
            row['owned_process_stopped'] = pilot.process.poll() is not None
        report['comparison'] = {}
        for group in ('pinna3', 'mixed-heavy'):
            before = report['variants']['stable']['groups'][group]
            after = report['variants'][candidate_name]['groups'].get(group, {'passed': False})
            if not before['passed'] or not after['passed']:
                continue
            report['comparison'][group] = {op: [
                {'slot': i+1, 'reduction_percent': 100*(1-b['guest_ticks']/a['guest_ticks']),
                 'packed_growth_percent': 100*(b['packed']/a['packed']-1)}
                for i, (a, b) in enumerate(zip(before[op], after[op]))]
                for op in ('saves', 'loads', 'overwrites')}
        report['passed'] = all(g['passed'] for v in report['variants'].values() for g in v['groups'].values())
    finally:
        if pilot and pilot.process and pilot.process.poll() is None:
            pilot.__exit__()
        (folder/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': report['passed'], 'comparison': report['comparison']}), flush=True)


if __name__ == '__main__':
    main()
