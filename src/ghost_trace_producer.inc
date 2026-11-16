namespace {
volatile MsTraceFenceInfo &fenceMailbox=*reinterpret_cast<volatile MsTraceFenceInfo*>(MS_TRACE_CONTROL_PPC+MS_TRACE_FENCE_INFO_OFFSET);
volatile MsTraceBranchMailbox &branchMailbox=*reinterpret_cast<volatile MsTraceBranchMailbox*>(MS_TRACE_CONTROL_PPC+MS_TRACE_BRANCH_MAILBOX_OFFSET);
GhostCheckpoints::Pin*pendingFence(){
    GhostCheckpoints::Pin*next=nullptr;if(!checkpoints)return next;
    for(unsigned i=0;i<GhostCheckpoints::kPins;++i){auto&p=checkpoints->pins.pins[i];
        if(p.phase==GhostCheckpoints::PENDING&&p.prefix.nonce==s.response.nonce&&p.prefix.run==s.run&&(!next||p.prefix.chunk<next->prefix.chunk))next=&p;
    }return next;
}
unsigned checkpointBoundary(){auto*p=pendingFence();return p?p->prefix.chunk:~0u;}
bool sourcePinned(){return checkpoints&&GhostCheckpoints::sourceOwned(checkpoints->pins,s.response.nonce,s.run);}
bool forkBlocksCapture(){return checkpoints&&checkpoints->phase!=FORK_NONE&&checkpoints->phase!=FORK_PUBLISHING;}
bool atomicContinuationPending(){return checkpoints&&checkpoints->fast&&checkpoints->phase==FORK_FAST_PENDING;}
void releaseFork(){
    auto&c=*checkpoints;if(c.ownsLoad){
        if(c.pins.loadRequest)GhostCheckpoints::forkAcknowledged(c.pins,c.load,c.newRun);
        GhostCheckpoints::releaseLoad(c.pins,c.load);c.ownsLoad=false;
    }
}
void forkFailed(unsigned error){auto&c=*checkpoints;c.error=error?error:MS_TRACE_BAD_SOURCE;c.phase=FORK_FAILED;releaseFork();}
bool publishFork(){
    auto&c=*checkpoints;auto*p=GhostCheckpoints::find(c.pins,c.snapshot.prefix);if(!p||!GhostCheckpoints::ready(*p))return false;
    DCInvalidateRange((void*)&branchMailbox.response,32);MsTraceBranchResponse response;memcpy(&response,(const void*)&branchMailbox.response,32);
    DCInvalidateRange((void*)&branchMailbox.request,32);const unsigned previous=branchMailbox.request.sequence;
    if(response.magic!=MS_TRACE_BRANCH_MAGIC||response.version!=MS_TRACE_BRANCH_VERSION||response.bootNonce!=s.response.nonce||
       response.ack!=previous||previous==~0u)return false;
    MsTraceBranch map={s.response.nonce,c.newRun,c.snapshot.game,c.snapshot.capabilities,c.snapshot.prefix,p->fence,kForkOwner,1,1,0};
    if(!MsTraceBranchValid(&map,MS_TRACE_BRANCH_FORK)||
       !GhostTraceBranchOwner::claim(&branchMailbox,s.response.nonce,&c))return false;
    MsTraceBranchRequest request={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,s.response.nonce,0,MS_TRACE_BRANCH_STORE,MS_TRACE_BRANCH_FORK,s.response.nonce,c.newRun};
    memcpy((void*)&branchMailbox.payload,&map,96);memcpy((void*)&branchMailbox.request,&request,32);
    DCStoreRange((void*)&branchMailbox.payload,128);c.branchSequence=previous+1;
    branchMailbox.request.sequence=c.branchSequence;DCStoreRange((void*)&branchMailbox.request,32);return true;
}
void pollFastContinuation(){
    auto&c=*checkpoints;
    DCInvalidateRange((void*)&branchMailbox.response,32);MsTraceBranchResponse r;memcpy(&r,(const void*)&branchMailbox.response,32);
    const bool reply=r.magic==MS_TRACE_BRANCH_MAGIC&&r.version==MS_TRACE_BRANCH_VERSION&&r.bootNonce==s.response.nonce&&
        r.ack==c.branchSequence&&r.reserved[1]==c.atomicRequest&&r.reserved[2]==c.oldRun;
    if(c.phase==FORK_FAST_PENDING){
        if(s.response.ackRequest!=c.atomicRequest||!reply)return;
        if(r.reserved[0]==c.newRun){
            const MsTraceResponse accepted=s.response;
            if(!initializeCapture(c.newRun,c.snapshot.scene,false)){
                // ARM ended the old leases even when the local hook refuses reset.
                memset(s.used,0,sizeof(s.used));memset(s.sealed,0,sizeof(s.sealed));memset(s.sent,0,sizeof(s.sent));
                s.run=c.newRun;c.canceled=true;c.error=MS_TRACE_BAD_SOURCE;
            }
            s.response=accepted;s.command=MS_TRACE_START;s.ordinary=true;
            s.parentNonce=c.snapshot.prefix.nonce;s.parentRun=c.snapshot.prefix.run;s.parentChunk=c.snapshot.prefix.chunk;
            s.runFlags=MS_TRACE_CONTINUATION_RUN_FLAGS;
            if(accepted.error||accepted.phase!=MS_TRACE_RECORDING){c.canceled=true;c.error=accepted.error?accepted.error:MS_TRACE_BAD_SOURCE;}
        }else if(!r.reserved[0]){c.canceled=true;c.error=s.response.error?s.response.error:MS_TRACE_BUSY;}
        else return;
        c.phase=c.canceled?FORK_UNTRACKED:FORK_FAST_READY;
        if(c.canceled)s.ending=MS_TRACE_RELEASE;
    }
    if(!reply||r.status==MS_TRACE_BRANCH_PENDING)return;
    if(r.status){c.error=r.status;c.canceled=true;s.ending=MS_TRACE_RELEASE;c.phase=FORK_UNTRACKED;}
    else c.durable=true;
    GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);releaseFork();
    if(c.phase==FORK_PUBLISHING){c.phase=FORK_NONE;c.fast=false;c.snapshot={};}
    else if(c.phase==FORK_UNTRACKED&&s.request==s.response.ackRequest&&
        (s.response.phase==MS_TRACE_DISCARDED||s.response.phase==MS_TRACE_SAVED||s.response.phase==MS_TRACE_FAILED)){
        c.phase=FORK_NONE;c.fast=false;c.snapshot={};
    }
}
void checkpointPoll(){
    if(!checkpoints)return;auto&c=*checkpoints;
    for(unsigned i=0;i<GhostCheckpoints::kPins;++i){auto&p=c.pins.pins[i];if(p.phase!=GhostCheckpoints::PENDING||p.prefix.nonce!=s.response.nonce||p.prefix.run!=s.run)continue;
        if(s.response.phase==MS_TRACE_FAILED){MsTraceFenceInfo empty={};GhostCheckpoints::acknowledge(c.pins,p.prefix.nonce,p.prefix.run,p.request,empty,s.response.error?s.response.error:MS_TRACE_IO);continue;}
        if(!p.request||s.response.ackRequest!=p.request)continue;
        DCInvalidateRange((void*)&fenceMailbox,32);MsTraceFenceInfo info;memcpy(&info,(const void*)&fenceMailbox,32);
        if(!GhostCheckpoints::acknowledge(c.pins,p.prefix.nonce,p.prefix.run,p.request,info,0)){
            MsTraceFenceInfo empty={};GhostCheckpoints::acknowledge(c.pins,p.prefix.nonce,p.prefix.run,p.request,empty,MS_TRACE_PROTOCOL);
        }
    }
    if(c.fast){pollFastContinuation();return;}
    if(c.phase==FORK_NONE||c.phase==FORK_READY||c.phase==FORK_FAILED)return;
    if(c.phase==FORK_FENCE){
        auto*p=GhostCheckpoints::find(c.pins,c.snapshot.prefix);
        if(!p||p->phase==GhostCheckpoints::FAILED){forkFailed(MS_TRACE_BAD_SOURCE);return;}
        if(!GhostCheckpoints::ready(*p))return;
        if(!GhostCheckpoints::forkIssued(c.pins,c.load,c.newRun)){forkFailed(MS_TRACE_PROTOCOL);return;}
        c.phase=FORK_SOURCE;if(s.command==MS_TRACE_START){flushRandom();s.ending=sourcePinned()?MS_TRACE_KEEP:discardOperation();}
    }
    if(c.phase==FORK_SOURCE){
        if(s.response.phase==MS_TRACE_FAILED){forkFailed(s.response.error);return;}
        if(s.request!=s.response.ackRequest||
           (s.response.phase!=MS_TRACE_SAVED&&s.response.phase!=MS_TRACE_IDLE&&s.response.phase!=MS_TRACE_DISCARDED))return;
        if(c.canceled){releaseFork();c.phase=FORK_NONE;return;}
        if(!startCapture(c.newRun,c.snapshot.scene,false)){forkFailed(MS_TRACE_PROTOCOL);return;}
        s.ordinary=true;c.phase=FORK_TAIL;return;
    }
    if(c.phase==FORK_TAIL){
        if(s.response.phase==MS_TRACE_FAILED){forkFailed(s.response.error);return;}
        if(s.request!=s.response.ackRequest||s.response.phase!=MS_TRACE_RECORDING)return;
        if(c.canceled){s.ending=MS_TRACE_DISCARD;c.phase=FORK_DISCARD;return;}
        if(publishFork())c.phase=FORK_MAP;return;
    }
    if(c.phase==FORK_MAP){
        DCInvalidateRange((void*)&branchMailbox.response,32);MsTraceBranchResponse response;memcpy(&response,(const void*)&branchMailbox.response,32);
        if(response.magic!=MS_TRACE_BRANCH_MAGIC||response.version!=MS_TRACE_BRANCH_VERSION||response.bootNonce!=s.response.nonce){forkFailed(MS_TRACE_PROTOCOL);return;}
        if(response.ack!=c.branchSequence)return;
        GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);
        if(response.status){c.error=response.status;s.ending=MS_TRACE_DISCARD;c.phase=FORK_DISCARD;return;}
        if(c.canceled){s.ending=MS_TRACE_KEEP;c.phase=FORK_DISCARD;return;}
        c.phase=FORK_READY;return;
    }
    if(c.phase==FORK_DISCARD&&s.request==s.response.ackRequest&&
       (s.response.phase==MS_TRACE_DISCARDED||s.response.phase==MS_TRACE_SAVED||s.response.phase==MS_TRACE_FAILED)){
        releaseFork();c.phase=c.canceled?FORK_NONE:FORK_FAILED;
    }
}
bool issueCheckpointFence(){
    auto*p=pendingFence();if(!p)return false;
    if(!p->request&&s.request==s.response.ackRequest&&s.command==MS_TRACE_START){
        command(MS_TRACE_FENCE,p->prefix.chunk);p->request=s.request;
    }return true;
}
}
bool installCheckpoints(CheckpointController&c){
    unsigned nonce;if(checkpoints||!backendIdentity(nonce))return false;c={};GhostCheckpoints::init(c.pins);c.serial=1;checkpoints=&c;return true;
}
CheckpointCapture captureCheckpoint(CheckpointSnapshot &out) {
    out = {};
    if (!checkpoints || !s.ordinary || !recording()) return CheckpointCapture::Unavailable;
    service();
    if (s.error || !recording() || checkpoints->pins.candidate != GhostCheckpoints::kNone)
        return CheckpointCapture::Unavailable;
    drainSpin();
    flushRandom();
    if (s.ending || !s.frame) return CheckpointCapture::Unavailable;

    auto &controller = *checkpoints;
    MsTracePrefix prefix;
    if (!s.used[s.active] && controller.lastPrefix.nonce == s.response.nonce &&
        controller.lastPrefix.run == s.run && controller.lastRecords == s.records) {
        prefix = controller.lastPrefix;
    } else {
        const unsigned index = s.active;
        if (!controller.serial) return CheckpointCapture::Unavailable;
        // Sealing another bank before the ACK would leave nowhere to record.
        if (s.sealed[index] || s.sealed[index ^ 1u]) return CheckpointCapture::BankBusy;
        if (!s.used[index]) return CheckpointCapture::Unavailable;
        prefix = {s.response.nonce, s.run, controller.serial++, s.frame, s.tick, s.next,
                  s.used[index], s.hash[index]};
        // Ownership must exist before this chunk can be published to ARM.
        if (!GhostCheckpoints::capture(controller.pins, prefix, 0)) return CheckpointCapture::Unavailable;
        seal();
        controller.lastPrefix = prefix;
        controller.lastRecords = s.records;
    }
    if (controller.pins.candidate == GhostCheckpoints::kNone &&
        !GhostCheckpoints::capture(controller.pins, prefix, 0)) return CheckpointCapture::Unavailable;
    out.magic = kCheckpointMagic;
    out.version = kCheckpointVersion;
    out.prefix = prefix;
    out.game = s.game;
    out.scene = s.scene;
    out.capabilities = s.capabilities;
    service();
    return CheckpointCapture::Captured;
}
void abandonCheckpoint(){if(checkpoints)GhostCheckpoints::abandon(checkpoints->pins);}
bool checkpointSaved(unsigned slot,unsigned generation){
    if(!checkpoints)return true;auto&state=checkpoints->pins;
    if(state.candidate<GhostCheckpoints::kPins)return GhostCheckpoints::commit(state,slot,generation);
    if(slot>=GhostCheckpoints::kSlots)return false;auto old=state.slots[slot];
    if(old.pin<GhostCheckpoints::kPins)GhostCheckpoints::clear(state,slot,old.generation);return true;
}
void checkpointCleared(unsigned slot,unsigned generation){if(checkpoints)GhostCheckpoints::clear(checkpoints->pins,slot,generation);}
int checkpointReady(const CheckpointSnapshot&v){
    if(!checkpointValid(v))return -1;if(!v.magic)return 1;if(!checkpoints)return -1;
    auto*p=GhostCheckpoints::find(checkpoints->pins,v.prefix);if(!p||p->phase==GhostCheckpoints::FAILED)return -1;return GhostCheckpoints::ready(*p)?1:0;
}
bool checkpointSourceOwned(unsigned nonce,unsigned run){return checkpoints&&GhostCheckpoints::sourceOwned(checkpoints->pins,nonce,run);}
bool checkpointExport(CheckpointSnapshot&v){
    if(!checkpointValid(v))return false;if(!v.magic)return true;if(!checkpoints)return false;
    auto*pin=GhostCheckpoints::find(checkpoints->pins,v.prefix);
    if(!pin||!GhostCheckpoints::ready(*pin))return false;
    v.fence=pin->fence;return checkpointValid(v);
}
bool importCheckpoint(const CheckpointSnapshot&v){
    if(!checkpointValid(v))return false;
    if(!v.magic)return !checkpoints||checkpoints->pins.candidate==GhostCheckpoints::kNone;
    return checkpoints&&v.fence.sequence&&GhostCheckpoints::adoptDurable(checkpoints->pins,v.prefix,v.fence);
}
bool checkpointLoadValid(const CheckpointSnapshot&v,unsigned slot,unsigned generation){
    if(!checkpointValid(v))return false;if(!v.magic)return true;
    if(!checkpoints||slot>=GhostCheckpoints::kSlots||!generation)return false;
    const auto&saved=checkpoints->pins.slots[slot];
    if(saved.generation!=generation||saved.pin>=GhostCheckpoints::kPins)return false;
    const auto&p=checkpoints->pins.pins[saved.pin];
    return p.references&&p.phase!=GhostCheckpoints::EMPTY&&MsTracePrefixSame(&p.prefix,&v.prefix);
}
int beginFastContinuation(const CheckpointSnapshot&v,unsigned slot,unsigned generation,unsigned newRun){
    if(!checkpointLoadValid(v,slot,generation)||!v.magic)return -1;
    if(!checkpoints||checkpoints->phase!=FORK_NONE||!fastPreparedRun(newRun)||!bootReady||!GhostMemory::ready())return 0;
    poll();auto&c=*checkpoints;
    if(!s.run||s.request!=s.response.ackRequest||s.ending||s.error||pendingFence()||v.game!=s.game||v.capabilities!=s.capabilities||
       (s.response.phase!=MS_TRACE_RECORDING&&s.response.phase!=MS_TRACE_SAVED&&s.response.phase!=MS_TRACE_DISCARDED&&s.response.phase!=MS_TRACE_IDLE))return 0;
    auto*p=GhostCheckpoints::find(c.pins,v.prefix);if(!p||!GhostCheckpoints::ready(*p))return 0;
    DCInvalidateRange((void*)&branchMailbox.response,32);MsTraceBranchResponse response;memcpy(&response,(const void*)&branchMailbox.response,32);
    DCInvalidateRange((void*)&branchMailbox.request,32);const unsigned previous=branchMailbox.request.sequence;
    if(response.magic!=MS_TRACE_BRANCH_MAGIC||response.version!=MS_TRACE_BRANCH_VERSION||response.bootNonce!=s.response.nonce||
       response.ack!=previous||previous==~0u||s.request==~0u||!GhostTraceBranchOwner::claim(&branchMailbox,s.response.nonce,&c))return 0;
    if(!GhostCheckpoints::retainLoad(c.pins,slot,generation,c.load)){GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);return -1;}
    c.ownsLoad=true;c.snapshot=v;c.newRun=newRun;c.oldRun=s.run;c.atomicRequest=s.request+1;c.branchSequence=previous+1;
    c.error=c.restoreActions=0;c.canceled=c.durable=false;c.fast=true;
    if(!GhostCheckpoints::forkIssued(c.pins,c.load,newRun)){releaseFork();GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);c.fast=false;return -1;}
    MsTraceBranch map={s.response.nonce,newRun,v.game,v.capabilities,v.prefix,p->fence,kForkOwner,1,1,0};
    if(!MsTraceBranchValid(&map,MS_TRACE_BRANCH_FORK)){releaseFork();GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);c.fast=false;return -1;}
    drainSpin();flushRandom();
    if(!GhostSpinObservation::uninstall(GhostSpinObservation::RECORD)){releaseFork();GhostTraceBranchOwner::release(&branchMailbox,s.response.nonce,&c);c.fast=false;return 0;}
    c.phase=FORK_FAST_PENDING;s.spinInstalled=false;
    MsTraceBranchRequest branch={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,s.response.nonce,c.branchSequence,MS_TRACE_BRANCH_ASYNC_CONTINUE,c.atomicRequest,sourcePinned()?1u:0u,s.run};
    memcpy((void*)&branchMailbox.payload,&map,96);memcpy((void*)&branchMailbox.request,&branch,32);DCStoreRange((void*)&branchMailbox.payload,128);
    const MsTraceRequest request={MS_TRACE_MAGIC,MS_TRACE_VERSION,s.response.nonce,c.atomicRequest,MS_TRACE_CONTINUE,newRun,v.scene,v.capabilities};
    s.request=c.atomicRequest;memcpy((void*)&mailbox.request,&request,32);DCStoreRange((void*)&mailbox.request,32);
    return 1;
}
void stopFastContinuation(){
    if(!checkpoints||!checkpoints->fast){reset();return;}
    auto&c=*checkpoints;c.canceled=true;
    if(c.phase!=FORK_FAST_PENDING){s.ending=MS_TRACE_RELEASE;c.phase=FORK_UNTRACKED;}
}
bool fastContinuationUntracked(){return checkpoints&&checkpoints->fast&&checkpoints->canceled;}
bool continuationPublicationPending(){return checkpoints&&checkpoints->fast&&checkpoints->phase!=FORK_NONE&&!checkpoints->durable;}
bool continuationBackgroundPending(){return checkpoints&&checkpoints->fast&&(checkpoints->phase==FORK_PUBLISHING||checkpoints->phase==FORK_UNTRACKED);}
bool beginContinuation(const CheckpointSnapshot&v,unsigned slot,unsigned generation,unsigned newRun){
    if(!checkpoints||!v.magic||!checkpointValid(v)||!newRun||
       (newRun==v.prefix.run&&s.response.nonce==v.prefix.nonce)||!bootReady||
       (s.game&&v.game!=s.game)||(s.command==MS_TRACE_START&&!s.ordinary))return false;
    auto&c=*checkpoints;if(c.phase!=FORK_NONE)return c.newRun==newRun&&MsTracePrefixSame(&c.snapshot.prefix,&v.prefix);
    if(slot<GhostCheckpoints::kSlots){
        if(!GhostCheckpoints::retainLoad(c.pins,slot,generation,c.load))return false;
    }else{
        if(slot!=GhostCheckpoints::kSlots||!generation||!importCheckpoint(v))return false;
        if(!GhostCheckpoints::retainPrefixLoad(c.pins,v.prefix,c.load)){
            GhostCheckpoints::abandon(c.pins);return false;
        }
        GhostCheckpoints::abandon(c.pins);
    }
    if(!MsTracePrefixSame(&c.load.prefix,&v.prefix)){GhostCheckpoints::releaseLoad(c.pins,c.load);return false;}
    drainSpin();c.ownsLoad=true;c.snapshot=v;c.newRun=newRun;c.branchSequence=c.error=c.restoreActions=0;c.canceled=false;c.phase=FORK_FENCE;
    flushRandom();checkpointPoll();return true;
}
int continuationStatus(){
    if(!checkpoints||checkpoints->phase==FORK_NONE)return -1;
    if(checkpoints->fast){poll();pollFastContinuation();return checkpoints->phase==FORK_FAST_READY&&!checkpoints->canceled&&!checkpoints->error?1:0;}
    if(checkpoints->phase==FORK_READY){
        if(s.run==checkpoints->newRun&&s.command==MS_TRACE_START&&s.response.phase==MS_TRACE_RECORDING&&
           s.request==s.response.ackRequest&&!s.ending&&!s.error&&GhostMemory::ready())return 1;
        forkFailed(MS_TRACE_BAD_SOURCE);return -1;
    }return checkpoints->phase==FORK_FAILED?-1:0;
}
bool continuationPending(){return checkpoints&&checkpoints->phase!=FORK_NONE;}
unsigned continuationRun(){return checkpoints?checkpoints->newRun:0;}
bool commitContinuation(){
    if(!checkpoints||checkpoints->canceled||continuationStatus()!=1)return false;auto&c=*checkpoints;
    s.frame=c.snapshot.prefix.frame;s.tick=c.snapshot.prefix.tick;s.stageEmitted=s.stageStart.words[7];beginAttempt();
    unsigned char marker[MS_TRACE_CONTINUATION_BYTES];MsTracePut(marker,1);MsTracePut(marker+4,MS_TRACE_CONTINUATION_RUN_FLAGS);MsTracePut(marker+8,c.restoreActions);
    MsTracePut(marker+12,c.snapshot.prefix.nonce);MsTracePut(marker+16,c.snapshot.prefix.run);MsTracePut(marker+20,c.snapshot.prefix.chunk);
    MsTracePut(marker+24,c.snapshot.prefix.checksum);MsTracePut(marker+28,*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED));
    s32 qf=0;const bool timed=gQFTTimer.currentQf(&qf)&&qf>=0;
    MsTracePut(marker+32,timed?static_cast<unsigned>(qf):0);MsTracePut(marker+36,gQFTTimer.attemptSerial());
    MsTracePut(marker+40,GhostStageContext::generation());MsTracePut(marker+44,timed?MS_TRACE_CONTINUATION_QF_VALID:0);
    append(MS_TRACE_CONTINUATION,marker,sizeof(marker));
    if(c.fast&&!c.durable)c.phase=FORK_PUBLISHING;
    else{releaseFork();c.phase=FORK_NONE;c.fast=false;c.snapshot={};}return !s.error;
}
void cancelContinuation(){
    if(!checkpoints||checkpoints->phase==FORK_NONE)return;
    if(checkpoints->fast){stopFastContinuation();return;}auto&c=*checkpoints;c.canceled=true;
    if(c.phase==FORK_FENCE||c.phase==FORK_FAILED){releaseFork();c.phase=FORK_NONE;return;}
    if(c.phase==FORK_READY){s.ending=MS_TRACE_KEEP;c.phase=FORK_DISCARD;}
    if(c.ownsLoad)GhostCheckpoints::releaseLoad(c.pins,c.load);
}
