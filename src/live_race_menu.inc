#pragma clang section text=""
namespace {
// Named arrays keep new text out of the fixed menu literal pools.
namespace OnlineText {
static const char chooseHelp[] = SUSAMUNE_GLYPH_A " Select   " SUSAMUNE_GLYPH_C " L" SUSAMUNE_GLYPH_SLASH "R World   " SUSAMUNE_GLYPH_B " Cancel";
static const char keepCancel[] = SUSAMUNE_GLYPH_A " Keep    " SUSAMUNE_GLYPH_B " Cancel";
static const char title[] = "Online";
static const char disconnectFirst[] = "Disconnect before changing setup";
static const char fixedStart[] = "This IL has a fixed start";
static const char unavailableAction[] = "Online action unavailable; check connection status";
static const char finishedAction[] = "Match finished - host can apply the next setup";
static const char matchFinished[] = "Match finished";
static const char finishedHelp[] = "Host: choose the next IL or mode, then Apply next setup.";
static const char freeRoam[] = "Free roam";
static const char raceMode[] = "IL racing";
static const char draftMode[] = "Draft set";
static const char draftOnly[] = "Draft sets only";
static const char manualOnly[] = "Choose ILs through the draft list";
static const char draftPoolNames[] = "Any%\0All ILs\0Non-Any%";
static const char draftSetNames[] = "Best of 3\0Best of 5";
static const char draftOpen[] = "Open IL list";
static const char draftTurn[] = "Your turn";
static const char draftWait[] = "Opponent's turn";
static const char draftPending[] = "Sending selection...";
static const char draftNoList[] = "Connect in Draft set mode to see the IL list";
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
static const char draftSelectedHelp[] = "IL chosen. Return to Online; both players choose Ready.";
static const char draftWaitingHelp[] = "You can leave this list while your opponent chooses.";
static const char draftScoreFormat[] = "Set: %u - %u  (Bo%u)   |   IL rounds: %u - %u  (Bo3)";
static const char draftSummaryFormat[] = "Set: %u - %u  (Bo%u)   |   Rounds: %u - %u";
static const char draftFixedBest[] = "3 per IL";
static const char freeRoamAction[] = "Free roam - host can choose IL racing";
static const char hostOnly[] = "Host only";
static const char applySetup[] = "Apply";
static const char finishFirst[] = "Finish the match first";
static const char setupAvailable[] = "Host can edit race setup";
static const char namePrompt[] = "Online name (16 characters)";
static const char pingFormat[] = "%lu ms";
static const char peerFormat[] = "%s  |  Peer: %.16s  |  %s";
static const char offline[] = "Offline";
static const char networkFormat[] = "Local IP: %u.%u.%u.%u:%u  |  Error: %ld";
static const char socketFormat[] = "Socket TX %u RX %u Drop %u Err S/R %u/%u Code %ld";
static const char noDiagnostics[] = "Socket diagnostics unavailable";
static const char packetFormat[] = "PPC TX %lu RX %lu Relay OK %lu";
static const char scoreFormat[] = "Score: %u - %u   |   IL Best of %u";
static const char noRace[] = "No race";
static const char readyFormat[] = "You: %s  |  Peer: %s  |  %s";
static const char notReady[] = "Not ready";
static const char locked[] = "Setup locked";
static const char prototype[] = "Two-player online prototype";
static const char empty[] = "";
static const char ipFormat[] = "%u.%u.%u.%u";
static const char roomFormat[] = "%06lu";
static const char armRace[] = "Arm race";
static const char connectFirst[] = "Connect first";
static const char leave[] = "Leave session";
static const char hostHelp[] = "Use the same relay server. Create a room, then share its code.";
static const char roomHelp[] = "Join with the room code. Both choose Ready to start the IL.";
static const char needName[] = "Enter an online name first";
static const char printableName[] = "Use printable letters, numbers or symbols";
static const char invalidSetup[] = "Online setup is invalid or busy";
static const char ipEditorFormat[] = "%03u%03u%03u%03u";
static const char portEditorFormat[] = "%05u";
static const char invalidIp[] = "Each IP segment must be 0 to 255";
static const char invalidPort[] = "UDP port must be 1 to 65535";
static const char dot[] = ".";
static const char digitHelp[] = "D-pad Left/Right: digit    Up/Down: value";
static const char stunBusy[] = "Disconnect before the NAT test";
static const char stunFormat[] = "STUN %s  A %s  B %s";
static const char stunRunning[] = "probing...";
static const char stunSame[] = "SAME - punching should work";
static const char stunDifferent[] = "DIFFERENT - symmetric NAT";
static const char stunOne[] = "one reply - retry X";
static const char stunNone[] = "no reply - retry X";
static const char stunFailed[] = "failed";
static const char endpointFormat[] = "%u.%u.%u.%u:%u";
static const char none[] = "--";
}

class OnlineTab final : public MenuTab {
    friend class ::Menu;
public:
    OnlineTab() : mSel(0), mMode(NONE), mCursor(0), mLength(0), mPage(0),
                  mUpper(false), mDiagnostics(false) { focus(); }
    const char *title() const override { return OnlineText::title; }
    bool grabsInput() const override { return mMode != NONE; }
    bool suppressesBinds() const override { return true; }
    bool fullScreen() const override { return mMode == NAME || numeric() || mMode == DRAFT_PICK; }
    void focus() override { mInput.begin(JUTGamePad::A | JUTGamePad::B | JUTGamePad::X | JUTGamePad::Y); }
    bool back() override {
        if (mMode == NONE) return false;
        mMode = NONE;
        focus();
        return true;
    }

    void update(Menu *menu, TMarioGamePad *pad) override {
        const u16 pressed = mInput.update();
        const LiveRace::Status status = LiveRace::status();
        if (mMode == DRAFT_PICK) {
            if (pressed & JUTGamePad::B) { back(); return; }
            if (!status.active || !LiveRace::options().draft) { back(); return; }
            const u32 nav = menu->navigationInput(pad);
            if (nav & TMarioGamePad::CSTICK_UP) mCursor = wrap(mCursor - 1, LiveDraft::CANDIDATE_COUNT);
            else if (nav & TMarioGamePad::CSTICK_DOWN) mCursor = wrap(mCursor + 1, LiveDraft::CANDIDATE_COUNT);
            if (!(pressed & JUTGamePad::A)) return;
            if (!draftTurn(status) || status.draftPending ||
                status.draft.candidates[mCursor] >= (unsigned)ILing::count() ||
                (status.draft.bannedMask & (1u << mCursor))) {
                menu->toast(status.race); return;
            }
            if (!LiveRace::chooseDraft(mCursor)) menu->toast(LiveRace::status().race);
            return;
        }
        if (mMode != NONE) {
            // A connection may become active while an editor is open.
            if (status.active && (!status.setupEditable || mSel < ENTRY_ROW)) { back(); return; }
            if (mMode == NAME) {
                if (pressed & JUTGamePad::START) {
                    if (JUTGamePad::mPadStatus[0].mButton & JUTGamePad::X) back();
                    else if (apply(menu)) back();
                } else if (pressed & JUTGamePad::Z) {
                    mLength = 0; mDraft.name[0] = 0;
                } else {
                    updateCreationKeyboardButtons(pressed, mDraft.name, mLength,
                        sizeof(mDraft.name) - 1, mPage, mUpper, mCursor);
                }
                return;
            }
            if (pressed & JUTGamePad::B) { back(); return; }
            if (numeric()) {
                if (pressed & (JUTGamePad::A | JUTGamePad::START)) {
                    if (readNumber(menu) && apply(menu)) back();
                    return;
                }
                if (pressed & JUTGamePad::DPAD_LEFT) mCursor = wrap(mCursor - 1, mLength);
                if (pressed & JUTGamePad::DPAD_RIGHT) mCursor = wrap(mCursor + 1, mLength);
                const int delta = (pressed & JUTGamePad::DPAD_UP) ? 1 :
                                  (pressed & JUTGamePad::DPAD_DOWN) ? -1 : 0;
                if (delta) mDigits[mCursor] = '0' + wrap(mDigits[mCursor] - '0' + delta, 10);
                return;
            }
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

        if (pressed & JUTGamePad::X) {
            // Phase-0 NAT probe on the race's own local port.
#if IS_EMULATOR
            const u16 localPort = 0;
#else
            const u16 localPort = LiveRace::options().port;
#endif
            if (status.active || !LiveStun::start(localPort)) menu->toast(OnlineText::stunBusy);
            else mDiagnostics = true;
            return;
        }
        const u32 nav = menu->navigationInput(pad);
        if (nav & TMarioGamePad::CSTICK_UP) mSel = wrap(mSel - 1, ROW_COUNT);
        else if (nav & TMarioGamePad::CSTICK_DOWN) mSel = wrap(mSel + 1, ROW_COUNT);
        const int direction = (nav & TMarioGamePad::CSTICK_LEFT) ? -1 :
                              (nav & TMarioGamePad::CSTICK_RIGHT) ? 1 : 0;
        if (!(pressed & JUTGamePad::A) && !direction) return;
        if (mSel == DIAGNOSTICS_ROW) { mDiagnostics = !mDiagnostics; return; }
        if (mSel == INPUTS_ROW) { LiveGhost::setInputsShown(!LiveGhost::inputsShown()); return; }
        if (mSel <= SET_LENGTH_ROW) {
            if (status.active && (!status.setupEditable || mSel < ENTRY_ROW)) {
                menu->toast(mSel < ENTRY_ROW ? OnlineText::disconnectFirst : OnlineText::finishFirst); return;
            }
            mDraft = LiveRace::options();
            if (mDraft.draft && mSel >= ENTRY_ROW && mSel <= BEST_ROW) {
                menu->toast(OnlineText::manualOnly); return;
            }
            if (!mDraft.draft && (mSel == POOL_ROW || mSel == SET_LENGTH_ROW)) {
                menu->toast(OnlineText::draftOnly); return;
            }
            if (mSel == EPISODE_ROW || mSel == BEST_ROW || mSel >= MODE_ROW) {
                if (mSel == MODE_ROW) {
                    const int mode = wrap((mDraft.freeRoam ? 2 : mDraft.draft ? 1 : 0) + (direction ? direction : 1), 3);
                    mDraft.freeRoam = mode == 2;
                    mDraft.draft = mode == 1;
                    if (mDraft.draft) mDraft.bestOf = 3;
                } else if (mSel == POOL_ROW) mDraft.pool = wrap(mDraft.pool + (direction ? direction : 1), 3);
                else if (mSel == SET_LENGTH_ROW) mDraft.setBo5 = !mDraft.setBo5;
                else if (mSel == BEST_ROW) mDraft.bestOf = 1 + 2 * wrap((mDraft.bestOf - 1) / 2 + (direction ? direction : 1), 4);
                else if (ILing::canChooseEpisode(mDraft.entry))
                    mDraft.episode = wrap(mDraft.episode + (direction ? direction : 1), 8);
                else { menu->toast(OnlineText::fixedStart); return; }
                apply(menu);
            } else if (pressed & JUTGamePad::A) beginEdit();
            return;
        }
        if (!(pressed & JUTGamePad::A)) return;
        bool accepted = false;
        if (mSel == DRAFT_ROW) {
            if (!status.active || !LiveRace::options().draft || status.draft.phase == LiveDraft::UNINITIALIZED) {
                menu->toast(OnlineText::draftNoList); return;
            }
            mMode = DRAFT_PICK;
            mCursor = 0;
            focus();
            return;
        }
        if (mSel == DISCONNECT_ROW) { LiveRace::disconnect(); return; }
        if (mSel == HOST_ROW && !status.active) accepted = LiveRace::host();
        if (mSel == JOIN_ROW && !status.active) accepted = LiveRace::join();
        if (mSel == READY_ROW && status.matchDone) { menu->toast(OnlineText::finishedAction); return; }
        if (mSel == READY_ROW && status.freeRoam) { menu->toast(OnlineText::freeRoamAction); return; }
        if (mSel == READY_ROW && status.connected) {
            if (!LiveRace::ready()) menu->toast(LiveRace::status().race);
            return;
        }
        if (mSel == SETUP_ROW && status.connected) {
            if (!status.hosting) { menu->toast(OnlineText::hostOnly); return; }
            if (!LiveRace::newMatch()) menu->toast(OnlineText::finishFirst);
            return;
        }
        if (!accepted) menu->toast(OnlineText::unavailableAction);
    }

    void draw(Menu *menu, int x, int y, int w, int h) override {
        if (mMode == NAME) {
            drawCreationKeyboard(menu, OnlineText::namePrompt, mDraft.name,
                                 mPage, mUpper, mCursor);
            return;
        }
        if (numeric()) { drawNumber(menu); return; }
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
        small(menu, text, x + 4, y, w - 8);
        if (options.draft) draftScore(text, sizeof(text), status, false);
        else snprintf(text, sizeof(text), OnlineText::scoreFormat,
                 status.localWins, status.peerWins, options.bestOf);
        int scoreSize = 18;
        while (scoreSize > 13 && Menu::textWidth(text, scoreSize) > w - 8) --scoreSize;
        menu->drawMenuText(status.freeRoam ? OnlineText::freeRoam : text,
                       x + 4, y + 18, scoreSize, scoreSize, cValue());
        const char *result = status.race ? status.race : OnlineText::noRace;
        int resultSize = 16;
        while (resultSize > 11 && Menu::textWidth(result, resultSize) > w - 8) --resultSize;
        menu->drawMenuText(result, x + 4, y + 42, resultSize, resultSize, cRow());
        snprintf(text, sizeof(text), OnlineText::readyFormat,
            status.localReady ? "Ready" : OnlineText::notReady, status.peerReady ? "Ready" : OnlineText::notReady,
            status.setupEditable && status.active ? OnlineText::setupAvailable : status.active ? OnlineText::locked : OnlineText::prototype);
        small(menu, text, x + 4, y + 64, w - 8);
        const bool diagnosticsShown = mDiagnostics || status.networkError != 0;
        if (diagnosticsShown) {
        snprintf(text, sizeof(text), OnlineText::networkFormat,
            status.localIp[0], status.localIp[1], status.localIp[2], status.localIp[3],
            status.localPort, status.networkError);
        small(menu, text, x + 4, y + 82, w - 8);
        const LiveRace::Diagnostics &diagnostics = status.diagnostics;
        const char *socketText = OnlineText::noDiagnostics;
        if (diagnostics.socketAvailable) {
            snprintf(text, sizeof(text), OnlineText::socketFormat,
                diagnostics.socketSent, diagnostics.socketReceived, diagnostics.dropped,
                diagnostics.sendErrors, diagnostics.receiveErrors, diagnostics.socketError);
            socketText = text;
        }
        small(menu, socketText, x + 4, y + 96, w - 8);
        if (LiveStun::result().state == LiveStun::IDLE) {
            snprintf(text, sizeof(text), OnlineText::packetFormat,
                diagnostics.submitted, diagnostics.received, diagnostics.accepted);
        } else stunLine(text, sizeof(text));
        small(menu, text, x + 4, y + 110, w - 8);
        }

        const int top = diagnosticsShown ? 130 : 88;
        const int rows = (h - top - 34) / ROW_H;
        const int first = listScrollStart(mSel, ROW_COUNT, rows);
        for (int i = first; i < ROW_COUNT && i < first + rows; ++i) {
            const char *value = OnlineText::empty;
            switch (i) {
            case NAME_ROW: value = options.name; break;
            case IP_ROW:
                snprintf(text, sizeof(text), OnlineText::ipFormat, options.serverIp[0], options.serverIp[1], options.serverIp[2], options.serverIp[3]);
                value = text; break;
            case PORT_ROW: snprintf(text, sizeof(text), "%u", options.port); value = text; break;
            case ROOM_ROW:
                if (status.roomCode) { snprintf(text, sizeof(text), OnlineText::roomFormat, status.roomCode); value = text; }
                else value = "--";
                break;
            case ENTRY_ROW: value = ILing::shortLabel(options.entry); break;
            case EPISODE_ROW:
                if (!ILing::canChooseEpisode(options.entry)) value = "Fixed";
                else if (ILing::choosesPlazaState(options.entry)) value = ILing::plazaStateName(options.episode);
                else { snprintf(text, sizeof(text), "%u", options.episode + 1); value = text; }
                break;
            case BEST_ROW:
                snprintf(text, sizeof(text), "%u", options.bestOf);
                value = options.draft ? OnlineText::draftFixedBest : text; break;
            case MODE_ROW: value = options.freeRoam ? OnlineText::freeRoam : options.draft ? OnlineText::draftMode : OnlineText::raceMode; break;
            case POOL_ROW: value = PackedText::at(OnlineText::draftPoolNames, options.pool < 3 ? options.pool : 0); break;
            case SET_LENGTH_ROW: value = PackedText::at(OnlineText::draftSetNames, options.setBo5 ? 1 : 0); break;
            case HOST_ROW: case JOIN_ROW: value = status.active ? "Unavailable" : "Start"; break;
            case READY_ROW: value = status.freeRoam ? OnlineText::freeRoam : status.matchDone ? OnlineText::matchFinished : status.localReady ? "Ready" :
                                   status.connected ? OnlineText::armRace : OnlineText::connectFirst; break;
            case SETUP_ROW: value = !status.connected ? OnlineText::connectFirst : !status.hosting ? OnlineText::hostOnly :
                                   status.setupEditable ? OnlineText::applySetup : OnlineText::finishFirst; break;
            case DRAFT_ROW: value = !options.draft ? OnlineText::draftOnly : status.draftPending ? OnlineText::draftPending :
                                   status.drafting ? (draftTurn(status) ? OnlineText::draftTurn : OnlineText::draftWait) : OnlineText::draftOpen; break;
            case DISCONNECT_ROW: value = status.active ? OnlineText::leave : OnlineText::offline; break;
            case INPUTS_ROW: value = LiveGhost::inputsShown() ? "On" : "Off"; break;
            case DIAGNOSTICS_ROW: value = mDiagnostics ? "On" : "Off"; break;
            }
            const int ry = y + top + (i - first) * ROW_H;
            if (i == mSel) drawRowHighlight(menu, x, ry, w, ROW_H);
            const bool disabled =
                (status.active && i <= SET_LENGTH_ROW && (!status.setupEditable || i < ENTRY_ROW)) ||
                (options.draft && i >= ENTRY_ROW && i <= BEST_ROW) ||
                (!options.draft && (i == POOL_ROW || i == SET_LENGTH_ROW));
            menu->drawMenuText(rowName(i), x + 4, ry, ROW_SZ, ROW_SZ, disabled ? cRowDim() : cRow());
            int size = ROW_SZ;
            while (size > 10 && Menu::textWidth(value, size) > w - 172) --size;
            menu->drawMenuText(value, x + w - Menu::textWidth(value, size) - 8,
                          ry, size, size, disabled ? cRowDim() : cValue());
        }
        small(menu, OnlineText::hostHelp, x + 4, y + h - 30, w - 8);
        small(menu, status.drafting ? OnlineText::draftWaitingHelp : status.matchDone || status.freeRoam ? OnlineText::finishedHelp : OnlineText::roomHelp,
              x + 4, y + h - 15, w - 8);
    }

private:
    enum Row { NAME_ROW, IP_ROW, PORT_ROW, ROOM_ROW, ENTRY_ROW, EPISODE_ROW,
               BEST_ROW, MODE_ROW, POOL_ROW, SET_LENGTH_ROW, HOST_ROW, JOIN_ROW, READY_ROW, SETUP_ROW, DRAFT_ROW, DISCONNECT_ROW,
               INPUTS_ROW, DIAGNOSTICS_ROW, ROW_COUNT };
    enum Mode { NONE, NAME, IP, PORT, ROOM, ENTRY, DRAFT_PICK };
    static const char *rowName(int row) {
        static const char names[] = "Name\0Server IP\0Server port\0Room code\0IL race\0Episode\0Best of\0Mode\0IL pool\0Set length\0Create room\0Join room\0Ready\0Apply next setup\0Draft IL list\0Disconnect\0Opponent inputs\0Diagnostics";
        return PackedText::at(names, row);
    }
    static bool draftTurn(const LiveRace::Status &status) {
        return status.drafting && LiveDraft::currentActor(status.draft) == (status.hosting ? 0 : 1);
    }
    static bool draftPicking(const LiveDraft::State &draft) {
        return draft.phase == LiveDraft::OPENING_HOST_PICK || draft.phase == LiveDraft::COUNTER_LOSER_PICK;
    }
    static void draftScore(char *text, unsigned size, const LiveRace::Status &status, bool detail) {
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
        int size = 17;
        while (size > 12 && Menu::textWidth(text, size) > w - 8) --size;
        menu->drawMenuText(text, x + 4, y + 30, size, size, cValue());
        const bool turn = draftTurn(status);
        const bool picking = draftPicking(status.draft);
        const char *action = status.draftPending ? OnlineText::draftPending : !status.drafting ?
            (status.race ? status.race : OnlineText::noRace) :
            turn ? (picking ? OnlineText::draftPick : OnlineText::draftBan) :
                   (picking ? OnlineText::draftPeerPick : OnlineText::draftPeerBan);
        size = 18;
        while (size > 12 && Menu::textWidth(action, size) > w - 8) --size;
        menu->drawMenuText(action, x + 4, y + 58, size, size, turn ? cValue() : cRow());
        if (status.drafting && status.race) small(menu, status.race, x + 4, y + 82, w - 8);
        for (unsigned i = 0; i < LiveDraft::CANDIDATE_COUNT; ++i) {
            const unsigned entry = status.draft.candidates[i];
            const bool banned = (status.draft.bannedMask & (1u << i)) != 0;
            const bool chosen = status.draft.selected != LiveDraft::NO_ENTRY && status.draft.selected == entry;
            const int ry = y + 108 + i * 30;
            if (i == mCursor) drawRowHighlight(menu, x, ry, w, 28);
            const char *label = entry < (unsigned)ILing::count() ? ILing::label(entry) : OnlineText::empty;
            size = 17;
            while (size > 11 && Menu::textWidth(label, size) > w - 115) --size;
            menu->drawMenuText(label, x + 8, ry + 3, size, size, banned ? cRowDim() : cRow());
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
        const char *verdict = stun.state == LiveStun::RUNNING ? OnlineText::stunRunning :
            stun.state == LiveStun::FAILED ? OnlineText::stunFailed :
            stun.verdict == LiveStun::SAME_MAPPING ? OnlineText::stunSame :
            stun.verdict == LiveStun::DIFFERENT_MAPPING ? OnlineText::stunDifferent :
            stun.verdict == LiveStun::ONE_REPLY ? OnlineText::stunOne : OnlineText::stunNone;
        snprintf(text, size, OnlineText::stunFormat, verdict, mapped[0], mapped[1]);
    }
    static void small(Menu *menu, const char *text, int x, int y, int width) {
        int size = FOOT_SZ;
        while (size > 9 && Menu::textWidth(text, size) > width) --size;
        menu->drawMenuText(text, x, y, size, size, cRow());
    }
    bool numeric() const { return mMode >= IP && mMode <= ROOM; }
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
    void beginEdit() {
        mMode = mSel + NAME;
        mCursor = mPage = 0;
        mUpper = false;
        if (mMode == NAME) mLength = strlen(mDraft.name);
        else if (mMode == IP) {
            snprintf(mDigits, sizeof(mDigits), OnlineText::ipEditorFormat, mDraft.serverIp[0], mDraft.serverIp[1], mDraft.serverIp[2], mDraft.serverIp[3]);
            mLength = 12;
        } else if (mMode == PORT) { snprintf(mDigits, sizeof(mDigits), OnlineText::portEditorFormat, mDraft.port); mLength = 5; }
        else if (mMode == ROOM) { snprintf(mDigits, sizeof(mDigits), OnlineText::roomFormat, mDraft.roomCode); mLength = 6; }
        mInput.begin(JUTGamePad::A | JUTGamePad::B | JUTGamePad::X | JUTGamePad::Y |
            JUTGamePad::Z | JUTGamePad::START | JUTGamePad::L | JUTGamePad::R |
            JUTGamePad::DPAD_LEFT | JUTGamePad::DPAD_RIGHT | JUTGamePad::DPAD_UP | JUTGamePad::DPAD_DOWN);
    }
    unsigned number(unsigned start, unsigned count) const {
        unsigned value = 0;
        for (unsigned i = 0; i < count; ++i) value = value * 10 + mDigits[start + i] - '0';
        return value;
    }
    bool readNumber(Menu *menu) {
        if (mMode == IP) {
            for (unsigned i = 0; i < 4; ++i)
                if (number(i * 3, 3) > 255) { menu->toast(OnlineText::invalidIp); return false; }
            for (unsigned i = 0; i < 4; ++i) mDraft.serverIp[i] = number(i * 3, 3);
        } else if (mMode == PORT) {
            const unsigned port = number(0, 5);
            if (!port || port > 65535) { menu->toast(OnlineText::invalidPort); return false; }
            mDraft.port = port;
        } else mDraft.roomCode = number(0, 6);
        return true;
    }
    void drawNumber(Menu *menu) {
        menu->fillMenuBox(70, 150, 500, 180, cPanel());
        menu->drawMenuText(rowName(mSel), 96, 170, 20, 20, cTitle());
        int x = 104;
        for (int i = 0; i < mLength; ++i) {
            if (mMode == IP && i && !(i % 3)) {
                menu->drawMenuText(OnlineText::dot, x, 216, 24, 24, cRow()); x += 26;
            }
            if (i == mCursor) menu->fillMenuBox(x - 3, 212, 26, 32, cRowSelBg());
            const char digit[] = { mDigits[i], 0 };
            menu->drawMenuText(digit, x, 216, 24, 24, i == mCursor ? cValue() : cRow());
            x += 26;
        }
        small(menu, OnlineText::digitHelp, 96, 268, 450);
        drawFooterText(menu, OnlineText::keepCancel, 96, 294);
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
    RawPromptInput mInput;
    char mDigits[13];
    u8 mSel, mMode, mCursor, mLength, mPage;
    bool mUpper, mDiagnostics;
};
}
#pragma clang section text=".foxtrot.text"
