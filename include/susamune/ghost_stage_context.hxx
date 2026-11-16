#pragma once

#include "Dolphin/types.h"

namespace GhostStageContext {
// Captured before TMarDirector::setup starts its resource worker.
enum { PRE_RESOURCE_SETUP = 1 };
struct Sample {
    u32 seed;
    u32 movementTicks;
    u32 directorTicks;
    u32 generation;
    u8 area;
    u8 episode;
};
void init();
bool sample(Sample *out);
// Scene identity is available before the resource worker finishes.
u32 generation();
void invalidateAfterRestore();
bool restoredStage();
}
