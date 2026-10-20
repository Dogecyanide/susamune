#ifndef SUSAMUNE_GHOST_CAMERA_H
#define SUSAMUNE_GHOST_CAMERA_H

#include "susamune/ghost_teaching.h"

#define SUSAMUNE_GHOST_CAMERA_MAGIC 0x53474341u
#define SUSAMUNE_GHOST_CAMERA_VERSION 1u
#define SUSAMUNE_GHOST_CAMERA_HEADER_SIZE 32u
#define SUSAMUNE_GHOST_CAMERA_SAMPLE_SIZE 24u
#define SUSAMUNE_GHOST_CAMERA_MAX_COUNT 5312u
#define SUSAMUNE_GHOST_CAMERA_INTERVAL_QF 15u
#define SUSAMUNE_GHOST_CAMERA_CUT 0x40u
#define SUSAMUNE_GHOST_CAMERA_TRUNCATED 1u
#define SUSAMUNE_GHOST_CAMERA_BANK_OFFSET (17983u * 16u)
#define SUSAMUNE_GHOST_CAMERA_MAX_SIZE (32u + 5312u * 24u)

struct SusamuneGhostCameraHeader {
    unsigned int magic;
    unsigned short version, headerSize;
    unsigned int count, flags, dataChecksum;
    unsigned int reserved[3];
};

/* qf32, xyz signed24 at quarter units, xyzw signed16 /32767,
   fovy16 in 1/256 degrees, segment6 + cut1 + reserved1. */
struct SusamuneGhostCameraSample { unsigned char bytes[24]; };

static int SusamuneGhostCameraHeaderValid(const unsigned char *p,
                                         unsigned int size) {
    unsigned int count;
    if (size < 32 || SusamuneGhostReadBe32(p) != SUSAMUNE_GHOST_CAMERA_MAGIC ||
        p[4] || p[5] != 1 || p[6] || p[7] != 32) return 0;
    count = SusamuneGhostReadBe32(p + 8);
    return count <= SUSAMUNE_GHOST_CAMERA_MAX_COUNT &&
        !(SusamuneGhostReadBe32(p + 12) & ~SUSAMUNE_GHOST_CAMERA_TRUNCATED) &&
        !SusamuneGhostReadBe32(p + 20) && !SusamuneGhostReadBe32(p + 24) &&
        !SusamuneGhostReadBe32(p + 28) && size == 32 + count * 24;
}

static int SusamuneGhostCameraSampleValid(const unsigned char *p,
        unsigned int startQf, unsigned int endQf, unsigned int previousQf,
        unsigned int segment, unsigned int previousSegment, int first) {
    unsigned int qf = SusamuneGhostReadBe32(p);
    unsigned int fov = ((unsigned int)p[21] << 8) | p[22];
    unsigned long long norm = 0;
    unsigned int i;
    if ((p[23] & 0x80u) || (p[23] & 63u) != segment ||
        qf < startQf || qf > endQf || fov < 256 || fov > 179u * 256 ||
        (!first && (segment < previousSegment || qf < previousQf ||
                    (segment == previousSegment && qf == previousQf))) ||
        ((first || segment != previousSegment) && !(p[23] & 0x40u))) return 0;
    for (i = 0; i < 4; ++i) {
        int v = (short)(((unsigned int)p[13 + 2*i] << 8) | p[14 + 2*i]);
        norm += (unsigned long long)((long long)v * v);
    }
    return norm >= 1073479689ull && norm <= 1073879689ull;
}

#endif
