#include "susamune/mem2_map.h"
#include "susamune/creation.hxx"
#include "susamune/creation_color.hxx"
#include "susamune/gradient_motion.hxx"
#include "susamune/settings.hxx"
#include "susamune/gameplay_speed_editor.hxx"
#include "susamune/qft_display.hxx"

#include "Dolphin/printf.h"
#include "SMS/Player/MarioGamePad.hxx"
#include "susamune/glyphs.hxx"
#include "susamune/layout_editor.hxx"
#include "susamune/menu.hxx"
#include "susamune/packed_text.hxx"

namespace {

typedef JUtility::TColor Color;

const char kOptionNames[] =
    "Text hue\0Text saturation\0Text lightness\0Text opacity\0Text brightness\0"
    "Background hue\0Background saturation\0Background lightness\0"
    "Background opacity\0Padding";
const char kElementOptionNames[] =
    "Element hue\0Element saturation\0Element lightness\0Element opacity\0"
    "Element brightness";

enum EditOption {
    OPTION_TEXT_H,
    OPTION_TEXT_S,
    OPTION_TEXT_L,
    OPTION_TEXT_A,
    OPTION_TEXT_BRIGHTNESS,
    OPTION_BG_H,
    OPTION_BG_S,
    OPTION_BG_L,
    OPTION_BG_A,
    OPTION_PADDING,
    OPTION_COLOR_MODE,
    OPTION_GRADIENT,
    OPTION_GRADIENT_DIRECTION,
    OPTION_GRADIENT_MOTION,
    OPTION_GRADIENT_SPEED,
    OPTION_COUNT,
};

enum ConfirmAction {
    CONFIRM_NONE,
    CONFIRM_KEEP,
    CONFIRM_CANCEL,
    CONFIRM_RESET,
};

// Only one Creation editor is active; keep its HSL choices through target changes.
constexpr unsigned kHslSlots = 256;
u8 sGradientPreset;
u16 sGradientDirectionSetting;
u8 sGradientDirectionBackup;
u8 sGradientMotionBackup, sGradientSpeedBackup;
u8 sCreationMinimumScale, sCreationMaximumScale;
u8 sGradientEnds[4][3];
const char kGradientNames[] = "Current colours\0Sunset\0Ocean\0Rainbow\0Blend ends\0One colour";
#if defined(__powerpc__)
#define sHsl (*reinterpret_cast<CreationColor::Hsl (*)[kHslSlots + 1]>(SUSAMUNE_HSL_CACHE_PPC_BASE))
#else
CreationColor::Hsl sHsl[kHslSlots + 1];
#endif

constexpr u8 kStyleOffsets[] = {
    __builtin_offsetof(CreationStyle, textA),
    __builtin_offsetof(CreationStyle, textBrightness),
    __builtin_offsetof(CreationStyle, bgR),
    __builtin_offsetof(CreationStyle, bgG),
    __builtin_offsetof(CreationStyle, bgB),
    __builtin_offsetof(CreationStyle, bgA),
    __builtin_offsetof(CreationStyle, padding),
};
static_assert(sizeof(kStyleOffsets) == OPTION_COLOR_MODE - OPTION_TEXT_A,
              "Creation scalar options changed");

u8 &styleValue(CreationStyle &style, int option) {
    return *(reinterpret_cast<u8 *>(&style) +
             kStyleOffsets[option - OPTION_TEXT_A]);
}

u8 styleValue(const CreationStyle &style, int option) {
    return *(reinterpret_cast<const u8 *>(&style) +
             kStyleOffsets[option - OPTION_TEXT_A]);
}

inline int clampi(int value, int lo, int hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

u8 lit(u8 value, u8 brightness) {
    return (u8)clampi((int)value * brightness / 100, 0, 255);
}

int glyphBytes(const char *text) {
    const u8 c = (u8)text[0];
    return ((c >= 0x81 && c <= 0x9f) || (c >= 0xe0 && c <= 0xfc)) && text[1]
               ? 2 : 1;
}

const char *glyphAt(const char *text, u16 index) {
    if (!text) return nullptr;
    while (*text && index) {
        text += glyphBytes(text);
        index--;
    }
    return *text ? text : nullptr;
}

int splitTextWidth(const char *text, int size, int *glyphs) {
    int width = 0;
    *glyphs = 0;
    while (*text) {
        const int bytes = glyphBytes(text);
        char one[3] = {text[0], '\0', '\0'};
        if (bytes == 2) one[1] = text[1];
        width += Menu::textWidth(one, size);
        text += bytes;
        (*glyphs)++;
    }
    return width;
}

bool textChannel(const u8 (*textRgb)[3], u16 slots, u16 target,
                 int channel, u16 *value) {
    if (!textRgb || slots == 0) return false;
    const int first = target ? target - 1 : 0;
    const int end = target ? first + 1 : slots;
    const u16 v = sHsl[first].channel[channel];
    for (int i = first + 1; i < end; i++) {
        if (sHsl[i].channel[channel] != v) return false;
    }
    *value = CreationColor::display(sHsl[first], channel);
    return true;
}

void adjustTextChannel(u8 (*textRgb)[3], u16 slots, u16 target,
                       int channel, int delta) {
    const int first = target ? target - 1 : 0;
    const int end = target ? first + 1 : slots;
    const u16 value = CreationColor::adjusted(sHsl[first].channel[channel], channel, delta);
    for (int i = first; i < end; i++) {
        sHsl[i].channel[channel] = value;
        CreationColor::toRgb(sHsl[i], textRgb[i]);
    }
}

void gradientRange(u8 (*rgb)[3], u16 firstSlot, u16 count, u8 preset, unsigned ends) {
    if (!count) return;
    for (u16 i = 0; i < count; ++i)
        CreationColor::gradient(preset, i, count, sGradientEnds[ends],
                                 sGradientEnds[ends + 1], rgb[firstSlot + i]);
}

void applyGradient(u8 (*rgb)[3], u16 slots, u8 preset, bool timer, bool captureEnds) {
    if (!preset || !rgb || !slots) return;
    if (captureEnds) {
        // Browsing presets must not overwrite the user's blend endpoints.
        for (unsigned c = 0; c < 3; ++c) {
            sGradientEnds[0][c] = rgb[0][c];
            sGradientEnds[1][c] = rgb[timer && slots >= 15 ? 5 : slots - 1][c];
            sGradientEnds[2][c] = rgb[timer && slots >= 15 ? 6 : 0][c];
            sGradientEnds[3][c] = rgb[timer && slots >= 15 ? 9 : slots - 1][c];
        }
    }
    if (timer && slots >= 15) {
        gradientRange(rgb, 0, 6, preset, 0);
        gradientRange(rgb, 6, 4, preset, 2);
        const u8 before[] = {1, 3, 7};
        for (unsigned i = 0; i < 3; ++i)
            for (unsigned c = 0; c < 3; ++c)
                rgb[10 + i][c] = (rgb[before[i]][c] + rgb[before[i] + 1][c] + 1) / 2;
    } else gradientRange(rgb, 0, slots, preset, 0);
    for (u16 i = 0; i < slots; ++i) sHsl[i] = CreationColor::fromRgb(rgb[i]);
}

void resetOption(CreationStyle &style, const CreationStyle &defaults,
                 u8 (*textRgb)[3], const u8 (*defaultRgb)[3],
                 u16 defaultRgbSlots, u16 slots, u8 option, u16 target) {
    if (option == OPTION_GRADIENT) {
        for (u16 i = 0; i < slots; ++i) {
            for (unsigned c = 0; c < 3; ++c)
                textRgb[i][c] = defaultRgb[defaultRgbSlots > 1 ? i : 0][c];
            sHsl[i] = CreationColor::fromRgb(textRgb[i]);
        }
    } else if (option <= OPTION_TEXT_L) {
        const int first = target ? target - 1 : 0;
        const int end = target ? first + 1 : slots;
        for (int i = first; i < end; i++) {
            sHsl[i].channel[option] = CreationColor::fromRgb(
                defaultRgb[defaultRgbSlots > 1 ? i : 0]).channel[option];
            CreationColor::toRgb(sHsl[i], textRgb[i]);
        }
    } else if (option >= OPTION_BG_H && option <= OPTION_BG_L) {
        const int channel = option - OPTION_BG_H;
        sHsl[slots].channel[channel] = CreationColor::fromRgb(&defaults.bgR).channel[channel];
        CreationColor::toRgb(sHsl[slots], &style.bgR);
    } else {
        styleValue(style, option) = styleValue(defaults, option);
    }
}

const char *targetLabel(u16 target, const char *preview, const char *targetNames,
                        char *out, int size) {
    if (target == 0) return "All";
    if (targetNames) return PackedText::at(targetNames, target - 1);
    const char *glyph = glyphAt(preview, target - 1);
    if (!glyph || *glyph == ' ') {
        snprintf(out, size, "%u%s", target, glyph ? " (space)" : "");
        return out;
    }
    int used = snprintf(out, size, "%u '", target);
    int bytes = glyphBytes(glyph);
    for (int i = 0; i < bytes && used + 2 < size; i++) out[used++] = glyph[i];
    if (used + 1 < size) out[used++] = '\'';
    out[used] = '\0';
    return out;
}

}  // namespace

void CreationEditor::reset() {
    NumberEditor::cancel(this);
    mStyle        = nullptr;
    mTextRgb      = nullptr;
    mBackupRgb    = nullptr;
    mTargetNames  = nullptr;
    mCustomMask   = nullptr;
    mCustomMaskBackup = 0;
    mRepeatMask   = 0;
    mTextSlots    = 0;
    mTargetSlots  = 0;
    mOption       = 0;
    mCapabilities = CAP_ALL;
    mTextTarget   = 0;
    mRepeatFrames = 0;
    mConfirm      = CONFIRM_NONE;
    mEditing      = false;
}

#pragma clang section text=""
void CreationEditor::begin(CreationStyle *style, u8 (*textRgb)[3],
                           u8 (*backupRgb)[3], u16 textSlots, u16 targetSlots,
                           const char *targetNames, u16 capabilities,
                           u16 *customMask) {
    if (!style || !textRgb || !backupRgb || textSlots == 0 || mEditing) return;
    if (textSlots > kHslSlots || (customMask && textSlots > 16)) return;
    mStyle        = style;
    mBackup       = *style;
    mTextRgb      = textRgb;
    mBackupRgb    = backupRgb;
    mTargetNames  = targetNames;
    mCustomMask   = customMask;
    mCustomMaskBackup = customMask ? *customMask : 0;
    mTextSlots    = textSlots;
    mTargetSlots  = targetSlots && targetSlots < textSlots ? targetSlots : textSlots;
    for (u16 i = 0; i < mTextSlots; i++) {
        for (int c = 0; c < 3; c++) mBackupRgb[i][c] = mTextRgb[i][c];
        sHsl[i] = CreationColor::fromRgb(mTextRgb[i]);
    }
    sHsl[mTextSlots] = CreationColor::fromRgb(&mStyle->bgR);
    mRepeatMask   = 0;
    mOption       = customMask ? OPTION_COLOR_MODE :
                   (capabilities & CAP_GRADIENT) && mTargetSlots > 1 ? OPTION_GRADIENT : 0;
    mCapabilities = capabilities;
    mTextTarget   = 0;
    mRepeatFrames = 0;
    mConfirm      = CONFIRM_NONE;
    mEditing      = true;
    sGradientPreset = 0;
    sGradientDirectionSetting = 0xffff;
    sCreationMinimumScale = 50;
    sCreationMaximumScale = 200;
    NumberEditor::cancel(this);
}

void CreationEditor::setScaleLimits(u8 minimum, u8 maximum) {
    sCreationMinimumScale = minimum;
    sCreationMaximumScale = maximum;
}

SettingId gradientSetting(unsigned option) {
    if (option == OPTION_GRADIENT_DIRECTION) return (SettingId)sGradientDirectionSetting;
    const unsigned first = sGradientDirectionSetting == SETTING_NATIVE_VERTICAL_GRADIENT
        ? SETTING_NATIVE_GRADIENT_MOTION : SETTING_QFT_GRADIENT_MOTION;
    return (SettingId)(first + (option == OPTION_GRADIENT_SPEED));
}

void CreationEditor::setGradientDirectionSetting(u16 setting) {
    sGradientDirectionSetting = setting;
    sGradientDirectionBackup = gSettings.get((SettingId)setting);
    sGradientMotionBackup = gSettings.get(gradientSetting(OPTION_GRADIENT_MOTION));
    sGradientSpeedBackup = gSettings.get(gradientSetting(OPTION_GRADIENT_SPEED));
}

#pragma clang section text=""
bool CreationEditor::optionEnabled(u8 option) const {
    if (option >= OPTION_GRADIENT_DIRECTION && option <= OPTION_GRADIENT_SPEED)
        return sGradientDirectionSetting != 0xffff;
    if (option == OPTION_GRADIENT)
        return (mCapabilities & CAP_GRADIENT) && mTargetSlots > 1;
    if (option == OPTION_COLOR_MODE)
        return mCustomMask && (mCapabilities & CAP_COLOR_MODE);
    if (option <= OPTION_TEXT_L)
        return mCapabilities & CAP_TEXT_COLOR;
    if (option == OPTION_TEXT_A)
        return mCapabilities & CAP_TEXT_ALPHA;
    if (option == OPTION_TEXT_BRIGHTNESS)
        return mCapabilities & CAP_BRIGHTNESS;
    if (option >= OPTION_BG_H && option <= OPTION_BG_A)
        return mCapabilities & CAP_BACKGROUND;
    return mCapabilities & CAP_PADDING;
}

void CreationEditor::moveOption(int direction) {
    const u8 first = mOption;
    // The colour-mode/gradient group is listed first, as draw() shows it.
    const int lead = OPTION_COUNT - OPTION_COLOR_MODE;
    do {
        const int order = mOption >= OPTION_COLOR_MODE ? mOption - OPTION_COLOR_MODE : mOption + lead;
        const int next = (order + OPTION_COUNT + direction) % OPTION_COUNT;
        mOption = next < lead ? OPTION_COLOR_MODE + next : next - lead;
    } while (!optionEnabled(mOption) && mOption != first);
}

u32 CreationEditor::repeatInput(TMarioGamePad *pad) {
    const u32 mask = TMarioGamePad::CSTICK_UP | TMarioGamePad::CSTICK_DOWN |
                     TMarioGamePad::CSTICK_LEFT | TMarioGamePad::CSTICK_RIGHT |
                     TMarioGamePad::L | TMarioGamePad::R;
    const u32 held = pad->mButtons.mInput & mask;
    u32 fired = pad->mButtons.mFrameInput & mask;
    fired |= held & ~mRepeatMask;

    if (!held) {
        mRepeatFrames = 0;
    } else if (held != mRepeatMask) {
        mRepeatFrames = 0;
    } else if (++mRepeatFrames >= 18) {
        fired |= held;
        mRepeatFrames = 14;
    }
    mRepeatMask = held;
    return fired;
}

u8 CreationEditor::update(TMarioGamePad *pad, const CreationStyle &defaults,
                          const u8 (*defaultRgb)[3], u16 defaultRgbSlots) {
    if (!mEditing || !mStyle || !pad) return UPDATE_NONE;
    if (NumberEditor::active(this)) {
        unsigned value;
        if (NumberEditor::update(gMenu, &value) != 1) return UPDATE_NONE;
        mStyle->scale = (u8)value;
        return UPDATE_CHANGED;
    }

    const u32 pressed = pad->mButtons.mRapidInput;
    if (mConfirm != CONFIRM_NONE) {
        if (pressed & TMarioGamePad::A) {
            if (mConfirm == CONFIRM_KEEP) {
                mConfirm = CONFIRM_NONE;
                mEditing = false;
                return UPDATE_FINISHED;
            }
            if (mConfirm == CONFIRM_CANCEL) {
                *mStyle = mBackup;
                if (sGradientDirectionSetting != 0xffff) {
                    gSettings.set((SettingId)sGradientDirectionSetting, sGradientDirectionBackup);
                    gSettings.set(gradientSetting(OPTION_GRADIENT_MOTION), sGradientMotionBackup);
                    gSettings.set(gradientSetting(OPTION_GRADIENT_SPEED), sGradientSpeedBackup);
                }
                if (mCustomMask) *mCustomMask = mCustomMaskBackup;
                for (u16 i = 0; i < mTextSlots; i++) {
                    for (int c = 0; c < 3; c++)
                        mTextRgb[i][c] = mBackupRgb[i][c];
                }
                mConfirm = CONFIRM_NONE;
                mEditing = false;
                return UPDATE_FINISHED | UPDATE_CANCELLED;
            }
            if (mOption >= OPTION_GRADIENT_DIRECTION) {
                gSettings.set(gradientSetting(mOption), mOption == OPTION_GRADIENT_SPEED ? 1 : 0);
            } else if (mOption == OPTION_COLOR_MODE && mCustomMask) {
                const u16 mask = mTextTarget ? 1u << (mTextTarget - 1)
                                            : (1u << mTextSlots) - 1u;
                *mCustomMask &= ~mask;
            } else if (optionEnabled(mOption)) {
                const u16 resetSlots = mOption == OPTION_GRADIENT
                    ? (mCapabilities & CAP_TIMER_GRADIENT) ? 13 : mTargetSlots : mTextSlots;
                resetOption(*mStyle, defaults, mTextRgb, defaultRgb,
                            defaultRgbSlots, resetSlots, mOption, mTextTarget);
                if (mOption == OPTION_GRADIENT) mTextTarget = 0;
                if (mOption == OPTION_GRADIENT || mOption <= OPTION_TEXT_L) sGradientPreset = 0;
                if (mOption <= OPTION_TEXT_L && mCustomMask &&
                    (mCapabilities & CAP_RGB_ENABLES_CUSTOM))
                    *mCustomMask |= mTextTarget ? 1u << (mTextTarget - 1)
                                                : (1u << mTextSlots) - 1u;
            } else {
                if (mCapabilities & CAP_POSITION) {
                    mStyle->x = defaults.x;
                    mStyle->y = defaults.y;
                }
                if (mCapabilities & CAP_SCALE)
                    mStyle->scale = defaults.scale;
            }
            mConfirm = CONFIRM_NONE;
            return UPDATE_CHANGED | (mOption <= OPTION_TEXT_L || mOption == OPTION_GRADIENT ? UPDATE_COLOR_CHANGED : 0) |
                   (mOption == OPTION_COLOR_MODE ? UPDATE_MODE_CHANGED : 0);
        }
        if (pressed & TMarioGamePad::B) mConfirm = CONFIRM_NONE;
        return UPDATE_NONE;
    }

    if ((pressed & TMarioGamePad::A) && (pad->mButtons.mInput & TMarioGamePad::X) &&
        (mCapabilities & CAP_SCALE)) {
        NumberEditor::begin(this, "Display size", mStyle->scale,
                            sCreationMinimumScale, sCreationMaximumScale, "%");
        return UPDATE_NONE;
    }
    if (pressed & TMarioGamePad::A) {
        mConfirm = CONFIRM_KEEP;
        return UPDATE_NONE;
    }
    if (pressed & TMarioGamePad::B) {
        mConfirm = CONFIRM_CANCEL;
        return UPDATE_NONE;
    }

    u8 result = UPDATE_NONE;
    if (pressed & TMarioGamePad::Z) {
        mConfirm = CONFIRM_RESET;
        return UPDATE_NONE;
    }
    if (pressed & TMarioGamePad::START) {
        const int count = mTargetSlots + 1;
        const int direction = (pad->mButtons.mInput & TMarioGamePad::X) ? -1 : 1;
        mTextTarget = (u16)((mTextTarget + count + direction) % count);
    }

    const u32 repeat = repeatInput(pad);
    const u32 layout =
        ((mCapabilities & CAP_POSITION)
             ? pad->mButtons.mRapidInput &
                   (TMarioGamePad::DPAD_LEFT | TMarioGamePad::DPAD_RIGHT |
                    TMarioGamePad::DPAD_UP | TMarioGamePad::DPAD_DOWN)
             : 0) |
        ((mCapabilities & CAP_SCALE)
             ? repeat & (TMarioGamePad::L | TMarioGamePad::R)
             : 0);
    if (LayoutEditor::updatePositionScale(
            layout & ~(TMarioGamePad::L | TMarioGamePad::R),
            mStyle->x, mStyle->y, mStyle->scale, sCreationMaximumScale,
            (mCapabilities & CAP_OFFSET_POSITION) ? 1280 : 640,
            (mCapabilities & CAP_OFFSET_POSITION) ? 960 : 480)) {
        result |= UPDATE_CHANGED;
    }
    if (layout & (TMarioGamePad::L | TMarioGamePad::R)) {
        const int delta = (layout & TMarioGamePad::L ? -2 : 0) +
                          (layout & TMarioGamePad::R ? 2 : 0);
        mStyle->scale = (u8)clampi(mStyle->scale + delta,
                                  sCreationMinimumScale, sCreationMaximumScale);
        result |= UPDATE_CHANGED;
    }

    if (repeat & TMarioGamePad::CSTICK_UP) {
        moveOption(-1);
    } else if (repeat & TMarioGamePad::CSTICK_DOWN) {
        moveOption(1);
    }

    int delta = 0;
    const int step = (pad->mButtons.mInput & TMarioGamePad::Y) ? 1 : 4;
    if (repeat & TMarioGamePad::CSTICK_LEFT) delta = -step;
    if (repeat & TMarioGamePad::CSTICK_RIGHT) delta = step;
    if (!delta || !optionEnabled(mOption)) return result;

    if (mOption >= OPTION_GRADIENT_DIRECTION) {
        gSettings.cycle(gradientSetting(mOption), delta > 0 ? 1 : -1);
        return result | UPDATE_CHANGED;
    } else if (mOption == OPTION_GRADIENT) {
        const bool captureEnds = !sGradientPreset;
        sGradientPreset = delta > 0 ? sGradientPreset % 5 + 1 :
                          sGradientPreset > 1 ? sGradientPreset - 1 : 5;
        mTextTarget = 0;
        applyGradient(mTextRgb, mTargetSlots, sGradientPreset,
                      mCapabilities & CAP_TIMER_GRADIENT, captureEnds);
        return result | UPDATE_CHANGED | UPDATE_COLOR_CHANGED;
    } else if (mOption == OPTION_COLOR_MODE) {
        const u16 mask = mTextTarget ? 1u << (mTextTarget - 1)
                                    : (1u << mTextSlots) - 1u;
        if (delta > 0) *mCustomMask |= mask;
        else *mCustomMask &= ~mask;
        return result | UPDATE_CHANGED | UPDATE_MODE_CHANGED;
    } else if (mOption <= OPTION_TEXT_L) {
        sGradientPreset = 0;
        adjustTextChannel(mTextRgb, mTextSlots, mTextTarget,
                           mOption - OPTION_TEXT_H, delta);
        if (mCustomMask && (mCapabilities & CAP_RGB_ENABLES_CUSTOM))
            *mCustomMask |= mTextTarget ? 1u << (mTextTarget - 1)
                                        : (1u << mTextSlots) - 1u;
    } else if (mOption >= OPTION_BG_H && mOption <= OPTION_BG_L) {
        const int channel = mOption - OPTION_BG_H;
        sHsl[mTextSlots].channel[channel] = CreationColor::adjusted(
            sHsl[mTextSlots].channel[channel], channel, delta);
        CreationColor::toRgb(sHsl[mTextSlots], &mStyle->bgR);
    } else if (mOption == OPTION_PADDING) {
        if (mStyle->padding == 0xff) {
            if (delta > 0) mStyle->padding = 0;
        } else if (mStyle->padding == 0 && delta < 0) {
            mStyle->padding = 0xff;
        } else {
            mStyle->padding = (u8)clampi(
                (int)mStyle->padding + (delta > 0 ? 1 : -1), 0, 16);
        }
    } else {
        u8 &value = styleValue(*mStyle, mOption);
        const int lo = mOption == OPTION_TEXT_BRIGHTNESS ? 25 : 0;
        const int hi = mOption == OPTION_TEXT_BRIGHTNESS ? 200 : 255;
        value = (u8)clampi((int)value + delta, lo, hi);
    }
    return result | UPDATE_CHANGED | (mOption <= OPTION_TEXT_L ? UPDATE_COLOR_CHANGED : 0);
}

void CreationEditor::draw(Menu *menu, const char *title, const char *preview) const {
    if (!menu || !mStyle) return;
    if (NumberEditor::active(this)) { NumberEditor::draw(menu); return; }

    const bool offsets = mCapabilities & CAP_OFFSET_POSITION;
    const int previewY = offsets ? (int)mStyle->y - 480 + 419 : mStyle->y;
    const int panelY = previewY < 224 ? 264 : 8;
    int optionCount = 0;
    for (int i = 0; i < OPTION_COUNT; i++)
        if (optionEnabled((u8)i)) optionCount++;
    const bool layoutControls = mCapabilities & (CAP_POSITION | CAP_SCALE);
    const int optionRows = optionCount > 10 ? (optionCount + 1) / 2 : optionCount > 5 ? 5 : optionCount;
    const bool colorModes = optionEnabled(OPTION_COLOR_MODE);
    const int panelH = 92 + optionRows * 14 + (layoutControls ? 17 : 0) +
                       (colorModes ? 14 : 0);
    menu->fillBox(8, panelY, 624, panelH, Color(0, 0, 0, 215));

    menu->drawText(title, 18, panelY + 9, 16, 16,
                   Color(255, 255, 255, 255));

    char status[128];
    const bool styleControls = mCapabilities &
        (CAP_TEXT_ALPHA | CAP_BRIGHTNESS | CAP_BACKGROUND |
         CAP_PADDING | CAP_TEXT_COLOR);
    if (styleControls) {
        char targetBuf[24];
        const char *target = targetLabel(mTextTarget, preview, mTargetNames,
                                         targetBuf, sizeof(targetBuf));
        if (mTextTarget == 0)
            snprintf(status, sizeof(status), mTargetNames ? "All elements"
                                                           : "All characters");
        else if (mTargetNames)
            snprintf(status, sizeof(status), "%s", target);
        else
            snprintf(status, sizeof(status), "Character %s", target);
        menu->drawText(status, 622 - Menu::textWidth(status, 12), panelY + 11,
                       12, 12, Color(190, 220, 255, 255));
    }

    int infoY = panelY + 29;
    if (layoutControls) {
        snprintf(status, sizeof(status), "Position X:%d Y:%d   Size:%u pct",
                 offsets ? (int)mStyle->x - 640 : mStyle->x,
                 offsets ? (int)mStyle->y - 480 : mStyle->y, mStyle->scale);
        menu->drawText(status, 18, infoY, 12, 12,
                       Color(190, 220, 255, 255));
        infoY += 17;
    }

    if (mCapabilities & (CAP_TEXT_COLOR | CAP_BACKGROUND)) {
        u16 hue, saturation, lightness;
        const u16 bgH = CreationColor::display(sHsl[mTextSlots], 0);
        const u16 bgS = CreationColor::display(sHsl[mTextSlots], 1);
        const u16 bgL = CreationColor::display(sHsl[mTextSlots], 2);
        const bool sameH = textChannel(mTextRgb, mTextSlots, mTextTarget, 0, &hue);
        const bool sameS = textChannel(mTextRgb, mTextSlots, mTextTarget, 1, &saturation);
        const bool sameL = textChannel(mTextRgb, mTextSlots, mTextTarget, 2, &lightness);
        const char *hslLabel = mTargetNames ? "Element HSL"
            : (mTextTarget == 0 ? "Text HSL" : "Character HSL");
        if (sameH && sameS && sameL && (mCapabilities & CAP_BACKGROUND)) {
            snprintf(status, sizeof(status),
                     "%s:%03u,%03u,%03u   Background HSL:%03u,%03u,%03u",
                     hslLabel, hue, saturation, lightness, bgH, bgS, bgL);
        } else if (mCapabilities & CAP_BACKGROUND) {
            snprintf(status, sizeof(status),
                     "%s: Mixed   Background HSL:%03u,%03u,%03u",
                     hslLabel, bgH, bgS, bgL);
        } else if (sameH && sameS && sameL) {
            snprintf(status, sizeof(status), "%s:%03u,%03u,%03u",
                     hslLabel, hue, saturation, lightness);
        } else {
            snprintf(status, sizeof(status), "%s: Mixed", hslLabel);
        }
        menu->drawText(status, 18, infoY, 11, 11,
                       Color(190, 220, 255, 255));
        infoY += 18;
    }

    if (colorModes) {
        menu->drawText((mCapabilities & CAP_RGB_ENABLES_CUSTOM)
                           ? "Original: retail colours   Custom: your HSL   Colour edits select Custom"
                           : "Original: tint retail colours   Custom: your colours with black outlines",
                       18, infoY, 9, 9, Color(190, 220, 255, 255));
        infoY += 14;
    }

    int shown = 0;
    for (int order = 0; order < OPTION_COUNT; order++) {
        const int i = order < 5 ? OPTION_COLOR_MODE + order : order - 5;
        if (!optionEnabled((u8)i)) continue;
        const int column = shown / optionRows;
        const int row = shown % optionRows;
        const int x = 18 + column * 306;
        const int y = infoY + row * 14;
        const bool selected = i == mOption;
        if (selected) {
            menu->fillBox(x - 3, y - 1, 294, 14, Color(90, 170, 255, 60));
            menu->drawText(">", x, y, 11, 11, Color(90, 170, 255, 255));
        }
        const char *optionName = i == OPTION_GRADIENT_SPEED ? "Animation speed" :
            i == OPTION_GRADIENT_MOTION ? "Gradient animation" :
            i == OPTION_GRADIENT_DIRECTION ? "Gradient direction" : i == OPTION_COLOR_MODE ? "Appearance" : i == OPTION_GRADIENT ? "Colour preset" : PackedText::at(
            mTargetNames && i <= OPTION_TEXT_BRIGHTNESS
                ? kElementOptionNames : kOptionNames, i);
        menu->drawText(optionName, x + 12, y, 11, 11,
                       selected ? Color(255, 255, 255, 255)
                                : Color(200, 206, 220, 255));

        const char *value = status;
        if (i == OPTION_GRADIENT_MOTION || i == OPTION_GRADIENT_SPEED) {
            value = gSettings.valueLabel(gradientSetting(i));
        } else if (i == OPTION_GRADIENT_DIRECTION) {
            value = gSettings.getBool((SettingId)sGradientDirectionSetting) ? "Vertical" : "Horizontal";
        } else if (i == OPTION_GRADIENT) {
            value = PackedText::at(kGradientNames, sGradientPreset);
        } else if (i == OPTION_COLOR_MODE) {
            const u16 mask = mTextTarget ? 1u << (mTextTarget - 1)
                                        : (1u << mTextSlots) - 1u;
            value = !(*mCustomMask & mask) ? "Original" :
                    (*mCustomMask & mask) == mask ? "Custom" : "Mixed";
        } else if (i <= OPTION_TEXT_L) {
            u16 v;
            if (textChannel(mTextRgb, mTextSlots, mTextTarget, i, &v))
                snprintf(status, sizeof(status), i ? "%u pct" : "%u deg", v);
            else
                value = "Mixed";
        } else if (i >= OPTION_BG_H && i <= OPTION_BG_L) {
            const int channel = i - OPTION_BG_H;
            snprintf(status, sizeof(status), channel ? "%u pct" : "%u deg",
                     CreationColor::display(sHsl[mTextSlots], channel));
        } else {
            const u8 scalar = styleValue(*mStyle, i);
            if (i == OPTION_PADDING && scalar == 0xff)
                value = "Off";
            else if (i == OPTION_TEXT_BRIGHTNESS)
                snprintf(status, sizeof(status), "%u pct", scalar);
            else
                snprintf(status, sizeof(status), "%u", scalar);
        }
        menu->drawText(value, x + 282 - Menu::textWidth(value, 11), y,
                       11, 11, Color(120, 220, 150, 255));
        shown++;
    }

    if (optionCount) {
        const char *controls = SUSAMUNE_GLYPH_C " U" SUSAMUNE_GLYPH_SLASH
                               "D Option   " SUSAMUNE_GLYPH_C " L"
                               SUSAMUNE_GLYPH_SLASH
                               "R Change   START: Next part   " SUSAMUNE_GLYPH_X
                               "+START: Previous";
        menu->drawText(controls, 18, panelY + panelH - 44, 9, 9,
                       Color(150, 170, 205, 255));
        menu->drawText(mOption == OPTION_GRADIENT_MOTION || mOption == OPTION_GRADIENT_SPEED
                           ? "Flow moves your colours. Pulse gently dims/brightens. Slow 8s / Normal 4s / Fast 2s."
                           : mOption == OPTION_GRADIENT_DIRECTION
                           ? (mCapabilities & CAP_TIMER_GRADIENT)
                                 ? "Top/bottom colours: normal digits 1/6; countdown digits 1/4."
                                 : "Vertical uses the first colour at the top and the last at the bottom."
                           : mOption == OPTION_GRADIENT
                           ? (mCapabilities & CAP_TIMER_GRADIENT)
                                 ? "All digits + separators. TIME image/background stay unchanged."
                                 : "All text. Blend ends: first to last colour. One colour: use first colour."
                           : "Hold " SUSAMUNE_GLYPH_Y " while adjusting: step 1 (normal 4)",
                       18, panelY + panelH - 32, 9, 9,
                       Color(150, 170, 205, 255));
    }
    if (layoutControls)
        menu->drawText("D-pad Move   L" SUSAMUNE_GLYPH_SLASH "R Size   X+A: Enter size",
                       18, panelY + panelH - 17, 9, 9,
                       Color(150, 170, 205, 255));
    const char *finish = SUSAMUNE_GLYPH_A " Keep  " SUSAMUNE_GLYPH_B
                         " Cancel  " SUSAMUNE_GLYPH_Z " Reset";
    menu->drawText(finish, 622 - Menu::textWidth(finish, 9), panelY + panelH - 17,
                   9, 9, Color(150, 170, 205, 255));

    if (mConfirm != CONFIRM_NONE) {
        const int boxY = panelY + (panelH - 78) / 2;
        menu->fillBox(128, boxY, 384, 78, Color(8, 11, 20, 245));
        const char *prompt = mConfirm == CONFIRM_KEEP
                                 ? "Keep these changes?"
                             : mConfirm == CONFIRM_CANCEL
                                 ? "Discard all changes?"
                                 : "Reset selected option?";
        menu->drawText(prompt, 320 - Menu::textWidth(prompt, 15) / 2,
                       boxY + 13, 15, 15, Color(255, 255, 255, 255));
        const char *answer = SUSAMUNE_GLYPH_A " Confirm    "
                             SUSAMUNE_GLYPH_B " Go Back";
        menu->drawText(answer, 320 - Menu::textWidth(answer, 12) / 2,
                       boxY + 47, 12, 12, Color(190, 220, 255, 255));
    }
}

namespace Creation {

void fillWhite(u8 (*out)[3], u16 slots) {
    for (u16 i = 0; i < slots; i++) {
        out[i][0] = 255;
        out[i][1] = 255;
        out[i][2] = 255;
    }
}

int glyphCount(const char *text) {
    int count = 0;
    while (text && *text) {
        text += glyphBytes(text);
        count++;
    }
    return count;
}

int textWidth(const char *text, int size) {
    if (!text) return 0;
    int count;
    return splitTextWidth(text, size, &count);
}

#pragma clang section text=".foxtrot.text"
void drawTextLine(Menu *menu, const CreationStyle &style,
                  const u8 (*textRgb)[3], u16 textSlots, const char *text,
                  int x, int y, int size, u16 firstSlot, bool shadow,
                  u16 selectedSlot) {
    if (!menu || !text || !textRgb || textSlots == 0) return;
    if (shadow) {
        menu->drawText(text, x + 1, y + 1, size, size, Color(0, 0, 0, 220));
    }
    const bool vertical = gQftDisplay.verticalGradient(textRgb);
    const u8 motion = gQftDisplay.animatedGradient(textRgb) ? GradientMotion::mode(false) : 0;
    const u16 phase = motion ? GradientMotion::phase(false) : 0;

    char run[192];
    int byte = 0;
    int glyph = 0;
    int drawX = x;
    int arrowCentre = -1;
    while (text[byte]) {
        const int startByte = byte;
        const u16 logicalSlot = (u16)(firstSlot + glyph);
        const u16 colorSlot = logicalSlot < textSlots ? logicalSlot : textSlots - 1;
        u8 moving[3];
        if (motion) GradientMotion::sample(textRgb, textSlots, colorSlot, motion, phase, moving);
        const u8 *rgb = motion ? moving : textRgb[colorSlot];
        const bool selectedRun = logicalSlot == selectedSlot;

        do {
            byte += glyphBytes(text + byte);
            glyph++;
            if (!text[byte]) break;
            const u16 nextLogical = (u16)(firstSlot + glyph);
            const u16 nextSlot = nextLogical < textSlots ? nextLogical : textSlots - 1;
            if (selectedRun || nextLogical == selectedSlot) break;
            if (motion && !vertical) break;
            if (!vertical && (textRgb[nextSlot][0] != rgb[0] || textRgb[nextSlot][1] != rgb[1] ||
                textRgb[nextSlot][2] != rgb[2])) break;
        } while (byte - startByte + 1 < (int)sizeof(run));

        int runBytes = byte - startByte;
        for (int i = 0; i < runBytes; i++) run[i] = text[startByte + i];
        run[runBytes] = '\0';
        if (vertical) {
            u8 ends[2][3];
            if (motion) {
                GradientMotion::sample(textRgb, textSlots, 0, motion, phase, ends[0]);
                GradientMotion::sample(textRgb, textSlots, textSlots - 1, motion, phase, ends[1]);
            }
            const u8 *first = motion ? ends[0] : textRgb[0];
            const u8 *last = motion ? ends[1] : textRgb[textSlots - 1];
            menu->drawTextVertical(run, drawX, y, size,
                Color(lit(first[0], style.textBrightness), lit(first[1], style.textBrightness),
                      lit(first[2], style.textBrightness), style.textA),
                Color(lit(last[0], style.textBrightness), lit(last[1], style.textBrightness),
                      lit(last[2], style.textBrightness), style.textA));
        } else {
            menu->drawText(run, drawX, y, size, size,
                           Color(lit(rgb[0], style.textBrightness),
                                 lit(rgb[1], style.textBrightness),
                                 lit(rgb[2], style.textBrightness), style.textA));
        }
        const int runWidth = Menu::textWidth(run, size);
        if (selectedRun) arrowCentre = drawX + runWidth / 2;
        drawX += runWidth;
    }

    if (arrowCentre >= 0) {
        int top = y - 8;
        if (top < 0) top = 0;
        const s16 arrow[6] = {
            (s16)(arrowCentre - 4), (s16)top,
            (s16)(arrowCentre + 4), (s16)top,
            (s16)arrowCentre,       (s16)(top + 6),
        };
        menu->fillPoly(arrow, 3, Color(90, 170, 255, 255));
    }
}

#pragma clang section text=""
void drawTextBox(Menu *menu, const CreationStyle &style,
                 const u8 (*textRgb)[3], u16 textSlots, const char *text,
                 bool rightAlignSlots, u16 selectedSlot) {
    if (!menu || !text) return;
    const int size = clampi(20 * (int)style.scale / 100, 10, 40);
    const int pad  = style.padding == 0xff ? 0 : style.padding;
    int count;
    const int w = splitTextWidth(text, size, &count);
    if (style.padding != 0xff) {
        menu->fillBox((int)style.x - pad, (int)style.y - pad,
                      w + pad * 2, size + pad * 2,
                      Color(style.bgR, style.bgG, style.bgB, style.bgA));
    }
    const u16 first = rightAlignSlots && count < textSlots
                          ? (u16)(textSlots - count) : 0;
    drawTextLine(menu, style, textRgb, textSlots, text, style.x, style.y,
                 size, first, false, selectedSlot);
}

}  // namespace Creation
