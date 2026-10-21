#include "susamune/gradient_motion.hxx"
#include "susamune/settings.hxx"
#include <Dolphin/OS.h>

namespace GradientMotion {
u8 mode(bool native) {
    return gSettings.get(native ? SETTING_NATIVE_GRADIENT_MOTION : SETTING_QFT_GRADIENT_MOTION);
}

// Exact 64-bit remainder from 32-bit steps: the mod links without libgcc, so a
// variable u64 % would need __umoddi3. Requires period < 2^31 (at most 8 s here).
static u32 timeRemainder(unsigned long long now, u32 period) {
    u32 rest = static_cast<u32>(now >> 32) % period;
    const u32 low = static_cast<u32>(now);
    for (int bit = 31; bit >= 0; --bit) {
        rest = rest << 1 | (low >> bit & 1u);
        if (rest >= period) rest -= period;
    }
    return rest;
}

u16 phase(bool native) {
    const unsigned speed = gSettings.get(native ? SETTING_NATIVE_GRADIENT_SPEED : SETTING_QFT_GRADIENT_SPEED);
    const u32 period = OS_TIMER_CLOCK * (8u >> (speed < 3 ? speed : 1));
    const u32 at = timeRemainder(OSGetTime(), period);
    return at / ((period + 1023) >> 10);
}

void sample(const u8 (*palette)[3], u16 count, u16 slot,
            u8 motion, u16 phase, u8 out[3]) {
    if (!count) return;
    if (slot >= count) slot = count - 1;
    unsigned first = slot, next = slot, weight = 0, gain = 256;
    phase &= 1023;
    if (motion == Flow) {
        const unsigned position = phase * count;
        first = (slot + (position >> 10)) % count;
        next = (first + 1) % count;
        weight = position & 1023;
    } else if (motion == Pulse) {
        gain = 192 + (phase < 512 ? phase : 1024 - phase) / 8;
    }
    for (unsigned c = 0; c < 3; ++c) {
        const unsigned value = (palette[first][c] * (1024 - weight) +
                                palette[next][c] * weight + 512) >> 10;
        out[c] = value * gain >> 8;
    }
}
}
