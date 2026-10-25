#pragma clang section text=""
namespace {
// Named arrays keep new text out of the fixed menu literal pools.
namespace OnlineText {
static const char chooseHelp[] = SUSAMUNE_GLYPH_A " Select   " SUSAMUNE_GLYPH_C " L" SUSAMUNE_GLYPH_SLASH "R World   " SUSAMUNE_GLYPH_B " Cancel";
static const char title[] = "Online";
static const char disconnectFirst[] = "Disconnect first";
static const char fixedStart[] = "This IL has a fixed start";
static const char unavailableAction[] = "Not available - check connection";
static const char finishedAction[] = "Match over - host sets up next";
static const char matchFinished[] = "Match finished";
static const char finishedHelp[] = "Host: pick the next IL or mode, then Apply.";
static const char freeRoam[] = "Free roam";
static const char raceMode[] = "IL racing";
static const char playlistMode[] = "Stageloader race";
static const char draftMode[] = "Draft set";
static const char draftOnly[] = "Draft sets only";
static const char manualOnly[] = "Choose ILs in the draft list";
static const char draftPoolNames[] = "Any%\0All ILs\0Non-Any%";
static const char draftSetNames[] = "Best of 3\0Best of 5";
static const char draftOpen[] = "Open IL list";
static const char draftTurn[] = "Your turn";
static const char draftWait[] = "Opponent's turn";
static const char draftPending[] = "Sending selection...";
static const char draftNoList[] = "Connect in Draft set mode first";
static const char draftTitle[] = "IL draft";
static const char draftBan[] = "Ban an IL";
static const char draftPick[] = "Choose an IL";
static const char draftPeerBan[] = "Opponent is banning";
static const char draftPeerPick[] = "Opponent is choosing";
static const char draftBanHelp[] = SUSAMUNE_GLYPH_A " Ban selected IL    " SUSAMUNE_GLYPH_B " Online setup";
static const char draftPickHelp[] = SUSAMUNE_GLYPH_A " Choose selected IL    " SUSAMUNE_GLYPH_B " Online setup";
static const char draftBackHelp[] = SUSAMUNE_GLYPH_B " Online setup / Ready / Disconnect";
static const char draftBanned[] = "BANNED";
static const char draftChosen[] = "CHOSEN";
static const char draftAvailable[] = "Available";
static const char draftSelectedHelp[] = "IL chosen - both choose Ready.";
static const char draftWaitingHelp[] = "You can leave this list.";
static const char draftScoreFormat[] = "Set: %u - %u  (Bo%u)   |   IL rounds: %u - %u  (Bo3)";
static const char draftSummaryFormat[] = "Set: %u - %u  (Bo%u)   |   Rounds: %u - %u";
static const char draftFixedBest[] = "3 per IL";
static const char freeRoamAction[] = "Free roam - host can pick IL racing";
static const char hostOnly[] = "Host only";
static const char applySetup[] = "Apply";
static const char finishFirst[] = "Finish the match first";
static const char setupAvailable[] = "Host can edit race setup";
static const char namePrompt[] = "Online name (16 characters)";
static const char pingFormat[] = "%lu ms";
static const char peerFormat[] = "%s  |  Peer: %.16s  |  %s";
static const char offline[] = "Offline";
static const char networkFormat[] = "Wii net: %s %us  IP %u.%u.%u.%u:%u  Error %ld";
static const char socketFormat[] = "ARM took %u  Socket TX %u RX %u Drop %u Err S/R %u/%u Code %ld";
static const char netOff[] = "off";
static const char netWaiting[] = "waiting for IP";
static const char netUp[] = "up";
static const char netFailed[] = "failed";
static const char *const netState[] = {netOff, netWaiting, netUp, netFailed};
static const char noDiagnostics[] = "Socket diagnostics unavailable";
static const char packetFormat[] = "PPC TX %lu RX %lu OK %lu";
static const char scoreFormat[] = "Score: %u - %u   |   IL Best of %u";
static const char noRace[] = "No race";
static const char readyFormat[] = "You: %s  |  Peer: %s  |  %s";
static const char notReady[] = "Not ready";
static const char locked[] = "Setup locked";
static const char prototype[] = "Two-player online prototype";
static const char empty[] = "";
static const char armRace[] = "Arm race";
static const char connectFirst[] = "Connect first";
static const char leave[] = "Leave session";
static const char hostHelp[] = "Create or join a room, swap codes.";
static const char roomHelp[] = "Both players choose Ready to start.";
static const char codePrompt[] = "Friend's code (14 characters)";
static const char codeHelp[] = SUSAMUNE_GLYPH_A " Type   " SUSAMUNE_GLYPH_X " Delete   " SUSAMUNE_GLYPH_Y " Last friend   START Enter";
static const char codeBack[] = SUSAMUNE_GLYPH_B " Back to Online";
static const char scoreTitle[] = "Online score bar";
static const char modelNames[] = "Shadow Mario\0Piantissimo\0Mario";
static const char codeChanged[] = "Your code changed - resend it";
static const char codeShare[] = "Send this code to a friend";
static const char localCodeShare[] = "Same router? Exchange the Same-network codes.";
static const char gettingAddress[] = "Getting address...";
static const char enterFriend[] = "Enter";
static const char natIdle[] = "Press A to test";
static const char roomFirst[] = "Create or join a room";
static const char needName[] = "Enter a name first";
static const char printableName[] = "Use printable characters";
static const char invalidSetup[] = "Setup invalid or busy";
static const char stunBusy[] = "NAT already tested online";
static const char stunFormat[] = "STUN %s  tries %u  A %s  B %s";
static const char stunRunning[] = "probing...";
static const char stunSame[] = "SAME - should work";
static const char stunDifferent[] = "DIFFERENT - symmetric";
static const char stunOne[] = "one reply - retry A";
static const char stunNone[] = "no reply - retry A";
static const char stunFailed[] = "failed, code %d";
static const char endpointFormat[] = "%u.%u.%u.%u:%u";
static const char none[] = "--";
static const char setupPage[] = "Race setup";
static const char opponentPage[] = "Opponent display";
static const char connectionPage[] = "Connection help";
static const char openPage[] = "Open";
static const char codeSteps[] = "Send your code, then enter your friend's code.";
static const char offlineSteps[] = "Choose a name, then create or join a room.";
static const char guestSetup[] = "The host chooses the next race setup.";
static const char lockedSetup[] = "This match is in progress; setup is locked.";
static const char savedSetup[] = "Options saved. Create or join when ready.";
static const char applySteps[] = "Choose the next mode or IL, then Apply next setup.";
static const char roamSteps[] = "Explore together. Race setup starts a new match.";
static const char connectionSteps[] = "NAT test runs offline. Details help diagnose a connection.";
static const char displaySteps[] = "Choose what you see. Score visibility and style are separate.";
static const char sessionFormat[] = "Score %u-%u  |  %s";
static const char draftStatusFormat[] = "Set %u-%u  |  Rounds %u-%u  |  %s";
static const char readyPeer[] = "Peer ready - press A";
static const char readyCancel[] = "Ready - A to cancel";
static const char readyStart[] = "Press A when ready";
static const char natAutomatic[] = "Automatic online";

}

class OnlineTab final : public MenuTab {
    friend class ::Menu;
public:
    OnlineTab() : mSel(0), mMode(NONE), mCursor(0), mLength(0), mPage(0),
                  mUpper(false), mDiagnostics(false), mSection(HOME) {
        // The tab lives in uncleared MEM2 runtime storage: the editor must start idle.
        mEditor.reset();
        focus();
    }
    const char *title() const override { return OnlineText::title; }
    bool grabsInput() const override { return mMode != NONE || LiveRace::holdingStart(); }
    bool suppressesBinds() const override { return true; }
    bool fullScreen() const override { return mMode != NONE && mMode != ENTRY && mMode != PLAYLIST && mMode != FORFEIT && mMode != KICK; }
    // After each online IL: Ready, or the draft list while a set is drafting.
    void openAfterRound() {
        const LiveRace::Status status = LiveRace::status();
        mSection = HOME;
        mMode = status.drafting ? DRAFT_PICK : NONE;
        mSel = mMode ? DRAFT_ROW : status.matchDone || status.freeRoam ? RACE_PAGE_ROW : READY_ROW;
        mCursor = 0;
        focus();
    }
    void focus() override { mInput.begin(JUTGamePad::A | JUTGamePad::B | JUTGamePad::X | JUTGamePad::Y); }
    bool back() override {
        if (mMode == FRIEND) mSection = HOME;
        if (mMode == NONE) {
            if (mSection == HOME) return false;
            mSel = mSection == SETUP ? RACE_PAGE_ROW : mSection == OPPONENT ? OPPONENT_PAGE_ROW : CONNECTION_PAGE_ROW;
            mSection = HOME;
        } else mMode = NONE;
        focus();
        return true;
    }

    void update(Menu *menu, TMarioGamePad *pad) override {
        const u16 pressed = mInput.update();
        const LiveRace::Status status = LiveRace::status();
        if (mMode == KICK) {
            if (pressed & JUTGamePad::B) { back(); return; }
            if (pressed & JUTGamePad::A) { LiveRace::kickGuest(mSel - GUEST1_ROW); back(); }
            return;
        }
        if (mMode == FORFEIT) {
            if (!status.canForfeit || (pressed & JUTGamePad::B)) { back(); return; }
            if (pressed & JUTGamePad::A) { LiveRace::forfeit(); back(); }
            return;
        }
        if (LiveRace::holdingStart()) {
            if (pressed & (JUTGamePad::A | JUTGamePad::B)) LiveRace::ready();
            return;
        }
        if (mMode == DRAFT_PICK) {
            if (pressed & JUTGamePad::B) { back(); return; }
            if (!status.active || !LiveRace::options().draft) { back(); return; }
            const u32 nav = menu->navigationInput(pad);
            const auto *group = LiveRace::groupState();
            const unsigned count = group ? group->config.players + 1 : LiveDraft::CANDIDATE_COUNT;
            if (nav & TMarioGamePad::CSTICK_UP) mCursor = wrap(mCursor - 1, count);
            else if (nav & TMarioGamePad::CSTICK_DOWN) mCursor = wrap(mCursor + 1, count);
            if (!(pressed & JUTGamePad::A)) return;
            if (!draftTurn(status) || status.draftPending ||
                (group ? group->candidates[mCursor] : status.draft.candidates[mCursor]) >= (unsigned)ILing::count() ||
                ((group ? group->bannedMask : status.draft.bannedMask) & (1u << mCursor))) {
                menu->toast(status.race); return;
            }
            if (!LiveRace::chooseDraft(mCursor)) menu->toast(LiveRace::status().race);
            return;
        }
        if (mMode == SCORE) {
            const CreationStyle defaults = {320, 16, 100, 255, 0, 0, 0, 130, 255, 0};
            static const u8 white[1][3] = {{255, 255, 255}};
            const u8 result = mEditor.update(pad, defaults, white);
            LiveRace::Prefs prefs = LiveRace::prefs();
            prefs.scoreX = mStyle.x; prefs.scoreY = mStyle.y; prefs.scoreScale = mStyle.scale;
            if (result & (CreationEditor::UPDATE_FINISHED | CreationEditor::UPDATE_CANCELLED)) {
                if (result & CreationEditor::UPDATE_CANCELLED) prefs = mPrefs;
                LiveRace::setPrefs(prefs);
                back();
            }
            return;
        }
        if (mMode == PLAYLIST) {
            if (pressed & JUTGamePad::B) { back(); return; }
            if (status.active && !status.setupEditable) { back(); return; }
            const u32 nav = menu->navigationInput(pad);
            if (nav & TMarioGamePad::CSTICK_UP) mCursor = wrap(mCursor - 1, 11);
            if (nav & TMarioGamePad::CSTICK_DOWN) mCursor = wrap(mCursor + 1, 11);
            if (pressed & JUTGamePad::A) {
                const bool loaded = mCursor == 0 ? StageLoader::queueCount() > 0 : mCursor <= 3 ?
                    StageLoader::loadBuiltinPlaylist(mCursor - 1) : StageLoader::loadCustomPlaylist(mCursor - 4);
                if (!loaded) { menu->toast("Playlist empty or unavailable"); return; }
                if (apply(menu)) back();
            }
            return;
        }
        if (mMode == FRIEND) {
            if (pressed & JUTGamePad::B) { back(); return; }
            if ((pressed & JUTGamePad::START) &&
                (JUTGamePad::mPadStatus[0].mButton & JUTGamePad::X)) { back(); return; }
            if (!status.active || (status.connected && !(status.hosting && LiveRace::groupState()))) { back(); return; }
            // Returning home retains the connection and the partial code.
            const u32 nav = menu->navigationInput(pad);
            int col = mCursor & 7, row = mCursor >> 3;
            if ((pressed & JUTGamePad::DPAD_LEFT) || (nav & TMarioGamePad::CSTICK_LEFT)) col = (col + 7) & 7;
            if ((pressed & JUTGamePad::DPAD_RIGHT) || (nav & TMarioGamePad::CSTICK_RIGHT)) col = (col + 1) & 7;
            if ((pressed & JUTGamePad::DPAD_UP) || (nav & TMarioGamePad::CSTICK_UP)) row = (row + 3) & 3;
            if ((pressed & JUTGamePad::DPAD_DOWN) || (nav & TMarioGamePad::CSTICK_DOWN)) row = (row + 1) & 3;
            mCursor = static_cast<u8>(row * 8 + col);
            if (pressed & JUTGamePad::X) {
                if (mLength) mCode[--mLength] = 0;
            } else if (pressed & JUTGamePad::Y) {
                if (LiveRace::lastFriend(mCode)) mLength = LiveP2P::CODE_CHARS;
            } else if ((pressed & JUTGamePad::A) && mLength < LiveP2P::CODE_CHARS) {
                mCode[mLength++] = LiveP2P::symbol(mCursor); mCode[mLength] = 0;
                if (mLength < LiveP2P::CODE_CHARS) return;
            } else if (!(pressed & JUTGamePad::START)) return;
            if (mLength == LiveP2P::CODE_CHARS && enterCode(menu)) back();
            return;
        }
        if (mMode != NONE) {
            // A connection may start or end while an editor is open.
            if (status.active && (!status.setupEditable || mMode == NAME)) { back(); return; }
            if (mMode == NAME) {
                if (pressed & JUTGamePad::START) {
                    if ((JUTGamePad::mPadStatus[0].mButton & JUTGamePad::X) || apply(menu)) back();
                } else if (pressed & JUTGamePad::Z) {
                    mLength = 0; mDraft.name[0] = 0;
                } else {
                    updateCreationKeyboardButtons(pressed, mDraft.name, mLength,
                        sizeof(mDraft.name) - 1, mPage, mUpper, mCursor);
                }
                return;
            }
            if (pressed & JUTGamePad::B) { back(); return; }
            const u32 nav = menu->navigationInput(pad);
            int position = ILing::menuPositionOf(mDraft.entry);
            if (nav & TMarioGamePad::CSTICK_UP) position = wrap(position - 1, ILing::count());
            else if (nav & TMarioGamePad::CSTICK_DOWN) position = wrap(position + 1, ILing::count());
            else if (nav & TMarioGamePad::CSTICK_LEFT) position = ILing::jumpMenuGroup(position, -1);
            else if (nav & TMarioGamePad::CSTICK_RIGHT) position = ILing::jumpMenuGroup(position, 1);
            const int entry = ILing::menuEntryAt(position);
            if (entry != mDraft.entry && ILing::streakEntrySelectable(entry)) {
                mDraft.entry = entry;
                const int episode = ILing::selectedEpisode(entry);
                mDraft.episode = episode >= 0 && episode < 8 ? episode : 0;
            }
            if ((pressed & JUTGamePad::A) && apply(menu)) back();
            return;
        }

        if (normalize(status)) return;
        if ((pressed & JUTGamePad::B) && mSection != HOME) { back(); return; }
        const u32 nav = menu->navigationInput(pad);
        if (nav & TMarioGamePad::CSTICK_UP) moveSelection(-1, status);
        else if (nav & TMarioGamePad::CSTICK_DOWN) moveSelection(1, status);
        const int direction = (nav & TMarioGamePad::CSTICK_LEFT) ? -1 :
                              (nav & TMarioGamePad::CSTICK_RIGHT) ? 1 : 0;
        if (!(pressed & JUTGamePad::A) && !direction) return;
        const int step = direction ? direction : 1;
        if (mSel >= RACE_PAGE_ROW && mSel <= CONNECTION_PAGE_ROW) {
            if (pressed & JUTGamePad::A) openPage(mSel == RACE_PAGE_ROW ? SETUP : mSel == OPPONENT_PAGE_ROW ? OPPONENT : CONNECTION, status);
            return;
        }
        if (mSection == CONNECTION && mSel == NAT_ROW && (pressed & JUTGamePad::A)) {
            // NAT probe on the race's own local port; online runs it automatically.
            if (status.active || !LiveStun::start(LiveRace::LOCAL_PORT)) menu->toast(OnlineText::stunBusy);
            return;
        }
        if (mSel == DIAGNOSTICS_ROW) { mDiagnostics = !mDiagnostics; return; }
        if (mSel == SCORE_VISIBLE_ROW) {
            LiveRace::Prefs prefs = LiveRace::prefs();
            prefs.hideScore = !prefs.hideScore; LiveRace::setPrefs(prefs); return;
        }
        if (mSel == INPUTS_ROW) { LiveGhost::setInputsShown(!LiveGhost::inputsShown()); return; }
        if (mSel >= SHOW_ROW && mSel <= SCORE_ROW) {
            LiveRace::Prefs prefs = LiveRace::prefs();
            if (mSel == SHOW_ROW) prefs.hideOpponent = !prefs.hideOpponent;
            else if (mSel == MODEL_ROW) prefs.model = wrap(prefs.model + step, LiveRace::MODEL_COUNT);
            else if (pressed & JUTGamePad::A) {
                // The Creation layout editor: position and size only, QFT untouched.
                mPrefs = prefs;
                mStyle.x = prefs.scoreX; mStyle.y = prefs.scoreY; mStyle.scale = prefs.scoreScale;
                mStyle.textA = 255; mStyle.bgA = 130;
                mEditor.setScaleLimits(50, 200);
                mEditor.begin(&mStyle, mRgb, mRgbBackup, 1, 0, nullptr,
                              CreationEditor::CAP_POSITION | CreationEditor::CAP_SCALE);
                if (mEditor.editing()) mMode = SCORE;
                return;
            } else return;
            LiveRace::setPrefs(prefs);
            return;
        }
        if (mSel == NAME_ROW || mSel == PLAYERS_ROW || (mSel >= ENTRY_ROW && mSel <= SET_LENGTH_ROW)) {
            if (mSel == PLAYERS_ROW && status.active) { menu->toast("Choose room size before connecting"); return; }
            if (status.active && (!status.setupEditable || mSel == NAME_ROW)) {
                menu->toast(mSel == NAME_ROW ? OnlineText::disconnectFirst : !status.hosting ? OnlineText::guestSetup : OnlineText::lockedSetup); return;
            }
            mDraft = LiveRace::options();
            if (mDraft.draft && mSel >= ENTRY_ROW && mSel <= BEST_ROW) {
                menu->toast(OnlineText::manualOnly); return;
            }
            if (!mDraft.draft && (mSel == POOL_ROW || mSel == SET_LENGTH_ROW)) {
                menu->toast(OnlineText::draftOnly); return;
            }
            if (mSel == EPISODE_ROW || mSel == BEST_ROW || mSel >= MODE_ROW) {
                if (mSel == PLAYERS_ROW) mDraft.players = 2 + wrap((mDraft.players < 2 ? 2 : mDraft.players) - 2 + step, 3);
                else if (mSel == MODE_ROW) {
                    const int mode = wrap((mDraft.playlist ? 3 : mDraft.freeRoam ? 2 : mDraft.draft ? 1 : 0) + step, 4);
                    mDraft.freeRoam = mode == 2;
                    mDraft.draft = mode == 1;
                    mDraft.playlist = mode == 3;
                    if (mDraft.playlist) {
                        mDraft.bestOf = 1;
                        if (!StageLoader::queueCount()) StageLoader::loadBuiltinPlaylist(1);
                    }
                    if (mDraft.draft) mDraft.bestOf = 3;
                } else if (mSel == POOL_ROW) mDraft.pool = wrap(mDraft.pool + step, 3);
                else if (mSel == SET_LENGTH_ROW) mDraft.setBo5 = !mDraft.setBo5;
                else if (mSel == BEST_ROW) mDraft.bestOf = 1 + 2 * wrap((mDraft.bestOf - 1) / 2 + step, 4);
                else if (ILing::canChooseEpisode(mDraft.entry))
                    mDraft.episode = wrap(mDraft.episode + step, 8);
                else { menu->toast(OnlineText::fixedStart); return; }
                apply(menu);
            } else if (pressed & JUTGamePad::A) beginEdit(mSel == NAME_ROW ? NAME : mDraft.playlist ? PLAYLIST : ENTRY);
            return;
        }
        if (!(pressed & JUTGamePad::A)) return;
        bool accepted = false;
        if (mSel == DRAFT_ROW) {
            if (!status.active || !LiveRace::options().draft || (!LiveRace::groupState() && status.draft.phase == LiveDraft::UNINITIALIZED)) {
                menu->toast(OnlineText::draftNoList); return;
            }
            mMode = DRAFT_PICK;
            mCursor = 0;
            focus();
            return;
        }
        if (mSel == FORFEIT_ROW && status.canForfeit) { mMode = FORFEIT; focus(); return; }
        if (mSel == DISCONNECT_ROW) { LiveRace::disconnect(); return; }
        if (mSel == HOST_ROW && !status.active) accepted = LiveRace::host();
        // The joiner's next step is the host's code, so its keyboard opens at once.
        if (mSel == JOIN_ROW && !status.active && LiveRace::join()) mSel = FRIEND_ROW;
        else if (mSel == CODE_ROW || mSel == LOCAL_CODE_ROW || mSel == FRIEND_ROW) {
            if (!status.active || (status.connected && !(status.hosting && LiveRace::groupState()))) { menu->toast(OnlineText::roomFirst); return; }
            if (mSel == CODE_ROW) { menu->toast(status.code[0] ? OnlineText::codeShare : OnlineText::gettingAddress); return; }
            if (mSel == LOCAL_CODE_ROW) { menu->toast(status.localCode[0] ? OnlineText::localCodeShare : OnlineText::gettingAddress); return; }
        }
        if (mSel == FRIEND_ROW || (mSel >= GUEST1_ROW && mSel <= GUEST3_ROW)) {
            if (mSel >= GUEST1_ROW && LiveRace::guestName(mSel - GUEST1_ROW)) {
                mMode = KICK; focus(); return;
            }
            mCode[0] = 0;
            beginEdit(FRIEND);
            return;
        }
        if (mSel == READY_ROW && status.matchDone) { menu->toast(OnlineText::finishedAction); return; }
        if (mSel == READY_ROW && status.freeRoam) { menu->toast(OnlineText::freeRoamAction); return; }
        if (mSel == READY_ROW && status.connected) {
            if (!LiveRace::ready()) menu->toast(LiveRace::status().race);
            return;
        }
        if (mSel == SETUP_ROW && status.connected) {
            if (!status.hosting) { menu->toast(OnlineText::hostOnly); return; }
            if (!LiveRace::newMatch()) menu->toast(OnlineText::finishFirst);
            else { mSection = HOME; mSel = LiveRace::options().draft ? DRAFT_ROW : READY_ROW; focus(); }
            return;
        }
        if (!accepted) menu->toast(OnlineText::unavailableAction);
    }

    void draw(Menu *menu, int x, int y, int w, int h) override {
        if (mMode == NAME) {
            drawCreationKeyboard(menu, OnlineText::namePrompt, mDraft.name, mPage, mUpper, mCursor);
            return;
        }
        if (mMode == FRIEND) { drawCode(menu); return; }
        if (mMode == KICK) {
            drawHelpLine(menu, x, y + 32, w, 60, "Remove this guest? They cannot rejoin until you enter their code again.");
            drawFooterText(menu, SUSAMUNE_GLYPH_A " Kick guest   " SUSAMUNE_GLYPH_B " Cancel", x + 4, y + 120);
            return;
        }
        if (mMode == FORFEIT) {
            drawHelpLine(menu, x, y + 32, w, 60, "Forfeit this race? You stay in the room. Other racers can finish.");
            drawFooterText(menu, SUSAMUNE_GLYPH_A " Forfeit race   " SUSAMUNE_GLYPH_B " Keep racing", x + 4, y + 120);
            return;
        }
        if (mMode == PLAYLIST) {
            drawHelpLine(menu, x, y, w, 30, "Host chooses; each player advances independently.");
            const int rows = (h - 52) / ROW_H;
            const int first = listScrollStart(mCursor, 11, rows);
            const int end = first + rows < 11 ? first + rows : 11;
            for (int i = first; i < end; ++i) {
                char label[32], value[20];
                if (i == 0) { strcpy(label, "Current Stageloader queue"); snprintf(value, sizeof(value), "%d levels", StageLoader::queueCount()); }
                else if (i <= 3) { snprintf(label, sizeof(label), "%s", StageLoader::builtinPlaylistName(i - 1)); strcpy(value, "Use"); }
                else { snprintf(label, sizeof(label), "Saved playlist %d", i - 3); const int count = StageLoader::customPlaylistEntryCount(i - 4);
                    if (count > 0) snprintf(value, sizeof(value), "%d levels", count); else strcpy(value, "Empty"); }
                drawValueRow(menu, x, y + 34 + (i - first) * ROW_H, w, label, value, i == mCursor, false, true);
            }
            drawScrollHints(menu, x, y + 34, w, rows * ROW_H, first, end, 11);
            drawFooterText(menu, SUSAMUNE_GLYPH_A " Use playlist   " SUSAMUNE_GLYPH_B " Back", x + 4, y + h - FOOT_SZ);
            return;
        }
        if (mMode == SCORE) {
            LiveRace::Prefs prefs = LiveRace::prefs();
            prefs.scoreX = mStyle.x; prefs.scoreY = mStyle.y; prefs.scoreScale = mStyle.scale;
            LiveRace::drawScore(menu, prefs);
            mEditor.draw(menu, OnlineText::scoreTitle, OnlineText::scoreTitle);
            return;
        }
        if (mMode == ENTRY) { drawEntries(menu, x, y, w, h); return; }
        if (mMode == DRAFT_PICK) { drawDraft(menu, x, y, w, h); return; }

        const LiveRace::Status status = LiveRace::status();
        const LiveRace::Options &options = LiveRace::options();
        char text[128];
        char ping[20];
        if (status.pingMs == ~0u) snprintf(ping, sizeof(ping), "--");
        else snprintf(ping, sizeof(ping), OnlineText::pingFormat, status.pingMs);
        snprintf(text, sizeof(text), OnlineText::peerFormat,
            status.connection ? status.connection : OnlineText::offline,
            status.peerName[0] ? status.peerName : "--", ping);
        small(menu, mSection == HOME ? text : mSection == SETUP ? OnlineText::setupPage :
            mSection == OPPONENT ? OnlineText::opponentPage : OnlineText::connectionPage, x + 4, y, w - 8);
        normalize(status);
        const char *pageHelp = help(status);
        const char *next = pageHelp;
        if (mSection == HOME && status.connected && !status.freeRoam) {
            const char *race = status.race ? status.race : OnlineText::empty;
            if (LiveRace::groupState()) snprintf(text, sizeof(text), "%u / %u players | %s", LiveRace::playersConnected(), options.players, race);
            else if (options.draft) {
                const unsigned local = status.hosting ? 0 : 1;
                snprintf(text, sizeof(text), OnlineText::draftStatusFormat,
                    status.draft.setWins[local], status.draft.setWins[local ^ 1],
                    status.draft.roundWins[local], status.draft.roundWins[local ^ 1], race);
            } else snprintf(text, sizeof(text), OnlineText::sessionFormat, status.localWins, status.peerWins, race);
            next = text;
        } else if ((mSection == HOME || mSection == CONNECTION) && status.hint && status.hint[0] && !status.codeChanged)
            next = status.hint;
        else if (mSection == HOME && !status.active && (status.networkError || status.diagnostics.trouble) && status.race && status.race[0])
            next = status.race;
        small(menu, next, x + 4, y + 21, w - 8);
        const bool showFooterHelp = strcmp(next, pageHelp) != 0;
        const bool diagnosticsShown = mSection == CONNECTION && mDiagnostics;
        if (diagnosticsShown) {
        snprintf(text, sizeof(text), OnlineText::networkFormat,
            OnlineText::netState[status.diagnostics.net & 3], status.diagnostics.waitedS, status.localIp[0], status.localIp[1], status.localIp[2], status.localIp[3],
            status.localPort, status.networkError);
        small(menu, text, x + 4, y + 48, w - 8);
        const LiveRace::Diagnostics &diagnostics = status.diagnostics;
        const char *socketText = OnlineText::noDiagnostics;
        if (diagnostics.socketAvailable) {
            snprintf(text, sizeof(text), OnlineText::socketFormat, diagnostics.forwarded,
                diagnostics.socketSent, diagnostics.socketReceived, diagnostics.dropped,
                diagnostics.sendErrors, diagnostics.receiveErrors, diagnostics.socketError);
            socketText = text;
        }
        small(menu, socketText, x + 4, y + 62, w - 8);
        if (status.active || LiveStun::result().state == LiveStun::IDLE) {
            snprintf(text, sizeof(text), OnlineText::packetFormat,
                diagnostics.submitted, diagnostics.received, diagnostics.accepted);
        } else stunLine(text, sizeof(text));
        small(menu, text, x + 4, y + 76, w - 8);
        }

        const int top = diagnosticsShown ? 98 : 48;
        const int rows = (h - top - 34) / ROW_H;
        const int count = visibleCount(status);
        int selected = 0;
        while (selected < count && rowAt(selected, status) != mSel) ++selected;
        const int first = listScrollStart(selected, count, rows);
        const int end = first + rows < count ? first + rows : count;
        for (int local = first; local < end; ++local) {
            const int i = rowAt(local, status);
            const char *value = OnlineText::empty;
            switch (i) {
            case NAME_ROW: value = options.name; break;
            case CODE_ROW:
                value = status.code[0] ? status.code : status.active && !status.connected ? OnlineText::gettingAddress : OnlineText::none;
                break;
            case LOCAL_CODE_ROW: value = status.localCode[0] ? status.localCode : OnlineText::none; break;
            case FRIEND_ROW:
                value = status.friendCode[0] ? status.friendCode :
                    status.active && !status.connected ? OnlineText::enterFriend : OnlineText::none;
                break;
            case GUEST1_ROW: case GUEST2_ROW: case GUEST3_ROW:
                value = LiveRace::guestName(i - GUEST1_ROW);
                if (!value) value = LiveRace::guestCode(i - GUEST1_ROW, text) ? text : "Enter code";
                break;
            case NAT_ROW: value = status.active ? OnlineText::natAutomatic : stunVerdict(text, sizeof(text)); break;
            case ENTRY_ROW:
                if (options.playlist) { snprintf(text, sizeof(text), "%u levels", LiveRace::playlistCount()); value = text; }
                else value = ILing::shortLabel(options.entry);
                break;
            case EPISODE_ROW:
                if (!ILing::canChooseEpisode(options.entry)) value = "Fixed";
                else if (ILing::choosesPlazaState(options.entry)) value = ILing::plazaStateName(options.episode);
                else { snprintf(text, sizeof(text), "%u", options.episode + 1); value = text; }
                break;
            case BEST_ROW:
                snprintf(text, sizeof(text), "%u", options.bestOf);
                value = options.draft ? OnlineText::draftFixedBest : text; break;
            case MODE_ROW: value = options.playlist ? OnlineText::playlistMode : options.freeRoam ? OnlineText::freeRoam : options.draft ? OnlineText::draftMode : OnlineText::raceMode; break;
            case PLAYERS_ROW: snprintf(text, sizeof(text), "%u players", options.players < 2 ? 2 : options.players); value = text; break;
            case POOL_ROW: value = PackedText::at(OnlineText::draftPoolNames, options.pool < 3 ? options.pool : 0); break;
            case SET_LENGTH_ROW: value = PackedText::at(OnlineText::draftSetNames, options.setBo5 ? 1 : 0); break;
            case HOST_ROW: case JOIN_ROW: value = status.active ? "Unavailable" : "Start"; break;
            case READY_ROW: value = status.localReady ? OnlineText::readyCancel : status.peerReady ? OnlineText::readyPeer : OnlineText::readyStart; break;
            case SETUP_ROW: value = !status.connected ? OnlineText::connectFirst : !status.hosting ? OnlineText::hostOnly :
                                   status.setupEditable ? OnlineText::applySetup : OnlineText::finishFirst; break;
            case DRAFT_ROW: value = !options.draft ? OnlineText::draftOnly : status.draftPending ? OnlineText::draftPending :
                                   status.drafting ? (draftTurn(status) ? OnlineText::draftTurn : OnlineText::draftWait) : OnlineText::draftOpen; break;
            case DISCONNECT_ROW: value = status.active ? OnlineText::leave : OnlineText::offline; break;
            case INPUTS_ROW: value = LiveGhost::inputsShown() ? "On" : "Off"; break;
            case SHOW_ROW: value = LiveRace::prefs().hideOpponent ? "Off" : "On"; break;
            case MODEL_ROW: value = PackedText::at(OnlineText::modelNames, LiveRace::prefs().model); break;
            case SCORE_ROW: value = "Edit"; break;
            case SCORE_VISIBLE_ROW: value = LiveRace::prefs().hideScore ? "Off" : "On"; break;
            case RACE_PAGE_ROW: case OPPONENT_PAGE_ROW: case CONNECTION_PAGE_ROW: value = OnlineText::openPage; break;
            case DIAGNOSTICS_ROW: value = mDiagnostics ? "On" : "Off"; break;
            }
            const int ry = y + top + (local - first) * ROW_H;
            if (i == mSel) drawRowHighlight(menu, x, ry, w, ROW_H);
            const bool disabled =
                (status.active && (i == NAME_ROW || (i >= ENTRY_ROW && i <= SET_LENGTH_ROW && !status.setupEditable))) ||
                (i == NAT_ROW && status.active) || (i == SETUP_ROW && !status.setupEditable) ||
                ((i == CODE_ROW || i == FRIEND_ROW) && (!status.active || (status.connected && !status.hosting))) ||
                (options.draft && i >= ENTRY_ROW && i <= BEST_ROW) ||
                (!options.draft && (i == POOL_ROW || i == SET_LENGTH_ROW));
            menu->drawMenuText(rowName(i), x + 4, ry, ROW_SZ, ROW_SZ, disabled ? cRowDim() : cRow());
            int size = ROW_SZ;
            const int valueWidth = w - Menu::textWidth(rowName(i), ROW_SZ) - 24;
            while (size > 10 && Menu::textWidth(value, size) > valueWidth) --size;
            char fitted[80];
            if (Menu::textWidth(value, size) > valueWidth) {
                snprintf(fitted, sizeof(fitted), "%s", value);
                unsigned length = strlen(fitted);
                while (length > 3 && Menu::textWidth(fitted, size) > valueWidth) {
                    fitted[--length] = 0;
                    fitted[length - 1] = fitted[length - 2] = fitted[length - 3] = '.';
                }
                value = fitted;
            }
            menu->drawMenuText(value, x + w - Menu::textWidth(value, size) - 8,
                          ry, size, size, disabled ? cRowDim() : cValue());
        }
        drawScrollHints(menu, x, y + top, w, rows * ROW_H, first, end, count);
        if (showFooterHelp) small(menu, pageHelp, x + 4, y + h - 30, w - 8);
    }

private:
    enum Row { NAME_ROW, HOST_ROW, JOIN_ROW, CODE_ROW, FRIEND_ROW, ENTRY_ROW, EPISODE_ROW,
               BEST_ROW, MODE_ROW, POOL_ROW, SET_LENGTH_ROW, READY_ROW, SETUP_ROW, DRAFT_ROW, DISCONNECT_ROW,
               NAT_ROW, INPUTS_ROW, SHOW_ROW,
               MODEL_ROW, SCORE_ROW,
               DIAGNOSTICS_ROW, SCORE_VISIBLE_ROW, RACE_PAGE_ROW, OPPONENT_PAGE_ROW, CONNECTION_PAGE_ROW, PLAYERS_ROW, LOCAL_CODE_ROW,
               GUEST1_ROW, GUEST2_ROW, GUEST3_ROW, FORFEIT_ROW, ROW_COUNT };
    enum Mode { NONE, NAME, FRIEND, ENTRY, DRAFT_PICK, SCORE, PLAYLIST, FORFEIT, KICK };
    enum Section { HOME, SETUP, OPPONENT, CONNECTION };
    bool visible(int row, const LiveRace::Status &status) const {
        const LiveRace::Options &options = LiveRace::options();
        const bool groupHost = status.active && status.hosting;
        if (row >= GUEST1_ROW && row <= GUEST3_ROW)
            return groupHost && (mSection == HOME || mSection == CONNECTION) && row - GUEST1_ROW < options.players - 1;
        if (row == FRIEND_ROW && groupHost) return false;
        if (row == LOCAL_CODE_ROW) return (mSection == HOME || mSection == CONNECTION) &&
            status.localCode[0] && status.active && (!status.connected || (status.hosting && LiveRace::groupState()));
        if (row == FORFEIT_ROW) return mSection == HOME && status.canForfeit;
        if (mSection == HOME) {
            if (row >= RACE_PAGE_ROW && row <= CONNECTION_PAGE_ROW) return true;
            if (!status.active) return row == NAME_ROW || row == PLAYERS_ROW || row == HOST_ROW || row == JOIN_ROW;
            if (row == DISCONNECT_ROW) return true;
            if (groupHost && row == CODE_ROW) return true;
            if (!status.connected) return row == CODE_ROW || row == FRIEND_ROW;
            if (row == DRAFT_ROW) return options.draft && !status.freeRoam && !status.matchDone;
            return row == READY_ROW && !status.freeRoam && !status.matchDone && !status.drafting && !status.racing;
        }
        if (mSection == SETUP) {
            if (row == MODE_ROW) return true;
            if (row == SETUP_ROW) return status.connected;
            if (options.freeRoam) return false;
            if (options.playlist) return row == ENTRY_ROW;
            if (options.draft) return row == POOL_ROW || row == SET_LENGTH_ROW;
            return row == ENTRY_ROW || row == BEST_ROW || (row == EPISODE_ROW && ILing::canChooseEpisode(options.entry));
        }
        if (mSection == OPPONENT)
            return (row == INPUTS_ROW && options.players == 2) || row == SHOW_ROW || row == MODEL_ROW || row == SCORE_ROW || row == SCORE_VISIBLE_ROW;
        return row == NAT_ROW || row == DIAGNOSTICS_ROW || (status.active && (row == CODE_ROW || row == FRIEND_ROW));
    }
    int rowAt(int index, const LiveRace::Status &status) const {
        static const u8 order[] = {NAME_ROW, PLAYERS_ROW, HOST_ROW, JOIN_ROW, CODE_ROW, LOCAL_CODE_ROW, FRIEND_ROW,
            GUEST1_ROW, GUEST2_ROW, GUEST3_ROW, READY_ROW, DRAFT_ROW, FORFEIT_ROW,
            MODE_ROW, ENTRY_ROW, EPISODE_ROW, BEST_ROW, POOL_ROW, SET_LENGTH_ROW, SETUP_ROW,
            SHOW_ROW, MODEL_ROW, INPUTS_ROW, SCORE_VISIBLE_ROW, SCORE_ROW, NAT_ROW, DIAGNOSTICS_ROW,
            RACE_PAGE_ROW, OPPONENT_PAGE_ROW, CONNECTION_PAGE_ROW, DISCONNECT_ROW};
        for (unsigned i = 0; i < sizeof(order); ++i)
            if (visible(order[i], status) && index-- == 0) return order[i];
        return -1;
    }
    int visibleCount(const LiveRace::Status &status) const {
        int count = 0;
        for (int row = 0; row < ROW_COUNT; ++row) count += visible(row, status);
        return count;
    }
    bool normalize(const LiveRace::Status &status) {
        if (visible(mSel, status)) return false;
        mSel = rowAt(0, status);
        focus();
        return true;
    }
    void moveSelection(int delta, const LiveRace::Status &status) {
        int index = 0;
        const int count = visibleCount(status);
        while (index < count && rowAt(index, status) != mSel) ++index;
        mSel = rowAt(wrap(index + delta, count), status);
    }
    void openPage(u8 section, const LiveRace::Status &status) {
        mSection = section;
        mSel = rowAt(0, status);
        focus();
    }
    void openSearchRow(int row) {
        mMode = NONE;
        mSection = (row >= ENTRY_ROW && row <= SET_LENGTH_ROW) || row == SETUP_ROW || row == RACE_PAGE_ROW ? SETUP :
            (row >= INPUTS_ROW && row <= SCORE_ROW) || row == SCORE_VISIBLE_ROW || row == OPPONENT_PAGE_ROW ? OPPONENT :
            row == NAT_ROW || row == DIAGNOSTICS_ROW || row == CODE_ROW || row == FRIEND_ROW || row == CONNECTION_PAGE_ROW ||
            (row >= GUEST1_ROW && row <= GUEST3_ROW) ? CONNECTION : HOME;
        mSel = row < 0 ? NAME_ROW : row;
        normalize(LiveRace::status());
        focus();
    }
    const char *help(const LiveRace::Status &status) const {
        if (mSel >= GUEST1_ROW && mSel <= GUEST3_ROW)
            return "Enter each invited guest code. Select a connected guest to kick them.";
        if (mSel == LOCAL_CODE_ROW) return OnlineText::localCodeShare;
        if (mSection == OPPONENT) return OnlineText::displaySteps;
        if (mSection == CONNECTION) return OnlineText::connectionSteps;
        if (mSection == SETUP) return !status.active ? OnlineText::savedSetup : !status.hosting ? OnlineText::guestSetup :
            !status.setupEditable ? OnlineText::lockedSetup : OnlineText::applySteps;
        if (!status.active) return OnlineText::offlineSteps;
        if (!status.connected) return status.codeChanged ? OnlineText::codeChanged : OnlineText::codeSteps;
        if (status.matchDone) return status.hosting ? OnlineText::applySteps : OnlineText::guestSetup;
        if (status.freeRoam) return OnlineText::roamSteps;
        if (status.drafting) return draftTurn(status) ? OnlineText::draftTurn : OnlineText::draftWait;
        return OnlineText::roomHelp;
    }

    static const char *rowName(int row) {
        if (row == FORFEIT_ROW) return "Forfeit race";
        if (row >= GUEST1_ROW && row <= GUEST3_ROW) return PackedText::at("Guest 1 code\0Guest 2 code\0Guest 3 code", row - GUEST1_ROW);
        if (row == LOCAL_CODE_ROW) return "Same-network code";
        if (row == PLAYERS_ROW) return "Room size";
        if (row == ENTRY_ROW && LiveRace::options().playlist) return "Playlist";
        static const char names[] = "Name\0Create room\0Join room\0Your code\0Friend's code\0IL race\0Episode\0Best of\0Mode\0IL pool\0Set length\0Ready\0Apply next setup\0Draft IL list\0Disconnect\0NAT test\0Opponent inputs\0Show opponent"
            "\0Opponent model\0Edit score bar"
            "\0Packet details\0Show score bar\0Race setup\0Opponent display\0Connection help";
        return PackedText::at(names, row);
    }
    static bool draftTurn(const LiveRace::Status &status) {
        if (const auto *group = LiveRace::groupState()) return LiveGroupRules::actor(*group) == LiveRace::groupPlayer();
        return status.drafting && LiveDraft::currentActor(status.draft) == (status.hosting ? 0 : 1);
    }
    static bool draftPicking(const LiveDraft::State &draft) {
        return draft.phase == LiveDraft::OPENING_HOST_PICK || draft.phase == LiveDraft::COUNTER_LOSER_PICK;
    }
    static void draftScore(char *text, unsigned size, const LiveRace::Status &status, bool detail) {
        if (const auto *group = LiveRace::groupState()) {
            snprintf(text, size, "%u players | One ban each | BO3 ILs | BO%u set", group->config.players, group->config.setBestOf);
            return;
        }
        const unsigned local = status.hosting ? 0 : 1;
        const unsigned bestOf = status.draft.bestOf == 3 || status.draft.bestOf == 5 ?
            status.draft.bestOf : LiveRace::options().setBo5 ? 5 : 3;
        snprintf(text, size, detail ? OnlineText::draftScoreFormat : OnlineText::draftSummaryFormat,
            status.draft.setWins[local], status.draft.setWins[local ^ 1], bestOf,
            status.draft.roundWins[local], status.draft.roundWins[local ^ 1]);
    }
    void drawDraft(Menu *menu, int x, int y, int w, int h) {
        menu->fillMenuBox(0, 0, 640, 480, cBackdrop());
        menu->fillMenuBox(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, cPanel());
        menu->fillMenuBox(PANEL_X, PANEL_Y, PANEL_W, 3, cAccent());
        x = PANEL_X + PAD; y = PANEL_Y + PAD;
        w = PANEL_W - PAD * 2; h = PANEL_H - PAD * 2;
        const LiveRace::Status status = LiveRace::status();
        char text[112];
        menu->drawMenuText(OnlineText::draftTitle, x + 4, y, 22, 22, cTitle());
        draftScore(text, sizeof(text), status, true);
        fit(menu, text, x + 4, y + 30, w - 8, 17, 12, cValue());
        const bool turn = draftTurn(status);
        const auto *group = LiveRace::groupState();
        if (group && (group->phase == LiveGroupRules::NeedCandidates || group->phase == LiveGroupRules::Lobby)) {
            snprintf(text, sizeof(text), "Waiting for players: %u / %u", LiveRace::playersConnected(), group->config.players);
            fit(menu, text, x + 4, y + 84, w - 8, 22, 16, cValue());
            small(menu, "The IL draft appears once everyone has connected.", x + 4, y + 124, w - 8);
            small(menu, "B: return to the room and enter guest codes", x + 4, y + 156, w - 8);
            drawFooterText(menu, OnlineText::draftBackHelp, x + 4, y + h - 16);
            return;
        }
        const bool picking = !group && draftPicking(status.draft);
        const char *action = status.draftPending ? OnlineText::draftPending : !status.drafting ?
            (status.race ? status.race : OnlineText::noRace) :
            turn ? (picking ? OnlineText::draftPick : OnlineText::draftBan) :
                   (picking ? OnlineText::draftPeerPick : OnlineText::draftPeerBan);
        fit(menu, action, x + 4, y + 58, w - 8, 18, 12, turn ? cValue() : cRow());
        if (status.drafting && status.race) small(menu, status.race, x + 4, y + 82, w - 8);
        for (unsigned i = 0; i < (group ? group->config.players + 1u : LiveDraft::CANDIDATE_COUNT); ++i) {
            const unsigned entry = group ? group->candidates[i] : status.draft.candidates[i];
            const bool banned = ((group ? group->bannedMask : status.draft.bannedMask) & (1u << i)) != 0;
            const bool chosen = group ? group->phase == LiveGroupRules::Ready && group->selected == entry : status.draft.selected != LiveDraft::NO_ENTRY && status.draft.selected == entry;
            const int ry = y + 108 + i * 30;
            if (i == mCursor) drawRowHighlight(menu, x, ry, w, 28);
            const char *label = entry < (unsigned)ILing::count() ? ILing::label(entry) : OnlineText::empty;
            fit(menu, label, x + 8, ry + 3, w - 115, 17, 11, banned ? cRowDim() : cRow());
            const char *mark = banned ? OnlineText::draftBanned : chosen ? OnlineText::draftChosen : OnlineText::draftAvailable;
            menu->drawMenuText(mark, x + w - Menu::textWidth(mark, 12) - 8, ry + 6, 12, 12,
                           banned ? cRowDim() : chosen ? cValue() : cRow());
        }
        small(menu, status.draft.phase == LiveDraft::IL_MATCH ? OnlineText::draftSelectedHelp :
                    OnlineText::draftWaitingHelp, x + 4, y + h - 34, w - 8);
        drawFooterText(menu, turn && !status.draftPending ?
            (picking ? OnlineText::draftPickHelp : OnlineText::draftBanHelp) : OnlineText::draftBackHelp,
            x + 4, y + h - 16);
    }
    static void stunLine(char *text, unsigned size) {
        const LiveStun::Result &stun = LiveStun::result();
        char mapped[LiveStun::SERVER_COUNT][24];
        for (unsigned i = 0; i < LiveStun::SERVER_COUNT; ++i) {
            const TWLiveEndpoint &at = stun.mapped[i];
            if (stun.answered >> i & 1u)
                snprintf(mapped[i], sizeof(mapped[i]), OnlineText::endpointFormat, at.ip[0], at.ip[1], at.ip[2], at.ip[3], at.port);
            else snprintf(mapped[i], sizeof(mapped[i]), OnlineText::none);
        }
        char failed[24];
        snprintf(text, size, OnlineText::stunFormat, stunVerdict(failed, sizeof(failed)), stun.attempts, mapped[0], mapped[1]);
    }
    // `scratch` holds the failure text when the probe could not run.
    static const char *stunVerdict(char *scratch, unsigned size) {
        const LiveStun::Result &stun = LiveStun::result();
        snprintf(scratch, size, OnlineText::stunFailed, stun.error);
        return stun.state == LiveStun::IDLE ? OnlineText::natIdle :
            stun.state == LiveStun::RUNNING ? OnlineText::stunRunning :
            stun.state == LiveStun::FAILED ? scratch :
            stun.verdict == LiveStun::SAME_MAPPING ? OnlineText::stunSame :
            stun.verdict == LiveStun::DIFFERENT_MAPPING ? OnlineText::stunDifferent :
            stun.verdict == LiveStun::ONE_REPLY ? OnlineText::stunOne : OnlineText::stunNone;
    }
    // Draws text at the largest size from `size` down to `least` that fits `width`.
    static void fit(Menu *menu, const char *text, int x, int y, int width, int size, int least, Color color) {
        while (size > least && Menu::textWidth(text, size) > width) --size;
        menu->drawMenuText(text, x, y, size, size, color);
    }
    static void small(Menu *menu, const char *text, int x, int y, int width) {
        fit(menu, text, x, y, width, FOOT_SZ, 9, cRow());
    }
    bool apply(Menu *menu) {
        if (!LiveRace::status().setupEditable) {
            menu->toast(OnlineText::disconnectFirst);
            return false;
        }
        if (!mDraft.name[0]) { menu->toast(OnlineText::needName); return false; }
        for (unsigned i = 0; i < sizeof(mDraft.name) - 1 && mDraft.name[i]; ++i) {
            const u8 ch = mDraft.name[i];
            if (ch < 32 || ch > 126) { menu->toast(OnlineText::printableName); return false; }
        }
        if (LiveRace::configure(mDraft)) return true;
        menu->toast(OnlineText::invalidSetup);
        return false;
    }
    bool enterCode(Menu *menu) {
        const char *error = mSel >= GUEST1_ROW && mSel <= GUEST3_ROW ?
            LiveRace::enterGuestCode(mSel - GUEST1_ROW, mCode) : LiveRace::enterCode(mCode);
        if (error) menu->toast(error);
        return !error;
    }
    void beginEdit(u8 mode) {
        mMode = mode;
        mCursor = mPage = 0;
        mUpper = false;
        mLength = mode == NAME ? strlen(mDraft.name) : 0;
        mInput.begin(JUTGamePad::A | JUTGamePad::B | JUTGamePad::X | JUTGamePad::Y |
            JUTGamePad::Z | JUTGamePad::START | JUTGamePad::L | JUTGamePad::R |
            JUTGamePad::DPAD_LEFT | JUTGamePad::DPAD_RIGHT | JUTGamePad::DPAD_UP | JUTGamePad::DPAD_DOWN);
    }
    void drawCode(Menu *menu) {
        menu->fillMenuBox(0, 0, 640, 480, cBackdrop());
        MenuTheme::panel(menu, PANEL_X, PANEL_Y, PANEL_W, PANEL_H,
                         mSel >= GUEST1_ROW && mSel <= GUEST3_ROW ? rowName(mSel) : OnlineText::codePrompt, MenuThemeAssets::Boat);
        const int x = PANEL_X + PAD, y = PANEL_Y + PAD + 10;
        char shown[LiveP2P::DISPLAY_CHARS + 1];
        LiveP2P::format(mCode, shown);
        menu->drawMenuText(shown[0] ? shown : "-", x + 4, y + 40, 26, 26, cValue());
        for (unsigned i = 0; i < 32; ++i) {
            const int cx = x + 56 + (i & 7) * 56, cy = y + 104 + (i >> 3) * 50;
            if (i == mCursor) MenuTheme::selection(menu, cx - 10, cy - 6, 44, 40);
            const char glyph[2] = {LiveP2P::symbol(i), 0};
            menu->drawMenuText(glyph, cx, cy, 26, 26, cRow());
        }
        drawFooterText(menu, OnlineText::codeHelp, x + 4, PANEL_Y + PANEL_H - PAD - 30);
        drawFooterText(menu, OnlineText::codeBack, x + 4, PANEL_Y + PANEL_H - PAD - 14);
    }
    void drawEntries(Menu *menu, int x, int y, int w, int h) {
        const int position = ILing::menuPositionOf(mDraft.entry);
        const int entries = ILing::count();
        const int listH = h - ROW_H;
        const int maxRows = listH / ROW_H;
        int rows = entries;
        int selectedRow = position;
        for (int i = 0; i < entries; ++i) {
            if (!ILing::beginsMenuGroup(i)) continue;
            rows++;
            if (i <= position) selectedRow++;
        }
        const int start = listScrollStart(selectedRow, rows, maxRows);
        int end = start + maxRows;
        if (end > rows) end = rows;
        int row = 0;
        int ry = y;
        for (int i = 0; i < entries && row < end; ++i) {
            if (ILing::beginsMenuGroup(i)) {
                if (row >= start) {
                    drawSectionHeader(menu, x, ry, w, ILing::menuGroupName(i));
                    ry += ROW_H;
                }
                row++;
                if (row >= end) break;
            }
            if (row >= start) {
                drawValueRow(menu, x, ry, w, ILing::label(ILing::menuEntryAt(i)),
                             nullptr, i == position, false, true);
                ry += ROW_H;
            }
            row++;
        }
        drawScrollHints(menu, x, y, w, listH, start, end, rows);
        drawFooterText(menu, OnlineText::chooseHelp, x + 4, y + h - FOOT_SZ);
    }
    LiveRace::Options mDraft;
    LiveRace::Prefs mPrefs;
    CreationEditor mEditor;
    CreationStyle mStyle;
    u8 mRgb[1][3], mRgbBackup[1][3];
    RawPromptInput mInput;
    char mCode[LiveP2P::DISPLAY_CHARS + 1];
    u8 mSel, mMode, mCursor, mLength, mPage;
    bool mUpper, mDiagnostics;
    u8 mSection;
};
}
bool Menu::openOnline() {
    if (!mNumTabs || (mShown && searchActive())) return false;
    if (mShown && mCurTab == mNumTabs - 1 &&
        static_cast<OnlineTab *>(mTabs[mCurTab])->mMode == OnlineTab::DRAFT_PICK) return true;
    if (mShown && mTabs[mCurTab]->grabsInput()) return false;
    mCurTab = mNumTabs - 1;
    mTabFirst = 0;
    mCRepeatFrames = 0;
    static_cast<OnlineTab *>(mTabs[mCurTab])->openAfterRound();
    mShown = true;
    return true;
}
#pragma clang section text=".foxtrot.text"
