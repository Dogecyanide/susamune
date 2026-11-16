#include "susamune/menu_sounds.hxx"
#include "susamune/menu_button_edges.hxx"

static MenuButtonEdges sMenuButtons;

// A root wrapper leaves the fixed constructor/render-helper pool unchanged.
class MenuSoundsDisplayTab final : public MenuTab {
public:
    explicit MenuSoundsDisplayTab(NestedMenuTab *parent)
        : mParent(parent), mTopRow(0), mEditingBackground(false), mPreviousButtons(0) {}
    const char *title() const override { return mParent->title(); }
    bool grabsInput() const override { return mEditingBackground || mParent->grabsInput(); }
    bool suppressesBinds() const override { return mEditingBackground || mParent->suppressesBinds(); }
    bool fullScreen() const override { return mEditingBackground || mParent->fullScreen(); }
    bool favoriteHint() const override { return mParent->favoriteHint(); }
    void focus() override { mParent->focus(); }
    static int topRows() { return JapaneseUi::available() ? 3 : 2; }
    static const char *rowName(int row) {
        return row == 0 ? Settings::name(SETTING_MENU_SOUNDS) : row == 1 ? "Menu colours" : "Menu language";
    }

    void update(Menu *menu, TMarioGamePad *pad) override {
        if (mEditingBackground) {
            gCreationExtras.updateEditor(pad);
            mEditingBackground = gCreationExtras.editing();
            return;
        }
        if (mParent->current()) {
            mParent->update(menu, pad);
            return;
        }
        const int top = topRows();
        int row = mTopRow < top ? mTopRow : mParent->mSel + top;
        const u32 nav = menu->navigationInput(pad);
        if (nav & TMarioGamePad::CSTICK_UP) row = wrap(row - 1, mParent->mCount + top);
        else if (nav & TMarioGamePad::CSTICK_DOWN) row = wrap(row + 1, mParent->mCount + top);
        mTopRow = row < top ? row : top;
        if (row >= top) mParent->mSel = row - top;
        if (!(mParent->mNavInput.update() & JUTGamePad::A)) return;
        if (mTopRow == 0) gSettings.cycle(SETTING_MENU_SOUNDS, 1);
        else if (mTopRow == 1) {
            gCreationExtras.beginColorEditor(SUSAMUNE_CREATION_MENU_BG, 1, rowName(1));
            mEditingBackground = true;
        }
        else if (mTopRow < top) JapaneseUi::toggle();
        else {
            mParent->mPage = mParent->mSel;
            mParent->focus();
        }
    }

    void draw(Menu *menu, int x, int y, int w, int h) override {
        if (mEditingBackground) {
            gCreationExtras.drawEditor(menu);
            return;
        }
        if (mParent->current()) {
            mParent->draw(menu, x, y, w, h);
            return;
        }
        drawValueRow(menu, x, y, w, rowName(0),
                     gSettings.valueLabel(SETTING_MENU_SOUNDS), mTopRow == 0, false, true);
        drawValueRow(menu, x, y + ROW_H, w, rowName(1), "Edit",
                     mTopRow == 1, false, true);
        const int top = topRows();
        if (top == 3) drawValueRow(menu, x, y + 2 * ROW_H, w, rowName(2),
            JapaneseUi::enabled() ? "Japanese" : "English", mTopRow == 2, false, true);
        for (int i = 0; i < mParent->mCount; ++i)
            drawValueRow(menu, x, y + (i + top) * ROW_H, w,
                         mParent->mChildren[i]->title(), nullptr,
                         mTopRow == top && mParent->mSel == i, false, true);
        drawHelpLine(menu, x, y, w, h, mTopRow == 0
            ? "Sunshine sounds when moving through menus and changing options."
            : mTopRow == 1 ? "Original guidebook or your own colours, with a live preview."
                          : mTopRow < top ? "Switch between English and Japanese menus for this session."
                          : mParent->mChildren[mParent->mSel]->summary());
    }

    NestedMenuTab *mParent;
    u8 mTopRow;
    bool mEditingBackground;
    u16 mPreviousButtons;
};
static_assert(sizeof(MenuSoundsDisplayTab) <= sizeof(sMenuRuntime.soundDisplay),
              "menu sound controls exceed the existing runtime window");

u32 Menu::soundSelection(MenuTab *tab) const {
    if (tab == reinterpret_cast<MenuTab *>(sMenuRuntime.soundDisplay)) {
        const auto *display = static_cast<MenuSoundsDisplayTab *>(tab);
        return soundSelection(display->mParent) * 7 + display->mTopRow +
            display->mEditingBackground * 3;
    }
    u8 *const hubs[] = {sMenuRuntime.settingsHub, sMenuRuntime.ilsHub,
                       sMenuRuntime.displayHub, sMenuRuntime.systemHub};
    for (u8 *storage : hubs) {
        if (tab != reinterpret_cast<MenuTab *>(storage)) continue;
        const auto *hub = static_cast<NestedMenuTab *>(tab);
        const u32 child = hub->current() ? soundSelection(hub->current()) : 0;
        return child * 257u + (u8)(hub->mPage + 1) * 17u + hub->mSel;
    }
    u8 *const categories[] = {sMenuRuntime.starred, sMenuRuntime.qol, sMenuRuntime.cosmetic,
                             sMenuRuntime.misc, sMenuRuntime.ui, sMenuRuntime.timer, sMenuRuntime.rng};
    for (u8 *storage : categories) {
        if (tab != reinterpret_cast<MenuTab *>(storage)) continue;
        const auto *page = static_cast<CategorySettingsTab *>(tab);
        return page->mSel + 257u * page->mMode;
    }
#define SOUND_PAGE(storage, type, expression) \
    if (tab == reinterpret_cast<MenuTab *>(sMenuRuntime.storage)) { \
        const auto *page = static_cast<type *>(tab); return (expression); }
    SOUND_PAGE(iling, ILingTab, page->mSel + 257u * page->mChoosingEpisode +
        521u * page->mEpisodeChoice + 1031u * page->mShowingStats +
        2053u * page->mShowingSegments + 4099u * page->mStatsSegment +
        8209u * page->mEditingName + 16411u * page->mNameCursor +
        32771u * page->mNamePage + 65537u * page->mConfirmDelete)
    SOUND_PAGE(ghosts, GhostsTab, page->mSel + 257u * page->mChoice +
        521u * page->mConfirmSave + 1031u * page->mConfirmDelete)
    SOUND_PAGE(records, RecordsTab, page->mSel + 257u * page->mPage +
        521u * page->mCategory + 1031u * page->mWorld +
        2053u * page->mAchievement + 4099u * page->mScope)
    SOUND_PAGE(pbSafety, PBSafetyTab, page->mSel)
    SOUND_PAGE(creation, CreationTab, page->mSel + 257u * page->mPage)
    SOUND_PAGE(layoutProfiles, LayoutProfilesTab, page->mSel + 257u * page->mMode +
        521u * page->mCursor + 1031u * page->mPage + 2053u * page->mLength)
    SOUND_PAGE(savestate, SavestatesTab, page->mSel + 257u * page->mSD +
        521u * page->mSDsel + 1031u * page->mNameMode +
        2053u * page->mNameCursor + 4099u * page->mNamePage +
        8209u * page->mConfirmClear + 16411u * page->mConfirmLoad +
        32771u * page->mConfirmDelete)
    SOUND_PAGE(binds, BindsTab, page->mSel + 257u * page->mPage)
    SOUND_PAGE(stageLoader, StageLoaderTab, page->mSel + 257u * page->mEditor +
        521u * page->mGoal + 1031u * page->mTextCursor + 2053u * page->mTextPage)
    SOUND_PAGE(streaking, StageLoaderTab, page->mSel + 257u * page->mEditor +
        521u * page->mGoal + 1031u * page->mTextCursor + 2053u * page->mTextPage)
    SOUND_PAGE(practiceControls, PracticeControlsTab, page->mSel + 257u * page->mBinding)
    SOUND_PAGE(tasProject, TasProjectTab, page->mSel + 257u * page->mPage +
        521u * page->mCursor + 1031u * page->mKeyPage + 2053u * page->mLength)
    SOUND_PAGE(guide, GuideTab, page->mPage)
#undef SOUND_PAGE
    return 0;
}

u32 Menu::soundState() const {
    if (!mShown) return 0;
    if (searchActive()) {
        const auto &search = sMenuRuntime.search;
        return 0x50000000u + search.mode * 65536u + search.selected * 256u +
            search.cursor + search.length * 37u + search.page * 1024u;
    }
    u32 state = soundSelection(mTabs[mCurTab]) * 257u + mCurTab;
    state = state * 3u + mTabs[mCurTab]->grabsInput();
    for (int i = 0; i < SETTING_COUNT; ++i)
        state = state * 33u + gSettings.get(static_cast<SettingId>(i));
    return state;
}

void Menu::updateWithSounds(TMarioGamePad *pad) {
    auto *display = reinterpret_cast<MenuSoundsDisplayTab *>(sMenuRuntime.soundDisplay);
    for (int i = 0; i < mNumTabs; ++i) {
        if (mTabs[i] == reinterpret_cast<MenuTab *>(sMenuRuntime.displayHub))
            mTabs[i] = new (display) MenuSoundsDisplayTab(
                reinterpret_cast<NestedMenuTab *>(sMenuRuntime.displayHub));
    }
    const u16 held = JUTGamePad::mPadStatus[0].mButton;
    sMenuButtons.sample(held);
    const u16 pressed = sMenuButtons.pressed;
    display->mPreviousButtons = held;
    if (!mShown || searchActive() || mTabs[mCurTab]->grabsInput()) sMenuButtons.deferred = 0;
    const bool recording = gBinds.recording();
    const bool wasShown = mShown;
    const u32 before = soundState();
    const u32 directions = TMarioGamePad::CSTICK_UP | TMarioGamePad::CSTICK_DOWN |
                           TMarioGamePad::CSTICK_LEFT | TMarioGamePad::CSTICK_RIGHT;
    const bool navigation = (pad->mButtons.mInput & directions) ||
        (pad->mButtons.mRapidInput & (TMarioGamePad::L | TMarioGamePad::R)) ||
        (pressed & (JUTGamePad::DPAD_UP | JUTGamePad::DPAD_DOWN |
                    JUTGamePad::DPAD_LEFT | JUTGamePad::DPAD_RIGHT));
    // Retail repeat/edge fields may survive a frozen director. Menu actions
    // use one physical edge, while directional scrolling keeps its repeat.
    const u32 buttons = JUTGamePad::A | JUTGamePad::B | JUTGamePad::X | JUTGamePad::Y |
        JUTGamePad::Z | JUTGamePad::START | JUTGamePad::L | JUTGamePad::R;
    const u32 frame = pad->mButtons.mFrameInput, rapid = pad->mButtons.mRapidInput;
    pad->mButtons.mFrameInput = (frame & ~buttons) | (pressed & buttons);
    pad->mButtons.mRapidInput = (rapid & ~buttons) | (pressed & buttons);
    update(pad);
    pad->mButtons.mFrameInput = frame;
    pad->mButtons.mRapidInput = rapid;
    MenuSounds::play(MenuSounds::choose({wasShown, mShown, before != soundState(),
        navigation, gSettings.getBool(SETTING_MENU_SOUNDS), recording, pressed}));
}
