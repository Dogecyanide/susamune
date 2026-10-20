"""One captured long-recording replacement through the actual PPC replay planner."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
import time
import shutil
import zlib

from timewarp_pool_ppc import ROOT, PoolPilot, build, sha
from timewarp_store_ppc import produced
from timewarp_replay_ppc import captured, stats
from timewarp_heap_gap_measure import gap
from timewarp_state_measure import quick_blocks
from timewarp_capacity_audit import BANKS, CAPACITY, placement


class LongPilot(PoolPilot):
    OUTPUT = 0x815a0000

    def command(self, cmd, slot=0, size=0, tag=0, expected_status=0):
        self.write(self.CONTROL + 48, struct.pack('>3I', slot, size, tag))
        self.write(self.CONTROL + 8, struct.pack('>I', cmd))
        self.sequence += 1
        began = time.perf_counter()
        self.write(self.CONTROL + 4, struct.pack('>I', self.sequence))
        deadline = time.monotonic() + 60
        while struct.unpack('>I', self.read(self.CONTROL + 12, 4))[0] != self.sequence:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(f'Owned PPC command {cmd} timed out')
            time.sleep(0.005)
        words = struct.unpack('>23I', self.read(self.CONTROL, 92))
        assert words[9] == 1, ('boundary canary', words)
        row = dict(command=cmd, slot=slot, status=words[4],
            host_seconds_to_ack=time.perf_counter() - began, packed=words[5], raw=words[6],
            adler=words[7], crc=words[8], occupied=words[10], candidate_blocks=words[15],
            stage_peak=words[16], commit_copied_bytes=words[17], generations=list(words[18:21]),
            live_blocks=words[21], aligned_block_bytes=words[22])
        allowed = expected_status if isinstance(expected_status, tuple) else (expected_status,)
        assert row['status'] in allowed, row
        return row

    def stream(self, slot, size):
        result = bytearray()
        while len(result) < size:
            row = self.command(6, slot, size=len(result))
            assert row['raw'] == size and row['packed'] > 0
            result.extend(self.read(self.OUTPUT, row['packed']))
        assert len(result) == size
        return bytes(result)


def projections(states, candidate, target):
    intern, sizes, ids = {}, [], []
    for state in [*states, candidate]:
        sequence = []
        for block in quick_blocks(state['packed'], state['raw']):
            if block not in intern:
                intern[block] = len(sizes)
                sizes.append(len(block))
            sequence.append(intern[block])
        ids.append(sequence)
    old = list(dict.fromkeys(itertools.chain.from_iterable(ids[:3])))
    referenced = set(ids[3])
    for slot in range(3):
        if slot != target:
            referenced.update(ids[slot])
    final = [n for n in old if n in referenced] + [n for n in ids[3] if n not in old]
    peak = placement(itertools.chain(old, ids[3]), sizes)
    stage = max(0, peak['occupied_bytes'] - CAPACITY)
    return dict(final=placement(final, sizes), append_peak=peak,
        ordinary_required_staging_bytes=stage, ordinary_staging_shortfall_bytes=max(0, stage-0x2f0000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--video-mode', choices=['PAL50', 'PAL60'], required=True)
    parser.add_argument('--reuse-build', type=Path)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT/'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    receipt_path = args.capture/'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    assert receipt['passed']
    info = receipt['capture']
    raw_path = Path(info['path'])
    meta_path = Path(info['metadata_path'])
    assert sha(raw_path) == info['raw_sha256'] and sha(meta_path) == info['metadata_sha256']
    canonical, gap_info = gap(raw_path.read_bytes(), meta_path.read_bytes())
    (folder/'canonical.raw').write_bytes(canonical)
    assert len(canonical) <= 0x151ffe0
    historical = ROOT/'build/timewarp-heap-gap-measure/receipt.json'
    prior = json.loads(historical.read_text())
    states = [captured(prior, name) for name in prior['known_capacity_failure']['names']]
    target = 1
    files = ['src/state_codec.cpp', 'src/state_store.cpp', 'src/state_import.cpp', 'src/state_crc.cpp',
        'src/state_quick_replay.cpp', 'src/qft_timer.cpp', 'scripts/timewarp/ppc_pool_bench.cpp',
        'scripts/timewarp/ppc_store_bench.cpp', 'scripts/timewarp_long_ghost_capacity.py',
        'scripts/timewarp_pool_ppc.py', 'scripts/timewarp_store_ppc.py']
    files += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'include/susamune').glob('state_*.h*')]
    files += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'vendor').rglob('*')
              if p.is_file() and p.suffix in ('.c','.h')]
    before = {name: sha(ROOT/name) for name in files}
    buffers = [('input',0x80080000,0x151ffe0), ('work',0x81600000,0x4e000),
        ('output',0x815a0000,0x30000), ('control',0x81700000,128),
        ('stack',0x815e0000,0x1f000), ('stage',0x71200000,0x2f0000),
        ('replay',0x71500000,0x4e000)]
    buffers += [(f'bank{n}', a, b) for n,(a,b) in enumerate(zip(
        (0x70010000,0x71800000,0x71100000,0x71b00000), BANKS))]
    for a,b in itertools.combinations(buffers,2):
        assert a[1]+a[2]+4 <= b[1]-4 or b[1]+b[2]+4 <= a[1]-4, (a,b)
    report = dict(passed=False, source_sha256=before, capture=info, video_mode=args.video_mode,
        scope='One real mostly-idle long-recording capture, historical PAL emulator Snapshot17 fixture. Root free gap alone canonicalized. Frozen production PPC codec/store/replay identified by source hashes in private game-free Dolphin; immutable source and synthetic admission. No maximum-entropy, Wii timing, game restore or PAL60 claim for PAL50 inputs.',
        inputs={str(receipt_path):sha(receipt_path),str(historical):sha(historical)},
        gap=gap_info, baseline=[s['input'] for s in states], target_slot=target,
        buffers=buffers, buffers_disjoint_with_guard_words=True, seeds=[])
    pilot = None
    try:
        if args.reuse_build:
            reused = json.loads((args.reuse_build/'receipt.json').read_text())
            assert reused['passed'] and reused['buffers'] == [list(b) for b in buffers]
            snapshot = args.reuse_build/'source-snapshot'
            dol = args.reuse_build/'bench.dol'
            assert sha(dol) == reused['build']['dol_sha256']
            report['build'] = reused['build']
            report['source_sha256'] = reused['source_sha256']
            report['snapshot_sha256'] = reused['snapshot_sha256']
            report['reused_build'] = str(args.reuse_build.resolve())
        else:
            snapshot = folder/'source-snapshot'
            for name in files:
                if name.endswith(('.cpp','.h','.hxx','.c')):
                    destination = snapshot/name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(ROOT/name,destination)
                    assert sha(destination) == before[name]
            # Non-state declarations used by the codec remain part of the frozen include tree.
            shutil.copytree(ROOT/'include',snapshot/'include',dirs_exist_ok=True)
            shutil.copytree(ROOT/'vendor',snapshot/'vendor',dirs_exist_ok=True)
            report['snapshot_sha256'] = {str(p.relative_to(snapshot)):sha(p)
                for p in snapshot.rglob('*') if p.is_file()}
            source = folder/'long_bench.cpp'
            source.write_text('#define TIMEWARP_QUICK_REPLAY 1\n#define TIMEWARP_LARGE_INPUT 1\n#include "'+
                              (snapshot/'src/state_crc.cpp').as_posix()+'"\n#include "'+
                              (snapshot/'scripts/timewarp/ppc_store_bench.cpp').as_posix()+'"\n')
            dol, report['build'] = build(folder, source, snapshot/'include')
        report['driver_sha256'] = sha(Path(__file__))
        assert report['snapshot_sha256'] == {str(p.relative_to(snapshot)):sha(p)
            for p in snapshot.rglob('*') if p.is_file()}
        pilot = LongPilot(args.dolphin, folder, dol, report, 1)
        report['runtime'] = pilot.evidence
        with pilot:
            pilot.command(1)
            for slot,state in enumerate(states):
                row = dict(produce=produced(pilot,slot,state), commit=pilot.command(4,slot))
                report['seeds'].append(row)
            pilot.write(pilot.INPUT, canonical)
            prepared = pilot.command(11,target,len(canonical),expected_status=(0,112))
            report['prepare'] = dict(command=prepared)
            if prepared['status'] == 0:
                report['prepare']['stats'] = stats(pilot)
                assert prepared['raw'] == len(canonical) and prepared['adler'] == zlib.adler32(canonical)
            report['old_roots_exact_before_commit_or_after_refusal'] = [pilot.encoded(i,s) for i,s in enumerate(states)]
            assert pilot.read(pilot.INPUT,len(canonical)) == canonical
            report['source_unchanged_through_preparation'] = True
            if prepared['status'] == 0:
                committed = pilot.command(12,target)
                report['commit'] = dict(command=committed, stats=stats(pilot))
                assert committed['generations'][0] == 1 and committed['generations'][2] == 3
                assert committed['generations'][1] == 4
                assert report['commit']['stats']['encode_calls'] - report['prepare']['stats']['encode_calls'] == report['prepare']['stats']['spilled_blocks']
            else:
                report['final_capacity_refused_old_roots_preserved'] = True
                pilot.command(1)
                pilot.command(2,target)
                pilot.write(pilot.INPUT,canonical)
                prepared = pilot.command(3,target,len(canonical))
                report['candidate_encoded_in_empty_store'] = prepared
                assert prepared['raw'] == len(canonical) and prepared['adler'] == zlib.adler32(canonical)
                pilot.command(4,target)
            packed = pilot.stream(target,prepared['packed'])
            assert zlib.crc32(packed) == prepared['crc']
            candidate = dict(raw=canonical,packed=packed)
            (folder/'canonical.quick').write_bytes(packed)
            blocks = quick_blocks(packed, canonical)
            report['candidate'] = dict(raw_bytes=len(canonical), packed_bytes=len(packed),
                packed_sha256=hashlib.sha256(packed).hexdigest(), gap_saving_bytes=info['packed_bytes']-len(packed))
            report['projection'] = projections(states,candidate,target)
            if 'commit' in report:
                assert report['projection']['final']['occupied_bytes'] == report['commit']['command']['occupied']
                final = [states[0],candidate,states[2]]
                report['final_roots'] = [dict(encoded=pilot.encoded(i,s),protected_decode=pilot.decode(i,s,True)) for i,s in enumerate(final)]
            else:
                assert not report['projection']['final']['fits']
                report['candidate_decode'] = pilot.decode(target,candidate,True)
            first,last = info['game_bytes'],info['game_bytes']+info['ghost_bytes']
            inside,edge = [],[]
            for i,block in enumerate(blocks):
                begin,end = i*0x20000,min((i+1)*0x20000,len(canonical))
                if begin < last and end > first:
                    (inside if first <= begin and end <= last else edge).append(dict(
                        block=i,raw_first=begin,raw_last=end,packed_bytes=len(block)))
            report['ghost_block_accounting'] = dict(ghost_raw_bytes=info['ghost_bytes'],
                wholly_ghost_blocks=inside, wholly_ghost_packed_bytes=sum(b['packed_bytes'] for b in inside),
                boundary_blocks=edge,boundary_packed_bytes=sum(b['packed_bytes'] for b in edge),
                limitation='Boundary blocks mix ghost bytes with game/practice bytes; this is block accounting, not a counterfactual marginal compression saving.')
            report['all_boundary_canaries_intact'] = True
        assert report['snapshot_sha256'] == {str(p.relative_to(snapshot)):sha(p)
            for p in snapshot.rglob('*') if p.is_file()}
        report['passed'] = True
    finally:
        if pilot and pilot.process and pilot.process.poll() is None:
            pilot.__exit__()
        report['owned_process_stopped'] = bool(pilot and pilot.process and pilot.process.poll() is not None)
        (folder/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','candidate','projection','ghost_block_accounting','owned_process_stopped')},indent=2),flush=True)


if __name__ == '__main__': main()
