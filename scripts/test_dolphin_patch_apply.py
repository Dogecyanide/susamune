"""The packaged ISO patcher preserves source/existing files and validates CRCs."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from gen_iso_bps import BpsBuilder

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dolphin_patch_apply", ROOT / "tools/dolphin_online/apply_patch.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class PatchApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="moonshine-bps-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source.iso"
        self.patch = self.folder / "patch.bps"
        self.output = self.folder / "output.iso"
        self.original = b"abcdefghijklmnopqrstuvwx"
        self.source.write_bytes(self.original)
        builder = BpsBuilder({(0, 4): zlib.crc32(self.original[:4]),
                              (12, 4): zlib.crc32(self.original[12:16]),
                              (4, 4): zlib.crc32(self.original[4:8])})
        builder.source_read(0, 4)
        builder.target_read(b"NEW")
        builder.source_copy(12, 4)
        builder.source_copy(4, 4)
        builder.zeros(19)
        self.expected = b"abcdNEWmnopefgh" + bytes(19)
        self.encoded = builder.encode(len(self.original), zlib.crc32(self.original))
        self.patch.write_bytes(self.encoded)

    def test_all_copy_modes_and_overlapping_target_copy(self):
        app.apply(self.source, self.patch, self.output)
        self.assertEqual(self.output.read_bytes(), self.expected)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_source_mismatch_creates_nothing(self):
        self.source.write_bytes(b"X" + self.original[1:])
        with self.assertRaisesRegex(ValueError, "Source checksum"):
            app.apply(self.source, self.patch, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_replaced(self):
        self.output.write_bytes(b"KEEP")
        with self.assertRaises(FileExistsError):
            app.apply(self.source, self.patch, self.output)
        self.assertEqual(self.output.read_bytes(), b"KEEP")

    def test_bad_patch_is_rejected_before_output(self):
        self.patch.write_bytes(self.encoded[:-1] + bytes([self.encoded[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "patch checksum"):
            app.apply(self.source, self.patch, self.output)
        self.assertFalse(self.output.exists())

    def test_bad_target_checksum_removes_only_created_output(self):
        data = bytearray(self.encoded)
        data[-8] ^= 1
        struct.pack_into("<I", data, len(data)-4, zlib.crc32(data[:-4]))
        self.patch.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Patched ISO checksum"):
            app.apply(self.source, self.patch, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
