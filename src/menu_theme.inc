#include "susamune/menu_theme.hxx"

void Menu::drawGuidebook(J2DOrthoGraph *ortho) {
    MenuTheme::begin(ortho);
    if (mShown && searchActive()) {
        mOrtho = ortho;
        if (drawSearch()) return;
    }
    if (!mShown || mTabs[mCurTab]->fullScreen()) {
        if (mShown && gCreationExtras.editingMenuBackground()) {
            mOrtho = ortho;
            MenuTheme::frame(this, ortho, true);
        }
        MenuTheme::page(mShown);
        draw(ortho);
        MenuTheme::page(false);
        return;
    }
    mOrtho = ortho;
    MenuTab *current = mTabs[mCurTab];
    bool sidebar = false;
    const u8 *hubs[] = {sMenuRuntime.settingsHub, sMenuRuntime.ilsHub,
                       sMenuRuntime.systemHub};
    for (const u8 *hub : hubs)
        if (current == reinterpret_cast<const MenuTab *>(hub))
            sidebar = static_cast<NestedMenuTab *>(current)->current() == nullptr;
    if (current == reinterpret_cast<MenuTab *>(sMenuRuntime.soundDisplay))
        sidebar = static_cast<MenuSoundsDisplayTab *>(current)->mParent->current() == nullptr;

    MenuTheme::frame(this, ortho, sidebar);
    const int stripX = 67, slotWidth = 164, slotStep = 169;
    mTabFirst = mCurTab > 2 ? mCurTab - 2 : 0;
    for (int i = mTabFirst; i < mNumTabs && i < mTabFirst + 3; ++i) {
#if ENABLE_DEBUG_WARPS
        const int icon = i - 2;
#else
        const int icon = i;
#endif
        MenuTheme::category(this, mTabs[i]->title(), icon,
                            stripX + (i - mTabFirst) * slotStep, slotWidth, i == mCurTab);
    }
    MenuTheme::shoulder(this, false);
    MenuTheme::shoulder(this, true);

    MenuTheme::page(true);
    current->draw(this, sidebar ? 171 : 58, 142,
                  sidebar ? 415 : 524, 248);
    MenuTheme::page(false);

    const Color footer = MenuTheme::footerColor();
    const bool search = searchAvailable() && gBinds.get(BIND_MENU_SEARCH);
    const char *hint = !search && current->favoriteHint()
        ? SUSAMUNE_GLYPH_A " Select   " SUSAMUNE_GLYPH_B " Back   "
          SUSAMUNE_GLYPH_X " Shine"
        : SUSAMUNE_GLYPH_A " Select   " SUSAMUNE_GLYPH_B " Back";
    drawText(hint, 44, 412, 14, 14, footer);
    char combo[kBindTextMax];
    if (search) {
        // The search shortcut is rebindable, so show the combo in use.
        static const char kSearchHint[] = "   %s Search";
        char line[kBindTextMax + sizeof(kSearchHint)];
        Binds::format(gBinds.get(BIND_MENU_SEARCH), combo);
        snprintf(line, sizeof(line), kSearchHint, combo);
        drawText(line, 44 + textWidth(hint, 14), 412, 14, 14, footer);
    }
    Binds::format(gBinds.get(BIND_MENU_TOGGLE), combo);
    const int closeWidth = textWidth(" Close", 14);
    drawText(combo, 592 - closeWidth - textWidth(combo, 14), 412, 14, 14, footer);
    drawText(" Close", 592 - closeWidth, 412, 14, 14, footer);
    drawToast();
    drawAchievementBanner(this);
    bgmStatsDraw(this);
}
