namespace GhostVisualMenu {
const char kTitle[] __attribute__((section(".rodata.ghost_visual_title"))) = "Ghost options";
const char kOpen[] __attribute__((section(".rodata.ghost_visual_open"))) = "Open";
const char kHelp[] __attribute__((section(".rodata.ghost_visual_help"))) =
    "Appearance, playback and recording options.";
const char kCameraHelp[] __attribute__((section(".rodata.ghost_visual_camera_help"))) =
    "Recorded follows the captured view in Watch. Free keeps camera control.";
const char kNoCamera[] __attribute__((section(".rodata.ghost_visual_no_camera"))) =
    "This ghost has no recorded camera; Watch uses Free.";
const char kFooter[] __attribute__((section(".rodata.ghost_visual_footer"))) =
    SUSAMUNE_GLYPH_A " Change  " SUSAMUNE_GLYPH_C " Select  " SUSAMUNE_GLYPH_B " Back";
const SettingId kSettings[] __attribute__((section(".rodata.ghost_visual_settings"))) = {
    SETTING_GHOST_DISPLAY, SETTING_GHOST_OPACITY, SETTING_GHOST_APPEARANCE,
    SETTING_GHOST_INPUTS, SETTING_GHOST_PATH, SETTING_GHOST_CAMERA, SETTING_COUNT,
};
const int kCount = sizeof(kSettings) / sizeof(kSettings[0]);
const char *sDisplayLabel __attribute__((section(".bss.ghost_visual_display_label")));
const char *sDisplayHelp __attribute__((section(".bss.ghost_visual_display_help")));

__attribute__((noinline, section(".text.ghost_visual_entry_label")))
const char *entryLabel(const char *label) {
    sDisplayLabel = label;
    return kTitle;
}

__attribute__((noinline, section(".text.ghost_visual_entry_help")))
const char *entryHelp(const char *help) {
    sDisplayHelp = help;
    return kHelp;
}

__attribute__((noinline, section(".text.ghost_visual_hidden")))
bool hiddenSelection(int selection) { return selection == 1 || selection == 2 || selection == 7; }

__attribute__((noinline, section(".text.ghost_visual_compact")))
int compactRow(int row) { return row - (row > 2) - (row > 3) - (row > 8); }

__attribute__((noinline, section(".text.ghost_visual_expand")))
int expandedRow(int row) {
    if (row >= 2) row += 2;
    if (row >= 8) ++row;
    // Preserve the legacy row renderer and its fixed string layout.
    volatile int expanded = row;
    return expanded;
}

__attribute__((noinline, section(".text.ghost_visual_update")))
bool update(Menu *menu, TMarioGamePad *pad, int &selected, u16 pressed) {
    if (pressed & JUTGamePad::B) return true;
    const u32 rapid = menu->navigationInput(pad);
    if (rapid & TMarioGamePad::CSTICK_UP) selected = wrap(selected - 1, kCount);
    else if (rapid & TMarioGamePad::CSTICK_DOWN) selected = wrap(selected + 1, kCount);
    const int direction = rapid & TMarioGamePad::CSTICK_LEFT ? -1 :
        ((rapid & TMarioGamePad::CSTICK_RIGHT) || (pressed & JUTGamePad::A)) ? 1 : 0;
    if (direction) {
        if (selected == kCount - 1) GhostContext::toggleDetails();
        else gSettings.cycle(kSettings[selected], direction);
    }
    return false;
}

__attribute__((noinline, section(".text.ghost_visual_draw")))
void draw(Menu *menu, int x, int y, int w, int h, int selected) {
    drawSectionHeader(menu, x, y, w, kTitle);
    const int visible = (h - HELP_H - 2 * ROW_H) / ROW_H;
    const int start = listScrollStart(selected, kCount, visible);
    const int end = clampi(start + visible, 0, kCount);
    for (int row = start; row < end; ++row)
        drawValueRow(menu, x, y + (row - start + 1) * ROW_H, w,
            row == kCount - 1 ? "Extra replay data" : row == 0 && sDisplayLabel ? sDisplayLabel : Settings::name(kSettings[row]),
            row == kCount - 1 ? (GhostContext::detailsEnabled() ? "On" : "Off") : gSettings.valueLabel(kSettings[row]),
            row == selected, false, true);
    char page[12]; snprintf(page, sizeof(page), "%d / %d", selected + 1, kCount);
    menu->drawMenuText(page, x + w - 52, y, 12, 12, cValue());
    if (end < kCount) {
        const s16 arrow[6] = {(s16)(x+w-12), (s16)(y+(visible+1)*ROW_H-8),
            (s16)(x+w), (s16)(y+(visible+1)*ROW_H-8), (s16)(x+w-6), (s16)(y+(visible+1)*ROW_H)};
        menu->fillPoly(arrow, 3, cRowDim());
    }
    const char *help = kSettings[selected] == SETTING_GHOST_CAMERA ? kCameraHelp : kHelp;
    if (kSettings[selected] == SETTING_GHOST_PATH)
        help = "Show the recorded route while watching. Cosmetic only; no effect when racing.";
    if (selected == 0 && sDisplayHelp) help = sDisplayHelp;
    if (kSettings[selected] == SETTING_GHOST_CAMERA && !Ghost::recordedCameraAvailable()) help = kNoCamera;
    if (selected == kCount - 1)
        help = "Session only, for new ghosts. Keep Off for website uploads until support is added.";
    drawHelpLine(menu, x, y, w, h - ROW_H, help);
    drawFooterText(menu, kFooter, x + 4, y + h - FOOT_SZ);
}
} // namespace GhostVisualMenu
