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

u16 phaseForSpeed(u8 speed) {
    const u32 period = OS_TIMER_CLOCK * (8u >> (speed < 3 ? speed : 1));
    const u32 at = timeRemainder(OSGetTime(), period);
    return at / ((period + 1023) >> 10);
}

u16 phase(bool native) {
    return phaseForSpeed(gSettings.get(native ? SETTING_NATIVE_GRADIENT_SPEED : SETTING_QFT_GRADIENT_SPEED));
}

void sample(const u8 (*palette)[3], u16 count, u16 slot,
            u8 motion, u16 phase, u8 out[3]) {
    if (!count) return;
    if (slot >= count) slot = count - 1;
    unsigned first = slot, next = slot, weight = 0, gain = 256, shine = 0;
    phase &= 1023;
    if (motion == Flow || motion == PingPong) {
        const unsigned position = motion == Flow ? phase * count :
            (phase < 512 ? phase : 1024 - phase) * 2u * (count - 1);
        first = (slot + (position >> 10)) % count;
        next = (first + 1) % count;
        weight = position & 1023;
    } else if (motion == Pulse) {
        gain = 192 + (phase < 512 ? phase : 1024 - phase) / 8;
    } else if (motion == Wave) {
        const unsigned at = (phase + slot * 1024u / count) & 1023;
        gain = 160 + (at < 512 ? at : 1024 - at) * 96 / 512;
    } else if (motion == Shimmer) {
        const int distance = (int)(phase * (count + 2)) - (int)((slot + 1) * 1024);
        const unsigned away = distance < 0 ? -distance : distance;
        if (away < 1024) shine = (1024 - away) * 3 / 4;
    } else if (motion == Steps) {
        first = next = (slot + (phase * count >> 10)) % count;
    } else if (motion == Sparkle) {
        const unsigned beat = phase >> 7;
        const unsigned at = phase & 127;
        if ((slot * 13u + beat * 7u) % (count + 1u) < 2u)
            shine = (at < 64 ? at : 128 - at) * 12u;
    } else if (motion == Curtain) {
        const unsigned edge = (phase < 512 ? phase : 1024 - phase) * 2;
        const unsigned distance = slot * 1024u / count;
        gain = edge > distance ? 256 : 64;
        if (edge <= distance && distance - edge < 128) gain += (128 - distance + edge) * 192 / 128;
    } else if (motion == Alternating) {
        const unsigned at = (phase + (slot & 1u) * 512u) & 1023;
        gain = 112 + (at < 512 ? at : 1024 - at) * 144 / 512;
    }
    for (unsigned c = 0; c < 3; ++c) {
        const unsigned value = (palette[first][c] * (1024 - weight) +
                                palette[next][c] * weight + 512) >> 10;
        out[c] = ((value * gain >> 8) * (1024 - shine) + 255 * shine) >> 10;
    }
}
}
