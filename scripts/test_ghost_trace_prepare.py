"""Exercise the production optional warm writer and unchanged START/FENCE paths."""
import ctypes as C
import struct
import unittest

import test_ghost_trace_storage as writer

NONCE = 0x12345678
RUN = 0x80000001
CAPS = 0x4ff
EXTRA = r'''
__declspec(dllexport) void warmRequest(unsigned op,unsigned run,unsigned caps,unsigned target){
 struct MsTracePrepareRequest*q=&prepareMailbox.request;
 q->magic=MS_TRACE_PREPARE_MAGIC;q->version=MS_TRACE_PREPARE_VERSION;q->bootNonce=traceMailbox.response.nonce;
 ++q->sequence;q->operation=op;q->run=run;q->capabilities=caps;q->target=target;
}
__declspec(dllexport) const void*warmResponse(void){return &prepareMailbox.response;}
__declspec(dllexport) void warmPermit(unsigned flags,unsigned queued){
 struct MsTracePreparePermit*p=&prepareMailbox.permit;p->magic=MS_TRACE_PREPARE_MAGIC;p->version=MS_TRACE_PREPARE_VERSION;
 p->bootNonce=traceMailbox.response.nonce;++p->sequence;p->flags=flags;p->queued=queued;p->reserved=0;
}
__declspec(dllexport) void warmBackground(unsigned count){for(unsigned i=0;i<count;++i)if(GhostTraceBackgroundPending())GhostTraceBackgroundService();}
__declspec(dllexport) unsigned warmState(unsigned field){switch(field){case 0:return WRITER->prepare.phase;case 1:return WRITER->prepare.active;case 2:return WRITER->prepare.created;case 3:return WRITER->prepare.file.index;case 4:return openCalls;case 5:return readCalls;case 6:return WRITER->prepare.headerHash;case 7:return WRITER->retained;default:return WRITER->active;}}
__declspec(dllexport) const void*warmFile(unsigned run,unsigned*n){char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.part",traceMailbox.response.nonce,run);int i=lookup(p);if(i<0){*n=0;return 0;}*n=testFiles[i].size;return testFiles[i].bytes;}
__declspec(dllexport) void warmMutate(unsigned offset,unsigned value){struct TestFile*f=&testFiles[WRITER->prepare.file.index];((u8*)f->bytes)[offset]=(u8)value;}
__declspec(dllexport) void warmSize(unsigned bytes){testFiles[WRITER->prepare.file.index].size=bytes;}
__declspec(dllexport) void warmSyncFailure(unsigned value){failSync=value;}
__declspec(dllexport) void warmReaders(unsigned value){readerActive=value;}
__declspec(dllexport) unsigned warmCloseCalls(void){return prepareCloseCalls;}
__declspec(dllexport) void warmClock(unsigned value){clockTick=value;}
__declspec(dllexport) void warmCachePending(void){WRITER->references.valid=WRITER->references.failed=WRITER->references.active=0;}
__declspec(dllexport) unsigned warmCacheValid(void){return WRITER->references.valid;}
__declspec(dllexport) void warmCollision(unsigned run,unsigned complete){char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.%s",traceMailbox.response.nonce,run,complete?"msgt":"part");FIL f;UINT written;f_open_char(&f,p,FA_CREATE_NEW|FA_WRITE);f_write(&f,"preserved original",18,&written);}
__declspec(dllexport) const void*warmFence(void){return &traceFence;}
'''


class WarmWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous = writer.EXPORTS
        previous_adapter = writer.ADAPTER
        writer.ADAPTER = writer.ADAPTER.replace("static int f_close(FIL *f){return", "static unsigned prepareCloseCalls;\nstatic int f_close(FIL *f){++prepareCloseCalls;return")
        writer.EXPORTS += EXTRA
        try:
            writer.TraceWriterTests.setUpClass.__func__(cls)
        finally:
            writer.EXPORTS = previous
            writer.ADAPTER = previous_adapter
        cls.lib.warmRequest.argtypes = [C.c_uint] * 4
        cls.lib.warmResponse.restype = C.POINTER(C.c_uint)
        cls.lib.warmFile.argtypes = [C.c_uint, C.POINTER(C.c_uint)]
        cls.lib.warmFile.restype = C.c_void_p
        cls.lib.warmFence.restype = C.POINTER(C.c_uint)

    def setUp(self):
        self.lib.reset()
        self.lib.warmReaders(0)
        self.lib.warmSyncFailure(0)

    def response(self):
        return list(self.lib.warmResponse()[:8])

    def execute(self):
        self.lib.run(100)

    def request(self, op=2, run=RUN, caps=CAPS, target=0, execute=True):
        self.lib.warmRequest(op, run, caps, target)
        if execute:
            self.execute()

    def allow(self, count=12):
        self.lib.warmPermit(1, 0)
        self.lib.warmBackground(1)
        self.lib.warmPermit(1, 0)
        self.lib.warmBackground(count)

    def prepare(self, run=RUN):
        self.request(run=run)
        self.allow()
        self.assertEqual(self.response()[4:7], [6, 0, run])

    def start(self, run=RUN, scene=0x603):
        self.lib.submit(1, run, scene, NONCE)
        self.execute()

    def file(self, run=RUN):
        count=C.c_uint()
        pointer=self.lib.warmFile(run,C.byref(count))
        return C.string_at(pointer,count.value) if pointer else None

    def finish(self, data=b'checked native payload' * 100):
        self.lib.chunk(0, RUN, 1, data, len(data), 0)
        self.lib.submit(2, RUN, 1, NONCE)
        self.execute()
        self.assertEqual(self.lib.response()[4], 4)
        count=C.c_uint();pointer=self.lib.file(1,C.byref(count))
        return C.string_at(pointer,count.value)

    def test_ready_requires_write_first_header_and_sync_before_advertising(self):
        self.request()
        self.allow(4)
        self.assertEqual(self.response()[4], 5)
        self.assertEqual(len(self.file()), 64)
        self.lib.warmSyncFailure(1)
        self.lib.warmBackground(1)
        self.assertEqual(self.response()[4:6], [7, 2])
        self.assertEqual(self.lib.response()[4], 0)

    def test_warm_start_skips_directory_and_open_and_replaces_scene_hash(self):
        self.prepare()
        placeholder=self.file()
        opens=self.lib.warmState(4)
        self.start()
        self.assertEqual(self.lib.response()[4], 2)
        self.assertEqual(self.lib.warmState(4), opens)
        actual=self.file()
        self.assertEqual(struct.unpack_from('>I',actual,24)[0],0x603)
        self.assertEqual(actual[:24],placeholder[:24])
        self.assertNotEqual(actual[60:],placeholder[60:])
        self.assertEqual(self.response()[4],9)
        self.assertEqual(self.lib.warmState(1),0)
        self.lib.chunk(0,RUN,1,b'prefix',6,0)
        self.lib.run(16)
        self.lib.submit(4,RUN,1,NONCE);self.execute()
        self.assertEqual(self.lib.warmFence()[5],struct.unpack_from('>I',actual,60)[0])

    def test_warm_and_cold_complete_files_are_identical(self):
        self.prepare();self.start();warm=self.finish()
        self.setUp();self.start();cold=self.finish()
        self.assertEqual(warm,cold)

    def test_start_before_any_preparation_work_uses_normal_fallback(self):
        self.request(execute=False)
        self.start()
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(self.response()[4],9)
        self.assertEqual(len(self.file()),64)
        opens=self.lib.warmState(4);self.allow()
        self.assertEqual(self.lib.warmState(4),opens)

    def test_start_adopts_owned_zero_byte_file_without_second_create(self):
        self.request();self.allow(3)
        self.assertEqual((self.response()[4],self.file()),(4,b''))
        opens=self.lib.warmState(4)
        self.lib.warmPermit(0,0)
        self.start()
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(self.lib.warmState(4),opens)
        self.assertEqual(len(self.file()),64)

    def test_start_adopts_header_before_background_sync_without_waiting_for_grant(self):
        self.request();self.allow(4)
        self.assertEqual(self.response()[4],5)
        self.lib.warmPermit(0,0)
        self.start()
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(self.response()[4],9)

    def test_active_capture_is_untouched_by_prepare_and_failure(self):
        self.start(run=4)
        old=list(self.lib.response()[:8])
        self.request(run=RUN);self.allow(4)
        self.lib.warmSyncFailure(1);self.lib.warmBackground(1)
        self.assertEqual(self.response()[4],7)
        self.assertEqual(list(self.lib.response()[:8]),old)
        self.assertEqual(len(self.file(run=4)),64)

    def test_unexpected_size_or_header_is_preserved_and_refused(self):
        for mutation in ('size','header'):
            self.setUp();self.prepare()
            if mutation=='size':self.lib.warmSize(100)
            else:self.lib.warmMutate(20,0xfe)
            old=self.file()
            self.start()
            self.assertEqual(self.lib.response()[4],6)
            self.lib.submit(3,RUN,0,NONCE);self.execute()
            self.assertEqual(self.file(),old)

    def test_failed_header_promotion_never_discard_deletes_the_file(self):
        self.prepare();self.lib.failures(32,0,0);self.start()
        self.assertEqual(self.lib.response()[4],6)
        self.assertEqual(self.lib.warmState(7),1)
        damaged=self.file()
        self.lib.submit(3,RUN,0,NONCE);self.execute()
        self.assertEqual(self.file(),damaged)

    def test_caps_mismatch_refuses_without_touching_prepared_file(self):
        self.prepare();old=self.file()
        self.lib.submit(1,RUN,0x603,NONCE);self.lib.capabilities(CAPS^1);self.execute()
        self.assertEqual(self.lib.response()[4],6)
        self.assertEqual(self.file(),old)

    def test_existing_part_and_completed_source_are_never_overwritten(self):
        for complete in (0,1):
            self.setUp();self.lib.warmCollision(RUN,complete)
            self.request();self.allow()
            self.assertEqual(self.response()[4],7)
            self.assertEqual(self.lib.response()[4],0)
            if not complete:self.assertEqual(self.file(),b'preserved original')

    def test_cancel_burns_identity_and_failed_close_keeps_fil_owned(self):
        self.prepare();sequence=self.response()[3];old=self.file();index=self.lib.warmState(3)
        self.request(3,target=sequence,caps=0)
        self.lib.failures(0xffffffff,1,0);self.allow(2)
        self.assertEqual(self.lib.warmState(1),2)
        self.request(run=RUN+1)
        self.assertEqual(self.response()[4:6],[8,2])
        self.assertEqual(self.lib.warmState(3),index)
        self.assertEqual(self.file(),old)
        self.lib.failures(0xffffffff,0,0);self.request(3,target=sequence,caps=0);self.allow(1)
        self.assertEqual(self.lib.warmState(1),0)

    def test_cancel_ready_then_revoke_and_prepare_new_identity_closes_old_owner(self):
        self.prepare();old=self.file();sequence=self.response()[3]
        self.request(3,target=sequence,caps=0)
        self.lib.warmPermit(0,0)
        self.request(run=RUN+1)
        self.assertEqual(self.response()[4:7],[8,5,RUN])
        self.lib.warmBackground(1)
        self.assertEqual(self.lib.warmState(1),1)
        self.allow(1)
        self.assertEqual(self.response()[4:7],[8,0,RUN])
        self.request(run=RUN+1)
        self.assertEqual(self.response()[4:7],[1,0,RUN+1])
        self.allow()
        self.assertEqual(self.response()[4:7],[6,0,RUN+1])
        self.assertEqual(self.file(),old)

    def test_unrelated_start_does_not_close_an_old_dirty_canceled_slot(self):
        self.request();self.allow(4)
        sequence=self.response()[3];self.request(3,target=sequence,caps=0)
        self.lib.warmPermit(0,0)
        self.request(run=RUN+1,execute=False)
        before=self.lib.warmCloseCalls();self.start(run=20)
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(self.lib.warmCloseCalls(),before)
        self.assertEqual(self.lib.warmState(1),1)

    def test_dirty_cleanup_requires_the_same_fresh_offline_ready_grant(self):
        self.request();self.allow(4)
        sequence=self.response()[3];self.request(3,target=sequence,caps=0)
        self.lib.warmPermit(0,0);before=self.lib.warmCloseCalls()
        self.lib.warmBackground(30)
        self.assertEqual(self.lib.warmCloseCalls(),before)
        self.assertEqual(self.lib.warmState(1),1)
        self.allow(1)
        self.assertEqual(self.lib.warmState(1),0)

    def test_repeated_same_identity_rejects_changed_capabilities(self):
        self.prepare();old=self.file()
        self.request(run=RUN,caps=CAPS^1)
        self.assertEqual(self.response()[4:6],[7,1])
        self.assertEqual(self.file(),old)

    def test_every_inactive_preparation_phase_falls_back_without_collision(self):
        for steps in (0,1,2):
            self.setUp();self.request();self.allow(steps)
            self.lib.warmPermit(0,0);self.start()
            self.assertEqual(self.lib.response()[4],2,steps)
            self.assertEqual(len(self.file()),64)
            self.assertEqual(self.response()[4],9)

    def test_racing_readers_revoked_permit_and_queue_pressure_block_new_work(self):
        for reason in ('readers','revoked','queued','stale'):
            self.setUp();self.request()
            self.lib.warmPermit(1,0);self.lib.warmBackground(1)
            if reason=='readers':self.lib.warmReaders(1);self.lib.warmPermit(1,0)
            elif reason=='revoked':self.lib.warmPermit(0,0)
            elif reason=='queued':self.lib.warmPermit(1,0x40001)
            else:self.lib.warmClock(1898437)
            self.lib.warmBackground(12)
            self.assertEqual(self.response()[4],1,reason)
            self.assertIsNone(self.file())

    def test_fresh_preparation_takes_priority_over_pending_bloom_scan(self):
        self.request()
        self.lib.warmPermit(1,0);self.lib.warmBackground(1)
        self.lib.warmCachePending()
        self.lib.warmPermit(1,0);self.lib.warmBackground(1)
        self.assertEqual(self.response()[4],2)
        self.assertEqual(self.lib.warmCacheValid(),0)

    def test_response_header_remains_bit_identical_through_every_phase(self):
        header=[0x4d535450,3,NONCE]
        self.assertEqual(self.response()[:3],header)
        self.request();self.assertEqual(self.response()[:3],header)
        self.lib.warmPermit(1,0);self.lib.warmBackground(1)
        for _ in range(6):
            self.lib.warmPermit(1,0);self.lib.warmBackground(1)
            self.assertEqual(self.response()[:3],header)
        self.start();self.assertEqual(self.response()[:3],header)

    def test_hello_has_no_file_io_and_old_primary_start_needs_no_prepare(self):
        opens=self.lib.warmState(4)
        self.request(1,run=0,caps=0)
        self.assertEqual(self.response()[4:6],[0,0])
        self.assertEqual(self.lib.warmState(4),opens)
        self.start(run=7)
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(len(self.file(run=7)),64)

    def test_unrelated_manual_start_does_not_consume_ordinary_warm_slot(self):
        self.prepare();old=self.file();self.start(run=7)
        self.assertEqual(self.lib.response()[4],2)
        self.assertEqual(self.response()[4],6)
        self.assertEqual(self.file(),old)
        self.assertEqual(self.lib.warmState(1),1)


if __name__=='__main__':unittest.main()
