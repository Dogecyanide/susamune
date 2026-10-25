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
#include "susamune/live_p2p.hxx"
#include "susamune/live_playlist.hxx"
#include "susamune/live_group.hxx"
#include "susamune/live_invites.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/menu.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/qft_timer.hxx"
#include "susamune/savestate.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/susamune_cfg.h"
#include "susamune/tas_project.hxx"
#include "susamune/warp_wheel.hxx"

#pragma clang section rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace LiveRace {
namespace {
namespace Session = LiveRaceSession;
enum Phase { NO_MATCH, WAIT_OFFER, WAIT_READY, RUNNING, ROUND_DONE, MATCH_DONE, ROAMING, DRAFTING };
enum { OFFER = 1, READY = 2, CANCEL = 3, START = 4, NEW_MATCH = 5, CATALOGUE = 1 };
enum { DRAFT_BEGIN = 6, DRAFT_NEXT = 7, DRAFT_APPLY = 8, DRAFT_REQUEST = 9 };
struct Scene { u8 area, episode, parentArea, parentEpisode; };
struct Runtime {
    Session::Session session;
    LiveP2P::Punch punch;
    LiveP2P::Code own, friendCode;
    u32 openedMs, networkSeenMs, sentPoseMs, round, stageSeen, sceneEpoch, punchMs;
    Scene localScene, peerScene;
    u8 sceneObservations, localWins, peerWins;
    Phase phase;
    bool active, hosting, stunStarted, addressed, friendKnown, unreachable;
    bool started, connected, localReady, peerReady;
    // localReady is intent; startPrepared is the scene reservation sent to peers.
    bool startPrepared, groupReadySent;
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
static const char assisted[] = "Assisted - round void";
static const char tie[] = "Tie - ready again";
static const char roundWon[] = "Round won";
static const char roundLost[] = "Round lost";
static const char matchWon[] = "Match won - host sets up next";
static const char matchLost[] = "Match lost - host sets up next";
static const char freeRoam[] = "Free roam - host can set a race";
static const char applyingSetup[] = "Sharing the next setup";
static const char freeRoamScore[] = "Online free roam";
static const char ready[] = "Ready when you are";
static const char cancelled[] = "Round cancelled";
static const char startDeclined[] = "Start declined";
static const char finishAction[] = "Finish the current action first";
static const char pendingGhost[] = "Save or dismiss the ghost first";
static const char couldNotStart[] = "Could not start";
static const char raceLive[] = "Race live - first IL finish wins";
static const char requires60Hz[] = "Online requires 60 Hz";
#if IS_EMULATOR
static const char networkBusy[] = "Run the Dolphin companion, then retry";
static const char networkStarting[] = "Starting Dolphin companion network";
#else
static const char networkBusy[] = "Network busy or closing";
static const char networkStarting[] = "Starting Wii network";
#endif
static const char waitingIl[] = "Waiting for host's IL";
static const char defaultName[] = "Player";
static const char offline[] = "Offline";
static const char disconnected[] = "Disconnected";
static const char waitingReady[] = "Ready - waiting for opponent";
static const char waitingResult[] = "Finished - waiting for opponent";
#if IS_EMULATOR
static const char networkLost[] = "Dolphin companion unavailable - reconnect";
#else
static const char networkLost[] = "Wii network lost - reconnect";
#endif
static const char invalidSettings[] = "Invalid settings";
static const char peerLeft[] = "Opponent left";
static const char connectionLost[] = "Connection lost";
static const char starting[] = "Starting network";
static const char connected[] = "Connected";
static const char gettingAddress[] = "Getting your address...";
static const char noAddress[] = "No reply from address servers";
static const char noSend[] = "Nothing sent - see Diagnostics";
static const char waitingFriend[] = "Waiting for friend";
static const char shareCode[] = "Send your code, enter your friend's";
static const char enterCode[] = "Enter the host's code";
static const char connecting[] = "Connecting directly...";
static const char cantConnect[] = "Can't connect directly";
static const char badCode[] = "Code not valid - check it";
static const char needJoinerCode[] = "Host code - enter the joiner's";
static const char needHostCode[] = "Joiner code - enter the host's";
static const char ownCode[] = "That is your own code";
static const char roomFirst[] = "Create or join a room first";
static const char hintHost[] = "Send your code, enter theirs";
static const char hintJoin[] = "Enter the host's code, send yours";
static const char hintSymmetric[] = "Symmetric NAT - direct play fails";
static const char hintBlocked[] = "Check both codes; a firewall may block play";
static const char empty[] = "";
static const char scoreFormat[] = "Online  %u - %u   Best of %u";
static const char setScoreFormat[] = "Set %u - %u  |  IL %u - %u";
static const char draftBegin[] = "Preparing five ILs";
static const char draftHostBan[] = "Player 1: ban one IL";
static const char draftGuestBan[] = "Player 2: ban two ILs";
static const char draftHostPick[] = "Player 1: pick the IL";
static const char draftWinnerBan[] = "Winner: ban one IL";
static const char draftLoserPick[] = "Loser: counterpick";
static const char setWon[] = "Set won - host sets up next";
static const char setLost[] = "Set lost - host sets up next";
}
#pragma clang section rodata="" data="" bss=""
namespace Text2 {
static const char reconnecting[] = "Reconnecting...";
static const char stillTrying[] = "Still trying - check codes";
static const char opponentFormat[] = "Opponent: %lu:%02lu.%02lu";
}
// Prototype 19 state; the fixed Runtime layout above stays unchanged.
struct Extra {
    u32 keepaliveMs, lostMs, settledMs, firstAttemptMs, lastAttemptMs, attemptSerial;
    u8 draftBody[24];
    u8 draftBytes, lastOffer;
    bool reconnecting, attemptSeen, stunKeepalive, codeChanged, autoOpen, startResend, draftResend;
    bool draftWasTurn, draftOpen, networkRetry;
    u32 retryMs;
};
Extra x;
LiveGroup::Room sGroup;
LiveInvites::State sInvites;
Scene sGroupScenes[3];
bool sGroupSceneKnown[3];
char sGroupMessage[80];
LivePlaylist::Transfer sPlaylist;
u8 sPlaylistSent;
const char kSharingPlaylist[] = "Receiving the host's playlist";
const char kPlaylistLive[] = "Playlist race - advance independently";
Prefs sPrefs = {MODEL_SHADOW, false, false, 100, 320, 16};
#pragma clang section rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

u32 nowMs() { return static_cast<u32>(OSGetTime() / (OS_TIMER_CLOCK / 1000u)); }
bool sendControl(void *, const Session::Endpoint &to, const void *data, unsigned bytes) {
    const bool sent = LiveTransport::sendControl(to, data, bytes);
    if (sent) ++s.diagnostics.submitted;
    return sent;
}
bool sendPose(void *, const Session::Endpoint &to, const void *data, unsigned bytes) {
    const bool sent = LiveTransport::publishPose(to, data, bytes);
    if (sent) ++s.diagnostics.submitted;
    return sent;
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
void receiveVisual(unsigned channel, const MSRHeader &header, const MSRPose &pose, unsigned receivedMs) {
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
    if (LiveGhost::submitFor(channel, visual, header.sequence, pose.remoteMs, pose.sceneEpoch, receivedMs, &input)) {
        s.peerScene = scene;
        s.peerSceneKnown = true;
        sGroupScenes[channel] = scene; sGroupSceneKnown[channel] = true;
    }
}
void receivedPose(void *, const MSRHeader &header, const MSRPose &pose, unsigned receivedMs) {
    if (sGroup.active) LiveGroup::pose(sGroup, 0, header, pose, receivedMs);
    else receiveVisual(0, header, pose, receivedMs);
}
bool validOptions(const Options &value) {
    if (value.entry < 0 || value.entry >= ILing::count() ||
        value.episode >= 8 || !(value.bestOf == 1 || value.bestOf == 3 || value.bestOf == 5 || value.bestOf == 7) ||
        !value.name[0] || value.name[16] || value.pool > 2 || value.players == 1 || value.players > 4 ||
        (value.draft && (value.freeRoam || value.playlist || value.bestOf != 3)) ||
        (value.playlist && (value.freeRoam || value.bestOf != 1))) return false;
    for (unsigned i = 0; i < 16 && value.name[i]; ++i)
        if (static_cast<u8>(value.name[i]) < 0x20 || static_cast<u8>(value.name[i]) > 0x7e) return false;
    return true;
}
unsigned configPayload(u8 *body, unsigned type) {
    memset(body, 0, 12);
    body[0] = static_cast<u8>(type);
    body[1] = sOptions.episode; body[2] = sOptions.bestOf;
    body[3] = (type == READY && s.startPrepared ? 1u : 0u) | (sOptions.freeRoam ? 2u : 0u) |
        (sOptions.draft ? 4u : 0u) | (sOptions.setBo5 ? 8u : 0u) | (sOptions.pool << 4) | (sOptions.playlist ? 64u : 0u);
    MSRWrite16(body + 4, static_cast<u16>(sOptions.entry));
    MSRWrite16(body + 6, static_cast<u16>(ILing::persistentSlot(sOptions.entry)));
    MSRWrite32(body + 8, CATALOGUE);
    if (sOptions.playlist) MSRWrite32(body + 12, sOptions.playlistHash);
    return sOptions.playlist ? 16 : 12;
}
bool decodeConfig(const u8 *body, unsigned bytes, Options &options) {
    if ((bytes != 12 && bytes != 16) || MSRRead32(body + 8) != CATALOGUE || body[0] < OFFER || body[0] > NEW_MATCH ||
        (body[3] & ~127u) || (body[0] != READY && (body[3] & 1u))) return false;
    options = sOptions;
    options.entry = static_cast<int>(MSRRead16(body + 4));
    options.episode = body[1]; options.bestOf = body[2];
    options.freeRoam = (body[3] & 2u) != 0;
    options.draft = (body[3] & 4u) != 0;
    options.setBo5 = (body[3] & 8u) != 0;
    options.pool = (body[3] >> 4) & 3u;
    options.playlist = (body[3] & 64u) != 0;
    if (bytes != (options.playlist ? 16u : 12u)) return false;
    options.playlistHash = options.playlist ? MSRRead32(body + 12) : 0;
    return validOptions(options) && ILing::persistentSlot(options.entry) == static_cast<int>(MSRRead16(body + 6));
}
bool sameConfig(const Options &options) {
    return options.entry == sOptions.entry && options.episode == sOptions.episode &&
        options.bestOf == sOptions.bestOf && options.freeRoam == sOptions.freeRoam &&
        options.draft == sOptions.draft && options.setBo5 == sOptions.setBo5 && options.pool == sOptions.pool &&
        options.playlist == sOptions.playlist && options.playlistHash == sOptions.playlistHash;
}
void resetRound() {
    s.startPrepared = s.groupReadySent = false;
    sPlaylistSent = 0;
    if (!s.hosting) { sPlaylist.received = 0; sPlaylist.complete = false; }
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
            memcpy(x.draftBody, body, sizeof(body)); x.draftBytes = sizeof(body);
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
        if (Session::sendReliable(s.session, MSR_READY, body, sizeof(body), s.round)) {
            memcpy(x.draftBody, body, sizeof(body)); x.draftBytes = sizeof(body);
            adoptDraft(next);
        }
    }
}
bool canConfigureRace() {
    return s.connected && s.hosting && (s.phase == MATCH_DONE || s.phase == ROAMING) &&
        !s.newMatchNeeded && !s.offerNeeded && !Session::status(s.session).pending;
}
void abortRound(const char *message, bool notify) {
    s.startPrepared = s.groupReadySent = false;
    if (StageLoader::onlinePlaylistActive()) StageLoader::cancel();
    s.message = message;
    s.localReady = s.peerReady = false;
    s.phase = ROUND_DONE;
    s.cancelNeeded = notify;
    s.startNeeded = s.readyNeeded = false;
}
void settleRound() {
    if (s.phase == RUNNING && s.localResult && s.peerResult) {
        u8 winner = LiveDraft::NO_PLAYER;
        if ((!s.localEligible && s.localQf != MSR_FORFEIT_QF) ||
            (!s.peerEligible && s.peerQf != MSR_FORFEIT_QF)) {
            s.message = Text::assisted;
        } else if (s.localQf == s.peerQf) {
            s.message = Text::tie;
        } else if (s.peerQf == MSR_FORFEIT_QF ||
                   (s.localQf != MSR_FORFEIT_QF && s.localQf < s.peerQf)) {
            ++s.localWins; s.message = Text::roundWon;
            winner = s.hosting ? LiveDraft::PLAYER_ONE : LiveDraft::PLAYER_TWO;
        } else {
            ++s.peerWins; s.message = Text::roundLost;
            winner = s.hosting ? LiveDraft::PLAYER_TWO : LiveDraft::PLAYER_ONE;
        }
        s.localReady = s.peerReady = false;
        x.autoOpen = true; x.settledMs = nowMs();
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
void startRound();
void prepareStart();
LiveGroup::Config groupConfig() {
    LiveGroup::Config c = {};
    c.rules = LiveGroupRules::Config{sOptions.players, sOptions.bestOf,
        static_cast<u8>(sOptions.setBo5 ? 5 : 3), sOptions.draft, sOptions.freeRoam};
    c.entry = sOptions.entry; c.episode = sOptions.episode; c.pool = sOptions.pool;
    c.playlist = sOptions.playlist; c.playlistHash = sOptions.playlistHash; c.catalogue = CATALOGUE;
    return c;
}
bool groupValid(void *, unsigned entry, unsigned pool, bool draft) {
    return entry < static_cast<unsigned>(ILing::count()) && (!draft || ILing::onlinePoolContains(entry, pool));
}
bool groupCandidates(void *, unsigned short *out, unsigned count, unsigned pool) {
    if (pool != sOptions.pool || count < 4 || count > 5) return false;
    u16 candidates[5];
    if (!drawCandidates(candidates)) return false;
    memcpy(out, candidates, count * sizeof(*out)); return true;
}
bool groupStart(void *, const LiveGroup::Config &c, const LivePlaylist::Plan *plan) {
    if (!s.startPrepared) return false;
    sOptions.entry = c.entry;
    sOptions.episode = c.rules.draft ? ILing::onlineDefaultEpisode(c.entry) : c.episode;
    if (plan) { sPlaylist.plan = *plan; sPlaylist.complete = true; sPlaylist.hash = c.playlistHash; }
    s.round = sGroup.rules.round; s.phase = WAIT_READY;
    s.localResult = s.peerResult = s.resultSent = false;
    startRound();
    return s.phase == RUNNING;
}
void groupCancel(void *) { abortRound(Text::cancelled, false); }
void groupPose(void *, unsigned player, const MSRHeader &h, const MSRPose &p, unsigned now) {
    const unsigned slot = LiveGroup::remoteSlot(sGroup, player);
    if (slot < LiveGhost::Channels) receiveVisual(slot, h, p, now);
}
void groupResetPose(void *, unsigned player) {
    const unsigned slot = LiveGroup::remoteSlot(sGroup, player);
    LiveGhost::resetFor(slot);
    if (slot < 3) sGroupSceneKnown[slot] = false;
}
const LiveGroup::Hooks kGroupHooks = {nullptr, groupValid, groupCandidates, groupStart, groupCancel, groupPose, groupResetPose};
void adoptGroupOptions() {
    const auto &c = sGroup.config;
    sOptions.players = c.rules.players; sOptions.bestOf = c.rules.bestOf;
    sOptions.setBo5 = c.rules.setBestOf == 5; sOptions.draft = c.rules.draft; sOptions.freeRoam = c.rules.freeRoam;
    sOptions.pool = c.pool; sOptions.playlist = c.playlist; sOptions.playlistHash = c.playlistHash;
    sOptions.entry = c.entry; sOptions.episode = c.episode;
}
void serviceGroup(u32 now) {
    namespace R = LiveGroupRules;
    // User intent can survive loading; only a reserved scene is sent as Ready.
    if (sGroup.rules.phase == R::Ready) {
        s.phase = WAIT_READY;
        prepareStart();
        if (s.startPrepared != s.groupReadySent && LiveGroup::ready(sGroup, s.startPrepared))
            s.groupReadySent = s.startPrepared;
    }
    if (sOptions.playlist && s.phase == RUNNING && !s.localResult && !StageLoader::onlinePlaylistActive()) LiveGroup::cancel(sGroup);
    if (s.localResult && !s.resultSent && LiveGroup::result(sGroup, s.localQf, s.localEligible)) s.resultSent = true;
    LiveGroup::tick(sGroup, now);
    if (sGroup.host) {
        for (unsigned i = 0; i < sInvites.count; ++i) {
            const auto &peer = i ? sGroup.extra[i - 1].info : s.session.info;
            if (peer.connected) LiveInvites::connected(sInvites, peer.peer);
        }
    }
    const R::State &r = sGroup.rules;
    if (sGroup.outcomeChanged) { x.autoOpen = true; x.settledMs = now; sGroup.outcomeChanged = false; }
    s.phase = r.phase == R::Racing ? RUNNING : r.phase == R::Results ? ROUND_DONE :
        r.phase == R::Finished ? MATCH_DONE : r.phase == R::Roaming ? ROAMING :
        r.phase == R::Ready ? WAIT_READY : DRAFTING;
    if (r.phase != R::Ready) s.localReady = s.startPrepared = s.groupReadySent = false;
    s.peerReady = r.readyMask == ((1u << r.config.players) - 1u);
    s.round = r.round;
    sOptions.entry = r.selected;
    if (r.config.draft) sOptions.episode = ILing::onlineDefaultEpisode(r.selected);
    if (!sGroup.host && sGroup.playlist.complete) sPlaylist = sGroup.playlist;
    for (unsigned player = 0; player < r.config.players; ++player) {
        if (player == sGroup.self) continue;
        const char *name = sGroup.members[player].name;
        LiveGhost::setNameFor(LiveGroup::remoteSlot(sGroup, player), name, strlen(name));
    }
    const unsigned joined = LiveGroup::connectedCount(sGroup);
    if (joined < r.config.players) snprintf(sGroupMessage, sizeof(sGroupMessage), "Waiting for players: %u / %u", joined, r.config.players);
    else if (r.phase == R::Draft) snprintf(sGroupMessage, sizeof(sGroupMessage), "%s: ban one IL", sGroup.members[R::actor(r)].name);
    else if (r.phase == R::NeedCandidates) strcpy(sGroupMessage, "Preparing the next IL draft");
    else if (r.phase == R::Roaming) strcpy(sGroupMessage, Text::freeRoam);
    else if (r.phase == R::Ready) strcpy(sGroupMessage, s.localReady ?
        (s.startPrepared ? "Waiting for all players to be warp-ready" : "Ready - waiting for a safe stage") : Text::ready);
    else if (r.phase == R::Racing) strcpy(sGroupMessage, s.localResult ? "Finished - waiting for the group" : sOptions.playlist ? kPlaylistLive : Text::raceLive);
    else if (r.winner < r.config.players) snprintf(sGroupMessage, sizeof(sGroupMessage), "%s won%s", sGroup.members[r.winner].name, r.phase == R::Finished ? " - host sets up next" : " the round");
    else strcpy(sGroupMessage, r.eligibleMask == ((1u << r.config.players) - 1) ? Text::tie : Text::cancelled);
    s.message = sGroupMessage;
}
__attribute__((noinline)) void receivedControlBody(const MSRHeader &header, const void *data, unsigned bytes) {
    const u8 *body = static_cast<const u8 *>(data);
    if (!s.hosting && header.kind == MSR_READY && bytes == 28 && body[0] == LiveGroup::Welcome) {
        if (header.round == MSRRead32(body + 16) && LiveGroup::adopt(sGroup, s.session, groupConfig(), kGroupHooks, body, bytes)) {
            adoptGroupOptions(); LiveGhost::resetAll(); memset(sGroupSceneKnown, 0, sizeof(sGroupSceneKnown));
        }
        return;
    }
    if (sGroup.active) { LiveGroup::control(sGroup, 0, header, data, bytes); return; }
    if (header.kind == MSR_READY && bytes && body[0] == LivePlaylist::Message) {
        if (!s.hosting && sOptions.playlist && s.phase == WAIT_READY && header.round == s.round) {
            if (LivePlaylist::receive(sPlaylist, body, bytes, sOptions.playlistHash, ILing::count()) && sPlaylist.complete)
                s.message = Text::ready;
        }
        return;
    }
    if (header.kind == MSR_READY && bytes && body[0] >= DRAFT_BEGIN) {
        receivedDraft(header, body, bytes);
        return;
    }
    if (header.kind == MSR_RESULT) {
        if ((s.phase != RUNNING && !(s.phase == WAIT_READY && s.startNeeded)) ||
            header.round != s.round || s.peerResult || bytes != 8 ||
            body[4] > 2 || body[5] || body[6] || body[7]) return;
        const u32 qf = MSRRead32(body);
        if (body[4] == 1 ? qf > 0x7fffffffu : qf != (body[4] == 2 ? 0xfffffffeu : 0xffffffffu)) return;
        s.peerQf = static_cast<s32>(qf);
        s.peerEligible = body[4] == 1; s.peerResult = true;
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
        sOptions.playlist = proposed.playlist; sOptions.playlistHash = proposed.playlistHash;
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
        if (sOptions.playlist) s.message = kSharingPlaylist;
        return;
    }
    if (!sameConfig(proposed) || header.round != s.round) return;
    if (header.kind == MSR_READY && body[0] == CANCEL &&
        (s.phase == WAIT_READY || s.phase == RUNNING || s.phase == ROUND_DONE)) {
        abortRound(Text::cancelled, false);
    } else if (header.kind == MSR_READY && body[0] == READY && s.phase == WAIT_READY) {
        s.peerReady = (body[3] & 1u) != 0;
    } else if (header.kind == MSR_START && body[0] == START && !s.hosting && s.phase == WAIT_READY) {
        if (s.startPrepared) s.startNeeded = true;
        else abortRound(Text::startDeclined, true);
    }
}
void receivedControl(void *, const MSRHeader &header, const void *data, unsigned bytes) {
    receivedControlBody(header, data, bytes);
}
const Session::Callbacks kCallbacks = {nullptr, sendControl, sendPose, receivedPose, receivedControl};

bool safeToStart() {
    if (!LevelWarp::readyForOnlineRace()) {
        s.message = "Ready - waiting for a safe stage";
        return false;
    }
    if (sOptions.playlist && (!sPlaylist.complete || sPlaylist.hash != sOptions.playlistHash)) {
        s.message = kSharingPlaylist;
        return false;
    }
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
void prepareStart() {
    if (s.phase != WAIT_READY || !s.localReady || s.startPrepared) return;
    if (!safeToStart() || (gMenu && !gMenu->openOnline())) return;
    // Main holds the director and Online owns input before this ACK can leave.
    s.startPrepared = true;
    s.readyNeeded = true;
    s.message = "Waiting for all players to be warp-ready";
}
void startRound() {
    s.startNeeded = false;
    // Online round clock: wall time between attempt starts, read-only beside QFT.
    x.attemptSerial = gQFTTimer.attemptSerial(); x.attemptSeen = false;
    if (s.phase != WAIT_READY || !s.startPrepared) {
        abortRound(Text::startDeclined, true);
        return;
    }
    if (!safeToStart() || !(sOptions.playlist ? StageLoader::startOnlinePlaylist(sPlaylist.plan) :
                           ILing::startOnline(sOptions.entry, sOptions.episode))) {
        abortRound(Text::couldNotStart, true);
        return;
    }
    s.phase = RUNNING;
    s.startPrepared = false;
    s.localResult = s.resultSent = false;
    s.message = sOptions.playlist ? kPlaylistLive : Text::raceLive;
    if (gMenu) gMenu->hide();
}
bool queueConfig(unsigned kind, unsigned type) {
    u8 body[16]; const unsigned bytes = configPayload(body, type);
    return Session::sendReliable(s.session, kind, body, bytes, s.round);
}
void serviceRace() {
    prepareStart();
    if (sOptions.playlist && s.phase == RUNNING && !s.localResult && !StageLoader::onlinePlaylistActive())
        abortRound(Text::cancelled, true);
    settleRound();
    if (Session::status(s.session).pending) return;
    if (x.startResend) {
        if (s.phase != RUNNING || queueConfig(MSR_START, START)) x.startResend = false;
    } else if (x.draftResend) {
        if (s.phase != DRAFTING ||
            Session::sendReliable(s.session, MSR_READY, x.draftBody, x.draftBytes, s.round)) x.draftResend = false;
    } else if (s.cancelNeeded) {
        if (queueConfig(MSR_READY, CANCEL)) s.cancelNeeded = false;
    } else if (s.localResult && !s.resultSent) {
        u8 body[8] = {};
        MSRWrite32(body, s.localEligible || s.localQf == MSR_FORFEIT_QF ? static_cast<u32>(s.localQf) : 0xffffffffu);
        body[4] = s.localQf == MSR_FORFEIT_QF ? 2 : s.localEligible;
        if (Session::sendReliable(s.session, MSR_RESULT, body, sizeof(body), s.round)) s.resultSent = true;
    } else if (s.hosting && s.newMatchNeeded) {
        u8 body[16]; const unsigned bytes = configPayload(body, NEW_MATCH);
        // Keep the round generation monotonic across matches to reject stale results.
        if (Session::sendReliable(s.session, MSR_READY, body, bytes, s.round + 1u)) {
            ++s.round; x.lastOffer = NEW_MATCH; s.localWins = s.peerWins = 0; s.newMatchNeeded = false;
            s.draft = {}; s.choiceNeeded = s.choiceSent = false;
            resetRound();
            s.message = s.phase == ROAMING ? Text::freeRoam : s.phase == DRAFTING ? Text::draftBegin : Text::ready;
        }
    } else if (s.hosting && (s.offerNeeded || s.phase == ROUND_DONE)) {
        if (!s.offerNeeded) {
            ++s.round; resetRound(); s.offerNeeded = true; x.lastOffer = OFFER;
        }
        if (queueConfig(MSR_READY, x.lastOffer == NEW_MATCH ? NEW_MATCH : OFFER)) {
            s.offerNeeded = false;
            if (!x.lastOffer) x.lastOffer = OFFER;
        }
    } else if (s.hosting && sOptions.playlist && s.phase == WAIT_READY && sPlaylistSent < sPlaylist.plan.count) {
        u8 body[60];
        const unsigned bytes = LivePlaylist::encode(sPlaylist.plan, sPlaylistSent, body);
        if (bytes && Session::sendReliable(s.session, MSR_READY, body, bytes, s.round)) sPlaylistSent += body[2];
    } else if (s.phase == DRAFTING) {
        serviceDraft();
    } else if (s.readyNeeded) {
        if (queueConfig(MSR_READY, READY)) s.readyNeeded = false;
    } else if (s.hosting && s.phase == WAIT_READY && s.startPrepared && s.peerReady) {
        if (queueConfig(MSR_START, START)) startRound();
    } else if (!s.hosting && s.startNeeded) {
        startRound();
    }
}
// Read-only: notes the wall time when QFT starts a new attempt in this round.
void sampleAttempt(u32 now) {
    const u32 serial = gQFTTimer.attemptSerial();
    if (s.phase != RUNNING || x.attemptSerial == serial) return;
    x.attemptSerial = serial;
    if (!x.attemptSeen) x.firstAttemptMs = now;
    x.lastAttemptMs = now; x.attemptSeen = true;
}
bool begin(bool hosting) {
    if (s.active || !validOptions(sOptions)) return false;
    if (hosting && sOptions.playlist && !sPlaylist.complete) { s.message = kSharingPlaylist; return false; }
    if (VIGetTvFormat() == VI_PAL) { s.message = Text::requires60Hz; return false; }
    if (!LiveTransport::begin(LOCAL_PORT)) { s.message = Text::networkBusy; return false; }
    s = {}; x = {}; sGroup = {}; sInvites = {};
    memset(sGroupSceneKnown, 0, sizeof(sGroupSceneKnown));
    s.active = true; s.hosting = hosting; s.openedMs = nowMs();
    s.diagnostics.net = NET_WAITING;
    s.networkSeenMs = s.openedMs;
    s.message = Text::networkStarting;
    LiveGhost::resetAll();
    return true;
}
void updatePose(u32 now) {
    Ghost::VisualState visual;
    Scene scene;
    const bool valid = Ghost::captureLiveVisual(&visual) && captureScene(scene);
    if (s.stageSeen != sStageMarker) {
        s.stageSeen = sStageMarker; ++s.sceneEpoch; s.sceneObservations = 0;
        LiveGhost::resetAll();
        const auto info = Session::status(s.session);
        unsigned length = 0; while (length < 16 && info.remoteName[length]) ++length;
        LiveGhost::setName(info.remoteName, length);
    }
    if (!valid) s.sceneObservations = 0;
    else if (!s.sceneObservations || !sameScene(scene, s.localScene)) {
        s.localScene = scene; s.sceneObservations = 1; ++s.sceneEpoch;
    } else if (s.sceneObservations < 3) ++s.sceneObservations;
    const bool stable = valid && s.sceneObservations >= 3;
    if (sGroup.active) {
        for (unsigned i = 0; i < sGroup.config.rules.players - 1u; ++i)
            LiveGhost::tickFor(i, now, stable && sGroupSceneKnown[i] && sameScene(s.localScene, sGroupScenes[i]));
    } else LiveGhost::tick(now, stable && s.peerSceneKnown && sameScene(s.localScene, s.peerScene));
    // Twenty snapshots per second leave IOS headroom for room traffic.
    if (now - s.sentPoseMs < 48u) return;
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
    if (!sGroup.active && PracticeSession::consumedInput(&input) && !input.error) {
        pose.buttons = input.buttons & MSR_INPUT_BUTTON_MASK;
        pose.stickX = input.stickX; pose.stickY = input.stickY;
        pose.substickX = input.substickX; pose.substickY = input.substickY;
        pose.triggerL = input.triggerL; pose.triggerR = input.triggerR;
    }
    if (sGroup.active) LiveGroup::localPose(sGroup, pose, now);
    else Session::publishPose(s.session, pose, s.round);
}
void acceptConnection() {
    const auto connection = Session::status(s.session);
    if (s.connected || !connection.connected) return;
    s.connected = true;
    if (s.hosting) LiveInvites::connected(sInvites, connection.peer);
    if (sGroup.active) { x.reconnecting = false; return; }
    if (x.reconnecting) {
        // Same room, same round: resend what may have been lost with the old link.
        x.reconnecting = false;
        s.message = Text::connected;
        if (s.localResult) s.resultSent = false;
        s.readyNeeded = s.phase == WAIT_READY;
        if (s.choiceSent) { s.choiceSent = false; s.choiceNeeded = true; }
        if (s.hosting) {
            if (sOptions.playlist) sPlaylistSent = 0;
            s.offerNeeded = x.lastOffer && s.phase != ROUND_DONE;
            x.draftResend = s.phase == DRAFTING && x.draftBytes;
            x.startResend = s.phase == RUNNING;
        }
        return;
    }
    s.round = 1;
    if (s.hosting) resetRound();
    else s.phase = WAIT_OFFER;
    s.offerNeeded = s.hosting;
    s.message = s.hosting ? (sOptions.freeRoam ? Text::freeRoam : sOptions.draft ? Text::draftBegin : Text::ready) : Text::waitingIl;
    unsigned length = 0; while (length < 16 && connection.remoteName[length]) ++length;
    LiveGhost::setName(connection.remoteName, length);
}
bool startSession(u32 now) {
    if (sGroup.active && !s.hosting) {
        LiveGhost::resetAll();
        memset(sGroupSceneKnown, 0, sizeof(sGroupSceneKnown));
    }
    Session::Config config = {};
    memcpy(config.name, sOptions.name, 16);
    const u64 stamp = OSGetTime();
    config.nonceHigh = static_cast<u32>(stamp >> 32) ^ 0x4d535231u;
    config.nonceLow = static_cast<u32>(stamp) | 1u;
    // The host's room secret is the PIN for every player in the room.
    config.pin = s.hosting ? s.own.secret : s.friendCode.secret;
    config.region = SUSAMUNE_GAME_VERSION - 1;
    config.timing = MSR_TIMING_60HZ;
    // receive() admits only endpoints from the host's current guest slots.
    const Session::Endpoint anyone = sGroup.active && sGroup.host && sGroup.welcomedMask & 2u ? s.session.info.peer : Session::Endpoint{};
    s.started = Session::init(s.session, config, kCallbacks) &&
        (s.hosting ? Session::startHost(s.session, anyone, now) :
                     Session::startGuest(s.session, s.friendCode.endpoint, now));
    if (s.started && s.hosting && sOptions.players > 2 && !sGroup.active) {
        s.started = LiveGroup::host(sGroup, s.session, groupConfig(), sOptions.playlist ? &sPlaylist.plan : nullptr, kGroupHooks, 1);

    }
    return s.started;
}
// Starts punching once both this player's address and the friend's code are known.
void usePeer(u32 now) {
    if (!s.addressed || !s.friendKnown) return;
    s.punchMs = now; s.unreachable = false;
    s.message = Text::connecting;
    if (s.hosting) {
        LiveP2P::reset(s.punch, s.own.secret, LiveP2P::HOST);
        LiveP2P::add(s.punch, s.friendCode.endpoint, LiveP2P::JOINER);
        return;
    }
    LiveP2P::reset(s.punch, s.friendCode.secret, LiveP2P::JOINER);
    LiveP2P::add(s.punch, s.friendCode.endpoint, LiveP2P::HOST);
    Session::stop(s.session);
    if (!startSession(now)) { s.unreachable = true; s.message = Text::invalidSettings; }
}
u32 freshSecret();
#if !IS_EMULATOR
SusamuneOnlineNameCfg *savedName();
#endif
u32 today() { return static_cast<u32>(OSGetTime() / (OS_TIMER_CLOCK * 86400ull)); }
// The room secret is kept per console so its code stays the same between
// sessions; it is replaced after about 90 days, but never on a clock that is
// unset or earlier than the day it was made.
u32 roomSecret() {
#if !IS_EMULATOR
    SusamuneOnlineNameCfg *saved = savedName();
    if (saved) {
        DCInvalidateRange(saved, sizeof(*saved));
        bool changed = false;
        const u32 day = today();
        const bool clock = day >= 9000u && day < 65535u;  // 2024 or later
        if (!saved->secret || saved->secret > LiveP2P::SECRET_MAX ||
            (clock && saved->secretDay && day >= saved->secretDay + 90u)) {
            x.codeChanged = saved->secret != 0;
            saved->secret = static_cast<u16>(freshSecret());
            saved->secretDay = clock ? static_cast<u16>(day) : 0;
            changed = true;
        } else if (!saved->secretDay && clock) {
            saved->secretDay = static_cast<u16>(day); changed = true;
        }
        u8 last[6];
        memcpy(last, s.own.endpoint.ip, 4);
        last[4] = static_cast<u8>(s.own.endpoint.port >> 8); last[5] = static_cast<u8>(s.own.endpoint.port);
        if (memcmp(saved->last, last, 6)) {
            if (saved->last[0]) x.codeChanged = true;
            memcpy(saved->last, last, 6); changed = true;
        }
        if (changed) {
            // The kernel sets the block magic on every boot; the name may stay empty.
            DCStoreRange(saved, sizeof(*saved));
            gSettings.markDirty();
        }
        return saved->secret;
    }
#endif
    return freshSecret();
}
u32 freshSecret() {
    const u64 stamp = OSGetTime();
    u32 mix = static_cast<u32>(stamp) ^ static_cast<u32>(stamp >> 32) * 0x9e3779b1u ^ OSGetTick();
    mix ^= mix >> 15; mix *= 0x2c1b3c6du; mix ^= mix >> 12;
    return mix % LiveP2P::SECRET_MAX + 1;
}

#if !IS_EMULATOR
// The name lives in susamune.ini (creation section, "online_name"); a kernel
// without the block leaves the flag clear and the name is simply not kept.
SusamuneOnlineNameCfg *savedName() {
    const volatile SusamuneCfg *cfg = SUSAMUNE_CFG_PPC_PTR;
    return cfg->magic == SUSAMUNE_CFG_MAGIC && (cfg->flags & SUSAMUNE_ONLINE_NAME_FLAG) ?
        SUSAMUNE_ONLINE_NAME_PPC_PTR : nullptr;
}
#endif
}

void init() {
    s = {}; sOptions = {}; sStageMarker = 0; x = {}; sGroup = {};
    memcpy(sOptions.name, Text::defaultName, 7);
    sOptions.bestOf = 3;
    sOptions.players = 2;
#if !IS_EMULATOR
    if (SusamuneOnlineNameCfg *saved = savedName()) {
        DCInvalidateRange(saved, sizeof(*saved));
        Options loaded = sOptions;
        memcpy(loaded.name, saved->name, 16);
        if (saved->magic == SUSAMUNE_ONLINE_NAME_MAGIC && validOptions(loaded)) sOptions = loaded;
        // Older ini files leave these zero: Shadow Mario, opponent and score shown.
        sPrefs.model = saved->model < MODEL_COUNT ? saved->model : MODEL_SHADOW;
        sPrefs.hideOpponent = saved->flags & SUSAMUNE_ONLINE_HIDE_OPPONENT;
        sPrefs.hideScore = (saved->flags & SUSAMUNE_ONLINE_HIDE_SCORE) != 0;
        if (saved->scoreScale) {
            sPrefs.scoreScale = saved->scoreScale; sPrefs.scoreX = saved->scoreX; sPrefs.scoreY = saved->scoreY;
        }
    }
#endif
    s.message = Text::offline;
    LiveGhost::reset();
}
const Options &options() { return sOptions; }
bool configure(const Options &options) {
    if (!validOptions(options)) return false;
    if (s.active) {
        if (!canConfigureRace()) return false;
        if (options.players != sOptions.players) return false;
        for (unsigned i = 0; i < 17; ++i) if (options.name[i] != sOptions.name[i]) return false;
    }
    if (options.playlist) {
        LivePlaylist::Plan plan;
        if (!StageLoader::copyOnlinePlaylist(&plan)) return false;
        sPlaylist.plan = plan; sPlaylist.hash = LivePlaylist::hash(plan);
        sPlaylist.complete = true; sPlaylist.received = plan.count; sPlaylistSent = 0;
    }
    sOptions = options;
    sOptions.playlistHash = sOptions.playlist ? sPlaylist.hash : 0;
    if (sOptions.playlist) { sOptions.entry = sPlaylist.plan.items[0].entry; sOptions.episode = sPlaylist.plan.items[0].episode & 7u; }
    bool ended = false;
    for (unsigned i = 0; i < sizeof(sOptions.name); ++i) {
        if (!sOptions.name[i]) ended = true;
        if (ended) sOptions.name[i] = 0;
    }
#if !IS_EMULATOR
    // Saved with the other settings when the menu closes.
    SusamuneOnlineNameCfg *saved = savedName();
    if (saved && memcmp(saved->name, sOptions.name, sizeof(sOptions.name))) {
        memcpy(saved->name, sOptions.name, sizeof(sOptions.name));
        saved->magic = SUSAMUNE_ONLINE_NAME_MAGIC;
        DCStoreRange(saved, sizeof(*saved));
        gSettings.markDirty();
    }
#endif
    return true;
}
bool host() { return begin(true); }
bool join() { return begin(false); }
const char *guestName(unsigned slot) {
    if (!s.active || !s.hosting || slot >= sInvites.count) return nullptr;
    if (!sGroup.active) return s.session.info.connected ? s.session.info.remoteName : nullptr;
    const auto &endpoint = sInvites.slots[slot].punch.peers[0].endpoint;
    for (unsigned i = 0; i < sInvites.count; ++i) {
        const auto &peer = i ? sGroup.extra[i - 1].info : s.session.info;
        if (peer.connected && !memcmp(&endpoint, &peer.peer, sizeof(endpoint))) return peer.remoteName;
    }
    return nullptr;
}
bool guestCode(unsigned slot, char *out) {
    out[0] = 0;
    char code[LiveP2P::CODE_CHARS + 1];
    if (!s.active || !s.hosting || slot >= sInvites.count ||
        !LiveP2P::encode(sInvites.slots[slot].code, code)) return false;
    LiveP2P::format(code, out);
    return true;
}
const char *enterGuestCode(unsigned slot, const char *text) {
    if (!s.active || !s.hosting) return Text::roomFirst;
    if (!s.addressed) return Text::gettingAddress;
    if (slot >= sInvites.count) return Text::badCode;
    if (guestName(slot)) return "This guest is already connected";
    LiveP2P::Code code;
    if (!LiveP2P::decode(text, &code)) return Text::badCode;
    if (!memcmp(&code.endpoint, &s.own.endpoint, sizeof(code.endpoint))) return Text::ownCode;
    const auto previous = sInvites.slots[slot].punch.peers[0].endpoint;
    if (!LiveInvites::set(sInvites, slot, code)) return "That guest is in another slot";
    if (sGroup.active) LiveGroup::replacePeer(sGroup, previous, code.endpoint, nowMs());
    s.friendCode = code; s.friendKnown = true; s.punchMs = nowMs(); s.unreachable = false;
    return nullptr;
}
bool kickGuest(unsigned slot) {
    if (!s.active || !s.hosting || slot >= sInvites.count ||
        !sInvites.slots[slot].punch.peers[0].state) return false;
    const auto endpoint = sInvites.slots[slot].punch.peers[0].endpoint;
    LiveInvites::clear(sInvites, slot);
    if (sGroup.active) LiveGroup::kickPeer(sGroup, endpoint);
    else {
        Session::kick(s.session); s.connected = false;
        s.friendKnown = x.reconnecting = false;
        LiveGhost::resetAll();
        if (s.phase == RUNNING || s.phase == WAIT_READY) abortRound(Text::cancelled, false);
    }
    return true;
}
const char *enterCode(const char *text) {
    if (s.active && s.hosting) return enterGuestCode(0, text);
    LiveP2P::Code code;
    if (!s.active || (s.connected && !(sGroup.active && sGroup.host))) return Text::roomFirst;
    if (sGroup.active && sGroup.host) return "Choose a guest code slot";
    if (!LiveP2P::decode(text, &code)) return Text::badCode;
    if (s.addressed && code.secret == s.own.secret &&
        !memcmp(&code.endpoint, &s.own.endpoint, sizeof(code.endpoint))) return Text::ownCode;
    s.friendCode = code; s.friendKnown = true;
#if !IS_EMULATOR
    if (SusamuneOnlineNameCfg *saved = savedName()) {
        u8 *f = saved->friendCode;
        memcpy(f, code.endpoint.ip, 4);
        f[4] = static_cast<u8>(code.endpoint.port >> 8); f[5] = static_cast<u8>(code.endpoint.port);
        f[6] = static_cast<u8>(code.secret >> 8); f[7] = static_cast<u8>(code.secret);
        DCStoreRange(saved, sizeof(*saved));
        gSettings.markDirty();
    }
#endif
    usePeer(nowMs());
    return nullptr;
}
void disconnect() {
    s.startPrepared = s.groupReadySent = false;
    x.reconnecting = x.networkRetry = false;
    if (StageLoader::onlinePlaylistActive()) StageLoader::cancel();
    LiveGroup::stop(sGroup);
    Session::stop(s.session); LiveStun::cancel(); LiveTransport::stop(); LiveGhost::resetAll();
    s.active = s.connected = false; s.phase = NO_MATCH;
    s.message = Text::disconnected;
}
bool ready() {
    if (sGroup.active) {
        if (sGroup.rules.phase != LiveGroupRules::Ready) return false;
        s.localReady = !s.localReady;
        if (!s.localReady) s.startPrepared = false;
        return true;
    }
    if (!s.connected || s.phase != WAIT_READY) return false;
    s.localReady = !s.localReady; s.readyNeeded = true;
    if (!s.localReady) s.startPrepared = false;
    if (!s.localReady && s.startNeeded) {
        abortRound(Text::startDeclined, true);
        return true;
    }
    s.message = s.localReady ? Text::waitingReady : Text::ready;
    return true;
}
bool forfeit() {
    if (!s.active || s.phase != RUNNING || s.localResult) return false;
    s.localQf = MSR_FORFEIT_QF; s.localEligible = false;
    s.localResult = true;
    s.message = "Forfeited - waiting for other racers";
    if (StageLoader::onlinePlaylistActive()) StageLoader::cancel();
    return true;
}
bool holdingStart() { return s.active && s.startPrepared; }
bool racingEntry(int entry) {
    return s.active && (s.connected || x.reconnecting) && s.phase == RUNNING &&
        !s.localResult && !sOptions.playlist && entry == sOptions.entry;
}
bool newMatch() {
    if (sGroup.active) return LiveGroup::configure(sGroup, groupConfig(), sOptions.playlist ? &sPlaylist.plan : nullptr);
    if (!canConfigureRace() || s.round == ~0u) return false;
    s.newMatchNeeded = true;
    s.message = Text::applyingSetup;
    return true;
}
bool chooseDraft(unsigned candidate) {
    if (sGroup.active) return LiveGroup::ban(sGroup, candidate);
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
unsigned playlistCount() { return sOptions.playlist && sPlaylist.complete ? sPlaylist.plan.count : 0; }
const LiveGroupRules::State *groupState() { return sGroup.active ? &sGroup.rules : nullptr; }
unsigned groupPlayer() { return sGroup.self; }
const char *playerName(unsigned player) { return sGroup.active && player < sGroup.config.rules.players ? sGroup.members[player].name : Text::empty; }
unsigned playersConnected() { return sGroup.active ? LiveGroup::connectedCount(sGroup) : s.connected ? 2 : s.active ? 1 : 0; }
void onPlaylistResult(s32 qf, bool eligible) {
    if (!sOptions.playlist || s.phase != RUNNING || s.localResult) return;
    s.localQf = qf; s.localEligible = eligible && qf >= 0;
    s.localResult = true; s.message = Text::waitingResult;
}
void onILResult(int entry, s32 qf, bool eligible) {
    if (sOptions.playlist) return;
    if (!(s.connected || x.reconnecting) || s.phase != RUNNING || s.localResult || entry != sOptions.entry) return;
    // Resets, deaths and loads keep the round clock running: add the wall time
    // from the first attempt of the round to the start of this one.
    if (x.attemptSeen && qf >= 0) {
        // A QF is 1001/120 ms (4 per 29.97 fps game frame); u32 holds about 9.9 hours.
        qf += static_cast<s32>((x.lastAttemptMs - x.firstAttemptMs) * 120u / 1001u);
    }
    s.localQf = qf; s.localEligible = eligible && qf >= 0;
    s.localResult = true;
    s.message = Text::waitingResult;
}
static void serviceAutoOpen() {
    const bool turn = s.connected && s.phase == DRAFTING && (sGroup.active ?
        LiveGroupRules::actor(sGroup.rules) == sGroup.self :
        LiveDraft::currentActor(s.draft) == (s.hosting ? LiveDraft::PLAYER_ONE : LiveDraft::PLAYER_TWO));
    if (turn && !x.draftWasTurn) x.draftOpen = true;
    if (!turn) x.draftOpen = false;
    x.draftWasTurn = turn;
    const bool result = x.autoOpen && nowMs() - x.settledMs >= 2000u;
    // Retry after a load/editor closes; B must not reopen the same turn forever.
    if (!gMenu || (!x.draftOpen && !result) || !s.connected || s.phase == RUNNING ||
        StageLoader::active() || !LevelWarp::readyForOnlineRace()) return;
    if (gMenu->openOnline()) x.autoOpen = x.draftOpen = false;
}
void update() {
    LiveStun::update();
    if (!s.active) return;
    const u32 now = nowMs();
    const auto transport = LiveTransport::poll();
    if (x.networkRetry) {
        if (now - x.retryMs < 2000u) return;
        if (transport.state == TW_LIVE_IDLE && LiveTransport::begin(LOCAL_PORT)) {
            x.networkRetry = false;
            s.openedMs = s.networkSeenMs = now;
        } else {
            x.retryMs = now;
            LiveTransport::stop();
        }
        return;
    }
    // A concurrent ARM publication can leave this one bounded read unavailable.
    if (transport.state == TW_LIVE_UNAVAILABLE && now - s.networkSeenMs < 15000u) return;
    Diagnostics &d = s.diagnostics;
    if (d.net != NET_UP) {
        // The worker gets an address from DHCP before it reports READY; that can take seconds.
        const u32 waited = (now - s.openedMs) / 1000u;
        d.waitedS = static_cast<u8>(waited > 255u ? 255u : waited);
    }
    if (transport.state == TW_LIVE_READY) {
        s.networkSeenMs = now;
        d.forwarded = static_cast<u8>(transport.txRead > 255u ? 255u : transport.txRead);
        LiveTransport::Endpoint local;
        if (!d.port && LiveTransport::localEndpoint(&local)) {
            memcpy(d.ip, local.ip, 4); d.port = local.port;
        }
        d.net = NET_UP;
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
    if (transport.state == TW_LIVE_FAILED || (s.stunStarted && transport.state != TW_LIVE_READY) ||
        (!s.stunStarted && now - s.openedMs > 30000u)) {
        // A transport restart must not destroy the room, invitations or scores.
        LiveStun::cancel(); LiveTransport::stop();
        s.connected = s.stunStarted = s.localReady = s.peerReady = s.startPrepared = s.groupReadySent = false;
        x.stunKeepalive = false; x.networkRetry = x.reconnecting = true; x.retryMs = now;
        d.net = NET_FAILED; d.trouble = true; s.message = Text2::reconnecting; return;
    }
    if (!s.stunStarted) {
        if (transport.state != TW_LIVE_READY) return;
        // STUN shares the race socket, so the address it learns is the one peers punch.
        if (!LiveStun::startShared()) { s.message = Text::networkBusy; return; }
        s.stunStarted = true;
        x.stunKeepalive = s.addressed;
        s.message = Text::gettingAddress;
    }
    LiveTransport::Packet packet;
    for (unsigned i = 0; i < 4 && LiveTransport::receive(packet); ++i) {
        ++s.diagnostics.received;
        if (LiveStun::accept(packet) ||
            (s.hosting ? LiveInvites::receive(sInvites, packet.endpoint, packet.data, packet.bytes, now) :
                LiveP2P::receive(s.punch, packet.endpoint, packet.data, packet.bytes, now, s.hosting && !s.connected)) ||
            ((!s.hosting || packet.bytes < MSR_HEADER_BYTES || packet.data[6] != MSR_HELLO ||
              LiveInvites::permits(sInvites, packet.endpoint)) &&
             (sGroup.active && sGroup.host ? LiveGroup::receive(sGroup, packet.endpoint, packet.data, packet.bytes, now) :
                (s.started && Session::receivePacket(s.session, packet.endpoint, packet.data, packet.bytes, now)))))
            ++s.diagnostics.accepted;
    }
    if (!s.addressed) {
        const LiveStun::Result &stun = LiveStun::result();
        if (stun.state == LiveStun::RUNNING) return;
        if (!stun.answered) {
            // Nothing leaving the socket is a Wii-side problem, not the internet.
            d.trouble = true;
            s.message = stun.attempts && d.socketSent ? Text::noAddress : Text::noSend;
            if (now - x.keepaliveMs >= 2000u) {
                x.keepaliveMs = now; LiveStun::startShared();
            }
            return;
        }
        s.own.endpoint = stun.mapped[stun.answered & 1u ? 0 : 1];
        s.own.secret = roomSecret();
        s.addressed = true; x.keepaliveMs = now;
        s.message = s.hosting ? Text::shareCode : Text::enterCode;
        if (s.hosting) {
            LiveP2P::reset(s.punch, s.own.secret, LiveP2P::HOST);
            LiveInvites::reset(sInvites, s.own.secret, sOptions.players - 1);
            if (!startSession(now)) { disconnect(); s.message = Text::invalidSettings; return; }
        }
        usePeer(now);
    }
    if (!s.connected || (sGroup.active && sGroup.host && LiveGroup::connectedCount(sGroup) < sGroup.config.rules.players)) {
        // Both sides send until the session connects; its pings keep the NAT open after.
        // Waiting never gives up: punches slow to once a second after 30 seconds.
        const unsigned interval = s.friendKnown && now - s.punchMs >= 30000u ?
            LiveP2P::PUNCH_SLOW_MS : LiveP2P::PUNCH_INTERVAL_MS;
        for (unsigned i = 0; i < (s.hosting ? sInvites.count : 1u); ++i) {
            u8 punch[LiveP2P::PUNCH_BYTES];
            auto &pending = s.hosting ? sInvites.slots[i].punch : s.punch;
            if (s.hosting && guestName(i)) continue;
            const unsigned bytes = LiveP2P::due(pending, 0, now, punch, interval);
            if (bytes && LiveTransport::sendControl(pending.peers[0].endpoint, punch, bytes))
                ++s.diagnostics.submitted;
        }
        if (s.friendKnown && !s.unreachable && now - s.punchMs >= 30000u) {
            s.unreachable = true; s.message = Text2::stillTrying;
        }
    }
    // STUN every 15 s keeps this NAT mapping open and notices a new address.
    const LiveStun::Result &stun = LiveStun::result();
    if (x.stunKeepalive && stun.state != LiveStun::RUNNING) {
        x.stunKeepalive = false;
        const TWLiveEndpoint &mapped = stun.mapped[stun.answered & 1u ? 0 : 1];
        if (stun.answered && memcmp(&mapped, &s.own.endpoint, sizeof(mapped))) {
            s.own.endpoint = mapped; x.codeChanged = true;
        }
    } else if (now - x.keepaliveMs >= 15000u) {
        x.keepaliveMs = now;
        x.stunKeepalive = LiveStun::startShared();
    }
    if (!s.started) return;
    Session::tick(s.session, now);
    acceptConnection();
    const auto connection = Session::status(s.session);
    if (!s.hosting && connection.error == Session::PEER_KICKED) {
        disconnect(); s.message = "Removed by host - ask for a new invitation"; return;
    }
    if (sGroup.active) {
        if (connection.state == Session::FAILED || connection.state == Session::STOPPED) {
            s.localReady = s.startPrepared = s.groupReadySent = false;
            s.connected = false; x.reconnecting = true;
            if (!startSession(now)) { disconnect(); s.message = Text::invalidSettings; return; }
        }
        sampleAttempt(now);
        updatePose(now);
        serviceGroup(now);
        serviceAutoOpen();
        return;
    }
    if (connection.state == Session::FAILED || connection.state == Session::STOPPED) {
        if (s.connected) {
            s.localReady = s.peerReady = s.startPrepared = false;
            s.readyNeeded = s.phase == WAIT_READY;
            // A lost link restores the same room silently: same codes, PIN and round.
            s.connected = false; x.reconnecting = true; x.lostMs = s.punchMs = now;
            s.message = Text2::reconnecting;
        }
        // Both sides keep trying until the player leaves.
        s.started = false;
        if (!startSession(now)) { disconnect(); s.message = Text::invalidSettings; }
        return;
    }
    sampleAttempt(now);
    if (!connection.connected) return;
    updatePose(now);
    serviceRace();
    serviceAutoOpen();
}
Status status() {
    Status out = {};
    const auto connection = Session::status(s.session);
    out.active = s.active; out.connected = !x.networkRetry && (sGroup.active && sGroup.host ? LiveGroup::connectedCount(sGroup) > 1 : s.connected); out.hosting = s.hosting;
    out.localReady = s.localReady; out.peerReady = s.peerReady; out.racing = s.phase == RUNNING;
    out.matchDone = s.phase == MATCH_DONE;
    out.freeRoam = s.phase == ROAMING;
    out.canForfeit = s.active && s.phase == RUNNING && !s.localResult;
    out.setupEditable = !s.active || canConfigureRace();
    out.drafting = sGroup.active ? sGroup.rules.phase == LiveGroupRules::Draft : s.phase == DRAFTING;
    out.draftPending = sGroup.active ? sGroup.requestAction != 0 : s.choiceNeeded || s.choiceSent || Session::status(s.session).pending;
    out.draft = s.draft;
    out.reconnecting = x.reconnecting; out.codeChanged = x.codeChanged;
    out.connection = !s.active ? Text::offline : x.networkRetry ? Text2::reconnecting : !s.stunStarted ? Text::starting :
        !s.addressed ? Text::gettingAddress : s.connected ? Text::connected :
        x.reconnecting ? Text2::reconnecting : s.unreachable ? Text2::stillTrying :
        s.friendKnown || connection.state == Session::ACCEPTING ? Text::connecting : Text::waitingFriend;
    out.hint = Text::empty;
    if (s.active && s.addressed && (!s.connected || (sGroup.active && sGroup.host))) {
        char code[LiveP2P::CODE_CHARS + 1];
        if (LiveP2P::encode(s.own, code)) LiveP2P::format(code, out.code);
        LiveP2P::Code local = s.own;
        if (LiveTransport::localEndpoint(&local.endpoint) && local.endpoint.ip[0] != 127 &&
            LiveP2P::encode(local, code)) LiveP2P::format(code, out.localCode);
        if (s.friendKnown && LiveP2P::encode(s.friendCode, code)) LiveP2P::format(code, out.friendCode);
        const bool symmetric = LiveStun::result().verdict == LiveStun::DIFFERENT_MAPPING;
        out.hint = s.unreachable ? (symmetric ? Text::hintSymmetric : Text::hintBlocked) :
            symmetric ? Text::hintSymmetric : s.hosting ? Text::hintHost : Text::hintJoin;
    }
    out.race = s.message ? s.message : Text::empty;
    memcpy(out.peerName, connection.remoteName, sizeof(out.peerName));
    out.pingMs = s.connected ? connection.pingMs : ~0u; out.networkError = s.networkError;
    out.localWins = s.localWins; out.peerWins = s.peerWins;
    out.diagnostics = s.diagnostics;
    // Keep the address after disconnect: 0.0.0.0 then means it was never known.
    memcpy(out.localIp, s.diagnostics.ip, 4);
    out.localPort = s.diagnostics.port;
    const u8 net = s.diagnostics.net;
    if (!s.active) out.diagnostics.net = net == NET_WAITING ? NET_FAILED :
        net == NET_UP && !s.diagnostics.trouble ? NET_OFF : net;
    return out;
}
void draw(Menu *menu) {
    if (sGroup.active) for (unsigned i = 0; i < sGroup.config.rules.players - 1u; ++i) LiveGhost::drawNameFor(i, menu);
    else LiveGhost::drawName(menu);
    if (!menu || menu->shown() || !s.connected || PracticeSession::hideHud()) return;
    LiveGhost::drawInputs(menu);
    if (!sPrefs.hideScore) drawScore(menu, sPrefs);
}
void drawScore(Menu *menu, const Prefs &prefs) {
    char text[80], opponent[32];
    if (sGroup.active) {
        const auto &r = sGroup.rules;
        const int scale = prefs.scoreScale >= 50 && prefs.scoreScale <= 200 ? prefs.scoreScale : 100;
        const int size = 12 * scale / 100;
        for (unsigned player = 0; player < r.config.players; ++player) {
            snprintf(text, sizeof(text), "%s%s   IL %u   Set %u", player == sGroup.self ? "> " : "",
                sGroup.members[player].name, r.roundWins[player], r.setWins[player]);
            if ((r.phase == LiveGroupRules::Results || r.phase == LiveGroupRules::Finished) &&
                (r.resultMask & (1u << player))) {
                const u32 cs = r.times[player] >= 0 ? static_cast<u32>((u64)(u32)r.times[player] * 1001u / 1200u) : 0;
                snprintf(text, sizeof(text), "%s  %lu:%02lu.%02lu%s  IL %u Set %u",
                    sGroup.members[player].name, cs / 6000u, cs / 100u % 60u, cs % 100u,
                    r.times[player] == MSR_FORFEIT_QF ? " (forfeit)" : r.eligibleMask & (1u << player) ? Text::empty : " (assisted)", r.roundWins[player], r.setWins[player]);
            }
            if ((r.resultMask & (1u << player)) && r.times[player] == MSR_FORFEIT_QF)
                snprintf(text, sizeof(text), "%s  DNF  IL %u Set %u",
                         sGroup.members[player].name, r.roundWins[player], r.setWins[player]);
            menu->drawText(text, prefs.scoreX - Menu::textWidth(text, size) / 2,
                prefs.scoreY + player * (size + 3), size, size, JUtility::TColor(255, 255, 255, 255));
        }
        return;
    }
    if (sOptions.draft) {
        const unsigned local = s.hosting ? 0 : 1;
        snprintf(text, sizeof(text), Text::setScoreFormat,
            s.draft.setWins[local], s.draft.setWins[local ^ 1], s.localWins, s.peerWins);
    } else if (sOptions.playlist) snprintf(text, sizeof(text), "Playlist race  %u levels", sPlaylist.plan.count);
    else snprintf(text, sizeof(text), Text::scoreFormat, s.localWins, s.peerWins, sOptions.bestOf);
    if (sOptions.playlist && s.phase == MATCH_DONE && s.localEligible && s.peerEligible) {
        const u32 own = static_cast<u32>((u64)(u32)s.localQf * 1001u / 1200u);
        const u32 peer = static_cast<u32>((u64)(u32)s.peerQf * 1001u / 1200u);
        snprintf(text, sizeof(text), "You %lu:%02lu.%02lu   Peer %lu:%02lu.%02lu",
                 own / 6000u, own / 100u % 60u, own % 100u,
                 peer / 6000u, peer / 100u % 60u, peer % 100u);
    }
    const char *score = s.phase == ROAMING ? Text::freeRoamScore : text;
    // The opponent finished first: their time, in the score bar, away from QFT.
    const char *message = s.message ? s.message : Text::empty;
    if (s.phase == RUNNING && s.peerResult && !s.localResult && s.peerEligible) {
        const u32 cs = static_cast<u32>(s.peerQf) * 1001u / 1200u;  // QF to centiseconds
        snprintf(opponent, sizeof(opponent), Text2::opponentFormat, cs / 6000u, cs / 100u % 60u, cs % 100u);
        message = opponent;
    }
    const bool showStatus = s.phase != RUNNING || s.localResult || message == opponent;
    const int scale = prefs.scoreScale >= 50 && prefs.scoreScale <= 200 ? prefs.scoreScale : 100;
    const int size = 14 * scale / 100, statusSize = 13 * scale / 100;
    int width = Menu::textWidth(score, size);
    const int statusWidth = showStatus ? Menu::textWidth(message, statusSize) : 0;
    if (statusWidth > width) width = statusWidth;
    // Anchored at its top centre: the default sits between the top HUD counters.
    const int left = prefs.scoreX - width / 2 - 4, top = prefs.scoreY;
    menu->fillBox(left, top, width + 8, (showStatus ? 42 : 24) * scale / 100,
                  JUtility::TColor(0, 0, 0, 130));
    menu->drawText(score, left + 4, top + 6 * scale / 100, size, size, JUtility::TColor(190, 250, 255, 255));
    if (showStatus)
        menu->drawText(message, left + 4, top + 25 * scale / 100, statusSize, statusSize,
                       JUtility::TColor(255, 255, 255, 255));
}
const Prefs &prefs() { return sPrefs; }
void setPrefs(const Prefs &prefs) {
    sPrefs = prefs;
    if (sPrefs.model >= MODEL_COUNT) sPrefs.model = MODEL_SHADOW;
#if !IS_EMULATOR
    if (SusamuneOnlineNameCfg *saved = savedName()) {
        saved->model = sPrefs.model;
        saved->flags = (sPrefs.hideOpponent ? SUSAMUNE_ONLINE_HIDE_OPPONENT : 0) |
            (sPrefs.hideScore ? SUSAMUNE_ONLINE_HIDE_SCORE : 0);
        saved->scoreX = sPrefs.scoreX; saved->scoreY = sPrefs.scoreY; saved->scoreScale = sPrefs.scoreScale;
        DCStoreRange(saved, sizeof(*saved));
        gSettings.markDirty();
    }
#endif
}
int opponentModel() { return s.active ? sPrefs.model : -1; }
bool opponentShown() { return !sPrefs.hideOpponent; }
bool lastFriend(char *out) {
#if !IS_EMULATOR
    if (const SusamuneOnlineNameCfg *saved = savedName()) {
        const u8 *f = saved->friendCode;
        LiveP2P::Code code = {};
        memcpy(code.endpoint.ip, f, 4);
        code.endpoint.port = static_cast<u16>(f[4] << 8 | f[5]);
        code.secret = static_cast<u32>(f[6] << 8 | f[7]);
        char raw[LiveP2P::CODE_CHARS + 1];
        if (LiveP2P::encode(code, raw)) { memcpy(out, raw, sizeof(raw)); return true; }
    }
#endif
    (void)out;
    return false;
}
}
#endif
