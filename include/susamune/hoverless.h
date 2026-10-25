#ifndef SUSAMUNE_HOVERLESS_H
#define SUSAMUNE_HOVERLESS_H

#include "susamune/susamune_cfg.h"

#define SUSAMUNE_HOVERLESS_MAGIC 0x53485652u
#define SUSAMUNE_HOVERLESS_VERSION 1u
#define SUSAMUNE_HOVERLESS_RULE 1u
#define SUSAMUNE_HOVERLESS_PROFILE 4u
#define SUSAMUNE_HOVERLESS_GHOST_PROFILE 5u
#define SUSAMUNE_HOVERLESS_FLAG 0x04000000u
#define SUSAMUNE_HOVERLESS_CFG_OFFSET 0x1A20u
#define SUSAMUNE_HOVERLESS_LIVE_OFFSET 0x1C80u
#define SUSAMUNE_HOVERLESS_WRITABLE 1u
#define SUSAMUNE_HOVERLESS_INHERIT_PROFILE 255u

struct SusamuneHoverlessCfg {
    unsigned int magic;
    unsigned short version, rule;
    unsigned short count;
    unsigned char activeProfile, flags;
    unsigned int saveSeq;
    unsigned char reserved[16];
    unsigned int ackSeq, status;
    unsigned char pad[24];
    signed int values[SUSAMUNE_ILING_PB_MAX_SLOTS];
};

struct SusamuneHoverlessFile {
    unsigned int magic;
    unsigned short version, rule;
    unsigned short count;
    unsigned char activeProfile, reserved0;
    unsigned int gameId, generation, checksum;
    unsigned char reserved[8];
    signed int values[SUSAMUNE_ILING_PB_MAX_SLOTS];
};

#if IS_EMULATOR
#define SUSAMUNE_HOVERLESS_PPC_PTR ((struct SusamuneHoverlessCfg *)0x71900140u)
#define SUSAMUNE_HOVERLESS_VALUES ((signed int *)0x719003A0u)
#else
#define SUSAMUNE_HOVERLESS_PPC_PTR ((struct SusamuneHoverlessCfg *)(SUSAMUNE_MEM2_CFG_PPC_BASE + SUSAMUNE_HOVERLESS_CFG_OFFSET))
#define SUSAMUNE_HOVERLESS_VALUES ((signed int *)(SUSAMUNE_MEM2_CFG_PPC_BASE + SUSAMUNE_HOVERLESS_LIVE_OFFSET))
#endif
#define SUSAMUNE_HOVERLESS_PHYS_PTR ((struct SusamuneHoverlessCfg *)(SUSAMUNE_MEM2_CFG_PHYS_BASE + SUSAMUNE_HOVERLESS_CFG_OFFSET))

static inline int SusamuneHoverlessProfileValid(unsigned int profile) {
    return profile <= SUSAMUNE_HOVERLESS_PROFILE || profile == SUSAMUNE_HOVERLESS_INHERIT_PROFILE;
}
static inline unsigned int SusamuneHoverlessChecksum(const struct SusamuneHoverlessFile *file) {
    const unsigned char *p = (const unsigned char *)file;
    unsigned int hash = 2166136261u, i;
    for (i = 0; i < sizeof(*file); ++i)
        hash = (hash ^ ((i >= 20 && i < 24) ? 0 : p[i])) * 16777619u;
    return hash;
}
static inline int SusamuneHoverlessValid(const struct SusamuneHoverlessFile *file, unsigned int gameId) {
    unsigned int i;
    if (file->magic != SUSAMUNE_HOVERLESS_MAGIC || file->version != SUSAMUNE_HOVERLESS_VERSION ||
        file->rule != SUSAMUNE_HOVERLESS_RULE || file->count != SUSAMUNE_ILING_PB_MAX_SLOTS ||
        !SusamuneHoverlessProfileValid(file->activeProfile) || file->gameId != gameId ||
        file->checksum != SusamuneHoverlessChecksum(file)) return 0;
    for (i = 0; i < SUSAMUNE_ILING_PB_MAX_SLOTS; ++i)
        if (file->values[i] < -1 || file->values[i] > SUSAMUNE_ILING_PB_MAX_QF) return 0;
    return 1;
}

typedef char hoverless_mailbox_size[(sizeof(struct SusamuneHoverlessCfg) == 608) ? 1 : -1];
typedef char hoverless_file_size[(sizeof(struct SusamuneHoverlessFile) == 576) ? 1 : -1];
typedef char hoverless_after_settings[(SUSAMUNE_CFG_SETTINGS_TAIL_OFFSET + SUSAMUNE_CFG_SETTINGS_TAIL_SIZE <= SUSAMUNE_HOVERLESS_CFG_OFFSET) ? 1 : -1];
typedef char hoverless_mailbox_end[(SUSAMUNE_HOVERLESS_CFG_OFFSET + sizeof(struct SusamuneHoverlessCfg) == SUSAMUNE_HOVERLESS_LIVE_OFFSET) ? 1 : -1];
typedef char hoverless_before_progress[(SUSAMUNE_HOVERLESS_LIVE_OFFSET + 4 * SUSAMUNE_ILING_PB_MAX_SLOTS <= SUSAMUNE_PROGRESS_CFG_OFFSET) ? 1 : -1];
typedef char hoverless_before_finish_breakdown[(SUSAMUNE_HOVERLESS_LIVE_OFFSET + 4 * SUSAMUNE_ILING_PB_MAX_SLOTS <= SUSAMUNE_FINISH_BREAKDOWN_CFG_OFFSET && 0x719003A0u + 4 * SUSAMUNE_ILING_PB_MAX_SLOTS <= SUSAMUNE_DOLPHIN_FINISH_BREAKDOWN_PPC_BASE) ? 1 : -1];
typedef char hoverless_finish_breakdown_flags[((SUSAMUNE_HOVERLESS_FLAG & SUSAMUNE_FINISH_BREAKDOWN_FLAG) == 0) ? 1 : -1];
typedef char hoverless_reply_line[(__builtin_offsetof(struct SusamuneHoverlessCfg, ackSeq) == 32) ? 1 : -1];
typedef char hoverless_values_line[(__builtin_offsetof(struct SusamuneHoverlessCfg, values) == 64) ? 1 : -1];
#endif
