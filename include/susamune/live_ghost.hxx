#pragma once
#include "susamune/ghost.hxx"
#include "susamune/practice_input.h"

#if TIMEWARP_LIVE_RACING
namespace LiveGhost {
void reset();
bool setName(const char *name, unsigned int length);
// Reset on a new session; sequence, milliseconds and scene epoch wrap modulo 32.
bool submit(const Ghost::VisualState &pose, u32 sequence, u32 remoteMs,
            u32 sceneEpoch, u32 receivedMs, const SusamunePracticeInput *input = nullptr);
// Latch once before rendering; the caller verifies the complete canonical scene.
void tick(u32 localNowMs, bool canDisplaySameCanonicalScene);
bool visualState(Ghost::VisualState *out);
bool inputState(SusamunePracticeInput *out);
bool inputsShown();
void setInputsShown(bool shown);
void drawInputs(Menu *menu);
// Uses the ordinary ghost-display/menu policy and Menu's established 2D pass.
void drawName(Menu *menu);
enum { Channels = 3 };
void resetAll();
void resetFor(unsigned channel);
bool setNameFor(unsigned channel, const char *, unsigned length);
bool submitFor(unsigned channel, const Ghost::VisualState &, u32 sequence, u32 remoteMs,
               u32 sceneEpoch, u32 receivedMs, const SusamunePracticeInput *);
void tickFor(unsigned channel, u32 now, bool sameScene);
bool visualStateFor(unsigned channel, Ghost::VisualState *);
void drawNameFor(unsigned channel, Menu *);
}
#endif
