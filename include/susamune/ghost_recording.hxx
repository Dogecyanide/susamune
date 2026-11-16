#pragma once
#include "susamune/ghost_recording_lifecycle.hxx"
#include "susamune/ghost_recording_manifest.h"
#include "ghost_trace_producer.hxx"
namespace GhostRecording {
using GhostRecordingLifecycle::Checkpoint;
using GhostRecordingLifecycle::Identity;
enum Gate { DEPART_READY, DEPART_WAIT, DEPART_REFUSED };
struct Info {
    unsigned ownerToken,startQf,endQf,resultQf,runFlags;
    int routeVariant;
    unsigned char area,episode,parent,routeFlags,splitCount,sourceProfile;
    SusamuneGhostSplitSample splits[8];
    char name[48];
};
struct Backend {
    bool (*load)(const void *manifest,unsigned bytes,bool observer,bool secondary);
    // Root supplies a logical prefix/fork backend before this mode may be enabled.
    bool (*checkpoint)(Checkpoint &,bool restore);
    int (*discardRetained)(Identity,bool begin); // 0 pending, 1 done, -1 failed
};
struct Runtime {
    GhostRecordingLifecycle::State state;
    Backend backend;
    GhostTrace::CheckpointController checkpoints;
    unsigned scene,waitFrames,discardIssued,saveToken,saveProfile,saveOwner,previousAutomatic;
    bool session,warmDisabled,fastLoad,fastSkip,lastLoadRecorded,unrecorded,automatic;
    unsigned fastSlot,fastGeneration;
    unsigned continuationSlot,continuationGeneration,continuationToken,continuedRun;
};
static_assert(sizeof(Runtime)<=0xC00,"recording control exceeds +0x2400..+0x3000 lease");
// Runtime belongs in a shared-arena control lease. No default/automatic installation.
bool install(Runtime &,unsigned bootNonce,unsigned capabilities,const Backend &);
bool enabled();bool ownsSession();bool capturing();void poll();
bool activeIdentity(Identity &,unsigned &ownerToken);
bool protectedToken(unsigned token);
bool discardHeaderHash(Identity,unsigned &hash);
bool copyProtectedName(char *,unsigned,unsigned *token);

Gate beforeDeparture(unsigned scene,bool selectedIL);
void automaticStageSetup(unsigned scene);
void automaticDeparture(unsigned nextScene);
bool automaticCapture();
void cancelArmed();void cancelActive();
void unrecordedDeparture();
bool finish(const Info &);void protect(unsigned ownerToken,unsigned pbToken);
void split(unsigned ownerToken,const SusamuneGhostSplitSample &);
bool copySelection(char *,unsigned,unsigned *token);bool selectionPending();
// Zero selects latest; a nonzero token binds save intent to one exact draft.
bool selectForSave(unsigned token);
bool exportManifest(void *,unsigned profile,const char *profileName,unsigned *ownerToken,unsigned *selectionToken);
bool queueSave(unsigned token,unsigned profile);bool queuedSave();
bool takeQueuedSave(unsigned profile,unsigned &token);
bool publicationStarted(unsigned selected,unsigned sequence);void publicationResult(unsigned sequence,bool success);
bool ownsToken(unsigned token);bool unprotect(unsigned token);
bool discard(unsigned token);bool loadManifest(const void *,unsigned,bool observer,bool secondary);
bool checkpoint(Checkpoint &,bool restore);
bool captureCheckpoint(GhostTrace::CheckpointSnapshot&, bool stopRecordingIfBankBusy = false);
void abandonCheckpoint();bool checkpointSaved(unsigned slot,unsigned generation);
void checkpointCleared(unsigned slot,unsigned generation);
int prepareCheckpointLoad(const GhostTrace::CheckpointSnapshot&,unsigned slot,unsigned generation);
// -1 rejects invalid checkpoint ownership; 0 is pending/busy; 1 is ready.
int prepareFastCheckpointLoad(const GhostTrace::CheckpointSnapshot&,unsigned slot,unsigned generation);
bool authorizeFastCheckpointLoad(const GhostTrace::CheckpointSnapshot&,unsigned slot,unsigned generation);
bool checkpointLoadRecorded();
bool checkpointLoadReady(const GhostTrace::CheckpointSnapshot&,unsigned slot,unsigned generation);
bool commitCheckpointLoad();void cancelCheckpointLoad();
bool checkpointLoadPending();
void noteContinuationAudio(unsigned actions);
bool checkpointExport(GhostTrace::CheckpointSnapshot&);
bool importCheckpoint(const GhostTrace::CheckpointSnapshot&);
class CheckpointSave {
    bool pending;
public:
    CheckpointSave():pending(false){}
    ~CheckpointSave(){if(pending)abandonCheckpoint();}
    bool capture(GhostTrace::CheckpointSnapshot &out, bool stopRecordingIfBankBusy = false) {
        pending = GhostRecording::captureCheckpoint(out, stopRecordingIfBankBusy);
        return pending;
    }
    bool commit(unsigned slot,unsigned generation){if(!pending)return false;if(!checkpointSaved(slot,generation))return false;pending=false;return true;}
};
class CheckpointLoad {
    bool pending;
public:
    CheckpointLoad():pending(true){}
    ~CheckpointLoad(){if(pending)cancelCheckpointLoad();}
    bool commit(){if(!commitCheckpointLoad())return false;pending=false;return true;}
};
const char *statusText();
}
