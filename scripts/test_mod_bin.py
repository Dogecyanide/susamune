"""Executable V3 span validation and protected-hole regression tests."""
import ctypes
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("packer", ROOT / "scripts/gen_mod_bin.py")
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)

def manifest(low=8, upper=4, low_mem=16, upper_mem=16):
    return {"game_id": 0x474D534A, "base_addr": 0x80426020,
            "region_reserve": 0xC2000,
            "segments": [{"offset": 0, "code": "12" * low, "memory_size": low_mem},
                         {"offset": 0x80000, "code": "34" * upper, "memory_size": upper_mem}],
            "writes": [(0x8000561C, 0x48000001)]}

class ModBinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        assert folder.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        src = folder / "validator.c"
        src.write_text('#include "susamune/mod_bin.h"\n__declspec(dllexport) int validate(const struct SusamuneModHeader *h, unsigned int n) { return SusamuneModFileValid(h, h->gameId, n); }\n')
        dll = folder / "validator.dll"
        subprocess.run([str(ROOT / "toolchain/clang.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
                        "-I", str(ROOT / "include"), str(src), "-o", str(dll)], check=True, capture_output=True)
        cls.library = ctypes.CDLL(str(dll))
        cls.validate = cls.library.validate
        cls.validate.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        cls.validate.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        import _ctypes
        del cls.validate
        _ctypes.FreeLibrary(cls.library._handle)
        del cls.library
        cls.temp.cleanup()

    def native(self, packed):
        # Shared C consumers see native words; this host is little endian.
        h = struct.unpack(">8I", packed[:32])
        words = list(h) + list(struct.unpack(">8I", packed[32:64]))
        out = bytearray(struct.pack("=16I", *words))
        out.extend(packed[64:32+h[4]])
        for off in range(32+h[4], len(packed), 8):
            out.extend(struct.pack("=2I", *struct.unpack(">2I", packed[off:off+8])))
        return out

    def valid(self, data):
        buf = ctypes.create_string_buffer(bytes(data))
        return self.validate(buf, len(data))

    def test_valid_scatter_and_bss(self):
        packed = packer.build_mod_bin(manifest())
        h = struct.unpack(">8I", packed[:32])
        self.assertEqual((h[1], h[4], h[7]), (3, 44, 32))
        self.assertTrue(self.valid(self.native(packed)))
        dest = bytearray([0xA5]) * 0xC0000
        for i in range(2):
            off, init, size, payload = struct.unpack_from(">4I", packed, 32+i*16)
            dest[off:off+init] = packed[32+payload:32+payload+init]
            dest[off+init:off+size] = bytes(size-init)
        self.assertEqual(dest[8:16], bytes(8))
        self.assertEqual(dest[0x80004:0x80010], bytes(12))
        self.assertEqual(dest[0x58000:0x80000], bytes([0xA5]) * 0x28000)

    def test_full_capacity_and_ceiling(self):
        value = manifest(0x58000, 0x40000, 0x58000, 0x40000)
        value.update(game_id=0x474D5345, base_addr=0x80429800)
        packed = packer.build_mod_bin(value)
        self.assertTrue(self.valid(self.native(packed)))
        value["writes"] *= 10000
        with self.assertRaisesRegex(ValueError, "ceiling"):
            packer.build_mod_bin(value)

    def test_jp_file_cannot_overlap_immutable_translation(self):
        low = 0x58000
        upper = packer.JP_STAGED_FILE_MAX_SIZE - low - 64 - 8
        value = manifest(low, upper, low, upper)
        self.assertEqual(len(packer.build_mod_bin(value)), packer.JP_STAGED_FILE_MAX_SIZE)
        value['segments'][1]['code'] += '00000000'
        value['segments'][1]['memory_size'] += 4
        with self.assertRaisesRegex(ValueError, 'Japanese UI'):
            packer.build_mod_bin(value)

    def test_host_rejects_holes_overflow_wrong_revision(self):
        for change in (lambda m: m["segments"][0].update(memory_size=0x58004),
                       lambda m: m["segments"][1].update(offset=0x7FFC0),
                       lambda m: m["segments"][1].update(memory_size=0x40004),
                       lambda m: m.update(region_reserve=0x82000),
                       lambda m: m.update(base_addr=0x80429800),
                       lambda m: m.update(writes=[(0x91F00000, 0)])):
            value = manifest()
            change(value)
            with self.assertRaises(ValueError): packer.build_mod_bin(value)

    def test_c_consumer_rejects_corrupt_descriptors_and_hooks(self):
        good = self.native(packer.build_mod_bin(manifest()))
        # Every offset is a native u32 in the shared C header/body.
        changes = {4: 2, 12: 0x80429800, 16: 0xFFFFFFFF, 20: 0xFFFFFFFF,
                   24: 0x82000, 28: 0x98004, 32: 0x58000, 36: 20,
                   40: 0x58004, 44: 0, 48: 0x7FFC0, 52: 0x40004,
                   56: 0x40004, 60: 0, 76: 0x91F00000}
        for offset, word in changes.items():
            damaged = good.copy()
            struct.pack_into("=I", damaged, offset, word)
            with self.subTest(offset=offset): self.assertFalse(self.valid(damaged))
        self.assertFalse(self.valid(good[:-4]))
        self.assertFalse(self.valid(good + bytes(4)))

if __name__ == "__main__": unittest.main()
