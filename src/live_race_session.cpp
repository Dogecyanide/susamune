#include "susamune/live_race_session.hxx"
#include "susamune/live_p2p.hxx"

#if TIMEWARP_LIVE_RACING
namespace LiveRaceSession {
namespace {
const unsigned kHandshakeMs = 30000, kTimeoutMs = 15000;
const unsigned kHeartbeatMs = 1000, kRetryMs = 250;

void copy(void *out, const void *in, unsigned bytes) {
    unsigned char *d = static_cast<unsigned char *>(out);
    const unsigned char *s = static_cast<const unsigned char *>(in);
    while (bytes--) *d++ = *s++;
}
bool equal(const void *a, const void *b, unsigned bytes) {
    const unsigned char *x = static_cast<const unsigned char *>(a);
    const unsigned char *y = static_cast<const unsigned char *>(b);
    while (bytes--) if (*x++ != *y++) return false;
    return true;
}
bool validEndpoint(const Endpoint &p) {
    return p.port && !p.reserved && p.ip[0] && p.ip[0] < 224;
}
bool sameEndpoint(const Endpoint &a, const Endpoint &b) {
    return a.port == b.port && !a.reserved && !b.reserved && equal(a.ip, b.ip, 4);
}
bool emptyEndpoint(const Endpoint &p) {
    return !p.port && !p.reserved && !(p.ip[0] | p.ip[1] | p.ip[2] | p.ip[3]);
}
bool validName(const char *name) {
    bool ended = false;
    if (!name[0]) return false;
    for (unsigned i = 0; i < MSR_NAME_BYTES; ++i) {
        unsigned char c = static_cast<unsigned char>(name[i]);
        if (!c) ended = true;
        else if (ended || c < 32 || c > 126) return false;
    }
    return true;
}
bool reliableKind(unsigned kind) {
    return kind == MSR_READY || kind == MSR_START || kind == MSR_RESULT;
}
void fail(Session &s, Error error) {
    s.info.state = FAILED; s.info.error = error;
    s.info.connected = s.info.pending = false;
    s.controlAck = s.handshakeAck = false;
}
MSRHeader header(const Session &s, unsigned kind, unsigned bytes,
                 unsigned sequence = 0, unsigned round = 0) {
    MSRHeader h = {};
    h.kind = static_cast<unsigned char>(kind);
    h.payloadBytes = static_cast<unsigned short>(bytes);
    h.sequence = sequence; h.round = round;
    h.sessionHigh = s.sessionHigh; h.sessionLow = s.sessionLow;
    h.region = s.config.region; h.timing = s.config.timing;
    h.participant = s.info.host ? 0 : 1;
    return h;
}
bool send(Session &s, const MSRHeader &h, const void *payload, bool pose = false) {
    unsigned char packet[MSR_HEADER_BYTES + kReliableBytes];
    if (h.payloadBytes > kReliableBytes || (h.payloadBytes && !payload) ||
        !MSREncodeHeader(packet, sizeof(packet), &h)) return false;
    if (h.payloadBytes) copy(packet + MSR_HEADER_BYTES, payload, h.payloadBytes);
    return pose ? s.callbacks.sendLatestPose(s.callbacks.context, s.info.peer,
                         packet, MSR_HEADER_BYTES + h.payloadBytes) :
                  s.callbacks.sendControl(s.callbacks.context, s.info.peer,
                         packet, MSR_HEADER_BYTES + h.payloadBytes);
}
void connected(Session &s) {
    s.info.state = CONNECTED; s.info.connected = true;
    s.lastReceiveMs = s.nowMs; s.lastPingMs = s.nowMs;
    s.pingSent = false;
}
bool sendHello(Session &s) {
    unsigned char payload[28];
    MSRWrite32(payload, s.config.pin);
    MSRWrite32(payload + 4, s.config.nonceHigh);
    MSRWrite32(payload + 8, s.config.nonceLow);
    copy(payload + 12, s.config.name, MSR_NAME_BYTES);
    MSRHeader h = header(s, MSR_HELLO, sizeof(payload));
    h.sessionHigh = h.sessionLow = 0;
    return send(s, h, payload);
}
bool sendAccept(Session &s) {
    unsigned char payload[24];
    MSRWrite32(payload, s.guestNonceHigh); MSRWrite32(payload + 4, s.guestNonceLow);
    copy(payload + 8, s.config.name, MSR_NAME_BYTES);
    return send(s, header(s, MSR_ACCEPT, sizeof(payload)), payload);
}
bool sendHandshakeAck(Session &s) {
    unsigned char kind = MSR_ACCEPT;
    if (!send(s, header(s, MSR_ACK, 1), &kind)) return false;
    s.handshakeAck = false;
    if (!s.info.connected) connected(s);
    return true;
}
bool sendControlAck(Session &s) {
    unsigned char kind = s.receivedHeader.kind;
    if (!send(s, header(s, MSR_ACK, 1, s.receivedHeader.sequence,
                        s.receivedHeader.round), &kind)) return false;
    s.controlAck = false;
    return true;
}
bool bound(const Session &s, const Endpoint &from, const MSRHeader &h) {
    return sameEndpoint(from, s.info.peer) && h.region == s.info.remoteRegion &&
        h.participant == (s.info.host ? 1 : 0) &&
        h.sessionHigh == s.sessionHigh && h.sessionLow == s.sessionLow;
}
bool expired(Session &s) {
    if (s.info.connected) {
        if (s.nowMs - s.lastReceiveMs >= kTimeoutMs) { fail(s, PEER_TIMEOUT); return true; }
        if (s.info.pending && s.nowMs - s.reliableStartedMs >= kTimeoutMs) {
            fail(s, RELIABLE_TIMEOUT); return true;
        }
    } else if ((s.info.state == LISTENING || s.info.state == JOINING ||
                s.info.state == ACCEPTING) && s.nowMs - s.startedMs >= kHandshakeMs) {
        fail(s, HANDSHAKE_TIMEOUT); return true;
    }
    return s.info.state == FAILED || s.info.state == STOPPED;
}
bool acceptHello(Session &s, const Endpoint &from, const MSRHeader &h,
                 const unsigned char *p) {
    if (!s.info.host || (s.info.state != LISTENING && s.info.state != ACCEPTING &&
                        s.info.state != CONNECTED) || h.payloadBytes != 28 ||
        h.participant != 1 || h.sequence || h.round || h.sessionHigh || h.sessionLow ||
        MSRRead32(p) != s.config.pin || !(MSRRead32(p + 4) | MSRRead32(p + 8)) ||
        !validName(reinterpret_cast<const char *>(p + 12)) ||
        (s.restricted && !sameEndpoint(from, s.allowedPeer))) return false;
    if (s.info.state != LISTENING) {
        if (!sameEndpoint(from, s.info.peer) || h.region != s.info.remoteRegion ||
            MSRRead32(p + 4) != s.guestNonceHigh || MSRRead32(p + 8) != s.guestNonceLow ||
            !equal(p + 12, s.info.remoteName, MSR_NAME_BYTES)) return false;
    } else {
        s.info.peer = from; s.info.remoteRegion = h.region;
        copy(s.info.remoteName, p + 12, MSR_NAME_BYTES);
        s.info.remoteName[MSR_NAME_BYTES] = 0;
        s.guestNonceHigh = MSRRead32(p + 4); s.guestNonceLow = MSRRead32(p + 8);
        s.sessionHigh = s.config.nonceHigh; s.sessionLow = s.config.nonceLow;
        s.info.state = ACCEPTING;
        s.handshakeSent = false;
    }
    if (sendAccept(s)) { s.handshakeSent = true; s.lastHandshakeMs = s.nowMs; }
    return true;
}
bool acceptOffer(Session &s, const Endpoint &from, const MSRHeader &h,
                 const unsigned char *p) {
    if (s.info.host || (s.info.state != JOINING && s.info.state != CONNECTED) ||
        !sameEndpoint(from, s.info.peer) || h.payloadBytes != 24 || h.participant ||
        h.sequence || h.round || !(h.sessionHigh | h.sessionLow) ||
        MSRRead32(p) != s.config.nonceHigh || MSRRead32(p + 4) != s.config.nonceLow ||
        !validName(reinterpret_cast<const char *>(p + 8))) return false;
    if (s.guestAccepted) {
        if (!bound(s, from, h) || !equal(p + 8, s.info.remoteName, MSR_NAME_BYTES)) return false;
    } else {
        s.sessionHigh = h.sessionHigh; s.sessionLow = h.sessionLow;
        s.info.remoteRegion = h.region;
        copy(s.info.remoteName, p + 8, MSR_NAME_BYTES);
        s.info.remoteName[MSR_NAME_BYTES] = 0;
        s.guestAccepted = true;
    }
    s.handshakeAck = true;
    sendHandshakeAck(s);
    return true;
}
}

bool init(Session &s, const Config &config, const Callbacks &callbacks) {
    Config c = config;
    Callbacks cb = callbacks;
    s = Session{};
    s.config = c; s.callbacks = cb;
    s.info.pingMs = ~0u;
    s.sendSequence = s.receiveSequence = s.poseSendSequence = s.pingSequence = 1;
    if (!validName(c.name) || c.pin > 999999 || !(c.nonceHigh | c.nonceLow) ||
        c.region > 2 || c.timing != MSR_TIMING_60HZ || !cb.sendControl ||
        !cb.sendLatestPose) { fail(s, INVALID_CONFIG); return false; }
    s.initialized = true;
    return true;
}
bool startHost(Session &s, const Endpoint &allowedPeer, unsigned nowMs) {
    if (!s.initialized || s.info.state != STOPPED ||
        (!emptyEndpoint(allowedPeer) && !validEndpoint(allowedPeer))) return false;
    s.allowedPeer = allowedPeer; s.restricted = !emptyEndpoint(allowedPeer);
    s.info.host = true; s.info.state = LISTENING;
    s.nowMs = s.startedMs = nowMs;
    return true;
}
bool startGuest(Session &s, const Endpoint &host, unsigned nowMs) {
    if (!s.initialized || s.info.state != STOPPED || !validEndpoint(host)) return false;
    s.info.host = false; s.info.peer = host; s.info.state = JOINING;
    s.nowMs = s.startedMs = nowMs;
    tick(s, nowMs);
    return true;
}
void stop(Session &s) {
    if (s.info.connected) send(s, header(s, MSR_LEAVE, 0), 0);
    s.info.state = STOPPED; s.info.connected = s.info.pending = false;
    s.controlAck = s.handshakeAck = false;
    s.initialized = false;
}
Status status(const Session &s) { return s.info; }

void tick(Session &s, unsigned nowMs) {
    s.nowMs = nowMs;
    if (expired(s)) return;
    if (s.handshakeAck) sendHandshakeAck(s);
    if (!s.info.connected) {
        // Early HELLOs die at a NAT that is not open yet; retry at the reliable pace.
        if ((!s.handshakeSent || nowMs - s.lastHandshakeMs >= kRetryMs) &&
            ((s.info.state == JOINING && !s.guestAccepted && sendHello(s)) ||
             (s.info.state == ACCEPTING && sendAccept(s)))) {
            s.handshakeSent = true; s.lastHandshakeMs = nowMs;
        }
        return;
    }
    if (s.controlAck) sendControlAck(s);
    // Never resend before an ACK can be back: one RTT plus a frame or so of slack.
    const unsigned retryMs = s.info.pingMs < 1000u && s.info.pingMs + 60u > kRetryMs ? s.info.pingMs + 60u : kRetryMs;
    if (s.info.pending && nowMs - s.reliableSentMs >= retryMs &&
        send(s, s.pendingHeader, s.pendingData)) s.reliableSentMs = nowMs;
    if (!s.pingSent || nowMs - s.lastPingMs >= kHeartbeatMs) {
        unsigned char payload[4];
        unsigned sentMs = s.pingPending ? s.pingSentMs : nowMs;
        MSRWrite32(payload, sentMs);
        if (send(s, header(s, MSR_PING, 4, s.pingSequence), payload)) {
            s.pingPending = s.pingSent = true;
            s.pingSentMs = sentMs; s.lastPingMs = nowMs;
        }
    }
}

bool sendReliable(Session &s, unsigned kind, const void *data, unsigned bytes,
                  unsigned round) {
    if (!s.info.connected || s.info.pending || !reliableKind(kind) ||
        bytes > kReliableBytes || (bytes && !data)) return false;
    MSRHeader h = header(s, kind, bytes, s.sendSequence, round);
    if (!send(s, h, data)) return false;
    s.pendingHeader = h;
    if (bytes) copy(s.pendingData, data, bytes);
    s.info.pending = true;
    s.reliableSentMs = s.reliableStartedMs = s.nowMs;
    return true;
}
bool publishPose(Session &s, const MSRPose &pose, unsigned round) {
    unsigned char payload[MSR_POSE_BYTES];
    if (!s.info.connected || !MSREncodePose(payload, sizeof(payload), &pose) ||
        !send(s, header(s, MSR_POSE, sizeof(payload), s.poseSendSequence, round), payload, true))
        return false;
    ++s.poseSendSequence;
    return true;
}

bool receivePacket(Session &s, const Endpoint &from, const void *data,
                   unsigned bytes, unsigned nowMs) {
    MSRHeader h;
    s.nowMs = nowMs;
    if (expired(s) || !validEndpoint(from) || !MSRDecodeHeader(data, bytes, &h) ||
        h.participant > 1) return false;
    const unsigned char *p = static_cast<const unsigned char *>(data) + MSR_HEADER_BYTES;
    if (h.kind == MSR_HELLO) return acceptHello(s, from, h, p);
    if (h.kind == MSR_ACCEPT) return acceptOffer(s, from, h, p);
    if (!bound(s, from, h)) return false;
    if (h.kind == MSR_ACK && h.payloadBytes == 1 && p[0] == MSR_ACCEPT &&
        !h.sequence && !h.round && s.info.host) {
        if (s.info.state == ACCEPTING) connected(s);
        return s.info.connected;
    }
    if (!s.info.connected) return false;
    if (h.kind == MSR_POSE) {
        MSRPose pose;
        if (!MSRDecodePose(p, h.payloadBytes, &pose) ||
            (s.poseSeen && !MSRSequenceAfter(h.sequence, s.poseReceiveSequence))) return false;
        s.poseSeen = true; s.poseReceiveSequence = h.sequence;
        s.lastReceiveMs = nowMs;
        if (s.callbacks.onPose) s.callbacks.onPose(s.callbacks.context, h, pose, nowMs);
        return true;
    }
    if (reliableKind(h.kind)) {
        if (h.payloadBytes > kReliableBytes) return false;
        if (h.sequence == s.receiveSequence) {
            s.receivedHeader = h;
            if (h.payloadBytes) copy(s.receivedData, p, h.payloadBytes);
            ++s.receiveSequence; s.controlSeen = s.controlAck = true;
            s.lastReceiveMs = nowMs;
            sendControlAck(s);
            if (s.callbacks.onControl) s.callbacks.onControl(s.callbacks.context, h, p, h.payloadBytes);
            return true;
        }
        if (!s.controlSeen || h.sequence != s.receivedHeader.sequence ||
            h.kind != s.receivedHeader.kind || h.round != s.receivedHeader.round ||
            h.payloadBytes != s.receivedHeader.payloadBytes ||
            !equal(p, s.receivedData, h.payloadBytes)) return false;
        s.controlAck = true; s.lastReceiveMs = nowMs;
        sendControlAck(s);
        return true;
    }
    if (h.kind == MSR_ACK) {
        if (!s.info.pending || h.payloadBytes != 1 || p[0] != s.pendingHeader.kind ||
            h.sequence != s.pendingHeader.sequence || h.round != s.pendingHeader.round) return false;
        s.info.pending = false; ++s.sendSequence;
    } else if (h.kind == MSR_PING) {
        if (h.payloadBytes != 4 || h.round) return false;
        send(s, header(s, MSR_PONG, 4, h.sequence), p);
    } else if (h.kind == MSR_PONG) {
        if (h.payloadBytes != 4 || h.round || !s.pingPending ||
            h.sequence != s.pingSequence || MSRRead32(p) != s.pingSentMs) return false;
        s.info.pingMs = nowMs - s.pingSentMs;
        s.pingPending = false; ++s.pingSequence;
    } else if (h.kind == MSR_LEAVE) {
        if (h.payloadBytes || h.round || h.sequence) return false;
        fail(s, PEER_LEFT);
        return true;
    } else return false;
    s.lastReceiveMs = nowMs;
    return true;
}
}

// P2P codec begin
namespace LiveP2P {
namespace {
const char kAlphabet[] = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
const unsigned kMagic = 0x4d535031u; // "MSP1"
unsigned nextKey(unsigned &key) {
    key ^= key << 13; key ^= key >> 17; key ^= key << 5;
    return key;
}
unsigned checksum(const Code &code) {
    const unsigned char bytes[] = {code.endpoint.ip[0], code.endpoint.ip[1], code.endpoint.ip[2],
        code.endpoint.ip[3], static_cast<unsigned char>(code.endpoint.port >> 8),
        static_cast<unsigned char>(code.endpoint.port), static_cast<unsigned char>(code.secret >> 8),
        static_cast<unsigned char>(code.secret)};
    unsigned hash = 0x811c9dc5u;
    for (unsigned i = 0; i < sizeof(bytes); ++i) hash = (hash ^ bytes[i]) * 0x01000193u;
    return (hash ^ hash >> 11 ^ hash >> 22) & 0x1ffu;
}
bool usable(const Code &code) {
    return code.secret && code.secret <= SECRET_MAX && code.endpoint.port &&
        !code.endpoint.reserved && code.endpoint.ip[0] && code.endpoint.ip[0] < 224;
}
// Bytes 0-5 hold the endpoint under a keystream seeded by the secret; the
// last 22 bits hold secret and checksum under a fixed mask.
void mask(unsigned char *bytes, unsigned secret) {
    unsigned key = (secret * 0x9e3779b1u) ^ kMagic;
    for (unsigned i = 0; i < 6; ++i) bytes[i] ^= static_cast<unsigned char>(nextKey(key) >> 7);
}
const unsigned kWordMask = 0x2d5a93u;
bool samePeer(const TWLiveEndpoint &a, const TWLiveEndpoint &b) {
    return a.port == b.port && a.ip[0] == b.ip[0] && a.ip[1] == b.ip[1] &&
        a.ip[2] == b.ip[2] && a.ip[3] == b.ip[3];
}
unsigned read32(const unsigned char *p) {
    return static_cast<unsigned>(p[0]) << 24 | static_cast<unsigned>(p[1]) << 16 | p[2] << 8 | p[3];
}
void write32(unsigned char *p, unsigned value) {
    p[0] = static_cast<unsigned char>(value >> 24); p[1] = static_cast<unsigned char>(value >> 16);
    p[2] = static_cast<unsigned char>(value >> 8); p[3] = static_cast<unsigned char>(value);
}
}

bool encode(const Code &code, char *out) {
    if (!usable(code)) return false;
    unsigned char bytes[9];
    for (unsigned i = 0; i < 4; ++i) bytes[i] = code.endpoint.ip[i];
    bytes[4] = static_cast<unsigned char>(code.endpoint.port >> 8);
    bytes[5] = static_cast<unsigned char>(code.endpoint.port);
    mask(bytes, code.secret);
    const unsigned word = (code.secret << 9 | checksum(code)) ^ kWordMask;
    bytes[6] = static_cast<unsigned char>(word >> 14);
    bytes[7] = static_cast<unsigned char>(word >> 6);
    bytes[8] = static_cast<unsigned char>(word << 2);
    for (unsigned i = 0; i < CODE_CHARS; ++i) {
        unsigned value = 0;
        for (unsigned bit = 5 * i; bit < 5 * i + 5; ++bit)
            value = value << 1 | (bytes[bit >> 3] >> (7 - (bit & 7)) & 1u);
        out[i] = kAlphabet[value];
    }
    out[CODE_CHARS] = 0;
    return true;
}

bool decode(const char *text, Code *out) {
    unsigned char bytes[9] = {};
    unsigned count = 0;
    for (; *text; ++text) {
        char c = *text;
        if (c == '-' || c == ' ') continue;
        if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
        unsigned value = 0;
        while (kAlphabet[value] && kAlphabet[value] != c) ++value;
        if (!kAlphabet[value] || count == CODE_CHARS) return false;
        for (unsigned k = 0; k < 5; ++k) {
            const unsigned bit = 5 * count + k;
            if (value >> (4 - k) & 1u) bytes[bit >> 3] |= static_cast<unsigned char>(0x80u >> (bit & 7));
        }
        ++count;
    }
    if (count != CODE_CHARS) return false;
    const unsigned word = (static_cast<unsigned>(bytes[6]) << 14 | bytes[7] << 6 | bytes[8] >> 2) ^ kWordMask;
    Code code = {};
    code.secret = word >> 9;
    mask(bytes, code.secret);
    for (unsigned i = 0; i < 4; ++i) code.endpoint.ip[i] = bytes[i];
    code.endpoint.port = static_cast<unsigned short>(bytes[4] << 8 | bytes[5]);
    if (!usable(code) || (word & 0x1ffu) != checksum(code)) return false;
    *out = code;
    return true;
}

void format(const char *code, char *out) {
    unsigned o = 0;
    for (unsigned i = 0; i < CODE_CHARS && code[i]; ++i) {
        if (i && !(i & 3)) out[o++] = '-';
        out[o++] = code[i];
    }
    out[o] = 0;
}

char symbol(unsigned index) { return kAlphabet[index & 31u]; }

void reset(Punch &punch, unsigned pin, unsigned char self) {
    punch = Punch{};
    punch.pin = pin;
    punch.self = self;
}

int add(Punch &punch, const TWLiveEndpoint &endpoint, unsigned char participant) {
    int empty = -1;
    for (unsigned i = 0; i < MAX_PEERS - 1; ++i) {
        const Peer &peer = punch.peers[i];
        if (peer.state && samePeer(peer.endpoint, endpoint)) return static_cast<int>(i);
        if (!peer.state && empty < 0) empty = static_cast<int>(i);
    }
    if (empty < 0 || participant >= MAX_PEERS || participant == punch.self) return -1;
    Peer &peer = punch.peers[empty];
    peer = Peer{};
    peer.endpoint = endpoint;
    peer.endpoint.reserved = 0;
    peer.participant = participant;
    peer.state = PUNCHING;
    return empty;
}

unsigned due(Punch &punch, unsigned index, unsigned nowMs, unsigned char *packet,
             unsigned intervalMs) {
    if (index >= MAX_PEERS - 1) return 0;
    Peer &peer = punch.peers[index];
    if (!peer.state || (peer.sent && nowMs - peer.lastSentMs < intervalMs)) return 0;
    peer.sent = 1;
    peer.lastSentMs = nowMs;
    write32(packet, kMagic);
    write32(packet + 4, punch.pin);
    packet[8] = punch.self;
    packet[9] = peer.state == OPEN ? 1 : 0;   // "I hear you"
    packet[10] = packet[11] = 0;
    return PUNCH_BYTES;
}

unsigned roster(const Punch &punch, unsigned index, unsigned char *packet) {
    unsigned bytes = PUNCH_BYTES;
    if (punch.self != HOST || index >= MAX_PEERS - 1 || punch.peers[index].state != OPEN) return 0;
    for (unsigned i = 0; i < MAX_PEERS - 1; ++i) {
        const Peer &peer = punch.peers[i];
        if (i == index || peer.state != OPEN) continue;
        unsigned char *entry = packet + bytes;
        for (unsigned k = 0; k < 4; ++k) entry[k] = peer.endpoint.ip[k];
        entry[4] = static_cast<unsigned char>(peer.endpoint.port >> 8);
        entry[5] = static_cast<unsigned char>(peer.endpoint.port);
        entry[6] = peer.participant;
        entry[7] = 0;
        bytes += ROSTER_ENTRY_BYTES;
    }
    if (bytes == PUNCH_BYTES) return 0;
    write32(packet, kMagic);
    write32(packet + 4, punch.pin);
    packet[8] = HOST;
    packet[9] = 2;   // roster
    packet[10] = static_cast<unsigned char>((bytes - PUNCH_BYTES) / ROSTER_ENTRY_BYTES);
    packet[11] = 0;
    return bytes;
}

bool receive(Punch &punch, const TWLiveEndpoint &from, const void *data, unsigned bytes,
             unsigned nowMs, bool adopt) {
    const unsigned char *p = static_cast<const unsigned char *>(data);
    if (bytes < PUNCH_BYTES || read32(p) != kMagic) return false;
    if (read32(p + 4) != punch.pin || p[8] >= MAX_PEERS || p[8] == punch.self || p[9] > 2 || p[11])
        return true;
    int slot = -1;
    for (unsigned i = 0; i < MAX_PEERS - 1; ++i)
        if (punch.peers[i].state && samePeer(punch.peers[i].endpoint, from)) slot = static_cast<int>(i);
    if (p[9] == 2) {
        if (p[8] != HOST || slot < 0 || punch.peers[slot].state != OPEN ||
            bytes != PUNCH_BYTES + ROSTER_ENTRY_BYTES * p[10]) return true;
        for (const unsigned char *entry = p + PUNCH_BYTES; entry < p + bytes; entry += ROSTER_ENTRY_BYTES) {
            const TWLiveEndpoint peer = {{entry[0], entry[1], entry[2], entry[3]},
                static_cast<unsigned short>(entry[4] << 8 | entry[5]), 0};
            if (peer.port && peer.ip[0] && peer.ip[0] < 224 && entry[6] != HOST && !entry[7])
                add(punch, peer, entry[6]);
        }
        return true;
    }
    if (bytes != PUNCH_BYTES || p[10]) return true;
    if (slot < 0 && adopt) {
        // The player reached us from another port than its code says (its NAT maps
        // per destination): punch back to where it really is.
        for (unsigned i = 0; i < MAX_PEERS - 1; ++i)
            if (punch.peers[i].state == PUNCHING && punch.peers[i].participant == p[8]) slot = static_cast<int>(i);
        if (slot >= 0) { punch.peers[slot].endpoint = from; punch.peers[slot].endpoint.reserved = 0; }
        else slot = add(punch, from, p[8]);
    }
    if (slot < 0) return true;
    Peer &peer = punch.peers[slot];
    peer.state = OPEN;
    peer.lastHeardMs = nowMs;
    peer.participant = p[8];
    return true;
}

bool open(const Punch &punch) {
    for (unsigned i = 0; i < MAX_PEERS - 1; ++i)
        if (punch.peers[i].state == OPEN) return true;
    return false;
}
}
// P2P codec end
#endif
