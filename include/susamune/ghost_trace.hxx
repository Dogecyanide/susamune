#pragma once
#include "ghost_trace.h"
#include "ghost_trace_producer.hxx"
#include "ghost_world_witness.h"
class TMario;
struct TWaterEmitInfo;
namespace LiveRaceSession { struct Session; }
namespace GhostSpinObservation { struct Queue; }
namespace GhostTrace { struct Completion { unsigned nonce,run,game,bytes,chunks,frames,capabilities,headerHash,footerHash; }; }
#if MOONSHINE_GHOST_TRACE
namespace GhostTrace {
void init();
void frame(unsigned *worldScratch = nullptr, unsigned worldSlots = 0);
GhostWorldWitness::Record worldSample(unsigned *scratch, unsigned slots);
void visualSample(unsigned char out[64]);
void directInput(bool frozen, bool suppressed, unsigned reasons = 0, unsigned heldState = ~0u);
void noteHold(unsigned reasons);
void practiceAction();
GhostSpinObservation::Queue &spinQueue();
void stageSetup(unsigned area, unsigned episode, unsigned generation);
bool armStage(unsigned scene, unsigned run);
bool stageArmed();
bool backendIdentity(unsigned &nonce);
bool armOrdinaryStage(unsigned scene,unsigned run);
bool armAutomaticStage(unsigned scene,unsigned run);
bool automaticStartPending();
bool finishOrdinary(unsigned run);
// Finish after the current frame has completed its draw-side observations.
bool queueOrdinaryFinish(unsigned run);
bool completion(unsigned run,Completion &);
unsigned completedRunFlags(unsigned run);
bool discarded(unsigned run);
bool retainedFile(unsigned run);
unsigned ownedRun();
unsigned failure(unsigned run);
void movement(TMario *, unsigned cue);
void reset();
bool receive(LiveRaceSession::Session &, const void *, unsigned);
void status(unsigned *out);
void event(unsigned kind, const void *payload, unsigned bytes);
bool recording();
// Optional background preparation never gates an ordinary START.
unsigned prepareNextRun(unsigned run);
void revokePreparation();
#if SUSAMUNE_SAVE_PROBE
bool saveProbeIdle();
#endif
void random(unsigned caller,unsigned result,unsigned seed);
void literalCall(unsigned caller,unsigned result,unsigned seed);
void water(const TWaterEmitInfo &, unsigned accepted);
}
#else
namespace GhostTrace {
inline bool backendIdentity(unsigned&){return false;}
inline bool armOrdinaryStage(unsigned,unsigned){return false;}
inline bool armAutomaticStage(unsigned,unsigned){return false;}
inline bool automaticStartPending(){return false;}
inline bool finishOrdinary(unsigned){return false;}
inline bool queueOrdinaryFinish(unsigned){return false;}
inline bool completion(unsigned,Completion&){return false;}
inline unsigned completedRunFlags(unsigned){return 0;}
inline bool discarded(unsigned){return false;}
inline bool retainedFile(unsigned){return false;}
inline unsigned ownedRun(){return 0;}
inline unsigned failure(unsigned){return 0;}
inline bool stageArmed(){return false;}
inline bool recording(){return false;}
inline unsigned prepareNextRun(unsigned){return 0;}
inline void revokePreparation(){}
inline void water(const TWaterEmitInfo &, unsigned) {}
inline void directInput(bool, bool, unsigned = 0, unsigned = ~0u) {}
inline void noteHold(unsigned) {} inline void practiceAction() {}
inline void stageSetup(unsigned, unsigned, unsigned) {}
inline void init() {} inline void frame(unsigned * = nullptr, unsigned = 0) {} inline void movement(TMario *, unsigned) {} inline void reset() {}
inline bool receive(LiveRaceSession::Session &, const void *, unsigned) { return false; }
}
#endif
