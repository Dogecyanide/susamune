#ifndef SUSAMUNE_RNG_CONTROL_HXX
#define SUSAMUNE_RNG_CONTROL_HXX

#include <Dolphin/types.h>

// Install the permanent crane dispatch wrappers and finish their tiny rand
// shims before the app state machine can load a stage.
void rngControlInit();

// Crane rand hooks run inside setupObjects(), so stale stage pointers must be
// dropped before that call begins.
void rngControlBeforeStageSetup();

// Re-adopt mod-side RNG state after a same-scenario restore.
void rngControlOnSavestateLoaded();

// Apply transition-based instruction controls before the director advances.
void rngControlApply();

enum { RNG_CONTROL_SAVESTATE_MAGIC = 0x43524e47u,
       RNG_CONTROL_SAVESTATE_WORDS = 128, RNG_CONTROL_SAVESTATE_DATA_WORDS = 18 };
// The opaque state block stores all five cache rows; validation never follows pointers.
bool rngControlCaptureSavestate(u32 *words, unsigned count);
bool rngControlValidateSavestate(const u32 *words, unsigned count);
// Call after the game heap is restored. A rejected owner clears every cache row.
bool rngControlRestoreSavestate(const u32 *words, unsigned count);
// Old states remain usable for practice, but cannot reconstruct a crane roll.
void rngControlRestoreLegacySavestate();
bool rngControlSavestateRequired();

enum { RNG_TRACE_CRANE_WORDS = 24 };
// Returns 24 words, or zero without touching out until a known crane is ready.
// 0..5: index, actor, retail roll, flags (vertical1/saved-speed2), state, timer.
// 6..17: current position/rotation, initial position/rotation, as raw f32 bits.
// 18..21: native words +138..144. Rotating: baseY/lower/upper offsets/speed;
// vertical: cargo pointer/sound id/upper/lower angles, not per-instance speed.
// 22: shared vertical speed; 23: saved rotating retail speed (flag2), otherwise0.
unsigned rngControlTraceCrane(unsigned index, unsigned *out, unsigned capacity);

// RNG setup, including Petey/King Boo, no longer applies the red HUD warning.
inline bool rngControlInvalidatesIl() { return false; }

extern "C" void susamuneForceKingBooFruit(void *slot, s32 reel);

// These arrays are executable two-word tail shims targeted by patches.py.
extern "C" u32 gCraneUpDownRandShim[];
extern "C" u32 gCraneRotYRandShim[];

#endif  // SUSAMUNE_RNG_CONTROL_HXX
