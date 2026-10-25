#pragma once
#include <Dolphin/types.h>
#include "susamune/gradient_options.h"

namespace GradientMotion {
enum { Off, Flow, Pulse, PingPong, Wave, Shimmer, Steps, Sparkle, Curtain, Alternating, Count };
static_assert(Count == SUSAMUNE_GRADIENT_MOTION_COUNT, "motion parser limit");
// Six/seven were invalid stop counts. Their 64 codes hold the extra modes
// without changing editor owners or persisted structure sizes.
inline u8 extraCode(u8 options) { return (options >> 3) * 2 + (options & 1); }
inline u8 wordStops(u8 options) { return (options & 7) < 6 ? options & 7 : extraCode(options) % 6; }
inline u8 wordSpeed(u8 options) { return (options & 7) < 6 ? (options >> 5) & 3 : extraCode(options) / 6 % 3; }
inline u8 wordMotion(u8 options) {
    if ((options & 7) >= 6) return 8 + extraCode(options) / 18;
    return ((options >> 3) & 3) | ((options >> 5) & 4);
}
inline u8 wordOptions(u8 stops, u8 speed, u8 motion) {
    if (motion < 8) return stops | (speed << 5) | ((motion & 3) << 3) | ((motion & 4) << 5);
    const unsigned code = (motion - 8) * 18 + speed * 6 + stops;
    return 6 + (code & 1) + (code >> 1) * 8;
}
inline u8 withWordMotion(u8 options, u8 motion) {
    return wordOptions(wordStops(options), wordSpeed(options), motion);
}
inline u8 withWordStops(u8 options, u8 stops) { return wordOptions(stops, wordSpeed(options), wordMotion(options)); }
inline u8 withWordSpeed(u8 options, u8 speed) { return wordOptions(wordStops(options), speed, wordMotion(options)); }
u8 mode(bool native);
u16 phase(bool native);
u16 phaseForSpeed(u8 speed);
// Palette bytes remain immutable; phase is a presentation-only 0..1023 cycle.
void sample(const u8 (*palette)[3], u16 count, u16 slot,
            u8 motion, u16 phase, u8 out[3]);
}
