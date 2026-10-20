"""Real ARM worker/coordinator fixed-tail windows, with full live-range canaries."""
import ctypes as C
import unittest
import zlib

import test_state_storage_kernel as state
from test_transfer_coordinator import CoordinatorChecks, bridge

TAIL = 0x80000000
CAPACITY = 0x4E000
PREFIX = 0x2F0000


class TailWindowTests(unittest.TestCase):
    fixture_transform = CoordinatorChecks.fixture_transform
    bridge_source = bridge('state') + r'''
__declspec(dllexport) const void *ghostBytes(void){return testPayload;}
__declspec(dllexport) u32 ghostSize(void){return sizeof(testPayload);}
'''
    setUpClass = classmethod(state.StateStorageKernelTests.setUpClass.__func__)
    setup_coordinator = CoordinatorChecks.setup_coordinator
    wire = CoordinatorChecks.wire
    activate = CoordinatorChecks.activate
    remote = CoordinatorChecks.remote
    buffer = state.StateStorageKernelTests.buffer
    file = state.StateStorageKernelTests.file

    def setUp(self):
        self.setup_coordinator()
        self.lib.ghostBytes.restype = C.c_void_p

    def archive(self):
        self.data=(bytes(range(251))*3000)[:CAPACITY*2+31]
        meta=b'bounded tail import metadata'
        self.lib.prepare(self.buffer(self.data),len(self.data),0,self.buffer(meta),len(meta))
        self.lib.submit(state.EXPORT,0,0,len(self.data),0,11)
        if self.lib.active():self.remote(2,1,state.EXPORT,11)
        (self.lib.pump if self.lib.active() else self.lib.run)(1000)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,state.OK)
        self.header=state.Header.from_buffer_copy(self.file())
        self.lib.clearIo()

    def snapshot(self):
        ranges=((self.lib.staging(),PREFIX),
                (self.lib.pool(),self.lib.poolSize()),
                (self.lib.extra(),self.lib.expandedSize()-self.lib.poolSize()),
                (self.lib.staging()+self.lib.stageBytes(),self.lib.stagingSize()-self.lib.stageBytes()),
                (self.lib.ghostBytes(),self.lib.ghostSize()))
        return tuple(zlib.crc32(C.string_at(p,n)) for p,n in ranges)

    def request(self,offset,size,command=state.WINDOW,owner=2,phase=5):
        self.lib.submit(command,1,offset,len(self.data),self.header.headerCrc,11)
        self.lib.windowSize(size)
        seq=C.c_uint.from_address(self.lib.mailbox()).value
        if self.lib.active():self.remote(owner,seq,command,11,phase=phase)

    def status(self):
        return C.c_uint.from_address(self.lib.mailbox()+44).value

    def test_exact_tail_output_preserves_candidate_all_banks_and_ghost(self):
        self.activate();self.archive()
        before=self.snapshot()
        for offset,size in ((0,1),(17,16385),(CAPACITY,CAPACITY),(len(self.data)-31,31)):
            with self.subTest(offset=offset,size=size):
                C.memset(self.lib.staging()+PREFIX,0xE7,CAPACITY)
                self.request(offset,TAIL|size);self.lib.pump(1000)
                self.assertEqual(self.status(),state.OK)
                self.assertEqual(self.wire().response.phase,7)
                self.assertEqual(C.string_at(self.lib.staging()+PREFIX,CAPACITY),
                                 self.data[offset:offset+size]+b'\xE7'*(CAPACITY-size))
                receipt=(C.c_uint*8).from_address(self.lib.mailbox()+7968)
                self.assertEqual(tuple(receipt[:3]),(offset,size,zlib.crc32(self.data[offset:offset+size])))
                self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+52).value,size)
                self.assertEqual(self.snapshot(),before)
                self.assertTrue(self.lib.guards())

    def test_bad_flags_sizes_offsets_and_wrong_commands_never_access_payload(self):
        for encoded,offset,command in ((TAIL,0,state.WINDOW),(TAIL|CAPACITY+1,0,state.WINDOW),
                (TAIL|0x40000000|1,0,state.WINDOW),(TAIL|32,0xffffffff,state.WINDOW),
                (TAIL|32,0,state.IMPORT),(TAIL|32,0,state.EXPORT)):
            with self.subTest(encoded=encoded,offset=offset,command=command):
                self.setUp();self.activate();self.archive();before=self.snapshot()
                tail=C.string_at(self.lib.staging()+PREFIX,CAPACITY)
                self.request(offset,encoded,command);self.lib.pump(1000)
                self.assertEqual(self.status(),9)
                self.assertEqual((self.lib.reads(),self.lib.writes()),(0,0))
                self.assertEqual(self.snapshot(),before)
                self.assertEqual(C.string_at(self.lib.staging()+PREFIX,CAPACITY),tail)

    def test_legacy_rejects_tail_marker_but_keeps_ordinary_window_behavior(self):
        self.archive();before=C.string_at(self.lib.staging(),self.lib.stagingSize())
        self.request(11,TAIL|32);self.lib.run(1000)
        self.assertEqual(self.status(),9)
        self.assertEqual((self.lib.reads(),self.lib.writes()),(0,0))
        self.assertEqual(C.string_at(self.lib.staging(),self.lib.stagingSize()),before)
        self.request(11,32);self.lib.run(1000)
        self.assertEqual(self.status(),state.OK)
        self.assertEqual(C.string_at(self.lib.staging(),32),self.data[11:43])

    def test_wrong_owner_and_cancellation_cannot_write_candidate_or_pool(self):
        self.activate();self.archive();before=self.snapshot()
        tail=C.string_at(self.lib.staging()+PREFIX,CAPACITY)
        self.request(0,TAIL|CAPACITY,owner=1)
        self.lib.pump(10)
        self.assertEqual((self.lib.reads(),self.lib.writes()),(0,0))
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(C.string_at(self.lib.staging()+PREFIX,CAPACITY),tail)
        self.setUp();self.activate();self.archive();before=self.snapshot()
        self.request(0,TAIL|CAPACITY)
        for _ in range(100):
            self.lib.pump(1)
            if self.lib.workerPhase()==5:break
        else:self.fail('Tail request did not reach payload phase')
        line=self.wire().request;line.phase=6
        self.assertTrue(self.lib.publish(C.byref(line)));self.lib.pump(1000)
        self.assertEqual(self.status(),state.CANCELLED)
        self.assertEqual(self.wire().response.phase,7)
        self.assertEqual(self.snapshot(),before)

    def test_changed_size_after_acceptance_and_read_failure_keep_other_ranges_intact(self):
        for mutate in (False,True):
            with self.subTest(mutate=mutate):
                self.setUp();self.activate();self.archive();before=self.snapshot()
                self.request(0,TAIL|CAPACITY)
                for _ in range(100):
                    self.lib.pump(1)
                    if self.lib.workerPhase()==5:break
                else:self.fail('No payload phase')
                if mutate:self.lib.windowSize(TAIL|CAPACITY-1)
                else:self.lib.readFailure(0)
                self.lib.pump(1000)
                self.assertEqual(self.status(),state.CANCELLED if mutate else state.IO)
                self.assertEqual(self.snapshot(),before)
                self.assertEqual(self.wire().response.phase,7)


if __name__=='__main__':unittest.main()
