#pragma once
#include "susamune/ghost_trace_decode.hxx"
#include "susamune/ghost_spin_observation.hxx"

namespace GhostWorldReplay {
namespace Trace = GhostTraceDecode;
enum { kMaxMovements = 64, kMaxRandomCalls = 16384,
       kRequiredCapabilities = 3u|(1u<<10)|(1u<<11)|(1u<<16)|(1u<<18) };
enum Mode { EXPERIMENTAL, REQUIRE_EVIDENCE };
enum State { PREPARING, INITIALIZATION_READY, LOADING, NEED_SOURCE, READY, RUNNING, COMPLETE, STOPPED };
enum FeedResult { ACCEPTED, FRAME_PENDING, FEED_FAILED };
enum Advance { FRAME_STARTED, WAIT_SOURCE, WAIT_NATIVE_SETUP, ADVANCE_FAILED };
enum Error {
    NONE, ARGUMENT, FORMAT, REGION, CAPABILITY, NO_PRE_STAGE_CAPTURE, ORDER,
    CAPACITY, MISSING_INPUT, UNSUPPORTED_TRANSITION, SETTINGS_CHANGED,
    INPUT_ORDER, INPUT_NOT_APPLIED, NATIVE_STATE, RNG_UNDERRUN, RNG_ORDER,
    RNG_MISMATCH, RNG_NOT_CONSUMED, VISUAL_MISMATCH, WORLD_MISMATCH,
    MISSING_EVIDENCE, PLATFORM_REFUSED, UNSUPPORTED_ACTION, CANCELLED, EMPTY_SOURCE, SPIN_ORDER, SPIN_MISMATCH, SPIN_NOT_CONSUMED
};
enum Evidence {
    STATIC_GLOBALS = 1u, ROOT_OBJECTS = 2u, RESOURCE_BUILD = 4u,
    FLAG_OWNERSHIP = 8u, SETTINGS_OWNERSHIP = 16u, CLOCK_MODEL = 32u,
    INPUT_HOOKS = 64u, RNG_HOOKS = 128u, VISUAL_WITNESS = 256u, WORLD_WITNESS = 512u,
    SHARED_MIRRORS = 1024u, MOVIE_TIMING = 2048u, LEGACY_LOADING_CLOCK = 4096u, kInitialEvidence = 255u, kAllEvidence = 8191u
};
enum PersistentAction { CARD_WRITE = 1, SETTINGS_WRITE, LIBRARY_WRITE, OTHER_WRITE };
struct InitialView {
    Trace::StageStart stage;
    const unsigned char *settings;
    unsigned missingEvidence;
};
struct Movement { Trace::Input input; unsigned tick; };
struct RandomCall { unsigned caller, result, seed, frame, tick, setup; };
static_assert(sizeof(RandomCall)==24, "RNG lease units must remain 24 bytes");
struct NativeFrame {
    unsigned scene, context, directorState;
    bool setupComplete, setupTerminated;
    // Omit unavailable witnesses in experimental runs; omissions remain in the report.
    const Trace::Visual *visual;
    const GhostWorldWitness::Record *world;
};
struct FrameView {
    const Trace::Frame *frame;
    const Trace::Input *boundary;
    const Trace::Visual *visual;
    unsigned sourceFrame, sourceTick, movements;
};
struct Report {
    Error error;
    unsigned detail, sourceFrame, sourceTick, missingEvidence;
    unsigned loadingFrames, playedFrames, movementCalls, randomCalls;
    bool experimental, complete;
};
struct Replay {
    unsigned game, capabilities, mode, error, detail, missingEvidence,runFlags,provenanceFrame;
    Movement *movements;
    RandomCall *random;
    GhostSpinObservation::Queue *spin;
    unsigned spinLastSequence;
    unsigned movementCapacity, randomCapacity, randomHead, randomCount;
    unsigned randomUsed, randomIndex;
    RandomCall randomFront;
    Trace::StageStart stage, pendingStage;
    unsigned char flagBytes[896], settings[64];
    Trace::Frame frame;
    Trace::Input boundary;
    Trace::Visual visual;
    GhostWorldWitness::Record world;
    unsigned sourceFrame, sourceTick, frameTick, movementCount, consumedMovements, activeTick;
    unsigned loadingFrames, playedFrames, movementCalls, randomCalls;
    unsigned movieScene, movieFrames;
    bool movieRandom, inheritedClockPending;
    unsigned clockOrigin, clockAttempt;
    bool haveStage, haveSettings, initialized, haveFrame, haveBoundary, haveVisual;
    bool sealed, running, pendingInput, ended, sawReady, haveWorld, worldMatched;
};
// A subarea can inherit time from a stage outside the recording.
inline bool clockMatches(const Replay &r,unsigned expected,unsigned observed) {
    const unsigned origin=r.visual.attempt==r.clockAttempt?r.clockOrigin:0;
    return expected>=origin&&expected-origin==observed&&(!origin||expected<=0x7fffffffu);
}
// All storage is caller-leased; initialization copies only bounded observations.
// The caller serializes feed() and native hooks, including the setup worker.
// randomCapacity counts 24-byte storage units; randomCount counts decoded calls.
// The private packet ring owns these bytes, not an array of expanded RandomCalls.
bool begin(Replay &, unsigned version, unsigned sourceGame, unsigned targetGame,
           unsigned capabilities, Mode, Movement *, unsigned movementCapacity,
           RandomCall *, unsigned randomCapacity);
bool attachSpinQueue(Replay &, GhostSpinObservation::Queue &);
// FRAME_PENDING does not consume its event. Retry after endFrame().
FeedResult feed(Replay &, const Trace::Event &);
// A continuation is applied after the last prefix frame, before reading its tail.
FeedResult sealBoundary(Replay &, unsigned frame, unsigned tick);
bool continueSource(Replay &, const MsTraceContinuation &);
// Old captures identify skipped movies but do not record their readiness/timing.
bool acceptSkippedMovie(Replay &);
bool finishSource(Replay &);
State state(const Replay &);
bool initialView(const Replay &, InitialView &);
// Coverage is a caller audit, not evidence supplied by the file. Persistent writes
// must already be blocked even for an experimental run.
bool confirmInitialization(Replay &, unsigned reconstructedEvidence, bool persistentWritesBlocked);
Advance beginFrame(Replay &, const NativeFrame &, FrameView &);
bool movement(Replay &, unsigned cue, unsigned ordinal, const Movement *&);
// Confirm each boundary/MOVE after applying gameplay scalars and control flags.
// Physical stop/pause input stays on the independent live pad channel.
bool inputApplied(Replay &, bool success);
bool verifyRandom(Replay &, unsigned caller, unsigned result, unsigned seed);
bool replayFeedback(Replay &,unsigned caller,unsigned seed,unsigned &value);
bool replayFloatFeedback(Replay &,unsigned caller,unsigned seed,unsigned &value);
bool endFrame(Replay &, bool worldObserved, bool worldMatches);
// Call before the platform executes any persistent action; refusal is terminal.
bool refuseAction(Replay &, PersistentAction);
void cancel(Replay &);
Report report(const Replay &);
}
