"""Check workspace-backed slicing CRC against the existing archive checksum."""

import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


class StateCrcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-slicing-crc-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = work / "crc.cpp"
        source.write_text(r'''
#include "susamune/state_crc.hxx"
#include "susamune/state_storage.h"
extern "C" {
__declspec(dllexport) int init(void*w,unsigned n){return StateCrc::init(w,n);}
__declspec(dllexport) unsigned update(const void*w,unsigned crc,const void*p,unsigned n){return StateCrc::update(w,crc,p,n);}
__declspec(dllexport) unsigned original(unsigned crc,const void*p,unsigned n){return SusamuneStateCrcUpdate(crc,p,n);}
}
''', encoding="ascii")
        dll = work / "crc.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-Oz",
            "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-I", str(ROOT / "include"),
            str(source), str(ROOT / "src/state_crc.cpp"), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)
        cls.lib.init.argtypes = [C.c_void_p, C.c_uint]
        cls.lib.update.argtypes = [C.c_void_p, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.original.argtypes = [C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.update.restype = cls.lib.original.restype = C.c_uint

    def workspace(self):
        storage = C.create_string_buffer(bytes([0xA7]) * (4096 + 64))
        pointer = (C.addressof(storage) + 31) & ~3
        self.assertTrue(self.lib.init(pointer, 4096))
        self.assertEqual(C.string_at(C.addressof(storage), pointer-C.addressof(storage)),
                         bytes([0xA7]) * (pointer-C.addressof(storage)))
        end = pointer + 4096
        self.assertEqual(C.string_at(end, C.addressof(storage) + 4160-end),
                         bytes([0xA7]) * (C.addressof(storage) + 4160-end))
        return storage, pointer

    def test_standard_vectors_all_alignments_and_seed_semantics(self):
        storage, workspace = self.workspace()
        rng = random.Random(0x43524334)
        cases = [b"", b"123456789", bytes(range(256))]
        cases.extend(rng.randbytes(size) for size in (*range(1, 36), 255, 256, 257, 4095, 4096, 4097, 65537, 6000001))
        for data in cases:
            for alignment in range(4):
                owner = C.create_string_buffer(alignment + len(data) + 4)
                pointer = C.addressof(owner) + alignment
                C.memmove(pointer, data, len(data))
                for seed in (0, 0xFFFFFFFF, 0xCBF43926, rng.getrandbits(32)):
                    actual = self.lib.update(workspace, seed, pointer, len(data))
                    self.assertEqual(actual, self.lib.original(seed, pointer, len(data)))
                    self.assertEqual(actual, (~zlib.crc32(data, (~seed) & 0xFFFFFFFF)) & 0xFFFFFFFF)

    def test_fragmented_spans_and_zero_length_preserve_running_crc(self):
        storage, workspace = self.workspace()
        rng = random.Random(0x46524147)
        data = rng.randbytes(100003)
        owner = C.create_string_buffer(data)
        for chunk in (1, 2, 3, 4, 7, 31, 16384, 65536):
            crc = 0xFFFFFFFF
            for offset in range(0, len(data), chunk):
                self.assertEqual(self.lib.update(None, crc, None, 0), crc)
                crc = self.lib.update(workspace, crc, C.addressof(owner) + offset,
                                      min(chunk, len(data)-offset))
            self.assertEqual((~crc) & 0xFFFFFFFF, zlib.crc32(data))

    def test_init_rejects_small_misaligned_and_wrapping_workspaces_without_writes(self):
        storage = C.create_string_buffer(bytes([0xA7]) * 4160)
        pointer = (C.addressof(storage) + 31) & ~3
        before = storage.raw
        for address, size in ((None, 4096), (pointer, 4095), (pointer + 1, 4096),
                              (pointer + 2, 4096), (pointer + 3, 4096),
                              ((1 << (C.sizeof(C.c_void_p)*8))-4096, 4096)):
            self.assertFalse(self.lib.init(address, size))
            self.assertEqual(storage.raw, before)

    def test_tables_can_be_regenerated_after_the_codec_overwrites_workspace(self):
        storage, workspace = self.workspace()
        tables = C.string_at(workspace, 4096)
        C.memset(workspace, 0x5B, 4096)
        self.assertTrue(self.lib.init(workspace, 4096))
        self.assertEqual(C.string_at(workspace, 4096), tables)
        words = (C.c_uint * 1024).from_address(workspace)
        for byte in range(256):
            value = byte
            for slice in range(4):
                for _ in range(8):
                    value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
                self.assertEqual(words[slice*256 + byte], value)


if __name__ == "__main__":
    unittest.main()
