#pragma once
#include "susamune/ghost_trace_checkpoint.h"
#include "susamune/ghost_state_reference.h"
#if MOONSHINE_GHOST_TRACE
int GhostTraceStorageAdmitted(void);
int GhostTraceBranchLookup(unsigned nonce,unsigned run,unsigned game,struct MsTraceLookup*);
int GhostTraceChildDependencyValid(const unsigned char*,unsigned nonce,unsigned run,unsigned game);
int GhostTraceFileIdentity(unsigned nonce,unsigned run,unsigned game,struct MsTraceFileIdentity*);
int GhostTraceBranchStore(const struct MsTraceBranch*,unsigned kind);
int GhostTraceBranchRelease(const struct MsTraceBranch*,unsigned kind);
int GhostTraceRetainedDiscard(unsigned nonce,unsigned run,unsigned headerHash,int begin);
void GhostTraceStateReferenceReset(void);
int GhostTraceStateReferencePrepare(const struct MsTraceStateReference*,unsigned game,unsigned project,unsigned id,unsigned generation);
int GhostTraceStateReferenceStore(void);
int GhostTraceStateReferenceRelease(void);
int GhostTraceStateReferenceRecover(int begin);
int GhostTraceStateReferenceCancel(void);
int GhostTraceStateReferenceBusy(void);
#endif
