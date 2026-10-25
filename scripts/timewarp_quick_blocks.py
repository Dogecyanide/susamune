"""Compare incremental PPC Quick output with measured canonical PPC streams."""
import argparse
import hashlib
import json
from pathlib import Path

from timewarp_state_measure import PpcQuick, ROOT, quick_blocks
from timewarp_cross_level_ppc import Batched


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/timewarp-quick-blocks')
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / 'build').resolve()) or folder.exists():
        parser.error('Use a fresh task build directory')
    inputs = [ROOT / name for name in ('build/timewarp-state-measure/ppc-receipt.json',
              'build/cross-level/current-ppc/receipt.json', 'build/timewarp-stress-measure/receipt.json')]
    receipt = dict(scope='Incremental encoder executed as PPC instructions; canonical output and source preservation only, not Wii speed.',
                   sources={name: digest(ROOT / name) for name in ('src/state_codec.cpp',
                     'include/susamune/state_codec.hxx', 'scripts/timewarp_state_measure.py',
                     'scripts/timewarp_quick_blocks.py')}, inputs={}, streams=[])
    try:
        with PpcQuick(args.dolphin, folder / 'ppc', incremental=True) as ppc:
            encoder = Batched(ppc)
            receipt['runtime'], receipt['batch'] = ppc.evidence, encoder.evidence
            for path in inputs:
                receipt['inputs'][str(path)] = digest(path)
                groups = json.loads(path.read_text())['sets']
                for group in groups:
                    for slot in group['slots']:
                        source, previous = Path(slot['raw_path']), Path(slot['ppc_quick']['path'])
                        raw, expected = source.read_bytes(), previous.read_bytes()
                        packed = encoder.encode(raw)
                        assert packed == expected
                        quick_blocks(packed, raw)
                        row = dict(raw_path=str(source), raw_sha256=digest(source), packed_bytes=len(packed),
                                   packed_sha256=hashlib.sha256(packed).hexdigest(), identical=True)
                        receipt['streams'].append(row)
                        print(json.dumps(dict(stream=len(receipt['streams']), packed_bytes=len(packed), identical=True)), flush=True)
            receipt['completed'] = True
    finally:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
