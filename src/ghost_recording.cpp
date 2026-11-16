#include "susamune/ghost_recording_native.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost.hxx"
#include "susamune/warp_wheel.hxx"
#include "SMS/System/GameSequence.hxx"

namespace GhostRecording {
static_assert(MS_TRACE_CONTINUATION_RUN_FLAGS==(SUSAMUNE_GHOST_RUN_ASSISTED|SUSAMUNE_GHOST_RUN_TAS|SUSAMUNE_GHOST_RUN_SAVESTATE_USED),"continuation flags");
namespace {
using namespace GhostRecordingLifecycle;
Runtime *runtime;
const char *status="Ghost recording unavailable";
unsigned text(unsigned char*out,const char*in,unsigned cap){unsigned n=0;while(n<cap&&in&&in[n]){const unsigned char c=in[n];if(c<32||c>126||c=='/'||c==92)break;out[n++]=c;}for(unsigned i=n;i<cap;++i)out[i]=0;return n;}
Draft *selected(){
    if(!runtime)return nullptr;
    unsigned value=runtime->saveOwner;
    if(!value){
        if(Draft*d=selection(runtime->state))return d;
        value=runtime->previousAutomatic;
    }
    Draft*d=find(runtime->state,value);
    return d&&(d->phase==READY||d->phase==FINALIZING)?d:nullptr;
}
bool playable(unsigned scene){
    const unsigned area=scene>>8;
    return area<=SUSAMUNE_GHOST_ROUTE_AREA_MAX &&
           (scene&255)<=SUSAMUNE_GHOST_ROUTE_EPISODE_MAX &&
           area!=TGameSequence::AREA_OPTION &&
           (area<TGameSequence::AREA_NONE||area>TGameSequence::AREA_TEST10);
}
unsigned course(unsigned area){
    const unsigned parent=LevelWarp::parentArea(area);
    return parent==255?area:parent;
}
bool sameCourseHop(unsigned from,unsigned to){
    return (from>>8)!=(to>>8)&&playable(to)&&course(from>>8)==course(to>>8);
}
bool evictable(const Draft&d){
    return d.phase==READY&&!d.pbToken&&!d.references&&d.token!=runtime->saveToken&&
           d.token!=runtime->saveOwner;
}
void stopUnrecorded(){
    if(!runtime)return;
    Draft*d=active(runtime->state);
    if(!d||d->phase!=FINALIZING)GhostTrace::stopFastContinuation();
    if(d&&(d->phase==CAPTURING||d->phase==ARMING))failed(runtime->state,d->identity,MS_TRACE_BUSY);
    runtime->unrecorded=true;runtime->continuationToken=0;runtime->lastLoadRecorded=false;
    status="Ghost recording stopped; storage busy";
}
void stamp(Draft&d,const Info&i,unsigned flags){
    unsigned char*p=d.manifest;__builtin_memset(p,0,256);MsRecordingPut(p,MS_RECORDING_MANIFEST_MAGIC);p[5]=1;p[6]=1;
    MsRecordingPut(p+8,256);MsRecordingPut(p+28,flags);p[38]=i.sourceProfile;p[39]=MS_RECORDING_MODE;p[40]=MS_RECORDING_CODEC;p[43]=4;
    p[44]=i.area;p[45]=i.episode;p[46]=i.parent;p[47]=i.routeFlags;MsRecordingPut(p+48,static_cast<unsigned>(i.routeVariant));
    MsRecordingPut(p+52,i.resultQf);MsRecordingPut(p+56,i.startQf);MsRecordingPut(p+60,i.endQf);MsRecordingPut(p+64,i.endQf-i.startQf);
    p[93]=static_cast<unsigned char>(text(p+120,i.name,48));p[95]=1;MsRecordingPut(p+240,d.token);
    if(i.splitCount){MsRecordingPut(p+184,i.splits[0].schema);p[188]=i.splits[0].route>>8;p[189]=i.splits[0].route;p[190]=i.splitCount;
        for(unsigned n=0;n<i.splitCount;++n)MsRecordingPut(p+192+n*4,i.splits[n].qf);}
}
}
bool install(Runtime&r,unsigned nonce,unsigned capabilities,const Backend&backend){
    if(runtime||!nonce||(capabilities&kRequired)!=kRequired||!backend.load||!backend.checkpoint||!backend.discardRetained)return false;
    unsigned liveNonce=0;if(!GhostTrace::backendIdentity(liveNonce)||liveNonce!=nonce)return false;
    r={};if(!GhostTrace::installCheckpoints(r.checkpoints))return false;init(r.state,nonce,capabilities);r.backend=backend;runtime=&r;status="Ghost recording ready";return true;
}
bool enabled(){return runtime&&GhostRecordingLifecycle::enabled(runtime->state);}
bool ownsSession(){return enabled()&&runtime->session;}
bool capturing(){const Draft*d=runtime?active(runtime->state):nullptr;return d&&d->phase==CAPTURING;}
bool activeIdentity(Identity &id,unsigned &owner){
    const Draft*d=runtime?active(runtime->state):nullptr;
    if(!d||d->phase!=CAPTURING)return false;id=d->identity;owner=d->token;return true;
}
bool discardHeaderHash(Identity id,unsigned &hash){
    if(!enabled())return false;
    for(unsigned i=0;i<kDrafts;++i){const Draft&d=runtime->state.drafts[i];
        if(d.phase==DISCARDING&&same(d.identity,id)&&same(d.completion.identity,id)&&d.completion.bytes>=96&&d.completion.frames){
            hash=d.completion.headerHash;return true;
        }
    }return false;
}
bool protectedToken(unsigned value){
    const Draft*d=runtime?find(runtime->state,value):nullptr;
    return d&&d->pbToken==value&&(d->phase==FINALIZING||d->phase==READY||d->phase==SAVING);
}
bool copyProtectedName(char*out,unsigned cap,unsigned*value){
    if(value)*value=0;if(!runtime||!out||!cap)return false;out[0]=0;
    for(unsigned n=0;n<kDrafts;++n){const Draft&d=runtime->state.drafts[n];
        if(!d.pbToken||!protectedToken(d.pbToken)||cap<=d.manifest[93])continue;
        __builtin_memcpy(out,d.manifest+120,d.manifest[93]);out[d.manifest[93]]=0;
        if(value)*value=d.pbToken;return true;
    }
    return false;
}
void warmNextRun(){
    if(runtime->state.reservedRun==GhostTrace::ownedRun())runtime->state.reservedRun=0;
    if(runtime->warmDisabled||GhostTrace::continuationPending()||!GhostTrace::prepareNextRun(0))return;
    const unsigned run=reserveRun(runtime->state);if(!run)return;
    const unsigned phase=GhostTrace::prepareNextRun(run);
    if(phase==3||phase==4){runtime->state.reservedRun=0;if(phase==3)runtime->warmDisabled=true;}
}
void poll(){
    GhostRecordingNative::poll();
    if(!enabled())return;
    if(GhostTrace::fastContinuationUntracked()&&!runtime->unrecorded)stopUnrecorded();
    if(runtime->unrecorded&&!GhostTrace::continuationPending()&&(GhostTrace::discarded(GhostTrace::ownedRun())||GhostTrace::retainedFile(GhostTrace::ownedRun())))runtime->unrecorded=false;
    State&s=runtime->state;Draft*d=GhostTrace::continuationPending()?nullptr:active(s);
    if(d&&(d->phase==ARMING||d->phase==CAPTURING||d->phase==FINALIZING)&&
       (GhostTrace::ownedRun()!=d->identity.run||GhostTrace::failure(d->identity.run)||GhostTrace::discarded(d->identity.run))){if(GhostTrace::ownedRun()==d->identity.run)GhostTrace::reset();failed(s,d->identity,1);status="Ghost recording failed";d=nullptr;}
    if(d&&d->phase==ARMING&&GhostTrace::ownedRun()==d->identity.run&&
       GhostTrace::recording()&&!GhostTrace::automaticStartPending())captured(s,d->identity);
    if(d&&d->phase==FINALIZING){GhostTrace::Completion c;
        if(GhostTrace::completion(d->identity.run,c)){
            Completion value={{c.nonce,c.run},c.bytes,c.chunks,c.frames,c.capabilities,c.headerHash,c.footerHash};
            if(completed(s,value)){
                MsRecordingPut(d->manifest+28,MsRecordingWord(d->manifest+28)|GhostTrace::completedRunFlags(c.run));
                MsRecordingPut(d->manifest+16,c.nonce);MsRecordingPut(d->manifest+20,c.run);MsRecordingPut(d->manifest+24,c.capabilities);
                MsRecordingPut(d->manifest+32,c.game);d->manifest[37]=c.game==SUSAMUNE_GHOST_GAME_ID_JP?0:c.game==SUSAMUNE_GHOST_GAME_ID_US?1:2;
                MsRecordingPut(d->manifest+68,c.frames);MsRecordingPut(d->manifest+84,c.nonce);MsRecordingPut(d->manifest+88,c.run);
                MsRecordingPut(d->manifest+224,c.bytes);MsRecordingPut(d->manifest+228,c.chunks);MsRecordingPut(d->manifest+232,c.headerHash);MsRecordingPut(d->manifest+236,c.footerHash);
                status="Ghost ready to save";
            }
        }
    }
    for(unsigned n=0;n<kDrafts;++n){Draft&draft=s.drafts[n];if(draft.phase!=DISCARDING)continue;
        if(GhostTrace::checkpointSourceOwned(draft.identity.nonce,draft.identity.run)){
            if(draft.completion.bytes||GhostTrace::retainedFile(draft.identity.run))discarded(s,draft.identity);continue;
        }
        if(GhostTrace::ownedRun()==draft.identity.run&&!draft.completion.bytes&&!GhostTrace::retainedFile(draft.identity.run)){
            if(GhostTrace::discarded(draft.identity.run))discarded(s,draft.identity);
        }else{const bool begin=(runtime->discardIssued&(1u<<n))==0;const int result=runtime->backend.discardRetained(draft.identity,begin);runtime->discardIssued|=1u<<n;
            if(result>0){discarded(s,draft.identity);runtime->discardIssued&=~(1u<<n);}else if(result<0){failed(s,draft.identity,1);status="Could not discard ghost";}}
    }
    warmNextRun();
}
Gate beforeDeparture(unsigned scene,bool selectedIL){
    GhostTrace::revokePreparation();
    if(GhostTraceFlat::active())return DEPART_WAIT;
    if(!enabled()||Ghost::observerPreparing()||Ghost::observerStatsSuppressed())return DEPART_READY;
    if(GhostWorldRuntime::busy())return GhostWorldRuntime::active()?DEPART_READY:DEPART_WAIT;
    if(runtime->automatic){
        if(!selectedIL)return DEPART_READY;
        automaticDeparture(~0u);
    }
    if(GhostTrace::continuationBackgroundPending())stopUnrecorded();
    if(runtime->unrecorded||GhostTrace::fastContinuationUntracked())return DEPART_READY;
    if(GhostTrace::continuationPending())return DEPART_WAIT;
    poll();
    if(!selectedIL&&(!runtime->session||scene!=runtime->scene))return DEPART_READY;
    Draft*d=active(runtime->state);
    if(d){
        if(d->phase==ARMING&&runtime->scene==scene&&GhostTrace::stageArmed()){runtime->waitFrames=0;return DEPART_READY;}
        if(d->phase==CAPTURING){status="Finishing previous ghost";return DEPART_WAIT;}
        if(++runtime->waitFrames<900)return DEPART_WAIT;
        status="Ghost storage timed out; departure canceled";cancelActive();return DEPART_REFUSED;
    }
    d=arm(runtime->state);
    if(!d){
        Draft *oldest=nullptr;
        for(unsigned n=0;n<kDrafts;++n){Draft &candidate=runtime->state.drafts[n];
            if(candidate.phase==DISCARDING){
                if(++runtime->waitFrames<900)return DEPART_WAIT;
                status="Ghost storage timed out; departure canceled";return DEPART_REFUSED;
            }
            if(evictable(candidate)&&(!oldest||candidate.token<oldest->token))oldest=&candidate;
        }
        if(oldest&&beginDiscard(runtime->state,oldest->token)){
            runtime->waitFrames=0;status="Retiring previous attempt";return DEPART_WAIT;
        }
        status="Save or discard a ghost first";return DEPART_REFUSED;
    }
    runtime->scene=scene;runtime->session=true;runtime->waitFrames=0;
    runtime->automatic=false;runtime->previousAutomatic=0;
    if(!GhostTrace::armOrdinaryStage(scene,d->identity.run)){failed(runtime->state,d->identity,1);status="Ghost storage is not ready";return DEPART_REFUSED;}
    status="Preparing ghost recording";return DEPART_WAIT;
}
bool automaticCapture(){return runtime&&runtime->automatic;}
void automaticDeparture(unsigned nextScene){
    if(!automaticCapture()||sameCourseHop(runtime->scene,nextScene))return;
    const Draft*d=active(runtime->state);
    if(!d||(d->phase!=ARMING&&d->phase!=CAPTURING))return;
    if(GhostTrace::continuationBackgroundPending())stopUnrecorded();
    else cancelActive();
}
void automaticStageSetup(unsigned scene){
    if(!enabled()||!playable(scene)||GhostWorldRuntime::busy()||
       Ghost::observerPreparing()||Ghost::observerStatsSuppressed()||GhostTraceFlat::active())return;
    State&s=runtime->state;
    if(Draft*d=active(s)){
        if(!runtime->automatic)return;
        if((d->phase==ARMING||d->phase==CAPTURING)&&sameCourseHop(runtime->scene,scene)){
            runtime->scene=scene;
            return;
        }
        automaticDeparture(scene);
        if(d->phase!=DISCARDING||!GhostTrace::discarded(d->identity.run))return;
        discarded(s,d->identity);
    }
    const unsigned run=s.reservedRun;
    if(!run||runtime->unrecorded||GhostTrace::continuationPending())return;
    Draft*previous=selection(s);
    if(!previous)previous=find(s,runtime->previousAutomatic);
    const unsigned previousToken=previous&&previous->phase==READY?previous->token:0;
    Draft*d=arm(s);
    if(!d){
        Draft*oldest=nullptr;
        for(Draft&candidate:s.drafts)
            if(evictable(candidate)&&candidate.token!=previousToken&&
               (!oldest||candidate.token<oldest->token))oldest=&candidate;
        if(oldest)beginDiscard(s,oldest->token);
        return;
    }
    if(!GhostTrace::armAutomaticStage(scene,run)){
        // No START was posted. Keep the warm identity and current save choice.
        d->phase=EMPTY;s.active=kNone;--s.serial;s.reservedRun=run;
        return;
    }
    runtime->scene=scene;runtime->automatic=runtime->session=true;runtime->waitFrames=0;
    runtime->previousAutomatic=previousToken;
    status="Preparing ghost recording";
}
void cancelActive(){if(!enabled()||GhostTrace::continuationPending())return;Draft*d=active(runtime->state);if(d&&(d->phase==ARMING||d->phase==CAPTURING)){if(beginDiscard(runtime->state,token(*d)))GhostTrace::reset();}}
void cancelArmed(){if(!enabled())return;Draft*d=active(runtime->state);if(d&&d->phase==ARMING)cancelActive();}
void unrecordedDeparture(){
    if(!enabled())return;
    if(runtime->state.serial<0x40000000u)++runtime->state.serial;
    status="Latest attempt was not recorded";
}
bool finish(const Info&i){
    if(!capturing()||!i.ownerToken||i.endQf<=i.startQf||i.splitCount>8)return false;
    Draft*d=active(runtime->state);if(!GhostTrace::queueOrdinaryFinish(d->identity.run))return false;
    if(!GhostRecordingLifecycle::finish(runtime->state,i.ownerToken))return false;
    runtime->previousAutomatic=0;
    stamp(*d,i,i.runFlags|(d->identity.run==runtime->continuedRun?MS_TRACE_CONTINUATION_RUN_FLAGS:0));status="Finishing ghost recording";return true;
}
void protect(unsigned owner,unsigned pb){if(enabled())GhostRecordingLifecycle::protect(runtime->state,owner,pb);}
void split(unsigned owner,const SusamuneGhostSplitSample&value){if(!enabled()||value.endpoint>=8)return;for(unsigned n=0;n<kDrafts;++n){Draft&d=runtime->state.drafts[n];
    if(d.ownerToken!=owner||(d.phase!=FINALIZING&&d.phase!=READY))continue;
    if(value.endpoint!=d.manifest[190])return;if(value.endpoint&&MsRecordingWord(d.manifest+184)!=value.schema)return;
    if(value.endpoint&&MsRecordingHalf(d.manifest+188)!=value.route)return;
    MsRecordingPut(d.manifest+184,value.schema);d.manifest[188]=value.route>>8;d.manifest[189]=value.route;
    MsRecordingPut(d.manifest+192+4*value.endpoint,value.qf);++d.manifest[190];return;
}}
bool selectForSave(unsigned value){
    if(!enabled())return false;
    if(!value){runtime->saveOwner=0;return true;}
    Draft*d=find(runtime->state,value);
    if(!d||(d->phase!=READY&&d->phase!=FINALIZING))return false;
    runtime->saveOwner=value;return true;
}
bool copySelection(char*out,unsigned cap,unsigned*value){const Draft*d=selected();if(!d||!out||cap<=d->manifest[93])return false;for(unsigned n=0;n<d->manifest[93];++n)out[n]=d->manifest[120+n];out[d->manifest[93]]=0;if(value)*value=token(*d);return true;}
bool selectionPending(){const Draft*d=selected();return d&&d->phase==FINALIZING;}
bool exportManifest(void*out,unsigned profile,const char*profileName,unsigned*owner,unsigned*selectionToken){
    Draft*d=selected();if(!d||d->phase!=READY||!out||!owner||!selectionToken||!SusamuneGhostPersonalProfile(profile)||((profile==SUSAMUNE_GHOST_HOVERLESS_PROFILE)!=(d->manifest[38]==SUSAMUNE_GHOST_HOVERLESS_PROFILE)))return false;
    unsigned char*p=static_cast<unsigned char*>(out);__builtin_memcpy(p,d->manifest,256);p[38]=profile;p[94]=static_cast<unsigned char>(text(p+168,profileName,16));MsRecordingPut(p+12,MsRecordingCrc(p));
    if(!MsRecordingManifestValid(p,256,MsRecordingWord(p+32),profile))return false;*owner=d->ownerToken;*selectionToken=token(*d);return true;
}
bool queueSave(unsigned value,unsigned profile){Draft*d=runtime?find(runtime->state,value):nullptr;if(!d||d->phase!=FINALIZING||runtime->saveToken)return false;runtime->saveToken=value;runtime->saveProfile=profile;return true;}
bool queuedSave(){return runtime&&runtime->saveToken;}
bool takeQueuedSave(unsigned profile,unsigned&value){if(!queuedSave())return false;Draft*d=find(runtime->state,runtime->saveToken);if(!d||d->phase==FAILED||profile!=runtime->saveProfile){runtime->saveToken=0;status="Ghost changed; confirm save again";return false;}if(d->phase!=READY)return false;value=runtime->saveToken;runtime->saveToken=0;return true;}
bool publicationStarted(unsigned value,unsigned seq){return enabled()&&beginSave(runtime->state,value,seq);}
void publicationResult(unsigned seq,bool success){
    if(!enabled())return;
    Draft*d=find(runtime->state,runtime->saveOwner);
    const bool selectedSave=d&&d->phase==SAVING&&d->saveSequence==seq;
    if(saveResult(runtime->state,seq,success)&&success&&selectedSave)runtime->saveOwner=0;
}
bool ownsToken(unsigned value){return enabled()&&find(runtime->state,value);}
bool unprotect(unsigned value){Draft*d=runtime?find(runtime->state,value):nullptr;if(!d||d->phase==SAVING||d->pbToken!=value)return false;d->pbToken=0;return true;}
bool discard(unsigned value){if(!enabled())return false;Draft*d=find(runtime->state,value);if(!d||!beginDiscard(runtime->state,value))return false;if(runtime->saveOwner==value)runtime->saveOwner=0;if(d&&!d->completion.bytes&&GhostTrace::ownedRun()==d->identity.run)GhostTrace::reset();return true;}
bool loadManifest(const void*p,unsigned n,bool observer,bool secondary){return enabled()&&p&&n==256&&MsRecordingManifestValid(static_cast<const unsigned char*>(p),n,MsRecordingWord(static_cast<const unsigned char*>(p)+32),static_cast<const unsigned char*>(p)[38])&&runtime->backend.load(p,n,observer,secondary);}
bool checkpoint(Checkpoint&value,bool restore){return enabled()&&runtime->backend.checkpoint(value,restore);}
bool captureCheckpoint(GhostTrace::CheckpointSnapshot &out, bool stopRecordingIfBankBusy) {
    out = {};
    if (enabled() && GhostTrace::continuationPending()) {
        if (GhostTrace::continuationPublicationPending() || GhostTrace::fastContinuationUntracked()) {
            stopUnrecorded();
            return true;
        }
        status = "Ghost storage busy - try again";
        return false;
    }
    if (!enabled() || !capturing()) return true;
    const auto result = GhostTrace::captureCheckpoint(out);
    if (result == GhostTrace::CheckpointCapture::BankBusy && stopRecordingIfBankBusy) {
        stopUnrecorded();
        return true;
    }
    if (result != GhostTrace::CheckpointCapture::Captured) {
        status = "Ghost checkpoint busy - try again";
        return false;
    }
    const Draft *draft = active(runtime->state);
    out.ownerToken = draft ? draft->token : 0;
    return true;
}
void abandonCheckpoint(){GhostTrace::abandonCheckpoint();}
bool checkpointSaved(unsigned slot,unsigned generation){return GhostTrace::checkpointSaved(slot,generation);}
void checkpointCleared(unsigned slot,unsigned generation){GhostTrace::checkpointCleared(slot,generation);}
int prepareFastCheckpointLoad(const GhostTrace::CheckpointSnapshot&saved,unsigned slot,unsigned generation){
    if(!GhostTrace::checkpointLoadValid(saved,slot,generation))return -1;
    if(!saved.magic){if(runtime){runtime->fastLoad=true;runtime->fastSlot=slot;runtime->fastGeneration=generation;runtime->lastLoadRecorded=false;}return 1;}
    if(!enabled())return -1;
    if(runtime->fastLoad&&(runtime->fastSlot!=slot||runtime->fastGeneration!=generation))return -1;
    runtime->fastLoad=true;runtime->fastSlot=slot;runtime->fastGeneration=generation;runtime->lastLoadRecorded=false;
    if(runtime->fastSkip||runtime->unrecorded)return 0;
    if(runtime->continuationToken){
        if(runtime->continuationSlot!=slot||runtime->continuationGeneration!=generation)return -1;
        return GhostTrace::continuationStatus()==1?1:0;
    }
    if(GhostTrace::continuationPending())return 0;
    Draft*d=active(runtime->state);const bool created=!d;
    if(d&&d->phase!=CAPTURING&&d->phase!=ARMING)return 0;
    if(!d)d=arm(runtime->state);if(!d)return 0;
    unsigned run=d->identity.run;
    if(!created){if(runtime->state.reservedRun==GhostTrace::ownedRun())runtime->state.reservedRun=0;run=takeRun(runtime->state);}
    if(!run){if(created)failed(runtime->state,d->identity,MS_TRACE_BUSY);return 0;}
    const int started=GhostTrace::beginFastContinuation(saved,slot,generation,run);
    if(started<=0){if(created)failed(runtime->state,d->identity,MS_TRACE_BUSY);return started;}
    runtime->continuationSlot=slot;runtime->continuationGeneration=generation;runtime->continuationToken=d->token;
    return GhostTrace::continuationStatus()==1?1:0;
}
bool authorizeFastCheckpointLoad(const GhostTrace::CheckpointSnapshot&saved,unsigned slot,unsigned generation){
    if(!GhostTrace::checkpointLoadValid(saved,slot,generation))return false;
    if(!runtime)return !saved.magic;
    runtime->fastLoad=runtime->fastSkip=true;runtime->fastSlot=slot;runtime->fastGeneration=generation;return true;
}
bool checkpointLoadRecorded(){return runtime&&runtime->lastLoadRecorded;}
int prepareCheckpointLoad(const GhostTrace::CheckpointSnapshot&saved,unsigned slot,unsigned generation){
    if(!saved.magic)return GhostTrace::checkpointValid(saved)?1:-1;
    if(!enabled()||!GhostTrace::checkpointValid(saved))return -1;
    if(runtime->continuationToken){
        if(runtime->continuationSlot!=slot||runtime->continuationGeneration!=generation)return -1;
        const int result=GhostTrace::continuationStatus();
        status=result==0?"Waiting for ghost checkpoint...":result<0?"Ghost continuation failed":"Ghost continuation ready";return result;
    }
    if(GhostTrace::checkpointReady(saved)<0){status="Ghost checkpoint is unavailable";return -1;}
    Draft*d=active(runtime->state);bool created=false;
    if(!d){d=arm(runtime->state);created=true;}
    if(!d||(d->phase!=CAPTURING&&d->phase!=ARMING)){status="Save or discard a ghost first";return -1;}
    unsigned run=d->identity.run;
    if(!created){if(runtime->state.reservedRun==GhostTrace::ownedRun())runtime->state.reservedRun=0;run=takeRun(runtime->state);if(!run)return -1;}
    if(!GhostTrace::beginContinuation(saved,slot,generation,run)){
        if(created)failed(runtime->state,d->identity,MS_TRACE_BAD_SOURCE);status="Ghost continuation unavailable";return -1;
    }
    runtime->continuationSlot=slot;runtime->continuationGeneration=generation;runtime->continuationToken=d->token;
    status="Waiting for ghost checkpoint...";return GhostTrace::continuationStatus();
}
bool checkpointLoadReady(const GhostTrace::CheckpointSnapshot&saved,unsigned slot,unsigned generation){
    if(runtime&&runtime->fastSkip)return runtime->fastLoad&&runtime->fastSlot==slot&&runtime->fastGeneration==generation&&GhostTrace::checkpointLoadValid(saved,slot,generation);
    if(!saved.magic)return GhostTrace::checkpointValid(saved);
    return enabled()&&runtime->continuationToken&&runtime->continuationSlot==slot&&runtime->continuationGeneration==generation&&
        MsTracePrefixSame(&runtime->checkpoints.snapshot.prefix,&saved.prefix)&&GhostTrace::continuationStatus()==1;
}
bool commitCheckpointLoad(){
    if(runtime&&runtime->fastLoad){
        runtime->lastLoadRecorded=false;
        if(!runtime->continuationToken||GhostTrace::continuationStatus()!=1){
            stopUnrecorded();runtime->fastLoad=runtime->fastSkip=false;return true;
        }
    }
    if(!runtime||!runtime->continuationToken){if(runtime)runtime->lastLoadRecorded=false;if(capturing())cancelActive();return true;}Draft*d=find(runtime->state,runtime->continuationToken);
    const unsigned scene=runtime->checkpoints.snapshot.scene;
    if(!d||!GhostTrace::commitContinuation()){
        if(runtime->fastLoad){stopUnrecorded();runtime->fastLoad=runtime->fastSkip=false;return true;}return false;}
    d->identity.run=GhostTrace::continuationRun();runtime->continuedRun=d->identity.run;d->phase=CAPTURING;d->ownerToken=d->pbToken=d->saveSequence=d->error=0;d->completion={};
    __builtin_memset(d->manifest,0,sizeof(d->manifest));runtime->session=true;runtime->scene=scene;
    runtime->continuationToken=0;runtime->lastLoadRecorded=true;runtime->fastLoad=runtime->fastSkip=false;status="Ghost continuation recording";return true;
}
void noteContinuationAudio(unsigned actions){if(runtime&&runtime->continuationToken)runtime->checkpoints.restoreActions|=actions&7u;}
bool checkpointLoadPending(){return runtime&&runtime->continuationToken!=0;}
void cancelCheckpointLoad(){
    if(runtime&&runtime->fastLoad){if(runtime->continuationToken)stopUnrecorded();runtime->fastLoad=runtime->fastSkip=false;return;}
    if(!runtime||!runtime->continuationToken)return;
    const bool unchanged=runtime->checkpoints.phase==GhostTrace::FORK_FENCE;
    GhostTrace::cancelContinuation();Draft*d=find(runtime->state,runtime->continuationToken);
    if(d&&!(unchanged&&d->phase==CAPTURING&&d->identity.run==GhostTrace::ownedRun()))
        failed(runtime->state,d->identity,MS_TRACE_BAD_SOURCE);
    runtime->continuationToken=0;
}
bool importCheckpoint(const GhostTrace::CheckpointSnapshot&saved){
#if IS_EMULATOR
    if(saved.magic){status="Streamed ghost state import unavailable";return false;}
#endif
    if(saved.magic&&!enabled()){status="Ghost continuation unavailable";return false;}
    if(GhostTrace::importCheckpoint(saved))return true;
    status="Ghost checkpoint is unavailable";return false;
}
bool checkpointExport(GhostTrace::CheckpointSnapshot&saved){
    if(saved.magic){status="Streamed ghost state export unavailable";return false;}
    if(GhostTrace::checkpointExport(saved))return true;status=GhostTrace::checkpointReady(saved)==0?
        "Waiting for ghost checkpoint storage":"Streamed ghost state export unavailable";return false;
}
const char*statusText(){return status;}
}
