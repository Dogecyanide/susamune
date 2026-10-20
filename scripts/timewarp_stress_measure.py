"""Measure actual PPC Quick streams from the user's named stress stages."""
import argparse
import hashlib
import json
from pathlib import Path

from timewarp_state_measure import PpcQuick, measure_set, POOL_BYTES, ROOT
from timewarp_cross_level_ppc import Batched, overlap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, default=ROOT / 'build/timewarp-stress-slots')
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/timewarp-stress-measure')
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / 'build').resolve()) or folder.is_relative_to(args.captures.resolve()):
        parser.error('Measurement output must be private and separate from captures')
    sources = ['src/state_codec.cpp', 'include/susamune/state_codec.hxx', 'vendor/lz4/lz4.c',
               'scripts/timewarp_stress_measure.py', 'scripts/timewarp_cross_level_ppc.py',
               'scripts/timewarp_state_measure.py']
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    captured = json.loads((args.captures / 'receipt.json').read_text())
    assert captured['cases'] and all(row['completed'] for row in captured['cases'])
    receipt = dict(scope='Current PPC Quick encoding of named historical PAL occupied-slot captures; no Wii timing claim.',
                   source_sha256=hashes, pool_bytes=POOL_BYTES, sets=[])
    try:
        with PpcQuick(args.dolphin, folder / 'ppc') as ppc:
            encoder = Batched(ppc)
            receipt['runtime'], receipt['batch'] = ppc.evidence, encoder.evidence
            for name in (row['name'] for row in captured['cases']):
                result = measure_set(name, args.captures / name / 'occupied', POOL_BYTES,
                                     None, encoder, folder / 'generated')
                result['cross_level_overlap'] = overlap(result)
                receipt['sets'].append(result)
                print(json.dumps(dict(set=name, quick=result['ppc_all_quick_capacity'],
                                      sharing=result['ppc_all_quick_sharing'])), flush=True)
    finally:
        assert hashes == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
