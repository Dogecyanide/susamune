"""Test the private bounded C block pool; optionally replay exact PPC receipts.

Nothing in this harness installs the pool in gameplay or measures Wii timing.
"""
import argparse
import ctypes as C
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
import zlib

from timewarp_state_measure import FRAME, BLOCK_BYTES, quick_blocks

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 0x8000
MAX_BLOCKS = 256
MAX_DESCRIPTORS = MAX_BLOCKS * 4
MAX_BANKS = 5


class Memory(C.Structure):
    _fields_ = [("banks", C.c_void_p * MAX_BANKS), ("sizes", C.c_uint * MAX_BANKS),
                ("count", C.c_uint)]


class Chunk(C.Structure):
    _fields_ = [("offset", C.c_uint), ("size", C.c_uint), ("hash", C.c_uint),
                ("refs", C.c_ushort), ("reserved", C.c_ushort)]


class Slot(C.Structure):
    _fields_ = [("count", C.c_uint), ("packed", C.c_uint), ("raw", C.c_uint),
                ("tag", C.c_uint), ("ids", C.c_ushort * MAX_BLOCKS)]


class Directory(C.Structure):
    _fields_ = [("magic", C.c_uint), ("sizes", C.c_uint * MAX_BANKS), ("bank_count", C.c_uint),
                ("high_water", C.c_uint), ("target", C.c_uint),
                ("slots", Slot * 4), ("chunks", Chunk * MAX_DESCRIPTORS)]


def plain(payload):
    return struct.pack(">II", len(payload), len(payload) | 0x80000000) + payload


def compressed_marker(marker, raw=BLOCK_BYTES):
    # Allocator tests use header-valid tokens; codec validation is separate.
    return struct.pack(">II", raw, 32) + bytes([marker]) * 32


class Harness:
    def __init__(self, directory, extra=""):
        directory = Path(directory)
        source = directory / "pool.cpp"
        source.write_text(r'''
#include "timewarp/state_chunk_pool.h"
extern "C" {
void *memcpy(void *d,const void *s,__SIZE_TYPE__ n) {
    unsigned char *a=(unsigned char*)d;const unsigned char *b=(const unsigned char*)s;
    for(__SIZE_TYPE__ i=0;i<n;++i)a[i]=b[i];return d;
}
void *memset(void *d,int c,__SIZE_TYPE__ n) {
    unsigned char *a=(unsigned char*)d;for(__SIZE_TYPE__ i=0;i<n;++i)a[i]=(unsigned char)c;return d;
}
__declspec(dllexport) unsigned layout(){return sizeof(TWChunkPool);}
__declspec(dllexport) int init(StatePoolMemory*m){return TWChunkInit(m);}
__declspec(dllexport) int valid(StatePoolMemory*m){return TWChunkValid(m);}
__declspec(dllexport) int begin(StatePoolMemory*m,unsigned s){return TWChunkBegin(m,s);}
__declspec(dllexport) int append(StatePoolMemory*m,const unsigned char*b,unsigned n){return TWChunkAppend(m,b,n);}
__declspec(dllexport) int appendHash(StatePoolMemory*m,const unsigned char*b,unsigned n,unsigned h){return TWChunkAppendHashed(m,b,n,h);}
__declspec(dllexport) int commit(StatePoolMemory*m,unsigned r,unsigned p,unsigned t){return TWChunkCommit(m,r,p,t);}
__declspec(dllexport) int abortSave(StatePoolMemory*m){return TWChunkAbort(m);}
__declspec(dllexport) int clear(StatePoolMemory*m,unsigned s){return TWChunkClear(m,s);}
__declspec(dllexport) int compact(StatePoolMemory*m){return TWChunkCompact(m);}
__declspec(dllexport) int memoryValid(StatePoolMemory*m){return TWBankValid(m);}
__declspec(dllexport) int move(StatePoolMemory*m,unsigned d,unsigned s,unsigned n){return TWBankMove(m,d,s,n);}
__declspec(dllexport) unsigned placement(StatePoolMemory*m,unsigned o,unsigned n){return TWChunkPlacement(m,o,n);}
}
'''.replace("StatePoolMemory", "TWBankMemory") + extra, encoding="ascii")
        dll = directory / "pool.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"),
                        "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), "-I", str(ROOT / "scripts"),
                        str(source), str(ROOT / "src/state_crc.cpp"), "-o", str(dll)], check=True)
        self.lib = C.CDLL(str(dll))
        for name in ("init", "valid", "abortSave", "compact", "memoryValid"):
            getattr(self.lib, name).argtypes = [C.POINTER(Memory)]
        for name in ("begin", "clear"):
            getattr(self.lib, name).argtypes = [C.POINTER(Memory), C.c_uint]
        self.lib.append.argtypes = [C.POINTER(Memory), C.c_void_p, C.c_uint]
        self.lib.appendHash.argtypes = [C.POINTER(Memory), C.c_void_p, C.c_uint, C.c_uint]
        self.lib.commit.argtypes = [C.POINTER(Memory)] + [C.c_uint] * 3
        self.lib.move.argtypes = [C.POINTER(Memory)] + [C.c_uint] * 3
        self.lib.placement.argtypes = [C.POINTER(Memory)] + [C.c_uint] * 2
        self.lib.placement.restype = C.c_uint
        if self.lib.layout() != C.sizeof(Directory):
            raise ValueError("C/host directory layouts differ")

    def close(self):
        C.windll.kernel32.FreeLibrary(C.c_void_p(self.lib._handle))


class Pool:
    def __init__(self, harness, first=DIRECTORY + 0x200000, second=0x200000,
                 sizes=None, guest_bases=None):
        self.harness = harness
        sizes = tuple(sizes or tuple(s for s in (first, second) if s))
        assert 1 <= len(sizes) <= MAX_BANKS
        order = sorted(range(len(sizes)), key=lambda i: guest_bases[i] if guest_bases else i)
        allocation = (C.c_ubyte * (sum(sizes) + 128 * len(sizes)))()
        C.memset(C.addressof(allocation), 0xA7, C.sizeof(allocation))
        self.backing, self.guards = allocation, []
        pointers = [0] * len(sizes)
        cursor = C.addressof(allocation)
        for i in order:
            pointer = (cursor + 63) & ~31
            pointers[i] = pointer
            end = pointer + sizes[i] + 32
            self.guards.append((cursor, pointer, sizes[i], end))
            cursor = end
        assert cursor <= C.addressof(allocation) + C.sizeof(allocation)
        self.memory = Memory((C.c_void_p * MAX_BANKS)(*pointers),
                             (C.c_uint * MAX_BANKS)(*sizes), len(sizes))
        assert self.call("init")
        self.directory = Directory.from_address(pointers[0])

    def call(self, name, *args):
        return getattr(self.harness.lib, name)(C.byref(self.memory), *args)

    def append(self, block, forced_hash=None):
        storage = C.create_string_buffer(block)
        return (self.call("append", storage, len(block)) if forced_hash is None else
                self.call("appendHash", storage, len(block), forced_hash))

    def put(self, slot, blocks, tag=1, fail_after=None, forced_hash=None):
        if not self.call("begin", slot):
            return False
        for i, block in enumerate(blocks):
            if i == fail_after or not self.append(block, forced_hash):
                assert self.call("abortSave")
                return False
        raw = sum(struct.unpack_from(">I", b)[0] for b in blocks)
        packed = 8 + sum(map(len, blocks))
        if not self.call("commit", raw, packed, tag):
            assert self.call("abortSave")
            return False
        return True

    def block(self, index):
        chunk = self.directory.chunks[index]
        bank, offset = 0, chunk.offset
        while offset >= self.memory.sizes[bank]:
            offset -= self.memory.sizes[bank]
            bank += 1
        assert chunk.size <= self.memory.sizes[bank] - offset
        return C.string_at(self.memory.banks[bank] + offset, chunk.size)

    def states(self):
        assert self.call("valid")
        return [(FRAME + b"".join(self.block(i - 1) for i in s.ids[:s.count]),
                 s.tag, s.raw) if s.count else None for s in self.directory.slots[:3]]

    def stats(self):
        live = [d for d in self.directory.chunks if d.refs]
        payload = sum(d.size for d in live)
        rounded = sum((d.size + 31) & ~31 for d in live)
        return {"directory_reserved_bytes": DIRECTORY,
                "directory_struct_bytes": C.sizeof(Directory),
                "unique_blocks": len(live), "payload_bytes": payload,
                "alignment_bytes": rounded - payload,
                "bank_tail_and_fragment_bytes": self.directory.high_water - DIRECTORY - rounded,
                "occupied_extent_bytes": self.directory.high_water,
                "free_tail_bytes": sum(self.memory.sizes) - self.directory.high_water}

    def canaries(self):
        for start, pointer, size, end in self.guards:
            assert C.string_at(start, pointer - start) == bytes([0xA7]) * (pointer - start)
            assert C.string_at(pointer + size, end - pointer - size) == bytes([0xA7]) * (end - pointer - size)


class ChunkPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-chunks-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = Harness(cls.temp.name)
        cls.addClassCleanup(cls.harness.close)

    def test_collision_requires_complete_equality_and_refcounts(self):
        pool = Pool(self.harness)
        a, b = compressed_marker(1), compressed_marker(2)
        self.assertTrue(pool.put(0, [a, a, b], 41, forced_hash=7))
        self.assertTrue(pool.put(1, [b, a], 42, forced_hash=7))
        self.assertEqual(pool.stats()["unique_blocks"], 2)
        self.assertEqual(sorted(d.refs for d in pool.directory.chunks if d.refs), [2, 3])
        before = pool.states()
        self.assertTrue(pool.call("clear", 0))
        self.assertEqual(pool.states()[1], before[1])
        self.assertTrue(pool.call("clear", 1))
        self.assertTrue(pool.call("compact"))
        self.assertEqual(pool.stats()["occupied_extent_bytes"], DIRECTORY)
        pool.canaries()

    def test_abort_at_every_candidate_boundary_preserves_three_roots(self):
        pool = Pool(self.harness)
        for s in range(3):
            self.assertTrue(pool.put(s, [compressed_marker(s), compressed_marker(9)], 100 + s))
        expected = pool.states()
        blocks = [compressed_marker(9), compressed_marker(23), compressed_marker(9), plain(b"tail")]
        for target, after in itertools.product(range(3), range(len(blocks))):
            self.assertFalse(pool.put(target, blocks, 200 + target, fail_after=after))
            self.assertEqual(pool.states(), expected)
            self.assertTrue(pool.call("compact"))
            self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_full_pool_replacement_refuses_without_reclaiming_old_root(self):
        block = plain(bytes([3]) * BLOCK_BYTES)
        needed = (len(block) + 31) & ~31
        pool = Pool(self.harness, DIRECTORY + 3 * needed, 0)
        for s in range(3):
            self.assertTrue(pool.put(s, [plain(bytes([s]) * BLOCK_BYTES)], 11 + s))
        expected = pool.states()
        self.assertFalse(pool.put(0, [block], 90))
        self.assertEqual(pool.states(), expected)
        # Referencing a retained block needs no new payload even when full.
        self.assertTrue(pool.put(0, [plain(bytes([1]) * BLOCK_BYTES)], 90))
        self.assertEqual(pool.states()[1:], expected[1:])
        pool.canaries()

    def test_bank_crossing_and_compaction_preserve_direct_blocks(self):
        pool = Pool(self.harness, DIRECTORY + 256, 384)
        expected = [None] * 3
        rng = random.Random(303)
        for _ in range(250):
            slot = rng.randrange(3)
            if rng.randrange(5) == 0:
                if pool.call("clear", slot):
                    expected[slot] = None
            else:
                blocks = [compressed_marker(rng.randrange(20)) for _ in range(rng.randrange(1, 5))]
                tag = rng.randrange(1, 0xFFFFFFFF)
                if pool.put(slot, blocks, tag):
                    expected[slot] = (FRAME + b"".join(blocks), tag, len(blocks) * BLOCK_BYTES)
            self.assertEqual(pool.states(), expected)
            self.assertTrue(pool.call("compact"))
            self.assertEqual(pool.states(), expected)
            pool.canaries()

    def test_full_import_reference_limit_and_short_last_block(self):
        pool = Pool(self.harness)
        self.assertTrue(pool.put(0, [compressed_marker(5)] * MAX_BLOCKS, 7))
        self.assertEqual(pool.directory.slots[0].raw, 0x2000000)
        self.assertFalse(pool.put(1, [compressed_marker(5)] * (MAX_BLOCKS + 1), 8))
        self.assertTrue(pool.call("begin", 1))
        self.assertTrue(pool.append(plain(b"last")))
        self.assertFalse(pool.append(compressed_marker(5)))
        self.assertFalse(pool.call("commit", 5, 20, 9))
        self.assertTrue(pool.call("abortSave"))
        self.assertEqual(pool.directory.slots[0].tag, 7)
        pool.canaries()

    def test_bad_directory_alias_and_reentry_fail_before_mutation(self):
        pool = Pool(self.harness)
        self.assertTrue(pool.put(0, [compressed_marker(2)], 17))
        self.assertTrue(pool.call("begin", 1))
        self.assertFalse(pool.call("begin", 2))
        chunk = next(d for d in pool.directory.chunks if d.refs)
        self.assertFalse(pool.call("append", pool.memory.banks[0] + chunk.offset, chunk.size))
        self.assertTrue(pool.call("abortSave"))
        expected = pool.states()
        original = pool.directory.slots[0].ids[0]
        pool.directory.slots[0].ids[0] = 0xFFFF
        before = C.string_at(pool.memory.banks[0], DIRECTORY)
        for name, args in (("begin", (1,)), ("clear", (0,)), ("compact", ())):
            self.assertFalse(pool.call(name, *args))
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
        pool.directory.slots[0].ids[0] = original
        self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_active_append_rejects_corrupt_layout_without_mutation(self):
        pool = Pool(self.harness)
        block = compressed_marker(2)
        self.assertTrue(pool.put(0, [block], 17))
        expected = pool.states()
        self.assertTrue(pool.call("begin", 1))
        chunk = next(d for d in pool.directory.chunks if d.refs)
        cases = [(pool.directory, "high_water", 0),
                 (pool.directory, "high_water", sum(pool.memory.sizes) + 32),
                 (pool.directory, "high_water", DIRECTORY),
                 (chunk, "offset", sum(pool.memory.sizes)),
                 (chunk, "offset", chunk.offset + 1),
                 (chunk, "size", 0xFFFFFFFF),
                 (chunk, "refs", 0xFFFF),
                 (chunk, "reserved", 2)]
        for record, field, bad in cases:
            original = getattr(record, field)
            setattr(record, field, bad)
            before = C.string_at(pool.memory.banks[0], DIRECTORY)
            self.assertFalse(pool.append(block), field)
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before, field)
            setattr(record, field, original)
        self.assertTrue(pool.call("abortSave"))
        self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_bank_description_cannot_live_inside_owned_banks(self):
        pool = Pool(self.harness)
        for bank in range(2):
            location = pool.memory.banks[bank] + 64
            C.memmove(location, C.byref(pool.memory), C.sizeof(Memory))
            alias = Memory.from_address(location)
            before = C.string_at(pool.memory.banks[0], DIRECTORY)
            self.assertFalse(self.harness.lib.init(C.byref(alias)))
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
        pool.canaries()

    def test_full_descriptor_budget_commits_then_reuses_released_ids(self):
        pool = Pool(self.harness)
        def blocks(first):
            return [struct.pack(">II", BLOCK_BYTES, 32) + struct.pack(">I", i) * 8
                    for i in range(first, first + MAX_BLOCKS)]
        for slot in range(3):
            self.assertTrue(pool.put(slot, blocks(slot * MAX_BLOCKS), 10 + slot))
        expected = pool.states()
        self.assertTrue(pool.call("begin", 1))
        candidate = blocks(MAX_BLOCKS * 3)
        for block in candidate:
            self.assertTrue(pool.append(block))
        self.assertEqual(pool.stats()["unique_blocks"], MAX_DESCRIPTORS)
        # A failed expectation check leaves all committed roots and the pending root intact.
        packed = 8 + sum(map(len, candidate))
        before = C.string_at(pool.memory.banks[0], DIRECTORY)
        self.assertFalse(pool.call("commit", MAX_BLOCKS * BLOCK_BYTES, packed + 1, 77))
        self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
        self.assertEqual(pool.states(), expected)
        self.assertTrue(pool.call("commit", MAX_BLOCKS * BLOCK_BYTES, packed, 77))
        self.assertEqual(pool.stats()["unique_blocks"], MAX_BLOCKS * 3)
        self.assertEqual(pool.states()[0], expected[0])
        self.assertEqual(pool.states()[2], expected[2])
        self.assertEqual(pool.directory.slots[1].tag, 77)
        self.assertTrue(pool.put(2, blocks(MAX_DESCRIPTORS), 78))
        self.assertTrue(pool.call("compact"))
        self.assertEqual(pool.stats()["unique_blocks"], MAX_BLOCKS * 3)
        pool.canaries()

    def test_deflate_and_bad_block_headers_are_not_quick_blocks(self):
        pool = Pool(self.harness)
        self.assertTrue(pool.put(0, [compressed_marker(2)], 17))
        expected = pool.states()
        bad = [zlib.compress(b"legacy deflate" * 20), b"", b"12345678",
               struct.pack(">II", 0, 0x80000001) + b"a",
               struct.pack(">II", 2, 0x80000001) + b"a",
               struct.pack(">II", 1, 1) + b"a",
               struct.pack(">II", BLOCK_BYTES + 1, 1) + b"a"]
        for block in bad:
            self.assertFalse(pool.put(1, [block], 99))
            self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_five_bank_placement_skips_multiple_short_tails(self):
        sizes = (DIRECTORY + 64, 64, 96, 160, 320)
        pool = Pool(self.harness, sizes=sizes, guest_bases=(5, 2, 1, 4, 3))
        blocks = [plain(bytes([i]) * 100) for i in range(3)]
        self.assertTrue(pool.put(0, [blocks[0]], 1))
        first = pool.directory.chunks[pool.directory.slots[0].ids[0] - 1]
        self.assertEqual(first.offset, DIRECTORY + 224)
        self.assertTrue(pool.put(1, [blocks[1]], 2))
        self.assertTrue(pool.put(2, [blocks[2]], 3))
        expected = pool.states()
        self.assertFalse(pool.put(0, [plain(bytes([4]) * 100)], 4))
        self.assertEqual(pool.states(), expected)
        self.assertTrue(pool.call("clear", 0))
        self.assertTrue(pool.call("compact"))
        self.assertEqual(pool.states()[1:], expected[1:])
        pool.canaries()

    def test_generic_move_matches_memmove_across_reversed_banks(self):
        sizes = (DIRECTORY + 64, 96, 160, 256, 512)
        pool = Pool(self.harness, sizes=sizes, guest_bases=(5, 2, 1, 4, 3))
        expected = bytearray((i * 131 + 7) & 255 for i in range(sum(sizes)))
        cursor = 0
        for bank, size in enumerate(sizes):
            C.memmove(pool.memory.banks[bank], bytes(expected[cursor:cursor + size]), size)
            cursor += size
        rng = random.Random(20261008)
        for _ in range(300):
            source, destination = [rng.randrange(DIRECTORY, len(expected)) for _ in range(2)]
            size = rng.randrange(min(len(expected) - source, len(expected) - destination) + 1)
            self.assertTrue(pool.call("move", destination, source, size))
            expected[destination:destination + size] = expected[source:source + size]
            actual = b"".join(C.string_at(pool.memory.banks[i], s) for i, s in enumerate(sizes))
            self.assertEqual(actual, expected)
            pool.canaries()

    def test_five_bank_invalid_descriptions_fail_before_mutation(self):
        pool = Pool(self.harness, sizes=(DIRECTORY + 64, 64, 96, 160, 320))
        cases = [("count", None, 0), ("count", None, MAX_BANKS + 1),
                 ("sizes", 4, 0), ("sizes", 4, 0xFFFFFFFF),
                 ("banks", 4, pool.memory.banks[2] + 32),
                 ("banks", 4, (1 << (C.sizeof(C.c_void_p) * 8)) - 16)]
        for field, index, value in cases:
            member = getattr(pool.memory, field)
            original = member if index is None else member[index]
            if index is None: setattr(pool.memory, field, value)
            else: member[index] = value
            before = C.string_at(pool.memory.banks[0], DIRECTORY)
            self.assertFalse(pool.call("init"))
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
            if index is None: setattr(pool.memory, field, original)
            else: member[index] = original
        pool.canaries()

    def test_extra_banks_cannot_hide_a_bank_descriptor_alias(self):
        pool = Pool(self.harness, sizes=(DIRECTORY + 256, 256, 256, 256, 256))
        for bank in range(MAX_BANKS):
            location = pool.memory.banks[bank] + 64
            C.memmove(location, C.byref(pool.memory), C.sizeof(Memory))
            alias = Memory.from_address(location)
            before = C.string_at(pool.memory.banks[0], DIRECTORY)
            self.assertFalse(self.harness.lib.init(C.byref(alias)))
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
        pool.canaries()

    def test_four_and_five_bank_pressure_keeps_all_old_roots(self):
        needed = (BLOCK_BYTES + 8 + 31) & ~31
        for count in (4, 5):
            pool = Pool(self.harness, sizes=(DIRECTORY + 2 * needed,) + (needed,) * (count - 1))
            for slot in range(3):
                self.assertTrue(pool.put(slot, [plain(bytes([slot]) * BLOCK_BYTES)], slot + 1))
            expected = pool.states()
            candidate = [plain(bytes([i]) * BLOCK_BYTES) for i in range(4, 8)]
            self.assertFalse(pool.put(0, candidate, 99))
            self.assertEqual(pool.states(), expected)
            self.assertTrue(pool.call("compact"))
            self.assertEqual(pool.states(), expected)
            pool.canaries()

    def test_randomized_four_and_five_bank_replacements_and_compaction(self):
        for count in (4, 5):
            pool = Pool(self.harness, sizes=(DIRECTORY + 128, 96, 160, 224, 320)[:count],
                        guest_bases=(5, 2, 1, 4, 3)[:count])
            expected = [None] * 3
            rng = random.Random(1600 + count)
            for _ in range(300):
                slot = rng.randrange(3)
                if rng.randrange(6) == 0:
                    if pool.call("clear", slot): expected[slot] = None
                else:
                    markers = [rng.randrange(1, 30) for _ in range(rng.randrange(1, 5))]
                    blocks = [struct.pack(">II", BLOCK_BYTES, 8 + m * 5) + bytes([m]) * (8 + m * 5)
                              for m in markers]
                    tag = rng.randrange(1, 100000)
                    if pool.put(slot, blocks, tag):
                        expected[slot] = (FRAME + b"".join(blocks), tag, len(blocks) * BLOCK_BYTES)
                self.assertEqual(pool.states(), expected)
                self.assertTrue(pool.call("compact"))
                self.assertEqual(pool.states(), expected)
                pool.canaries()


def captures(receipt_path, output):
    allocator = ROOT / "scripts/timewarp/state_chunk_pool.h"
    allocator_hash = hashlib.sha256(allocator.read_bytes()).hexdigest()
    source_receipt = json.loads(receipt_path.read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix="timewarp-chunk-captures-") as temp:
        harness = Harness(temp)
        try:
            for capture_set in source_receipt["sets"]:
                pool = Pool(harness, 0xFF0000, 0x200000)
                expected, blocks, raw_states = [], [], []
                peak = DIRECTORY
                for row in capture_set["slots"]:
                    packed = Path(row["ppc_quick"]["path"]).read_bytes()
                    raw = Path(row["raw_path"]).read_bytes()
                    assert hashlib.sha256(packed).hexdigest() == row["ppc_quick"]["sha256"]
                    assert hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
                    blocks.append(quick_blocks(packed, raw))
                    raw_states.append(raw)
                    # Opaque metadata binding is simulated; real StoredState is not imported.
                    tag = zlib.crc32(row["raw_sha256"].encode())
                    expected.append((packed, tag, len(raw)))
                accepted = [None] * 3
                admitted = []
                for slot in range(3):
                    before = pool.states()
                    fits = pool.put(slot, blocks[slot], expected[slot][1])
                    admitted.append(fits)
                    if fits:
                        accepted[slot] = expected[slot]
                    else:
                        assert pool.states() == before
                    peak = max(peak, pool.directory.high_water)
                assert pool.states() == accepted
                runtime_stats = pool.stats()
                runtime_peak = peak
                if not all(admitted):
                    # Sizing experiment only: this larger host bank is not available on console.
                    upper = DIRECTORY + BLOCK_BYTES + sum(
                        (len(b) + 31) & ~31 for bs in blocks for b in bs)
                    pool = Pool(harness, 0xFF0000, (max(0x200000, upper - 0xFF0000) + 31) & ~31)
                    for slot in range(3):
                        assert pool.put(slot, blocks[slot], expected[slot][1])
                    assert pool.states() == expected
                stats = pool.stats()
                peak = pool.directory.high_water
                for slot in range(3):
                    candidate = blocks[(slot + 1) % 3]
                    for after in (0, len(candidate) // 2, len(candidate) - 1):
                        assert not pool.put(slot, candidate, 888, fail_after=after)
                        assert pool.states() == expected
                    assert pool.put(slot, blocks[slot], expected[slot][1])
                    peak = max(peak, pool.directory.high_water)
                    assert pool.states() == expected
                for slot, state in enumerate(pool.states()):
                    quick_blocks(state[0], raw_states[slot])
                pool.canaries()
                results.append({"name": capture_set["name"], **stats,
                                "runtime_capacity_bytes": 0xFF0000 + 0x200000,
                                "fits_existing_pool": all(admitted),
                                "runtime_slot_admission": admitted,
                                "runtime_pool_after_attempts": runtime_stats,
                                "sizing_minimum_growth_bytes": max(0, stats["occupied_extent_bytes"] - 0x11F0000),
                                "runtime_peak_extent_bytes": runtime_peak,
                                "replacement_experiment_peak_extent_bytes": peak,
                                "canonical_streams_equal": True,
                                "all_three_independently_decoded": True,
                                "interrupted_replacements_preserved_roots": True,
                                "same_stream_replacement_preserved_metadata_tags": True})
                print(f"{capture_set['name']}: {stats['occupied_extent_bytes']:,} bytes including directory; "
                      f"fits existing pool: {all(admitted)}")
        finally:
            harness.close()
    if hashlib.sha256(allocator.read_bytes()).hexdigest() != allocator_hash:
        raise RuntimeError("Allocator changed during the experiment; rerun before writing a receipt")
    result = {"scope": "Native C allocator prototype over exact PPC Quick streams, not gameplay or Wii timing. Rejected triples use an explicitly larger host bank only to measure required capacity.",
              "limits": "No production storage/codec integration, full StoredState metadata, power-loss persistence, or corruption recovery.",
              "policy": "All three old roots retained until complete candidate commits; no destructive reclaim.",
              "input_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
              "allocator_sha256": allocator_hash,
              "sets": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-state-measure/chunk-pool-receipt.json")
    args, remaining = parser.parse_known_args()
    if args.receipt:
        captures(args.receipt, args.output)
    else:
        unittest.main(argv=[__file__] + remaining)
