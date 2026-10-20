#pragma once
#include <Dolphin/types.h>

namespace GradientMotion {
enum { Off, Flow, Pulse };
u8 mode(bool native);
u16 phase(bool native);
// Palette bytes remain immutable; phase is a presentation-only 0..1023 cycle.
void sample(const u8 (*palette)[3], u16 count, u16 slot,
            u8 motion, u16 phase, u8 out[3]);
}
