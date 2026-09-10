"""Run the C bank mapper and pool transactions with physically reversed banks."""

import ctypes as C
import itertools
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from test_state_slot_pool import Entry, Pool, metadata

ROOT = Path(__file__).resolve().parents[1]


class Memory(C.Structure):
    _fields_ = [("banks", C.c_void_p * 2), ("sizes", C.c_uint * 2)]


class Span(C.Structure):
    _fields_ = [("data", C.c_void_p), ("size", C.c_uint)]


class StatePoolMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-pool-banks-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "bank.c"
        source.write_text(r'''
#include "susamune/state_pool_memory.h"
#define API __declspec(dllexport)
API int valid(StatePoolMemory*m){return StatePoolMemoryValid(m);}
API unsigned capacity(StatePoolMemory*m){return StatePoolMemoryCapacity(m);}
API int span(StatePoolMemory*m,unsigned o,unsigned n,StatePoolMemorySpan*s){return StatePoolMemorySpanAt(m,o,n,s);}
API int copyIn(StatePoolMemory*m,unsigned o,const void*p,unsigned n){return StatePoolMemoryCopyIn(m,o,p,n);}
API int copyOut(StatePoolMemory*m,unsigned o,void*p,unsigned n){return StatePoolMemoryCopyOut(m,o,p,n);}
API int move(StatePoolMemory*m,unsigned d,unsigned s,unsigned n){return StatePoolMemoryMove(m,d,s,n);}
API int clear(StateSlotPool*p,StatePoolMemory*m,unsigned s){return StateSlotPoolClearBanked(p,m,s);}
API int commit(StateSlotPool*p,StatePoolMemory*m,unsigned s,unsigned n,const unsigned char*t,unsigned z){return StateSlotPoolCommitBanked(p,m,s,n,t,z);}
API int reclaim(StateSlotPool*p,StatePoolMemory*m,unsigned s,unsigned n){return StateSlotPoolReclaimForReplaceBanked(p,m,s,n);}
API int prepared(StateSlotPool*p,StatePoolMemory*m,unsigned s,unsigned n){return StateSlotPoolCommitPreparedBanked(p,m,s,n);}
API unsigned mergeLittle(unsigned a,unsigned b,unsigned shift){return StateSlotPoolMergeWords(a,b,shift);}
''', encoding="ascii")
        big_endian = source.with_name("big-endian.c")
        big_endian.write_text(r'''
#undef __BYTE_ORDER__
#define __BYTE_ORDER__ __ORDER_BIG_ENDIAN__
#include "susamune/state_slot_pool.h"
__declspec(dllexport) unsigned mergeBig(unsigned a,unsigned b,unsigned shift){return StateSlotPoolMergeWords(a,b,shift);}
''', encoding="ascii")
        dll = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                        "-O2", "-I", str(ROOT / "include"), str(source), str(big_endian), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)
        cls.lib.valid.argtypes = cls.lib.capacity.argtypes = [C.POINTER(Memory)]
        cls.lib.span.argtypes = [C.POINTER(Memory), C.c_uint, C.c_uint, C.POINTER(Span)]
        for name in ("copyIn", "copyOut"):
            getattr(cls.lib, name).argtypes = [C.POINTER(Memory), C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.move.argtypes = [C.POINTER(Memory), C.c_uint, C.c_uint, C.c_uint]
        cls.lib.clear.argtypes = [C.POINTER(Pool), C.POINTER(Memory), C.c_uint]
        cls.lib.commit.argtypes = [C.POINTER(Pool), C.POINTER(Memory), C.c_uint,
                                   C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.reclaim.argtypes = cls.lib.prepared.argtypes = [C.POINTER(Pool), C.POINTER(Memory), C.c_uint, C.c_uint]
        for name in ("mergeLittle", "mergeBig"):
            getattr(cls.lib, name).argtypes = [C.c_uint, C.c_uint, C.c_uint]
            getattr(cls.lib, name).restype = C.c_uint

    def fixture(self, primary=13, secondary=11):
        storage = (C.c_ubyte * 128)(*([0xA7] * 128))
        address = C.addressof(storage)
        memory = Memory((C.c_void_p * 2)(address + 64, address + 16),
                        (C.c_uint * 2)(primary, secondary))
        self.assertTrue(self.lib.valid(C.byref(memory)))
        return memory, storage

    def put(self, memory, data, offset=0):
        owner = C.create_string_buffer(data)
        self.assertTrue(self.lib.copyIn(C.byref(memory), offset, owner, len(data)))

    def get(self, memory, offset=0, size=None):
        size = sum(memory.sizes) - offset if size is None else size
        owner = C.create_string_buffer(size)
        self.assertTrue(self.lib.copyOut(C.byref(memory), offset, owner, size))
        return owner.raw

    def guards(self, memory, storage):
        covered = set(range(64, 64 + memory.sizes[0])) | set(range(16, 16 + memory.sizes[1]))
        self.assertTrue(all(storage[i] == 0xA7 for i in range(128) if i not in covered))

    def check_pool(self, pool, memory, storage, expected):
        self.assertEqual(pool.used, sum(map(len, expected.values())))
        for slot, entry in enumerate(pool.slots):
            if slot in expected:
                self.assertEqual(self.get(memory, entry.offset, entry.size), expected[slot])
            else:
                self.assertEqual((entry.offset, entry.size), (0, 0))
        self.guards(memory, storage)

    def test_span_and_copy_cross_boundary_with_second_bank_below_first(self):
        memory, storage = self.fixture()
        self.put(memory, bytes(range(24)))
        self.assertEqual(self.get(memory), bytes(range(24)))
        span = Span()
        self.assertTrue(self.lib.span(C.byref(memory), 11, 8, C.byref(span)))
        self.assertEqual((span.data, span.size), (memory.banks[0] + 11, 2))
        self.assertTrue(self.lib.span(C.byref(memory), 13, 6, C.byref(span)))
        self.assertEqual((span.data, span.size), (memory.banks[1], 6))
        self.assertTrue(self.lib.span(C.byref(memory), 24, 0, C.byref(span)))
        self.assertEqual((span.data, span.size), (None, 0))
        self.guards(memory, storage)

    def test_misaligned_word_merge_matches_both_host_and_console_byte_order(self):
        rng = random.Random(0x574F5244)
        for _ in range(100):
            data = bytes(rng.randrange(256) for _ in range(8))
            for order, name in (("little", "mergeLittle"), ("big", "mergeBig")):
                for offset in (1, 2, 3):
                    self.assertEqual(getattr(self.lib, name)(int.from_bytes(data[:4], order),
                        int.from_bytes(data[4:], order), offset * 8),
                        int.from_bytes(data[offset:offset + 4], order))

    def test_all_bounded_overlap_directions_and_boundary_positions_match_memmove(self):
        data = bytes(range(24))
        for primary in (1, 13, 23):
            memory, storage = self.fixture(primary, 24 - primary)
            for size in range(25):
                for source in range(25 - size):
                    for destination in range(25 - size):
                        self.put(memory, data)
                        expected = bytearray(data)
                        expected[destination:destination + size] = data[source:source + size]
                        self.assertTrue(self.lib.move(C.byref(memory), destination, source, size))
                        self.assertEqual(self.get(memory), expected)
            self.guards(memory, storage)

    def test_large_word_moves_cover_every_alignment_and_both_physical_bank_orders(self):
        primary, secondary = 4099, 2083
        capacity = primary + secondary
        original = bytes((i * 71 + i // 5) & 255 for i in range(capacity))
        rng = random.Random(0x504F4F4C)
        operations = [(1, 0, 4096), (0, 1, 4096), (4, 0, 4096), (0, 4, 4096),
                      (primary - 33, primary - 32, 65), (primary - 32, primary - 33, 65),
                      (0, primary, secondary), (primary, 0, secondary)]
        for _ in range(100):
            size = rng.randrange(capacity + 1)
            operations.append((rng.randrange(capacity - size + 1),
                               rng.randrange(capacity - size + 1), size))
        for align_first, align_second, reversed_banks in itertools.product(range(4), range(4), (False, True)):
            storage = (C.c_ubyte * (capacity + 256))(*([0xA7] * (capacity + 256)))
            start_first = 64 + align_first
            start_second = 64 + primary + 64 + align_second
            if reversed_banks:
                start_second = 64 + align_second
                start_first = 64 + secondary + 64 + align_first
            address = C.addressof(storage)
            memory = Memory((C.c_void_p * 2)(address + start_first, address + start_second),
                            (C.c_uint * 2)(primary, secondary))
            with self.subTest(first=align_first, second=align_second, reversed=reversed_banks):
                for destination, source, size in operations:
                    self.put(memory, original)
                    expected = bytearray(original)
                    expected[destination:destination + size] = original[source:source + size]
                    self.assertTrue(self.lib.move(C.byref(memory), destination, source, size))
                    self.assertEqual(self.get(memory), expected)
                for source_alignment, destination_alignment in itertools.product(range(4), repeat=2):
                    source = C.create_string_buffer(capacity + 8)
                    destination = C.create_string_buffer(capacity + 8)
                    C.memmove(C.addressof(source) + source_alignment, original, capacity)
                    self.assertTrue(self.lib.copyIn(C.byref(memory), 0,
                        C.addressof(source) + source_alignment, capacity))
                    self.assertTrue(self.lib.copyOut(C.byref(memory), 0,
                        C.addressof(destination) + destination_alignment, capacity))
                    self.assertEqual(C.string_at(C.addressof(destination) + destination_alignment, capacity), original)
                covered = set(range(start_first, start_first + primary)) | set(range(start_second, start_second + secondary))
                self.assertTrue(all(storage[i] == 0xA7 for i in range(len(storage)) if i not in covered))

    def test_staged_replacements_preserve_other_slots_across_boundary(self):
        for sizes, order, slot, packed, staging_size in itertools.product(
                ((4, 3, 5), (10, 4, 3), (1, 0, 7), (6, 6, 6), (0, 0, 0)),
                itertools.permutations(range(3)), range(3), (1, 6, 11, 17, 25), (0, 1, 6, 30)):
            memory, storage = self.fixture()
            pool, expected = Pool(), {}
            for i in order:
                if sizes[i]:
                    expected[i] = bytes([31 + i * 29]) * sizes[i]
                    pool.slots[i] = Entry(pool.used, sizes[i])
                    self.put(memory, expected[i], pool.used)
                    pool.used += sizes[i]
            before = metadata(pool), self.get(memory, 0, pool.used)
            candidate = bytes((123 + i * 7) % 256 for i in range(packed))
            first = min(packed, staging_size)
            staging = C.create_string_buffer(candidate[:first])
            tail = min(packed - first, 24 - pool.used)
            self.put(memory, candidate[first:first + tail], pool.used)
            fits = packed <= 24 - (pool.used - sizes[slot]) and packed - first <= 24 - pool.used
            self.assertEqual(bool(self.lib.commit(C.byref(pool), C.byref(memory), slot, packed,
                                                 staging, staging_size)), fits)
            if fits:
                expected[slot] = candidate
                self.check_pool(pool, memory, storage, expected)
            else:
                self.assertEqual((metadata(pool), self.get(memory, 0, pool.used)), before)
                self.guards(memory, storage)

    def test_reclaim_and_publish_cross_bank_while_disabled_bank_refuses(self):
        for slot in range(3):
            memory, storage = self.fixture()
            expected = {i: bytes([i + 20]) * 8 for i in range(3)}
            pool = Pool((Entry * 3)(Entry(0, 8), Entry(8, 8), Entry(16, 8)), 24)
            self.put(memory, b"".join(expected.values()))
            before = metadata(pool), bytes(storage)
            disabled = Memory(memory.banks, (C.c_uint * 2)(13, 0))
            self.assertFalse(self.lib.reclaim(C.byref(pool), C.byref(disabled), slot, 8))
            self.assertEqual((metadata(pool), bytes(storage)), before)
            self.assertTrue(self.lib.reclaim(C.byref(pool), C.byref(memory), slot, 8))
            del expected[slot]
            self.check_pool(pool, memory, storage, expected)
            self.put(memory, b"NEWSTATE", pool.used)
            self.assertTrue(self.lib.prepared(C.byref(pool), C.byref(memory), slot, 8))
            expected[slot] = b"NEWSTATE"
            self.check_pool(pool, memory, storage, expected)
            self.assertTrue(self.lib.clear(C.byref(pool), C.byref(memory), slot))
            del expected[slot]
            self.check_pool(pool, memory, storage, expected)

    def test_invalid_ranges_aliases_and_layouts_refuse_before_writing(self):
        memory, storage = self.fixture()
        self.put(memory, bytes(range(24)))
        before = bytes(storage)
        owner = C.create_string_buffer(40)
        for offset, size in ((25, 0), (23, 2), (0xFFFFFFFF, 2), (1, 0xFFFFFFFF)):
            self.assertFalse(self.lib.copyIn(C.byref(memory), offset, owner, size))
            self.assertFalse(self.lib.copyOut(C.byref(memory), offset, owner, size))
            self.assertFalse(self.lib.move(C.byref(memory), offset, 0, size))
            self.assertFalse(self.lib.move(C.byref(memory), 0, offset, size))
            self.assertEqual(bytes(storage), before)
        self.assertFalse(self.lib.copyIn(C.byref(memory), 0, memory.banks[1], 5))
        self.assertFalse(self.lib.copyOut(C.byref(memory), 0, memory.banks[0] + 1, 5))
        self.assertFalse(self.lib.copyIn(C.byref(memory), 0, None, 1))
        pool = Pool((Entry * 3)(Entry(0, 4), Entry(3, 4), Entry()), 7)
        self.assertFalse(self.lib.commit(C.byref(pool), C.byref(memory), 1, 4, owner, 4))
        self.assertFalse(self.lib.clear(C.byref(pool), C.byref(memory), 1))
        self.assertEqual(bytes(storage), before)
        bad = Memory((C.c_void_p * 2)(memory.banks[0], memory.banks[0] + 1), (C.c_uint * 2)(13, 11))
        self.assertFalse(self.lib.valid(C.byref(bad)))
        bad.sizes[:] = (0xFFFFFFFF, 1)
        self.assertFalse(self.lib.valid(C.byref(bad)))
        self.assertFalse(self.lib.valid(None))


if __name__ == "__main__":
    unittest.main()
