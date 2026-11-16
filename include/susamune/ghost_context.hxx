#pragma once
#include "Dolphin/types.h"
#include "susamune/ghost_context.h"

namespace GhostContext {
bool detailsEnabled();
void toggleDetails();
void beginFrame();
void *prefix(void *bank);
const void *prefix(const void *bank);
u32 prefixSize(const void *bank);
void reset(void *bank);
void clearSegment(void *bank, u16 segment);
void segment(void *bank, u16 segment, u32 qf, u32 inputIndex, bool synthetic);
void input(void *bank, u16 segment, u32 qf, u32 inputIndex);
void endpoint(void *bank, u16 segment, u32 qf, u32 inputCount, bool held);
void restored(void *bank);
u32 exportSize(const void *bank, u32 endQf);
bool exportInto(void *out, const void *bank, u32 endQf, u32 firstInput, u32 inputCount);
}
