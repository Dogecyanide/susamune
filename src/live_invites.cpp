#if TIMEWARP_LIVE_RACING
#include "susamune/live_invites.hxx"
#include "susamune/live_race_wire.h"

namespace LiveInvites {
namespace {
bool same(const TWLiveEndpoint &a, const TWLiveEndpoint &b) {
    for (unsigned i = 0; i < 4; ++i) if (a.ip[i] != b.ip[i]) return false;
    return a.port == b.port;
}
int destination(const State &s, const TWLiveEndpoint &from) {
    const int exact = find(s, from);
    if (exact >= 0) return exact;
    int candidate = -1;
    for (unsigned i = 0; i < s.count; ++i) {
        const auto &p = s.slots[i].punch.peers[0];
        if (p.state != LiveP2P::PUNCHING) continue;
        bool ip = true;
        for (unsigned j = 0; j < 4; ++j) if (p.endpoint.ip[j] != from.ip[j]) ip = false;
        if (!ip) continue;
        // Shared public IPs cannot identify which pending invitation changed port.
        if (candidate >= 0) return -1;
        candidate = static_cast<int>(i);
    }
    if (candidate >= 0) return candidate;
    return -1;
}
}
void reset(State &s, unsigned pin, unsigned count) {
    s = {}; s.pin = pin; s.count = count <= 3 ? count : 0;
    for (unsigned i = 0; i < s.count; ++i) LiveP2P::reset(s.slots[i].punch, pin, LiveP2P::HOST);
}
int find(const State &s, const TWLiveEndpoint &endpoint) {
    for (unsigned i = 0; i < s.count; ++i) {
        const auto &p = s.slots[i].punch.peers[0];
        if (p.state && same(p.endpoint, endpoint)) return static_cast<int>(i);
    }
    return -1;
}
void clear(State &s, unsigned slot) {
    if (slot >= s.count) return;
    s.slots[slot] = {};
    LiveP2P::reset(s.slots[slot].punch, s.pin, LiveP2P::HOST);
}
bool permits(const State &s, const TWLiveEndpoint &endpoint) {
    return find(s, endpoint) >= 0;
}
bool set(State &s, unsigned slot, const LiveP2P::Code &code) {
    if (slot >= s.count) return false;
    const int existing = find(s, code.endpoint);
    if (existing >= 0 && existing != static_cast<int>(slot)) return false;
    auto &invite = s.slots[slot];
    LiveP2P::reset(invite.punch, s.pin, LiveP2P::HOST);
    if (LiveP2P::add(invite.punch, code.endpoint, LiveP2P::JOINER) < 0) return false;
    invite.code = code;
    return true;
}
int connected(State &s, const TWLiveEndpoint &endpoint) {
    const int slot = destination(s, endpoint);
    if (slot < 0) return slot;
    auto &p = s.slots[slot].punch.peers[0];
    p.endpoint = endpoint; p.participant = LiveP2P::JOINER; p.state = LiveP2P::OPEN;
    return slot;
}
bool receive(State &s, const TWLiveEndpoint &from, const void *data, unsigned bytes, unsigned now) {
    const auto *p = static_cast<const unsigned char *>(data);
    if (bytes < LiveP2P::PUNCH_BYTES || MSRRead32(p) != 0x4d535031u) return false;
    if (bytes != LiveP2P::PUNCH_BYTES || MSRRead32(p + 4) != s.pin ||
        p[8] != LiveP2P::JOINER || p[9] > 1 || p[10] || p[11]) return true;
    const int slot = destination(s, from);
    if (slot >= 0) LiveP2P::receive(s.slots[slot].punch, from, data, bytes, now, true);
    return true;
}
}
#endif
