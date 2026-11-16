#pragma once
#include "susamune/ghost_trace_decode.hxx"

class TMarioGamePad;
struct TMarioControllerWork;
namespace GhostWorldInput {
namespace Trace = GhostTraceDecode;
enum MirrorPolicy { CAPTURED_SHARED, PRESERVE_SHARED, RECONSTRUCTED_SHARED, EXPERIMENTAL_PAD_MIRROR };
enum WorkPolicy { PRESERVE_NATIVE_WORK, RESTORE_INITIALIZED_WORK };
enum Evidence { NON_CAPTURED_MIRRORS = 1u, NATIVE_WORK_PRESERVED = 2u };
enum Error {
    OK, INVALID_INPUT, MISSING_SHARED, INVALID_TARGET, OWNER_REQUIRED,
    ALREADY_BORROWED, NOT_BORROWED, BUSY_OWNER, STALE_OWNER, MODE_MISMATCH,
    CONTROL_MISMATCH, INPUT_PHASE, WORK_PROOF_REQUIRED
};
enum GuardResult { OWNED, BUSY, STALE };
struct Plan { Trace::Input input; MirrorPolicy mirrors; WorkPolicy work; bool workProven; };
struct Targets {
    TMarioGamePad *pad;
    TMarioControllerWork *work;
    void *sharedButtons, *sharedStick, *sharedSubstick;
};
struct Owner { unsigned generation, token; };
struct Guard {
    void *context;
    // OWNED holds serialization and validates target lifetimes until leave().
    GuardResult (*enter)(void *, const Owner &, const Targets &);
    void (*leave)(void *);
};
struct ModeState { unsigned short flags; short stickTimer; int disabledFrames; };
struct Controls {
    bool frozen, suppressed, setupResetsMode, initialStage;
    bool haveHistory, practiceHistory;
    ModeState history;
};
struct Backup { Trace::ProcessedPad pad; Trace::ControllerWork work; Trace::SharedPad shared; };
struct Borrow {
    Targets targets;
    Owner owner;
    Guard guard;
    Backup backup;
    ModeState expected, observed;
    unsigned controls, applications;
    Error error;
    bool active, boundaryApplied, mirrorsWritten, workWritten;
};
// Pointer-free plans contain validated scalars; apply() validates again before writing.
Error prepare(Plan &, const Trace::Input &, MirrorPolicy = CAPTURED_SHARED,
              const Trace::SharedPad *reconstructed = nullptr,
              WorkPolicy = PRESERVE_NATIVE_WORK, bool initializationAndOrderProven = false);
// Zero-initialize Borrow once. One borrow covers a boundary and its MOVE calls.
Error begin(Borrow &, const Targets &, Owner, Guard);
Error apply(Borrow &, const Plan &, Controls);
// Initial setup may initialize canonical E4/E8 counters once. Frame borrowing
// never restores E2/E4/E8 over the native simulation.
// BUSY permits retry; STALE abandons the backup without dereferencing old targets.
Error restore(Borrow &);
// PADStatus, rumble, ports, reset bookkeeping and persistent actions are never targets.
bool capturedMirrors(const Plan &);
unsigned evidenceGaps(const Plan &);
static_assert(sizeof(Trace::Buttons)==48&&sizeof(Trace::Stick)==16&&sizeof(Trace::SharedPad)==80,
              "audited shared controller scalar layout");
}
