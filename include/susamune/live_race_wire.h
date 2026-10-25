#ifndef SUSAMUNE_LIVE_RACE_WIRE_H
#define SUSAMUNE_LIVE_RACE_WIRE_H

#include "ghost_fludd.h"

enum {
    // V7 omits controller inputs from group poses and supports host removal.
    MSR_PROTOCOL = 7, MSR_FORFEIT_QF = -2, MSR_HEADER_BYTES = 32, MSR_MAX_PACKET_BYTES = 256,
    MSR_POSE_BYTES = 56, MSR_POSE_BASE_BYTES = 48, MSR_GROUP_ENTRY_BYTES = 56, MSR_NAME_BYTES = 16, MSR_INPUT_BUTTON_MASK = 0x1f7f,
    MSR_HELLO = 1, MSR_ACCEPT, MSR_POSE, MSR_PING, MSR_PONG,
    MSR_LEAVE, MSR_READY, MSR_START, MSR_RESULT, MSR_ACK, MSR_GROUP_POSES,
    MSR_TIMING_60HZ = 1, MSR_VISIBLE = 1,
    MSR_ANIMATION_COUNT = 336, MSR_ANIMATION_PHASE_MAX = 4095, MSR_YOSHI_MAX = 5
};

/* Wire regions follow SGHF (JP=0, US=1, PAL=2), not game-build IDs. */
typedef struct MSRHeader {
    unsigned int sequence, sessionHigh, sessionLow, round;
    unsigned short payloadBytes;
    unsigned char kind, region, timing, participant;
} MSRHeader;

typedef struct MSRPose {
    unsigned int remoteMs, sceneEpoch, heldObjectId;
    int x, y, z; /* Game coordinates multiplied by eight. */
    unsigned short yaw, animation, phase, heldNameKey;
    unsigned char area, episode, parentArea, parentEpisode, yoshi, flags;
    unsigned char fludd[8];
    unsigned short buttons;
    signed char stickX, stickY, substickX, substickY;
    unsigned char triggerL, triggerR;
} MSRPose;

static inline unsigned int MSRRead16(const unsigned char *p) {
    return ((unsigned int)p[0] << 8) | p[1];
}
static inline unsigned int MSRRead32(const unsigned char *p) {
    return (MSRRead16(p) << 16) | MSRRead16(p + 2);
}
static inline void MSRWrite16(unsigned char *p, unsigned int value) {
    p[0] = (unsigned char)(value >> 8); p[1] = (unsigned char)value;
}
static inline void MSRWrite32(unsigned char *p, unsigned int value) {
    MSRWrite16(p, value >> 16); MSRWrite16(p + 2, value);
}
static inline int MSRReadSigned32(const unsigned char *p) {
    unsigned int value = MSRRead32(p);
    return value <= 0x7fffffffu ? (int)value : -1 - (int)(~value);
}
static inline int MSRSequenceAfter(unsigned int next, unsigned int previous) {
    unsigned int delta = next - previous;
    return delta && delta < 0x80000000u;
}
static inline int MSRHeaderValid(const MSRHeader *h) {
    return h && h->kind >= MSR_HELLO && h->kind <= MSR_GROUP_POSES &&
        h->payloadBytes <= MSR_MAX_PACKET_BYTES - MSR_HEADER_BYTES &&
        h->region < 3 && h->timing == MSR_TIMING_60HZ && h->participant < 4;
}
static inline int MSRDecodeHeader(const void *data, unsigned int bytes,
                                MSRHeader *out) {
    const unsigned char *p = (const unsigned char *)data;
    MSRHeader h;
    if (!p || !out || bytes < MSR_HEADER_BYTES || bytes > MSR_MAX_PACKET_BYTES ||
        MSRRead32(p) != 0x4d535231u || MSRRead16(p + 4) != MSR_PROTOCOL ||
        p[7] || MSRRead16(p + 10) || p[31]) return 0;
    h.kind = p[6]; h.payloadBytes = (unsigned short)MSRRead16(p + 8);
    h.sequence = MSRRead32(p + 12);
    h.sessionHigh = MSRRead32(p + 16); h.sessionLow = MSRRead32(p + 20);
    h.round = MSRRead32(p + 24);
    h.region = p[28]; h.timing = p[29]; h.participant = p[30];
    if (!MSRHeaderValid(&h) || bytes != MSR_HEADER_BYTES + h.payloadBytes) return 0;
    *out = h;
    return 1;
}
static inline int MSREncodeHeader(void *data, unsigned int capacity,
                                const MSRHeader *h) {
    unsigned char *p = (unsigned char *)data;
    if (!p || !MSRHeaderValid(h) || capacity < MSR_HEADER_BYTES + h->payloadBytes)
        return 0;
    MSRWrite32(p, 0x4d535231u); MSRWrite16(p + 4, MSR_PROTOCOL);
    p[6] = h->kind; p[7] = 0;
    MSRWrite16(p + 8, h->payloadBytes); MSRWrite16(p + 10, 0);
    MSRWrite32(p + 12, h->sequence);
    MSRWrite32(p + 16, h->sessionHigh); MSRWrite32(p + 20, h->sessionLow);
    MSRWrite32(p + 24, h->round);
    p[28] = h->region; p[29] = h->timing; p[30] = h->participant; p[31] = 0;
    return 1;
}

static inline int MSRPoseValid(const MSRPose *p) {
    return p && p->x >= -8000000 && p->x <= 8000000 &&
        p->y >= -8000000 && p->y <= 8000000 && p->z >= -8000000 && p->z <= 8000000 &&
        p->animation < MSR_ANIMATION_COUNT && p->phase <= MSR_ANIMATION_PHASE_MAX &&
        p->yoshi <= MSR_YOSHI_MAX &&
        !(p->flags & ~MSR_VISIBLE) && !(p->buttons & ~MSR_INPUT_BUTTON_MASK) &&
        SusamuneGhostVisualValid(p->fludd, 1) &&
        (!(p->fludd[0] & SUSAMUNE_GHOST_VISUAL_YOSHI) || p->yoshi != 0);
}
static inline int MSRDecodePose(const void *data, unsigned int bytes, MSRPose *out) {
    const unsigned char *p = (const unsigned char *)data;
    MSRPose pose = {0};
    if (!p || !out || (bytes != MSR_POSE_BYTES && bytes != MSR_POSE_BASE_BYTES) || MSRRead16(p + 38)) return 0;
    pose.area = p[0]; pose.episode = p[1]; pose.parentArea = p[2]; pose.parentEpisode = p[3];
    pose.remoteMs = MSRRead32(p + 4); pose.sceneEpoch = MSRRead32(p + 8);
    pose.x = MSRReadSigned32(p + 12); pose.y = MSRReadSigned32(p + 16);
    pose.z = MSRReadSigned32(p + 20);
    pose.yaw = (unsigned short)MSRRead16(p + 24);
    pose.animation = (unsigned short)MSRRead16(p + 26);
    pose.phase = (unsigned short)MSRRead16(p + 28);
    pose.heldNameKey = (unsigned short)MSRRead16(p + 30);
    pose.heldObjectId = MSRRead32(p + 32); pose.yoshi = p[36]; pose.flags = p[37];
    for (unsigned int i = 0; i < 8; ++i) pose.fludd[i] = p[40 + i];
    if (bytes == MSR_POSE_BYTES) {
    pose.buttons = (unsigned short)MSRRead16(p + 48);
    pose.stickX = (signed char)p[50]; pose.stickY = (signed char)p[51];
    pose.substickX = (signed char)p[52]; pose.substickY = (signed char)p[53];
    pose.triggerL = p[54]; pose.triggerR = p[55];
    }
    if (!MSRPoseValid(&pose)) return 0;
    *out = pose;
    return 1;
}
static inline int MSREncodePose(void *data, unsigned int capacity, const MSRPose *pose) {
    unsigned char *p = (unsigned char *)data;
    if (!p || capacity < MSR_POSE_BYTES || !MSRPoseValid(pose)) return 0;
    p[0] = pose->area; p[1] = pose->episode; p[2] = pose->parentArea; p[3] = pose->parentEpisode;
    MSRWrite32(p + 4, pose->remoteMs); MSRWrite32(p + 8, pose->sceneEpoch);
    MSRWrite32(p + 12, (unsigned int)pose->x); MSRWrite32(p + 16, (unsigned int)pose->y);
    MSRWrite32(p + 20, (unsigned int)pose->z);
    MSRWrite16(p + 24, pose->yaw); MSRWrite16(p + 26, pose->animation);
    MSRWrite16(p + 28, pose->phase); MSRWrite16(p + 30, pose->heldNameKey);
    MSRWrite32(p + 32, pose->heldObjectId); p[36] = pose->yoshi; p[37] = pose->flags;
    MSRWrite16(p + 38, 0);
    for (unsigned int i = 0; i < 8; ++i) p[40 + i] = pose->fludd[i];
    MSRWrite16(p + 48, pose->buttons);
    p[50] = (unsigned char)pose->stickX; p[51] = (unsigned char)pose->stickY;
    p[52] = (unsigned char)pose->substickX; p[53] = (unsigned char)pose->substickY;
    p[54] = pose->triggerL; p[55] = pose->triggerR;
    return 1;
}

#endif
