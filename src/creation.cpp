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
#include "susamune/menu_theme.hxx"
#include "susamune/menu_theme_assets.hxx"
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
    OPTION_GRADIENT_STOPS,
    OPTION_GRADIENT_STOP,
    OPTION_ORIGINAL_COLOURS,
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
u8 *sGradientOptions;
u8 sGradientOptionsBackup, sGradientStop;
bool sGradientLocalAnimation;
u16 sOriginalColourSetting;
u8 sOriginalColourBackup, sEditorHomeRow;
enum { GROUP_LAYOUT, GROUP_COLOURS, GROUP_ANIMATION, GROUP_COUNT, GROUP_HOME = GROUP_COUNT };
const char kGroupNames[] = "Position & size\0Colours\0Animation";
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

unsigned stopIndex(unsigned stop, unsigned count, unsigned slots) {
    return count > 1 ? (stop * (slots - 1) + (count - 1) / 2) / (count - 1) : 0;
}

void blendStops(u8 (*rgb)[3], unsigned slots, const u8 stops[5][3], unsigned count) {
    if (!slots || !count) return;
    for (unsigned i = 0; i < slots; ++i) {
        if (count == 1) {
            for (unsigned c = 0; c < 3; ++c) rgb[i][c] = stops[0][c];
            continue;
        }
        unsigned segment = 0;
        while (segment + 1 < count && i > stopIndex(segment + 1, count, slots)) ++segment;
        const unsigned first = stopIndex(segment, count, slots);
        const unsigned next = segment + 1 < count ? segment + 1 : segment;
        const unsigned last = stopIndex(next, count, slots);
        const unsigned span = last > first ? last - first : 1;
        for (unsigned c = 0; c < 3; ++c)
            rgb[i][c] = (stops[segment][c] * (span - (i - first)) +
                         stops[next][c] * (i - first) + span / 2) / span;
    }
}

void editGradientStops(u8 (*rgb)[3], unsigned slots, bool timer,
                       unsigned count, int channel = -1, int delta = 0) {
    // Six normal digits store every anchor, including a five-stop countdown.
    const unsigned sourceSlots = timer ? 6 : slots;
    u8 stops[5][3];
    for (unsigned i = 0; i < count; ++i)
        for (unsigned c = 0; c < 3; ++c)
            stops[i][c] = rgb[stopIndex(i, count, sourceSlots)][c];
    if (channel >= 0) {
        CreationColor::Hsl color = CreationColor::fromRgb(stops[sGradientStop]);
        color.channel[channel] = CreationColor::adjusted(color.channel[channel], channel, delta);
        CreationColor::toRgb(color, stops[sGradientStop]);
    }
    blendStops(rgb, sourceSlots, stops, count);
    if (timer) {
        // Sample the full palette; four countdown digits need not own anchors.
        for (unsigned i = 0; i < 4; ++i) {
            const unsigned position = i * 5 * 256 / 3, first = position >> 8;
            const unsigned next = first < 5 ? first + 1 : first, weight = position & 255;
            for (unsigned c = 0; c < 3; ++c)
                rgb[6 + i][c] = (rgb[first][c] * (256 - weight) + rgb[next][c] * weight + 128) >> 8;
        }
        const u8 before[] = {1, 3, 7};
        for (unsigned i = 0; i < 3; ++i)
            for (unsigned c = 0; c < 3; ++c)
                rgb[10 + i][c] = (rgb[before[i]][c] + rgb[before[i] + 1][c] + 1) / 2;
    }
    for (unsigned i = 0; i < slots; ++i) sHsl[i] = CreationColor::fromRgb(rgb[i]);
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
    mGroup        = GROUP_COLOURS;
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
    sGradientOptions = nullptr;
    sGradientLocalAnimation = false;
    sGradientStop = 0;
    mGroup = GROUP_HOME;
    sEditorHomeRow = capabilities & (CAP_POSITION | CAP_SCALE) ? GROUP_LAYOUT : GROUP_COLOURS;
    sOriginalColourSetting = 0xffff;
    sCreationMinimumScale = 50;
    sCreationMaximumScale = 200;
    NumberEditor::cancel(this);
}

void CreationEditor::setOriginalColourSetting(u16 setting) {
    sOriginalColourSetting = setting;
    sOriginalColourBackup = gSettings.get((SettingId)setting);
    mOption = OPTION_ORIGINAL_COLOURS;
}

void CreationEditor::setGradientOptions(u8 *options, bool animation) {
    sGradientOptions = options;
    sGradientOptionsBackup = *options;
    sGradientLocalAnimation = animation;
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
    if (option == OPTION_ORIGINAL_COLOURS) return sOriginalColourSetting != 0xffff;
    if (option == OPTION_GRADIENT_STOPS) return sGradientOptions != nullptr;
    if (option == OPTION_GRADIENT_STOP) return sGradientOptions && GradientMotion::wordStops(*sGradientOptions);
    if (option >= OPTION_GRADIENT_MOTION && option <= OPTION_GRADIENT_SPEED && sGradientLocalAnimation)
        return true;
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

bool CreationEditor::groupEnabled(u8 group) const {
    if (group == GROUP_LAYOUT) return mCapabilities & (CAP_POSITION | CAP_SCALE);
    if (group == GROUP_ANIMATION) return optionEnabled(OPTION_GRADIENT_MOTION);
    return mCapabilities & (CAP_TEXT_COLOR | CAP_BACKGROUND | CAP_TEXT_ALPHA | CAP_BRIGHTNESS | CAP_PADDING);
}

bool CreationEditor::optionInGroup(u8 option) const {
    if (!optionEnabled(option)) return false;
    if (mGroup == GROUP_ANIMATION)
        return option == OPTION_GRADIENT_MOTION || option == OPTION_GRADIENT_SPEED;
    return mGroup == GROUP_COLOURS && option != OPTION_GRADIENT_MOTION && option != OPTION_GRADIENT_SPEED;
}

void CreationEditor::moveOption(int direction) {
    const u8 first = mOption;
    // The colour-mode/gradient group is listed first, as draw() shows it.
    const int lead = OPTION_COUNT - OPTION_COLOR_MODE;
    do {
        const int order = mOption >= OPTION_COLOR_MODE ? mOption - OPTION_COLOR_MODE : mOption + lead;
        const int next = (order + OPTION_COUNT + direction) % OPTION_COUNT;
        mOption = next < lead ? OPTION_COLOR_MODE + next : next - lead;
    } while (!optionInGroup(mOption) && mOption != first);
}

u32 CreationEditor::repeatInput(TMarioGamePad *pad) {
    const u32 mask = TMarioGamePad::DPAD_UP | TMarioGamePad::DPAD_DOWN |
                     TMarioGamePad::CSTICK_UP | TMarioGamePad::CSTICK_DOWN |
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
                if (sOriginalColourSetting != 0xffff)
                    gSettings.set((SettingId)sOriginalColourSetting, sOriginalColourBackup);
                if (sGradientOptions) *sGradientOptions = sGradientOptionsBackup;
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
            if (mOption == OPTION_ORIGINAL_COLOURS && mGroup == GROUP_COLOURS) {
                gSettings.set((SettingId)sOriginalColourSetting, 0);
            } else if (mGroup == GROUP_LAYOUT) {
                if (mCapabilities & CAP_POSITION) { mStyle->x = defaults.x; mStyle->y = defaults.y; }
                if (mCapabilities & CAP_SCALE) mStyle->scale = defaults.scale;
            } else if (mOption == OPTION_GRADIENT_STOPS || mOption == OPTION_GRADIENT_STOP) {
                *sGradientOptions = GradientMotion::withWordStops(*sGradientOptions, 0);
                sGradientStop = 0;
                resetOption(*mStyle, defaults, mTextRgb, defaultRgb,
                            defaultRgbSlots, mCapabilities & CAP_TIMER_GRADIENT ? 13 : mTextSlots, OPTION_GRADIENT, 0);
                mTextTarget = 0;
            } else if (sGradientLocalAnimation && mOption >= OPTION_GRADIENT_MOTION && mOption <= OPTION_GRADIENT_SPEED) {
                *sGradientOptions = mOption == OPTION_GRADIENT_SPEED ?
                    GradientMotion::withWordSpeed(*sGradientOptions, 1) :
                    GradientMotion::withWordMotion(*sGradientOptions, GradientMotion::Off);
            } else if (mOption >= OPTION_GRADIENT_DIRECTION && mOption <= OPTION_GRADIENT_SPEED) {
                gSettings.set(gradientSetting(mOption), mOption == OPTION_GRADIENT_SPEED ? 1 : 0);
            } else if (mOption == OPTION_COLOR_MODE && mCustomMask) {
                const u16 mask = mTextTarget ? 1u << (mTextTarget - 1)
                                            : (1u << mTextSlots) - 1u;
                *mCustomMask &= ~mask;
            } else if (optionEnabled(mOption)) {
                const unsigned stops = sGradientOptions ? GradientMotion::wordStops(*sGradientOptions) : 0;
                const u16 resetSlots = mOption == OPTION_GRADIENT
                    ? (mCapabilities & CAP_TIMER_GRADIENT) ? 13 : mTargetSlots : mTextSlots;
                const u16 target = stops && mOption <= OPTION_TEXT_L
                    ? stopIndex(sGradientStop, stops, mCapabilities & CAP_TIMER_GRADIENT ? 6 : mTextSlots) + 1
                    : mTextTarget;
                resetOption(*mStyle, defaults, mTextRgb, defaultRgb,
                            defaultRgbSlots, resetSlots, mOption, target);
                if (stops && mOption <= OPTION_TEXT_L)
                    editGradientStops(mTextRgb, mTextSlots, mCapabilities & CAP_TIMER_GRADIENT, stops);
                if (mOption == OPTION_GRADIENT) {
                    mTextTarget = 0;
                    if (sGradientOptions) *sGradientOptions = GradientMotion::withWordStops(*sGradientOptions, 0);
                }
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
            return UPDATE_CHANGED | (mOption <= OPTION_TEXT_L || mOption == OPTION_GRADIENT || mOption == OPTION_GRADIENT_STOPS || mOption == OPTION_GRADIENT_STOP ? UPDATE_COLOR_CHANGED : 0) |
                   (mOption == OPTION_COLOR_MODE ? UPDATE_MODE_CHANGED : 0);
        }
        if (pressed & TMarioGamePad::B) mConfirm = CONFIRM_NONE;
        return UPDATE_NONE;
    }

    if (mGroup == GROUP_HOME) {
        const u32 nav = repeatInput(pad);
        const int direction = nav & (TMarioGamePad::CSTICK_UP | TMarioGamePad::DPAD_UP) ? -1 :
                              nav & (TMarioGamePad::CSTICK_DOWN | TMarioGamePad::DPAD_DOWN) ? 1 : 0;
        if (direction) do { sEditorHomeRow = (sEditorHomeRow + GROUP_COUNT + 2 + direction) % (GROUP_COUNT + 2); }
            while (sEditorHomeRow < GROUP_COUNT && !groupEnabled(sEditorHomeRow));
        if (pressed & TMarioGamePad::A) {
            if (sEditorHomeRow < GROUP_COUNT) {
                mGroup = sEditorHomeRow;
                if (mGroup >= GROUP_COLOURS && !optionInGroup(mOption)) moveOption(1);
            } else if (sEditorHomeRow == GROUP_COUNT) {
                mEditing = false;
                return UPDATE_FINISHED;
            } else mConfirm = CONFIRM_CANCEL;
        } else if (pressed & TMarioGamePad::B) mConfirm = CONFIRM_CANCEL;
        else if (pressed & TMarioGamePad::START) mConfirm = CONFIRM_KEEP;
        return UPDATE_NONE;
    }
    if ((pressed & TMarioGamePad::A) && mGroup == GROUP_LAYOUT && (mCapabilities & CAP_SCALE)) {
        NumberEditor::begin(this, "Display size", mStyle->scale,
                            sCreationMinimumScale, sCreationMaximumScale, " pct");
        return UPDATE_NONE;
    }
    if (pressed & (TMarioGamePad::A | TMarioGamePad::B)) {
        sEditorHomeRow = mGroup;
        mGroup = GROUP_HOME;
        return UPDATE_NONE;
    }
    u8 result = UPDATE_NONE;
    if (pressed & TMarioGamePad::Z) {
        mConfirm = CONFIRM_RESET;
        return UPDATE_NONE;
    }
    if (pressed & TMarioGamePad::START) {
        mConfirm = CONFIRM_KEEP;
        return UPDATE_NONE;
    }
    if (pressed & TMarioGamePad::X) {
        if (sGradientOptions && GradientMotion::wordStops(*sGradientOptions)) {
            const unsigned count = GradientMotion::wordStops(*sGradientOptions);
            sGradientStop = (sGradientStop + count + ((pad->mButtons.mInput & TMarioGamePad::Y) ? -1 : 1)) % count;
            return UPDATE_NONE;
        }
        const int count = mTargetSlots + 1;
        const int direction = (pad->mButtons.mInput & TMarioGamePad::Y) ? -1 : 1;
        mTextTarget = (u16)((mTextTarget + count + direction) % count);
    }

    const u32 repeat = repeatInput(pad);
    const u32 layout =
        ((mGroup == GROUP_LAYOUT && (mCapabilities & CAP_POSITION))
             ? pad->mButtons.mRapidInput &
                   (TMarioGamePad::DPAD_LEFT | TMarioGamePad::DPAD_RIGHT |
                    TMarioGamePad::DPAD_UP | TMarioGamePad::DPAD_DOWN)
             : 0) |
        ((mGroup == GROUP_LAYOUT && (mCapabilities & CAP_SCALE))
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
    if (!delta || !optionInGroup(mOption)) return result;

    if (mOption == OPTION_ORIGINAL_COLOURS) {
        gSettings.cycle((SettingId)sOriginalColourSetting, delta > 0 ? 1 : -1);
        return result | UPDATE_CHANGED;
    }
    if (mOption <= OPTION_TEXT_L && sOriginalColourSetting != 0xffff)
        gSettings.set((SettingId)sOriginalColourSetting, 1);
    if (mOption == OPTION_GRADIENT_STOPS) {
        const unsigned count = (GradientMotion::wordStops(*sGradientOptions) + (delta > 0 ? 1 : 5)) % 6;
        *sGradientOptions = GradientMotion::withWordStops(*sGradientOptions, count);
        sGradientStop = 0;
        mTextTarget = 0;
        if (count) editGradientStops(mTextRgb, mTextSlots,
                                      mCapabilities & CAP_TIMER_GRADIENT, count);
        return result | UPDATE_CHANGED | UPDATE_COLOR_CHANGED;
    } else if (mOption == OPTION_GRADIENT_STOP) {
        const unsigned count = GradientMotion::wordStops(*sGradientOptions);
        sGradientStop = (sGradientStop + count + (delta > 0 ? 1 : -1)) % count;
        return result;
    } else if (sGradientLocalAnimation && mOption >= OPTION_GRADIENT_MOTION && mOption <= OPTION_GRADIENT_SPEED) {
        const unsigned count = mOption == OPTION_GRADIENT_SPEED ? 3 : GradientMotion::Count;
        const unsigned old = mOption == OPTION_GRADIENT_SPEED ? GradientMotion::wordSpeed(*sGradientOptions) : GradientMotion::wordMotion(*sGradientOptions);
        const unsigned value = (old + count + (delta > 0 ? 1 : -1)) % count;
        *sGradientOptions = mOption == OPTION_GRADIENT_SPEED ?
            GradientMotion::withWordSpeed(*sGradientOptions, value) : GradientMotion::withWordMotion(*sGradientOptions, value);
        return result | UPDATE_CHANGED;
    } else if (mOption >= OPTION_GRADIENT_DIRECTION && mOption <= OPTION_GRADIENT_SPEED) {
        gSettings.cycle(gradientSetting(mOption), delta > 0 ? 1 : -1);
        return result | UPDATE_CHANGED;
    } else if (mOption == OPTION_GRADIENT) {
        const bool captureEnds = !sGradientPreset;
        sGradientPreset = delta > 0 ? sGradientPreset % 5 + 1 :
                          sGradientPreset > 1 ? sGradientPreset - 1 : 5;
        mTextTarget = 0;
        if (sGradientOptions) *sGradientOptions = GradientMotion::withWordStops(*sGradientOptions, 0);
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
        if (sGradientOptions && GradientMotion::wordStops(*sGradientOptions)) {
            editGradientStops(mTextRgb, mTextSlots, mCapabilities & CAP_TIMER_GRADIENT,
                              GradientMotion::wordStops(*sGradientOptions), mOption, delta);
            mTextTarget = 0;
            return result | UPDATE_CHANGED | UPDATE_COLOR_CHANGED;
        }
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
    const int top = previewY < 224 ? 228 : 8;
    const Color ink = MenuTheme::textColor(), muted = MenuTheme::textColor(true);
    const Color selectedInk(255, 248, 209, 255);
    MenuTheme::panel(menu, 8, top, 624, 212, title, MenuThemeAssets::TabGlasses);
    menu->drawText("LIVE PREVIEW", 513, top + 8, 11, 11, Color(245, 221, 117, 255));
    if (mGroup == GROUP_HOME) {
        int y = top + 34;
        for (unsigned row = 0; row < GROUP_COUNT + 2; ++row) {
            if (row < GROUP_COUNT && !groupEnabled(row)) continue;
            const char *label = row < GROUP_COUNT ? PackedText::at(kGroupNames, row) :
                                row == GROUP_COUNT ? "Save changes" : "Discard changes";
            if (row == sEditorHomeRow) {
                MenuTheme::selection(menu, 20, y - 1, 600, 23, true);
            }
            menu->drawText(label, 48, y + 1, 16, 16, row == sEditorHomeRow ? selectedInk : ink);
            const char *hint = row == GROUP_LAYOUT ? "Move and resize" : row == GROUP_COLOURS ? "Palette and background" :
                row == GROUP_ANIMATION ? "Style and speed" : row == GROUP_COUNT ? "Keep this look" : "Restore the previous look";
            menu->drawText(hint, 348, y + 4, 12, 12, row == sEditorHomeRow ? selectedInk : muted);
            y += 24;
        }
    } else {
        menu->drawText(PackedText::at(kGroupNames, mGroup), 28, top + 32, 17, 17, ink);
    }
    char status[96];
    if (mGroup == GROUP_HOME) {
        // The item page owns its controls; the live preview remains underneath.
    } else if (mGroup == GROUP_LAYOUT) {
        snprintf(status, sizeof(status), "X: %d     Y: %d     Size: %u pct",
                 offsets ? (int)mStyle->x - 640 : mStyle->x,
                 offsets ? (int)mStyle->y - 480 : mStyle->y, mStyle->scale);
        menu->drawText(status, 28, top + 73, 18, 18, ink);
        const char *controls = !(mCapabilities & CAP_SCALE) ? "D-pad: move" :
            mCapabilities & CAP_POSITION ? "D-pad: move     L / R: resize     A: enter size" :
            "L / R: resize     A: enter size";
        menu->drawText(controls,
                       28, top + 108, 14, 14, ink);
        menu->drawText("The preview stays at its actual screen position.", 28, top + 139, 12, 12, muted);
    } else {
        const unsigned stops = sGradientOptions ? GradientMotion::wordStops(*sGradientOptions) : 0;
        char targetBuf[24];
        if (stops) snprintf(status, sizeof(status), "Colour stop %u of %u", sGradientStop + 1, stops);
        else snprintf(status, sizeof(status), "%s", targetLabel(mTextTarget, preview, mTargetNames, targetBuf, sizeof(targetBuf)));
        menu->drawText(status, 28, top + 53, 18, 18, ink);
        menu->drawText(SUSAMUNE_GLYPH_X " Next item", 276, top + 57, 12, 12, ink);
        if (stops) for (unsigned i = 0; i < stops; ++i) {
            const unsigned index = stopIndex(i, stops, mCapabilities & CAP_TIMER_GRADIENT ? 6 : mTextSlots);
            const u8 *rgb = mTextRgb[index];
            const int x = 434 + i * 35;
            if (i == sGradientStop) menu->fillBox(x - 2, top + 53, 28, 18, ink);
            menu->fillBox(x, top + 55, 24, 14, Color(rgb[0], rgb[1], rgb[2], 255));
        }
        unsigned options[OPTION_COUNT], count = 0, selected = 0;
        for (unsigned order = 0; order < OPTION_COUNT; ++order) {
            const unsigned lead = OPTION_COUNT - OPTION_COLOR_MODE;
            const unsigned i = order < lead ? OPTION_COLOR_MODE + order : order - lead;
            if (!optionInGroup(i)) continue;
            if (i == mOption) selected = count;
            options[count++] = i;
        }
        const unsigned first = selected > 4 ? selected - 4 : 0;
        if (count > 5) {
            snprintf(status, sizeof(status), "%u / %u", selected + 1, count);
            menu->drawText(status, 606 - Menu::textWidth(status, 12), top + 35, 12, 12, muted);
            if (first) menu->drawText(SUSAMUNE_GLYPH_UP, 611, top + 59, 12, 12, ink);
            if (first + 5 < count) menu->drawText(SUSAMUNE_GLYPH_DOWN, 611, top + 163, 12, 12, ink);
            menu->fillBox(616, top + 76, 3, 83, Color(219, 210, 165, 255));
            menu->fillBox(616, top + 76 + first * 83 / count, 3, 5 * 83 / count, ink);
        }
        for (unsigned row = first; row < count && row < first + 5; ++row) {
            const unsigned i = options[row];
            const int y = top + 76 + (row - first) * 19;
            if (i == mOption) MenuTheme::selection(menu, 20, y - 2, 592, 19);
            const char *name = i == OPTION_GRADIENT_STOPS ? "Colour stops" : i == OPTION_GRADIENT_STOP ? "Selected stop" :
                i == OPTION_ORIGINAL_COLOURS ? "Appearance" : i == OPTION_GRADIENT_SPEED ? "Speed" : i == OPTION_GRADIENT_MOTION ? "Gradient animation" :
                i == OPTION_GRADIENT_DIRECTION ? "Direction" : i == OPTION_COLOR_MODE ? "Appearance" :
                i == OPTION_GRADIENT ? "Colour preset" : PackedText::at(
                mTargetNames && i <= OPTION_TEXT_BRIGHTNESS ? kElementOptionNames : kOptionNames, i);
            menu->drawText(name, 30, y, 14, 14, i == mOption ? selectedInk : ink);
            const char *value = status;
            if (i == OPTION_ORIGINAL_COLOURS) value = gSettings.get((SettingId)sOriginalColourSetting) ? "Custom" : "Original guidebook";
            else if (i == OPTION_GRADIENT_STOPS) {
                if (stops) snprintf(status, sizeof(status), "%u", stops); else value = "Per character";
            } else if (i == OPTION_GRADIENT_STOP) snprintf(status, sizeof(status), "%u / %u", sGradientStop + 1, stops);
            else if (i == OPTION_GRADIENT_MOTION || i == OPTION_GRADIENT_SPEED) {
                if (sGradientLocalAnimation) value = PackedText::at(i == OPTION_GRADIENT_MOTION ? "Off\0Flow\0Pulse\0Ping-pong\0Wave\0Shimmer\0Steps\0Sparkle\0Curtain\0Alternating" : "Slow\0Normal\0Fast",
                    i == OPTION_GRADIENT_SPEED ? GradientMotion::wordSpeed(*sGradientOptions) : GradientMotion::wordMotion(*sGradientOptions));
                else value = gSettings.valueLabel(gradientSetting(i));
            } else if (i == OPTION_GRADIENT_DIRECTION) value = gSettings.getBool((SettingId)sGradientDirectionSetting) ? "Vertical" : "Horizontal";
            else if (i == OPTION_GRADIENT) value = PackedText::at(kGradientNames, sGradientPreset);
            else if (i == OPTION_COLOR_MODE) {
                const u16 mask = mTextTarget ? 1u << (mTextTarget - 1) : (1u << mTextSlots) - 1u;
                value = !(*mCustomMask & mask) ? "Original" : (*mCustomMask & mask) == mask ? "Custom" : "Mixed";
            } else if (i <= OPTION_TEXT_L) {
                u16 v;
                const unsigned target = stops ? stopIndex(sGradientStop, stops, mCapabilities & CAP_TIMER_GRADIENT ? 6 : mTextSlots) + 1 : mTextTarget;
                if (textChannel(mTextRgb, mTextSlots, target, i, &v)) snprintf(status, sizeof(status), i ? "%u pct" : "%u deg", v);
                else value = "Mixed";
            } else if (i >= OPTION_BG_H && i <= OPTION_BG_L) {
                const unsigned channel = i - OPTION_BG_H;
                snprintf(status, sizeof(status), channel ? "%u pct" : "%u deg", CreationColor::display(sHsl[mTextSlots], channel));
            } else {
                const u8 scalar = styleValue(*mStyle, i);
                if (i == OPTION_PADDING && scalar == 0xff) value = "Off";
                else snprintf(status, sizeof(status), i == OPTION_TEXT_BRIGHTNESS ? "%u pct" : "%u", scalar);
            }
            menu->drawText(value, 606 - Menu::textWidth(value, 14), y, 14, 14, i == mOption ? selectedInk : ink);
        }
        menu->drawText(mGroup == GROUP_ANIMATION ? "Pick a style and speed. Watch the live preview." :
            "C-stick: select / change   X: next part   Hold Y: fine adjustment", 28, top + 173, 11, 11, muted);
    }
    menu->drawText(mGroup == GROUP_HOME ? "Choose what to change" : "START: save changes", 20, top + 195, 11, 11, ink);
    const char *finish = mGroup == GROUP_HOME ? SUSAMUNE_GLYPH_A " Choose    " SUSAMUNE_GLYPH_B " Back" :
        mGroup == GROUP_LAYOUT && (mCapabilities & CAP_SCALE) ? SUSAMUNE_GLYPH_A " Enter size    " SUSAMUNE_GLYPH_B " Back    " SUSAMUNE_GLYPH_Z " Reset" :
        SUSAMUNE_GLYPH_A " Done    " SUSAMUNE_GLYPH_B " Back    " SUSAMUNE_GLYPH_Z " Reset";
    menu->drawText(finish, 620 - Menu::textWidth(finish, 12), top + 194, 12, 12, ink);
    if (mConfirm != CONFIRM_NONE) {
        MenuTheme::panel(menu, 126, top + 65, 388, 80, "Confirm changes", MenuThemeAssets::TabShine);
        const char *prompt = mConfirm == CONFIRM_KEEP ? "Keep these changes?" : mConfirm == CONFIRM_CANCEL ? "Discard all changes?" : "Reset selected control?";
        menu->drawText(prompt, 320 - Menu::textWidth(prompt, 14) / 2, top + 103, 14, 14, ink);
        const char *answer = SUSAMUNE_GLYPH_A " Confirm     " SUSAMUNE_GLYPH_B " Go back";
        menu->drawText(answer, 320 - Menu::textWidth(answer, 13) / 2, top + 126, 13, 13, ink);
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
                  u16 selectedSlot, u8 gradientOptions) {
    if (!menu || !text || !textRgb || textSlots == 0) return;
    if (shadow) {
        menu->drawText(text, x + 1, y + 1, size, size, Color(0, 0, 0, 220));
    }
    const bool vertical = gQftDisplay.verticalGradient(textRgb);
    const u8 localMotion = GradientMotion::wordMotion(gradientOptions);
    const u8 motion = localMotion ? localMotion : gQftDisplay.animatedGradient(textRgb) ? GradientMotion::mode(false) : 0;
    const u16 phase = localMotion ? GradientMotion::phaseForSpeed(GradientMotion::wordSpeed(gradientOptions)) : motion ? GradientMotion::phase(false) : 0;
    const bool stops = GradientMotion::wordStops(gradientOptions);
    const unsigned visible = glyphCount(text);
    const unsigned paletteSlots = localMotion && !stops && visible < textSlots ? visible : textSlots;

    char run[192];
    int byte = 0;
    int glyph = 0;
    int drawX = x;
    int arrowCentre = -1;
    while (text[byte]) {
        const int startByte = byte;
        const u16 logicalSlot = (u16)(firstSlot + glyph);
        const u16 colorSlot = stops ? stopIndex(glyph, visible, textSlots) : logicalSlot < textSlots ? logicalSlot : textSlots - 1;
        u8 moving[3];
        if (motion) GradientMotion::sample(textRgb, paletteSlots, colorSlot, motion, phase, moving);
        const u8 *rgb = motion ? moving : textRgb[colorSlot];
        const bool selectedRun = logicalSlot == selectedSlot;

        do {
            byte += glyphBytes(text + byte);
            glyph++;
            if (!text[byte]) break;
            const u16 nextLogical = (u16)(firstSlot + glyph);
            const u16 nextSlot = nextLogical < textSlots ? nextLogical : textSlots - 1;
            if (selectedRun || nextLogical == selectedSlot) break;
            if (stops || (motion && !vertical)) break;
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
    drawTextBox(menu, style, textRgb, textSlots, text, rightAlignSlots,
                selectedSlot, gQftDisplay.gradientOptions(textRgb));
}

void drawTextBox(Menu *menu, const CreationStyle &style,
                 const u8 (*textRgb)[3], u16 textSlots, const char *text,
                 bool rightAlignSlots, u16 selectedSlot, u8 gradientOptions) {
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
                 size, first, false, selectedSlot, gradientOptions);
}

}  // namespace Creation
