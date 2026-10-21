#include "susamune/live_race.hxx"

#if TIMEWARP_LIVE_RACING
#include "Dolphin/OS.h"
#include "Dolphin/VI.h"
#include "Dolphin/VI_types.h"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"
#include "Dolphin/string.h"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/System/Application.hxx"
#include "susamune/addresses.hxx"
#include "susamune/ghost_format.h"
#include "susamune/iling.hxx"
#include "susamune/live_ghost.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_relay.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/menu.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/savestate.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/tas_project.hxx"
#include "susamune/warp_wheel.hxx"

#pragma clang section rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace LiveRace {
namespace {
namespace Session = LiveRaceSession;
namespace Relay = LiveRelay;
enum Phase { NO_MATCH, WAIT_OFFER, WAIT_READY, RUNNING, ROUND_DONE, MATCH_DONE, ROAMING, DRAFTING };
enum { OFFER = 1, READY = 2, CANCEL = 3, START = 4, NEW_MATCH = 5, CATALOGUE = 1 };
enum { DRAFT_BEGIN = 6, DRAFT_NEXT = 7, DRAFT_APPLY = 8, DRAFT_REQUEST = 9 };
struct Scene { u8 area, episode, parentArea, parentEpisode; };
struct Runtime {
    Session::Session session;
    Relay::Client relay;
    u32 openedMs, networkSeenMs, sentPoseMs, round, stageSeen, sceneEpoch;
    Scene localScene, peerScene;
    u8 sceneObservations, localWins, peerWins;
    Phase phase;
    bool active, hosting, relayStarted, started, connected, localReady, peerReady;
    bool offerNeeded, readyNeeded, startNeeded, cancelNeeded, newMatchNeeded;
    bool localResult, peerResult, resultSent, localEligible, peerEligible;
    bool peerSceneKnown;
    s32 localQf, peerQf, networkError;
    const char *message;
    Diagnostics diagnostics;
    LiveDraft::State draft;
    LiveDraft::Token choiceToken;
    u32 draftRandom;
    u8 choice;
    bool choiceNeeded, choiceSent;
};
Options sOptions;
Runtime s;
volatile u32 sStageMarker;
static_assert(sizeof(Runtime) < 2048, "online session scalar budget");
static_assert(MSR_ANIMATION_COUNT == SUSAMUNE_GHOST_ANIMATION_ID_MAX + 1,
              "online animation catalogue");
static_assert(MSR_ANIMATION_PHASE_MAX == SUSAMUNE_GHOST_ANIMATION_PHASE_MAX,
              "online animation phase");

namespace Text {
static const char assisted[] = "Assisted result - round void";
static const char tie[] = "Tie - ready for another round";
static const char roundWon[] = "Round won";
static const char roundLost[] = "Round lost";
static const char matchWon[] = "Match won - host can set up the next match";
static const char matchLost[] = "Match lost - host can set up the next match";
static const char freeRoam[] = "Free roam - host can set up a race";
static const char applyingSetup[] = "Sharing the next setup";
static const char freeRoamScore[] = "Online free roam";
static const char ready[] = "Ready when you are";
static const char cancelled[] = "Round cancelled - ready again";
static const char startDeclined[] = "Start declined - ready again";
static const char finishAction[] = "Finish the current practice action first";
static const char pendingGhost[] = "Save or dismiss the pending ghost first";
static const char couldNotStart[] = "Could not start - ready again";
static const char raceLive[] = "Race live - first eligible IL finish";
static const char requires60Hz[] = "Online prototype requires 60 Hz";
static const char needServer[] = "Enter the relay server IP and port";
static const char needRoom[] = "Enter the six-digit room code";
#if IS_EMULATOR
static const char networkBusy[] = "Run the Dolphin companion, then retry";
static const char networkStarting[] = "Starting Dolphin companion network";
#else
static const char networkBusy[] = "Network unavailable or still closing";
static const char networkStarting[] = "Starting Wii network";
#endif
static const char waitingIl[] = "Waiting for host's IL";
static const char defaultName[] = "Player";
static const char offline[] = "Offline";
static const char disconnected[] = "Disconnected";
static const char waitingReady[] = "Ready - waiting for the other player";
static const char waitingResult[] = "Finished - waiting for opponent's time";
#if IS_EMULATOR
static const char networkLost[] = "Dolphin companion unavailable - reconnect";
#else
static const char networkLost[] = "Wii network unavailable - reconnect";
#endif
static const char invalidSettings[] = "Invalid connection settings";
static const char peerLeft[] = "Opponent left";
static const char connectionLost[] = "Connection lost - reconnect";
static const char starting[] = "Starting network";
static const char connected[] = "Connected";
static const char waitingGuest[] = "Waiting for guest";
static const char connecting[] = "Connecting to opponent";
static const char openingRoom[] = "Connecting to relay server";
static const char noRoom[] = "Room not found - check the code";
static const char roomFull[] = "Room already has two players";
static const char serverBusy[] = "Server full - try again shortly";
static const char roomClosed[] = "Room closed - create or join a new room";
static const char lobbyExpired[] = "Room expired - create a new room";
static const char serverLost[] = "Relay server unavailable - reconnect";
static const char empty[] = "";
static const char scoreFormat[] = "Online  %u - %u   Best of %u";
static const char setScoreFormat[] = "Set %u - %u  |  IL %u - %u";
static const char draftBegin[] = "Preparing five ILs";
static const char draftHostBan[] = "Player 1: ban one IL";
static const char draftGuestBan[] = "Player 2: ban two ILs";
static const char draftHostPick[] = "Player 1: pick the IL";
static const char draftWinnerBan[] = "Previous winner: ban one IL";
static const char draftLoserPick[] = "Previous loser: choose the counterpick";
static const char setWon[] = "Set won - host can apply the next setup";
static const char setLost[] = "Set lost - host can apply the next setup";
}

u32 nowMs() { return static_cast<u32>(OSGetTime() / (OS_TIMER_CLOCK / 1000u)); }
bool sendControl(void *, const Session::Endpoint &, const void *data, unsigned bytes) {
    return Relay::sendControl(s.relay, data, bytes);
}
bool sendPose(void *, const Session::Endpoint &, const void *data, unsigned bytes) {
    return Relay::sendPose(s.relay, data, bytes);
}
bool sameScene(const Scene &a, const Scene &b) {
    return a.area == b.area && a.episode == b.episode &&
        a.parentArea == b.parentArea && a.parentEpisode == b.parentEpisode;
}
bool portableScene(const Scene &scene) {
    if (scene.episode > SUSAMUNE_GHOST_ROUTE_EPISODE_MAX) return false;
    switch (scene.area) {
#define LIVE_PARENT(area, parent) case area: return scene.parentArea == parent && \
        (parent == 0xffu ? scene.parentEpisode == 0xffu : scene.parentEpisode < 8);
        SUSAMUNE_GHOST_PORTABLE_ROUTE_LIST(LIVE_PARENT)
#undef LIVE_PARENT
    default: return false;
    }
}
bool captureScene(Scene &scene) {
    scene.area = gpApplication.mCurrentScene.mAreaID;
    scene.episode = gpApplication.mCurrentScene.mEpisodeID;
    scene.parentArea = LevelWarp::parentArea(scene.area);
    scene.parentEpisode = 0xff;
    if (scene.parentArea != 0xff) {
        if (!TFlagManager::smInstance) return false;
        const s32 episode = TFlagManager::smInstance->getFlag(0x40003);
        if (episode < 0 || episode > 7) return false;
        scene.parentEpisode = static_cast<u8>(episode);
    }
    return portableScene(scene);
}
void receivedPose(void *, const MSRHeader &header, const MSRPose &pose, unsigned receivedMs) {
    const Scene scene = {pose.area, pose.episode, pose.parentArea, pose.parentEpisode};
    if (!portableScene(scene)) return;
    Ghost::VisualState visual = {};
    visual.x = pose.x * 0.125f; visual.y = pose.y * 0.125f; visual.z = pose.z * 0.125f;
    visual.yaw = static_cast<s16>(pose.yaw);
    visual.animationId = pose.animation; visual.animationPhase = pose.phase;
    visual.heldObjectId = pose.heldObjectId; visual.heldNameKey = pose.heldNameKey;
    visual.yoshi = pose.yoshi; visual.visible = (pose.flags & MSR_VISIBLE) != 0;
    memcpy(&visual.fludd, pose.fludd, sizeof(pose.fludd));
    SusamunePracticeInput input = {};
    input.buttons = pose.buttons;
    input.stickX = pose.stickX; input.stickY = pose.stickY;
    input.substickX = pose.substickX; input.substickY = pose.substickY;
    input.triggerL = pose.triggerL; input.triggerR = pose.triggerR;
    if (LiveGhost::submit(visual, header.sequence, pose.remoteMs, pose.sceneEpoch, receivedMs, &input)) {
        s.peerScene = scene;
        s.peerSceneKnown = true;
    }
}
bool validOptions(const Options &value) {
    if (!value.port || value.roomCode > 999999 || value.entry < 0 || value.entry >= ILing::count() ||
        value.episode >= 8 || !(value.bestOf == 1 || value.bestOf == 3 || value.bestOf == 5 || value.bestOf == 7) ||
        !value.name[0] || value.name[16] || value.pool > 2 ||
        (value.draft && (value.freeRoam || value.bestOf != 3))) return false;
    for (unsigned i = 0; i < 16 && value.name[i]; ++i)
        if (static_cast<u8>(value.name[i]) < 0x20 || static_cast<u8>(value.name[i]) > 0x7e) return false;
    return true;
}
void configPayload(u8 *body, unsigned type) {
    memset(body, 0, 12);
    body[0] = static_cast<u8>(type);
    body[1] = sOptions.episode; body[2] = sOptions.bestOf;
    body[3] = (type == READY && s.localReady ? 1u : 0u) | (sOptions.freeRoam ? 2u : 0u) |
        (sOptions.draft ? 4u : 0u) | (sOptions.setBo5 ? 8u : 0u) | (sOptions.pool << 4);
    MSRWrite16(body + 4, static_cast<u16>(sOptions.entry));
    MSRWrite16(body + 6, static_cast<u16>(ILing::persistentSlot(sOptions.entry)));
    MSRWrite32(body + 8, CATALOGUE);
}
bool decodeConfig(const u8 *body, unsigned bytes, Options &options) {
    if (bytes != 12 || MSRRead32(body + 8) != CATALOGUE || body[0] < OFFER || body[0] > NEW_MATCH ||
        (body[3] & ~63u) || (body[0] != READY && (body[3] & 1u))) return false;
    options = sOptions;
    options.entry = static_cast<int>(MSRRead16(body + 4));
    options.episode = body[1]; options.bestOf = body[2];
    options.freeRoam = (body[3] & 2u) != 0;
    options.draft = (body[3] & 4u) != 0;
    options.setBo5 = (body[3] & 8u) != 0;
    options.pool = body[3] >> 4;
    return validOptions(options) && ILing::persistentSlot(options.entry) == static_cast<int>(MSRRead16(body + 6));
}
bool sameConfig(const Options &options) {
    return options.entry == sOptions.entry && options.episode == sOptions.episode &&
        options.bestOf == sOptions.bestOf && options.freeRoam == sOptions.freeRoam &&
        options.draft == sOptions.draft && options.setBo5 == sOptions.setBo5 && options.pool == sOptions.pool;
}
void resetRound() {
    s.localReady = s.peerReady = false;
    s.localResult = s.peerResult = s.resultSent = false;
    s.startNeeded = s.readyNeeded = s.cancelNeeded = false;
    s.phase = sOptions.freeRoam ? ROAMING :
        sOptions.draft && s.draft.phase != LiveDraft::IL_MATCH ? DRAFTING : WAIT_READY;
}
const char *draftMessage() {
    switch (s.draft.phase) {
    case LiveDraft::OPENING_HOST_BAN: return Text::draftHostBan;
    case LiveDraft::OPENING_GUEST_BANS: return Text::draftGuestBan;
    case LiveDraft::OPENING_HOST_PICK: return Text::draftHostPick;
    case LiveDraft::COUNTER_WINNER_BAN: return Text::draftWinnerBan;
    case LiveDraft::COUNTER_LOSER_PICK: return Text::draftLoserPick;
    default: return Text::draftBegin;
    }
}
bool applyChoice(LiveDraft::State &draft, u8 actor, unsigned candidate, LiveDraft::Token token) {
    return LiveDraft::ban(draft, actor, candidate, token) || LiveDraft::pick(draft, actor, candidate, token);
}
void adoptDraft(const LiveDraft::State &draft) {
    s.draft = draft;
    s.choiceNeeded = s.choiceSent = false;
    if (draft.phase == LiveDraft::IL_MATCH) {
        sOptions.entry = draft.selected;
        sOptions.episode = static_cast<u8>(ILing::onlineDefaultEpisode(draft.selected));
        s.localWins = s.peerWins = 0;
        s.phase = ROUND_DONE;
        s.message = Text::ready;
    } else {
        s.phase = DRAFTING;
        s.message = draftMessage();
    }
}
bool drawCandidates(u16 *entries) {
    unsigned count = 0;
    if (!s.draftRandom) s.draftRandom = s.session.config.nonceLow ^ 0x74696d65u;
    if (!s.draftRandom) s.draftRandom = 1;
    for (int entry = 0; entry < ILing::count(); ++entry) {
        if (!ILing::onlinePoolContains(entry, sOptions.pool)) continue;
        ++count;
        s.draftRandom ^= s.draftRandom << 13;
        s.draftRandom ^= s.draftRandom >> 17;
        s.draftRandom ^= s.draftRandom << 5;
        const unsigned slot = count <= 5 ? count - 1 : s.draftRandom % count;
        if (slot < 5) entries[slot] = static_cast<u16>(entry);
    }
    return count >= 5;
}
void draftPayload(u8 *body, unsigned type, LiveDraft::Token token) {
    memset(body, 0, 12);
    body[0] = static_cast<u8>(type);
    MSRWrite32(body + 4, token.generation);
    MSRWrite32(body + 8, token.revision);
}
void receivedDraft(const MSRHeader &header, const u8 *body, unsigned bytes) {
    if (!sOptions.draft || s.phase != DRAFTING || header.round != s.round || bytes < 12 || body[3]) return;
    const LiveDraft::Token token = {MSRRead32(body + 4), MSRRead32(body + 8)};
    LiveDraft::State next = s.draft;
    if (body[0] == DRAFT_BEGIN || body[0] == DRAFT_NEXT) {
        if (s.hosting || bytes != 24 || body[1] || body[2] || body[22] || body[23]) return;
        u16 entries[5];
        for (unsigned i = 0; i < 5; ++i) {
            entries[i] = MSRRead16(body + 12 + 2 * i);
            if (!ILing::onlinePoolContains(entries[i], sOptions.pool)) return;
        }
        if (body[0] == DRAFT_BEGIN) {
            if (next.phase != LiveDraft::UNINITIALIZED || token.generation != s.round || token.revision ||
                !LiveDraft::begin(next, s.round, sOptions.setBo5 ? 5 : 3, entries)) return;
        } else if (!LiveDraft::nextCandidates(next, entries, token)) return;
        adoptDraft(next);
    } else if (body[0] == DRAFT_REQUEST || body[0] == DRAFT_APPLY) {
        if (bytes != 12 || !applyChoice(next, body[1], body[2], token)) return;
        if (body[0] == DRAFT_REQUEST) {
            if (!s.hosting || body[1] != LiveDraft::PLAYER_TWO || s.choiceNeeded) return;
            s.choice = body[2]; s.choiceToken = token; s.choiceNeeded = true;
        } else if (!s.hosting) adoptDraft(next);
    }
}
void serviceDraft() {
    if (s.choiceNeeded) {
        const u8 actor = LiveDraft::currentActor(s.draft);
        LiveDraft::State next = s.draft;
        if (!applyChoice(next, actor, s.choice, s.choiceToken)) {
            s.choiceNeeded = s.choiceSent = false;
            return;
        }
        u8 body[12]; draftPayload(body, s.hosting ? DRAFT_APPLY : DRAFT_REQUEST, s.choiceToken);
        body[1] = actor; body[2] = s.choice;
        if (Session::sendReliable(s.session, MSR_READY, body, sizeof(body), s.round)) {
            if (s.hosting) adoptDraft(next);
            else { s.choiceNeeded = false; s.choiceSent = true; }
        }
    } else if (s.hosting && (s.draft.phase == LiveDraft::UNINITIALIZED || s.draft.phase == LiveDraft::NEED_CANDIDATES)) {
        u16 entries[5];
        if (!drawCandidates(entries)) return;
        const bool initial = s.draft.phase == LiveDraft::UNINITIALIZED;
        LiveDraft::State next = s.draft;
        const LiveDraft::Token token = initial ? LiveDraft::Token{s.round, 0} : LiveDraft::token(next);
        if (initial ? !LiveDraft::begin(next, s.round, sOptions.setBo5 ? 5 : 3, entries) :
                      !LiveDraft::nextCandidates(next, entries, token)) return;
        u8 body[24] = {}; draftPayload(body, initial ? DRAFT_BEGIN : DRAFT_NEXT, token);
        for (unsigned i = 0; i < 5; ++i) MSRWrite16(body + 12 + 2 * i, entries[i]);
        if (Session::sendReliable(s.session, MSR_READY, body, sizeof(body), s.round)) adoptDraft(next);
    }
}
bool canConfigureRace() {
    return s.connected && s.hosting && (s.phase == MATCH_DONE || s.phase == ROAMING) &&
        !s.newMatchNeeded && !s.offerNeeded && !Session::status(s.session).pending;
}
void abortRound(const char *message, bool notify) {
    s.message = message;
    s.localReady = s.peerReady = false;
    s.phase = ROUND_DONE;
    s.cancelNeeded = notify;
    s.startNeeded = s.readyNeeded = false;
}
void settleRound() {
    if (s.phase == RUNNING && s.localResult && s.peerResult) {
        u8 winner = LiveDraft::NO_PLAYER;
        if (!s.localEligible || !s.peerEligible) {
            s.message = Text::assisted;
        } else if (s.localQf == s.peerQf) {
            s.message = Text::tie;
        } else if (s.localQf < s.peerQf) {
            ++s.localWins; s.message = Text::roundWon;
            winner = s.hosting ? LiveDraft::PLAYER_ONE : LiveDraft::PLAYER_TWO;
        } else {
            ++s.peerWins; s.message = Text::roundLost;
            winner = s.hosting ? LiveDraft::PLAYER_TWO : LiveDraft::PLAYER_ONE;
        }
        s.localReady = s.peerReady = false;
        s.phase = (s.localWins > sOptions.bestOf / 2 || s.peerWins > sOptions.bestOf / 2) ? MATCH_DONE : ROUND_DONE;
        if (s.phase == MATCH_DONE) s.message = s.localWins > s.peerWins ? Text::matchWon : Text::matchLost;
        if (sOptions.draft) {
            LiveDraft::recordRound(s.draft, winner, LiveDraft::token(s.draft));
            if (s.draft.phase == LiveDraft::SET_DONE) {
                s.phase = MATCH_DONE;
                const unsigned local = s.hosting ? 0 : 1;
                s.message = s.draft.setWins[local] > s.draft.setWins[local ^ 1] ? Text::setWon : Text::setLost;
            } else if (s.draft.phase == LiveDraft::NEED_CANDIDATES) {
                s.phase = DRAFTING; s.message = Text::draftBegin;
            }
        }
    }
}
void receivedControl(void *, const MSRHeader &header, const void *data, unsigned bytes) {
    const u8 *body = static_cast<const u8 *>(data);
    if (header.kind == MSR_READY && bytes && body[0] >= DRAFT_BEGIN) {
        receivedDraft(header, body, bytes);
        return;
    }
    if (header.kind == MSR_RESULT) {
        if ((s.phase != RUNNING && !(s.phase == WAIT_READY && s.startNeeded)) ||
            header.round != s.round || s.peerResult || bytes != 8 ||
            body[4] > 1 || body[5] || body[6] || body[7]) return;
        const u32 qf = MSRRead32(body);
        if (body[4] ? qf > 0x7fffffffu : qf != 0xffffffffu) return;
        s.peerQf = body[4] ? static_cast<s32>(qf) : -1;
        s.peerEligible = body[4]; s.peerResult = true;
        settleRound();
        return;
    }
    Options proposed;
    if (!decodeConfig(body, bytes, proposed)) return;
    if (header.kind == MSR_READY && (body[0] == OFFER || body[0] == NEW_MATCH) && !s.hosting) {
        const bool newMatch = body[0] == NEW_MATCH;
        if (!header.round || (newMatch ?
            !((s.phase == MATCH_DONE || s.phase == ROAMING) && header.round == s.round + 1u) :
            !((s.phase == WAIT_OFFER && header.round == 1) ||
              (s.phase == ROUND_DONE && header.round == s.round + 1u)))) return;
        if (!newMatch && s.phase != WAIT_OFFER && !sameConfig(proposed)) return;
        sOptions.entry = proposed.entry; sOptions.episode = proposed.episode; sOptions.bestOf = proposed.bestOf;
        sOptions.freeRoam = proposed.freeRoam;
        sOptions.draft = proposed.draft; sOptions.setBo5 = proposed.setBo5; sOptions.pool = proposed.pool;
        s.round = header.round;
        if (newMatch) {
            s.localWins = s.peerWins = 0; s.draft = {};
            s.choiceNeeded = s.choiceSent = false;
        }
        resetRound();
        if (s.phase == ROAMING) s.message = Text::freeRoam;
        else if (s.phase == DRAFTING) s.message = Text::draftBegin;
        else if (newMatch || !s.message || s.message == Text::waitingIl) s.message = Text::ready;
        return;
    }
    if (!sameConfig(proposed) || header.round != s.round) return;
    if (header.kind == MSR_READY && body[0] == CANCEL &&
        (s.phase == WAIT_READY || s.phase == RUNNING || s.phase == ROUND_DONE)) {
        abortRound(Text::cancelled, false);
    } else if (header.kind == MSR_READY && body[0] == READY && s.phase == WAIT_READY) {
        s.peerReady = (body[3] & 1u) != 0;
    } else if (header.kind == MSR_START && body[0] == START && !s.hosting && s.phase == WAIT_READY) {
        if (s.localReady) s.startNeeded = true;
        else abortRound(Text::startDeclined, true);
    }
}
const Session::Callbacks kCallbacks = {nullptr, sendControl, sendPose, receivedPose, receivedControl};

bool safeToStart() {
    if (Ghost::observerPreparing() || Ghost::observerStatsSuppressed() || StageLoader::active() ||
        PracticeSession::ownsGameplayInput() || SavestateManager::diskBusy() || TasProject::busy() ||
        WarpWheel::shown() || WarpWheel::promptPending() || gSettings.getBool(SETTING_DISABLE_WARPS)) {
        s.message = Text::finishAction;
        return false;
    }
    char name[64]; u32 token;
    if (ILing::copyWarpDiscardName(sOptions.entry, name, sizeof(name), &token)) {
        s.message = Text::pendingGhost;
        return false;
    }
    return true;
}
void startRound() {
    s.startNeeded = false;
    if (s.phase != WAIT_READY || !s.localReady) {
        abortRound(Text::startDeclined, true);
        return;
    }
    if (!safeToStart() || !ILing::startOnline(sOptions.entry, sOptions.episode)) {
        abortRound(Text::couldNotStart, true);
        return;
    }
    s.phase = RUNNING;
    s.localResult = s.resultSent = false;
    s.message = Text::raceLive;
    if (gMenu) gMenu->hide();
}
bool queueConfig(unsigned kind, unsigned type) {
    u8 body[12]; configPayload(body, type);
    return Session::sendReliable(s.session, kind, body, sizeof(body), s.round);
}
void serviceRace() {
    settleRound();
    if (Session::status(s.session).pending) return;
    if (s.cancelNeeded) {
        if (queueConfig(MSR_READY, CANCEL)) s.cancelNeeded = false;
    } else if (s.localResult && !s.resultSent) {
        u8 body[8] = {};
        MSRWrite32(body, s.localEligible ? static_cast<u32>(s.localQf) : 0xffffffffu);
        body[4] = s.localEligible;
        if (Session::sendReliable(s.session, MSR_RESULT, body, sizeof(body), s.round)) s.resultSent = true;
    } else if (s.hosting && s.newMatchNeeded) {
        u8 body[12]; configPayload(body, NEW_MATCH);
        // Keep the round generation monotonic across matches to reject stale results.
        if (Session::sendReliable(s.session, MSR_READY, body, sizeof(body), s.round + 1u)) {
            ++s.round; s.localWins = s.peerWins = 0; s.newMatchNeeded = false;
            s.draft = {}; s.choiceNeeded = s.choiceSent = false;
            resetRound();
            s.message = s.phase == ROAMING ? Text::freeRoam : s.phase == DRAFTING ? Text::draftBegin : Text::ready;
        }
    } else if (s.hosting && (s.offerNeeded || s.phase == ROUND_DONE)) {
        if (!s.offerNeeded) {
            ++s.round; resetRound(); s.offerNeeded = true;
        }
        if (queueConfig(MSR_READY, OFFER)) s.offerNeeded = false;
    } else if (s.phase == DRAFTING) {
        serviceDraft();
    } else if (s.readyNeeded) {
        if (queueConfig(MSR_READY, READY)) s.readyNeeded = false;
    } else if (s.hosting && s.phase == WAIT_READY && s.localReady && s.peerReady) {
        if (queueConfig(MSR_START, START)) startRound();
    } else if (!s.hosting && s.startNeeded) {
        startRound();
    }
}
bool begin(bool hosting) {
    if (s.active || !validOptions(sOptions)) return false;
    if (VIGetTvFormat() == VI_PAL) { s.message = Text::requires60Hz; return false; }
    Session::Endpoint endpoint = {};
    memcpy(endpoint.ip, sOptions.serverIp, 4); endpoint.port = sOptions.port;
    if (!TWLiveEndpointValid(&endpoint)) { s.message = Text::needServer; return false; }
    if (!hosting && sOptions.roomCode < 100000u) { s.message = Text::needRoom; return false; }
#if IS_EMULATOR
    const u16 localPort = 0; // Let a local relay or second Dolphin own its own port.
#else
    const u16 localPort = sOptions.port;
#endif
    if (!LiveTransport::begin(localPort)) { s.message = Text::networkBusy; return false; }
    s = {};
    s.active = true; s.hosting = hosting; s.openedMs = nowMs();
    s.networkSeenMs = s.openedMs;
    s.message = Text::networkStarting;
    LiveGhost::reset();
    return true;
}
void updatePose(u32 now) {
    Ghost::VisualState visual;
    Scene scene;
    const bool valid = Ghost::captureLiveVisual(&visual) && captureScene(scene);
    if (s.stageSeen != sStageMarker) {
        s.stageSeen = sStageMarker; ++s.sceneEpoch; s.sceneObservations = 0;
        LiveGhost::reset();
        const auto info = Session::status(s.session);
        unsigned length = 0; while (length < 16 && info.remoteName[length]) ++length;
        LiveGhost::setName(info.remoteName, length);
    }
    if (!valid) s.sceneObservations = 0;
    else if (!s.sceneObservations || !sameScene(scene, s.localScene)) {
        s.localScene = scene; s.sceneObservations = 1; ++s.sceneEpoch;
    } else if (s.sceneObservations < 3) ++s.sceneObservations;
    const bool stable = valid && s.sceneObservations >= 3;
    LiveGhost::tick(now, stable && s.peerSceneKnown && sameScene(s.localScene, s.peerScene));
    if (now - s.sentPoseMs < 33u) return;
    s.sentPoseMs = now;
    if (!stable) return;
    MSRPose pose = {};
    pose.remoteMs = now; pose.sceneEpoch = s.sceneEpoch;
    pose.area = scene.area; pose.episode = scene.episode;
    pose.parentArea = scene.parentArea; pose.parentEpisode = scene.parentEpisode;
    pose.x = static_cast<s32>(visual.x * 8); pose.y = static_cast<s32>(visual.y * 8); pose.z = static_cast<s32>(visual.z * 8);
    pose.yaw = static_cast<u16>(visual.yaw); pose.animation = visual.animationId; pose.phase = visual.animationPhase;
    pose.heldObjectId = visual.heldObjectId; pose.heldNameKey = visual.heldNameKey;
    pose.yoshi = visual.yoshi; pose.flags = visual.visible ? MSR_VISIBLE : 0;
    memcpy(pose.fludd, &visual.fludd, sizeof(pose.fludd));
    // update runs before the next director call, matching its last completed input.
    SusamunePracticeInput input = {};
    if (PracticeSession::consumedInput(&input) && !input.error) {
        pose.buttons = input.buttons & MSR_INPUT_BUTTON_MASK;
        pose.stickX = input.stickX; pose.stickY = input.stickY;
        pose.substickX = input.substickX; pose.substickY = input.substickY;
        pose.triggerL = input.triggerL; pose.triggerR = input.triggerR;
    }
    Session::publishPose(s.session, pose, s.round);
}
void acceptConnection() {
    const auto connection = Session::status(s.session);
    if (s.connected || !connection.connected) return;
    s.connected = true; s.round = 1;
    if (s.hosting) resetRound();
    else s.phase = WAIT_OFFER;
    s.offerNeeded = s.hosting;
    s.message = s.hosting ? (sOptions.freeRoam ? Text::freeRoam : sOptions.draft ? Text::draftBegin : Text::ready) : Text::waitingIl;
    unsigned length = 0; while (length < 16 && connection.remoteName[length]) ++length;
    LiveGhost::setName(connection.remoteName, length);
}
Session::Endpoint serverEndpoint() {
    Session::Endpoint endpoint = {};
    memcpy(endpoint.ip, sOptions.serverIp, 4); endpoint.port = sOptions.port;
    return endpoint;
}
bool startSession(u32 now) {
    if (s.started) return true;
    const auto relay = Relay::status(s.relay);
    if (!relay.peerReady) return false;
    Session::Config config = {};
    memcpy(config.name, sOptions.name, 16);
    const u64 stamp = OSGetTime();
    config.nonceHigh = static_cast<u32>(stamp >> 32) ^ 0x4d535231u;
    config.nonceLow = static_cast<u32>(stamp) | 1u;
    config.pin = relay.roomCode; config.region = SUSAMUNE_GAME_VERSION - 1;
    config.timing = MSR_TIMING_60HZ;
    const auto endpoint = serverEndpoint();
    s.started = Session::init(s.session, config, kCallbacks) &&
        (s.hosting ? Session::startHost(s.session, endpoint, now) : Session::startGuest(s.session, endpoint, now));
    return s.started;
}
bool relayControl(void *, const Session::Endpoint &to, const void *data, unsigned bytes) {
    const bool sent = LiveTransport::sendControl(to, data, bytes);
    if (sent) ++s.diagnostics.submitted;
    return sent;
}
bool relayPose(void *, const Session::Endpoint &to, const void *data, unsigned bytes) {
    const bool sent = LiveTransport::publishPose(to, data, bytes);
    if (sent) ++s.diagnostics.submitted;
    return sent;
}
void receivedRelay(void *, const void *data, unsigned bytes, unsigned now) {
    // A peer packet can overtake the server's room-ready notice.
    if (!startSession(now)) return;
    Session::receivePacket(s.session, serverEndpoint(), data, bytes, now);
    acceptConnection();
}
const Relay::Callbacks kRelayCallbacks = {nullptr, relayControl, relayPose, receivedRelay};
const char *relayFailure(Relay::Error error) {
    switch (error) {
    case Relay::NO_ROOM: return Text::noRoom;
    case Relay::ROOM_FULL: return Text::roomFull;
    case Relay::SERVER_BUSY: return Text::serverBusy;
    case Relay::ROOM_CLOSED: return Text::roomClosed;
    case Relay::PEER_LEFT: return Text::peerLeft;
    case Relay::LOBBY_EXPIRED: return Text::lobbyExpired;
    case Relay::INVALID_CONFIG: return Text::invalidSettings;
    default: return Text::serverLost;
    }
}
}

void init() {
    s = {}; sOptions = {}; sStageMarker = 0;
    memcpy(sOptions.name, Text::defaultName, 7);
    sOptions.serverIp[0] = 147; sOptions.serverIp[1] = 185;
    sOptions.serverIp[2] = 221; sOptions.serverIp[3] = 213;
    sOptions.port = 48222; sOptions.bestOf = 3;
    s.message = Text::offline;
    LiveGhost::reset();
}
const Options &options() { return sOptions; }
bool configure(const Options &options) {
    if (!validOptions(options)) return false;
    if (s.active) {
        if (!canConfigureRace() || options.port != sOptions.port || options.roomCode != sOptions.roomCode) return false;
        for (unsigned i = 0; i < 17; ++i) if (options.name[i] != sOptions.name[i]) return false;
        for (unsigned i = 0; i < 4; ++i) if (options.serverIp[i] != sOptions.serverIp[i]) return false;
    }
    sOptions = options;
    bool ended = false;
    for (unsigned i = 0; i < sizeof(sOptions.name); ++i) {
        if (!sOptions.name[i]) ended = true;
        if (ended) sOptions.name[i] = 0;
    }
    return true;
}
bool host() { return begin(true); }
bool join() { return begin(false); }
void disconnect() {
    Session::stop(s.session); Relay::stop(s.relay); LiveTransport::stop(); LiveGhost::reset();
    s.active = s.connected = false; s.phase = NO_MATCH;
    s.message = Text::disconnected;
}
bool ready() {
    if (!s.connected || s.phase != WAIT_READY || (!s.localReady && !safeToStart())) return false;
    s.localReady = !s.localReady; s.readyNeeded = true;
    if (!s.localReady && s.startNeeded) {
        abortRound(Text::startDeclined, true);
        return true;
    }
    s.message = s.localReady ? Text::waitingReady : Text::ready;
    return true;
}
bool newMatch() {
    if (!canConfigureRace() || s.round == ~0u) return false;
    s.newMatchNeeded = true;
    s.message = Text::applyingSetup;
    return true;
}
bool chooseDraft(unsigned candidate) {
    if (!s.connected || s.phase != DRAFTING || s.choiceNeeded || s.choiceSent || s.offerNeeded ||
        Session::status(s.session).pending || candidate >= LiveDraft::CANDIDATE_COUNT) return false;
    const u8 actor = s.hosting ? LiveDraft::PLAYER_ONE : LiveDraft::PLAYER_TWO;
    LiveDraft::State next = s.draft;
    const auto token = LiveDraft::token(next);
    if (!applyChoice(next, actor, candidate, token)) return false;
    s.choice = static_cast<u8>(candidate); s.choiceToken = token; s.choiceNeeded = true;
    return true;
}
void beforeStageSetup() { ++sStageMarker; }
void onILResult(int entry, s32 qf, bool eligible) {
    if (!s.connected || s.phase != RUNNING || s.localResult || entry != sOptions.entry) return;
    s.localQf = qf; s.localEligible = eligible && qf >= 0;
    s.localResult = true;
    s.message = Text::waitingResult;
}
void update() {
    LiveStun::update();
    if (!s.active) return;
    const u32 now = nowMs();
    const auto transport = LiveTransport::poll();
    // A concurrent ARM publication can leave this one bounded read unavailable.
    if (transport.state == TW_LIVE_UNAVAILABLE && now - s.networkSeenMs < 15000u) return;
    if (transport.state == TW_LIVE_READY) {
        s.networkSeenMs = now;
        LiveTransport::Diagnostics diagnostics;
        if (LiveTransport::diagnostics(transport, &diagnostics)) {
            // Retirement withdraws this line; retain the last valid attempt.
            s.diagnostics.socketSent = diagnostics.sent;
            s.diagnostics.socketReceived = diagnostics.received;
            s.diagnostics.dropped = diagnostics.dropped;
            s.diagnostics.sendErrors = diagnostics.sendErrors;
            s.diagnostics.receiveErrors = diagnostics.receiveErrors;
            s.diagnostics.socketError = diagnostics.lastError;
            s.diagnostics.socketAvailable = true;
        }
    }
    s.networkError = transport.error;
    if (transport.state == TW_LIVE_FAILED || (s.relayStarted && transport.state != TW_LIVE_READY) ||
        (!s.relayStarted && now - s.openedMs > 15000u)) {
        disconnect(); s.message = Text::networkLost; return;
    }
    if (!s.relayStarted) {
        if (transport.state != TW_LIVE_READY) return;
        const u64 stamp = OSGetTime();
        Relay::init(s.relay, kRelayCallbacks);
        if (!Relay::begin(s.relay, s.hosting, s.hosting ? 0u : sOptions.roomCode,
                static_cast<u32>(stamp >> 32) ^ 0x4d524c31u, static_cast<u32>(stamp) | 1u,
                serverEndpoint(), now)) {
            disconnect(); s.message = Text::invalidSettings; return;
        }
        s.relayStarted = true;
        s.message = Text::openingRoom;
    }
    LiveTransport::Packet packet;
    for (unsigned i = 0; i < 4 && LiveTransport::receive(packet); ++i) {
        ++s.diagnostics.received;
        if (Relay::receive(s.relay, packet.endpoint, packet.data, packet.bytes, now))
            ++s.diagnostics.accepted;
    }
    Relay::tick(s.relay, now);
    const auto relay = Relay::status(s.relay);
    if (relay.state == Relay::FAILED) {
        const char *message = relayFailure(relay.error);
        disconnect(); s.message = message;
        s.networkError = -1000 - static_cast<s32>(relay.error);
        return;
    }
    if (!relay.peerReady) {
        if (relay.roomCode && s.hosting) s.message = Text::waitingGuest;
        return;
    }
    if (!startSession(now)) {
        disconnect(); s.message = Text::invalidSettings; return;
    }
    Session::tick(s.session, now);
    acceptConnection();
    const auto connection = Session::status(s.session);
    if (connection.state == Session::FAILED || connection.state == Session::STOPPED) {
        disconnect(); s.message = connection.error == Session::PEER_LEFT ? Text::peerLeft : Text::connectionLost; return;
    }
    if (!connection.connected) return;
    updatePose(now);
    serviceRace();
}
Status status() {
    Status out = {};
    const auto connection = Session::status(s.session);
    out.active = s.active; out.connected = s.connected; out.hosting = s.hosting;
    out.localReady = s.localReady; out.peerReady = s.peerReady; out.racing = s.phase == RUNNING;
    out.matchDone = s.phase == MATCH_DONE;
    out.freeRoam = s.phase == ROAMING;
    out.setupEditable = !s.active || canConfigureRace();
    out.drafting = s.phase == DRAFTING;
    out.draftPending = s.choiceNeeded || s.choiceSent || Session::status(s.session).pending;
    out.draft = s.draft;
    const auto relay = Relay::status(s.relay);
    out.roomCode = s.active && relay.roomCode ? relay.roomCode : sOptions.roomCode;
    out.connection = !s.active ? Text::offline : !s.relayStarted ? Text::starting : s.connected ? Text::connected :
        relay.peerReady ? Text::connecting : s.hosting && relay.roomCode ? Text::waitingGuest : Text::openingRoom;
    out.race = s.message ? s.message : Text::empty;
    memcpy(out.peerName, connection.remoteName, sizeof(out.peerName));
    out.pingMs = s.connected ? connection.pingMs : ~0u; out.networkError = s.networkError;
    out.localWins = s.localWins; out.peerWins = s.peerWins;
    out.diagnostics = s.diagnostics;
    LiveTransport::Endpoint endpoint;
    if (s.active && LiveTransport::localEndpoint(&endpoint)) {
        memcpy(out.localIp, endpoint.ip, 4);
        out.localPort = endpoint.port;
    }
    return out;
}
void draw(Menu *menu) {
    LiveGhost::drawName(menu);
    if (!menu || menu->shown() || !s.connected || PracticeSession::hideHud()) return;
    LiveGhost::drawInputs(menu);
    char text[80];
    if (sOptions.draft) {
        const unsigned local = s.hosting ? 0 : 1;
        snprintf(text, sizeof(text), Text::setScoreFormat,
            s.draft.setWins[local], s.draft.setWins[local ^ 1], s.localWins, s.peerWins);
    } else snprintf(text, sizeof(text), Text::scoreFormat, s.localWins, s.peerWins, sOptions.bestOf);
    const char *score = s.phase == ROAMING ? Text::freeRoamScore : text;
    const bool showStatus = s.phase != RUNNING || s.localResult;
    const char *message = s.message ? s.message : Text::empty;
    int width = Menu::textWidth(score, 14);
    int statusSize = 13;
    while (statusSize > 10 && Menu::textWidth(message, statusSize) > 390) --statusSize;
    const int statusWidth = showStatus ? Menu::textWidth(message, statusSize) : 0;
    if (statusWidth > width) width = statusWidth;
    menu->fillBox(28, 398, width + 8, showStatus ? 42 : 24,
                  JUtility::TColor(0, 0, 0, 130));
    menu->drawText(score, 32, 404, 14, 14, JUtility::TColor(190, 250, 255, 255));
    if (showStatus)
        menu->drawText(message, 32, 423, statusSize, statusSize, JUtility::TColor(255, 255, 255, 255));
}
}
#endif
