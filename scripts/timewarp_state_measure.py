"""Measure Quick-stream capacity and exact block sharing on private captures.

Example (captures are only read; outputs belong in this checkout's build/):
  python scripts/timewarp_state_measure.py --capture-root PATH_TO_RELEASE_CHECKOUT

Native x64 encoding is a screening result: PPC selects different LZ4 hashes.
Captured streams are independently decoded before their sizes enter a receipt.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
BLOCK_BYTES = 0x20000
FRAME = struct.pack(">II", 0x4D534C34, BLOCK_BYTES)
POOL_BYTES = 0xFF0000 + 0x200000
MIB = 1024 * 1024
DEFAULT_SETS = {
    "peaceful-plaza": "build/state-capacity-pal/peaceful-plaza",
    "bianco-plant-plaza": "build/state-capacity-pal/bianco-plant-plaza",
    "feedback4-user": "build/v2.3.3-feedback4/state-speed/user-capture",
    "feedback5-save": "build/v2.3.3-feedback5/save-lifecycle/captures",
    "feedback5-final": "build/v2.3.3-feedback5/final-lifecycle/captures",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode_lz4(encoded, expected):
    """Independent bounded decoder; repeated matches may overlap themselves."""
    cursor = 0
    result = bytearray()

    def length(base):
        nonlocal cursor
        if base == 15:
            while True:
                if cursor == len(encoded):
                    raise ValueError("Missing length extension")
                value = encoded[cursor]
                cursor += 1
                base += value
                if value != 255:
                    break
        return base

    while cursor < len(encoded):
        token = encoded[cursor]
        cursor += 1
        literals = length(token >> 4)
        if literals > len(encoded) - cursor or literals > expected - len(result):
            raise ValueError("Literal overrun")
        result.extend(encoded[cursor:cursor + literals])
        cursor += literals
        if cursor == len(encoded):
            break
        if cursor + 2 > len(encoded):
            raise ValueError("Missing match offset")
        distance = int.from_bytes(encoded[cursor:cursor + 2], "little")
        cursor += 2
        amount = length(token & 15) + 4
        if not distance or distance > len(result) or amount > expected - len(result):
            raise ValueError("Match overrun")
        pattern = result[-distance:]
        result.extend((pattern * ((amount + distance - 1) // distance))[:amount])
    if len(result) != expected:
        raise ValueError("Wrong decoded block length")
    return bytes(result)


def quick_blocks(encoded, raw):
    if encoded[:8] != FRAME:
        raise ValueError("Unsupported Quick frame")
    cursor, raw_offset = 8, 0
    blocks = []
    while raw_offset < len(raw):
        start = cursor
        if cursor + 8 > len(encoded):
            raise ValueError("Missing block header")
        raw_bytes, packed_word = struct.unpack_from(">II", encoded, cursor)
        cursor += 8
        plain = bool(packed_word & 0x80000000)
        packed_bytes = packed_word & 0x7FFFFFFF
        if raw_bytes != min(BLOCK_BYTES, len(raw) - raw_offset) or not packed_bytes:
            raise ValueError("Wrong block length")
        if (packed_bytes != raw_bytes if plain else packed_bytes >= raw_bytes):
            raise ValueError("Wrong compressed length")
        if packed_bytes > len(encoded) - cursor:
            raise ValueError("Short block payload")
        payload = encoded[cursor:cursor + packed_bytes]
        decoded = payload if plain else decode_lz4(payload, raw_bytes)
        if decoded != raw[raw_offset:raw_offset + raw_bytes]:
            raise ValueError("Decoded bytes differ from capture")
        cursor += packed_bytes
        blocks.append(encoded[start:cursor])
        raw_offset += raw_bytes
    if cursor != len(encoded):
        raise ValueError("Trailing Quick bytes")
    return blocks


def check_stream(encoded, raw):
    if encoded[:4] == b"MSL4":
        blocks = quick_blocks(encoded, raw)
        return "Quick", blocks
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(encoded, len(raw) + 1)
    if (decoded != raw or not decoder.eof or decoder.unused_data or
            decoder.unconsumed_tail):
        raise ValueError("Invalid Deflate stream or decoded bytes differ")
    return "Deflate", None


def capacity(total, pool):
    return {
        "stream_bytes": total,
        "minimum_pool_growth_bytes": max(0, total - pool),
        "thresholds": [{
            "growth_bytes": growth,
            "capacity_bytes": pool + growth,
            "fits": total <= pool + growth,
            "headroom_bytes": pool + growth - total,
        } for growth in (0, MIB, 2 * MIB)],
    }


def sharing(streams, pool, digest=hashlib.sha256):
    """Hash lookup is followed by complete format/header/payload equality."""
    buckets = defaultdict(list)
    unique = []
    rows = []
    saved = references = 0
    for name, blocks in streams:
        duplicates, slot_saved = 0, 0
        for block in blocks:
            key = digest(FRAME + block).digest()
            if any(candidate == block for candidate in buckets[key]):
                duplicates += 1
                slot_saved += len(block)
            else:
                buckets[key].append(block)
                unique.append(block)
        saved += slot_saved
        references += len(blocks)
        rows.append({"slot": name, "blocks": len(blocks),
                     "duplicate_blocks": duplicates,
                     "gross_saved_bytes": slot_saved})
    total = 8 * len(streams) + sum(len(b) for _, bs in streams for b in bs)
    # Illustrative overhead only; this does not define a runtime allocator.
    illustrated = (8 * len(streams) + sum((len(b) + 31) & ~31 for b in unique)
                   + 16 * len(unique) + 4 * references)
    return {
        "scope": "Only the listed Quick streams; missing/Deflate slots are excluded.",
        "stream_count": len(streams),
        "block_references": references,
        "unique_blocks": len(unique),
        "gross_saved_bytes": saved,
        "gross_saved_percent": saved * 100 / total if total else 0,
        "gross_upper_bound_capacity": capacity(total - saved, pool),
        "illustrative_overhead": {
            "assumption": "32-byte chunks, 16-byte unique descriptors, 4-byte references; no hash index or transaction/recovery reserve.",
            "bytes_above_gross_lower_bound": illustrated - (total - saved),
            "capacity": capacity(illustrated, pool),
        },
        "slots_in_order": rows,
    }


class HostQuick:
    def __enter__(self):
        # Reuse the production-code harness without running its unittest suite.
        from test_state_codec import StateCodecTests, Span, Result, Guarded
        self.suite, self.Span, self.Result, self.Guarded = StateCodecTests, Span, Result, Guarded
        try:
            self.suite.setUpClass()
        except BaseException:
            self.suite.doClassCleanups()
            raise
        return self

    def __exit__(self, *_):
        self.suite.doClassCleanups()

    def encode(self, raw):
        lib = self.suite.lib
        owner = C.create_string_buffer(raw)
        source = self.Span(C.addressof(owner), len(raw))
        work = self.Guarded(lib.workspace())
        output = self.Guarded(len(raw) + 65536)
        dest = self.Span(output.ptr, output.size)
        result = self.Result()
        lib.packQuick(work.ptr, work.size, C.byref(source), 1,
                      C.byref(dest), 1, C.byref(result))
        if (result.status != 0 or result.raw != len(raw) or
                result.adler != zlib.adler32(raw) or not work.guards() or not output.guards()):
            raise RuntimeError("Production host Quick encoding failed")
        return C.string_at(output.ptr, result.compressed)


class PpcQuick:
    """An owned, game-free Dolphin process executes the production PPC codec."""
    CONTROL, INPUT, WORK, OUTPUT = 0x81700000, 0x80080000, 0x81600000, 0x80F00000
    MAGIC = b"TWQK"

    def __init__(self, dolphin, folder, *, incremental=False):
        self.dolphin, self.folder = dolphin.resolve(), folder
        self.incremental = incremental
        self.process = None
        self.handle = None
        self.sequence = 0
        self.evidence = {}

    def __enter__(self):
        try:
            self.start()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=10)
            self.evidence["owned_process_stopped"] = self.process.poll() is not None

    def start(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        source = self.folder / "codec-bench.cpp"
        source.write_text('#define TW_BENCH_BLOCKS ' + str(int(self.incremental)) + '\n#include "' + (ROOT / "src/state_codec.cpp").as_posix() + '"\n' + r'''
extern "C" {
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n) {
 unsigned char*o=(unsigned char*)d;const unsigned char*i=(const unsigned char*)s;
 while(n--)*o++=*i++;return d;
}
void *memset(void*d,int v,__SIZE_TYPE__ n) {
 unsigned char*o=(unsigned char*)d;while(n--)*o++=(unsigned char)v;return d;
}
void *memmove(void*d,const void*s,__SIZE_TYPE__ n) {
 unsigned char*o=(unsigned char*)d;const unsigned char*i=(const unsigned char*)s;
 if(o<i){for(__SIZE_TYPE__ j=0;j<n;++j)o[j]=i[j];}
 else {while(n){--n;o[n]=i[n];}}return d;
}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n) {
 const unsigned char*x=(const unsigned char*)a,*y=(const unsigned char*)b;
 while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;
}
#if TW_BENCH_BLOCKS
struct BlockSink {unsigned char *next; unsigned left;};
bool emitBlock(void *ctx,const StateCodec::ReadSpan (&parts)[2]) {
 BlockSink *sink=(BlockSink*)ctx;
 for(unsigned i=0;i<2;++i) {
  if(parts[i].size>sink->left)return false;
  memcpy(sink->next,parts[i].data,parts[i].size);
  sink->next+=parts[i].size;sink->left-=parts[i].size;
 }
 return true;
}
#endif
void bench() {
 volatile unsigned int*box=(volatile unsigned int*)0x81700000;
 for(unsigned int i=0;i<16;++i)box[i]=0;
 box[8]=StateCodec::workspaceSize();box[0]=0x5457514b;
 unsigned int seen=0;
 for(;;) {
  unsigned int seq=box[1];if(seq==seen)continue;
  seen=seq;unsigned int size=box[2];
  if(!size||size>0xe80000){box[4]=1;box[3]=seq;continue;}
  *(volatile unsigned int*)0x815ffffc=0xdeadbeef;
  *(volatile unsigned int*)0x8164e000=0xdeadbeef;
  StateCodec::ReadSpan input={(void*)0x80080000,size};
  StateCodec::WriteSpan output={(void*)0x80f00000,0x6f0000};
#if TW_BENCH_BLOCKS
  unsigned char *dest=(unsigned char*)output.data;
  const unsigned char frame[8]={0x4d,0x53,0x4c,0x34,0,2,0,0};
  memcpy(dest,frame,8);BlockSink sink={dest+8,output.size-8};
  StateCodec::Result result=StateCodec::compressQuickBlocks((void*)0x81600000,0x4e000,
   &input,1,&output,1,emitBlock,&sink);
#else
  StateCodec::Result result=StateCodec::compress((void*)0x81600000,0x4e000,
   &input,1,&output,1,false,true);
#endif
  box[4]=result.status;box[5]=result.compressedBytes;
  box[6]=result.rawBytes;box[7]=result.adler32;
  box[9]=*(volatile unsigned int*)0x815ffffc;
  box[10]=*(volatile unsigned int*)0x8164e000;
  asm volatile("sync" ::: "memory");box[3]=seq;
 }
}
}
asm(".section .text.start,\"ax\"\n.globl _start\n_start:\n"
    "lis 1,0x815f\nori 1,1,0xf000\nli 0,0\nstw 0,0(1)\n"
    "mfmsr 3\nrlwinm 3,3,0,17,15\nmtmsr 3\nisync\nbl bench\nb .\n");
''', encoding="ascii")
        link = self.folder / "codec-bench.ld"
        link.write_text("ENTRY(_start)\nSECTIONS { . = 0x80004000; "
                        ".text : { *(.text.start) *(.text*) *(.foxtrot.text*) . = ALIGN(32); } "
                        ". = ALIGN(32); .rodata : { *(.rodata*) *(.foxtrot.rodata*) . = ALIGN(32); } "
                        ". = ALIGN(32); .data : { *(.data*) *(.foxtrot.data*) *(.got*) . = ALIGN(32); } "
                        ". = ALIGN(32); .bss : { *(.bss*) *(.foxtrot.bss*) *(COMMON) . = ALIGN(32); } "
                        "/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n", encoding="ascii")
        obj, elf, dol = [self.folder / ("codec-bench." + suffix) for suffix in ("o", "elf", "dol")]
        commands = [
            [str(ROOT / "toolchain/clang++.exe"), "--target=powerpc-gecko-ibm-kuribo-eabi",
             "-O2", "-fno-exceptions", "-fno-rtti", "-fno-builtin", "-ffunction-sections",
             "-fdata-sections", "-fno-unwind-tables", "-nostdlib", "-I", str(ROOT / "include"),
             "-c", str(source), "-o", str(obj)],
            [str(ROOT / "toolchain/ld.lld.exe"), "--gc-sections", "-T", str(link), str(obj), "-o", str(elf)],
            [sys.executable, str(ROOT / "scripts/elf2dol.py"), str(elf), str(dol)],
        ]
        for command in commands:
            subprocess.run(command, check=True)
        profile = Path(tempfile.mkdtemp(prefix="profile-", dir=self.folder))
        (profile / "Config").mkdir()
        (profile / "Config/Dolphin.ini").write_text(
            "[Core]\nHLE_BS2 = True\nCPUThread = False\nCPUCore = 1\nFastmem = False\n"
            "MMU = False\nEmulationSpeed = 0.0\nDefaultISO = \nEnableCheats = False\n"
            "SlotA = 0\nSlotB = 0\nGFXBackend = Null\n"
            "[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
            "PauseOnFocusLost = False\n[Analytics]\nEnabled = False\n", encoding="ascii")
        (profile / "Config/Logger.ini").write_text(
            "[Options]\nWriteToFile = True\nVerbosity = 4\n"
            "[Logs]\nBOOT = True\nCORE = True\nMEMMAP = True\nPOWERPC = True\nCOMMON = True\n", encoding="ascii")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags, startup.wShowWindow = 1, 0
        self.process = subprocess.Popen([str(self.dolphin), "-b", "-u", str(profile), "-e", str(dol)], startupinfo=startup)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [C.c_ulong, C.c_bool, C.c_ulong]
        self.kernel.OpenProcess.restype = C.c_void_p
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.kernel.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p]
        self.kernel.WriteProcessMemory.argtypes = self.kernel.ReadProcessMemory.argtypes
        self.kernel.VirtualQueryEx.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t]
        self.kernel.VirtualQueryEx.restype = C.c_size_t
        self.handle = self.kernel.OpenProcess(0x438, False, self.process.pid)
        if not self.handle:
            raise OSError(C.get_last_error(), "Cannot open owned Dolphin process")
        deadline = time.monotonic() + 30
        self.mem1 = None
        while self.mem1 is None:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Standalone PPC codec handshake did not start")
            self.find_memory()
            time.sleep(0.1)
        self.evidence.update({"kind": "Production PPC codec in a standalone game-free Dolphin DOL",
                              "incremental_quick_blocks": self.incremental,
                              "dolphin_path": str(self.dolphin), "dolphin_sha256": sha(self.dolphin.read_bytes()),
                              "owned_pid": self.process.pid, "profile": str(profile),
                              "dol_sha256": sha(dol.read_bytes()), "commands": commands,
                              "workspace_bytes": struct.unpack(">I", self.read(self.CONTROL + 32, 4))[0]})

    def host_read(self, address, size, required=True):
        data = C.create_string_buffer(size)
        read = C.c_size_t()
        success = self.kernel.ReadProcessMemory(self.handle, address, data, size, C.byref(read))
        if not success or read.value != size:
            if required:
                raise OSError(C.get_last_error(), "Owned-process read failed")
            return None
        return data.raw

    def find_memory(self):
        class MemoryInfo(C.Structure):
            _fields_ = [("base", C.c_void_p), ("allocation", C.c_void_p), ("aprotect", C.c_ulong),
                        ("size", C.c_size_t), ("state", C.c_ulong), ("protect", C.c_ulong), ("kind", C.c_ulong)]
        address = 0
        while address < 0x7FFFFFFFFFFF:
            info = MemoryInfo()
            if not self.kernel.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
                break
            base = int(info.base or 0)
            if info.state == 0x1000 and info.protect & 0xFF in (2, 4, 8, 0x20, 0x40, 0x80):
                if info.size >= 0x1800000 and self.host_read(base + 0x1700000, 4, False) == self.MAGIC:
                    self.mem1 = base
            address = base + info.size

    def address(self, guest):
        if 0x80000000 <= guest < 0x81800000:
            return self.mem1 + guest - 0x80000000
        raise ValueError("Guest address outside the owned benchmark buffers")

    def read(self, guest, size):
        return self.host_read(self.address(guest), size)

    def write(self, guest, data):
        written = C.c_size_t()
        if not self.kernel.WriteProcessMemory(self.handle, self.address(guest), data, len(data), C.byref(written)) or written.value != len(data):
            raise OSError(C.get_last_error(), "Owned-process write failed")

    def encode(self, raw):
        if not 0 < len(raw) <= 0xE80000:
            raise ValueError("Raw capture exceeds the standalone PPC input buffer")
        self.write(self.INPUT, raw)
        self.write(self.CONTROL + 8, struct.pack(">I", len(raw)))
        self.sequence += 1
        self.write(self.CONTROL + 4, struct.pack(">I", self.sequence))
        deadline = time.monotonic() + 60
        while struct.unpack(">I", self.read(self.CONTROL + 12, 4))[0] != self.sequence:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("PPC compression did not complete")
            time.sleep(0.01)
        words = struct.unpack(">11I", self.read(self.CONTROL, 44))
        if (words[4] or words[6] != len(raw) or words[7] != zlib.adler32(raw) or
                words[9:11] != (0xDEADBEEF, 0xDEADBEEF) or not 0 < words[5] <= 0x6F0000):
            raise RuntimeError(f"PPC compression failed: {words}")
        if self.read(self.INPUT, len(raw)) != raw:
            raise RuntimeError("PPC codec changed its input capture")
        return self.read(self.OUTPUT, words[5])


def measure_set(name, folder, pool, host, ppc=None, generated=None):
    rows, captured_quick = [], []
    generated_quick = {kind: [] for kind, encoder in (("host_x64", host), ("ppc", ppc)) if encoder}
    existing_total = 0
    existing_count = 0
    for slot in range(1, 4):
        path = folder / f"slot{slot}.raw"
        raw = path.read_bytes()
        row = {"slot": slot, "raw_path": str(path.resolve()),
               "raw_bytes": len(raw), "raw_sha256": sha(raw)}
        packed_path = path.with_suffix(".packed")
        if packed_path.is_file():
            packed = packed_path.read_bytes()
            codec, blocks = check_stream(packed, raw)
            row["captured"] = {"path": str(packed_path.resolve()), "codec": codec,
                               "bytes": len(packed), "sha256": sha(packed),
                               "decoded_matches_raw": True}
            existing_count += 1
            existing_total += len(packed)
            if blocks is not None:
                captured_quick.append((slot, blocks))
        for kind, encoder in (("host_x64", host), ("ppc", ppc)):
            if not encoder:
                continue
            packed = encoder.encode(raw)
            blocks = quick_blocks(packed, raw)
            generated_quick[kind].append((slot, blocks))
            row[kind + "_quick"] = {"bytes": len(packed), "sha256": sha(packed),
                                    "blocks": len(blocks), "decoded_matches_raw": True}
            if row.get("captured", {}).get("codec") == "Quick":
                row[kind + "_quick"]["same_bytes_as_captured"] = sha(packed) == row["captured"]["sha256"]
            if generated:
                destination = generated / name / f"slot{slot}.{kind}-quick"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(packed)
                row[kind + "_quick"]["path"] = str(destination.resolve())
        rows.append(row)
    result = {"name": name, "slots": rows}
    if existing_count:
        result["captured_streams"] = {"slot_count": existing_count,
                                      "capacity": capacity(existing_total, pool)}
    if captured_quick:
        result["captured_quick_sharing"] = sharing(captured_quick, pool)
    for kind, streams in generated_quick.items():
        total = sum(row[kind + "_quick"]["bytes"] for row in rows)
        result[kind + "_all_quick_capacity"] = capacity(total, pool)
        result[kind + "_all_quick_sharing"] = sharing(streams, pool)
    return result


class MeasurementTests(unittest.TestCase):
    def test_quick_validation_and_trailing_bytes(self):
        raw = b"abc"
        block = struct.pack(">II", 3, 0x80000003) + raw
        self.assertEqual(quick_blocks(FRAME + block, raw), [block])
        for encoded in (FRAME + block + b"x", FRAME + block[:-1],
                        FRAME + struct.pack(">II", 3, 0x80000002) + b"ab"):
            with self.assertRaises(ValueError):
                quick_blocks(encoded, raw)
        with self.assertRaises(ValueError):
            quick_blocks(FRAME + block, b"abd")

    def test_overlapping_lz4_match_and_errors(self):
        self.assertEqual(decode_lz4(b"\x14a\x01\x00", 9), b"a" * 9)
        for encoded in (b"\x14a\x00\x00", b"\x14a\x02\x00", b"\xf0"):
            with self.assertRaises(ValueError):
                decode_lz4(encoded, 9)

    def test_dedup_compares_bytes_after_hash_collision(self):
        class Collision:
            def __init__(self, _):
                pass

            def digest(self):
                return b"collision"

        result = sharing([(1, [b"first", b"other"]), (2, [b"first"])], 20, Collision)
        self.assertEqual(result["unique_blocks"], 2)
        self.assertEqual(result["gross_saved_bytes"], 5)
        self.assertEqual(result["gross_upper_bound_capacity"]["stream_bytes"], 26)

    def test_capacity_boundary(self):
        self.assertTrue(capacity(20, 20)["thresholds"][0]["fits"])
        self.assertFalse(capacity(21, 20)["thresholds"][0]["fits"])
        self.assertEqual(capacity(21, 20)["minimum_pool_growth_bytes"], 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, help="Read the five historical triples beneath this checkout")
    parser.add_argument("--set", action="append", default=[], metavar="LABEL=DIRECTORY")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-state-measure/receipt.json")
    parser.add_argument("--pool-bytes", type=lambda value: int(value, 0), default=POOL_BYTES)
    parser.add_argument("--skip-host-quick", "--captured-only", dest="skip_host_quick", action="store_true", help="Skip native x64 production-code encoding")
    parser.add_argument("--ppc-dolphin", type=Path, help="Run the production PPC codec in an owned standalone Dolphin process (Windows)")
    parser.add_argument("--save-generated-streams", action="store_true", help="Retain checked generated streams beside the JSON receipt")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MeasurementTests))
        return 0 if result.wasSuccessful() else 1
    sets = {name: args.capture_root / path for name, path in DEFAULT_SETS.items()} if args.capture_root else {}
    for item in args.set:
        if "=" not in item:
            parser.error("--set requires LABEL=DIRECTORY")
        name, path = item.split("=", 1)
        if not name or name in sets or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
            parser.error("Capture labels must be unique ASCII letters, digits, hyphens or underscores")
        sets[name] = Path(path)
    if not sets or args.pool_bytes <= 0:
        parser.error("Supply --capture-root or --set and a positive pool size")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "build").resolve()):
        parser.error("Receipts must stay inside this checkout's ignored build/ directory")
    for folder in sets.values():
        if output.is_relative_to(folder.resolve()):
            parser.error("Output cannot overwrite the input capture directory")
    sources = ["src/state_codec.cpp", "vendor/lz4/lz4.c", "vendor/lz4/lz4.h",
               "vendor/lz4/state_lz4_config.h", "include/susamune/state_slot_pool.h",
               "include/susamune/mem2_map.h", "scripts/test_state_codec.py",
               "scripts/timewarp_state_measure.py"]
    receipt = {
        "scope": "Private read-only capture measurement; no gameplay, Wii timing, allocator, or portability claims.",
        "host_scope": "Native x64 U32/hash5 screening only. PPC uses byPtr/hash4; host sizes and sharing do not establish PPC results.",
        "dedup_scope": "Gross upper bound removes only exactly equal complete encoded blocks including length/plain flags. Each frame header is retained. Descriptor/index/alignment/recovery costs are not free bytes.",
        "pool_bytes": args.pool_bytes,
        "pool_basis": "Current expanded pool = 0xFF0000 snapshot + 0x200000 extra; metadata and codec workspaces are separate.",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {path: sha((ROOT / path).read_bytes()) for path in sources},
        "sets": [],
    }

    def run(host, ppc):
        for name, folder in sets.items():
            result = measure_set(name, folder, args.pool_bytes, host, ppc,
                                 output.parent / "generated" if args.save_generated_streams else None)
            receipt["sets"].append(result)
            summary = {"set": name, "captured_bytes": result.get("captured_streams", {}).get("capacity", {}).get("stream_bytes")}
            for kind, encoder in (("host_x64", host), ("ppc", ppc)):
                if encoder:
                    summary.update({kind + "_quick_bytes": result[kind + "_all_quick_capacity"]["stream_bytes"],
                                    kind + "_growth_needed": result[kind + "_all_quick_capacity"]["minimum_pool_growth_bytes"],
                                    kind + "_dedup_gross_bytes": result[kind + "_all_quick_sharing"]["gross_saved_bytes"]})
            print(json.dumps(summary), flush=True)

    with ExitStack() as stack:
        host = stack.enter_context(HostQuick()) if not args.skip_host_quick else None
        ppc = stack.enter_context(PpcQuick(args.ppc_dolphin, output.parent / "ppc")) if args.ppc_dolphin else None
        if ppc:
            receipt["ppc_scope"] = "Actual production big-endian 32-bit PPC instruction execution on private captured bytes in Dolphin; no Wii elapsed-time or in-game lifecycle claim."
            receipt["ppc_execution"] = ppc.evidence
        run(host, ppc)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Receipt: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
