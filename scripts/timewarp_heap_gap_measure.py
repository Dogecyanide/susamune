"""Measure canonical free-heap bytes on immutable captures; no gameplay edits."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from timewarp_state_measure import PpcQuick, ROOT
from timewarp_cross_level_ppc import Batched
from test_state_store import StoreCodec, StorePool
from test_timewarp_staged_transaction import StageHarness

BANKS = [0xff0000, 0x200000, 0xc2000, 0x13e000]
INPUTS = ['build/cross-level/current-ppc/receipt.json',
          'build/timewarp-stress-measure/receipt.json', 'build/timewarp-noki1-measure/receipt.json']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gap(raw, metadata):
    heap, size = struct.unpack_from('>2I', metadata, 12)
    count = struct.unpack_from('>I', metadata, 24)[0]
    regions = [struct.unpack_from('>3I', metadata, 40 + n * 12) for n in range(count)]
    _, length, offset = next(r for r in regions if r[0] == heap)
    start, end, heap_size = struct.unpack_from('>3I', raw, offset + 0x30)
    free, head, tail = struct.unpack_from('>3I', raw, offset + 0x68)
    assert length == size and heap < start <= head <= tail <= end == heap + size
    assert heap_size == end - start and free == tail - head
    first, last = offset + head - heap, offset + tail - heap
    filtered = raw[:first] + bytes(free) + raw[last:]
    assert len(filtered) == len(raw) and filtered[:first] == raw[:first] and filtered[last:] == raw[last:]
    return filtered, dict(heap=hex(heap), heap_end=hex(end), allocated_head_end=hex(head),
        allocated_tail_start=hex(tail), raw_offset=first, free_bytes=free,
        nonzero_free_bytes=free - raw[first:last].count(0),
        filtered_raw_sha256=digest(filtered))


def occupied(states, harness, codec, canonical):
    pool = StorePool(harness, codec, BANKS)
    results = []
    for slot, state in enumerate(states):
        raw, encoded = state['canonical' if canonical else 'original']
        accepted = pool.put(slot, raw, encoded, 1001 + slot, 0)
        results.append(accepted)
        if not accepted:
            break
    for slot, accepted in enumerate(results):
        if accepted:
            pool.decode(slot, True)
    return dict(accepted=results, occupied_bytes=pool.pool.directory.high_water,
        free_bytes=sum(BANKS) - pool.pool.directory.high_water,
        all_admitted_roots_decode=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT / 'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    (folder / 'allocator').mkdir()
    (folder / 'generated').mkdir()
    files = ['src/state_codec.cpp', 'src/state_store.cpp', 'scripts/timewarp_heap_gap_measure.py']
    before = {p: digest((ROOT / p).read_bytes()) for p in files}
    report = dict(passed=False, source_sha256=before, sets=[],
        scope='Hypothetical free-gap canonicalization on private captured bytes. Actual PPC Quick encoding and native production Store capacity/restore checks. No game memory writes, allocation-lifetime proof, production implementation or Wii timing claim.',
        decomp_layout='JKRSolidHeap mFreeSize/+0x68, mCurStart/+0x6c, mCurEnd/+0x70; JKRHeap mStart/+0x30, mEnd/+0x34, mSize/+0x38.',
        inputs={p: digest((ROOT / p).read_bytes()) for p in INPUTS})
    codec, harness = StoreCodec(folder), StageHarness(folder / 'allocator')
    all_states = {}
    try:
        with PpcQuick(args.dolphin, folder / 'ppc') as ppc:
            encoder = Batched(ppc)
            report['runtime'] = ppc.evidence
            for receipt in INPUTS:
                for group in json.loads((ROOT / receipt).read_text())['sets']:
                    states, rows = [], []
                    for row in group['slots']:
                        path = Path(row['raw_path'])
                        raw, metadata = path.read_bytes(), path.with_suffix('.metadata').read_bytes()
                        assert digest(raw) == row['raw_sha256']
                        packed = Path(row['ppc_quick']['path']).read_bytes()
                        assert digest(packed) == row['ppc_quick']['sha256']
                        filtered, info = gap(raw, metadata)
                        encoded = encoder.encode(filtered)
                        destination = folder / 'generated' / (group['name'] + '-slot' + str(row['slot']) + '.quick')
                        destination.write_bytes(encoded)
                        info.update(name=group['name'] + '/slot' + str(row['slot']), raw_path=str(path),
                            raw_sha256=digest(raw), metadata_sha256=digest(metadata), original_packed_bytes=len(packed),
                            canonical_packed_bytes=len(encoded), packed_saving_bytes=len(packed) - len(encoded),
                            packed_path=str(destination), packed_sha256=digest(encoded))
                        state = {'original': (raw, packed), 'canonical': (filtered, encoded)}
                        all_states[info['name']] = state
                        states.append(state); rows.append(info)
                    original = occupied(states, harness, codec, False)
                    canonical = occupied(states, harness, codec, True)
                    result = dict(name=group['name'], slots=rows, original=original, canonical=canonical,
                        pool_saving_bytes=original['occupied_bytes'] - canonical['occupied_bytes'])
                    report['sets'].append(result)
                    print(json.dumps({k: result[k] for k in ('name', 'original', 'canonical', 'pool_saving_bytes')}), flush=True)
            names = ['mixed/slot1', 'noki1/slot1', 'same-level/slot2']
            states = [all_states[name] for name in names]
            report['known_capacity_failure'] = dict(names=names,
                original=occupied(states, harness, codec, False), canonical=occupied(states, harness, codec, True))
        assert before == {p: digest((ROOT / p).read_bytes()) for p in files}
        report['passed'] = True
    finally:
        codec.close(); harness.close()
        (folder / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['known_capacity_failure']), flush=True)


if __name__ == '__main__':
    main()
