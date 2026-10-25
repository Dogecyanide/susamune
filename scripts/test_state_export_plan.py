"""Export shared roots through the real ARM coordinator and archive worker."""
import ctypes as C
import struct
import unittest
import zlib

import test_state_storage_kernel as state
from test_transfer_coordinator import CoordinatorChecks, bridge

MAGIC = 0x51504C31
FRAME = b'MSL4\x00\x02\x00\x00'


class Range(C.Structure):
    _fields_ = [('offset', C.c_uint), ('size', C.c_uint)]


class Plan(C.Structure):
    _fields_ = [(name, C.c_uint) for name in
        ('magic', 'version', 'count', 'raw', 'packed', 'metadata', 'checksum', 'kind')]
    _fields_ += [('blocks', Range * 256)]

    def seal(self):
        self.checksum = 0
        self.checksum = zlib.crc32(bytes(self))


class ExportPlanTests(unittest.TestCase):
    fixture_transform = CoordinatorChecks.fixture_transform
    bridge_source = bridge('state')
    setUpClass = classmethod(state.StateStorageKernelTests.setUpClass.__func__)
    setup_coordinator = CoordinatorChecks.setup_coordinator
    wire = CoordinatorChecks.wire
    activate = CoordinatorChecks.activate
    remote = CoordinatorChecks.remote
    buffer = state.StateStorageKernelTests.buffer
    file = state.StateStorageKernelTests.file

    def setUp(self):
        self.setup_coordinator()
        self.lib.poolPointer.restype = C.c_void_p
        self.lib.poolPointer.argtypes = [C.c_uint]

    def prepare(self, entries=None, kind=0, raw_size=None):
        if entries is None:
            addresses = (0x8000, 0xFF0000, 0x11F0000, 0x8000, 0x12B2000)
            entries = []
            for i, address in enumerate(addresses):
                raw = bytes([21 if address == 0x8000 else i + 31]) * (77 if i == 4 else 0x20000)
                block = struct.pack('>II', len(raw), 0x80000000 | len(raw)) + raw
                entries.append((address, block))
        meta = b'unchanged snapshot metadata'
        self.lib.prepare(self.buffer(bytes(8)), 8, 0x8000, self.buffer(meta), len(meta))
        packed = (FRAME if kind == 0 else b'') + b''.join(block for _, block in entries)
        h = state.Header.from_address(self.lib.mailbox() + 96)
        h.packedSize = len(packed)
        h.rawSize = raw_size if raw_size is not None else sum(struct.unpack_from('>I', block)[0] for _, block in entries)
        h.headerCrc = 0
        h.headerCrc = zlib.crc32(bytes(h))
        plan = Plan(MAGIC, 2, len(entries), h.rawSize, h.packedSize, h.metadataCrc, 0, kind)
        for i, (offset, block) in enumerate(entries):
            C.memmove(self.lib.poolPointer(offset), block, len(block))
            plan.blocks[i] = Range(offset, len(block))
        plan.seal()
        C.memmove(self.lib.staging(), bytes(plan), C.sizeof(plan))
        self.lib.submit(state.EXPORT, 0, 0, len(packed), 0, 11)
        self.lib.windowSize(MAGIC)
        return packed, meta, plan

    def send(self):
        seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.remote(2, seq, state.EXPORT, 11)

    def finish(self):
        self.assertGreater(self.lib.pump(10000), 0)
        self.assertEqual(self.wire().response.phase, 7)
        self.assertTrue(self.lib.guards())
        return C.c_uint.from_address(self.lib.mailbox() + 44).value

    def test_four_banks_and_repeated_blocks_export_the_canonical_stream(self):
        self.activate()
        packed, meta, plan = self.prepare()
        self.send()
        self.assertEqual(self.finish(), state.OK)
        data = self.file()
        header = state.Header.from_buffer_copy(data)
        self.assertEqual(data[96:96 + len(meta)], meta)
        self.assertEqual(data[96 + len(meta):], packed)
        self.assertEqual(header.payloadCrc, zlib.crc32(packed))
        self.assertEqual(C.string_at(self.lib.staging(), C.sizeof(plan)), bytes(plan))

    def test_invalid_plan_fields_and_block_bounds_refuse_before_file_writes(self):
        for kind in ('magic', 'version', 'count', 'empty', 'crc', 'kind', 'metadata',
                     'raw', 'packed', 'directory', 'unaligned', 'overflow', 'size',
                     'trailing', 'bank_crossing', 'raw_header', 'packed_header'):
            with self.subTest(kind=kind):
                self.setUp()
                self.activate()
                _, _, plan = self.prepare()
                if kind == 'empty': plan.count = 0
                elif kind == 'count': plan.count = 257
                elif kind == 'kind': plan.kind = 2
                elif kind in ('magic', 'version', 'metadata', 'raw', 'packed'):
                    setattr(plan, kind, getattr(plan, kind) + 1)
                elif kind == 'directory': plan.blocks[0].offset = 0x7FE0
                elif kind == 'unaligned': plan.blocks[0].offset += 1
                elif kind == 'overflow': plan.blocks[0].offset = 0xFFFFFFE0
                elif kind == 'size': plan.blocks[0].size = 0
                elif kind == 'trailing': plan.blocks[255].size = 1
                elif kind == 'bank_crossing': plan.blocks[0].offset = 0xFF0000 - 32
                elif kind == 'raw_header': C.memmove(self.lib.poolPointer(0x8000), struct.pack('>I', 1), 4)
                elif kind == 'packed_header': C.memmove(self.lib.poolPointer(0x8000) + 4, bytes(4), 4)
                plan.seal()
                if kind == 'crc': plan.checksum ^= 1
                C.memmove(self.lib.staging(), bytes(plan), C.sizeof(plan))
                self.send()
                self.assertEqual(self.finish(), 9)
                self.assertEqual(self.lib.writes(), 0)
                self.assertIsNone(self.file())

    def test_mid_export_resealed_plan_cannot_change_the_accepted_ranges(self):
        self.activate()
        _, _, plan = self.prepare()
        self.send()
        while self.lib.writes() < 20000:
            self.assertGreater(self.lib.pump(1), 0)
        plan.blocks[0].offset = 0xFF0000
        plan.seal()
        C.memmove(self.lib.staging(), bytes(plan), C.sizeof(plan))
        self.assertEqual(self.finish(), 9)
        self.assertIsNone(self.file())

    def test_cancellation_closes_export_before_terminal_receipt(self):
        self.activate()
        self.prepare()
        self.send()
        while self.lib.writes() < 20000:
            self.assertGreater(self.lib.pump(1), 0)
        line = self.wire().request
        line.phase = 6
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.assertEqual(self.finish(), state.CANCELLED)
        self.assertIsNone(self.file())
        self.assertEqual(self.lib.workerPhase(), 0)

    def test_legacy_mode_cannot_interpret_a_plan(self):
        self.prepare(entries=[(0x8000, struct.pack('>II', 16, 0x80000010) + bytes(16))])
        self.assertGreaterEqual(self.lib.run(100), 0)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox() + 44).value, 9)
        self.assertEqual(self.lib.writes(), 0)
        self.assertIsNone(self.file())

    def test_full_256_reference_plan_keeps_archive_format(self):
        from mod_transport import encode_quick, decode_quick
        raw = bytes([71]) * 0x20000
        block = encode_quick(raw)[8:]
        self.activate()
        packed, meta, _ = self.prepare(entries=[(0x8000, block)] * 256)
        self.send()
        self.assertEqual(self.finish(), state.OK)
        self.assertEqual(self.file()[96 + len(meta):], packed)
        self.assertEqual(decode_quick(packed, 0x2000000), raw * 256)

    def test_opaque_deflate_exports_unchanged_across_all_banks(self):
        raw = bytes(range(256)) * 2200
        packed = zlib.compress(raw, level=0)
        addresses = (0x8000, 0xFF0000, 0x11F0000, 0x12B2000, 0xA0000)
        entries = [(address, packed[i * 0x20000:(i + 1) * 0x20000])
                   for i, address in enumerate(addresses)]
        self.activate()
        expected, meta, plan = self.prepare(entries, kind=1, raw_size=len(raw))
        self.send()
        self.assertEqual(self.finish(), state.OK)
        exported = self.file()[96 + len(meta):]
        self.assertEqual(exported, expected)
        self.assertEqual(exported, packed)
        self.assertEqual(zlib.decompress(exported), raw)
        self.assertEqual(C.string_at(self.lib.staging(), C.sizeof(plan)), bytes(plan))

    def test_opaque_zlib_prefix_can_cross_one_byte_ranges(self):
        raw = b'unchanged old snapshot' * 400
        packed = zlib.compress(raw)
        self.activate()
        _, meta, _ = self.prepare([(0x8000, packed[:1]), (0xFF0000, packed[1:2]),
                                  (0x12B2000, packed[2:])], kind=1, raw_size=len(raw))
        self.send()
        self.assertEqual(self.finish(), state.OK)
        self.assertEqual(self.file()[96 + len(meta):], packed)

    def test_opaque_rejects_wrong_framing_and_oversized_ranges_before_writes(self):
        raw = b'previous state' * 500
        packed = zlib.compress(raw)
        for kind in ('quick_as_deflate', 'deflate_as_quick', 'bad_check', 'dictionary',
                     'bad_method', 'large_window', 'truncated_prefix', 'oversized'):
            with self.subTest(kind=kind):
                self.setUp()
                self.activate()
                block = packed
                codec = 1
                if kind == 'quick_as_deflate': block = FRAME + packed
                elif kind == 'deflate_as_quick': codec = 0
                elif kind == 'bad_check': block = bytes([packed[0], packed[1] ^ 1]) + packed[2:]
                elif kind in ('dictionary', 'bad_method', 'large_window'):
                    cmf = 0x78 if kind == 'dictionary' else 0x77 if kind == 'bad_method' else 0x88
                    flg = 0x20 if kind == 'dictionary' else 0
                    flg += (-(cmf * 256 + flg)) % 31
                    block = bytes([cmf, flg]) + packed[2:]
                elif kind == 'truncated_prefix': block = packed[:1]
                elif kind == 'oversized': block = packed + bytes(0x20001 - len(packed))
                self.prepare([(0x8000, block)], kind=codec, raw_size=len(raw))
                self.send()
                self.assertEqual(self.finish(), 9)
                self.assertEqual(self.lib.writes(), 0)
                self.assertIsNone(self.file())


if __name__ == '__main__':
    unittest.main()
