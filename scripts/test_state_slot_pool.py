"""Exercise the production slot pool's transactional replacement and compaction."""

import ctypes as C
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Entry(C.Structure):
    _fields_ = [("offset", C.c_uint), ("size", C.c_uint)]


class Pool(C.Structure):
    _fields_ = [("slots", Entry * 3), ("used", C.c_uint)]


def metadata(pool):
    return C.string_at(C.addressof(pool), C.sizeof(pool))


class StateSlotPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-state-pool-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = work / "pool.cpp"
        source.write_text(r'''
#include "susamune/state_slot_pool.h"
extern "C" {
__declspec(dllexport) int valid(StateSlotPool*p,unsigned c) {
    return StateSlotPoolValid(p,c);
}
__declspec(dllexport) int canCommit(StateSlotPool*p,unsigned c,unsigned s,
                                  unsigned n,unsigned z) {
    return StateSlotPoolCanCommit(p,c,s,n,z);
}
__declspec(dllexport) int commit(StateSlotPool*p,unsigned char*b,unsigned c,
                               unsigned s,unsigned n,const unsigned char*t,
                               unsigned z) {
    return StateSlotPoolCommit(p,b,c,s,n,t,z);
}
__declspec(dllexport) int clear(StateSlotPool*p,unsigned char*b,unsigned c,
                              unsigned s) {
    return StateSlotPoolClear(p,b,c,s);
}
}
''', encoding="ascii")
        dll = work / "pool.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                        "-O1", "-I", str(ROOT / "include"), str(source),
                        "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.valid.argtypes = [C.POINTER(Pool), C.c_uint]
        cls.lib.canCommit.argtypes = [C.POINTER(Pool)] + [C.c_uint] * 4
        cls.lib.commit.argtypes = [C.POINTER(Pool), C.c_void_p, C.c_uint,
                                   C.c_uint, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.clear.argtypes = [C.POINTER(Pool), C.c_void_p, C.c_uint, C.c_uint]

    def make_pool(self, sizes, order=(0, 1, 2), capacity=24):
        pool = Pool()
        buf = (C.c_ubyte * (capacity + 16))(*([0xA7] * (capacity + 16)))
        expected = {}
        for slot in order:
            size = sizes[slot]
            if size:
                expected[slot] = bytes((17 + slot * 31 + i) % 256 for i in range(size))
                pool.slots[slot] = Entry(pool.used, size)
                buf[pool.used:pool.used + size] = expected[slot]
                pool.used += size
        self.assertTrue(self.lib.valid(C.byref(pool), capacity))
        return pool, buf, expected

    def assert_contents(self, pool, buf, expected, capacity):
        self.assertTrue(self.lib.valid(C.byref(pool), capacity))
        self.assertEqual(pool.used, sum(map(len, expected.values())))
        for slot in range(3):
            entry = pool.slots[slot]
            if slot in expected:
                self.assertEqual(bytes(buf[entry.offset:entry.offset + entry.size]), expected[slot])
            else:
                self.assertEqual((entry.offset, entry.size), (0, 0))
        self.assertEqual(bytes(buf[capacity:]), bytes([0xA7] * 16))

    def replace(self, sizes, order, slot, packed, staging_size, capacity):
        pool, buf, expected = self.make_pool(sizes, order, capacity)
        old_used = pool.used
        old_meta, old_bytes = metadata(pool), bytes(buf[:old_used])
        candidate = bytes((93 + i * 7) % 256 for i in range(packed))
        first = min(packed, staging_size)
        staging = (C.c_ubyte * max(staging_size, 1))()
        staging[:first] = candidate[:first]
        fits = (packed <= capacity - (old_used - sizes[slot]) and
                packed - first <= capacity - old_used)
        # The compressor may only write the actually unused tail.
        tail_size = min(packed - first, capacity - old_used)
        buf[old_used:old_used + tail_size] = candidate[first:first + tail_size]
        self.assertEqual(bool(self.lib.canCommit(C.byref(pool), capacity, slot,
                                                packed, staging_size)), fits)
        self.assertEqual(bool(self.lib.commit(C.byref(pool), buf, capacity, slot,
                                             packed, staging, staging_size)), fits)
        if fits:
            expected[slot] = candidate
            self.assert_contents(pool, buf, expected, capacity)
        else:
            self.assertEqual(metadata(pool), old_meta)
            self.assertEqual(bytes(buf[:old_used]), old_bytes)
            self.assertEqual(bytes(buf[capacity:]), bytes([0xA7] * 16))

    def test_larger_replacement_moves_overlapping_tail_before_staging_copy(self):
        self.replace((4, 3, 5), (0, 1, 2), 1, 10, 4, 24)

    def test_larger_replacement_moves_overlapping_tail_left(self):
        self.replace((6, 4, 3), (0, 1, 2), 0, 8, 1, 24)

    def test_smaller_replacement_compacts_tail_left(self):
        self.replace((6, 4, 3), (0, 1, 2), 0, 5, 1, 24)

    def test_growth_shrink_and_empty_slots_in_every_physical_order(self):
        for sizes in itertools.product(range(4), repeat=3):
            for order in itertools.permutations(range(3)):
                for slot in range(3):
                    for packed in (1, 3, 6, 9):
                        for staging in (0, 1, 3, 9):
                            self.replace(sizes, order, slot, packed, staging, 12)

    def test_capacity_failure_preserves_all_existing_slots(self):
        # Replacement could fit after reclaiming its old slot, but cannot be
        # completely staged beforehand; that old slot must stay intact.
        self.replace((6, 3, 3), (1, 0, 2), 0, 6, 5, 12)
        self.replace((4, 3, 3), (2, 1, 0), 1, 6, 6, 12)

    def test_clear_compacts_each_slot_and_empty_clear_does_nothing(self):
        for order in itertools.permutations(range(3)):
            pool, buf, expected = self.make_pool((3, 4, 5), order)
            for slot in (1, 2, 0):
                self.assertTrue(self.lib.clear(C.byref(pool), buf, 24, slot))
                del expected[slot]
                self.assert_contents(pool, buf, expected, 24)
                before = metadata(pool), bytes(buf)
                self.assertFalse(self.lib.clear(C.byref(pool), buf, 24, slot))
                self.assertEqual((metadata(pool), bytes(buf)), before)

    def test_malformed_layouts_are_rejected_before_any_write(self):
        cases = [
            ([(0, 4), (4, 3), (7, 2)], 25),  # beyond capacity
            ([(0, 4), (1, 0), (0, 0)], 4),   # empty slot with an offset
            ([(0, 4), (5, 3), (0, 0)], 8),   # gap
            ([(0, 4), (0, 3), (0, 0)], 4),   # duplicate offset
            ([(0, 4), (3, 3), (0, 0)], 6),   # overlap
            ([(0, 4), (9, 1), (0, 0)], 8),   # outside used bytes
            ([(0, 4), (4, 0xFFFFFFFF), (0, 0)], 8),
            ([(0, 4), (0, 0), (0, 0)], 5),   # unowned trailing byte
        ]
        for entries, used in cases:
            with self.subTest(entries=entries, used=used):
                pool = Pool((Entry * 3)(*(Entry(*entry) for entry in entries)), used)
                buf = (C.c_ubyte * 40)(*([0xA7] * 40))
                staging = (C.c_ubyte * 8)()
                before = metadata(pool), bytes(buf)
                self.assertFalse(self.lib.valid(C.byref(pool), 24))
                self.assertFalse(self.lib.commit(C.byref(pool), buf, 24, 0, 4, staging, 8))
                self.assertFalse(self.lib.clear(C.byref(pool), buf, 24, 0))
                self.assertEqual((metadata(pool), bytes(buf)), before)

    def test_argument_and_unsigned_capacity_boundaries(self):
        pool, buf, _ = self.make_pool((3, 4, 5))
        staging = (C.c_ubyte * 8)()
        before = metadata(pool), bytes(buf)
        for selected, packed, source, staging_size in ((3, 4, staging, 8),
                                                      (0, 0, staging, 8),
                                                      (0, 4, None, 8)):
            self.assertFalse(self.lib.commit(C.byref(pool), buf, 24, selected,
                                             packed, source, staging_size))
            self.assertEqual((metadata(pool), bytes(buf)), before)
        self.assertFalse(self.lib.commit(None, buf, 24, 0, 4, staging, 8))
        self.assertFalse(self.lib.commit(C.byref(pool), None, 24, 0, 4, staging, 8))
        pool = Pool((Entry * 3)(Entry(0, 0xFFFFFFFF), Entry(), Entry()), 0xFFFFFFFF)
        self.assertTrue(self.lib.valid(C.byref(pool), 0xFFFFFFFF))
        self.assertFalse(self.lib.canCommit(C.byref(pool), 0xFFFFFFFF, 0, 0xFFFFFFFF, 0))
        self.assertTrue(self.lib.canCommit(C.byref(pool), 0xFFFFFFFF, 0, 0xFFFFFFFF, 0xFFFFFFFF))


if __name__ == "__main__":
    unittest.main()
