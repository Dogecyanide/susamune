"""Verify the retail JUT post-error callback used by the photo report."""

import argparse
from pathlib import Path

from audit_practice_hooks import Dol


REGIONS = {
    "jp": (0x800104E4, 0x8D98),
    "us": (0x802C7504, 0xA100),
    "pal": (0x802BF598, 0xA038),
}


def verify(region, path):
    dol = Dol(path)
    context, post_offset = REGIONS[region]
    expected = (0x818D0000 | post_offset, 0x3AA30000, 0x387A0000,
                0x7D8803A6, 0x389B0000, 0x38BC0000, 0x38DD0000,
                0x3AE00001, 0x4E800021, 0x7EA3AB78)
    if dol.words(context + 0x22C, len(expected)) != expected:
        raise ValueError(f"{region}: JUT post-error callback ABI mismatch")
    expected = (0x2C170000, 0x40820040, 0x800D0000 | post_offset,
                0x28000000, 0x41820034)
    if dol.words(context + 0x214, len(expected)) != expected:
        raise ValueError(f"{region}: JUT callback single-call guard mismatch")
    print(f"{region}: JUT photo-report callback ABI passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dol_directory", type=Path)
    args = parser.parse_args()
    for region in REGIONS:
        verify(region, args.dol_directory / f"{region}.dol")


if __name__ == "__main__":
    main()
