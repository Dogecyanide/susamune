"""Verify FOXTROT's non-timer hooks against user-supplied retail DOLs."""

import argparse
import hashlib
from pathlib import Path
import struct


REGIONS = {
    "jp": (0x80011BD8, 0x800EDA30, 0x80352F70, 0x803E4820,
           0x80408AD0, 0x800ED07C, 0x801151F8, 0x800ED088, 0x80114DD8),
    "us": (0x802C8B9C, 0x8029A4AC, 0x80023004, 0x803ACDE8,
           0x8040CC10, 0x80299AF8, 0x8021B900, 0x80299B04, 0x8021B4E0),
    "pal": (0x802C0C30, 0x80292344, 0x800230BC, 0x803A5168,
            0x80404370, 0x80291990, 0x80213854, 0x8029199C, 0x80213434),
}


class Dol:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        if len(self.data) < 0x100:
            raise ValueError("truncated DOL")
        offsets = struct.unpack_from(">18I", self.data, 0)
        addresses = struct.unpack_from(">18I", self.data, 0x48)
        sizes = struct.unpack_from(">18I", self.data, 0x90)
        self.sections = list(zip(offsets, addresses, sizes))
        for offset, _, size in self.sections:
            if size and (offset < 0x100 or offset + size > len(self.data)):
                raise ValueError("invalid DOL section")

    def words(self, address, count=1):
        for offset, base, size in self.sections:
            if base <= address and address + 4 * count <= base + size:
                return struct.unpack_from(">" + "I" * count, self.data,
                                          offset + address - base)
        raise ValueError(f"unmapped address {address:08X}")

    def calls_to(self, target):
        result = []
        for offset, base, size in self.sections[:7]:
            for i in range(0, size, 4):
                word = struct.unpack_from(">I", self.data, offset + i)[0]
                if word & 0xFC000003 != 0x48000001:
                    continue
                displacement = word & 0x03FFFFFC
                if displacement & 0x02000000:
                    displacement -= 0x04000000
                if base + i + displacement == target:
                    result.append(base + i)
        return result


def verify(region, path):
    dol = Dol(path)
    read, movement, camera, vtable, mode, hit_call, hit, clear_call, clear = REGIONS[region]

    def expect(address, values, label):
        actual = dol.words(address, len(values))
        if actual != tuple(values):
            raise ValueError(f"{region}: {label} mismatch at {address:08X}")

    expect(read, [0x7C0802A6], "relocatable pad prologue")
    direct = {"jp": 0x800ECDBC, "us": 0x80299838, "pal": 0x802916D0}[region]
    expect(direct + 0x90, [0x3BA00001], "normal app result is DEFAULT (1)")
    expect(movement, [0x7C0802A6, 0x90010004, 0x9421FFF8,
                      0x88030064, 0x2C000004, 0x41820008,
                      0x48000008], "movement only in state 4")
    expect(vtable + 8 * 4, [camera], "camera perform vtable slot")
    expect(mode, [1], "retail controller normalization mode")
    expect(camera + 0x2EC, [0x73C00014, 0x418200B4, 0xC01D016C,
                            0x389F00B4, 0x387D01EC, 0xD01F0074],
           "camera render cues and cached matrix offsets")
    expect(camera + 0x214, [0xC03D0048, 0x387D016C, 0xC05D004C,
                            0xC07D0028, 0xC09D002C],
           "camera projection inputs")
    expect(camera + 0x22C, [0x387D01EC, 0x389D0124,
                            0x38BD0030, 0x38DD0148],
           "camera look-at inputs")
    for site, target in ((hit_call, hit), (clear_call, clear)):
        branch = 0x48000001 | ((target - site) & 0x03FFFFFC)
        expect(site, [branch], "collision call")
        if dol.calls_to(target) != [site]:
            raise ValueError(f"{region}: unexpected collision callers")
    print(f"{region}: all practice hook invariants passed; "
          f"SHA256 {hashlib.sha256(dol.data).hexdigest()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dol_directory", type=Path,
                        help="directory containing jp.dol, us.dol and pal.dol")
    args = parser.parse_args()
    for region in REGIONS:
        verify(region, args.dol_directory / f"{region}.dol")


if __name__ == "__main__":
    main()
