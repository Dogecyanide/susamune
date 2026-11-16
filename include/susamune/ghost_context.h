#ifndef SUSAMUNE_GHOST_CONTEXT_H
#define SUSAMUNE_GHOST_CONTEXT_H

#include "susamune/ghost_camera.h"
#include "susamune/ghost_simulation_settings.h"

#define SUSAMUNE_GHOST_CONTEXT_MAGIC 0x53474358u
#define SUSAMUNE_GHOST_CONTEXT_VERSION 1u
#define SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE 32u
#define SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE 96u
#define SUSAMUNE_GHOST_CONTEXT_SETTINGS_SCHEMA 1u
#define SUSAMUNE_GHOST_CONTEXT_MAX_COUNT 169u
#define SUSAMUNE_GHOST_CONTEXT_MAX_SIZE (32u + 169u * 96u)
#define SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET \
    (SUSAMUNE_GHOST_CAMERA_BANK_OFFSET + SUSAMUNE_GHOST_CAMERA_MAX_SIZE)
#define SUSAMUNE_GHOST_CONTEXT_TRUNCATED 1u
#define SUSAMUNE_GHOST_CONTEXT_SEGMENT 1u
#define SUSAMUNE_GHOST_CONTEXT_SETTINGS 2u
#define SUSAMUNE_GHOST_CONTEXT_INPUT_GAP 3u
#define SUSAMUNE_GHOST_CONTEXT_RESTORE 4u
#define SUSAMUNE_GHOST_CONTEXT_HELD_END 5u
#define SUSAMUNE_GHOST_CONTEXT_INTERPOLATED_END 6u
#define SUSAMUNE_GHOST_CONTEXT_SEED_KNOWN 1u
#define SUSAMUNE_GHOST_CONTEXT_AGE_KNOWN 2u
#define SUSAMUNE_GHOST_CONTEXT_CAMERA_KNOWN 4u
#define SUSAMUNE_GHOST_CONTEXT_YAW_VARIED 8u
#define SUSAMUNE_GHOST_CONTEXT_SYNTHETIC_START 16u
#define SUSAMUNE_GHOST_CONTEXT_RESTORED 32u
#define SUSAMUNE_GHOST_CONTEXT_BEFORE_INPUTS 64u
#define SUSAMUNE_GHOST_CONTEXT_FLAGS 127u

struct SusamuneGhostContextHeader {
    unsigned int magic;
    unsigned short version, headerSize;
    unsigned int count, flags, dataChecksum;
    unsigned short recordSize, settingsSchema;
    unsigned int reserved[2];
};

/* Observations describe capture provenance, not a complete replay state. */
struct SusamuneGhostContextRecord {
    unsigned int captureQf, inputIndex, sourceFrameSerial;
    unsigned int movementTicks, directorTicks, preSetupSeed;
    unsigned short segment;
    unsigned char kind, flags;
    short cameraYaw;
    unsigned short cameraMode;
    unsigned char settings[64];
};

static inline unsigned int SusamuneGhostContextHalf(const unsigned char *p) {
    return ((unsigned int)p[0] << 8) | p[1];
}

static inline int SusamuneGhostContextHeaderValid(const unsigned char *p,
                                                 unsigned int size) {
    unsigned int count;
    if (size < SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE ||
        SusamuneGhostReadBe32(p) != SUSAMUNE_GHOST_CONTEXT_MAGIC ||
        SusamuneGhostContextHalf(p + 4) != SUSAMUNE_GHOST_CONTEXT_VERSION ||
        SusamuneGhostContextHalf(p + 6) != SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE ||
        (SusamuneGhostReadBe32(p + 12) & ~SUSAMUNE_GHOST_CONTEXT_TRUNCATED) ||
        SusamuneGhostContextHalf(p + 20) != SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE ||
        SusamuneGhostContextHalf(p + 22) != SUSAMUNE_GHOST_CONTEXT_SETTINGS_SCHEMA ||
        SusamuneGhostReadBe32(p + 24) || SusamuneGhostReadBe32(p + 28)) return 0;
    count = SusamuneGhostReadBe32(p + 8);
    return count <= SUSAMUNE_GHOST_CONTEXT_MAX_COUNT &&
        size == SUSAMUNE_GHOST_CONTEXT_HEADER_SIZE + count * SUSAMUNE_GHOST_CONTEXT_RECORD_SIZE;
}

static inline int SusamuneGhostContextRecordValid(const unsigned char *p,
        unsigned int segmentCount, unsigned int inputCount,
        unsigned int segmentStartQf, unsigned int segmentEndQf,
        const unsigned char *previous) {
    const unsigned int qf = SusamuneGhostReadBe32(p);
    const unsigned int input = SusamuneGhostReadBe32(p + 4);
    const unsigned int segment = SusamuneGhostContextHalf(p + 24);
    const unsigned int kind = p[26], flags = p[27];
    if (segment >= segmentCount || qf < segmentStartQf || qf > segmentEndQf ||
        input > inputCount || SusamuneGhostContextHalf(p + 30) > 0x49u ||
        kind < SUSAMUNE_GHOST_CONTEXT_SEGMENT ||
        kind > SUSAMUNE_GHOST_CONTEXT_INTERPOLATED_END ||
        (flags & ~SUSAMUNE_GHOST_CONTEXT_FLAGS) ||
        ((flags & SUSAMUNE_GHOST_CONTEXT_BEFORE_INPUTS) && input) ||
        (!(flags & SUSAMUNE_GHOST_CONTEXT_SEED_KNOWN) && SusamuneGhostReadBe32(p + 20)) ||
        (!(flags & SUSAMUNE_GHOST_CONTEXT_AGE_KNOWN) &&
            (SusamuneGhostReadBe32(p + 12) || SusamuneGhostReadBe32(p + 16))) ||
        (!(flags & SUSAMUNE_GHOST_CONTEXT_CAMERA_KNOWN) &&
            (SusamuneGhostReadBe32(p + 28) || (flags & SUSAMUNE_GHOST_CONTEXT_YAW_VARIED))) ||
        ((flags & SUSAMUNE_GHOST_CONTEXT_SYNTHETIC_START) && kind != SUSAMUNE_GHOST_CONTEXT_SEGMENT) ||
        (kind == SUSAMUNE_GHOST_CONTEXT_RESTORE && !(flags & SUSAMUNE_GHOST_CONTEXT_RESTORED)) ||
        (kind >= SUSAMUNE_GHOST_CONTEXT_HELD_END && qf != segmentEndQf) ||
        !SusamuneGhostSimulationSettingsValid(p + 32)) return 0;
    if (previous) {
        const unsigned int priorSegment = SusamuneGhostContextHalf(previous + 24);
        if (segment < priorSegment || qf < SusamuneGhostReadBe32(previous) ||
            (kind != SUSAMUNE_GHOST_CONTEXT_RESTORE && input < SusamuneGhostReadBe32(previous + 4))) return 0;
        if (segment == priorSegment &&
            (kind == SUSAMUNE_GHOST_CONTEXT_SEGMENT || previous[26] >= SUSAMUNE_GHOST_CONTEXT_HELD_END)) return 0;
    }
    return 1;
}

typedef char SusamuneGhostContextHeaderSize[
    sizeof(struct SusamuneGhostContextHeader) == 32 ? 1 : -1];
typedef char SusamuneGhostContextRecordSize[
    sizeof(struct SusamuneGhostContextRecord) == 96 ? 1 : -1];
typedef char SusamuneGhostContextBankBounds[
    SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET + SUSAMUNE_GHOST_CONTEXT_MAX_SIZE <= 0x695e0u ? 1 : -1];

#endif
