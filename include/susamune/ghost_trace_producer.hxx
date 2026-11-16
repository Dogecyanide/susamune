#pragma once
#include "ghost_trace_branch_owner.hxx"
#include "ghost_checkpoint_lifecycle.hxx"
#include "ghost_trace_continuation.h"
#include "ghost_state_reference.h"
namespace GhostTrace {
enum { kCheckpointMagic=0x4d534743u, kCheckpointVersion=1, kForkOwner=0x464f524bu };
struct CheckpointSnapshot {
    unsigned magic,version;MsTracePrefix prefix;
    unsigned game,scene,capabilities,ownerToken;MsTraceFenceInfo fence;unsigned reserved[2];
};
static_assert(sizeof(CheckpointSnapshot)==96,"streamed checkpoint sidecar");
enum ForkPhase { FORK_NONE, FORK_FENCE, FORK_SOURCE, FORK_TAIL, FORK_MAP, FORK_READY, FORK_FAILED, FORK_DISCARD, FORK_FAST_PENDING, FORK_FAST_READY, FORK_PUBLISHING, FORK_UNTRACKED };
struct CheckpointController {
    GhostCheckpoints::State pins;GhostCheckpoints::Load load;CheckpointSnapshot snapshot;
    MsTracePrefix lastPrefix;unsigned lastRecords,serial,phase,newRun,branchSequence,error,restoreActions;
    unsigned atomicRequest,oldRun;bool canceled,ownsLoad,fast,durable;
};
enum class CheckpointCapture { Unavailable, Captured, BankBusy };
bool checkpointValid(const CheckpointSnapshot&v);
#if MOONSHINE_GHOST_TRACE
bool installCheckpoints(CheckpointController&);
CheckpointCapture captureCheckpoint(CheckpointSnapshot&);
void abandonCheckpoint();bool checkpointSaved(unsigned slot,unsigned generation);
void checkpointCleared(unsigned slot,unsigned generation);
int checkpointReady(const CheckpointSnapshot&);
bool checkpointSourceOwned(unsigned nonce,unsigned run);
bool checkpointExport(CheckpointSnapshot&);
bool importCheckpoint(const CheckpointSnapshot&);
bool beginContinuation(const CheckpointSnapshot&,unsigned slot,unsigned generation,unsigned newRun);
int continuationStatus();bool continuationPending();unsigned continuationRun();
bool checkpointLoadValid(const CheckpointSnapshot&,unsigned slot,unsigned generation);
int beginFastContinuation(const CheckpointSnapshot&,unsigned slot,unsigned generation,unsigned newRun);
void stopFastContinuation();bool fastContinuationUntracked();bool continuationPublicationPending();bool continuationBackgroundPending();
bool commitContinuation();void cancelContinuation();
#else
inline bool installCheckpoints(CheckpointController&){return false;}
inline CheckpointCapture captureCheckpoint(CheckpointSnapshot &out) {
    out = {};
    return CheckpointCapture::Unavailable;
}
inline void abandonCheckpoint(){}
inline bool checkpointSaved(unsigned,unsigned){return true;}
inline void checkpointCleared(unsigned,unsigned){}
inline int checkpointReady(const CheckpointSnapshot&v){return checkpointValid(v)&&!v.magic?1:-1;}
inline bool checkpointSourceOwned(unsigned,unsigned){return false;}
inline bool checkpointExport(CheckpointSnapshot&v){return checkpointValid(v)&&!v.magic;}
inline bool importCheckpoint(const CheckpointSnapshot&v){return checkpointValid(v)&&!v.magic;}
inline bool beginContinuation(const CheckpointSnapshot&,unsigned,unsigned,unsigned){return false;}
inline int continuationStatus(){return -1;}inline bool continuationPending(){return false;}
inline unsigned continuationRun(){return 0;}inline bool commitContinuation(){return false;}inline void cancelContinuation(){}
inline bool checkpointLoadValid(const CheckpointSnapshot&v,unsigned,unsigned){return checkpointValid(v)&&!v.magic;}
inline int beginFastContinuation(const CheckpointSnapshot&,unsigned,unsigned,unsigned){return 0;}
inline void stopFastContinuation(){} inline bool fastContinuationUntracked(){return false;} inline bool continuationPublicationPending(){return false;} inline bool continuationBackgroundPending(){return false;}
#endif
}
