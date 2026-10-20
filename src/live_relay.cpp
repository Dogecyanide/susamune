#include "susamune/live_relay.hxx"

#if TIMEWARP_LIVE_RACING
namespace LiveRelay {
namespace {
bool equal(const unsigned char *a, const unsigned char *b, unsigned bytes) {
    unsigned difference = 0;
    for (unsigned i = 0; i < bytes; ++i) difference |= a[i] ^ b[i];
    return !difference;
}
bool nonzero(const unsigned char *p, unsigned bytes) {
    unsigned value = 0;
    for (unsigned i = 0; i < bytes; ++i) value |= p[i];
    return value != 0;
}
void fail(Client &c, Error error) {
    c.info.state = FAILED; c.info.error = error; c.info.peerReady = false;
}
bool emit(Client &c, unsigned kind, const void *data, unsigned bytes, bool pose) {
    unsigned char packet[256];
    MSLHeader h = c.identity;
    h.kind = (unsigned char)kind; h.payloadBytes = (unsigned short)bytes;
    h.flags = c.info.host ? MSL_HOST : 0;
    MSLEncode(packet, &h);
    for (unsigned i = 0; i < bytes; ++i)
        packet[MSL_HEADER_BYTES + i] = ((const unsigned char *)data)[i];
    return (pose ? c.callbacks.sendLatestPose : c.callbacks.sendControl)(
        c.callbacks.context, c.server, packet, MSL_HEADER_BYTES + bytes);
}
bool authenticated(const Client &c, const MSLHeader &h) {
    return h.room == c.identity.room &&
        h.generationHigh == c.identity.generationHigh &&
        h.generationLow == c.identity.generationLow &&
        equal(h.token, c.identity.token, 16);
}
bool forward(Client &c, const void *inner, unsigned bytes, bool pose) {
    MSRHeader header;
    if (c.info.state != READY || bytes > MSL_INNER_MAX ||
        !MSRDecodeHeader(inner, bytes, &header) ||
        header.participant != (c.info.host ? 0 : 1)) return false;
    return emit(c, MSL_DATA, inner, bytes, pose);
}
}

bool init(Client &c, const Callbacks &callbacks) {
    c = Client(); c.callbacks = callbacks;
    c.initialized = callbacks.sendControl && callbacks.sendLatestPose && callbacks.onPacket;
    if (!c.initialized) fail(c, INVALID_CONFIG);
    return c.initialized;
}
bool begin(Client &c, bool host, unsigned room, unsigned high, unsigned low,
           const Endpoint &server, unsigned now) {
    if (!c.initialized || (c.info.state != STOPPED && c.info.state != FAILED)) return false;
    if (!(high | low) || (host ? room != 0 : room < 100000 || room > 999999) ||
        !server.port || !nonzero(server.ip, 4) || server.ip[0] >= 224 ||
        server.ip[0] == 0 || server.reserved) {
        fail(c, INVALID_CONFIG); return false;
    }
    Callbacks callbacks = c.callbacks; init(c, callbacks);
    c.server = server; c.info.host = host; c.info.state = OPENING;
    c.requestedRoom = room; c.info.roomCode = room;
    c.identity.room = room; c.identity.nonceHigh = high; c.identity.nonceLow = low;
    c.nowMs = c.startedMs = c.receivedMs = now;
    tick(c, now);
    return true;
}
void tick(Client &c, unsigned now) {
    c.nowMs = now;
    if (c.info.state == STOPPED || c.info.state == FAILED) return;
    bool opening = c.info.state == OPENING || c.info.state == PROVING;
    if (now - (opening ? c.startedMs : c.receivedMs) >= 15000) {
        fail(c, SERVER_TIMEOUT); return;
    }
    if (c.sent && now - c.sentMs < (opening ? 500u : 1000u)) return;
    unsigned kind = c.info.state == OPENING ? MSL_OPEN :
                    c.info.state == PROVING ? MSL_PROVE : MSL_KEEPALIVE;
    if (emit(c, kind, 0, 0, false)) { c.sent = true; c.sentMs = now; }
}
bool receive(Client &c, const Endpoint &from, const void *data, unsigned bytes, unsigned now) {
    MSLHeader h;
    if (c.info.state == STOPPED || c.info.state == FAILED || from.port != c.server.port ||
        !equal(from.ip, c.server.ip, 4) || !MSLDecode(data, bytes, &h) ||
        h.nonceHigh != c.identity.nonceHigh || h.nonceLow != c.identity.nonceLow ||
        (h.flags & MSL_HOST) != (c.info.host ? MSL_HOST : 0)) return false;
    const unsigned char *payload = (const unsigned char *)data + MSL_HEADER_BYTES;
    bool opening = c.info.state == OPENING || c.info.state == PROVING;
    if (opening && h.kind == MSL_CHALLENGE) {
        if (h.room != c.requestedRoom || h.payloadBytes || h.generationHigh ||
            h.generationLow || (h.flags & MSL_PEER_READY) || !nonzero(h.token, 16)) return false;
        for (unsigned i = 0; i < 16; ++i) c.challenge[i] = c.identity.token[i] = h.token[i];
        c.info.state = PROVING; c.sent = false; tick(c, now); return true;
    }
    if (c.info.state == PROVING && h.kind == MSL_WELCOME) {
        if (h.payloadBytes != 16 || !equal(payload, c.challenge, 16) ||
            !nonzero(h.token, 16) || !(h.generationHigh | h.generationLow) ||
            h.room < 100000 || (!c.info.host && h.room != c.requestedRoom)) return false;
        c.identity = h; c.info.roomCode = h.room;
        c.info.peerReady = (h.flags & MSL_PEER_READY) != 0;
        c.info.state = c.info.peerReady ? READY : WAITING;
        c.receivedMs = now; c.sent = false; return true;
    }
    if (h.kind == MSL_ERROR) {
        if (h.payloadBytes != 4 || (h.flags & MSL_PEER_READY)) return false;
        if (opening) {
            if (c.info.state != PROVING || h.room != c.requestedRoom ||
                h.generationHigh || h.generationLow || !equal(h.token, c.challenge, 16)) return false;
        } else if (!authenticated(c, h)) return false;
        unsigned error = MSRRead32(payload);
        if (error < NO_ROOM || error > LOBBY_EXPIRED) return false;
        fail(c, (Error)error); return true;
    }
    if (opening || !authenticated(c, h)) return false;
    if (h.kind == MSL_STATUS) {
        if (h.payloadBytes) return false;
        if (h.flags & MSL_PEER_READY) { c.info.peerReady = true; c.info.state = READY; }
        c.receivedMs = now; return true;
    }
    if (h.kind != MSL_DATA || !(h.flags & MSL_PEER_READY)) return false;
    MSRHeader inner;
    if (!MSRDecodeHeader(payload, h.payloadBytes, &inner) ||
        inner.participant != (c.info.host ? 1 : 0)) return false;
    c.info.peerReady = true; c.info.state = READY; c.receivedMs = now;
    c.callbacks.onPacket(c.callbacks.context, payload, h.payloadBytes, now);
    return true;
}
bool sendControl(Client &c, const void *data, unsigned bytes) { return forward(c, data, bytes, false); }
bool sendPose(Client &c, const void *data, unsigned bytes) { return forward(c, data, bytes, true); }
void stop(Client &c) {
    if (c.info.state == WAITING || c.info.state == READY) emit(c, MSL_LEAVE, 0, 0, false);
    c.info.state = STOPPED; c.info.peerReady = false;
}
Status status(const Client &c) { return c.info; }
}
#endif
