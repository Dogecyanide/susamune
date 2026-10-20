"""Run production Store/Import/Codec on PPC with isolated captured level data."""
import argparse
import json
from pathlib import Path
import random
import struct
import zlib

from timewarp_pool_ppc import ROOT, PoolPilot, build, load_set, sha


def produced(pilot, slot, state, mode=0):
    pilot.command(2, slot)
    pilot.write(pilot.INPUT, state['raw'])
    row = pilot.command(3, slot, len(state['raw']), mode)
    assert row['raw'] == len(state['raw'])
    assert row['adler'] == zlib.adler32(state['raw'])
    if not mode:
        assert row['packed'] == len(state['packed'])
        assert row['crc'] == zlib.crc32(state['packed'])
    return row


def exact(pilot, states):
    return [{'encoded': pilot.encoded(n, state),
             'decoded': pilot.decode(n, state, True)} for n, state in enumerate(states)]


def imported(pilot, slot, raw, packed, kind, abort_first=False, bad_adler=False):
    pilot.write(pilot.CONTROL + 96, struct.pack('>5I', len(raw), len(packed),
        zlib.adler32(raw) ^ int(bad_adler), zlib.crc32(packed), kind))
    pilot.command(8, slot)
    offset, windows = 0, []
    while offset < len(packed):
        part = packed[offset:offset + 0x4e000]
        pilot.write(pilot.OUTPUT, part)
        row = pilot.command(9, slot, len(part))
        next_offset, status = struct.unpack('>2I', pilot.read(pilot.CONTROL + 116, 8))
        assert offset < next_offset <= offset + len(part)
        assert status == int(next_offset == len(packed))
        assert pilot.read(pilot.OUTPUT, len(part)) == b'\xdb' * len(part)
        windows.append(dict(row, offset=offset, next_offset=next_offset))
        offset = next_offset
        if abort_first:
            pilot.command(5, slot)
            return {'windows': windows, 'aborted': True}
    row = pilot.command(4, slot, expected_status=94 if bad_adler else 0)
    if bad_adler:
        pilot.command(5, slot)
    return {'windows': windows, 'commit': row, 'bad_adler_refused': bad_adler}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    files = ['src/state_store.cpp', 'src/state_import.cpp', 'src/state_codec.cpp', 'src/state_crc.cpp', 'src/qft_timer.cpp',
        'scripts/timewarp/ppc_store_bench.cpp', 'scripts/timewarp/ppc_pool_bench.cpp',
        'scripts/timewarp_store_ppc.py', 'scripts/timewarp_pool_ppc.py']
    files += [str(p.relative_to(ROOT)).replace('\\', '/') for p in
              (ROOT / 'include/susamune').glob('state_*.h*')]
    before = {name: sha(ROOT / name) for name in files}
    report = {'passed': False, 'source_sha256': before, 'sets': [],
        'scope': 'Actual PPC Store/Import/Codec with measured level captures in a game-free owned Dolphin process. Four real bank lengths at isolated fake-VMEM addresses. No gameplay, ARM cache ownership or Wii timing claim.',
        'timing_limit': 'Host command acknowledgement includes polling overhead and unlimited emulation speed.'}
    try:
        dol, report['build'] = build(folder, ROOT / 'scripts/timewarp/ppc_store_bench.cpp')
        pilot = PoolPilot(args.dolphin, folder, dol, report, 1)
        report['runtime'] = pilot.evidence
        mixed_receipt = ROOT / 'build/cross-level/current-ppc/receipt.json'
        noki_receipt = ROOT / 'build/timewarp-noki1-measure/receipt.json'
        report['input_receipts'] = {str(p): sha(p) for p in (mixed_receipt, noki_receipt)}
        with pilot:
            for label, receipt in [('noki1', noki_receipt), ('mixed', mixed_receipt)]:
                states = load_set(receipt, label)
                pilot.command(1)
                saves = []
                for slot, state in enumerate(states):
                    row = {'produce': produced(pilot, slot, state), 'commit': pilot.command(4, slot)}
                    row['prior_roots_exact'] = [pilot.encoded(n, prior) for n, prior in enumerate(states[:slot + 1])]
                    saves.append(row)
                    print(json.dumps({'set': label, 'slot': slot, 'occupied': row['commit']['occupied']}), flush=True)
                report['sets'].append({'name': label, 'saves': saves, 'roots_exact': exact(pilot, states)})
            report['abort'] = {'produce': produced(pilot, 1, states[0]), 'old_roots': exact(pilot, states)}
            pilot.command(5, 1)
            report['abort']['after'] = exact(pilot, states)
            raw = random.Random(1601).randbytes(0x200000)
            packed = zlib.compress(raw)
            report['opaque_abort'] = imported(pilot, 1, raw, packed, 1, abort_first=True)
            report['opaque_abort']['old_roots'] = exact(pilot, states)
            report['opaque_bad_adler'] = imported(pilot, 1, raw, packed, 1, bad_adler=True)
            report['opaque_bad_adler']['old_roots'] = exact(pilot, states)
            report['opaque_import'] = imported(pilot, 1, raw, packed, 1)
            states[1] = {'raw': raw, 'packed': packed}
            report['opaque_import']['roots_exact'] = exact(pilot, states)
            candidate = load_set(mixed_receipt, 'same-level')[1]
            report['quick_import'] = imported(pilot, 2, candidate['raw'], candidate['packed'], 0)
            states[2] = candidate
            report['quick_import']['roots_exact'] = exact(pilot, states)
            pilot.command(10, 0)
            produced(pilot, 0, {'raw': raw}, mode=2)
            report['deflate_producer'] = {'commit': pilot.command(4, 0), 'decode': pilot.decode(0, {'raw': raw}, True)}
        assert before == {name: sha(ROOT / name) for name in files}
        report['passed'] = True
    finally:
        (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'receipt': str(folder / 'receipt.json')}), flush=True)


if __name__ == '__main__':
    main()
