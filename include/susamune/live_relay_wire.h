#ifndef SUSAMUNE_LIVE_RELAY_WIRE_H
#define SUSAMUNE_LIVE_RELAY_WIRE_H

#include "live_race_wire.h"

enum {
    MSL_PROTOCOL = 1, MSL_HEADER_BYTES = 48, MSL_INNER_MAX = 208,
    MSL_OPEN = 1, MSL_CHALLENGE, MSL_PROVE, MSL_WELCOME, MSL_KEEPALIVE,
    MSL_STATUS, MSL_DATA, MSL_LEAVE, MSL_ERROR,
    MSL_HOST = 1, MSL_PEER_READY = 2
};
typedef struct MSLHeader {
    unsigned room, nonceHigh, nonceLow, generationHigh, generationLow;
    unsigned char token[16];
    unsigned short payloadBytes;
    unsigned char kind, flags;
} MSLHeader;

static inline int MSLDecode(const void *data, unsigned bytes, MSLHeader *out) {
    const unsigned char *p = (const unsigned char *)data;
    MSLHeader h;
    if (!p || !out || bytes < MSL_HEADER_BYTES || bytes > 256 ||
        MSRRead32(p) != 0x4d534c31u || p[4] != MSL_PROTOCOL || p[7] ||
        MSRRead16(p + 46) || p[5] < MSL_OPEN || p[5] > MSL_ERROR ||
        (p[6] & ~(MSL_HOST | MSL_PEER_READY))) return 0;
    h.kind = p[5]; h.flags = p[6]; h.room = MSRRead32(p + 8);
    h.nonceHigh = MSRRead32(p + 12); h.nonceLow = MSRRead32(p + 16);
    for (unsigned i = 0; i < 16; ++i) h.token[i] = p[20 + i];
    h.generationHigh = MSRRead32(p + 36); h.generationLow = MSRRead32(p + 40);
    h.payloadBytes = (unsigned short)MSRRead16(p + 44);
    if (h.room > 999999 || !(h.nonceHigh | h.nonceLow) ||
        bytes != MSL_HEADER_BYTES + h.payloadBytes) return 0;
    *out = h;
    return 1;
}
static inline void MSLEncode(void *data, const MSLHeader *h) {
    unsigned char *p = (unsigned char *)data;
    MSRWrite32(p, 0x4d534c31u); p[4] = MSL_PROTOCOL; p[5] = h->kind;
    p[6] = h->flags; p[7] = 0; MSRWrite32(p + 8, h->room);
    MSRWrite32(p + 12, h->nonceHigh); MSRWrite32(p + 16, h->nonceLow);
    for (unsigned i = 0; i < 16; ++i) p[20 + i] = h->token[i];
    MSRWrite32(p + 36, h->generationHigh); MSRWrite32(p + 40, h->generationLow);
    MSRWrite16(p + 44, h->payloadBytes); MSRWrite16(p + 46, 0);
}
#endif
