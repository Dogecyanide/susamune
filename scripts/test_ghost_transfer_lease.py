"""Actual PPC ghost consumer and lease client, with controlled ARM publications."""
import unittest

import test_ghost_storage_paging as paging


def instrument(source):
    source = source.replace('namespace Ghost {', r'''
static unsigned int prepareChecks,readerChecks,readerErrors;
static bool failExport,tearSubmit,tearConsume,reenterReader,tearRelease;
static void inspectPreparation(void *);
static void inspectReader(const void *);
static void inspectFlush(void *,u32);
namespace Ghost {''', 1)
    source = source.replace('void DCFlushRange(void*,u32){}',
        'static void inspectFlush(void *,u32);\nvoid DCFlushRange(void *p,u32 n){inspectFlush(p,n);}')
    source = source.replace('if(canonicalExport) {',
        'inspectPreparation(out);if(failExport)return false;if(canonicalExport) {', 1)
    source = source.replace('bool importPlayback(const void*,u32,bool){playbackImports++;',
        'bool importPlayback(const void *data,u32,bool){inspectReader(data);playbackImports++;')
    source = source.replace('bool importObserverTrack(const void*,u32,bool){observerImports++;',
        'bool importObserverTrack(const void *data,u32,bool){inspectReader(data);observerImports++;')
    source = source.replace('testTransfer={};sTransferToken={};',
        'prepareChecks=readerChecks=readerErrors=0;failExport=tearSubmit=tearConsume=reenterReader=tearRelease=false;'
        'testTransfer={};sTransferToken={};')
    return source


BRIDGE = r'''
static TWLeaseArm arm;
static unsigned int savedGeneration;
static void publishArm() {
    ++testTransfer.responsePublication.issued;
    testTransfer.responsePublication.generation=testTransfer.responsePublication.issued;
}
static void inspectPreparation(void *p) {
    ++prepareChecks;
    if(TransferLease::mode()!=TransferLease::SHARED)return;
    if(p!=sharedPayload||TransferLease::sPpc.phase!=TW_PPC_LOCAL||
       TransferLease::sPpc.key.owner!=TW_OWNER_GHOST||quiet())++readerErrors;
    if(tearSubmit){savedGeneration=testTransfer.responsePublication.generation;
        testTransfer.responsePublication.generation=0;tearSubmit=false;}
}
static void inspectReader(const void *p) {
    ++readerChecks;
    if(p!=sharedPayload||TransferLease::sPpc.phase!=TW_PPC_BORROWED||quiet())++readerErrors;
    TransferLease::Token competitor;
    if(TransferLease::claim(TransferLease::STATE,competitor))++readerErrors;
    if(reenterReader) {
        const u32 seq=mailbox.request.requestSeq;
        init();update();refresh();
        if(mailbox.request.requestSeq!=seq||quiet())++readerErrors;
    }
    if(tearConsume){savedGeneration=testTransfer.responsePublication.generation;
        testTransfer.responsePublication.generation=0;tearConsume=false;}
}
static void inspectFlush(void *p,u32) {
    if(tearRelease&&p==&testTransfer.requestPublication&&
       testTransfer.requestPublication.generation&&
       sTransferPhase==TRANSFER_CONSUME&&testTransfer.request.phase==TW_WIRE_LOCAL) {
        savedGeneration=testTransfer.responsePublication.generation;
        testTransfer.responsePublication.generation=0;tearRelease=false;
    }
}
static int startShared(bool backend=true) {
    reset();
    TransferLease::sPpc={};TransferLease::sControl={};TransferLease::sPublisher={};
    TransferLease::sMode=TransferLease::UNINITIALIZED;TransferLease::sOwner=0;TransferLease::sShared=false;
    arm={};testTransfer={};TWLeaseResetBegin(&arm,&testTransfer);
    CHECK(TWLeaseRetired(&arm,TW_OWNER_GHOST,1));CHECK(TWLeaseRetired(&arm,TW_OWNER_STATE,1));
    CHECK(TWLeaseResetPublish(&arm,&testTransfer));publishArm();
    init();CHECK(quiet()&&sRefreshQueued[0]);
    CHECK(TransferLease::mode()==TransferLease::CAPABLE);
    CHECK(TransferLease::activate(quiet(),true,true));
    CHECK(TWLeaseActivate(&arm,&testTransfer,1,1));
    mailbox.response.ackSeq=0;
    mailbox.response.flags=backend?SUSAMUNE_GHOST_RESPONSE_READY:0;
    mailbox.response.status=backend?0:SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE;
    publishArm();TransferLease::poll();
    CHECK(transferReady());CHECK(available()==backend);
    sRefreshQueued[0]=sRefreshQueued[1]=false;
    memset(payload,0x69,sizeof(payload));memset(sharedPayload,0xA5,sizeof(sharedPayload));
    return 0;
}
static int done(bool pump=true) {
    CHECK(TWLeaseStart(&arm,&testTransfer,TW_OWNER_GHOST,
        mailbox.request.requestSeq,0,mailbox.request.command));
    TWLeaseToken token={arm.key.epoch,arm.key.ticket};
    CHECK(TWLeaseFinish(&arm,&testTransfer,token,1,1,1));publishArm();
    if(pump)update();return 0;
}
static void sharedPage(u32 count=1) {
    makePage(count);memcpy(sharedPayload,payload,sizeof(SusamuneGhostCatalogPage));
}
static int readyShared(bool imported=false) {
    CHECK(refreshPage(imported,0));sharedPage();ack();CHECK(busy());
    CHECK(done()==0);CHECK(quiet());CHECK(imported?importedCatalogReady():catalogReady());
    return 0;
}
EXPORT shared_claim_before_prepare(int which) {
    CHECK(startShared()==0);
    TransferLease::Token state;CHECK(TransferLease::claim(TransferLease::STATE,state));
    const u32 seq=mailbox.request.requestSeq;
    Identity id={};id.profile=SUSAMUNE_GHOST_IMPORTED_PROFILE;id.region=0;id.id=3;
    id.flags=SUSAMUNE_GHOST_SLOT_PRESENT|SUSAMUNE_GHOST_SLOT_IMPORTED;
    memcpy(id.leaf,"exact.smsghost",15);
    if(which==0)CHECK(!saveNew());
    else if(which==1)CHECK(!load(id));
    else if(which==2)CHECK(!remove(id));
    else CHECK(scanImports());
    CHECK(prepareChecks==0&&mailbox.request.requestSeq==seq);
    for(u32 i=0;i<sizeof(sharedPayload);++i)CHECK(sharedPayload[i]==0xA5);
    CHECK(quiet());CHECK(TransferLease::release(state));
    if(which==3){update();CHECK(busy()&&mailbox.request.command==SUSAMUNE_GHOST_CMD_IMPORT_SCAN);}
    else if(which==0){CHECK(saveNew());CHECK(prepareChecks==1&&readerErrors==0);}
    else {CHECK(which==1?load(id):remove(id));CHECK(!memcmp(sharedPayload,id.leaf,sizeof(id.leaf)));}
    CHECK(testTransfer.request.phase==TW_WIRE_ARM&&testTransfer.request.owner==TW_OWNER_GHOST);
    return 0;
}
EXPORT shared_two_receipts(int reversed) {
    CHECK(startShared()==0);CHECK(saveNew(42));
    const u32 seq=mailbox.request.requestSeq;
    if(reversed)CHECK(done()==0);else ack();
    CHECK(busy()&&!quiet()&&savedToken==0);
    init();CHECK(busy()&&mailbox.request.requestSeq==seq);
    if(reversed)ack();else CHECK(done()==0);
    CHECK(quiet()&&savedToken==42&&checkpoints==1&&readerErrors==0);
    CHECK(sRefreshQueued[0]);
    TransferLease::Token state;CHECK(TransferLease::claim(TransferLease::STATE,state));
    update();CHECK(quiet()&&sRefreshQueued[0]&&mailbox.request.requestSeq==seq);
    CHECK(TransferLease::release(state));update();CHECK(busy());return 0;
}
EXPORT shared_reader_lifetime(int variant) {
    CHECK(startShared()==0);CHECK(readyShared(variant==1)==0);
    Identity id;CHECK(copyIdentity(variant==1,0,&id));
    if(variant==2)CHECK(loadObserver(id,false));else CHECK(load(id));
    reenterReader=true;
    if(variant==3)acceptImport=false;
    ack();CHECK(readerChecks==0&&busy());CHECK(done()==0);
    CHECK(readerChecks==1&&readerErrors==0&&quiet());
    CHECK(TransferLease::sPpc.phase==TW_PPC_IDLE);return 0;
}
EXPORT shared_stale_or_error(int variant) {
    CHECK(startShared()==0);CHECK(readyShared()==0);
    Identity id;CHECK(copyIdentity(false,0,&id));CHECK(load(id));
    if(variant==0)onSavestateLoaded();
    if(variant==1){++testProfile;update();}
    ack(variant==2?SUSAMUNE_GHOST_STATUS_IO_BASE:0);
    if(variant==3)mailbox.response.payloadSize=0xffffffffu;
    CHECK(done()==0);CHECK(readerChecks==0&&quiet());return 0;
}
EXPORT shared_timeout_retains_owner() {
    CHECK(startShared()==0);CHECK(readyShared()==0);
    Identity id;CHECK(copyIdentity(false,0,&id));CHECK(loadObserver(id,false));
    for(u32 i=0;i<=kTimeoutFrames;++i)update();CHECK(timedOut()&&!quiet());
    TransferLease::Token state;CHECK(!TransferLease::claim(TransferLease::STATE,state));
    CHECK(observerStops==1);ack();CHECK(busy());CHECK(done()==0);
    CHECK(quiet()&&!timedOut()&&readerChecks==0);return 0;
}
EXPORT shared_retry_after_transient(int variant) {
    CHECK(startShared()==0);
    if(variant==0){tearSubmit=true;CHECK(saveNew());CHECK(sTransferPhase==TRANSFER_SUBMIT);}
    else {
        CHECK(readyShared()==0);Identity id;CHECK(copyIdentity(false,0,&id));CHECK(load(id));
        tearConsume=variant==1;tearRelease=variant==2;ack();CHECK(done()==0);
        CHECK(sTransferPhase==(variant==1?TRANSFER_CONSUME:TRANSFER_RELEASE));
    }
    const u32 seq=mailbox.request.requestSeq;CHECK(!quiet());update();CHECK(!quiet());
    testTransfer.responsePublication.generation=savedGeneration;update();
    CHECK(mailbox.request.requestSeq==seq);
    if(variant==0){CHECK(sTransferPhase==TRANSFER_REMOTE);ack();CHECK(done()==0);}
    CHECK(quiet()&&readerChecks==(variant?1u:0u));return 0;
}
EXPORT shared_failure_never_falls_back(int variant) {
    CHECK(startShared()==0);CHECK(saveNew());
    if(variant==0){TWLeaseResetBegin(&arm,&testTransfer);publishArm();}
    else {TransferLease::sPublisher.issued=0xffffffffu;ack();CHECK(done(false)==0);}
    update();CHECK(!quiet()&&busy()&&sTransferFailed);
    const u32 seq=mailbox.request.requestSeq;init();CHECK(!saveNew());
    for(u32 i=0;i<sizeof(payload);++i)CHECK(payload[i]==0x69);
    CHECK(transferPayload()==sharedPayload&&mailbox.request.requestSeq==seq);return 0;
}
EXPORT shared_backend_and_local_failure(int unavailable) {
    CHECK(startShared(!unavailable)==0);
    if(unavailable){CHECK(!available()&&!saveNew()&&quiet()&&prepareChecks==0);}
    else {failExport=true;CHECK(!saveNew());CHECK(quiet()&&prepareChecks==1&&readerErrors==0);}
    TransferLease::Token codec;CHECK(TransferLease::claim(TransferLease::CODEC,codec));
    CHECK(TransferLease::release(codec));return 0;
}
EXPORT fresh_image_refuses_surviving_shared_epoch() {
    CHECK(startShared()==0);
    sSharedBackend=false;sTransferPhase=TRANSFER_NONE;
    TransferLease::sPpc={};TransferLease::sControl={};TransferLease::sPublisher={};
    TransferLease::sMode=TransferLease::UNINITIALIZED;TransferLease::sOwner=0;TransferLease::sShared=false;
    init();CHECK(sTransferFailed&&!saveNew());
    for(u32 i=0;i<sizeof(payload);++i)CHECK(payload[i]==0x69);return 0;
}
'''


class GhostLeaseTests(unittest.TestCase):
    fixture_transform = staticmethod(instrument)
    bridge_source = BRIDGE
    setUpClass = classmethod(paging.GhostStoragePagingTests.setUpClass.__func__)

    def check(self, name, values=(0,)):
        for value in values:
            with self.subTest(case=value):
                line = getattr(self.dll,name)(value)
                context = '\n'.join(self.fixture_source.splitlines()[max(0,line-2):line+1]) if line else ''
                self.assertEqual(line,0,context)

    def test_claim_precedes_export_filename_or_catalog_preparation(self):
        self.check('shared_claim_before_prepare',range(4))

    def test_both_receipts_required_and_queued_refresh_yields_to_state(self):
        self.check('shared_two_receipts',range(2))

    def test_result_readers_keep_owner_through_reentrancy_and_validation(self):
        self.check('shared_reader_lifetime',range(4))

    def test_stale_error_and_malformed_results_release_only_after_done(self):
        self.check('shared_stale_or_error',range(4))

    def test_timeout_holds_owner_until_late_ack_and_discards_stale_observer(self):
        self.check('shared_timeout_retains_owner')

    def test_transient_publication_retries_do_not_repeat_consumers(self):
        self.check('shared_retry_after_transient',range(3))

    def test_reset_or_publication_failure_never_reuses_legacy_address(self):
        self.check('shared_failure_never_falls_back',range(2))

    def test_backend_unavailable_and_local_export_failure_leave_no_owner(self):
        self.check('shared_backend_and_local_failure',range(2))

    def test_fresh_image_cannot_adopt_surviving_shared_epoch(self):
        self.check('fresh_image_refuses_surviving_shared_epoch')


if __name__=='__main__':
    unittest.main()
