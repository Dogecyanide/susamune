"""Private no-heap boot decoder proof; no loader, cache or reset integration."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import subprocess
import tempfile
import unittest

from timewarp_state_measure import decode_lz4

ROOT = Path(__file__).resolve().parents[1]
FRAME = struct.pack(">II", 0x4D534C34, 0x20000)
BLOCK = 0x20000
OK, INVALID, CORRUPT, COMMIT_FAILED = range(4)


def plain(payload):
    return struct.pack(">II", len(payload), len(payload) | 0x80000000) + payload


def matched(raw=32, distance=1):
    # One literal, an overlapping match, then the required five final literals.
    match = raw - 6
    extension = bytearray()
    if match - 4 >= 15:
        remain = match - 4 - 15
        while remain >= 255:
            extension.append(255)
            remain -= 255
        extension.append(remain)
    encoded = bytes([0x10 | min(match - 4, 15), ord("A")]) + struct.pack("<H", distance)
    encoded += extension + b"\x50abcde"
    return struct.pack(">II", raw, len(encoded)) + encoded


class Harness:
    def __init__(self, directory):
        self.path = Path(directory)
        source = self.path / "boot_quick.c"
        source.write_text(r'''
#include "timewarp/boot_quick.h"
#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
EXPORT int validate(const void *p,unsigned n,unsigned r) { return TWBootQuickValidate(p,n,r); }
EXPORT int decode(const void *p,unsigned n,void *d,unsigned r,unsigned cap) {
    return TWBootQuickDecode(p,n,d,r,cap);
}
''', encoding="ascii")
        compiler = str(ROOT / "toolchain/clang.exe")
        common = ["-x", "c", "-std=c11", "-O2", "-fno-builtin", "-ffreestanding",
                  "-I", str(ROOT / "scripts")]
        dll = self.path / "boot_quick.dll"
        subprocess.run([compiler, "--target=x86_64-pc-windows-msvc", *common,
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
                        str(source), "-o", str(dll)], check=True)
        self.ppc = self.path / "boot_quick.o"
        subprocess.run([compiler, "--target=powerpc-gecko-ibm-kuribo-eabi", *common,
                        "-c", str(source), "-o", str(self.ppc)], check=True)
        subprocess.run([compiler, "--target=powerpc-gecko-ibm-kuribo-eabi", *common,
                        "-S", str(source), "-o", str(self.ppc.with_suffix(".s"))], check=True)
        self.lib = C.CDLL(str(dll))
        self.lib.validate.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        self.lib.decode.argtypes = [C.c_void_p, C.c_uint, C.c_void_p, C.c_uint, C.c_uint]

    def close(self):
        C.windll.kernel32.FreeLibrary(C.c_void_p(self.lib._handle))

    def run(self, encoded, raw, capacity=None):
        encoded = bytes(encoded)
        capacity = raw + 96 if capacity is None else capacity
        destination = C.create_string_buffer(bytes([0xA7]) * (capacity + 128))
        source = C.create_string_buffer(encoded)
        status = self.lib.decode(source, len(encoded), C.addressof(destination) + 64, raw, capacity)
        self.source_unchanged = C.string_at(source, len(encoded)) == encoded
        return status, C.string_at(C.addressof(destination), capacity + 128)


class BootQuickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-boot-quick-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = Harness(cls.temp.name)
        cls.addClassCleanup(cls.harness.close)

    def check_exact(self, encoded, expected, bss=96):
        status, memory = self.harness.run(encoded, len(expected), len(expected) + bss)
        self.assertEqual(status, OK)
        self.assertEqual(memory[:64], bytes([0xA7]) * 64)
        self.assertEqual(memory[64:64 + len(expected)], expected)
        self.assertEqual(memory[64 + len(expected):], bytes([0xA7]) * (bss + 64))
        self.assertTrue(self.harness.source_unchanged)

    def check_rejected(self, encoded, raw, status=CORRUPT, capacity=None):
        capacity = raw + 96 if capacity is None else capacity
        result, memory = self.harness.run(encoded, raw, capacity)
        self.assertEqual(result, status)
        self.assertEqual(memory, bytes([0xA7]) * len(memory))
        self.assertTrue(self.harness.source_unchanged)

    def test_plain_boundaries_and_multiple_independent_blocks(self):
        for count in (1, 5, 31, BLOCK - 1, BLOCK):
            payload = bytes((i * 19 + 3) & 255 for i in range(count))
            self.check_exact(FRAME + plain(payload), payload)
        full = bytes([0x35]) * BLOCK
        self.check_exact(FRAME + plain(full) + plain(b"last"), full + b"last")

    def test_overlapping_match_and_extended_match_length(self):
        for raw in (13, 24, 32, 273, BLOCK):
            block = matched(raw)
            expected = b"A" * (raw - 5) + b"abcde"
            self.assertEqual(decode_lz4(block[8:], raw), expected)
            self.check_exact(FRAME + block, expected)
        first = matched(BLOCK)
        self.check_exact(FRAME + first + matched(32),
                         b"A" * (BLOCK - 5) + b"abcde" + b"A" * 27 + b"abcde")

    def test_extended_literals_and_maximum_little_endian_match_distance(self):
        def extension(length):
            if length < 15:
                return b""
            remaining = length - 15
            return bytes([255]) * (remaining // 255) + bytes([remaining % 255])
        literals = bytes((i * 37 + 11) & 255 for i in range(65535))
        count = BLOCK - len(literals) - 5
        encoded = b"\xff" + extension(len(literals)) + literals
        encoded += b"\xff\xff" + extension(count - 4) + b"\x50abcde"
        raw = literals + literals[:count] + b"abcde"
        self.assertEqual(decode_lz4(encoded, len(raw)), raw)
        self.check_exact(FRAME + struct.pack(">II", len(raw), len(encoded)) + encoded, raw)

    def test_late_bad_block_never_writes_valid_earlier_block(self):
        prefix = FRAME + plain(b"P" * BLOCK)
        for tail in (matched(32, 0), matched(32, 2), matched(32)[:-1],
                     struct.pack(">II", 31, 0x80000020) + b"x" * 32):
            self.check_rejected(prefix + tail, BLOCK + 32)

    def test_bad_lz4_lengths_offsets_and_terminal_sequences(self):
        for payload, raw in ((b"\xf0", 32), (b"\xf0\xff", 32),
                             (b"\xf0\x20short", 32), (b"\x10A\x01", 32),
                             (b"\x1fA\x00\x00\x07\x50abcde", 32),
                             (b"\x1fA\x02\x00\x07\x50abcde", 32),
                             (b"\x1fA\x01\x00\xff", 32),
                             (b"\x10A\x01\x00", 32),
                             (b"\x14A\x01\x00\x40bcde", 13),
                             (b"\x13A\x01\x00\x50abcde", 14)):
            self.check_rejected(FRAME + struct.pack(">II", raw, len(payload)) + payload, raw)

    def test_frame_bounds_and_no_trailing_bytes(self):
        encoded = FRAME + matched(32)
        for end in range(len(encoded)):
            self.check_rejected(encoded[:end], 32, INVALID if end == 0 else CORRUPT)
        for broken in (b"BAD!" + encoded[4:], encoded[:4] + b"\0\0\0\1" + encoded[8:],
                       encoded + b"\0", FRAME + plain(b"short") + plain(b"tail"),
                       FRAME + struct.pack(">II", 32, 0),
                       FRAME + struct.pack(">II", 32, 0x8000001f) + b"x" * 31,
                       FRAME + struct.pack(">II", 32, 32) + b"x" * 32):
            self.check_rejected(broken, 32)
        self.check_rejected(encoded, 31)
        self.check_rejected(encoded, 33)
        self.check_rejected(encoded, 0, INVALID)
        self.check_rejected(encoded, 32, INVALID, capacity=31)

    def test_ranges_alias_and_wrapping_addresses_fail_before_reads_or_writes(self):
        encoded = FRAME + matched(32)
        memory = C.create_string_buffer(bytes([0xA7]) * 256)
        address = C.addressof(memory)
        C.memmove(address + 96, encoded, len(encoded))
        before = C.string_at(address, 256)
        maximum = (1 << (C.sizeof(C.c_void_p) * 8)) - 1
        for source, packed, destination, initialized, capacity in (
                (0, 20, address, 32, 64), (address + 96, len(encoded), 0, 32, 64),
                (maximum - 3, 20, address, 32, 64),
                (address + 96, len(encoded), maximum - 3, 32, 64),
                (address + 96, len(encoded), address + 96, 32, 64),
                (address + 96, len(encoded), address + 100, 32, 64),
                # Source overlaps only the declared BSS, still part of the owned destination.
                (address + 96, len(encoded), address + 64, 16, 80)):
            self.assertEqual(self.harness.lib.decode(source, packed, destination,
                                                    initialized, capacity), INVALID)
            self.assertEqual(C.string_at(address, 256), before)

    def test_deterministic_mutations_preserve_destination_on_rejection(self):
        rng = random.Random(7911)
        original = FRAME + matched(273)
        for _ in range(500):
            mutated = bytearray(original)
            for _ in range(rng.randrange(1, 4)):
                mutated[rng.randrange(len(mutated))] = rng.randrange(256)
            status, memory = self.harness.run(mutated, 273)
            if status == OK:
                self.assertEqual(memory[64:337], decode_lz4(mutated[16:], 273))
                self.assertEqual(memory[:64] + memory[337:], bytes([0xA7]) * (64 + 96 + 64))
            else:
                self.assertEqual(status, CORRUPT)
                self.assertEqual(memory, bytes([0xA7]) * len(memory))


def artifacts(receipt_path, output):
    receipt = json.loads(receipt_path.read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix="timewarp-boot-segments-") as temp:
        harness = Harness(temp)
        try:
            for region in receipt["regions"]:
                name = region["region"]
                mod = (ROOT / f"build/baseline-console/mod_{name}.bin").read_bytes()
                assert hashlib.sha256(mod).hexdigest() == region["mod_sha256"]
                for index, segment in enumerate(region["segments"]):
                    offset, initialized, runtime, payload_offset = struct.unpack_from(">4I", mod, 32 + 16 * index)
                    assert (offset, initialized, runtime) == (
                        segment["offset"], segment["initialized_bytes"], segment["runtime_bytes"])
                    raw = mod[32 + payload_offset:32 + payload_offset + initialized]
                    packed = (receipt_path.parent / f"{name}-segment{index}.ppc-quick").read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == segment["raw_sha256"]
                    assert hashlib.sha256(packed).hexdigest() == segment["quick_sha256"]
                    status, memory = harness.run(packed, initialized, runtime)
                    assert status == OK and memory[64:64 + initialized] == raw
                    assert memory[:64] == bytes([0xA7]) * 64
                    assert memory[64 + initialized:] == bytes([0xA7]) * (runtime - initialized + 64)
                    assert harness.source_unchanged
                    # Corrupt the last block header after a complete valid first block.
                    cursor = 8
                    while cursor < len(packed):
                        last = cursor
                        cursor += 8 + (struct.unpack_from(">I", packed, cursor + 4)[0] & 0x7fffffff)
                    damaged = bytearray(packed)
                    damaged[last:last + 4] = b"\0\0\0\0"
                    failed, untouched = harness.run(damaged, initialized, runtime)
                    assert failed == CORRUPT and untouched == bytes([0xA7]) * len(untouched)
                    results.append({"region": name, "segment": index, "initialized_bytes": initialized,
                                    "bss_bytes_untouched": runtime - initialized,
                                    "decoded_exact": True, "late_corruption_preserved_destination": True})
                    print(f"{name} segment {index}: {initialized:,} exact initialized bytes; "
                          f"{runtime - initialized:,} BSS bytes untouched")
            from elftools.elf.elffile import ELFFile
            with harness.ppc.open("rb") as stream:
                elf = ELFFile(stream)
                sections = {s.name: s["sh_size"] for s in elf.iter_sections()
                            if s["sh_flags"] & 2 and s["sh_size"]}
            assembly = harness.ppc.with_suffix(".s").read_text()
            stack_frames = [int(n) for n in re.findall(r"stwu\s+1,\s*-(\d+)\(1\)", assembly)]
        finally:
            harness.close()
    result = {"scope": "Private native-C reconstruction of six actual PPC Quick transport segments.",
              "limits": "No production format, loader integration, checksum policy, cache maintenance, PPC execution, or boot/reset timing.",
              "decoder_sha256": hashlib.sha256((ROOT / "scripts/timewarp/boot_quick.h").read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "input_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
              "ppc_object_allocated_sections": sections,
              "ppc_function_frame_sizes_not_call_chain_peak": stack_frames, "segments": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-transport-measure/decoder-receipt.json")
    args, remaining = parser.parse_known_args()
    if args.receipt:
        artifacts(args.receipt, args.output)
    else:
        unittest.main(argv=[__file__] + remaining)
