"""V9 metadata through production ARM storage and the independent host reader."""
import ctypes
import struct
import unittest
import zlib

import validate_ghost as ghost
import test_ghost_camera_storage as camera_fixture
from test_ghost_camera_storage import camera_file
from test_ghost_format import build_ghost
from test_ghost_kernel_paging import IMPORT
from test_ghost_storage import rechecksum_ghost
from test_ghost_teaching import teaching_file


def rng_file(seed=0x12345678, provenance=1, base=None):
    out = bytearray(camera_file() if base is None else base)
    struct.pack_into('>H', out, 4, 9)
    struct.pack_into('>I', out, 24, 63)
    struct.pack_into('>II', out, 0x118, seed, provenance)
    return seal_table(out)


def seal_table(data):
    out = bytearray(data)
    struct.pack_into('>I', out, 204, zlib.crc32(out[0x100:0x900]))
    return rechecksum_ghost(out)


class InitialRngTests(unittest.TestCase):
    setUpClass = classmethod(camera_fixture.CameraStorageTests.setUpClass.__func__)
    setUp = camera_fixture.CameraStorageTests.setUp
    add = camera_fixture.CameraStorageTests.add
    file = camera_fixture.CameraStorageTests.file
    request = camera_fixture.CameraStorageTests.request
    page = camera_fixture.CameraStorageTests.page
    accepted = camera_fixture.CameraStorageTests.accepted
    rejected = camera_fixture.CameraStorageTests.rejected

    def test_all_seed_bits_and_legacy_files_round_trip(self):
        for seed in (0, 0x12345678, 0x80000000, 0xffffffff):
            with self.subTest(seed=seed):
                self.dll.reset()
                result = self.accepted(rng_file(seed))
                self.assertEqual(result['initial_rng'],
                                 {'seed': seed, 'provenance': 'first_recorded_pose'})
        old = [build_ghost(version=3), build_ghost(version=4), teaching_file(),
               teaching_file(fludd=[bytes(8)] * 3),
               teaching_file(fludd=[bytes(8)] * 3, extended=True), camera_file()]
        for data in old:
            with self.subTest(version=struct.unpack_from('>H', data, 4)[0]):
                self.dll.reset()
                self.assertIsNone(self.accepted(data)['initial_rng'])

    def test_catalog_and_load_preserve_seed_and_camera(self):
        data = rng_file(0xfedcba98, base=camera_file(5312, 1))
        self.add(IMPORT + 'seed.smsghost', data)
        rows, total, _, _ = self.page(profile=4)
        self.assertEqual((len(rows), total, rows[0][2]), (1, 1, 'seed.smsghost'))
        result = self.request(2, rows[0][0], profile=4, generation=rows[0][1],
                              payload=b'seed.smsghost'.ljust(96, b'\0'))
        self.assertEqual(result['status'], 0)
        self.assertEqual(ctypes.string_at(self.dll.payload(), result['size']), data)
        self.assertLessEqual(self.dll.maximumRead(), 0x4000)

    def test_provenance_version_and_reserved_segments_are_checked(self):
        for flags in (0, 2, 3, 0x80000001, 0xffffffff):
            with self.subTest(flags=flags):
                self.rejected(rng_file(provenance=flags))
        legacy = bytearray(rng_file())
        struct.pack_into('>H', legacy, 4, 8)
        struct.pack_into('>I', legacy, 24, 31)
        self.rejected(rechecksum_ghost(legacy))
        unused = bytearray(rng_file())
        struct.pack_into('>II', unused, 0x138, 42, 1)
        self.rejected(seal_table(unused))
        wrong_mask = bytearray(rng_file())
        struct.pack_into('>I', wrong_mask, 24, 31)
        self.rejected(rechecksum_ghost(wrong_mask))

    def test_later_used_segments_cannot_claim_another_initial_seed(self):
        data = bytearray(rng_file(base=camera_file(0)))
        struct.pack_into('>H', data, 184, 2)
        struct.pack_into('>I', data, 0x104, 1)
        struct.pack_into('>I', data, 0x10c, 100)
        struct.pack_into('>4Ii4B2I', data, 0x120, 1, 1, 104, 104, 0, 2, 0, 255, 0, 0, 0)
        struct.pack_into('>H', data, 0x912, 0)
        self.accepted(seal_table(data))
        struct.pack_into('>II', data, 0x138, 17, 1)
        self.rejected(seal_table(data))

    def test_seed_is_covered_by_segment_and_outer_checksums(self):
        bad = bytearray(rng_file())
        bad[0x118] ^= 1
        self.rejected(bytes(bad))
        self.rejected(rechecksum_ghost(bad))
        self.assertEqual(self.accepted(seal_table(bad))['initial_rng']['seed'], 0x13345678)


if __name__ == '__main__':
    unittest.main()
