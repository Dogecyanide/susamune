#include "susamune/layout_editor.hxx"

#include "SMS/Player/MarioGamePad.hxx"
#include "susamune/menu.hxx"
#include "susamune/menu_theme.hxx"

namespace {

int clampi(int value, int lo, int hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

}  // namespace

namespace LayoutEditor {

bool updatePositionScale(u32 rapid, u16 &x, u16 &y, u8 &scale, int maxScale,
                         int maxX, int maxY) {
    if (rapid & TMarioGamePad::DPAD_LEFT) {
        x = (u16)clampi((int)x - 2, 0, maxX);
    }
    if (rapid & TMarioGamePad::DPAD_RIGHT) {
        x = (u16)clampi((int)x + 2, 0, maxX);
    }
    if (rapid & TMarioGamePad::DPAD_UP) {
        y = (u16)clampi((int)y - 2, 0, maxY);
    }
    if (rapid & TMarioGamePad::DPAD_DOWN) {
        y = (u16)clampi((int)y + 2, 0, maxY);
    }
    if (rapid & TMarioGamePad::L) {
        scale = (u8)clampi((int)scale - 2, 50, maxScale);
    }
    if (rapid & TMarioGamePad::R) {
        scale = (u8)clampi((int)scale + 2, 50, maxScale);
    }
    const u32 controls = TMarioGamePad::DPAD_LEFT | TMarioGamePad::DPAD_RIGHT |
                         TMarioGamePad::DPAD_UP | TMarioGamePad::DPAD_DOWN |
                         TMarioGamePad::L | TMarioGamePad::R;
    return (rapid & controls) != 0;
}

void drawHeader(Menu *menu, int boxHeight, const char *title, const char *status) {
    MenuTheme::panel(menu, 8, 8, 624, boxHeight, title);
    menu->drawText(status, 18, 43, 11, 11, MenuTheme::textColor());
}

}  // namespace LayoutEditor
