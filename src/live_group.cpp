#include "susamune/live_group.hxx"
#if TIMEWARP_LIVE_RACING
#include <Dolphin/mem.h>

namespace LiveGroup {
namespace {
namespace S = LiveRaceSession;
namespace R = LiveGroupRules;
enum { ReadyAction = 1, BanAction, ResultAction, CancelAction };
S::Session &link(Room &r, unsigned i) { return i ? r.extra[i - 1] : *r.primary; }
unsigned everyone(const Room &r) { return (1u << r.config.rules.players) - 1; }
void changed(Room &r) { if (++r.serial == 0) r.active = false; }
bool configValid(const Config &local, const Hooks &hooks, const Config &c) {
    R::State check;
    return hooks.validEntry && hooks.startRace && (!c.rules.draft || hooks.drawCandidates) &&
        c.catalogue == local.catalogue && c.episode < 8 && c.pool < 3 &&
        R::begin(check, c.rules, 1, c.entry) &&
        !(c.playlist && (c.rules.draft || c.rules.freeRoam || c.rules.bestOf != 1 || !c.playlistHash)) &&
        hooks.validEntry(hooks.context, c.entry, c.pool, false);
}
bool extraSend(void *context, const S::Endpoint &to, const void *data, unsigned bytes) {
    const S::Callbacks &cb = static_cast<LinkContext *>(context)->room->primary->callbacks;
    return cb.sendControl(cb.context, to, data, bytes);
}
bool extraSendPose(void *context, const S::Endpoint &to, const void *data, unsigned bytes) {
    const S::Callbacks &cb = static_cast<LinkContext *>(context)->room->primary->callbacks;
    return cb.sendLatestPose(cb.context, to, data, bytes);
}
void extraPose(void *context, const MSRHeader &h, const MSRPose &p, unsigned now) {
    LinkContext &c = *static_cast<LinkContext *>(context);
    pose(*c.room, c.index, h, p, now);
}
void extraControl(void *context, const MSRHeader &h, const void *data, unsigned bytes) {
    LinkContext &c = *static_cast<LinkContext *>(context);
    control(*c.room, c.index, h, data, bytes);
}
bool sameEndpoint(const S::Endpoint &a, const S::Endpoint &b) {
    return a.port && a.port == b.port && a.ip[0] == b.ip[0] && a.ip[1] == b.ip[1] &&
        a.ip[2] == b.ip[2] && a.ip[3] == b.ip[3];
}
void cancelLocal(Room &r) {
    const bool racing = r.rules.phase == R::Racing;
    R::cancel(r.rules); r.settledAt = r.now; changed(r);
    if (racing && r.hooks.cancelRace) r.hooks.cancelRace(r.hooks.context);
}
void apply(Room &r, unsigned player, unsigned action, int value, unsigned generation, unsigned revision, unsigned round) {
    if (generation != r.rules.generation || player >= r.config.rules.players) return;
    const unsigned old = r.rules.phase;
    bool accepted = false;
    if (action == ReadyAction && (value == 0 || value == 1) && round == r.rules.round)
        accepted = R::ready(r.rules, player, value != 0, generation);
    else if (action == BanAction && value >= 0)
        accepted = R::ban(r.rules, player, value, R::Token{generation, revision});
    else if (action == ResultAction)
        accepted = R::result(r.rules, player, value, value >= 0, generation, round);
    else if (action == CancelAction && round == r.rules.round &&
             (old == R::Racing || old == R::Ready)) { cancelLocal(r); return; }
    if (!accepted) return;
    changed(r);
    if (old == R::Racing && r.rules.phase != old) { r.settledAt = r.now; r.outcomeChanged = true; }
}
bool request(Room &r, unsigned action, int value) {
    // A failed start must still cancel when an older Ready request is queued.
    if (!r.active || (r.requestAction && action != CancelAction) || !(r.connectedMask & 1)) return false;
    if (r.host) { apply(r, 0, action, value, r.rules.generation, r.rules.revision, r.rules.round); return true; }
    r.requestAction = action; r.requestValue = value; r.requestGeneration = r.rules.generation;
    r.requestRevision = r.rules.revision; r.requestRound = r.rules.round;
    return true;
}
void welcomeBytes(const Room &r, unsigned player, unsigned char *p) {
    memset(p, 0, 28);
    p[0] = Welcome; p[1] = r.config.rules.players; p[2] = player;
    p[3] = r.config.rules.bestOf; p[4] = r.config.rules.setBestOf;
    p[5] = (r.config.rules.draft ? 1 : 0) | (r.config.rules.freeRoam ? 2 : 0) | (r.config.playlist ? 4 : 0);
    p[6] = r.config.episode; p[7] = r.config.pool; MSRWrite16(p + 8, r.config.entry);
    MSRWrite32(p + 12, r.config.catalogue); MSRWrite32(p + 16, r.rules.generation);
    MSRWrite32(p + 20, r.config.playlistHash);
}
void snapshotBytes(const Room &r, unsigned char *p) {
    const R::State &s = r.rules;
    memset(p, 0, 64);
    p[0] = Snapshot; p[1] = s.phase; p[2] = r.connectedMask; p[3] = s.readyMask;
    MSRWrite32(p + 4, s.generation); MSRWrite32(p + 8, r.serial); MSRWrite32(p + 12, s.round);
    MSRWrite16(p + 16, s.selected); p[18] = s.resultMask; p[19] = s.eligibleMask;
    p[20] = s.winner; p[21] = s.rotation; p[22] = s.bans; p[23] = s.bannedMask;
    for (unsigned i = 0; i < 4; ++i) { p[24 + i] = s.roundWins[i]; p[28 + i] = s.setWins[i]; MSRWrite32(p + 42 + 4 * i, s.times[i]); }
    for (unsigned i = 0; i < 5; ++i) MSRWrite16(p + 32 + 2 * i, s.candidates[i]);
    MSRWrite32(p + 58, s.revision);
}
bool readSnapshot(Room &r, const unsigned char *p, unsigned bytes) {
    if (bytes != 64 || p[1] > R::Roaming || (p[2] & ~everyone(r)) || !(p[2] & (1u << r.self)) ||
        (p[3] & ~everyone(r)) || MSRRead32(p + 4) != r.rules.generation ||
        !MSRSequenceAfter(MSRRead32(p + 8), r.receivedSerial) || p[62] || p[63] ||
        (p[18] & ~everyone(r)) || (p[19] & ~p[18]) || (p[20] != R::Nobody && p[20] >= r.config.rules.players) ||
        p[21] >= r.config.rules.players || p[22] > r.config.rules.players ||
        (p[23] & ~((1u << (r.config.rules.players + 1)) - 1))) return false;
    R::State next = r.rules;
    next.phase = p[1]; next.readyMask = p[3]; next.round = MSRRead32(p + 12);
    next.selected = MSRRead16(p + 16); next.resultMask = p[18]; next.eligibleMask = p[19];
    next.winner = p[20]; next.rotation = p[21]; next.bans = p[22]; next.bannedMask = p[23];
    next.revision = MSRRead32(p + 58);
    if (!r.hooks.validEntry(r.hooks.context, next.selected, r.config.pool, false)) return false;
    for (unsigned i = 0; i < 4; ++i) {
        next.roundWins[i] = p[24 + i]; next.setWins[i] = p[28 + i]; next.times[i] = MSRReadSigned32(p + 42 + 4 * i);
        if (next.roundWins[i] > r.config.rules.bestOf || next.setWins[i] > r.config.rules.setBestOf ||
            ((next.resultMask & (1u << i)) && ((next.eligibleMask & (1u << i)) ? next.times[i] < 0 : (next.times[i] != -1 && next.times[i] != MSR_FORFEIT_QF)))) return false;
    }
    for (unsigned i = 0; i < 5; ++i) {
        next.candidates[i] = MSRRead16(p + 32 + 2 * i);
        if (next.phase == R::Draft && i <= r.config.rules.players &&
            !r.hooks.validEntry(r.hooks.context, next.candidates[i], r.config.pool, true)) return false;
    }
    const bool start = next.phase == R::Racing && (r.rules.phase != R::Racing || next.round != r.rules.round);
    const bool ended = r.rules.phase == R::Racing && next.phase != R::Racing;
    if (r.hooks.resetPose) for (unsigned player = 0; player < r.config.rules.players; ++player)
        if ((r.connectedMask & ~p[2]) & (1u << player)) r.hooks.resetPose(r.hooks.context, player);
    r.rules = next; r.receivedSerial = MSRRead32(p + 8); r.connectedMask = p[2];
    if (start) {
        Config chosen = r.config; chosen.entry = next.selected;
        if (!r.hooks.startRace(r.hooks.context, chosen, r.config.playlist ? &r.playlist.plan : nullptr))
            request(r, CancelAction, 0);
    }
    if (ended) {
        r.settledAt = r.now; r.outcomeChanged = true;
        if (next.resultMask != everyone(r) && r.hooks.cancelRace) r.hooks.cancelRace(r.hooks.context);
    }
    return true;
}
void receiveBundle(Room &r, const unsigned char *p, unsigned bytes) {
    if (r.host || bytes < 4 + MSR_GROUP_ENTRY_BYTES || p[0] > 3 || bytes != 4u + p[0] * MSR_GROUP_ENTRY_BYTES) return;
    for (unsigned i = 0; i < p[0]; ++i) {
        const unsigned char *entry = p + 4 + i * MSR_GROUP_ENTRY_BYTES;
        const unsigned player = entry[0];
        if (player == r.self || player >= r.config.rules.players || !(r.connectedMask & (1u << player))) continue;
        MSRPose pose; MSRHeader h = {};
        if (!MSRDecodePose(entry + 8, MSR_POSE_BASE_BYTES, &pose)) continue;
        h.sequence = MSRRead32(entry + 4); h.region = entry[1]; h.participant = player;
        if (r.hooks.pose) r.hooks.pose(r.hooks.context, player, h, pose, r.now);
    }
}
bool sendNext(Room &r, unsigned peer) {
    S::Session &s = link(r, peer);
    if (!s.info.connected || s.info.pending) return false;
    unsigned char body[64]; unsigned bytes = 0;
    unsigned &sent = r.sentSerial[peer];
    unsigned char &step = r.syncStep[peer];
    if (step == 0) { welcomeBytes(r, peer + 1, body); bytes = 28; }
    else if (step <= r.config.rules.players) {
        const unsigned player = step - 1;
        memset(body, 0, 20); body[0] = Name; body[1] = player; body[2] = r.members[player].region;
        memcpy(body + 4, r.members[player].name, 16); bytes = 20;
    } else if (r.config.playlist && r.playlistAt[peer] < r.playlist.plan.count) {
        bytes = LivePlaylist::encode(r.playlist.plan, r.playlistAt[peer], body);
    } else if (sent != r.serial) { snapshotBytes(r, body); bytes = 64; }
    if (!bytes || !S::sendReliable(s, MSR_READY, body, bytes, r.rules.generation)) return false;
    if (step <= r.config.rules.players) ++step;
    else if (body[0] == LivePlaylist::Message) r.playlistAt[peer] += body[2];
    else sent = r.serial;
    return true;
}
}
bool host(Room &r, S::Session &primary, const Config &config, const LivePlaylist::Plan *plan, const Hooks &hooks, unsigned generation) {
    r = {}; r.primary = &primary; r.config = config; r.hooks = hooks; r.host = true;
    if (!configValid(config, hooks, config) || !R::begin(r.rules, config.rules, generation, config.entry)) return false;
    if (config.playlist) {
        if (!plan || LivePlaylist::hash(*plan) != config.playlistHash) return false;
        r.playlist.plan = *plan; r.playlist.hash = config.playlistHash; r.playlist.complete = true;
    }
    r.active = true; r.serial = 1; r.connectedMask = 1;
    memcpy(r.members[0].name, primary.config.name, 16); r.members[0].region = primary.config.region;
    for (unsigned i = 1; i < config.rules.players - 1u; ++i) {
        S::Config c = primary.config; c.nonceLow ^= i * 0x9e3779b9u;
        r.links[i - 1] = LinkContext{&r, i};
        S::Callbacks callbacks = {&r.links[i - 1], extraSend, extraSendPose, extraPose, extraControl};
        if (!S::init(r.extra[i - 1], c, callbacks) || !S::startHost(r.extra[i - 1], S::Endpoint{}, primary.nowMs)) { stop(r); return false; }
    }
    return true;
}
bool configure(Room &r, const Config &config, const LivePlaylist::Plan *plan) {
    if (!r.active || !r.host || r.config.rules.players != config.rules.players || !configValid(r.config, r.hooks, config) ||
        (r.rules.phase != R::Finished && r.rules.phase != R::Roaming) || r.rules.generation == ~0u ||
        (config.playlist && (!plan || LivePlaylist::hash(*plan) != config.playlistHash))) return false;
    if (!R::begin(r.rules, config.rules, r.rules.generation + 1, config.entry)) return false;
    r.config = config; r.poseMask = 0; r.requestAction = 0; r.outcomeChanged = false;
    r.playlist = {};
    if (plan && config.playlist) { r.playlist.plan = *plan; r.playlist.complete = true; r.playlist.hash = config.playlistHash; }
    for (unsigned i = 0; i < 3; ++i) { r.syncStep[i] = 0; r.sentSerial[i] = 0; r.playlistAt[i] = 0; }
    changed(r);
    return true;
}
bool adopt(Room &r, S::Session &primary, const Config &local, const Hooks &hooks, const void *data, unsigned bytes) {
    const unsigned char *p = static_cast<const unsigned char *>(data);
    if (!data || bytes != 28 || p[0] != Welcome || p[1] < 3 || p[1] > 4 || !p[2] || p[2] >= p[1] ||
        (p[5] & ~7u) || p[10] || p[11] || MSRRead32(p + 24) || !MSRRead32(p + 16)) return false;
    if (r.active) {
        if (r.host || r.self != p[2]) return false;
        if (r.rules.generation == MSRRead32(p + 16)) return true;
        if (!MSRSequenceAfter(MSRRead32(p + 16), r.rules.generation) ||
            (r.rules.phase != R::Finished && r.rules.phase != R::Roaming)) return false;
    }
    Config c = {};
    c.rules = R::Config{p[1], p[3], p[4], (p[5] & 1u) != 0, (p[5] & 2u) != 0};
    c.entry = MSRRead16(p + 8); c.episode = p[6]; c.pool = p[7]; c.playlist = p[5] & 4u;
    c.catalogue = MSRRead32(p + 12); c.playlistHash = MSRRead32(p + 20);
    if (!configValid(local, hooks, c)) return false;
    r = {}; r.primary = &primary; r.hooks = hooks;
    if (!R::begin(r.rules, c.rules, MSRRead32(p + 16), c.entry)) return false;
    r.config = c; r.self = p[2]; r.active = true; r.connectedMask = 1u | (1u << r.self);
    memcpy(r.members[r.self].name, primary.config.name, 16); r.members[r.self].region = primary.config.region;
    memcpy(r.members[0].name, primary.info.remoteName, 16); r.members[0].region = primary.info.remoteRegion;
    return true;
}
void stop(Room &r) {
    if (r.host) for (unsigned i = 0; i < 2; ++i) S::stop(r.extra[i]);
    r.active = false;
}
bool receive(Room &r, const TWLiveEndpoint &from, const void *data, unsigned bytes, unsigned now) {
    if (!r.active || !r.host) return false;
    // Route an existing guest before offering HELLO to any vacant listener.
    if (sameEndpoint(from, r.primary->info.peer)) return S::receivePacket(*r.primary, from, data, bytes, now);
    for (unsigned i = 0; i < r.config.rules.players - 2u; ++i)
        if (sameEndpoint(from, r.extra[i].info.peer)) return S::receivePacket(r.extra[i], from, data, bytes, now);
    if (S::receivePacket(*r.primary, from, data, bytes, now)) return true;
    for (unsigned i = 0; i < r.config.rules.players - 2u; ++i)
        if (S::receivePacket(r.extra[i], from, data, bytes, now)) return true;
    return false;
}
bool kickPeer(Room &r, const TWLiveEndpoint &endpoint) {
    if (!r.active || !r.host) return false;
    for (unsigned i = 0; i < r.config.rules.players - 1u; ++i) {
        S::Session &s = link(r, i);
        if (!sameEndpoint(endpoint, s.info.peer)) continue;
        S::kick(s);
        r.welcomedMask &= ~(1u << (i + 1));
        r.poseMask &= ~(1u << (i + 1));
        if (r.hooks.resetPose) r.hooks.resetPose(r.hooks.context, i + 1);
        return true;
    }
    return false;
}
void replacePeer(Room &r, const TWLiveEndpoint &oldPeer, const TWLiveEndpoint &newPeer, unsigned now) {
    if (!r.active || !r.host || sameEndpoint(oldPeer, newPeer)) return;
    for (unsigned i = 0; i < r.config.rules.players - 1u; ++i) {
        S::Session &s = link(r, i);
        if (s.info.connected || !sameEndpoint(oldPeer, s.info.peer)) continue;
        S::Config config = s.config;
        ++config.nonceHigh;
        if (S::init(s, config, s.callbacks)) S::startHost(s, newPeer, now);
        r.poseMask &= ~(1u << (i + 1));
        if (r.hooks.resetPose) r.hooks.resetPose(r.hooks.context, i + 1);
        return;
    }
}
bool control(Room &r, unsigned peer, const MSRHeader &h, const void *data, unsigned bytes) {
    if (!r.active || !data || !bytes) return false;
    const unsigned char *p = static_cast<const unsigned char *>(data);
    if (h.kind == MSR_GROUP_POSES) { receiveBundle(r, p, bytes); return true; }
    if (h.kind != MSR_READY || h.round != r.rules.generation) return false;
    if (r.host) {
        if (p[0] != Request || bytes != 20 || p[2] || p[3] || peer >= r.config.rules.players - 1u) return false;
        apply(r, peer + 1, p[1], MSRReadSigned32(p + 16), MSRRead32(p + 4), MSRRead32(p + 8), MSRRead32(p + 12));
        return true;
    }
    if (p[0] == Snapshot) return readSnapshot(r, p, bytes);
    if (p[0] == Name) {
        if (bytes != 20 || p[1] >= r.config.rules.players || p[2] >= 3 || p[3]) return false;
        bool ended = false;
        for (unsigned i = 4; i < 20; ++i) {
            if (!p[i]) ended = true;
            else if (ended || p[i] < 32 || p[i] > 126) return false;
        }
        memcpy(r.members[p[1]].name, p + 4, 16); r.members[p[1]].name[16] = 0; r.members[p[1]].region = p[2];
        return true;
    }
    if (p[0] == LivePlaylist::Message && r.config.playlist) {
        if (bytes < LivePlaylist::HeaderBytes || bytes != LivePlaylist::HeaderBytes + p[2] * 2u) return false;
        for (unsigned i = 0; i < p[2]; ++i)
            if (!r.hooks.validEntry(r.hooks.context, p[12 + 2 * i], r.config.pool, false)) return false;
        return LivePlaylist::receive(r.playlist, p, bytes, r.config.playlistHash, 65535);
    }
    return false;
}
void pose(Room &r, unsigned peer, const MSRHeader &h, const MSRPose &p, unsigned now) {
    if (!r.active || !r.host || peer >= r.config.rules.players - 1u) return;
    const unsigned player = peer + 1;
    // Relay timelines survive guest reconnects, even if a roster update is missed.
    const unsigned epoch = r.poses[player].sceneEpoch +
        (!(r.poseMask & (1u << player)) || r.remoteSceneEpoch[player] != p.sceneEpoch);
    r.remoteSceneEpoch[player] = p.sceneEpoch;
    r.poses[player] = p; r.poses[player].sceneEpoch = epoch;
    MSRHeader relay = h; relay.sequence = ++r.poseSequence[player];
    r.poseReceived[player] = now; r.poseMask |= 1u << player;
    if (r.hooks.pose) r.hooks.pose(r.hooks.context, player, relay, r.poses[player], now);
}
void localPose(Room &r, const MSRPose &p, unsigned now) {
    if (!r.active) return;
    if (!r.host) { S::publishPose(*r.primary, p, r.rules.round, false); return; }
    r.poses[0] = p; r.poseSequence[0] = ++r.ownPoseSequence; r.poseReceived[0] = now; r.poseMask |= 1;
}
void tick(Room &r, unsigned now) {
    if (!r.active) return;
    r.now = now;
    if (!r.host) {
        if (r.requestAction && !r.primary->info.pending && r.primary->info.connected) {
            unsigned char body[20] = {}; body[0] = Request; body[1] = r.requestAction;
            MSRWrite32(body + 4, r.requestGeneration); MSRWrite32(body + 8, r.requestRevision);
            MSRWrite32(body + 12, r.requestRound); MSRWrite32(body + 16, r.requestValue);
            if (S::sendReliable(*r.primary, MSR_READY, body, sizeof(body), r.rules.generation)) r.requestAction = 0;
        }
        return;
    }
    unsigned mask = 1;
    for (unsigned i = 0; i < r.config.rules.players - 1u; ++i) {
        S::Session &s = link(r, i);
        if (i) S::tick(s, now);
        if (s.info.connected) {
            mask |= 1u << (i + 1); r.members[i + 1].ping = s.info.pingMs;
            if (!(r.connectedMask & (1u << (i + 1)))) {
                r.poseMask &= ~(1u << (i + 1));
                if (r.hooks.resetPose) r.hooks.resetPose(r.hooks.context, i + 1);
                memcpy(r.members[i + 1].name, s.info.remoteName, 17); r.members[i + 1].region = s.info.remoteRegion;
                for (unsigned j = 0; j < 3; ++j) { r.syncStep[j] = 0; r.sentSerial[j] = 0; r.playlistAt[j] = 0; }
            }
        } else if (i && (s.info.state == S::FAILED || s.info.state == S::STOPPED)) {
            const S::Endpoint allowed = (r.welcomedMask & (1u << (i + 1))) ? s.info.peer : S::Endpoint{};
            S::Config config = s.config;
            ++config.nonceHigh;
            if (S::init(s, config, s.callbacks)) S::startHost(s, allowed, now);
        }
    }
    if (mask != r.connectedMask) {
        if ((r.connectedMask & ~mask) && (r.rules.phase == R::Racing || r.rules.phase == R::Ready)) cancelLocal(r);
        r.connectedMask = mask; r.welcomedMask |= mask; changed(r);
    }
    if (mask == everyone(r)) {
        if (r.rules.phase == R::NeedCandidates) {
            unsigned short entries[5];
            if (r.hooks.drawCandidates(r.hooks.context, entries, r.config.rules.players + 1, r.config.pool) &&
                R::candidates(r.rules, entries, r.config.rules.players + 1, R::token(r.rules))) changed(r);
        } else if (r.rules.phase == R::Ready && R::start(r.rules, mask)) {
            Config chosen = r.config; chosen.entry = r.rules.selected;
            if (!r.hooks.startRace(r.hooks.context, chosen, r.config.playlist ? &r.playlist.plan : nullptr)) cancelLocal(r);
            else changed(r);
        } else if (r.rules.phase == R::Results && now - r.settledAt >= 2000 && R::advance(r.rules)) changed(r);
    }
    const unsigned guests = r.config.rules.players - 1u;
    for (unsigned i = 0; i < guests; ++i) sendNext(r, (r.controlRecipient + i) % guests);
    r.controlRecipient = (r.controlRecipient + 1) % guests;
    // Bundles use the bounded FIFO: a shared latest-pose slot can repeatedly
    // overwrite one recipient before the ARM worker gets to send it.
    for (unsigned i = 0; i < r.config.rules.players - 1u; ++i) {
        const unsigned recipient = r.recipient % (r.config.rules.players - 1u);
        S::Session &s = link(r, recipient);
        // Initial roster first; later reliable retries must not hide movement.
        if (!s.info.connected || r.syncStep[recipient] <= r.config.rules.players ||
            !r.sentSerial[recipient] || now - r.sentAt[recipient] < 48) { ++r.recipient; continue; }
        unsigned char body[4 + 3 * MSR_GROUP_ENTRY_BYTES] = {}; unsigned count = 0;
        for (unsigned player = 0; player < r.config.rules.players; ++player) {
            if (player == recipient + 1 || !(r.poseMask & r.connectedMask & (1u << player)) || now - r.poseReceived[player] > 1000) continue;
            unsigned char *entry = body + 4 + count * MSR_GROUP_ENTRY_BYTES;
            entry[0] = player; entry[1] = r.members[player].region; MSRWrite32(entry + 4, r.poseSequence[player]);
            unsigned char encoded[MSR_POSE_BYTES];
            if (MSREncodePose(encoded, sizeof(encoded), &r.poses[player])) {
                memcpy(entry + 8, encoded, MSR_POSE_BASE_BYTES); ++count;
            }
        }
        body[0] = count;
        if (!count) { ++r.recipient; continue; }
        if (S::publishGroupPoses(s, body, 4 + count * MSR_GROUP_ENTRY_BYTES, r.rules.round)) {
            r.sentAt[recipient] = now; ++r.recipient;
        }
        break;
    }
}
bool ready(Room &r, bool value) { return r.rules.phase == R::Ready && (!r.config.playlist || r.playlist.complete) && request(r, ReadyAction, value); }
bool ban(Room &r, unsigned candidate) { return R::actor(r.rules) == r.self && candidate <= r.config.rules.players && request(r, BanAction, candidate); }
bool result(Room &r, int qf, bool eligible) { return r.rules.phase == R::Racing && request(r, ResultAction, eligible && qf >= 0 ? qf : qf == MSR_FORFEIT_QF ? MSR_FORFEIT_QF : -1); }
bool cancel(Room &r) { return request(r, CancelAction, 0); }
unsigned connectedCount(const Room &r) { unsigned n = 0; for (unsigned i = 0; i < 4; ++i) n += (r.connectedMask >> i) & 1; return n; }
unsigned remoteSlot(const Room &r, unsigned player) { return player < r.self ? player : player - 1; }
}
#endif
