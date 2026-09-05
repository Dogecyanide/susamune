"""Verify the retail draw ABI used by the scoped native timer layout."""

import argparse
from pathlib import Path

from audit_practice_hooks import Dol


REGIONS = {
    "jp": (0x80014710, 0x80014C38, (0x803A8BC0, 0x803A8BF0, 0x803A8D48)),
    "us": (0x802CB6D4, 0x802CBBFC, (0x803E0598, 0x803E05C8, 0x803E0720)),
    "pal": (0x802C3768, 0x802C3C90, (0x803D7F50, 0x803D7F80, 0x803D80D8)),
}


def verify(region, path):
    dol = Dol(path)
    draw, matrix, vtables = REGIONS[region]

    def expect(address, words, label):
        if dol.words(address, len(words)) != tuple(words):
            raise ValueError(f"{region}: {label} mismatch at {address:08X}")

    for table in vtables:
        expect(table + 0x28, [matrix], "pane/picture/text makeMatrix slot")
    expect(draw + 0x238, [0x81990000, 0x80990014, 0x818C0028,
                        0x80190018, 0x7C84D214, 0x7D8803A6,
                        0x7CA0DA14, 0x4E800021], "matrix virtual dispatch")
    expect(draw + 0x270, [0x387E0084, 0x38990054, 0x38B90084],
           "parent/global/local matrix offsets")
    expect(draw + 0x290, [0x38790034, 0x389E0034], "parent clip intersection")
    expect(draw + 0x394, [0x833900D0], "bounded child list ABI")
    print(f"{region}: native timer draw ABI passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dol_directory", type=Path)
    args = parser.parse_args()
    for region in REGIONS:
        verify(region, args.dol_directory / f"{region}.dol")


if __name__ == "__main__":
    main()
