"""Native ARM worker -> borrowed tail -> production import/store -> ARM export.

Both libraries share the same five bank buffers and candidate prefix. The host
drives the mailbox protocol; this does not emulate PPC cache coherency, validate
game snapshot metadata, or prove Wii timing/endian behavior.
"""
import ctypes as C
from pathlib import Path
import random
import struct
import unittest
import zlib

import test_state_storage_kernel as state
from test_state_codec import Guarded
from test_state_export_plan import Plan, FRAME, MAGIC
from test_state_import import Cursor, MORE, COMPLETE, INVALID, FULL
from test_state_store import StoreCodec, StorePool, Identity, identity
from test_timewarp_chunk_pool import Memory, Directory
from test_timewarp_staged_transaction import StageMemory
from test_transfer_coordinator import CoordinatorChecks, bridge, fixture

ROOT = Path(__file__).resolve().parents[1]
PREFIX, TAIL_BYTES, TAIL = 0xF0000, 0x4E000, 0x80000000
BANK_SIZES = (0xFF0000, 0x200000, 0x2C2000, 0x13E000, 0x70000)
BANK_STARTS = (0, 0xFF0000, 0x11F0000, 0x14B2000, 0x15F0000)


def raw_quick(raw):
    return FRAME + b''.join(struct.pack('>II', len(p), 0x80000000 | len(p)) + p
        for p in (raw[i:i + 0x20000] for i in range(0, len(raw), 0x20000)))


def pipeline_fixture(text):
    text = text.replace('#define FIXTURE_WRITES 16', '#define FIXTURE_WRITES 4')
    text = text.replace('#define FIXTURE_FILE_BYTES 6000000', '#define FIXTURE_FILE_BYTES 8000000')
    text = text.replace('static u8 testPayload[', 'static __attribute__((aligned(32))) u8 testPayload[')
    text = text.replace('static int f_close(FIL *f) { (void)f; return FR_OK; }',
                        'static u32 closedFiles;\nstatic int f_close(FIL *f) { (void)f; ++closedFiles; return FR_OK; }')
    return fixture(text)


IMPORT_BRIDGE = '#include "' + (ROOT / 'src/state_import.cpp').as_posix() + '"\n' + r'''
extern "C" {
__declspec(dllexport) int ib(StateStore::Store*s,StateImport::Cursor*c,unsigned n){return StateImport::begin(*s,*c,n);}
__declspec(dllexport) int ia(StateStore::Store*s,StateImport::Cursor*c,const void*p,unsigned n){return StateImport::append(*s,*c,p,n);}
__declspec(dllexport) unsigned sealed(StateStore::Store*s){return s->sealed;}
__declspec(dllexport) int capacityRefused(StateStore::Store*s){return StateStore::capacityRefused(*s);}
}
'''


class BoundPool:
    def __init__(self, worker):
        self.worker = worker
        addresses = [worker.poolPointer(offset) for offset in BANK_STARTS]
        assert all(p and p % 32 == 0 for p in addresses)
        self.memory = Memory((C.c_void_p * 5)(*addresses), (C.c_uint * 5)(*BANK_SIZES), 5)
        self.stage_memory = StageMemory(C.pointer(self.memory), worker.staging(), PREFIX)
        self.directory = Directory.from_address(addresses[0])

    def canaries(self):
        assert self.worker.guards()


class BoundStore(StorePool):
    def __init__(self, worker, codec):
        self.pool, self.codec = BoundPool(worker), codec
        C.memset(self.pool.memory.banks[0], 0, 0x8000)
        self.storage, self.table = Guarded(codec.lib.storeSize()), Guarded(codec.lib.rt())
        self.roots, self.identities = [None] * 3, [Identity() for _ in range(3)]
        assert codec.lib.si(self.storage.ptr, C.byref(self.pool.stage_memory), self.table.ptr, self.table.size)


class ImportPipelineTests(unittest.TestCase):
    fixture_transform = staticmethod(pipeline_fixture)
    bridge_source = bridge('state') + r'''
__declspec(dllexport) u32 pipelineOpen(void){return FileOpen;}
__declspec(dllexport) u32 pipelineCloses(void){return closedFiles;}
__declspec(dllexport) u32 pipelineMetadataOffset(void){return __builtin_offsetof(struct SusamuneStateStorageMailbox,metadata);}
'''
    setup_coordinator = CoordinatorChecks.setup_coordinator
    wire = CoordinatorChecks.wire
    activate = CoordinatorChecks.activate
    remote = CoordinatorChecks.remote
    buffer = state.StateStorageKernelTests.buffer
    file = state.StateStorageKernelTests.file

    @classmethod
    def setUpClass(cls):
        original = state.ADAPTER
        state.ADAPTER = original.replace('static u8 state', 'static __attribute__((aligned(32))) u8 state')
        try:
            state.StateStorageKernelTests.setUpClass.__func__(cls)
        finally:
            state.ADAPTER = original
        folder = Path(cls.temp.name) / 'codec'
        folder.mkdir()
        cls.codec = StoreCodec(folder, IMPORT_BRIDGE)
        cls.addClassCleanup(cls.codec.close)
        cls.codec.lib.ib.argtypes = [C.c_void_p, C.POINTER(Cursor), C.c_uint]
        cls.codec.lib.ia.argtypes = [C.c_void_p, C.POINTER(Cursor), C.c_void_p, C.c_uint]
        cls.codec.lib.sch.restype = C.c_uint
        cls.codec.lib.sealed.argtypes = [C.c_void_p]
        cls.codec.lib.capacityRefused.argtypes = [C.c_void_p]
        cls.lib.poolPointer.argtypes = [C.c_uint]
        cls.lib.poolPointer.restype = C.c_void_p

    def setUp(self):
        self.setup_coordinator()
        self.activate()
        self.store = BoundStore(self.lib, self.codec)
        self.tail = self.lib.staging() + PREFIX
        self.finished = True

    def seed(self, large=False):
        for slot in range(3):
            raw = random.Random(221 + slot).randbytes(0x740000 if large else 0x5011 + slot)
            kind = 0 if large else int(slot == 1)
            packed = zlib.compress(raw) if kind else raw_quick(raw)
            self.assertTrue(self.store.put(slot, raw, packed, 501 + slot, kind))
        self.old_identities = tuple(bytes(i) for i in self.store.identities)
        self.store.guards()

    def archive(self, raw, packed, kind=0):
        self.raw, self.packed, self.kind = raw, packed, kind
        self.meta = b'pipeline-owned snapshot metadata'
        self.header = state.Header(0x4D535341, 1, 96, len(self.meta), len(packed), len(raw),
            0x474D534A, 123, 15, 6789, zlib.crc32(self.meta), zlib.crc32(packed), 0, 0x10203)
        self.header.name = b'Pipeline source'
        self.header.headerCrc = zlib.crc32(bytes(self.header))
        self.archive_buffer = self.buffer(bytes(self.header) + self.meta + packed)
        self.assertGreaterEqual(self.lib.add(b'/Moonshine data/states/state_00000001.mss',
            self.archive_buffer, 96 + len(self.meta) + len(packed)), 0)
        self.info = identity(raw, packed, 9842, kind)

    def begin(self, slot=1):
        self.slot = slot
        self.assertTrue(self.finished)
        self.assertTrue(self.store.begin(slot))
        self.cursor = Cursor()
        self.assertTrue(self.store.call('ib', C.byref(self.cursor), len(self.packed)))

    def live_digest(self):
        ranges = [(self.store.pool.memory.banks[i], size) for i, size in enumerate(BANK_SIZES)]
        ranges.append((self.lib.staging(), PREFIX))
        return tuple(zlib.crc32(C.string_at(p, size)) for p, size in ranges)

    def submit(self, command, file_id, offset, size, crc, reserved):
        self.assertTrue(self.finished)
        self.lib.submit(command, file_id, offset, size, crc, 11)
        self.lib.windowSize(reserved)
        self.seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.remote(2, self.seq, command, 11)
        self.request = self.wire().request
        self.command, self.file_id, self.finished = command, file_id, False
        self.close_count = self.lib.pipelineCloses()

    def submit_window(self):
        self.window_offset = self.cursor.offset
        self.window_size = min(TAIL_BYTES, len(self.packed) - self.cursor.offset)
        self.before_worker = self.live_digest()
        self.submit(state.WINDOW, 1, self.window_offset, len(self.packed), self.header.headerCrc,
                    TAIL | self.window_size)

    def terminal(self, status=state.OK):
        self.lib.pump(10000)
        m = self.lib.mailbox()
        self.assertEqual(C.c_uint.from_address(m + 40).value, self.seq)
        self.assertEqual(C.c_uint.from_address(m + 44).value, status)
        done = self.wire().response
        self.assertEqual(done.phase, 7)
        for field in ('epoch', 'ticket', 'owner', 'seq', 'session', 'command'):
            self.assertEqual(getattr(done, field), getattr(self.request, field))
        receipt = (C.c_uint * 8).from_address(m + 64)
        self.assertEqual(tuple(receipt[:4]), (11, self.command, self.file_id, self.seq))
        self.assertEqual(self.lib.workerPhase(), 0)
        self.assertFalse(self.lib.pipelineOpen())
        self.assertGreater(self.lib.pipelineCloses(), self.close_count)
        self.assertTrue(self.lib.guards())
        self.finished = True

    def window_valid(self):
        self.assertTrue(self.finished)
        r = (C.c_uint * 8).from_address(self.lib.mailbox() + 7968)
        return (tuple(r[:2]) == (self.window_offset, self.window_size)
                and not any(r[3:]) and r[2] == zlib.crc32(C.string_at(self.tail, self.window_size)))

    def append_window(self):
        self.assertTrue(self.window_valid())
        self.assertEqual(self.live_digest(), self.before_worker)
        m = self.lib.mailbox()
        receipt = (C.c_uint * 8).from_address(m + 64)
        self.assertEqual(tuple(receipt[4:7]), (len(self.meta), len(self.packed), self.header.headerCrc))
        self.assertEqual(C.string_at(m + 96, 96), bytes(self.header))
        self.assertEqual(C.string_at(m + self.lib.pipelineMetadataOffset(), len(self.meta)), self.meta)
        result = self.store.call('ia', C.byref(self.cursor), self.tail, self.window_size)
        C.memset(self.tail, 0xE7, TAIL_BYTES)
        return result

    def read_append(self):
        self.submit_window()
        self.terminal()
        return self.append_window()

    def import_all(self):
        reread = False
        while self.cursor.offset < len(self.packed):
            previous = self.cursor.offset
            result = self.read_append()
            self.assertIn(result, (MORE, COMPLETE))
            self.assertGreater(self.cursor.offset, previous)
            reread |= self.cursor.offset - previous < self.window_size
        self.assertEqual(result, COMPLETE)
        return reread

    def abort_preserving_roots(self):
        self.assertTrue(self.finished, 'Do not abort or reuse while the worker owns a tail window')
        self.assertTrue(self.store.call('sa'))
        self.assertEqual(tuple(bytes(i) for i in self.store.identities), self.old_identities)
        for slot in range(3):
            self.store.decode(slot, protected=True)
        self.assertTrue(self.store.begin(self.slot))
        self.assertTrue(self.store.call('sa'))

    def commit_export(self, all_banks=False):
        self.assertTrue(self.finished)
        self.assertEqual(self.cursor.kind, self.kind)
        self.assertEqual(self.store.call('sch'), self.info.checksum)
        self.assertTrue(self.store.seal(self.info))
        self.assertFalse(self.store.call('capacityRefused'))
        self.store.commit(self.slot, self.raw, self.packed, self.info)
        self.assertFalse(self.store.call('capacityRefused'))
        for slot in range(3):
            self.store.decode(slot, protected=True)
        seq, _ = self.store.borrowed(self.slot)
        self.assertTrue(self.store.call('se', seq, C.byref(self.info), self.header.metadataCrc, self.lib.staging()))
        plan = Plan.from_buffer_copy(C.string_at(self.lib.staging(), C.sizeof(Plan)))
        self.assertEqual((plan.magic, plan.kind, plan.packed), (MAGIC, self.kind, len(self.packed)))
        if all_banks:
            seen = {max(i for i, start in enumerate(BANK_STARTS) if block.offset >= start)
                    for block in plan.blocks[:plan.count]}
            self.assertEqual(seen, {0, 1, 2, 3, 4})
        C.memmove(self.lib.mailbox() + 96, bytes(self.header), 96)
        C.memmove(self.lib.mailbox() + self.lib.pipelineMetadataOffset(), self.meta, len(self.meta))
        self.submit(state.EXPORT, 0, 0, len(self.packed), 0, MAGIC)
        self.assertFalse(self.store.begin(0))
        self.terminal()
        exported_id = C.c_uint.from_address(self.lib.mailbox() + 48).value
        self.assertNotEqual(exported_id, 1)
        self.assertEqual(self.file(exported_id), bytes(self.header) + self.meta + self.packed)
        self.assertEqual(C.string_at(self.lib.staging(), C.sizeof(plan)), bytes(plan))
        self.assertTrue(self.store.call('sk', seq, C.byref(self.info)))
        self.assertTrue(self.store.call('su', seq))
        self.store.guards()

    def test_quick_roundtrip_shares_live_five_bank_pool(self):
        self.seed(large=True)
        raw = random.Random(691).randbytes(0xA0000) + self.store.roots[2][0][0xA0000:]
        self.archive(raw, raw_quick(raw))
        self.begin(2)
        self.assertTrue(self.import_all())
        self.commit_export(all_banks=True)

    def test_legacy_deflate_roundtrip_keeps_exact_stream(self):
        self.seed()
        raw = random.Random(871).randbytes(0x110021)
        self.archive(raw, zlib.compress(raw), kind=1)
        self.begin()
        self.assertFalse(self.import_all())
        self.commit_export()

    def second_window(self):
        self.seed()
        raw = random.Random(988).randbytes(0xC0031)
        self.archive(raw, raw_quick(raw))
        self.begin()
        self.assertEqual(self.read_append(), MORE)

    def test_malformed_second_window_preserves_three_old_roots(self):
        self.second_window()
        C.memmove(C.addressof(self.archive_buffer) + 96 + len(self.meta) + self.cursor.offset + 4,
                  struct.pack('>I', 0x80020001), 4)
        self.assertEqual(self.read_append(), INVALID)
        self.assertFalse(self.store.seal(self.info))
        self.assertFalse(self.store.call('capacityRefused'))
        self.abort_preserving_roots()

    def test_stale_archive_and_stale_window_receipt_are_not_consumed(self):
        for stale_header in (True, False):
            with self.subTest(stale_header=stale_header):
                self.setUp()
                self.second_window()
                old_offset = self.cursor.offset
                if stale_header:
                    header = state.Header.from_buffer(self.archive_buffer)
                    header.sceneKey ^= 1
                    header.headerCrc = 0
                    header.headerCrc = zlib.crc32(bytes(header))
                self.submit_window()
                self.terminal(state.STALE if stale_header else state.OK)
                if not stale_header:
                    C.c_uint.from_address(self.lib.mailbox() + 7968).value = 0
                    self.assertFalse(self.window_valid())
                self.assertEqual(self.cursor.offset, old_offset)
                self.assertEqual(self.live_digest(), self.before_worker)
                self.abort_preserving_roots()

    def test_window_crc_and_whole_archive_crc_fail_before_commit(self):
        for tail_corruption in (True, False):
            with self.subTest(tail_corruption=tail_corruption):
                self.setUp()
                self.second_window()
                if tail_corruption:
                    self.submit_window()
                    self.terminal()
                    C.c_ubyte.from_address(self.tail + 16).value ^= 1
                    self.assertFalse(self.window_valid())
                else:
                    C.c_ubyte.from_address(C.addressof(self.archive_buffer) + 96 + len(self.meta)
                                          + self.cursor.offset + 16).value ^= 1
                    self.import_all()
                    self.assertNotEqual(self.store.call('sch'), self.info.checksum)
                    self.assertFalse(self.store.seal(self.info))
                    self.assertFalse(self.store.call('sc', C.byref(self.info)))
                self.abort_preserving_roots()

    def test_cancel_and_io_failure_close_before_abort_and_reuse(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                self.setUp()
                self.second_window()
                self.submit_window()
                for _ in range(100):
                    self.lib.pump(1)
                    if self.lib.workerPhase() == 5:
                        break
                else:
                    self.fail('Second window did not reach the payload phase')
                self.assertTrue(self.lib.pipelineOpen())
                self.assertFalse(self.finished)
                self.assertNotEqual(C.c_uint.from_address(self.lib.mailbox() + 40).value, self.seq)
                self.lib.pump(1)
                if cancel:
                    line = self.wire().request
                    line.phase = 6
                    self.assertTrue(self.lib.publish(C.byref(line)))
                else:
                    self.lib.readFailure(0)
                self.terminal(state.CANCELLED if cancel else state.IO)
                self.assertEqual(self.live_digest(), self.before_worker)
                self.abort_preserving_roots()
                self.lib.readFailure(0xFFFFFFFF)
                self.begin()
                self.import_all()
                self.commit_export()

    def test_full_candidate_preserves_all_three_five_bank_roots(self):
        self.seed(large=True)
        raw = random.Random(156).randbytes(0x600000)
        self.archive(raw, raw_quick(raw))
        self.begin()
        while self.cursor.offset < len(self.packed):
            result = self.read_append()
            if result == FULL:
                break
            self.assertEqual(result, MORE)
        else:
            self.fail('Expected a real full-pool refusal with old roots retained')
        self.assertGreater(self.cursor.offset, TAIL_BYTES)
        self.assertFalse(self.store.seal(self.info))
        self.abort_preserving_roots()

    def test_sealed_candidate_final_capacity_refusal_preserves_old_roots(self):
        self.seed(large=True)
        raw = self.store.roots[2][0] + random.Random(417).randbytes(0x60000)
        self.archive(raw, raw_quick(raw))
        self.begin(2)
        self.import_all()
        self.assertTrue(self.store.seal(self.info))
        self.assertTrue(self.store.call('sealed'))
        self.assertTrue(self.store.call('sv'))
        self.assertFalse(self.store.call('sc', C.byref(self.info)))
        self.assertTrue(self.store.call('capacityRefused'))
        self.abort_preserving_roots()
        self.assertFalse(self.store.call('capacityRefused'))

    def test_retained_payload_corruption_can_refuse_a_structurally_valid_sealed_commit(self):
        self.second_window()
        chunk_id = self.store.pool.directory.slots[0].ids[0] - 1
        chunk = self.store.pool.directory.chunks[chunk_id]
        changed = self.lib.poolPointer(chunk.offset) + 16
        C.c_ubyte.from_address(changed).value ^= 1
        self.import_all()
        self.assertTrue(self.store.seal(self.info))
        self.assertTrue(self.store.call('sealed'))
        self.assertTrue(self.store.call('sv'))
        self.assertFalse(self.store.call('sc', C.byref(self.info)))
        self.assertFalse(self.store.call('capacityRefused'))
        # Undo the injected hardware-fault analogue before checking preservation.
        C.c_ubyte.from_address(changed).value ^= 1
        self.abort_preserving_roots()


if __name__ == '__main__':
    unittest.main()
