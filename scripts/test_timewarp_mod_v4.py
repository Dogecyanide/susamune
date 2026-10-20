"""Private C V4 preflight/install tests; no actual Wii boot or cache claim."""
import argparse
import ctypes as C
import json
import re
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from timewarp_mod_v4 import (ROOT, GAMES, BASES, CAPS, build_mod_v4,
                             baseline_inputs, cold_inputs, stage, sha)

REGION_BYTES = 0xC0000
SENTINEL = 0xA7


def word(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def put(data, offset, value):
    struct.pack_into(">I", data, offset, value)


def seal(data):
    put(data, 36, zlib.crc32(data[64:]))
    put(data, 40, 0)
    put(data, 40, zlib.crc32(data[:64]))
    return data


def seal_payload(data, index):
    descriptor = 64 + index * 32
    offset, size = word(data, descriptor + 12), word(data, descriptor + 16)
    put(data, descriptor + 24, zlib.crc32(data[64 + offset:64 + offset + size]))
    return seal(data)


def tiny(*, flags=0, cold=False, quick=False):
    segments = []
    for index, (offset, _) in enumerate(CAPS):
        raw = bytes([0x30 + index]) * 32
        segment = dict(offset=offset, memory_size=64, raw=raw)
        if quick:
            segment["quick"] = struct.pack(">4I", 0x4D534C34, 0x20000, 32, 0x80000020) + raw
        segments.append(segment)
    return build_mod_v4(GAMES["jp"], segments, [(0x8000561C, 0x48000000)],
                        flags=flags, cold=bytes(range(32)) if cold else None,
                        cold_vma=stage(flags) + 0xA0 if cold else None)


def match_block(literals, distance, raw_size):
    def extension(size):
        return bytes([255]) * ((size - 15) // 255) + bytes([(size - 15) % 255]) if size >= 15 else b""
    amount = raw_size - len(literals) - 5
    encoded = bytes([(min(len(literals), 15) << 4) | min(amount - 4, 15)])
    encoded += extension(len(literals)) + literals + struct.pack("<H", distance)
    encoded += extension(amount - 4) + b"\x50abcde"
    expected = bytearray(literals)
    for _ in range(amount):
        expected.append(expected[-distance])
    expected.extend(b"abcde")
    return struct.pack(">2I", raw_size, len(encoded)) + encoded, bytes(expected)


class Harness:
    def __init__(self, directory):
        self.path = Path(directory)
        source = self.path / "mod_v4.c"
        source.write_text(r'''
#include "timewarp/mod_v4.h"
#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
EXPORT int validate(const void *p,unsigned n,unsigned g,unsigned f,unsigned s) {
    return TWModV4Validate(p,n,g,f,s);
}
EXPORT int install(const void *p,unsigned n,unsigned g,unsigned f,unsigned s,
                   void *d,unsigned cap,unsigned base) {
    return TWModV4Install(p,n,g,f,s,d,cap,base);
}
EXPORT int production_validate(const struct SusamuneModHeader *p,unsigned g,unsigned n) {
    return SusamuneModFileValid(p,g,n);
}
EXPORT int production_header(const struct SusamuneModHeader *p,unsigned g) {
    return SusamuneModHeaderValid(p,g);
}
EXPORT unsigned production_size(const struct SusamuneModHeader *p) { return SusamuneModFileSize(p); }
EXPORT int production_install(const struct SusamuneModHeader *p,unsigned g,unsigned n,
                              void *d,unsigned cap,unsigned base) {
    return SusamuneModInstall(p,g,n,d,cap,base);
}
EXPORT unsigned production_info(const struct SusamuneModHeader *p,unsigned what) {
    switch (what) {
        case 0: return SusamuneModHeaderBytes(p);
        case 1: return SusamuneModSegmentMemory(p,0);
        case 2: return SusamuneModSegmentMemory(p,1);
        case 3: return SusamuneModColdAddress(p);
        case 4: return SusamuneModColdSize(p);
    }
    return 0;
}
''', encoding="ascii")
        compiler = str(ROOT / "toolchain/clang.exe")
        common = ["-x", "c", "-std=c11", "-O2", "-fno-builtin", "-ffreestanding",
                  "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "scripts"),
                  "-I", str(ROOT / "include")]
        dll = self.path / "mod_v4.dll"
        subprocess.run([compiler, "--target=x86_64-pc-windows-msvc", *common, "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", str(source), "-o", str(dll)], check=True)
        self.objects = {}
        self.disassemblers = {}
        for name, target, options in (("ppc", "powerpc-gecko-ibm-kuribo-eabi", []),
                                      ("arm", "armeb-none-eabi", ["-mcpu=arm926ej-s"])):
            obj = self.path / f"mod_v4-{name}.o"
            subprocess.run([compiler, f"--target={target}", *options, *common,
                            "-c", str(source), "-o", str(obj)], check=True)
            subprocess.run([compiler, f"--target={target}", *options, *common,
                            "-S", str(source), "-o", str(obj.with_suffix(".s"))], check=True)
            self.objects[name] = obj
            kit, executable = (("devkitPPC", "powerpc-eabi-objdump.exe") if name == "ppc" else
                               ("devkitARM", "arm-none-eabi-objdump.exe"))
            disassembler = next((p / "launcher/nintendont_devkitpro" / kit / "bin" / executable
                                 for p in (ROOT, *ROOT.parents)
                                 if (p / "launcher/nintendont_devkitpro" / kit / "bin" / executable).is_file()), None)
            if disassembler is None:
                raise RuntimeError(f"missing {executable} for object audit")
            disassembly = subprocess.check_output([str(disassembler), "-d", str(obj)], text=True)
            obj.with_suffix(".disassembly").write_text(disassembly)
            self.disassemblers[name] = dict(path=str(disassembler), sha256=sha(disassembler.read_bytes()))
        gcc = Path(self.disassemblers["arm"]["path"]).with_name("arm-none-eabi-gcc.exe")
        obj = self.path / "mod_v4-arm-gnu89.o"
        kernel_flags = ["-mbig-endian", "-O2", "-std=gnu89", "-g", "-Wall", "-Werror",
                        "-mcpu=arm926ej-s", "-msoft-float", "-mfloat-abi=soft", "-fdata-sections",
                        "-ffunction-sections", "-fno-builtin-toupper", "-fno-builtin-memcpy",
                        "-fno-builtin-memset", "-fno-builtin-memcmp", "-fno-builtin-malloc", "-fno-builtin-free"]
        subprocess.run([str(gcc), *kernel_flags, "-I", str(ROOT / "include"), "-I", str(ROOT / "scripts"),
                        "-c", str(source), "-o", str(obj)], check=True)
        subprocess.run([str(gcc), *kernel_flags, "-I", str(ROOT / "include"), "-I", str(ROOT / "scripts"),
                        "-S", str(source), "-o", str(obj.with_suffix(".s"))], check=True)
        obj.with_suffix(".disassembly").write_text(subprocess.check_output(
            [self.disassemblers["arm"]["path"], "-d", str(obj)], text=True))
        self.objects["arm-gnu89"] = obj
        self.disassemblers["arm-gnu89"] = self.disassemblers["arm"]
        self.lib = C.CDLL(str(dll))
        self.lib.validate.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint, C.c_uint]
        self.lib.install.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint, C.c_uint,
                                    C.c_void_p, C.c_uint, C.c_uint]
        self.lib.production_validate.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
        self.lib.production_header.argtypes = [C.c_void_p, C.c_uint]
        self.lib.production_size.argtypes = [C.c_void_p]
        self.lib.production_size.restype = C.c_uint
        self.lib.production_info.argtypes = [C.c_void_p, C.c_uint]
        self.lib.production_info.restype = C.c_uint
        self.lib.production_install.argtypes = [C.c_void_p, C.c_uint, C.c_uint,
                                               C.c_void_p, C.c_uint, C.c_uint]

    def close(self):
        C.windll.kernel32.FreeLibrary(C.c_void_p(self.lib._handle))

    def run(self, encoded, game=None, flags=0, source_vma=None, destination_vma=None,
            capacity=REGION_BYTES, storage=None):
        game = GAMES["jp"] if game is None else game
        source_vma = stage(flags) if source_vma is None else source_vma
        destination_vma = BASES[game] if destination_vma is None else destination_vma
        storage = C.create_string_buffer(bytes([SENTINEL]) * (REGION_BYTES + 128)) if storage is None else storage
        # Deliberately unaligned host pointer proves the byte-oriented reader.
        source = C.create_string_buffer(b"X" + bytes(encoded) + b"Y")
        status = self.lib.install(C.addressof(source) + 1, len(encoded), game, flags, source_vma,
                                  C.addressof(storage) + 64, capacity, destination_vma)
        assert source.raw[:len(encoded) + 2] == b"X" + bytes(encoded) + b"Y"
        return status, storage


class ModV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-v4-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.h = Harness(cls.temp.name)
        cls.addClassCleanup(cls.h.close)

    def reject(self, encoded, **kwargs):
        result, memory = self.h.run(encoded, **kwargs)
        self.assertNotEqual(result, 0)
        self.assertEqual(memory.raw[:-1], bytes([SENTINEL]) * (REGION_BYTES + 128))

    def test_raw_quick_cold_and_environments(self):
        for flags in (0, 1):
            for cold in (False, True):
                for quick in (False, True):
                    result, memory = self.h.run(tiny(flags=flags, cold=cold, quick=quick), flags=flags)
                    self.assertEqual(result, 0)
                    expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
                    for i, (offset, _) in enumerate(CAPS):
                        expected[64 + offset:96 + offset] = bytes([0x30 + i]) * 32
                        expected[96 + offset:128 + offset] = bytes(32)
                    self.assertEqual(memory.raw[:-1], expected)

    def test_word_writer_partial_words_overlap_far_history_and_block_boundary(self):
        cases = []
        for literal_count in range(1, 8):
            for distance in range(1, literal_count + 1):
                cases.append([match_block(bytes(range(literal_count)), distance, 64)])
        cases.append([match_block(bytes(i % 251 for i in range(65535)), 65535, 66564)])
        cases.append([match_block(b"xyz", 3, 0x20000), match_block(b"ab", 2, 64)])
        for blocks in cases:
            raw = b"".join(b[1] for b in blocks)
            packed = struct.pack(">2I", 0x4D534C34, 0x20000) + b"".join(b[0] for b in blocks)
            segments = [dict(offset=0, raw=raw, quick=packed, memory_size=len(raw) + 4),
                        dict(offset=0x80000, raw=b"last", memory_size=8)]
            data = build_mod_v4(GAMES["jp"], segments, [])
            result, memory = self.h.run(data)
            self.assertEqual(result, 0)
            self.assertEqual(memory.raw[64:64 + len(raw)], raw)
            self.assertEqual(memory.raw[64 + len(raw):68 + len(raw)], bytes(4))

    def test_generated_target_object_has_no_byte_or_halfword_stores(self):
        for target, path in self.h.objects.items():
            assembly = path.with_suffix(".s").read_text()
            pattern = r"^\s*(?:strb\w*|strh\w*)\s" if target.startswith("arm") else r"^\s*(?:stb\w*|sth\w*)\s"
            self.assertEqual(re.findall(pattern, assembly, re.M), [], target)
            disassembly = path.with_suffix(".disassembly").read_text()
            pattern = r"\b(?:strb\w*|strh\w*)\s" if target.startswith("arm") else r"\b(?:stb\w*|sth\w*)\s"
            self.assertEqual(re.findall(pattern, disassembly), [], target)

    def test_header_fields_overflow_environment_and_wrong_game(self):
        for offset, value in ((0, 0), (4, 3), (8, GAMES["us"]), (12, BASES[GAMES["us"]]),
                              (16, 0xFFFFFFE0), (20, 0xFFFFFFFF), (24, 0xC0000),
                              (28, 0x98004), (28, 124), (32, 1), (32, 4), (44, 2),
                              (48, 1), (52, 1), (56, 1), (60, 1)):
            damaged = bytearray(tiny())
            put(damaged, offset, value)
            self.reject(seal(damaged))
        self.reject(tiny(), game=GAMES["pal"])
        self.reject(tiny(), flags=1)
        self.reject(tiny(), source_vma=stage(0) + 32)
        self.reject(tiny(), destination_vma=BASES[GAMES["jp"]] + 32)
        self.reject(tiny(), capacity=REGION_BYTES - 1)

    def test_descriptor_placements_sizes_kinds_and_overlapping_payloads(self):
        data = tiny(cold=True, quick=True)
        edits = ((0, 4), (4, 0x58004), (8, 0x58004), (4, 33), (8, 63),
                 (12, 0), (12, 0xFFFFFFE0), (16, 0xFFFFFFFF), (20, 2), (28, 1),
                 (32, 0), (32 + 8, 0x40004), (32 + 12, word(data, 64 + 12)),
                 (64, stage(0) + 0xC0), (64 + 4, 31), (64 + 8, 64),
                 (64 + 16, 64), (64 + 20, 0), (64 + 28, 1))
        for offset, value in edits:
            damaged = bytearray(data)
            put(damaged, 64 + offset, value)
            self.reject(seal(damaged))

    def test_header_payload_body_and_descriptor_crcs(self):
        data = tiny(cold=True, quick=True)
        for offset in (40, 36, 64 + 24, 64 + word(data, 64 + 12), 64 + 2 * 32 + 24):
            damaged = bytearray(data)
            damaged[offset] ^= 1
            self.reject(damaged)
        damaged = bytearray(data)
        damaged[64 + word(data, 64 + 12) + 20] ^= 1
        self.reject(seal(damaged))  # Valid outer CRC still requires the stored CRC.

    def test_canonical_padding_hook_bounds_and_trailing_bytes(self):
        data = tiny(quick=True)
        padding = 64 + word(data, 64 + 12) + word(data, 64 + 16)
        for offset in (padding, len(data) - 1):
            damaged = bytearray(data)
            damaged[offset] = 1
            self.reject(seal(damaged))
        hook = 64 + word(data, 16)
        for address in (0x7FFFFFFC, 0x8000561D, BASES[GAMES["jp"]], stage(0), 0xFFFFFFFC):
            damaged = bytearray(data)
            put(damaged, hook, address)
            self.reject(seal(damaged))
        self.reject(data + bytes(32))

    def test_every_small_container_truncation_preserves_entire_destination(self):
        data = tiny(cold=True, quick=True)
        for length in range(len(data)):
            self.reject(data[:length])

    def test_late_quick_corruption_with_all_crcs_repaired_is_atomic(self):
        damaged = bytearray(tiny(quick=True))
        late = 64 + word(damaged, 64 + 32 + 12)
        put(damaged, late + 8, 31)
        self.reject(seal_payload(damaged, 1))

    def test_pointer_wrap_null_alias_and_source_in_protected_hole(self):
        data = tiny()
        game, base = GAMES["jp"], BASES[GAMES["jp"]]
        memory = C.create_string_buffer(bytes([SENTINEL]) * REGION_BYTES)
        src = C.create_string_buffer(data)
        maximum = (1 << (C.sizeof(C.c_void_p) * 8)) - 1
        for pointer in (None, maximum - 1):
            self.assertNotEqual(self.h.lib.install(pointer, len(data), game, 0, stage(0), memory, REGION_BYTES, base), 0)
            self.assertNotEqual(self.h.lib.install(src, len(data), game, 0, stage(0), pointer, REGION_BYTES, base), 0)
        self.assertNotEqual(self.h.lib.install(src, len(data), game, 0, stage(0),
                                               C.addressof(memory) + 1, REGION_BYTES, base), 0)
        for offset in (0, 0x58000, 0x7FFC0, 0x80000):
            C.memmove(C.addressof(memory) + offset, data, len(data))
            before = memory.raw
            self.assertNotEqual(self.h.lib.install(C.addressof(memory) + offset, len(data), game, 0,
                                                   stage(0), memory, REGION_BYTES, base), 0)
            self.assertEqual(memory.raw, before)

    def test_regional_ceiling_exact_and_above(self):
        game = GAMES["jp"]
        segments = [dict(offset=0, raw=bytes(0x57F80), memory_size=0x57F80),
                    dict(offset=0x80000, raw=bytes(0x2E000), memory_size=0x2E000)]
        data = build_mod_v4(game, segments, [])
        self.assertEqual(len(data), 0x86000)
        self.assertEqual(self.h.run(data)[0], 0)
        segments[1]["raw"] += bytes(4)
        segments[1]["memory_size"] += 4
        with self.assertRaises(ValueError):
            build_mod_v4(game, segments, [])
        self.reject(data + bytes(32))

    def test_packer_rejects_wrong_cold_vma_bad_raw_and_wrong_quick(self):
        segments = [dict(offset=o, raw=b"1234", memory_size=4) for o, _ in CAPS]
        with self.assertRaises(ValueError):
            build_mod_v4(GAMES["jp"], segments, [], cold=bytes(32), cold_vma=stage(0) + 0x40)
        segments[0]["quick"] = b"MSL4garbage"
        with self.assertRaises(ValueError):
            build_mod_v4(GAMES["jp"], segments, [])
        del segments[0]["quick"]
        segments[0]["memory_size"] = 3
        with self.assertRaises(ValueError):
            build_mod_v4(GAMES["jp"], segments, [])


def verify_install(harness, encoded, game, segments, flags=0):
    status, memory = harness.run(encoded, game=game, flags=flags)
    assert status == 0
    expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
    for segment in segments:
        start = 64 + segment["offset"]
        raw, size = segment["raw"], segment["memory_size"]
        expected[start:start + len(raw)] = raw
        expected[start + len(raw):start + size] = bytes(size - len(raw))
    assert memory.raw[:-1] == expected
    # Simulate reset damage in installed hot bytes; immutable transport is reused.
    for offset, _ in CAPS:
        C.memset(C.addressof(memory) + 64 + offset, 0xEE, 32)
    status, memory = harness.run(encoded, game=game, flags=flags, storage=memory)
    assert status == 0 and memory.raw[:-1] == expected
    # Hook words are deliberately not published by this installer.
    damaged = bytearray(encoded)
    descriptor = 64 + 32
    packed = 64 + word(damaged, descriptor + 12)
    end = packed + word(damaged, descriptor + 16)
    cursor = packed + 8
    while cursor < end:
        last = cursor
        cursor += 8 + (word(damaged, cursor + 4) & 0x7FFFFFFF)
    put(damaged, last, 0)
    seal_payload(damaged, 1)
    status, untouched = harness.run(damaged, game=game, flags=flags)
    assert status != 0 and untouched.raw[:-1] == bytes([SENTINEL]) * (REGION_BYTES + 128)
    production = C.create_string_buffer(bytes([SENTINEL]) * (REGION_BYTES + 128))
    source = C.create_string_buffer(encoded)
    status = harness.lib.production_install(source, game, len(encoded), C.addressof(production) + 64,
                                             REGION_BYTES, BASES[game])
    if flags:
        assert status != 0 and production.raw[:-1] == bytes([SENTINEL]) * (REGION_BYTES + 128)
    else:
        assert status == 0 and production.raw[:-1] == expected
    return memory.raw[64:64 + REGION_BYTES]


def verify_timer_bytes(memory, name, timer_receipt):
    expected = timer_receipt["builds"][f"console-{name}"]["symbols"]
    for symbol in expected.values():
        offset, size = symbol["address"] - BASES[GAMES[name]], symbol["size"]
        assert offset >= 0 and offset + size <= len(memory)
        actual = memory[offset:offset + size]
        if symbol["sha256"] is None:
            assert actual == bytes(size)
        else:
            assert sha(actual) == symbol["sha256"]
    return len(expected)


def artifacts(receipt_path, output, cold_receipt_path=None, transport_receipt_path=None):
    from elftools.elf.elffile import ELFFile
    rows, objects, audits = [], {}, {}
    timer_path = ROOT / "doc/timewarp-timer-baseline.json"
    timer_receipt = json.loads(timer_path.read_text())
    with tempfile.TemporaryDirectory(prefix="timewarp-v4-artifacts-") as temp:
        harness = Harness(temp)
        try:
            for name, game, segments, writes, baseline in baseline_inputs(receipt_path):
                encoded = build_mod_v4(game, segments, writes)
                memory = verify_install(harness, encoded, game, segments)
                timer_count = verify_timer_bytes(memory, name, timer_receipt)
                rows.append(dict(region=name, container_bytes=len(encoded),
                                 container_sha256=sha(encoded), exact_hot_and_bss=True,
                                 all_other_bytes_including_timer_scratch_unchanged=True,
                                 timer_symbols_exact=timer_count, cold_present=False,
                                 late_malformed_quick_no_writes=True, reset_reinstall_exact=True))
                print(f"{name}: exact hot/BSS; protected gaps intact; reset reinstall exact")
            if cold_receipt_path:
                for name, tag, game, flags, segments, encoded, baseline, evidence in cold_inputs(
                        cold_receipt_path, transport_receipt_path):
                    memory = verify_install(harness, encoded, game, segments, flags)
                    timer_count = verify_timer_bytes(memory, name, timer_receipt)
                    cold_descriptor = 64 + 2 * 32
                    target = word(encoded, cold_descriptor)
                    payload_offset = word(encoded, cold_descriptor + 12)
                    stored = word(encoded, cold_descriptor + 16)
                    assert target == stage(flags) + 64 + payload_offset == evidence["cold"]["vma"]
                    cold = encoded[64 + payload_offset:64 + payload_offset + stored]
                    assert sha(cold) == evidence["cold"]["payload_sha256"]
                    for hole in evidence["retained"]["holes"]:
                        begin, end = hole["begin"] - BASES[game], hole["end"] - BASES[game]
                        assert memory[begin:end] == bytes(end - begin)
                    rows.append(dict(region=name, placement=tag, flags=flags,
                                     container_bytes=len(encoded), container_sha256=sha(encoded),
                                     exact_hot_and_bss=True, reset_reinstall_exact=True,
                                     late_malformed_quick_no_writes=True, cold_present=True,
                                     cold_vma=target, cold_source_unchanged=True,
                                     all_other_bytes_including_timer_scratch_unchanged=True,
                                     timer_symbols_exact=timer_count,
                                     zeroed_reusable_mem1_bytes=evidence["retained"]["reusable_mem1_bytes"],
                                     pilot_scope="Console-baseline code; both cold address placements are link/transport proofs, not emulator/gameplay builds."))
                    print(f"{name} {tag}: cold VMA exact; {timer_count} timer symbols exact; reset reinstall exact")
            for target, path in harness.objects.items():
                with path.open("rb") as stream:
                    elf = ELFFile(stream)
                    objects[target] = {s.name: s["sh_size"] for s in elf.iter_sections()
                                       if s["sh_flags"] & 2 and s["sh_size"]}
                disassembly = path.with_suffix(".disassembly").read_text()
                pattern = r"\b(?:strb\w*|strh\w*)\s" if target.startswith("arm") else r"\b(?:stb\w*|sth\w*)\s"
                assert not re.findall(pattern, disassembly)
                output.parent.mkdir(parents=True, exist_ok=True)
                retained = output.parent / f"mod-v4-{target}.disassembly"
                retained.write_text(disassembly)
                audits[target] = dict(disassembler=harness.disassemblers[target],
                                      disassembly_sha256=sha(retained.read_bytes()),
                                      narrow_stores=0, pending_output_bytes=4)
        finally:
            harness.close()
    result = dict(scope="Private native-C V4 installation from actual PPC-compressed baseline hot segments.",
                  limits="PPC and big-endian ARM compiled only. No signature, actual Wii boot, cache maintenance, hook publication or elapsed timing.",
                  input_receipt_sha256=sha(receipt_path.read_bytes()),
                  timer_baseline_sha256=sha(timer_path.read_bytes()),
                  source_sha256={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in
                                 (ROOT / "include/susamune/mod_bin.h", ROOT / "include/susamune/mod_v4.h",
                                  ROOT / "include/susamune/mod_quick.h", ROOT / "scripts/timewarp/mod_v4.h",
                                  ROOT / "scripts/timewarp/boot_quick.h", ROOT / "scripts/timewarp_mod_v4.py",
                                  ROOT / "scripts/mod_transport.py", Path(__file__))},
                  allocated_object_sections=objects, word_output_object_audits=audits, regions=rows)
    if cold_receipt_path:
        result.update(cold_receipt_sha256=sha(cold_receipt_path.read_bytes()))
        if transport_receipt_path:
            result['transport_receipt_sha256'] = sha(transport_receipt_path.read_bytes())
        else:
            result['cold_encoding'] = 'deterministic host boot encoder'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-mod-v4/install-receipt.json")
    parser.add_argument("--cold-receipt", type=Path)
    parser.add_argument("--transport-receipt", type=Path)
    parser.add_argument("--host-encode", action="store_true")
    args, remaining = parser.parse_known_args()
    if args.receipt:
        if args.host_encode and (not args.cold_receipt or args.transport_receipt):
            parser.error("host encoding requires a cold receipt and no PPC transport receipt")
        if not args.host_encode and bool(args.cold_receipt) != bool(args.transport_receipt):
            parser.error("cold and transport receipts are required together, or use --host-encode")
        artifacts(args.receipt, args.output, args.cold_receipt, args.transport_receipt)
    else:
        unittest.main(argv=[__file__] + remaining)
