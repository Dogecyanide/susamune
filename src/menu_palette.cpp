#include "susamune/menu_palette.hxx"
#include "susamune/settings.hxx"
#include "Dolphin/string.h"

const unsigned char MoonshineMenuDefaults[MENU_COLOUR_COUNT][3] = MOONSHINE_MENU_DEFAULT_VALUES;

namespace MenuPalette {
void reset() { MoonshineMenuPaletteInit(MOONSHINE_MENU_PALETTE_LIVE); }
void adopt() {
    if (MoonshineMenuPaletteValid(MOONSHINE_MENU_PALETTE_STAGE))
        *MOONSHINE_MENU_PALETTE_LIVE = *MOONSHINE_MENU_PALETTE_STAGE;
    else reset();
}
void stage() { *MOONSHINE_MENU_PALETTE_STAGE = *MOONSHINE_MENU_PALETTE_LIVE; }
JUtility::TColor colour(unsigned role, JUtility::TColor fallback) {
    const auto &palette = *MOONSHINE_MENU_PALETTE_LIVE;
    if (role >= MENU_COLOUR_COUNT || !gSettings.get(SETTING_MENU_CUSTOM_BACKGROUND) ||
        !(palette.custom & (1u << role))) return fallback;
    const auto *rgb = palette.rgb[role];
    return JUtility::TColor(rgb[0],rgb[1],rgb[2],
        role == MENU_CATEGORIES || role == MENU_FOOTER ? 255 : fallback.a);
}
const char *names() {
    static const char labels[]="Paper\0Header\0Category strip\0Sidebar\0Outer trim\0Inner trim\0Selected tab\0Selected row\0Text\0Help text\0Values\0Selected text\0Moonshine title\0Sidebar text\0Book spine\0Footer";
    return labels;
}
}
