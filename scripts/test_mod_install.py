"""Shared production V3/V4 dispatch, first-line reads and installer tests.

V3 metadata is native-word ABI in the existing little-endian test fixture;
V4 input is always the untouched big-endian wire file.
"""
import ctypes as C
import mmap
import struct
import tempfile
import unittest

import test_mod_bin as legacy
from test_timewarp_mod_v4 import Harness, tiny, put, seal, REGION_BYTES, SENTINEL
from timewarp_mod_v4 import GAMES, BASES, stage


class ModInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mod-install-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.h = Harness(cls.temp.name)
        cls.addClassCleanup(cls.h.close)

    def install(self, data):
        source = C.create_string_buffer(bytes(data))
        memory = C.create_string_buffer(bytes([SENTINEL]) * (REGION_BYTES + 128))
        result = self.h.lib.production_install(source, GAMES["jp"], len(data),
                                               C.addressof(memory) + 64, REGION_BYTES, BASES[GAMES["jp"]])
        return result, memory.raw[:-1], source

    def test_v3_native_compatibility_and_word_install(self):
        packed = legacy.packer.build_mod_bin(legacy.manifest())
        native = legacy.ModBinTests.native(None, packed)
        result, memory, source = self.install(native)
        self.assertEqual(result, 0)
        self.assertEqual(self.h.lib.production_size(source), len(packed))
        self.assertEqual([self.h.lib.production_info(source, i) for i in range(5)], [32, 16, 16, 0, 0])
        expected = bytearray([SENTINEL]) * (REGION_BYTES + 128)
        expected[64:72] = bytes([0x12]) * 8
        expected[72:80] = bytes(8)
        expected[64 + 0x80000:68 + 0x80000] = bytes([0x34]) * 4
        expected[68 + 0x80000:80 + 0x80000] = bytes(12)
        self.assertEqual(memory, expected)

    def test_v4_wire_dispatch_accessors_and_console_policy(self):
        for cold in (False, True):
            data = tiny(cold=cold, quick=True)
            result, memory, source = self.install(data)
            self.assertEqual(result, 0)
            self.assertTrue(self.h.lib.production_validate(source, GAMES["jp"], len(data)))
            self.assertEqual(self.h.lib.production_size(source), len(data))
            self.assertEqual([self.h.lib.production_info(source, i) for i in range(5)],
                             [64, 64, 64, stage(0) + 0xA0 if cold else 0, 32 if cold else 0])
            self.assertEqual(memory[64 + 0x58000:64 + 0x80000], bytes([SENTINEL]) * 0x28000)
        data = tiny(flags=1, cold=True, quick=True)
        result, memory, source = self.install(data)
        self.assertNotEqual(result, 0)
        self.assertFalse(self.h.lib.production_validate(source, GAMES["jp"], len(data)))
        self.assertEqual(memory, bytes([SENTINEL]) * len(memory))

    def test_complete_preflight_and_invalid_size_no_writes(self):
        good = tiny(quick=True)
        for data in (b"", good[:16], good[:32], good[:-1], good + bytes(32)):
            result, memory, _ = self.install(data)
            self.assertNotEqual(result, 0)
            self.assertEqual(memory, bytes([SENTINEL]) * len(memory))
        damaged = bytearray(good)
        put(damaged, 64 + 32 + 8, 0x40004)
        result, memory, _ = self.install(seal(damaged))
        self.assertNotEqual(result, 0)
        self.assertEqual(memory, bytes([SENTINEL]) * len(memory))

    def test_v3_late_hook_rejection_precedes_any_install(self):
        native = legacy.ModBinTests.native(None, legacy.packer.build_mod_bin(legacy.manifest()))
        struct.pack_into("=I", native, len(native) - 8, stage(0))
        result, memory, _ = self.install(native)
        self.assertNotEqual(result, 0)
        self.assertEqual(memory, bytes([SENTINEL]) * len(memory))

    def test_header_valid_and_file_size_read_only_first_cache_line(self):
        kernel = C.WinDLL("kernel32", use_last_error=True)
        kernel.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, C.c_uint]
        kernel.VirtualAlloc.restype = C.c_void_p
        kernel.VirtualProtect.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, C.POINTER(C.c_uint)]
        kernel.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, C.c_uint]
        allocation = kernel.VirtualAlloc(None, mmap.PAGESIZE * 2, 0x3000, 4)
        self.assertTrue(allocation)
        try:
            previous = C.c_uint()
            self.assertTrue(kernel.VirtualProtect(allocation + mmap.PAGESIZE, mmap.PAGESIZE, 1, C.byref(previous)))
            pointer = allocation + mmap.PAGESIZE - 32
            v3 = legacy.ModBinTests.native(None, legacy.packer.build_mod_bin(legacy.manifest()))
            for data in (v3, tiny(), tiny(cold=True), tiny(flags=1, cold=True)):
                C.memmove(pointer, bytes(data[:32]), 32)
                self.assertTrue(self.h.lib.production_header(pointer, GAMES["jp"]))
                self.assertEqual(self.h.lib.production_size(pointer), len(data))
            for offset in (16, 20):
                damaged = bytearray(tiny())
                put(damaged, offset, 0xFFFFFFFF)
                C.memmove(pointer, bytes(damaged[:32]), 32)
                self.assertFalse(self.h.lib.production_header(pointer, GAMES["jp"]))
                self.assertEqual(self.h.lib.production_size(pointer), 0)
        finally:
            self.assertTrue(kernel.VirtualFree(allocation, 0, 0x8000))


if __name__ == "__main__":
    unittest.main()
