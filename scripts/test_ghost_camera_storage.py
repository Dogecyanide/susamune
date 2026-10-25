"""V8 camera tails through independent host and production ARM storage validation."""
import ctypes
import struct
import unittest
import zlib

import validate_ghost as ghost
import validate_ghost_storage as storage
from test_ghost_format import build_ghost
from test_ghost_teaching import teaching_file
from test_ghost_storage import envelope, rechecksum_ghost
import test_ghost_kernel_paging as kernel
from test_ghost_kernel_paging import AUTO, PERSONAL, IMPORT


def camera_file(count=3, flags=0):
    end = max(4, count - 1)
    base = build_ghost(version=4, start_qf=100,
                       samples=[(0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0, end, 0, 0)])
    prefix = teaching_file(inputs=[], splits=[], base=base, fludd=[], extended=True)
    samples = bytearray()
    for i in range(count):
        samples.extend(struct.pack('>I', 100 + i) + bytes(9) +
                       struct.pack('>4hHB', 0, 0, 0, 32767, 45 * 256, 64 if not i else 0))
    header = struct.pack('>IHH6I', 0x53474341, 1, 32, count, flags, zlib.crc32(samples), 0, 0, 0)
    out = bytearray(prefix + header + samples)
    struct.pack_into('>H', out, 4, 8)
    struct.pack_into('>I', out, 8, len(out))
    struct.pack_into('>I', out, 24, 31)
    struct.pack_into('>I', out, 72, len(out) - 256)
    return rechecksum_ghost(out)


def camera_offset(data):
    return 0x900 + struct.unpack_from('>I', data, 68)[0] * 16 + 32


def change_camera(data, offset, value, seal=True):
    out = bytearray(data)
    begin = camera_offset(out)
    out[begin + offset:begin + offset + len(value)] = value
    if seal:
        struct.pack_into('>I', out, begin + 16, zlib.crc32(out[begin + 32:]))
    return rechecksum_ghost(out)


class CameraStorageTests(unittest.TestCase):
    setUpClass = classmethod(kernel.GhostKernelPagingTests.setUpClass.__func__)
    setUp = kernel.GhostKernelPagingTests.setUp
    add = kernel.GhostKernelPagingTests.add
    file = kernel.GhostKernelPagingTests.file
    request = kernel.GhostKernelPagingTests.request
    page = kernel.GhostKernelPagingTests.page

    def accepted(self, data):
        result = ghost.validate_ghost(data)
        storage.validate_slot_file(envelope(data), game_id=0x474D534A, profile=0, slot=0)
        saved = self.request(1, AUTO, payload=data)
        self.assertEqual(saved['status'], 0)
        self.assertEqual(self.file(PERSONAL + f"g{saved['slot']:02}a.sgh")[64:], data)
        return result

    def rejected(self, data):
        with self.assertRaises(ghost.FormatError):
            ghost.validate_ghost(data)
        self.assertNotEqual(self.request(1, AUTO, payload=data)['status'], 0)

    def test_empty_and_maximum_camera_streams_are_valid_and_chunked(self):
        for count in (0, 3, 5312):
            with self.subTest(count=count):
                self.dll.reset()
                result = self.accepted(camera_file(count, int(count == 5312)))
                self.assertEqual(result['camera']['sample_count'], count)
                self.assertEqual(result['camera']['truncated'], count == 5312)
                self.assertGreater(self.passes, 1)
                self.assertLessEqual(self.dll.maximumRead(), 0x4000)

    def test_catalog_import_and_personal_load_preserve_camera_tail(self):
        data = camera_file()
        self.add(IMPORT + 'camera.smsghost', data)
        rows, total, _, _ = self.page(profile=4)
        self.assertEqual((len(rows), total, rows[0][2]), (1, 1, 'camera.smsghost'))
        result = self.request(2, rows[0][0], profile=4, generation=rows[0][1],
                              payload=b'camera.smsghost'.ljust(96, b'\0'))
        self.assertEqual(result['status'], 0)
        self.assertEqual(ctypes.string_at(self.dll.payload(), result['size']), data)
        self.accepted(data)
        rows, total, _, _ = self.page()
        result = self.request(2, rows[0][0], generation=rows[0][1])
        self.assertEqual(result['status'], 0)
        self.assertEqual(ctypes.string_at(self.dll.payload(), result['size']), data)

    def test_malformed_camera_header_and_samples_are_rejected_by_both_readers(self):
        data = camera_file()
        changes = [(0, b'BAD!'), (5, b'\x02'), (7, b'\x21'),
                   (8, struct.pack('>I', 5313)), (12, struct.pack('>I', 2)),
                   (20, b'\x01'), (24, b'\x01'), (28, b'\x01'),
                   (32, struct.pack('>I', 99)), (56, struct.pack('>I', 100)),
                   (32 + 13, bytes(8)), (32 + 21, b'\x00\xff'),
                   (32 + 21, struct.pack('>H', 180 * 256)),
                   (32 + 23, b'\x00'), (32 + 23, b'\x7f'), (32 + 23, b'\xc0')]
        for offset, value in changes:
            with self.subTest(offset=offset, value=value):
                self.rejected(change_camera(data, offset, value))

    def test_camera_crc_and_teaching_boundary_remain_independent(self):
        data = camera_file()
        self.rejected(change_camera(data, 32 + 4, b'\x01', seal=False))
        malformed = bytearray(data)
        struct.pack_into('>I', malformed, camera_offset(data) - 32 + 8, 0xffffffff)
        self.rejected(rechecksum_ghost(malformed))
        for amount in (1, 24, 32):
            truncated = bytearray(data[:-amount])
            struct.pack_into('>I', truncated, 8, len(truncated))
            struct.pack_into('>I', truncated, 72, len(truncated) - 256)
            self.rejected(rechecksum_ghost(truncated))


if __name__ == '__main__':
    unittest.main()
