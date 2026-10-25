"""Build and publish root export plans under the real PPC transfer lease."""
import unittest

import test_state_storage_client as client
from test_state_transfer_lease import BRIDGE


EXTRA = r'''
static u32 built, builderKind, builderError;
static bool buildPlan(void *context, SusamuneStateExportPlan &p, u32 metadataCrc) {
 ++built;
 if(context!=&built || ghostCanClaim() || StateStorage::sTransferPhase!=StateStorage::TRANSFER_LOCAL)
  builderError=1;
 p={};p.magic=SUSAMUNE_STATE_EXPORT_PLAN;p.version=SUSAMUNE_STATE_EXPORT_PLAN_VERSION;
 p.count=3;p.rawBytes=0x4004d;p.packedBytes=44;p.metadataCrc=metadataCrc;
 p.blocks[0]={0x8000,11};p.blocks[1]={SUSAMUNE_STATE_POOL_SIZE,12};
 p.blocks[2]={SUSAMUNE_TRANSFER_POOL_SIZE-SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE,13};
 if(builderKind==1)p.blocks[0].offset=SUSAMUNE_STATE_POOL_SIZE-32,p.blocks[0].size=40,p.packedBytes=73;
 if(builderKind==5)p.blocks[2].offset-=32,p.blocks[2].size=40,p.packedBytes=71;
 if(builderKind==2)p.kind=2;
 p.checksum=SusamuneStateExportPlanCrc(&p);
 if(builderKind==3)p.checksum^=1;
 return builderKind!=4;
}
static bool planned() {
 SusamuneStateArchiveHeader h={};h.metadataSize=8;h.packedSize=builderKind==1?73:builderKind==5?71:44;
 h.rawSize=0x4004d;h.gameId=0x474d5350;h.buildCrc=23;h.snapshotVersion=17;
 const u32 metadata[2]={0x12345678,0x87654321};
 return StateStorage::startPlannedExport(h,metadata,buildPlan,&built);
}
EXPORT planned_claim_before_builder(int held) {
 built=builderKind=builderError=0;CHECK(startShared()==0);
 TransferLease::Token ghost;
 if(held)CHECK(TransferLease::claim(TransferLease::GHOST,ghost));
 static SusamuneStateStorageMailbox before;before=testMailbox;
 clearCacheLog();const bool started=planned();
 if(held){CHECK(!started&&!built&&!memcmp(&before,&testMailbox,sizeof(before)));
  CHECK(TransferLease::release(ghost));return 0;}
 CHECK(started&&built==1&&!builderError);
 CHECK(testMailbox.request.command==SUSAMUNE_STATE_CMD_EXPORT&&
  testMailbox.request.reserved==SUSAMUNE_STATE_EXPORT_PLAN&&!testMailbox.request.poolOffset);
 bool first=false,second=false,fifth=false,plan=false;
 for(u32 i=0;i<flushCount;++i){const auto&f=flushed[i];
  if(f.address==testPool+0x8000&&f.size==11)first=true;
  if(f.address==testExtra&&f.size==12)second=true;
  if(f.address==fifthBank&&f.size==13)fifth=true;
  if(f.address==testStaging&&f.size==sizeof(SusamuneStateExportPlan))plan=true;}
 CHECK(first&&second&&fifth&&plan&&!ghostCanClaim());
 acknowledge(SUSAMUNE_STATE_IO_ERROR,0,0);tick();StateStorage::Result result;
 CHECK(!StateStorage::takeResult(result));CHECK(done()==0);
 CHECK(StateStorage::takeResult(result)&&!ghostCanClaim());
 CHECK(StateStorage::consumeResult(result)&&StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT invalid_plan_never_publishes(int kind) {
 built=builderError=0;builderKind=kind;CHECK(startShared()==0);
 static SusamuneStateStorageMailbox before;before=testMailbox;
 CHECK(!planned()&&built==1&&!builderError);
 CHECK(!memcmp(&before,&testMailbox,sizeof(before)));
 CHECK(StateStorage::quiet()&&ghostCanClaim());return 0;
}
EXPORT legacy_plan_never_calls_builder() {
 reset(0);built=builderKind=builderError=0;CHECK(!planned()&&!built);
 CHECK(StateStorage::quiet());return 0;
}
EXPORT planned_cancel_retains_the_original_request_and_owner() {
 built=builderKind=builderError=0;CHECK(startShared()==0);CHECK(planned());
 const auto request=testMailbox.request;
 CHECK(StateStorage::cancel()&&!memcmp(&request,&testMailbox.request,sizeof(request)));
 CHECK(!StateStorage::quiet()&&!ghostCanClaim());
 acknowledge(SUSAMUNE_STATE_CANCELLED,0,0);CHECK(done()==0);
 StateStorage::Result result;CHECK(StateStorage::takeResult(result));
 CHECK(result.status==SUSAMUNE_STATE_CANCELLED&&!ghostCanClaim());
 CHECK(StateStorage::consumeResult(result)&&StateStorage::quiet());return 0;
}
'''


class PlannedClientTests(unittest.TestCase):
    fixture_source = BRIDGE + EXTRA
    setUpClass = classmethod(client.StateStorageClientTests.setUpClass.__func__)

    def test_builder_runs_only_after_exclusive_claim_and_flushes_every_range(self):
        for held in (0, 1):
            with self.subTest(held=held):
                self.assertEqual(self.lib.planned_claim_before_builder(held), 0)

    def test_invalid_callback_crc_kind_and_bank_crossing_preserve_mailbox(self):
        for kind in range(1, 6):
            with self.subTest(kind=kind):
                self.assertEqual(self.lib.invalid_plan_never_publishes(kind), 0)

    def test_legacy_backend_refuses_before_builder_runs(self):
        self.assertEqual(self.lib.legacy_plan_never_calls_builder(), 0)

    def test_cancel_keeps_original_plan_request_and_owner_until_consumption(self):
        self.assertEqual(self.lib.planned_cancel_retains_the_original_request_and_owner(), 0)


if __name__ == '__main__':
    unittest.main()
