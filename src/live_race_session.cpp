#include "susamune/live_race_session.hxx"

#if TIMEWARP_LIVE_RACING
namespace LiveRaceSession {
namespace {
const unsigned kHandshakeMs = 30000, kTimeoutMs = 10000;
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
        if ((!s.handshakeSent || nowMs - s.lastHandshakeMs >= kHeartbeatMs) &&
            ((s.info.state == JOINING && !s.guestAccepted && sendHello(s)) ||
             (s.info.state == ACCEPTING && sendAccept(s)))) {
            s.handshakeSent = true; s.lastHandshakeMs = nowMs;
        }
        return;
    }
    if (s.controlAck) sendControlAck(s);
    if (s.info.pending && nowMs - s.reliableSentMs >= kRetryMs &&
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
#endif
