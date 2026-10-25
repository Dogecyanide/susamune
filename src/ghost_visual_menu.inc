namespace GhostVisualMenu {
const char kTitle[] __attribute__((section(".rodata.ghost_visual_title"))) = "Ghost visuals";
const char kOpen[] __attribute__((section(".rodata.ghost_visual_open"))) = "Open";
const char kHelp[] __attribute__((section(".rodata.ghost_visual_help"))) =
    "Appearance, recorded inputs and the camera used while watching.";
const char kCameraHelp[] __attribute__((section(".rodata.ghost_visual_camera_help"))) =
    "Recorded follows the captured view in Watch. Free keeps camera control.";
const char kNoCamera[] __attribute__((section(".rodata.ghost_visual_no_camera"))) =
    "This ghost has no recorded camera; Watch uses Free.";
const char kFooter[] __attribute__((section(".rodata.ghost_visual_footer"))) =
    SUSAMUNE_GLYPH_A " Change  " SUSAMUNE_GLYPH_C " Select  " SUSAMUNE_GLYPH_B " Back";
const SettingId kSettings[] __attribute__((section(".rodata.ghost_visual_settings"))) = {
    SETTING_GHOST_DISPLAY, SETTING_GHOST_OPACITY, SETTING_GHOST_APPEARANCE,
    SETTING_GHOST_INPUTS, SETTING_GHOST_PATH, SETTING_GHOST_CAMERA,
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
    if (direction) gSettings.cycle(kSettings[selected], direction);
    return false;
}

__attribute__((noinline, section(".text.ghost_visual_draw")))
void draw(Menu *menu, int x, int y, int w, int h, int selected) {
    drawSectionHeader(menu, x, y, w, kTitle);
    for (int row = 0; row < kCount; ++row)
        drawValueRow(menu, x, y + (row + 1) * ROW_H, w,
            row == 0 && sDisplayLabel ? sDisplayLabel : Settings::name(kSettings[row]),
            gSettings.valueLabel(kSettings[row]),
            row == selected, false, true);
    const char *help = selected == kCount - 1 ? kCameraHelp : kHelp;
    if (kSettings[selected] == SETTING_GHOST_PATH)
        help = "Show the recorded route while watching. Cosmetic only; no effect when racing.";
    if (selected == 0 && sDisplayHelp) help = sDisplayHelp;
    if (selected == kCount - 1 && !Ghost::recordedCameraAvailable()) help = kNoCamera;
    drawHelpLine(menu, x, y, w, h - ROW_H, help);
    drawFooterText(menu, kFooter, x + 4, y + h - FOOT_SZ);
}
} // namespace GhostVisualMenu
