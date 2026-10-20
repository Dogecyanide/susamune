"""Production state client and lease client with adversarial ARM completions."""
import unittest
import test_state_storage_client as client


BRIDGE = r'''
#define CHECK(v) do{if(!(v))return __LINE__;}while(0)
#define EXPORT extern "C" __declspec(dllexport) int
static TWLeaseArm arm;
static void publishArm(){++testTransfer.responsePublication.issued;
 testTransfer.responsePublication.generation=testTransfer.responsePublication.issued;}
static int startShared(bool backend=true){
 reset(0);expanded=true;StateStorage::init();arm={};
 TWLeaseResetBegin(&arm,&testTransfer);
 CHECK(TWLeaseRetired(&arm,TW_OWNER_GHOST,1));CHECK(TWLeaseRetired(&arm,TW_OWNER_STATE,1));
 CHECK(TWLeaseResetPublish(&arm,&testTransfer));publishArm();
 TransferLease::sMode=TransferLease::UNINITIALIZED;StateStorage::init();
 CHECK(TransferLease::mode()==TransferLease::CAPABLE&&StateStorage::quiet());
 CHECK(TransferLease::activate(true,StateStorage::quiet(),true));
 CHECK(TWLeaseActivate(&arm,&testTransfer,1,1));testMailbox.response.available=backend;
 publishArm();StateStorage::update();CHECK(TransferLease::mode()==TransferLease::SHARED);
 CHECK(StateStorage::sSharedBackend&&StateStorage::available()==backend);
 CHECK(StateStorage::stagingSize()==SUSAMUNE_TRANSFER_STAGE_SIZE);
 CHECK(StatePoolMemoryCapacity(&StateStorage::sMemory)==SUSAMUNE_TRANSFER_POOL_SIZE);
 memset(testStaging,0xA5,sizeof(testStaging));return 0;
}
static int done(bool pump=true){
 const auto&r=testMailbox.request;
 CHECK(TWLeaseStart(&arm,&testTransfer,TW_OWNER_STATE,r.seq,r.session,r.command));
 TWLeaseToken key={arm.key.epoch,arm.key.ticket};
 CHECK(TWLeaseFinish(&arm,&testTransfer,key,1,1,1));publishArm();
 if(pump)StateStorage::update();return 0;
}
static bool ghostCanClaim(){TransferLease::Token t;
 if(!TransferLease::claim(TransferLease::GHOST,t))return false;
 return TransferLease::release(t);}
EXPORT claim_before_prepare(int which){
 CHECK(startShared()==0);prepareProject(0);
 TransferLease::Token ghost;CHECK(TransferLease::claim(TransferLease::GHOST,ghost));
 static SusamuneStateStorageMailbox before;before=testMailbox;int accepted=0;
 if(which==0)accepted=beginTape(12,2,0);
 else if(which==1)accepted=beginRename(7,999,"Name");
 else if(which==2)accepted=beginProject("Project");
 else if(which==3)accepted=beginProjectCommit(0);
 else accepted=beginExport(100,0);
 CHECK(!accepted&&!memcmp(&before,&testMailbox,sizeof(before))&&StateStorage::quiet());
 for(u32 i=0;i<sizeof(testStaging);++i)CHECK(testStaging[i]==0xA5);
 CHECK(TransferLease::release(ghost));CHECK(beginTape(12,2,0));
 CHECK(testTransfer.request.owner==TW_OWNER_STATE&&testTransfer.request.phase==TW_WIRE_ARM);
 for(u32 i=SUSAMUNE_TRANSFER_STAGE_SIZE;i<sizeof(testStaging);++i)CHECK(testStaging[i]==0xA5);
 return 0;
}
EXPORT two_receipts_and_deferred_reader(int reversed){
 CHECK(startShared()==0);CHECK(beginImport(100,0));StateStorage::Result r;
 if(reversed)CHECK(done()==0);else {acknowledge(3,0,0);tick();}
 CHECK(!StateStorage::takeResult(r)&&!StateStorage::quiet()&&!ghostCanClaim());
 if(reversed){acknowledge(3,0,0);tick();}else CHECK(done()==0);
 CHECK(!StateStorage::quiet()&&!StateStorage::busy());
 CHECK(StateStorage::takeResult(r));const u32 seq=testMailbox.request.seq;
 for(u32 i=0;i<650;++i){tick();CHECK(!StateStorage::quiet()&&!ghostCanClaim());}
 StateStorage::init();CHECK(testMailbox.request.seq==seq&&!beginTape(1,0,0));
 CHECK(StateStorage::consumeResult(r));CHECK(StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT streaming_owner_and_stale_result(){
 CHECK(startShared()==0);CHECK(beginImport(100,0));acknowledge(3,0,0);CHECK(done()==0);
 StateStorage::Result first,next;CHECK(StateStorage::takeResult(first));
 CHECK(StateStorage::consumeResult(first,true));CHECK(!StateStorage::quiet()&&!ghostCanClaim());
 CHECK(TransferLease::sPpc.phase==TW_PPC_LOCAL);const u32 ticket=TransferLease::sPpc.leaseTicket;
 CHECK(beginImport(200,0));CHECK(TransferLease::sPpc.leaseTicket==ticket);
 CHECK(testTransfer.request.ticket>ticket);acknowledge(3,0,0);CHECK(done()==0);
 CHECK(StateStorage::takeResult(next));CHECK(first.token.generation!=next.token.generation);
 CHECK(!StateStorage::consumeResult(first)&&!StateStorage::releaseOwner()&&!ghostCanClaim());
 CHECK(StateStorage::consumeResult(next,true));CHECK(!StateStorage::consumeResult(next));
 CHECK(StateStorage::releaseOwner()&&StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT cancel_and_abandon_keeps_original_command(int success){
 CHECK(startShared()==0);const u32 crc=prepareWindow(100);
 CHECK(beginWindow(100,0,100,crc));const auto original=testMailbox.request;
 StateStorage::abandon();CHECK(!memcmp(&original,&testMailbox.request,sizeof(original)));
 CHECK(testTransfer.request.phase==TW_WIRE_CANCEL&&!StateStorage::quiet()&&!ghostCanClaim());
 if(success)windowReceipt(0);else acknowledge(SUSAMUNE_STATE_CANCELLED,0,0);
 tick();CHECK(!StateStorage::quiet());CHECK(done()==0);
 StateStorage::Result r;CHECK(!StateStorage::takeResult(r));CHECK(StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT transient_consumption_and_failure(int failure){
 CHECK(startShared()==0);CHECK(beginImport(100,0));acknowledge(3,0,0);CHECK(done()==0);
 StateStorage::Result r;CHECK(StateStorage::takeResult(r));
 const u32 published=testTransfer.responsePublication.generation;
 if(failure)TransferLease::sPublisher.issued=0xffffffffu;
 else testTransfer.responsePublication.generation=0;
 CHECK(StateStorage::consumeResult(r));CHECK(!StateStorage::quiet()&&StateStorage::busy());
 CHECK(!StateStorage::consumeResult(r)&&!beginTape(1,0,0));
 tick();CHECK(!StateStorage::quiet());testTransfer.responsePublication.generation=published;tick();
 if(failure){CHECK(StateStorage::sTransferFailed&&!StateStorage::quiet());StateStorage::init();
  CHECK(StateStorage::stagingSize()==SUSAMUNE_TRANSFER_STAGE_SIZE&&!beginImport(100,0));}
 else CHECK(StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT result_and_request_generation_limits(int kind){
 CHECK(startShared()==0);
 if(kind)StateStorage::sResultGeneration=0xffffffffu;else StateStorage::sSequence=0xffffffffu;
 CHECK(beginImport(100,0));if(!kind)CHECK(testMailbox.request.seq==1);
 acknowledge(3,0,0);CHECK(done()==0);StateStorage::Result r;
 if(kind)CHECK(!StateStorage::takeResult(r)&&StateStorage::sTransferFailed&&!StateStorage::quiet());
 else {CHECK(StateStorage::takeResult(r));CHECK(StateStorage::consumeResult(r));
  const auto token=r.token;StateStorage::init();CHECK(beginImport(100,0));acknowledge(3,0,0);CHECK(done()==0);
  CHECK(StateStorage::takeResult(r));CHECK(!StateStorage::consumeResult(token));CHECK(StateStorage::consumeResult(r));}
 return 0;
}
EXPORT backend_and_reset_failure(int unavailable){
 CHECK(startShared(!unavailable)==0);
 if(unavailable){CHECK(!beginTape(1,0,0)&&StateStorage::quiet()&&ghostCanClaim());return 0;}
 CHECK(beginImport(100,0));TWLeaseResetBegin(&arm,&testTransfer);publishArm();tick();
 CHECK(StateStorage::sTransferFailed&&!StateStorage::quiet());StateStorage::init();
 CHECK(!beginTape(1,0,0)&&StateStorage::stagingSize()==SUSAMUNE_TRANSFER_STAGE_SIZE);return 0;
}
EXPORT all_four_banks_and_dynamic_stage(){
 CHECK(startShared()==0);const u32 offset=SUSAMUNE_STATE_POOL_EXPANDED_SIZE-16;
 CHECK(beginImport(SUSAMUNE_TRANSFER_STAGE_SIZE+SUSAMUNE_TRANSFER_RECLAIM_SIZE+16,offset));
 clearCacheLog();acknowledge(3,0,0);CHECK(done()==0);StateStorage::Result r;
 CHECK(StateStorage::takeResult(r));unsigned mask=0;
 for(u32 i=0;i<invalidateCount;++i){const auto&c=invalidated[i];
  if(c.address==testStaging&&c.size==SUSAMUNE_TRANSFER_STAGE_SIZE)mask|=1;
  if(c.address==testExtra+sizeof(testExtra)-16&&c.size==16)mask|=2;
  if(c.address==thirdBank&&c.size==sizeof(thirdBank))mask|=4;
  if(c.address==fourthBank&&c.size==sizeof(fourthBank))mask|=8;}
 CHECK(mask==15);CHECK(StateStorage::consumeResult(r)&&StateStorage::quiet());return 0;
}
EXPORT tail_window_api_bounds(int kind){
 reset(0);CHECK(!StateStorage::tailWindowBase()&&!StateStorage::tailWindowSize());
 CHECK(!StateStorage::startImportWindow(7,999,100,0,100));CHECK(testMailbox.request.seq==0);
 CHECK(startShared()==0);const u32 capacity=StateStorage::tailWindowSize();
 CHECK(capacity==0x4E000u&&StateStorage::tailWindowBase()==testStaging+0x2F0000u);
 const u32 size=kind==0?0:kind==1?capacity+1:kind==2?SUSAMUNE_STATE_WINDOW_TAIL|32:32;
 const u32 offset=kind==3?0xffffffffu:0;
 CHECK(!StateStorage::startImportWindow(7,999,100,offset,size));CHECK(StateStorage::quiet());
 TransferLease::Token ghost;CHECK(TransferLease::claim(TransferLease::GHOST,ghost));
 CHECK(!StateStorage::startImportWindow(7,999,100,0,100));CHECK(TransferLease::release(ghost));
 CHECK(testMailbox.request.seq==0);for(u32 i=0;i<sizeof(testStaging);++i)CHECK(testStaging[i]==0xA5);
 return 0;
}
EXPORT tail_window_cache_and_borrow(int corrupt){
 CHECK(startShared()==0);const u32 size=StateStorage::tailWindowSize(),prefix=0x2F0000u;
 const u32 crc=prepareWindow(size*2);clearCacheLog();
 CHECK(StateStorage::startImportWindow(7,crc,size*2,size,size));
 CHECK(testMailbox.request.reserved==(SUSAMUNE_STATE_WINDOW_TAIL|size));
 bool flush=false;for(u32 i=0;i<flushCount;++i){const auto&c=flushed[i];
  if(c.address==testStaging+prefix&&c.size==size)flush=true;CHECK(c.address!=testStaging);}
 CHECK(flush);clearCacheLog();windowReceipt(corrupt);tick();
 StateStorage::Result result;CHECK(!StateStorage::takeResult(result)&&!ghostCanClaim());
 CHECK(done()==0);CHECK(StateStorage::takeResult(result));CHECK(result.status==(corrupt?3u:0u));
 bool invalidatedTail=false;for(u32 i=0;i<invalidateCount;++i){const auto&c=invalidated[i];
  if(c.address==testStaging+prefix&&c.size==size)invalidatedTail=true;CHECK(c.address!=testStaging);}
 CHECK(invalidatedTail);CHECK(!StateStorage::quiet()&&!ghostCanClaim());
 CHECK(StateStorage::consumeResult(result,true));CHECK(!ghostCanClaim());
 CHECK(StateStorage::startImportWindow(7,crc,size*2,0,32));
 const auto request=testMailbox.request;CHECK(StateStorage::cancel());
 CHECK(!memcmp(&request,&testMailbox.request,sizeof(request))&&!StateStorage::quiet());
 windowReceipt(0);CHECK(done()==0);CHECK(StateStorage::takeResult(result));
 CHECK(StateStorage::consumeResult(result)&&StateStorage::quiet());
 for(u32 i=0;i<prefix;++i)CHECK(testStaging[i]==0xA5);return 0;
}
EXPORT tail_window_stale_receipt_and_cancel(){
 CHECK(startShared()==0);const u32 crc=prepareWindow(100);
 CHECK(StateStorage::startImportWindow(7,crc,100,0,100));clearCacheLog();
 acknowledge(SUSAMUNE_STATE_CANCELLED,1,0);CHECK(done()==0);StateStorage::Result result;
 CHECK(!StateStorage::takeResult(result)&&!StateStorage::quiet()&&!ghostCanClaim());
 for(u32 i=0;i<invalidateCount;++i)CHECK(invalidated[i].address!=StateStorage::tailWindowBase());
 StateStorage::abandon();acknowledge(SUSAMUNE_STATE_CANCELLED,0,0);tick();
 CHECK(StateStorage::quiet()&&!StateStorage::takeResult(result)&&ghostCanClaim());return 0;
}
'''


class StateTransferLeaseTests(unittest.TestCase):
    fixture_source = BRIDGE
    setUpClass = classmethod(client.StateStorageClientTests.setUpClass.__func__)

    def check(self, name, values=(0,)):
        for value in values:
            with self.subTest(case=value):
                self.assertEqual(getattr(self.lib, name)(value), 0, name)

    def test_claim_precedes_tape_header_metadata_and_name_writes(self):
        self.check('claim_before_prepare', range(5))

    def test_both_receipts_then_reader_retains_across_deferred_frames(self):
        self.check('two_receipts_and_deferred_reader', range(2))

    def test_stream_chains_keep_owner_and_stale_result_cannot_release_new_reader(self):
        self.check('streaming_owner_and_stale_result')

    def test_abandoned_cancel_preserves_command_and_consumes_real_terminal_status(self):
        self.check('cancel_and_abandon_keeps_original_command', range(2))

    def test_failed_cleanup_accepts_consumption_but_quarantines_memory(self):
        self.check('transient_consumption_and_failure', range(2))

    def test_request_wrap_and_nonwrapping_result_identity_across_init(self):
        self.check('result_and_request_generation_limits', range(2))

    def test_backend_availability_and_epoch_change_fail_closed(self):
        self.check('backend_and_reset_failure', range(2))

    def test_import_invalidates_dynamic_stage_and_every_pool_bank(self):
        self.check('all_four_banks_and_dynamic_stage')

    def test_tail_window_refuses_legacy_unknown_flags_and_competing_owner(self):
        self.check('tail_window_api_bounds',range(4))

    def test_tail_window_exact_cache_range_actual_receipt_size_and_retained_owner(self):
        self.check('tail_window_cache_and_borrow',(0,1,2,8))

    def test_tail_window_stale_receipt_cannot_finish_borrow_or_cancellation(self):
        self.check('tail_window_stale_receipt_and_cancel')


if __name__ == '__main__':
    unittest.main()
