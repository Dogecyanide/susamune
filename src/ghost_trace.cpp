#include "susamune/ghost_provenance.h"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/state_save_probe.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_memory.hxx"
#include "susamune/ghost_trace_hooks.hxx"
#include "susamune/ghost_trace_codec.h"
#include "susamune/ghost_trace_compression.h"
#include "susamune/ghost_trace_prepare.h"
#include "susamune/warp_wheel.hxx"
#include "susamune/live_race.hxx"
#include "susamune/actions.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_race_wire.h"
#include "susamune/addresses.hxx"
#include "susamune/menu.hxx"
#include "susamune/ghost_simulation.hxx"
#include "susamune/ghost_trace_observation.h"
#include "susamune/ghost_spin_observation.hxx"
#include "susamune/iling.hxx"
#include "susamune/rng_control.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/replay_session.hxx"
#include "susamune/settings.hxx"
#include "JSystem/J3D/J3DAnimation.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/qft_timer.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/Map/BGCheck.hxx"
#include "SMS/Player/Watergun.hxx"
#include "SMS/Player/Yoshi.hxx"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/Enemy/Conductor.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/VI.h"
#include "Dolphin/mem.h"
#include "Dolphin/string.h"

#if IS_EMULATOR
namespace GhostRecordingProbe { bool install(); }
#endif
namespace GhostTrace {
namespace {
struct ContactSample {unsigned role,pointer,valid,reserved;unsigned char triangle[0x48];};
struct CameraSample {unsigned pointer,mode,child,valid;unsigned char interpolation[0x48];};
static_assert(sizeof(TBGCheckData)==0x48 && __builtin_offsetof(TBGCheckData,mNormal)==0x34,"native triangle layout");
static_assert(__builtin_offsetof(TMario,mTranslation)==0x10 && __builtin_offsetof(TMario,mRotation)==0x30,"inherited actor layout");
static_assert(__builtin_offsetof(CPolarSubCamera,mInbetween)==0x6c && __builtin_offsetof(CPolarSubCamera,mWorldTranslation)==0x124,"camera layout");
struct StageStart {unsigned words[16];unsigned char flags[0x380];unsigned npcPollutionPhase,observations;};
static_assert(sizeof(TFlagManager)==0x380 && sizeof(StageStart)==968,"stage-start schema 3");
struct State {
    unsigned magic, command, request, run, frame, tick, next, active, ending, error;
    unsigned used[2], hash[2], sealed[2], sent[2], first[2], last[2];
    unsigned records, total, peak, worstTicks, scene, actorSerial, actorCount, capabilities, attempt, worldHash, introStage;
    unsigned blobPointer[5],blobSize[5];
    MsTraceResponse response; MsTraceMetrics metrics;
    GhostSpinObservation::Queue spin;
    unsigned practiceContext[11], holdControl, heldSinceFrame, craneGeneration, craneMask;bool spinInstalled;
    GhostSimulation::Snapshot settings;
    StageStart stageStart;unsigned stageEmitted,initialScene,game,runFlags;bool waitingStage,ordinary,finishPending,publishFinish,retainedRelease;
    bool automatic,openingAutomatic;
    unsigned rngCount,rngFirst,rngLast,rngNames;unsigned rngCaller[64];unsigned char rngIndex[512];
    unsigned contactMask;ContactSample contacts[4];CameraSample cameraMeta;
    unsigned prepareHello,parentNonce,parentRun,parentChunk;unsigned char prepareKnown;
    bool inputSeen,cameraSeen,mirrorSeen;unsigned char previousMirrors[80];unsigned char previousInput[24+sizeof(TMarioGamePad)+sizeof(TMarioControllerWork)];
};
struct Actor { unsigned pointer,id,seen,size; unsigned char data[0x150], padding[32]; };
static_assert(sizeof(Actor)==384 && sizeof(Actor)*1024==MOONSHINE_GHOST_ARAM_BYTES,"charged actor cache");
static_assert(sizeof(State)<=0x1000,"trace producer ends before private replay control");
State &s=*reinterpret_cast<State*>(MS_TRACE_CONTROL_PPC+MS_TRACE_PPC_OFFSET);
volatile MsTraceMailbox &mailbox=*reinterpret_cast<volatile MsTraceMailbox*>(MS_TRACE_CONTROL_PPC);
bool bootReady;
CheckpointController*checkpoints;
void checkpointPoll();unsigned checkpointBoundary();bool sourcePinned();bool forkBlocksCapture();bool issueCheckpointFence();
bool atomicContinuationPending();
Actor *actors=reinterpret_cast<Actor*>(MS_TRACE_ACTOR_CACHE_PPC);
unsigned char *buffer(unsigned index){return reinterpret_cast<unsigned char*>(index?MS_TRACE_BUFFER1_PPC:MS_TRACE_BUFFER0_PPC);}
bool readable(const void *p,unsigned bytes) {
    const unsigned n=reinterpret_cast<unsigned>(p);return !(n&3u)&&n>=0x80000000u&&n<=0x81800000u-bytes;
}
void poll(){DCInvalidateRange((void*)&mailbox.response,64);memcpy(&s.response,(const void*)&mailbox.response,32);memcpy(&s.metrics,(const void*)&mailbox.metrics,32);}
bool automaticReply() {
    return s.command==MS_TRACE_START&&mailbox.request.operation==MS_TRACE_START&&
        mailbox.request.sequence==s.request&&mailbox.request.run==s.run&&mailbox.request.scene==s.initialScene&&
        s.response.magic==MS_TRACE_MAGIC&&s.response.version==MS_TRACE_VERSION&&
        s.response.nonce&&s.response.nonce==mailbox.request.nonce;
}
bool automaticWritable() {
    if(!automaticReply())return false;
    if(s.response.ackRequest==s.request)
        return s.response.phase==MS_TRACE_RECORDING&&!s.response.error&&!s.response.ackChunk;
    return s.response.ackRequest+1u==s.request&&
        (s.response.phase==MS_TRACE_IDLE||s.response.phase==MS_TRACE_SAVED||s.response.phase==MS_TRACE_DISCARDED);
}
void command(unsigned operation,unsigned boundary=0) {
    MsTraceRequest req={MS_TRACE_MAGIC,MS_TRACE_VERSION,s.response.nonce,++s.request,operation,s.run,operation==MS_TRACE_KEEP?s.next-1:operation==MS_TRACE_FENCE?boundary:s.scene,s.capabilities|(s.error<<24)};
    memcpy((void*)&mailbox.request,&req,32);DCStoreRange((void*)&mailbox.request,32);if(operation!=MS_TRACE_FENCE)s.command=operation;
}
void seal() {
    const unsigned i=s.active;if(!s.used[i]||s.sealed[i])return;
    s.sealed[i]=s.next++;s.active^=1u;
}
void flushRandom();void drainSpin();void contextObservation();
void stop(unsigned error) {s.error=error;s.ending=MS_TRACE_KEEP;}
void append(unsigned kind,const void *data,unsigned bytes) {
    const bool writable=s.openingAutomatic?automaticWritable():s.response.phase==MS_TRACE_RECORDING;
    if(s.waitingStage||!writable||s.ending||s.command!=MS_TRACE_START||bytes>65523)return;
    const bool irq=OSDisableInterrupts();
    if(kind!=MS_TRACE_RNG_BLOCK)flushRandom();
    if(s.ending){OSRestoreInterrupts(irq);return;}
    unsigned i=s.active;
    if(s.sealed[i]){stop(MS_TRACE_OVERFLOW);OSRestoreInterrupts(irq);return;}
    if(bytes+12>MS_TRACE_BUFFER_BYTES-s.used[i]){seal();i=s.active;}
    if(s.sealed[i]){stop(MS_TRACE_OVERFLOW);OSRestoreInterrupts(irq);return;}
    unsigned char *out=buffer(i)+s.used[i];out[0]=kind>>8;out[1]=kind;out[2]=bytes>>8;out[3]=bytes;
    MsTracePut(out+4,s.frame);MsTracePut(out+8,s.tick);if(bytes)memcpy(out+12,data,bytes);
    if(!s.used[i])s.first[i]=s.frame;s.last[i]=s.frame;
    s.hash[i]=MsTraceHash(s.hash[i],out,bytes+12);s.used[i]+=bytes+12;s.total+=bytes+12;++s.records;
    if(kind==MS_TRACE_CONTINUATION)s.runFlags|=MS_TRACE_CONTINUATION_RUN_FLAGS;
    const unsigned queued=s.used[0]+s.used[1];if(queued>s.peak)s.peak=queued;
    OSRestoreInterrupts(irq);
}
void flushRandom() {
    const bool irq=OSDisableInterrupts();
    if(!s.rngCount){OSRestoreInterrupts(irq);return;}
    unsigned char record[16+64*4+512];
    MsTracePut(record,s.rngFirst);MsTracePut(record+4,s.rngLast);
    MsTracePut(record+8,s.rngCount);MsTracePut(record+12,s.rngNames);
    for(unsigned i=0;i<s.rngNames;++i)MsTracePut(record+16+i*4,s.rngCaller[i]);
    const unsigned length=16+s.rngNames*4+s.rngCount;
    memcpy(record+16+s.rngNames*4,s.rngIndex,s.rngCount);s.rngCount=s.rngNames=0;
    append(MS_TRACE_RNG_BLOCK,record,length);OSRestoreInterrupts(irq);
}
void blob(unsigned kind,const void *p,unsigned bytes) {
    const unsigned index=kind<=MS_TRACE_FLAGS?kind-MS_TRACE_MARIO:kind-MS_TRACE_FLUDD+3;
    static const unsigned offsets[]={0,0x2000,0x4000,0x5000,0x7000};
    static const unsigned limits[]={0x2000,0x2000,0x1000,0x2000,0x1000};
    if(index>=5||bytes>limits[index]||!readable(p,bytes))return;
    unsigned char *cache=reinterpret_cast<unsigned char*>(MS_TRACE_CONTROL_PPC+0x8000u)+offsets[index];
    const unsigned pointer=reinterpret_cast<unsigned>(p);
    const bool fresh=s.blobPointer[index]!=pointer||s.blobSize[index]!=bytes;
    unsigned char record[0x220];
    for(unsigned offset=0;offset<bytes;offset+=0x200){
        const unsigned n=bytes-offset<0x200?bytes-offset:0x200;
        const auto *source=static_cast<const unsigned char*>(p)+offset;
        if(!fresh&&!memcmp(cache+offset,source,n))continue;
        MsTracePut(record,pointer);MsTracePut(record+4,offset);MsTracePut(record+8,bytes);
        const unsigned delta=fresh?0:MsTraceWordDelta(record+16,cache+offset,source,n);
        unsigned packed=16+delta;
        if(delta)MsTracePut(record+12,n|0x80000000u);
        else{MsTracePut(record+12,n);memcpy(record+16,source,n);packed=n+16;}
        append(kind,record,packed);memcpy(cache+offset,source,n);
    }
    s.blobPointer[index]=pointer;s.blobSize[index]=bytes;
}
void actor(const void *p,unsigned size) {
    if(!readable(p,size))return;
    const unsigned pointer=reinterpret_cast<unsigned>(p);unsigned index=(pointer>>4)&1023u,free=1024;
    for(unsigned n=0;n<1024;++n,index=(index+1)&1023u){
        Actor &a=actors[index];
        if(a.pointer==pointer){free=index;break;}
        if(a.pointer<=1u&&free==1024)free=index;
        if(!a.pointer)break;
    }
    if(free==1024){stop(MS_TRACE_LIMIT);return;}
    Actor &a=actors[free];if(a.pointer==pointer&&a.seen==s.frame)return;
    const bool created=a.pointer!=pointer||a.size!=size;
    if(created){a.pointer=pointer;a.id=++s.actorSerial;a.size=size;memset(a.data,0,sizeof(a.data));}
    unsigned char record[0x170];unsigned mask[3]={},at=28;
    MsTracePut(record,a.id);MsTracePut(record+4,pointer);MsTracePut(record+8,size);MsTracePut(record+12,created);
    const unsigned *words=static_cast<const unsigned*>(p);
    for(unsigned n=0;n<size/4;++n)if(created||memcmp(a.data+n*4,words+n,4)){
        mask[n/32]|=1u<<(n&31u);memcpy(record+at,words+n,4);at+=4;
    }
    for(unsigned n=0;n<3;++n)MsTracePut(record+16+n*4,mask[n]);
    if(at>28){append(MS_TRACE_ACTOR,record,at);memcpy(a.data,p,size);}
    a.seen=s.frame;++s.actorCount;s.worldHash=MsTraceHash(s.worldHash,p,size);
}
template<class Iterator> bool validNode(const Iterator &it) {
    static_assert(sizeof(Iterator)==4,"native list iterator layout");
    unsigned address;memcpy(&address,&it,4);return readable(reinterpret_cast<void*>(address),12);
}
void roster() {
    if(!readable(gpConductor,0x40))return;
    unsigned managers=0;s.actorCount=0;s.worldHash=2166136261u;
    // Enemy managers precede general managers so shared entries retain the larger prefix.
    for(unsigned list=0;list<2;++list){
        const auto &items=list?gpConductor->_10:gpConductor->_20;
        for(auto it=items.begin();it!=items.end();++it){
            if(!validNode(it)){stop(MS_TRACE_BAD_SOURCE);return;}
            if(++managers>256){stop(MS_TRACE_LIMIT);return;}
            const auto *manager=reinterpret_cast<const TLiveManager*>(*it);
            if(!readable(manager,0x38)||manager->mObjCount>2048||manager->mObjCount>manager->mMaxObjs||
                (manager->mObjCount&&!readable(manager->mObjAry,manager->mObjCount*4))){stop(MS_TRACE_BAD_SOURCE);return;}
            for(unsigned i=0;i<manager->mObjCount&&!s.ending;++i)actor(manager->mObjAry[i],list?0xf4:0x150);
        }
    }
    unsigned alone=0;
    for(auto it=gpConductor->_30.begin();it!=gpConductor->_30.end()&&!s.ending;++it){
        if(!validNode(it)){stop(MS_TRACE_BAD_SOURCE);return;}
        if(++alone>2048){stop(MS_TRACE_LIMIT);return;}actor(*it,0xf4);
    }
    for(unsigned i=0;i<1024;++i)if(actors[i].pointer>1u&&actors[i].seen!=s.frame){
        const unsigned id=actors[i].id;append(MS_TRACE_ACTOR_END,&id,4);actors[i].pointer=1;
    }
}
void contacts(TMario *mario) {
    const TBGCheckData *planes[]={mario->mWallTriangle,mario->mRoofTriangle,mario->mFloorTriangle,mario->mFloorTriangleWater};
    for(unsigned role=0;role<4;++role){
        ContactSample sample={};sample.role=role;sample.pointer=reinterpret_cast<unsigned>(planes[role]);
        if(readable(planes[role],sizeof(TBGCheckData))){sample.valid=1;memcpy(sample.triangle,planes[role],sizeof(TBGCheckData));}
        if(!(s.contactMask&(1u<<role))||memcmp(&sample,&s.contacts[role],sizeof(sample))){
            append(MS_TRACE_CONTACT,&sample,sizeof(sample));s.contacts[role]=sample;s.contactMask|=1u<<role;
        }
    }
    CameraSample sample={};sample.pointer=reinterpret_cast<unsigned>(gpCamera);sample.mode=0xffffffffu;
    if(readable(gpCamera,0x70)){
        sample.valid=1;sample.mode=*reinterpret_cast<const unsigned*>(reinterpret_cast<const unsigned char*>(gpCamera)+0x50);
        sample.child=reinterpret_cast<unsigned>(gpCamera->mInbetween);
        if(readable(gpCamera->mInbetween,0x48)){sample.valid|=2;memcpy(sample.interpolation,gpCamera->mInbetween,0x48);}
    }
    if(!s.cameraSeen||memcmp(&sample,&s.cameraMeta,sizeof(sample))){append(MS_TRACE_CAMERA_META,&sample,sizeof(sample));s.cameraMeta=sample;s.cameraSeen=true;}
}
__attribute__((noinline)) void inputMirrors() {
    static_assert(sizeof(JUTGamePad::CButton)==48&&sizeof(JUTGamePad::CStick)==16,"shared input schema 1");
    unsigned char mirror[80],record[88];
    memcpy(mirror,static_cast<const void*>(&JUTGamePad::mPadButton[0]),48);
    memcpy(mirror+48,static_cast<const void*>(&JUTGamePad::mPadMStick[0]),16);
    memcpy(mirror+64,static_cast<const void*>(&JUTGamePad::mPadSStick[0]),16);
    if(s.mirrorSeen&&!memcmp(mirror,s.previousMirrors,80))return;
    MsTracePut(record,1);MsTracePut(record+4,80);
    const unsigned packed=s.mirrorSeen?MsTraceWordDelta(record+8,s.previousMirrors,mirror,80):0;
    if(packed)append(MS_TRACE_PAD_MIRRORS_DELTA,record,packed+8);
    else {memcpy(record+8,mirror,80);append(MS_TRACE_PAD_MIRRORS,record,sizeof(record));}
    memcpy(s.previousMirrors,mirror,80);s.mirrorSeen=true;
}
__attribute__((noinline)) void inputRecord(const unsigned char *input) {
    inputMirrors();
    const unsigned bytes=sizeof(s.previousInput);
    unsigned char delta[4+sizeof(s.previousInput)];
    const unsigned packed=s.inputSeen?MsTraceWordDelta(delta+4,s.previousInput,input,bytes):0;
    if(packed){MsTracePut(delta,bytes);append(MS_TRACE_INPUT_DELTA,delta,packed+4);}
    else append(MS_TRACE_INPUT,input,bytes);
    memcpy(s.previousInput,input,bytes);s.inputSeen=true;
}
void provenance(bool force){
    if(!recording())return;
    const unsigned previous=s.runFlags;
    GhostStageContext::Sample stage;
    s32 qf=0;
    if(GhostStageContext::sample(&stage)&&gQFTTimer.currentQf(&qf)&&gQFTTimer.practiceAssisted())
        s.runFlags|=SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS;
    if(force||previous!=s.runFlags){const unsigned words[]={MS_TRACE_PROVENANCE_SCHEMA,s.runFlags};append(MS_TRACE_PROVENANCE,words,sizeof(words));}
}
void contextObservation() {
    unsigned words[11]={1,MS_OBSERVE_CONTEXT};ILing::captureTraceContext(words+2);
    words[8]=(Ghost::observerActive()?1u:0u)|(Ghost::observerPreparing()?2u:0u)|
        (ReplaySession::blocksResults()?4u:0u)|(PracticeSession::assisted()?8u:0u)|
        (gQFTTimer.practiceAssisted()?16u:0u)|(Ghost::observerStatsSuppressed()?32u:0u)|
        (gSettings.get(SETTING_FMV_SKIPS)==2?64u:0u);
    words[9]=gQFTTimer.attemptSerial();words[10]=(unsigned(gpApplication.mCurrentScene.mAreaID)<<8)|gpApplication.mCurrentScene.mEpisodeID;
    if(memcmp(words,s.practiceContext,sizeof(words))){append(MS_TRACE_OBSERVATION,words,sizeof(words));memcpy(s.practiceContext,words,sizeof(words));}
}
void controlObservation(unsigned reasons) {
    const auto*d=RetailInput::stageDirector();const unsigned state=d?d->mCurState:0xffffffffu;
    if(reasons!=s.holdControl){const unsigned words[]={1,MS_OBSERVE_CONTROL,reasons,state};append(MS_TRACE_OBSERVATION,words,sizeof(words));s.holdControl=reasons;}
}
void drainSpin() {
    if(!recording())return;
    auto&q=s.spin;if(q.error){stop(MS_TRACE_BAD_SOURCE);return;}
    for(unsigned i=0;i<q.count;++i){const auto&e=q.events[i];const unsigned words[]={1,MS_OBSERVE_SPIN,e.sequence,e.caller,e.result,e.outDir,e.valid};append(MS_TRACE_OBSERVATION,words,sizeof(words));}
    q.count=0;
}
void animationObservation() {
    unsigned words[7]={1,MS_OBSERVE_ANIMATION};const auto*d=RetailInput::stageDirector();
    auto*m=gpMarioOriginal;
    if(d&&d->_260&&OSIsThreadTerminated(&gSetupThread)&&readable(m,sizeof(TMario))&&m->mModelData){
        const auto*f=m->getMotionFrameCtrl();
        if(readable(f,sizeof(*f))&&f->mNumFrames>0){
            memcpy(words+4,&f->mCurFrame,4);memcpy(words+5,&f->mFrameRate,4);
            if((words[4]&0x7f800000u)!=0x7f800000u&&(words[5]&0x7f800000u)!=0x7f800000u){words[2]=1;words[3]=m->mAnimationID;words[6]=unsigned(f->mNumFrames);}
        }
    }
    if(!words[2])memset(words+3,0,16);
    append(MS_TRACE_OBSERVATION,words,sizeof(words));
}
void craneObservations() {
    const unsigned generation=GhostStageContext::generation();
    if(s.craneGeneration!=generation){s.craneGeneration=generation;s.craneMask=0;}
    for(unsigned i=0;i<5;++i)if(!(s.craneMask&(1u<<i))){
        unsigned words[2+RNG_TRACE_CRANE_WORDS]={1,MS_OBSERVE_CRANE};
        if(rngControlTraceCrane(i,words+2,RNG_TRACE_CRANE_WORDS)){append(MS_TRACE_OBSERVATION,words,sizeof(words));s.craneMask|=1u<<i;}
    }
}
__attribute__((noinline)) void visual() {
    unsigned char record[64];visualSample(record);
    append(MS_TRACE_VISUAL,record,sizeof(record));provenance(true);
}
void beginAttempt() {
    s.attempt=gQFTTimer.attemptSerial();s.introStage=0;
    s32 qf;
    if(!gQFTTimer.currentQf(&qf))s.introStage=GhostStageContext::generation();
}
bool sameAttempt() {
    const unsigned attempt=gQFTTimer.attemptSerial();if(attempt==s.attempt)return true;
    // The first timer start inside this captured intro is not a level restart.
    if(!s.introStage||GhostStageContext::generation()!=s.introStage)return false;
    s.attempt=attempt;s.introStage=0;return true;
}
void flushBackground() {
    if(!recording())return;
    const bool irq=OSDisableInterrupts();
    const unsigned other=s.active^1u;
    // Keep both full buffers for SD stalls, but hand off smaller ready batches
    // when the other bank is free so resets have less left to drain.
    if(s.used[s.active]>=0x20000u&&!s.used[other]&&!s.sealed[other]&&!s.sent[other])seal();
    OSRestoreInterrupts(irq);
}
void service() {
    poll();
    if(s.openingAutomatic) {
        // Both banks remain private until the writer acknowledges this exact start.
        if(!automaticReply()||s.response.ackRequest!=s.request) {
            if(!automaticWritable()&&!s.error)stop(MS_TRACE_PROTOCOL);
            return;
        }
        s.openingAutomatic=false;
        const bool ownsWriter=s.response.phase==MS_TRACE_RECORDING&&!s.response.error;
        if(!ownsWriter||s.response.ackChunk||s.ending) {
            if(!s.error&&(!ownsWriter||s.response.ackChunk))
                s.error=s.response.error?s.response.error:MS_TRACE_PROTOCOL;
            s.waitingStage=false;
            memset(s.used,0,sizeof(s.used));memset(s.sealed,0,sizeof(s.sealed));memset(s.sent,0,sizeof(s.sent));
            s.ending=ownsWriter?(s.ending==MS_TRACE_RETIRE?MS_TRACE_RETIRE:MS_TRACE_DISCARD):0;
            if(!ownsWriter)s.command=0;
            return;
        }
    }
    checkpointPoll();
    if(atomicContinuationPending())return;
    if(s.command==MS_TRACE_RETAIN&&s.request==s.response.ackRequest&&s.response.error==MS_TRACE_BUSY){
        s.retainedRelease=true;s.ending=MS_TRACE_RELEASE;command(MS_TRACE_RELEASE);return;
    }
    for(unsigned i=0;i<2;++i){
        if(s.sent[i]&&s.response.ackChunk>=s.sent[i]){s.used[i]=s.sealed[i]=s.sent[i]=0;s.hash[i]=2166136261u;}
        if(s.sealed[i]&&!s.sent[i]&&s.sealed[i]<=checkpointBoundary()){
            DCStoreRange(buffer(i),s.used[i]);MsTraceChunk c={s.run,s.sealed[i],s.used[i],s.hash[i],s.first[i],s.last[i],{0,0}};
            memcpy((void*)&mailbox.chunks[i],&c,32);DCStoreRange((void*)&mailbox.chunks[i],32);s.sent[i]=s.sealed[i];
        }
    }
    if(s.response.phase==MS_TRACE_SAVED||s.response.phase==MS_TRACE_DISCARDED){
        memset(s.used,0,sizeof(s.used));memset(s.sealed,0,sizeof(s.sealed));memset(s.sent,0,sizeof(s.sent));
    }
    if(s.response.phase==MS_TRACE_FAILED){s.error=s.response.error;if(s.ending!=MS_TRACE_DISCARD&&s.ending!=MS_TRACE_RETIRE&&s.ending!=MS_TRACE_RELEASE)return;}
    if(issueCheckpointFence()||s.request!=s.response.ackRequest)return;
    if((s.ending==MS_TRACE_DISCARD||s.ending==MS_TRACE_RETIRE||s.ending==MS_TRACE_RELEASE)&&s.run&&s.command!=s.ending){command(s.ending);return;}
    if(s.ending&&s.command==MS_TRACE_START){
        seal();
        for(unsigned i=0;i<2;++i)if(s.sealed[i]&&!s.sent[i])return;
        command(MS_TRACE_KEEP);
    }
}
}
GhostWorldWitness::Record worldSample(unsigned *scratch,unsigned slots) {
    const auto *director=RetailInput::stageDirector();
    if(!director||!director->_260||!OSIsThreadTerminated(&gSetupThread))return GhostWorldWitness::unavailable();
    return GhostWorldWitness::captureNative(reinterpret_cast<unsigned>(gpConductor),scratch,slots);
}
__attribute__((noinline)) void visualSample(unsigned char record[64]) {
    memset(record,0,64);MsTracePut(record,1);
    s32 qf=0;GhostStageContext::Sample stage;
    const bool timed=GhostStageContext::sample(&stage)&&gQFTTimer.currentQf(&qf);
    unsigned flags=timed?2u:0u;
#if TIMEWARP_LIVE_RACING
    Ghost::VisualState v={};
    if(Ghost::captureLiveVisual(&v)) {
        flags|=1u;memcpy(record+16,&v.x,12);
        MsTracePut(record+28,(unsigned(static_cast<unsigned short>(v.yaw))<<16)|v.animationId);
        MsTracePut(record+32,(unsigned(v.animationPhase)<<16)|v.heldNameKey);
        MsTracePut(record+36,v.heldObjectId);
        record[40]=v.yoshi;record[41]=v.visible;memcpy(record+44,&v.fludd,8);
    }
#endif
    MsTracePut(record+4,flags);MsTracePut(record+8,static_cast<unsigned>(qf));
    MsTracePut(record+12,(unsigned(gpApplication.mCurrentScene.mAreaID)<<8)|gpApplication.mCurrentScene.mEpisodeID);
    const auto *director=RetailInput::stageDirector();
    MsTracePut(record+52,director?director->unk58:0);
    MsTracePut(record+56,gQFTTimer.attemptSerial());
    MsTracePut(record+60,GhostStageContext::generation());

}

void init(){
    bootReady=GhostMemory::admitted();if(!bootReady)return;
    memset(&s,0,sizeof(s));s.magic=MS_TRACE_MAGIC;poll();
    if(s.response.magic!=MS_TRACE_MAGIC||s.response.version!=MS_TRACE_VERSION){bootReady=false;return;}
    DCInvalidateRange((void*)&mailbox.request,32);s.request=mailbox.request.sequence;
    if(s.response.phase==MS_TRACE_RECORDING||s.response.phase==MS_TRACE_OPENING){s.run=mailbox.request.run;command(MS_TRACE_DISCARD);}
}
#if SUSAMUNE_SAVE_PROBE
bool saveProbeIdle(){
    if(!bootReady || !GhostMemory::ready() || s.magic!=MS_TRACE_MAGIC || s.waitingStage)return false;
    poll();
    if(s.response.magic!=MS_TRACE_MAGIC || s.response.version!=MS_TRACE_VERSION || !s.response.nonce ||
       (s.response.phase!=MS_TRACE_IDLE && s.response.phase!=MS_TRACE_SAVED && s.response.phase!=MS_TRACE_DISCARDED) ||
       s.request!=s.response.ackRequest || mailbox.request.sequence!=s.request)return false;
    for(unsigned i=0;i<2;++i)
        if(s.used[i] || s.sealed[i] || s.sent[i] || mailbox.chunks[i].sequence>s.response.ackChunk)return false;
    return true;
}
#endif
bool recording(){
    if(!bootReady||s.command!=MS_TRACE_START||s.ending||s.waitingStage||s.publishFinish||forkBlocksCapture())return false;
    return s.openingAutomatic?automaticWritable():s.response.phase==MS_TRACE_RECORDING;
}
void stageSetup(unsigned area,unsigned episode,unsigned generation) {
    if(!bootReady||!GhostMemory::admitted()||s.magic!=MS_TRACE_MAGIC)return;
    if(s.ordinary&&s.waitingStage&&((area<<8)|episode)!=s.scene){stop(MS_TRACE_PROTOCOL);return;}
    if(s.waitingStage && ((area<<8)|episode)==s.scene) {
        const bool armed=stageArmed();
        if(s.openingAutomatic?!automaticWritable():!armed) {
            stop(MS_TRACE_PROTOCOL);return;
        }
        s.waitingStage=false;s.attempt=gQFTTimer.attemptSerial();s.introStage=generation;
        if(!GhostTraceHooks::setActive(recording()||GhostWorldRuntime::hooksActive())){stop(MS_TRACE_BAD_SOURCE);return;}
    }
    StageStart &sample=s.stageStart;memset(&sample,0,sizeof(sample));
    sample.words[0]=3;sample.words[1]=recording()?4u:0u;sample.words[2]=(area<<8)|episode;
    memcpy(sample.words+3,&gpApplication.mPrevScene,4);
    memcpy(sample.words+4,&gpApplication.mCurrentScene,4);
    memcpy(sample.words+5,&gpApplication.mNextScene,4);
    sample.words[6]=*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED);
    sample.words[7]=generation;sample.words[8]=sizeof(sample.flags);
    if(readable(TFlagManager::smInstance,sizeof(sample.flags))) {
        memcpy(sample.flags,TFlagManager::smInstance,sizeof(sample.flags));sample.words[1]|=1u;
    }
    const auto *heap=static_cast<const JKRSolidHeap*>(gpApplication.mCurrentHeap);
    if(readable(heap,sizeof(*heap))) {
        const unsigned start=reinterpret_cast<unsigned>(heap->mStart),end=reinterpret_cast<unsigned>(heap->mEnd);
        const unsigned head=heap->_6C,tail=heap->_70;
        if(start>=0x80000000u&&end<=0x81800000u&&start<=head&&head<=tail&&tail<=end&&heap->_68==tail-head) {
            sample.words[1]|=2u;sample.words[9]=head-start;sample.words[10]=end-tail;sample.words[11]=end-start;
        }
    }
    sample.words[12]=*reinterpret_cast<volatile const unsigned*>(0x80000000u);
    sample.words[13]=*reinterpret_cast<volatile const unsigned*>(0x80000004u);
    sample.words[14]=VIGetTvFormat();sample.words[15]=gpApplication.mCutSceneID;
    sample.npcPollutionPhase=*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_NPC_POLLUTION_PHASE);
    sample.observations=15;
    if(sample.npcPollutionPhase>=30){if(recording())stop(MS_TRACE_BAD_SOURCE);return;}
    if(recording()){
        // The last retail spin check still belongs to the departing frame.
        drainSpin();
        if(!recording())return;
        GhostSimulation::capture(s.settings);append(MS_TRACE_SESSION,&s.settings,sizeof(s.settings));
        append(MS_TRACE_STAGE_START,&sample,sizeof(sample));s.stageEmitted=generation;
    }
}

void literalCall(unsigned caller,unsigned result,unsigned seed){
    if(!recording())return;
    const bool irq=OSDisableInterrupts();flushRandom();
    unsigned char raw[12];MsTracePut(raw,caller);MsTracePut(raw+4,result);MsTracePut(raw+8,seed);
    append(MS_TRACE_RNG,raw,sizeof(raw));OSRestoreInterrupts(irq);
}
void random(unsigned caller,unsigned result,unsigned seed){
    if(!recording())return;
    const bool irq=OSDisableInterrupts();
    if(result!=((seed>>16)&32767u)){
        literalCall(caller,result,seed);
        OSRestoreInterrupts(irq);return;
    }
    if(s.rngCount && (s.rngCount==512 || seed!=s.rngLast*1103515245u+12345u))flushRandom();
    unsigned index=0;while(index<s.rngNames&&s.rngCaller[index]!=caller)++index;
    if(index==64){flushRandom();index=0;}
    if(!s.ending){
        if(index==s.rngNames)s.rngCaller[s.rngNames++]=caller;
        if(!s.rngCount)s.rngFirst=seed;
        s.rngLast=seed;s.rngIndex[s.rngCount++]=static_cast<unsigned char>(index);
    }
    OSRestoreInterrupts(irq);
}
void event(unsigned kind,const void *payload,unsigned bytes){if(recording())append(kind,payload,bytes);}
void water(const TWaterEmitInfo &info,unsigned accepted){
    if(!recording())return;
    struct Sample {unsigned accepted,source;unsigned char info[sizeof(TWaterEmitInfo)];} sample;
    sample.accepted=accepted;sample.source=reinterpret_cast<unsigned>(&info);memcpy(sample.info,static_cast<const void*>(&info),sizeof(info));
    append(MS_TRACE_WATER,&sample,sizeof(sample));
}
namespace {
volatile MsTracePrepareMailbox &prepareBox=*reinterpret_cast<volatile MsTracePrepareMailbox*>(MS_TRACE_PREPARE_PPC);
bool prepareResponse(MsTracePrepareResponse &r,unsigned *retirement=nullptr){
    if(!bootReady||!GhostMemory::admitted()||!s.response.nonce)return false;
    DCInvalidateRange((void*)&prepareBox.response,32);memcpy(&r,(const void*)&prepareBox.response,32);
    const unsigned flags=r.status&~MS_TRACE_PREPARE_ERROR_MASK;
    const bool valid=r.magic==MS_TRACE_PREPARE_MAGIC&&r.version>=MS_TRACE_PREPARE_LEGACY_VERSION&&r.version<=MS_TRACE_PREPARE_VERSION&&
        r.bootNonce==s.response.nonce&&r.phase<=MS_PREP_LINKING&&(r.phase<=MS_PREP_CONSUMED||r.version>=3)&&
        !(flags&~MS_TRACE_RETIRE_PENDING)&&(!flags||r.version>=2)&&
        (r.status&MS_TRACE_PREPARE_ERROR_MASK)<=MS_PREP_BUSY;
    if(retirement)*retirement=valid?flags:0;
    r.status&=MS_TRACE_PREPARE_ERROR_MASK;
    if(!valid||(s.prepareKnown&&s.prepareKnown!=r.version)){s.prepareHello=0;s.prepareKnown=0;}return valid;
}
unsigned captureCapabilities(){return MS_TRACE_HAS_SESSION|MS_TRACE_HAS_FRAME|MS_TRACE_HAS_MARIO|MS_TRACE_HAS_CAMERA|MS_TRACE_HAS_FLAGS|MS_TRACE_HAS_ACTOR_BASE|MS_TRACE_HAS_FLUDD|MS_TRACE_HAS_YOSHI|MS_TRACE_HAS_INPUT|MS_TRACE_HAS_WATER_REQUESTS|MS_TRACE_HAS_EXTENDED_STATE|MS_TRACE_HAS_CONTACTS|MS_TRACE_HAS_CAMERA_META|MS_TRACE_HAS_STAGE_START|MS_TRACE_HAS_VISUAL|MS_TRACE_HAS_FRAME_INPUT|MS_TRACE_HAS_PAD_MIRRORS|MS_TRACE_HAS_WORLD_WITNESS|MS_TRACE_HAS_CONTINUATION|MS_TRACE_HAS_STAGE_OWNED_CLOCK|MS_TRACE_HAS_NPC_PHASE|GhostTraceHooks::capabilities();}
void prepareRequest(unsigned op,unsigned run,unsigned sequence,unsigned version,unsigned target=0){
    const MsTracePrepareRequest q={MS_TRACE_PREPARE_MAGIC,version,s.response.nonce,sequence,op,run,op==MS_PREP_FILE?captureCapabilities():0u,target};
    memcpy((void*)&prepareBox.request,&q,32);DCStoreRange((void*)&prepareBox.request,32);
}
void preparePermit(bool allow,unsigned heldState=~0u,unsigned reasons=0,bool frozen=false){
    MsTracePrepareResponse r;unsigned retirement=0;if(!prepareResponse(r,&retirement))return;
    const auto *d=RetailInput::stageDirector();
    const unsigned queued=s.used[0]+s.used[1];
    const bool common=d&&d->_260&&OSIsThreadTerminated(&gSetupThread)&&!GhostWorldRuntime::busy()&&!GhostTraceFlat::active()&&
        !PracticeSession::freeCamera()&&queued<=MS_TRACE_PREPARE_MAX_QUEUED;
    const bool normalTime=!gSettings.get(SETTING_GAMEPLAY_SPEED)&&!actionsFastForwardActive()&&!PracticeSession::recording()&&!PracticeSession::replaying();
    allow=allow&&s.prepareKnown&&((r.phase>=MS_PREP_MKDIR&&r.phase<=MS_PREP_SYNC)||r.phase==MS_PREP_FAILED||r.phase==MS_PREP_CANCELED||r.phase==MS_PREP_LINKING||retirement)&&
        common&&LevelWarp::readyForOnlineRace()&&(!forkBlocksCapture()||fastContinuationUntracked())&&!PracticeSession::paused()&&normalTime;
    // Required graph work may progress under a stable UI or frame-advance hold.
    bool metadata=s.prepareKnown>=3&&r.version>=3&&r.phase==MS_PREP_LINKING&&continuationBackgroundPending()&&common&&heldState<=255u&&
        !(reasons&~(MS_HOLD_MENU|MS_HOLD_PRACTICE))&&(d->mCurState!=TMarDirector::STATE_STAGE_EXIT_2||frozen)&&LevelWarp::readyForStorageMaintenance(static_cast<unsigned char>(heldState))&&
        (frozen||heldState==TMarDirector::STATE_PAUSE_MENU||normalTime);
#if TIMEWARP_LIVE_RACING
    if(allow||metadata){const bool offline=!LiveRace::status().active;allow=allow&&offline;metadata=metadata&&offline;}
#endif
    MsTracePreparePermit permit={MS_TRACE_PREPARE_MAGIC,r.version,s.response.nonce,prepareBox.permit.sequence+1,
        metadata?MS_TRACE_PREPARE_METADATA_FLAG:allow?MS_TRACE_PREPARE_READY_FLAG:0u,queued,s.frame,0};
    if(!permit.sequence)permit.sequence=1;
    memcpy((void*)&prepareBox.permit,&permit,32);DCStoreRange((void*)&prepareBox.permit,32);
}
}
unsigned prepareNextRun(unsigned run){
    MsTracePrepareResponse r;if(!prepareResponse(r))return 0;
    MsTracePrepareRequest q;memcpy(&q,(const void*)&prepareBox.request,32);
    if(q.magic!=MS_TRACE_PREPARE_MAGIC||q.version!=r.version||q.bootNonce!=s.response.nonce||!q.sequence){s.prepareHello=0;s.prepareKnown=false;}
    if(!s.prepareKnown) {
        if(!s.prepareHello) {
            unsigned sequence=r.ack+1;if(!sequence||sequence==~0u)sequence=1;
            while(sequence==r.ack||sequence==q.sequence){if(++sequence==~0u||!sequence)sequence=1;}
            s.prepareHello=sequence;prepareRequest(MS_PREP_HELLO,0,sequence,r.version);return 0;
        }
        if(q.operation!=MS_PREP_HELLO||q.version!=r.version||q.sequence!=s.prepareHello||r.ack!=s.prepareHello||r.status)return 0;
        s.prepareKnown=static_cast<unsigned char>(r.version);
    }
    if(r.ack!=q.sequence)return q.operation==MS_PREP_HELLO?0u:1u;
    if(!run)return 1;
    if(r.phase==MS_PREP_LINKING)return 1;
    if(r.run==run) {
        if(r.status&&r.status!=MS_PREP_BUSY)return 3;
        if(r.phase==MS_PREP_CANCELED||r.phase==MS_PREP_CONSUMED)return 4;
        if(q.operation==MS_PREP_FILE&&q.run==run)return r.phase==MS_PREP_READY?2u:1u;
    }
    if(s.request!=s.response.ackRequest||forkBlocksCapture())return 1;
    if(q.sequence==~0u)return 0;
    if(r.run&&r.run!=run&&r.phase>=MS_PREP_MKDIR&&r.phase<=MS_PREP_READY) {
        if(r.run==s.run)return 1;
        if(!r.ownerSequence)return 3;
        prepareRequest(MS_PREP_CANCEL,r.run,q.sequence+1,r.version,r.ownerSequence);return 1;
    }
    if(r.status==MS_PREP_BUSY)return 1;
    if(r.status)return 3;
    prepareRequest(MS_PREP_FILE,run,q.sequence+1,r.version);return 1;
}
bool fastPreparedRun(unsigned run){
    MsTracePrepareResponse r;if(!run||!prepareResponse(r)||s.prepareKnown<3||r.version<3||r.phase!=MS_PREP_READY||r.status||r.run!=run)return false;
    MsTracePrepareRequest q;memcpy(&q,(const void*)&prepareBox.request,32);
    return q.magic==MS_TRACE_PREPARE_MAGIC&&q.version==r.version&&q.bootNonce==s.response.nonce&&q.operation==MS_PREP_FILE&&
        q.run==run&&q.sequence==r.ack&&r.ownerSequence==q.sequence&&q.capabilities==captureCapabilities();
}
unsigned discardOperation(){
    MsTracePrepareResponse r;
    return s.ordinary&&!s.error&&prepareResponse(r)&&s.prepareKnown>=2&&r.version>=2?MS_TRACE_RETIRE:MS_TRACE_DISCARD;
}
unsigned retainOperation(){
    MsTracePrepareResponse r;return prepareResponse(r)&&s.prepareKnown>=3&&r.version>=3?MS_TRACE_RETAIN:MS_TRACE_KEEP;
}
void revokePreparation(){preparePermit(false);}
void reset(){
    revokePreparation();
    if(!bootReady||!GhostMemory::admitted()||s.magic!=MS_TRACE_MAGIC||s.publishFinish)return;
    drainSpin();
    // A failed writer cannot finish. Close it without deleting a possible checkpoint prefix.
    if(s.response.phase==MS_TRACE_FAILED&&s.command)s.ending=MS_TRACE_RELEASE;
    else if(s.command==MS_TRACE_START)s.ending=sourcePinned()?retainOperation():discardOperation();
}
__attribute__((noinline)) bool initializeCapture(unsigned run,unsigned scene,bool waitForStage) {
    const unsigned request=s.request,nonce=s.response.nonce,hello=s.prepareHello;const unsigned char known=s.prepareKnown;
    if(!GhostSpinObservation::uninstall())return false;
    const bool automaticContinuation=!waitForStage&&s.automatic&&forkBlocksCapture()&&
        checkpoints->snapshot.prefix.run==s.run&&checkpoints->snapshot.prefix.nonce==nonce;
    StageStart initial=s.stageStart;initial.words[1]&=~4u;initial.observations|=8u;
    memset(&s,0,sizeof(s));s.magic=MS_TRACE_MAGIC;s.stageStart=initial;
    s.request=request;s.response.nonce=nonce;s.run=run;s.prepareHello=hello;s.prepareKnown=known;
    s.scene=s.initialScene=scene;s.waitingStage=waitForStage;s.automatic=automaticContinuation;s.game=*reinterpret_cast<volatile const unsigned*>(0x80000000u);
    s.capabilities=captureCapabilities();s.next=1;s.hash[0]=s.hash[1]=2166136261u;
    memset(actors,0,MOONSHINE_GHOST_ARAM_BYTES);
    memset((void*)&mailbox.chunks,0,sizeof(mailbox.chunks));DCStoreRange((void*)&mailbox.chunks,64);
    return true;
}
__attribute__((noinline)) bool startCapture(unsigned run,unsigned scene,bool waitForStage) {
    revokePreparation();
    if(GhostTraceFlat::active()||StateSaveProbe::enabled()||!run||scene>0xffffu||!bootReady||!GhostMemory::ready()||GhostWorldRuntime::busy())return false;
    poll();
    if((s.response.phase!=MS_TRACE_IDLE&&s.response.phase!=MS_TRACE_SAVED&&s.response.phase!=MS_TRACE_DISCARDED)||
       s.request!=s.response.ackRequest)return false;
    if(!initializeCapture(run,scene,waitForStage))return false;
    command(MS_TRACE_START);return true;
}
__attribute__((noinline)) bool armStage(unsigned scene,unsigned run) {return startCapture(run,scene,true);}
__attribute__((noinline)) bool stageArmed() {
    if(!bootReady||!GhostMemory::admitted())return false;
    poll();return s.waitingStage&&s.response.phase==MS_TRACE_RECORDING&&s.response.ackRequest==s.request;
}
bool backendIdentity(unsigned &nonce) {
    if(!bootReady||!GhostMemory::ready())return false;poll();
    if(s.response.magic!=MS_TRACE_MAGIC||s.response.version!=MS_TRACE_VERSION||!s.response.nonce)return false;
    nonce=s.response.nonce;return true;
}
bool armOrdinaryStage(unsigned scene,unsigned run) {
    if(!armStage(scene,run))return false;s.ordinary=true;return true;
}
bool armAutomaticStage(unsigned scene,unsigned run) {
    if(!bootReady||!GhostMemory::ready())return false;
    poll();
    // A cold open can contend with the disc load. Only consume a prepared file.
    if(!fastPreparedRun(run)||!startCapture(run,scene,true))return false;
    s.ordinary=s.automatic=s.openingAutomatic=true;
    return true;
}
bool automaticStartPending(){return bootReady&&s.openingAutomatic;}
unsigned ownedRun(){return bootReady?s.run:0;}
unsigned failure(unsigned run){if(!bootReady||s.run!=run)return 0;poll();
    if(s.openingAutomatic)return s.error;
    if(s.retainedRelease&&s.command==MS_TRACE_RELEASE&&s.request!=s.response.ackRequest&&s.response.error==MS_TRACE_BUSY)return 0;
    return s.error?s.error:s.response.error;}
bool finishOrdinary(unsigned run) {
    if(s.openingAutomatic||!s.ordinary||s.run!=run||!recording())return false;
    drainSpin();contextObservation();provenance(true);
    flushRandom();
    if(continuationPublicationPending()){seal();s.publishFinish=true;return true;}
    s.ending=MS_TRACE_KEEP;return true;
}
bool queueOrdinaryFinish(unsigned run) {
    if(s.openingAutomatic||!s.ordinary||s.run!=run||!recording()||s.finishPending)return false;
    s.finishPending=true;return true;
}
void flushOrdinaryFinish() {
    if(s.publishFinish){if(!continuationPublicationPending()){s.publishFinish=false;s.ending=MS_TRACE_KEEP;}return;}
    if(s.finishPending){s.finishPending=false;finishOrdinary(s.run);}
}
bool discarded(unsigned run){if(!bootReady||s.run!=run)return false;
    if(s.automatic&&!s.openingAutomatic&&!s.command&&s.error)return true;
    poll();return (s.command==MS_TRACE_DISCARD||s.command==MS_TRACE_RETIRE||s.command==MS_TRACE_RETAIN||s.command==MS_TRACE_RELEASE)&&s.response.phase==MS_TRACE_DISCARDED&&s.response.ackRequest==s.request;}
bool retainedFile(unsigned run){if(!bootReady||s.run!=run||s.openingAutomatic||!s.command)return false;poll();return s.response.phase==MS_TRACE_SAVED||
    ((s.command==MS_TRACE_RETAIN||s.retainedRelease)&&s.response.phase==MS_TRACE_DISCARDED&&s.request==s.response.ackRequest);}
unsigned completedRunFlags(unsigned run){return bootReady&&s.run==run?s.runFlags:0;}
bool completion(unsigned run,Completion &out) {
    if(!bootReady||!s.ordinary||s.run!=run||continuationPublicationPending())return false;poll();
    if(s.command!=MS_TRACE_KEEP||s.response.phase!=MS_TRACE_SAVED||s.response.ackRequest!=s.request||s.error||s.response.error||!s.frame||s.response.bytes<96)return false;
    unsigned char header[64]={},footer[32]={};
    const unsigned game=*reinterpret_cast<volatile const unsigned*>(0x80000000u);
    MsTracePut(header,MS_TRACE_MAGIC);MsTracePut(header+4,MS_TRACE_FILE_VERSION);MsTracePut(header+8,64);
    MsTracePut(header+12,game);MsTracePut(header+16,s.response.nonce);MsTracePut(header+20,s.run);
    MsTracePut(header+24,s.initialScene);MsTracePut(header+28,s.capabilities);MsTracePut(header+32,MS_TRACE_BUFFER_BYTES);
    if(s.parentRun){MsTracePut(header+36,MS_TRACE_CONTINUATION_RUN_FLAGS);MsTracePut(header+40,MS_TRACE_PROVENANCE_TAG);
        MsTracePut(header+44,MS_TRACE_BRANCH_HEADER_TAG);MsTracePut(header+48,s.parentNonce);MsTracePut(header+52,s.parentRun);MsTracePut(header+56,s.parentChunk);}
    MsTracePut(footer,0x444f4e45u);MsTracePut(footer+4,s.run);MsTracePut(footer+8,s.response.ackChunk);
    MsTracePut(footer+12,s.response.bytes-32);MsTracePut(footer+16,s.capabilities);
    MsTracePut(footer+20,s.metrics.reserved[0]);MsTracePut(footer+24,s.metrics.reserved[1]);MsTracePut(footer+28,s.metrics.reserved[3]);
    out={s.response.nonce,s.run,game,s.response.bytes,s.response.ackChunk,s.frame,s.capabilities,
        MsTraceHash(2166136261u,header,60),MsTraceHash(2166136261u,footer,32)};return true;
}
#include "ghost_trace_producer.inc"
bool receive(LiveRaceSession::Session &session,const void *data,unsigned bytes) {
    if(bytes!=16||!session.info.connected||strcmp(session.info.remoteName,"Memory monitor"))return false;
    const unsigned char *p=static_cast<const unsigned char*>(data);if(MSRRead32(p)!=0x4d4d5131u)return false;
    const unsigned op=MSRRead32(p+8);
#if IS_EMULATOR
    if(op==11)return GhostRecordingProbe::install();
    if(op==6)return GhostWorldRuntime::arm(MSRRead32(p+12));
    if(op==7){GhostWorldRuntime::stop();return true;}
    if(op==8){GhostWorldRuntime::status(reinterpret_cast<unsigned*>(MS_TRACE_CONTROL_PPC+0x3000));return true;}
#endif
    if(op==9) {
        if(!bootReady||!GhostMemory::ready())return true;
        poll();
        const unsigned entry=MSRRead32(p+12),game=*reinterpret_cast<volatile const unsigned*>(0x80000000u);
        if(s.command==MS_TRACE_KEEP&&s.response.phase==MS_TRACE_SAVED&&s.response.ackRequest==s.request&&entry&&entry<=0x7fffffffu) {
            const unsigned region=game==0x474d534au?1u:game==0x474d5345u?2u:3u;
            if(GhostWorldRuntime::armFile(s.response.nonce,s.run,region)&&!GhostWorldRuntime::startAt(int(entry-1)))GhostWorldRuntime::stop();
        }
        return true;
    }
    if(op==10){GhostWorldRuntime::stop();return true;}
    if(op<3||op>5)return false;
    if(!bootReady||!GhostMemory::ready())return true;
    poll();
    if(s.response.magic!=MS_TRACE_MAGIC||s.response.version!=MS_TRACE_VERSION||!s.response.nonce)return true;
    if(op==3&&(MSRRead32(p+12)&0x80000000u)) {
        const unsigned destination=MSRRead32(p+12);
        return !(destination&0x7fff0000u)&&armStage(destination&0xffffu,MSRRead32(p+4));
    }
    if(op==3){
        if((s.response.phase!=MS_TRACE_IDLE&&s.response.phase!=MS_TRACE_SAVED&&s.response.phase!=MS_TRACE_DISCARDED)||s.request!=s.response.ackRequest)return true;
        if(startCapture(MSRRead32(p+4),(unsigned(gpApplication.mCurrentScene.mAreaID)<<8)|gpApplication.mCurrentScene.mEpisodeID,false)&&gMenu)
            gMenu->toast("Starting SD ghost trace...");
    }else if(op==5&&s.run){drainSpin();contextObservation();provenance(true);s.ending=sourcePinned()?MS_TRACE_KEEP:discardOperation();}
    else if(op==4&&s.command==MS_TRACE_START&&s.response.phase==MS_TRACE_RECORDING){drainSpin();contextObservation();provenance(true);flushRandom();s.ending=MS_TRACE_KEEP;}
    return true;
}
void frame(unsigned *worldScratch,unsigned worldSlots) {
    if(!bootReady||!GhostMemory::admitted()||s.magic!=MS_TRACE_MAGIC)return;
    drainSpin();
    // ARAM is acquired only after stage setup; idle boot has no attempt to cancel.
    if(!GhostMemory::ready()&&s.run&&s.command==MS_TRACE_START)s.ending=sourcePinned()?MS_TRACE_KEEP:discardOperation();
    const unsigned oldPhase=s.response.phase;
    const bool automaticSetupCaptured=s.automatic&&!s.waitingStage;
    flushOrdinaryFinish();flushRandom();flushBackground();service();
    if(!GhostTraceHooks::setActive(recording()||GhostWorldRuntime::hooksActive())){stop(MS_TRACE_BAD_SOURCE);service();return;}
    if(oldPhase!=MS_TRACE_RECORDING&&s.response.phase==MS_TRACE_RECORDING){if(!automaticSetupCaptured)beginAttempt();if(gMenu&&!s.ordinary)gMenu->toast("SD ghost trace recording");}
    if(recording()&&s.frame&&!s.automatic&&!sameAttempt()){reset();service();return;}
    if(oldPhase!=MS_TRACE_SAVED&&s.response.phase==MS_TRACE_SAVED&&gMenu&&!s.ordinary)gMenu->toast("SD ghost trace saved");
    if(!recording()){if(!GhostWorldRuntime::busy()&&GhostSpinObservation::uninstall(GhostSpinObservation::RECORD))s.spinInstalled=false;return;}
    if(!s.spinInstalled){if(!GhostSpinObservation::install(s.spin,GhostSpinObservation::RECORD)){stop(MS_TRACE_BAD_SOURCE);return;}s.spinInstalled=true;}
    const unsigned before=OSGetTick();flushRandom();++s.frame;
    if(s.stageStart.words[7]&&s.stageStart.words[7]!=s.stageEmitted) {
        append(MS_TRACE_STAGE_START,&s.stageStart,sizeof(s.stageStart));s.stageEmitted=s.stageStart.words[7];
    }
    const unsigned scene=(unsigned(gpApplication.mCurrentScene.mAreaID)<<8)|gpApplication.mCurrentScene.mEpisodeID;
    if(scene!=s.scene){s.scene=scene;s.contactMask=0;s.inputSeen=s.cameraSeen=s.mirrorSeen=false;memset(actors,0,MOONSHINE_GHOST_ARAM_BYTES);memset(s.blobPointer,0,sizeof(s.blobPointer));}
    unsigned words[8]={scene,unsigned(gpApplication.mContext),VIGetRetraceCount(),OSGetTick(),
        *reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED),s.tick,0,0};
    const TMarDirector *director=RetailInput::stageDirector();
    words[6]=director?director->mCurState:0xffffffffu;words[7]=gMenu&&gMenu->shown()?1u:0u;
    if(director&&director->_260)words[7]|=2u;
    if(director&&OSIsThreadTerminated(&gSetupThread))words[7]|=4u;
    if(s.heldSinceFrame)words[7]|=8u;s.heldSinceFrame=0;
    append(MS_TRACE_FRAME,words,sizeof(words));visual();contextObservation();animationObservation();craneObservations();
    unsigned char worldRecord[GhostWorldWitness::kWireBytes];
    GhostWorldWitness::encode(worldRecord,worldSample(worldScratch,worldSlots));
    append(MS_TRACE_WORLD_WITNESS,worldRecord,sizeof(worldRecord));
    if(director&&director->_260){
        blob(MS_TRACE_CAMERA,gpCamera,0x350);
        blob(MS_TRACE_FLAGS,TFlagManager::smInstance,sizeof(TFlagManager));
        if(readable(gpMarioOriginal,0x400)){
            blob(MS_TRACE_FLUDD,gpMarioOriginal->mFludd,sizeof(TWaterGun));
            blob(MS_TRACE_YOSHI,gpMarioOriginal->mYoshi,sizeof(TYoshi));
        }
        roster();
        unsigned summary[2]={s.actorCount,s.worldHash};append(MS_TRACE_WORLD_SUMMARY,summary,sizeof(summary));
    }
    GhostSimulation::Snapshot settings;
GhostSimulation::capture(settings);
    if(s.frame==1||memcmp(&settings,&s.settings,sizeof(settings))){append(MS_TRACE_SESSION,&settings,sizeof(settings));s.settings=settings;}
    if(s.frame==1){unsigned identity[4]={*reinterpret_cast<volatile const unsigned*>(0x80000000u),*reinterpret_cast<volatile const unsigned*>(0x80000004u),MS_TRACE_VERSION,SUSAMUNE_GAME_VERSION};append(MS_TRACE_IDENTITY,identity,sizeof(identity));}
    const unsigned elapsed=OSGetTick()-before;if(elapsed>s.worstTicks)s.worstTicks=elapsed;
}
GhostSpinObservation::Queue &spinQueue(){return s.spin;}
void practiceAction(){if(recording()){s.runFlags|=SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS;provenance(true);contextObservation();}}
void noteHold(unsigned reasons){if(recording()){s.heldSinceFrame=1;controlObservation(reasons|MS_HOLD_GAME_MODE);}}
void directInput(bool frozen,bool suppressed,unsigned reasons,unsigned heldState) {
    preparePermit(!frozen&&!suppressed&&!reasons,heldState,reasons,frozen);
    if(!recording())return;
    if(frozen)s.heldSinceFrame=1;
    controlObservation((frozen?(reasons|MS_HOLD_DIRECT):0u)|(suppressed?MS_HOLD_INPUT:0u));
    provenance(false);
    unsigned char input[sizeof(s.previousInput)]={};
    MsTracePut(input+4,0x80000000u|(frozen?1u:0u)|(suppressed?2u:0u));
    memcpy(input+8,&JUTGamePad::mPadStatus[0],11);
    const auto *pad=gpApplication.mGamePads[0];
    if(readable(pad,sizeof(TMarioGamePad))) {
        memcpy(input+24,static_cast<const void*>(pad),sizeof(TMarioGamePad));MsTracePut(input+20,1);
    }
    inputRecord(input);
}
void movement(TMario *mario,unsigned cue) {
    if(!recording()||!GhostMemory::ready()||!(cue&1u)||mario!=gpMarioOriginal)return;
    drainSpin();provenance(false);
    const unsigned before=OSGetTick();flushRandom();++s.tick;
    // Observed before retail Mario::perform, not a synthetic PAD sample.
    unsigned char input[24+sizeof(TMarioGamePad)+sizeof(TMarioControllerWork)]={};
    MsTracePut(input,cue);MsTracePut(input+4,0);
    memcpy(input+8,&JUTGamePad::mPadStatus[0],11);
    if(readable(mario,sizeof(TMario))){
        unsigned valid=0;
        if(readable(mario->mController,sizeof(TMarioGamePad))){memcpy(input+24,static_cast<const void*>(mario->mController),sizeof(TMarioGamePad));valid|=1;}
        if(readable(mario->mControllerWork,sizeof(TMarioControllerWork))){memcpy(input+24+sizeof(TMarioGamePad),mario->mControllerWork,sizeof(TMarioControllerWork));valid|=2;}
        MsTracePut(input+20,valid);
    }
    inputRecord(input);
    if(readable(mario,0xe8))contacts(mario);
    blob(MS_TRACE_MARIO,mario,0x574);blob(MS_TRACE_CAMERA,gpCamera,0x350);
    const unsigned elapsed=OSGetTick()-before;if(elapsed>s.worstTicks)s.worstTicks=elapsed;
}
void status(unsigned *out) {
    if(!bootReady||!GhostMemory::admitted()){memset(out,0,44);out[1]=MS_TRACE_NO_STORAGE;return;}
    out[0]=s.response.phase;out[1]=s.error?s.error:s.response.error;out[2]=s.total;out[3]=s.response.bytes;
    out[4]=s.used[0]+s.used[1];out[5]=s.peak;out[6]=s.records;const unsigned bus=*reinterpret_cast<volatile const unsigned*>(0x800000f8u);
    out[7]=bus?static_cast<unsigned>((static_cast<unsigned long long>(s.worstTicks)*4000000u)/bus):0;
    out[8]=s.metrics.maxWriteTicks;out[9]=s.frame;out[10]=s.capabilities;
}
}
#endif
