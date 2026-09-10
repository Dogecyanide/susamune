import ctypes
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from decode_crash import decode_binary, decode_text, render, symbolize

ROOT = Path(__file__).resolve().parents[1]


def finish(data):
    struct.pack_into(">I", data, 16, 0)
    struct.pack_into(">I", data, 16, zlib.crc32(data) & 0xFFFFFFFF)
    return bytes(data)


def fixture(core=False):
    data = bytearray(512 if core else 2048)
    struct.pack_into(">IHH6I", data, 0, 0x53434352 if core else 0x53435248,
                     1, len(data), 3, 7, 0, 0x474D534A, 0x12345678, 2 if core else 4096)
    struct.pack_into(">I", data, 176 if core else 208, 0x80427000)
    struct.pack_into(">I", data, 228 if core else 292, 1 if core else 0)
    if core:
        data[232:239] = b"FOXTROT"
    else:
        struct.pack_into(">H", data, 44, 2)
    return data


class CrashReportTests(unittest.TestCase):
    def test_both_binary_formats(self):
        for core in (False, True):
            report = decode_binary(finish(fixture(core)))
            self.assertEqual(report["pc"], 0x80427000)
            self.assertEqual(report["exception"], 2)
            self.assertTrue(report["verified"])

    def test_corruption_and_truncation(self):
        data = bytearray(finish(fixture(True)))
        data[177] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            decode_binary(bytes(data))
        with self.assertRaisesRegex(ValueError, "length"):
            decode_binary(finish(fixture())[:-1])

    def test_complete_crc_does_not_excuse_invalid_counts(self):
        data = fixture()
        struct.pack_into(">I", data, 292, 17)
        with self.assertRaisesRegex(ValueError, "out-of-bounds"):
            decode_binary(finish(data))
        data = fixture()
        struct.pack_into(">H", data, 1540, 321)
        with self.assertRaisesRegex(ValueError, "out-of-bounds"):
            decode_binary(finish(data))

    def test_wrapped_events_stay_chronological(self):
        data = fixture()
        struct.pack_into(">II", data, 288, 1, 2)
        struct.pack_into(">5I", data, 296 + 15 * 20, 6, 0, 10, 11, 12)
        struct.pack_into(">5I", data, 296, 7, 0, 20, 21, 22)
        events = decode_binary(finish(data))["breadcrumbs"]
        self.assertEqual([event["event"] for event in events], [6, 7])

    def test_copied_photo_fields_do_not_claim_crc_verification(self):
        result = decode_text("REPORT 00000007-12345678 JP/GMSJ MOD 12345678\n"
                             "PC 80427000 LR 80001000 SP 817FFFF0\nEXCEPTION 2 (DSI)")
        self.assertFalse(result["verified"])
        self.assertIn("cannot be verified", render(result))

    def test_retail_console_photo_block(self):
        result = decode_text("MOONSHINE V2.3.0 FOXTROT\n"
            "REPORT 00000007-89ABCDEF\nJP/GMSJ  MOD 12345678\n"
            "EXCEPTION 2  CONTEXT 1\nPC 80427000  LR 80001000\n"
            "SP 817FFFF0  DAR 00000004\nDSISR 00000000  SRR1 0000B032\n"
            "SCENE 06000000  LAST 7\nSAVE: complete\n")
        self.assertEqual(result["generation"], 7)
        self.assertEqual(result["game_id"], 0x474D534A)
        self.assertEqual(result["mod_crc32"], 0x12345678)
        self.assertEqual(result["pc"], 0x80427000)
        self.assertEqual(result["sp"], 0x817FFFF0)
        self.assertFalse(result["verified"])

    def test_symbols_require_matching_build_and_bounded_function(self):
        report = decode_binary(finish(fixture()))
        manifest = dict(game_id=0x474D534A, mod_crc32=0x12345678,
                        symbols=[dict(address=0x80426F00, size=0x200, name="example")])
        symbolize(report, manifest)
        self.assertEqual(report["symbols"]["pc"], "example+0x100")
        manifest["mod_crc32"] = 0
        with self.assertRaisesRegex(ValueError, "does not match"):
            symbolize(report, manifest)


class KernelChecksumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clang = ROOT / "toolchain/clang.exe"
        if sys.platform != "win32" or not clang.exists():
            raise unittest.SkipTest("Bundled Windows compiler required for native C fixture")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-crash-crc-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        production = (ROOT / "launcher/kernel/SusamuneCrash.c").read_text()
        common = (ROOT / "launcher/kernel/common.c").read_text()
        header = (ROOT / "launcher/kernel/common.h").read_text()
        checksums = header[header.index("extern const u32 SusamuneCrcNibbleTable"):
                           header.index("#define SEEK_CUR")]
        checksums += common[common.index("const u32 SusamuneCrcNibbleTable"):
                            common.index("void BootStatus(")]
        checksums += production[production.index("static u32 ReportChecksum"):
                               production.index("static u32 CrashChecksum")]
        checksums += production[production.index("static u32 ModFileCrc"):
                                production.index("static bool ValidStagedMod")]
        patch = (ROOT / "launcher/kernel/Patch.c").read_text()
        validators = patch[patch.index("static bool SusamuneShadowAssetValid("):
                           patch.index("static void SusamunePublishAsset(")]
        source = work / "crc.c"
        source.write_text('''typedef unsigned int u32;
typedef unsigned char u8;
typedef _Bool bool;
#include "susamune/crash_report.h"
#include "susamune/mod_bin.h"
#include "susamune/ghost_model_asset.h"
static u32 syncSize;
static void sync_before_read(void *data, u32 size) { syncSize = size; }
''' + checksums + validators + '''
__declspec(dllexport) u32 reportCrc(const void *data, u32 size) {
    return ReportChecksum(data, size);
}
__declspec(dllexport) u32 modCrc(const void *data, u32 size) {
    return ModFileCrc((const struct SusamuneModHeader *)data, size);
}
__declspec(dllexport) u32 assetCrc(const void *data, u32 size) {
    return SusamuneCrc32(data, size);
}
__declspec(dllexport) u32 byteCrc(u32 crc, u8 byte) {
    return SusamuneCrcByte(crc, byte);
}
__declspec(dllexport) int validAsset(const void *data, int pianta) {
    syncSize = 0;
    return pianta ? SusamunePiantaAssetValid(data) : SusamuneShadowAssetValid(data);
}
__declspec(dllexport) u32 assetSyncSize(void) { return syncSize; }
''', encoding="ascii")
        library = work / "crc.dll"
        subprocess.run([str(clang), "--target=x86_64-pc-windows-msvc", "-O2",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, capture_output=True, text=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(
            ctypes.c_void_p(cls.dll._handle)))
        for name in ("reportCrc", "modCrc", "assetCrc"):
            getattr(cls.dll, name).argtypes = [ctypes.c_void_p, ctypes.c_uint]
            getattr(cls.dll, name).restype = ctypes.c_uint
        cls.dll.byteCrc.argtypes = [ctypes.c_uint, ctypes.c_ubyte]
        cls.dll.byteCrc.restype = ctypes.c_uint
        cls.dll.validAsset.argtypes = [ctypes.c_void_p, ctypes.c_int]
        cls.dll.validAsset.restype = ctypes.c_int
        cls.dll.assetSyncSize.restype = ctypes.c_uint

    def test_production_mod_crc_matches_ieee_vectors_and_staging_limit(self):
        rng = random.Random(0x435243)
        vectors = [b"", b"123456789", bytes(range(256))]
        vectors += [rng.randbytes(size) for size in
                    (1, 15, 16, 17, 19, 20, 21, 31, 32, 511, 512, 2048, 0x9F000)]
        for data in vectors:
            with self.subTest(size=len(data)):
                self.assertEqual(self.dll.modCrc(data, len(data)), zlib.crc32(data))

    def test_production_report_crc_ignores_only_checksum_field(self):
        rng = random.Random(0x53434352)
        for size in [0, 15, 16, 17, 19, 20, 21, 512, 2048]:
            for _ in range(16):
                data = rng.randbytes(size)
                expected = bytearray(data)
                expected[16:min(20, size)] = bytes(max(0, min(20, size) - 16))
                self.assertEqual(self.dll.reportCrc(data, size), zlib.crc32(expected))
        for core in (False, True):
            data = finish(fixture(core))
            self.assertEqual(self.dll.reportCrc(data, len(data)),
                             struct.unpack_from(">I", data, 16)[0])

    def test_current_mod_artifacts_match_kernel_checksum(self):
        paths = list((ROOT / "build").glob("mod_*.bin"))
        if not paths:
            self.skipTest("No built mod artifacts")
        for path in paths:
            data = path.read_bytes()
            with self.subTest(region=path.stem):
                self.assertEqual(self.dll.modCrc(data, len(data)), zlib.crc32(data))

    def test_shared_crc_covers_every_byte_for_varied_internal_states(self):
        states = (0, 1, 0xFFFFFFFF, 0x80000000, 0x12345678, 0xEDB88320)
        for state in states:
            for byte in range(256):
                expected = zlib.crc32(bytes((byte,)), state ^ 0xFFFFFFFF) ^ 0xFFFFFFFF
                self.assertEqual(self.dll.byteCrc(state, byte), expected)

    def test_shared_asset_crc_is_byte_order_and_alignment_independent(self):
        words = (0, 1, 0xFFFFFFFF, 0x01234567, 0x89ABCDEF, 0x80000000)
        vectors = [struct.pack(endian + "6I", *words) for endian in (">", "<")]
        vectors += [bytes(range(256)), bytes(reversed(range(256)))]
        for data in vectors:
            for offset in range(8):
                storage = ctypes.create_string_buffer(b"x" * offset + data + b"y" * 8)
                self.assertEqual(self.dll.assetCrc(ctypes.byref(storage, offset), len(data)),
                                 zlib.crc32(data))

    def test_production_asset_validators_keep_header_crc_and_cache_guards(self):
        for pianta, magic, span, bmd_size, btk_size, checksum in (
            (0, 0x5347534D, 0x10000, 0xF8C0, 0x440, 0xFC04D868),
            (1, 0x5347504D, 0x12000, 0x119A0, 0, 0x448001A9),
        ):
            asset = bytearray(span)
            storage = ctypes.create_string_buffer(bytes(asset))
            self.assertEqual(self.dll.validAsset(storage, pianta), 0)
            self.assertEqual(self.dll.assetSyncSize(), span)
            struct.pack_into("<IHH i 5I", asset, 0, magic, 1, 32, 1,
                             32 + bmd_size + btk_size, 32, bmd_size, checksum, 0)
            storage = ctypes.create_string_buffer(bytes(asset))
            self.assertEqual(self.dll.validAsset(storage, pianta), 0)
            self.assertEqual(self.dll.assetSyncSize(), span)


if __name__ == "__main__":
    unittest.main()
