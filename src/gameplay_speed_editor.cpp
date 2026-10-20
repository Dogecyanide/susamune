#include "susamune/gameplay_speed_editor.hxx"
#include "susamune/menu.hxx"
#include "susamune/raw_prompt_input.hxx"
#include "susamune/settings.hxx"
#include "Dolphin/printf.h"

namespace {
const char kSpeedEditorTitle[] = "Gameplay speed";
const char kSpeedEditorPresetTitle[] = "Slowdown preset";
const char *sNumberEditorTitle, *sNumberEditorUnit;
unsigned sNumberEditorMinimum, sNumberEditorMaximum;
const char kSpeedEditorHelp[] = "D-pad Left/Right: digit    Up/Down: value";
const char kSpeedEditorFooter[] = "A / Start: keep    B: cancel";
const void *sSpeedEditorOwner;
RawPromptInput sSpeedEditorInput;
char sSpeedEditorDigits[3];
u8 sSpeedEditorCursor;
bool sSpeedEditorPreset;
}

namespace NumberEditor {
void begin(const void *owner, const char *title, unsigned percent,
           unsigned minimum, unsigned maximum, const char *unit) {
    sNumberEditorTitle = title;
    sNumberEditorUnit = unit;
    sNumberEditorMinimum = minimum;
    sNumberEditorMaximum = maximum;
    sSpeedEditorDigits[0] = '0' + percent / 100;
    sSpeedEditorDigits[1] = '0' + (percent / 10) % 10;
    sSpeedEditorDigits[2] = '0' + percent % 10;
    sSpeedEditorCursor = 0;
    sSpeedEditorOwner = owner;
    sSpeedEditorInput.begin(JUTGamePad::A | JUTGamePad::B | JUTGamePad::X |
                 JUTGamePad::Y | JUTGamePad::Z | JUTGamePad::START |
                 JUTGamePad::L | JUTGamePad::R | JUTGamePad::DPAD_LEFT |
                 JUTGamePad::DPAD_RIGHT | JUTGamePad::DPAD_UP | JUTGamePad::DPAD_DOWN);
}

bool active(const void *owner) { return sSpeedEditorOwner && sSpeedEditorOwner == owner; }

void cancel(const void *owner) {
    if (!active(owner)) return;
    sSpeedEditorOwner = nullptr;
    sSpeedEditorInput.clear();
}

int update(Menu *menu, unsigned *value, char *acceptedDigits) {
    if (!sSpeedEditorOwner) return 0;
    const u16 pressed = sSpeedEditorInput.update();
    if (pressed & JUTGamePad::B) {
        cancel(sSpeedEditorOwner);
        return -1;
    } else if (pressed & (JUTGamePad::A | JUTGamePad::START)) {
        const unsigned percent = (sSpeedEditorDigits[0] - '0') * 100 +
                                 (sSpeedEditorDigits[1] - '0') * 10 + sSpeedEditorDigits[2] - '0';
        if (percent < sNumberEditorMinimum || percent > sNumberEditorMaximum) {
            char message[48];
            snprintf(message, sizeof(message), "Choose %u-%u%s", sNumberEditorMinimum,
                     sNumberEditorMaximum, sNumberEditorUnit);
            menu->toast(message);
            return 0;
        }
        *value = percent;
        if (acceptedDigits) {
            for (unsigned i = 0; i < 3; ++i) acceptedDigits[i] = sSpeedEditorDigits[i];
            acceptedDigits[3] = '\0';
        }
        cancel(sSpeedEditorOwner);
        return 1;
    } else {
        if (pressed & JUTGamePad::DPAD_LEFT) sSpeedEditorCursor = sSpeedEditorCursor ? sSpeedEditorCursor - 1 : 2;
        if (pressed & JUTGamePad::DPAD_RIGHT) sSpeedEditorCursor = (sSpeedEditorCursor + 1) % 3;
        const int delta = (pressed & JUTGamePad::DPAD_UP) ? 1 :
                          (pressed & JUTGamePad::DPAD_DOWN) ? -1 : 0;
        if (delta) sSpeedEditorDigits[sSpeedEditorCursor] = '0' + (sSpeedEditorDigits[sSpeedEditorCursor] - '0' + delta + 10) % 10;
    }
    return 0;
}

void draw(Menu *menu) {
    typedef JUtility::TColor Color;
    const Color text(238, 242, 252, 255);
    const Color hint(200, 206, 220, 255);
    menu->fillBox(0, 0, 640, 480, Color(0, 0, 0, 135));
    menu->fillBox(70, 140, 500, 206, Color(8, 11, 20, 245));
    menu->fillBox(70, 140, 500, 3, Color(90, 170, 255, 255));
    menu->drawText(sNumberEditorTitle, 96, 162, 20, 20, text);
    for (unsigned i = 0; i < 3; ++i) {
        const int x = 104 + i * 26;
        if (sSpeedEditorCursor == i) menu->fillBox(x - 3, 208, 26, 32, Color(90, 170, 255, 100));
        const char digit[] = {sSpeedEditorDigits[i], 0};
        menu->drawText(digit, x, 212, 24, 24, text);
    }
    menu->drawText(sNumberEditorUnit, 187, 212, 24, 24, text);
    char range[32];
    snprintf(range, sizeof(range), "Choose %03u-%03u%s", sNumberEditorMinimum,
             sNumberEditorMaximum, sNumberEditorUnit);
    menu->drawText(range, 244, 218, 14, 14, hint);
    menu->drawText(kSpeedEditorHelp, 96, 272, 13, 13, hint);
    menu->drawText(kSpeedEditorFooter, 96, 304, 13, 13, hint);
}
}

namespace GameplaySpeedEditor {
void begin(const void *owner, bool preset) {
    sSpeedEditorPreset = preset;
    const unsigned value = gSettings.get(preset ? SETTING_SLOWDOWN_PRESET : SETTING_GAMEPLAY_SPEED);
    NumberEditor::begin(owner, preset ? kSpeedEditorPresetTitle : kSpeedEditorTitle,
                        value ? value : 100, 1, 100, "%");
}
bool active(const void *owner) { return NumberEditor::active(owner); }
void cancel(const void *owner) { NumberEditor::cancel(owner); }
void update(Menu *menu) {
    unsigned value;
    if (NumberEditor::update(menu, &value) == 1)
        gSettings.set(sSpeedEditorPreset ? SETTING_SLOWDOWN_PRESET : SETTING_GAMEPLAY_SPEED,
                      value == 100 ? 0 : value);
}
void draw(Menu *menu) { NumberEditor::draw(menu); }
}
