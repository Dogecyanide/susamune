#include "susamune/menu_theme.hxx"
#pragma clang section text="" rodata=".menu_search.rodata" data="" bss=""
#define SEARCH_CODE(name) __attribute__((section(".menu_search.text." #name)))

namespace MenuSearch {
static char lower(char c) { return c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c; }
SEARCH_CODE(contains) static bool contains(const char *text, const char *word, unsigned length) {
    if (!text) return false;
    for (; *text; ++text) {
        unsigned i = 0;
        while (i < length && text[i] && lower(text[i]) == lower(word[i])) ++i;
        if (i == length) return true;
    }
    return false;
}
SEARCH_CODE(matches) bool matches(const char *query, const Entry &entry) {
    while (*query) {
        while (*query && static_cast<unsigned char>(*query) <= ' ') ++query;
        const char *word = query;
        while (static_cast<unsigned char>(*query) > ' ') ++query;
        const unsigned length = query - word;
        if (length && !contains(entry.label, word, length) &&
            !contains(entry.section, word, length) &&
            !contains(entry.group, word, length) &&
            !contains(entry.page, word, length)) return false;
    }
    return true;
}

enum Kind { CATEGORY, CREATION, BINDS, TAS, CAMERA, STATES, ILS, LOADER,
            SAFETY, GHOSTS, GUIDE, LAYOUT, ONLINE, DISPLAY };
struct Group { u16 offset; u8 kind, top; };
#define SEARCH_GROUP(member, kind, top) \
    {__builtin_offsetof(MenuRuntime, member), kind, top}
static const Group groups[] = {
    SEARCH_GROUP(tasProject, TAS, 1), SEARCH_GROUP(practiceControls, CAMERA, 1),
    SEARCH_GROUP(savestate, STATES, 1), SEARCH_GROUP(misc, CATEGORY, 1),
    SEARCH_GROUP(rng, CATEGORY, 1), SEARCH_GROUP(qol, CATEGORY, 1),
    SEARCH_GROUP(iling, ILS, 2), SEARCH_GROUP(stageLoader, LOADER, 2),
    SEARCH_GROUP(streaking, LOADER, 2), SEARCH_GROUP(pbSafety, SAFETY, 2),
    SEARCH_GROUP(timer, CATEGORY, 2), SEARCH_GROUP(creation, CREATION, 5),
    SEARCH_GROUP(layoutProfiles, LAYOUT, 5), SEARCH_GROUP(ui, CATEGORY, 5),
    SEARCH_GROUP(cosmetic, CATEGORY, 5), SEARCH_GROUP(binds, BINDS, 6),
    SEARCH_GROUP(guide, GUIDE, 6), SEARCH_GROUP(ghosts, GHOSTS, 4),
    SEARCH_GROUP(soundDisplay, DISPLAY, 5),
#if TIMEWARP_LIVE_RACING
    SEARCH_GROUP(online, ONLINE, 7),
#endif
};
#undef SEARCH_GROUP
}

// Indices describe built-in rows only; catalogue names and live values never
// enter this scan. Labels stay borrowed from the same accessors as drawing.
SEARCH_CODE(entry) bool Menu::searchEntry(unsigned index, MenuSearch::Entry &entry, bool open) {
    using namespace MenuSearch;
    const unsigned firstTop = ENABLE_DEBUG_WARPS ? 2 : 0;
    const unsigned topCount = mNumTabs - firstTop;
    if (index < topCount) {
        const unsigned top = index + firstTop;
        entry = {mTabs[top]->title(), mTabs[top]->title(), nullptr, nullptr};
        if (open) {
            mCurTab = top;
            u8 *hubs[] = {sMenuRuntime.settingsHub, sMenuRuntime.ilsHub,
                         sMenuRuntime.displayHub, sMenuRuntime.systemHub};
            const int tops[] = {1, 2, 5, 6};
            for (unsigned i = 0; i < 4; ++i)
                if (index == static_cast<unsigned>(tops[i])) {
                    auto *hub = reinterpret_cast<NestedMenuTab *>(hubs[i]);
                    hub->mPage = -1;
                    hub->mSel = 0;
                }
            if (index == 5)
                reinterpret_cast<MenuSoundsDisplayTab *>(sMenuRuntime.soundDisplay)->mTopRow = 0;
            mTabs[top]->focus();
        }
        return true;
    }
    index -= topCount;
    for (const Group &group : groups) {
        auto *tab = reinterpret_cast<MenuTab *>(reinterpret_cast<u8 *>(&sMenuRuntime) + group.offset);
        entry = {nullptr, mTabs[group.top + firstTop]->title(), tab->title(), nullptr};
        int page = 0, row = -1;
        const auto offer = [&](const char *label) {
            if (index) { --index; return false; }
            entry.label = label;
            return true;
        };
        // Direct top tabs already appeared above.
        if (group.top != 4 && group.top != 7 && group.kind != DISPLAY &&
            offer(tab->title())) goto found;
        switch (group.kind) {
        case CATEGORY: {
            auto copy = *static_cast<CategorySettingsTab *>(tab);
            const int pages = copy.hasPages() ? copy.pageCount() : 1;
            for (int p = 0; p < pages; ++p) {
                page = copy.hasPages() ? p + 1 : 0;
                copy.mMode = page;
                row = 0;
                if (page) {
                    entry.page = copy.pages()[p].name;
                    if (offer(entry.page)) goto found;
                }
                u8 ids[kMenuSettingCount];
                const int count = copy.buildList(ids);
                for (row = 0; row < count + copy.extraRows(); ++row)
                    if (offer(row < count ?
                        (displayFavoriteId(ids[row]) ? DisplayFavorites::name(ids[row] - kDisplayFavoriteFirst)
                                                     : Settings::name(static_cast<SettingId>(ids[row]))) :
                        copy.extraRowName(row - count))) goto found;
            }
            break;
        }
        case CREATION: {
            auto copy = *static_cast<CreationTab *>(tab);
            for (page = 1; page <= CreationTab::PAGE_COUNT; ++page) {
                copy.mPage = page;
                row = copy.pageFirst();
                entry.page = CreationTab::pageName(page - 1);
                if (offer(entry.page)) goto found;
                for (; row < copy.pageEnd(); ++row)
                    if (offer(copy.rowName(row))) goto found;
            }
            break;
        }
        case BINDS:
            for (page = 1; page <= BindsTab::pageCount(); ++page) {
                entry.page = kBindPages[page - 1].name;
                row = 0;
                if (offer(entry.page)) goto found;
                for (; row < kBindPages[page - 1].count; ++row)
                    if (offer(Binds::name(BindsTab::bindAt(kBindPages[page - 1].first + row)))) goto found;
            }
            break;
        case TAS:
            for (page = TasProjectTab::MAIN; page <= TasProjectTab::CHECKPOINTS; ++page) {
                if (page) entry.page = TasProjectTab::rowName(TasProjectTab::MAIN, 5);
                for (row = 0; row < (page ? 5 : 10); ++row)
                    if (offer(TasProjectTab::rowName(page, row))) goto found;
            }
            break;
        case CAMERA:
            for (row = 0; row < static_cast<PracticeControlsTab *>(tab)->rowCount(); ++row)
                if (offer(PracticeControlsTab::rowName(row))) goto found;
            break;
        case STATES:
            for (page = 0; page < 2; ++page) {
                if (page) entry.page = SavestatesTab::rowName(SavestatesTab::ROW_SD);
                for (row = 0; row < (page ? SavestatesTab::SD_FILES : SavestatesTab::ROW_COUNT); ++row)
                    if (offer(SavestatesTab::rowName(row, page))) goto found;
            }
            break;
        case ILS:
            for (row = 0; row < ILingTab::OPTION_COUNT + ILing::count(); ++row) {
                const int position = row - ILingTab::OPTION_COUNT;
                if (position >= 0) entry.page = ILing::menuGroupName(position);
                if (offer(position < 0 ? ILingTab::optionName(row) :
                    ILing::label(ILing::menuEntryAt(position)))) goto found;
            }
            break;
        case LOADER: {
            auto *loader = static_cast<StageLoaderTab *>(tab);
            for (row = 0; row < loader->optionCount(); ++row)
                if (offer(loader->optionName(loader->optionAt(row)))) goto found;
            page = 1;
            for (row = 0; row < loader->catalogueCount(); ++row)
                if (offer(ILing::label(loader->catalogueEntryAt(row)))) goto found;
            break;
        }
        case SAFETY:
            for (row = 0; row < Settings::ilPbSettingCount(); ++row)
                if (offer(Settings::name(Settings::ilPbSettingAt(row)))) goto found;
            break;
        case GHOSTS:
            for (row = 0; row <= GhostsTab::SAVE_NEW_SELECTION; ++row)
                if (!GhostVisualMenu::hiddenSelection(row) && offer(GhostsTab::rowName(row))) goto found;
            row = GhostsTab::IMPORT_SCAN_SELECTION;
            if (offer(GhostsTab::rowName(row))) goto found;
            row = GhostsTab::IMPORTED_PAGE_SELECTION;
            if (offer(GhostsTab::rowName(row))) goto found;
            page = 1;
            entry.page = GhostVisualMenu::kTitle;
            for (row = 0; row < GhostVisualMenu::kCount; ++row)
                if (offer(Settings::name(GhostVisualMenu::kSettings[row]))) goto found;
            break;
        case GUIDE:
            for (row = 0; row < 6; ++row)
                if (offer(GuideTab::pageName(row))) goto found;
            break;
        case DISPLAY:
            for (row = 0; row < 2; ++row)
                if (offer(MenuSoundsDisplayTab::rowName(row))) goto found;
            break;
#if TIMEWARP_LIVE_RACING
        case ONLINE:
            for (row = 0; row < OnlineTab::ROW_COUNT; ++row)
                if (offer(OnlineTab::rowName(row))) goto found;
            break;
#endif
        default: break;
        }
        continue;
found:
        if (!open) return true;
        switch (group.kind) {
        case CATEGORY: {
            auto *target = static_cast<CategorySettingsTab *>(tab);
            target->mMode = page; target->mSel = row < 0 ? 0 : row;
            break;
        }
        case CREATION: {
            auto *target = static_cast<CreationTab *>(tab);
            target->mPage = page; target->mSel = row < 0 ? 0 : row;
            break;
        }
        case BINDS: {
            auto *target = static_cast<BindsTab *>(tab);
            target->mPage = page; target->mSel = row < 0 ? 0 : row;
            break;
        }
        case TAS: {
            auto *target = static_cast<TasProjectTab *>(tab);
            target->mPage = page; target->mSel = row < 0 ? 0 : row;
            break;
        }
        case STATES: {
            auto *target = static_cast<SavestatesTab *>(tab);
            target->mSD = page;
            if (page) target->mSDsel = row;
            else target->mSel = row < 0 ? 0 : row;
            break;
        }
        case LOADER: {
            auto *target = static_cast<StageLoaderTab *>(tab);
            target->mSel = row < 0 ? 0 : row + (page ? target->catalogueFirst() : 0);
            break;
        }
        case GHOSTS: {
            auto *target = static_cast<GhostsTab *>(tab);
            target->mChoice = page ? GhostsTab::CHOICE_VISUALS : GhostsTab::CHOICE_NONE;
            target->mSel = row < 0 ? 0 : row;
            target->mPromptInput.begin(SUSAMUNE_BIND_BUTTON_MASK);
            break;
        }
        case CAMERA: static_cast<PracticeControlsTab *>(tab)->mSel = row < 0 ? 0 : row; break;
        case ILS: static_cast<ILingTab *>(tab)->mSel = row < 0 ? 0 : row; break;
        case SAFETY: static_cast<PBSafetyTab *>(tab)->mSel = row < 0 ? 0 : row; break;
        case GUIDE: static_cast<GuideTab *>(tab)->mPage = row < 0 ? 0 : row; break;
        case DISPLAY: {
            auto *target = static_cast<MenuSoundsDisplayTab *>(tab);
            target->mParent->mPage = -1;
            target->mTopRow = row;
            break;
        }
#if TIMEWARP_LIVE_RACING
        case ONLINE: static_cast<OnlineTab *>(tab)->mSel = row < 0 ? 0 : row; break;
#endif
        default: break;
        }
        mCurTab = group.top + firstTop;
        u8 *hubStorage = group.top == 1 ? sMenuRuntime.settingsHub :
            group.top == 2 ? sMenuRuntime.ilsHub :
            group.top == 5 ? sMenuRuntime.displayHub :
            group.top == 6 ? sMenuRuntime.systemHub : nullptr;
        if (hubStorage && group.kind != DISPLAY)
            reinterpret_cast<NestedMenuTab *>(hubStorage)->openChild(tab);
        else tab->focus();
        mTabFirst = mCRepeatFrames = 0;
        return true;
    }
    return false;
}

SEARCH_CODE(active) bool Menu::searchActive() const { return sMenuRuntime.search.mode != MenuSearch::CLOSED; }
SEARCH_CODE(available) bool Menu::searchAvailable() const {
    if (!mShown || searchActive() || mTabs[mCurTab]->grabsInput()) return false;
    const u8 *hubs[] = {sMenuRuntime.settingsHub, sMenuRuntime.ilsHub,
                       sMenuRuntime.systemHub};
    for (const u8 *storage : hubs)
        if (mTabs[mCurTab] == reinterpret_cast<const MenuTab *>(storage))
            return reinterpret_cast<const NestedMenuTab *>(storage)->current() == nullptr;
    if (mTabs[mCurTab] == reinterpret_cast<MenuTab *>(sMenuRuntime.soundDisplay))
        return reinterpret_cast<MenuSoundsDisplayTab *>(sMenuRuntime.soundDisplay)->mParent->current() == nullptr;
    return false;
}

// Search (L+Y by default) only exists where searchAvailable() says so, which
// already excludes sub-pages such as the creation editor and its Y steps.
SEARCH_CODE(shortcut) bool Menu::searchShortcut(TMarioGamePad *pad) {
    const u32 search = searchAvailable() ? gBinds.get(BIND_MENU_SEARCH) : 0;
    if (search && gBinds.wasPressedRaw(BIND_MENU_SEARCH)) {
        openSearch();
        return true;
    }
    // A shoulder that starts a search combo changes tabs on release instead,
    // so holding it for the combo does not leave the page first.
    const u32 shoulder = (search & (search - 1)) ? search & (TMarioGamePad::L | TMarioGamePad::R) : 0;
    const u32 tabs = (pad->mButtons.mRapidInput & ~shoulder) | (pad->mButtons._8 & shoulder);
    if (tabs & TMarioGamePad::L) switchTab(-1);
    if (tabs & TMarioGamePad::R) switchTab(+1);
    return false;
}

SEARCH_CODE(open) void Menu::openSearch() {
    if (!searchAvailable()) return;
    auto &state = sMenuRuntime.search;
    state = {};
    state.mode = MenuSearch::KEYBOARD;
    state.input.begin(SUSAMUNE_BIND_BUTTON_MASK);
}

SEARCH_CODE(cache) void Menu::cacheSearch(bool recount) {
    auto &state = sMenuRuntime.search;
    state.first = listScrollStart(state.selected, state.count, 6);
    state.visible = 0;
    unsigned match = 0;
    MenuSearch::Entry entry;
    for (unsigned i = 0; searchEntry(i, entry); ++i) {
        if (!MenuSearch::matches(state.query, entry)) continue;
        if (match >= state.first && state.visible < 6)
            state.results[state.visible++] = {entry, static_cast<u16>(i)};
        ++match;
        if (!recount && state.visible == 6) break;
    }
    if (recount) state.count = match;
}

SEARCH_CODE(update) void Menu::updateSearch(TMarioGamePad *pad) {
    using namespace MenuSearch;
    auto &state = sMenuRuntime.search;
    const u16 held = JUTGamePad::mPadStatus[0].mButton & SUSAMUNE_BIND_BUTTON_MASK;
    if (state.mode == RELEASE) {
        if (!held) state.mode = CLOSED;
        return;
    }
    const u16 pressed = state.input.update();
    if ((pressed & JUTGamePad::START) && (held & JUTGamePad::X)) {
        state.mode = RELEASE;
        return;
    }
    if (state.mode == KEYBOARD) {
        if (pressed & JUTGamePad::START) {
            state.selected = state.count = 0;
            cacheSearch(true);
            state.mode = RESULTS;
            state.input.begin(SUSAMUNE_BIND_BUTTON_MASK);
        } else if (pressed & JUTGamePad::Z) {
            state.length = 0; state.query[0] = 0;
        } else {
            updateCreationKeyboardButtons(pressed, state.query, state.length,
                sizeof(state.query) - 1, state.page, state.upper, state.cursor);
        }
        return;
    }
    if (pressed & JUTGamePad::B) {
        state.mode = KEYBOARD;
        state.input.begin(SUSAMUNE_BIND_BUTTON_MASK);
        return;
    }
    const u32 nav = navigationInput(pad);
    if (state.count) {
        if (nav & TMarioGamePad::CSTICK_UP) state.selected = wrap(state.selected - 1, state.count);
        else if (nav & TMarioGamePad::CSTICK_DOWN) state.selected = wrap(state.selected + 1, state.count);
        if (listScrollStart(state.selected, state.count, 6) != state.first) cacheSearch(false);
        if (pressed & JUTGamePad::A) {
            Entry entry;
            const unsigned row = state.selected - state.first;
            if (row < state.visible) {
                searchEntry(state.results[row].index, entry, true);
                // The selection press must never reach the destination action.
                state.mode = RELEASE;
            }
        }
    }
}

SEARCH_CODE(draw) bool Menu::drawSearch() {
    using namespace MenuSearch;
    const auto &state = sMenuRuntime.search;
    if (state.mode == CLOSED || state.mode == RELEASE) return false;
    MenuTheme::page(false);
    if (state.mode == KEYBOARD) {
        drawCreationKeyboard(this, "Search Moonshine", state.query, state.page, state.upper, state.cursor);
        return true;
    }
    fillMenuBox(36, 64, 568, 360, cPanel());
    char line[160];
    snprintf(line, sizeof(line), "Search: %s", state.query[0] ? state.query : "All built-in options");
    drawMenuText(line, 56, 82, 18, 18, cTitle());
    snprintf(line, sizeof(line), "%u results", state.count);
    drawMenuText(line, 56, 108, 12, 12, cRowDim());
    for (unsigned i = 0; i < state.visible; ++i) {
        const Entry &entry = state.results[i].entry;
        const int y = 140 + i * 39;
        drawValueRow(this, 52, y, 536, entry.label, nullptr, state.first + i == state.selected, false, true);
        snprintf(line, sizeof(line), "%s%s%s%s%s", entry.section,
            entry.group && entry.group != entry.section ? " / " : "",
            entry.group && entry.group != entry.section ? entry.group : "",
            entry.page ? " / " : "", entry.page ? entry.page : "");
        char path[256];
        fitHelpLine(line, path, 524, 11);
        drawMenuText(path, 60, y + 22, 11, 11, cRowDim());
    }
    if (!state.count) drawMenuText("No matching options. Try fewer words.", 56, 160, 16, 16, cRow());
    drawFooterText(this, SUSAMUNE_GLYPH_A " Open   " SUSAMUNE_GLYPH_B " Edit search   "
        SUSAMUNE_GLYPH_X "+Start Cancel", 56, 396);
    return true;
}

#undef SEARCH_CODE
#pragma clang section text="" rodata="" data="" bss=""
