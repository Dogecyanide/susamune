#ifndef SUSAMUNE_MOD_BIN_H
#define SUSAMUNE_MOD_BIN_H

#include "susamune/mem2_map.h"

// =====================================================================
// mod_bin.h
//
// The on-disc format of mod_<region>.bin and the MEM2 window it is staged
// in. The mod used to be a byte array compiled into the Nintendont kernel
// (one launcher per game version, and a second copy of the blob resident in
// MEM2 for the whole session). It is now a file next to the launcher's
// boot.dol that the loader reads for the detected disc and the kernel copies
// into MEM1, so one launcher serves GMSJ/GMSE/GMSP.
//
// The hook writes travel with the code: their addresses are per-version, so
// a blob without its write list is not applicable to anything.
//
// Shared by all three toolchains, so this header is plain C with no type
// dependencies. Everything is big-endian on both sides; no swapping.
//
// Flow:
//   loader (PPC) -- knows the game id before booting the kernel; reads
//                   <launch_dir>/mod_<region>.bin into the MEM2 window below
//                   and flushes it. Writes a zeroed header if there is none.
//   kernel (ARM) -- PatchSusamune() validates the header against the running
//                   GAME_ID, copies both validated spans, zeroes each BSS
//                   tail, and applies the writes.
//                   SusamuneCfg.c also reads gameId from it to pick which
//                   susamune.ini sections belong to this run.
// =====================================================================

#define SUSAMUNE_MOD_MAGIC   0x534D4F44u  // 'SMOD'
#define SUSAMUNE_MOD_VERSION 3u

// Disc header bytes 0..3 of each supported revision.
#define SUSAMUNE_MOD_GAME_ID_JP  0x474D534Au  // "GMSJ"
#define SUSAMUNE_MOD_GAME_ID_US  0x474D5345u  // "GMSE"
#define SUSAMUNE_MOD_GAME_ID_PAL 0x474D5350u  // "GMSP"

#define SUSAMUNE_MOD_BASE_JP  0x80426020u
#define SUSAMUNE_MOD_BASE_US  0x80429800u
#define SUSAMUNE_MOD_BASE_PAL 0x80420D60u
#define SUSAMUNE_MOD_REGION_SIZE 0xC0000u
#define SUSAMUNE_SCRATCH 0x40u
#define SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE 0x58000u
#define SUSAMUNE_MOD_BLOB_MAX_SIZE 0x98000u
#define SUSAMUNE_MOD_UPPER_OFFSET 0x80000u
#define SUSAMUNE_MOD_UPPER_SIZE 0x40000u
#define SUSAMUNE_MOD_ATTACHMENT_HEAP_OFFSET 0x58000u
#define SUSAMUNE_MOD_ATTACHMENT_HEAP_SIZE 0x20000u
// Timer scratch is an ABI: growing the arena must never move it.
#define SUSAMUNE_MOD_SCRATCH_OFFSET 0x7FFC0u
#define SUSAMUNE_DEBUG_STACK_SIZE 0x2000u
#define SUSAMUNE_ARENA_RESERVE_SIZE \
    (SUSAMUNE_MOD_REGION_SIZE + SUSAMUNE_DEBUG_STACK_SIZE)

#define SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId)                         \
    ((gameId) == SUSAMUNE_MOD_GAME_ID_JP    ? SUSAMUNE_MOD_BASE_JP   \
     : (gameId) == SUSAMUNE_MOD_GAME_ID_US  ? SUSAMUNE_MOD_BASE_US   \
     : (gameId) == SUSAMUNE_MOD_GAME_ID_PAL ? SUSAMUNE_MOD_BASE_PAL  \
                                             : 0u)

// V3 body: two segment descriptors, their initialized payloads, then hooks.
// The protected attachment heap and timer scratch are absent from both spans.
struct SusamuneModHeader {
    unsigned int magic;         // SUSAMUNE_MOD_MAGIC
    unsigned int version;       // SUSAMUNE_MOD_VERSION
    unsigned int gameId;        // SUSAMUNE_MOD_GAME_ID_*
    unsigned int baseAddr;      // MEM1 address the code is linked at
    unsigned int codeSize;      // descriptor table plus initialized payloads
    unsigned int writeCount;
    unsigned int arenaReserve;  // what getArenaLo() adds; see PatchSusamuneGeckoCodes
    unsigned int memSize;       // sum of both runtime spans, excluding the hole
};

#define SUSAMUNE_MOD_HEADER_SIZE 32u
#define SUSAMUNE_MOD_SEGMENT_COUNT 2u
#define SUSAMUNE_MOD_SEGMENT_TABLE_SIZE 32u
struct SusamuneModSegment {
    unsigned int offset;
    unsigned int initSize;
    unsigned int memSize;
    unsigned int payloadOffset; // Relative to the body, after the header.
};

static inline int SusamuneModHeaderValid(const struct SusamuneModHeader *h,
                                        unsigned int gameId)
{
    unsigned int end;
    if (!SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId) ||
        h->magic != SUSAMUNE_MOD_MAGIC || h->version != SUSAMUNE_MOD_VERSION ||
        h->gameId != gameId || h->baseAddr != SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId) ||
        h->arenaReserve != SUSAMUNE_ARENA_RESERVE_SIZE ||
        h->codeSize < SUSAMUNE_MOD_SEGMENT_TABLE_SIZE ||
        h->codeSize > SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE - SUSAMUNE_MOD_HEADER_SIZE ||
        h->memSize > SUSAMUNE_MOD_BLOB_MAX_SIZE ||
        ((h->codeSize | h->memSize) & 3u))
        return 0;
    end = SUSAMUNE_MOD_HEADER_SIZE + h->codeSize;
    return h->writeCount <= (SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE - end) / 8u;
}

static inline unsigned int SusamuneModFileSize(const struct SusamuneModHeader *h)
{
    return SUSAMUNE_MOD_HEADER_SIZE + h->codeSize + h->writeCount * 8u;
}

static inline int SusamuneModFileValid(const struct SusamuneModHeader *h,
    unsigned int gameId, unsigned int fileSize)
{
    const struct SusamuneModSegment *s = (const struct SusamuneModSegment *)(h + 1);
    const unsigned int *writes;
    unsigned int i, cursor = SUSAMUNE_MOD_SEGMENT_TABLE_SIZE, total = 0;
    if (fileSize < SUSAMUNE_MOD_HEADER_SIZE || !SusamuneModHeaderValid(h, gameId) ||
        fileSize != SusamuneModFileSize(h))
        return 0;
    for (i = 0; i < SUSAMUNE_MOD_SEGMENT_COUNT; ++i) {
        unsigned int cap = i ? SUSAMUNE_MOD_UPPER_SIZE : SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE;
        if (s[i].offset != (i ? SUSAMUNE_MOD_UPPER_OFFSET : 0u) ||
            s[i].memSize > cap || s[i].initSize > s[i].memSize ||
            s[i].payloadOffset != cursor || ((s[i].initSize | s[i].memSize) & 3u) ||
            s[i].initSize > h->codeSize - cursor)
            return 0;
        cursor += s[i].initSize;
        total += s[i].memSize;
    }
    if (cursor != h->codeSize || total != h->memSize)
        return 0;
    writes = (const unsigned int *)((const unsigned char *)(h + 1) + h->codeSize);
    for (i = 0; i < h->writeCount; ++i) {
        unsigned int addr = writes[i * 2u];
        // Hooks target retail MEM1 only, never the image, heaps, or MEM2.
        if ((addr & 3u) || addr < 0x80000000u || addr >= h->baseAddr)
            return 0;
    }
    return 1;
}

// The file name for a given disc id, spelled the same way by the build
// (scripts/gen_mod_bin.py) and the loader. Null for a game we have no mod for.
#define SUSAMUNE_MOD_REGION_TAG(gameId)                            \
    ((gameId) == SUSAMUNE_MOD_GAME_ID_JP    ? "jp"                 \
     : (gameId) == SUSAMUNE_MOD_GAME_ID_US  ? "us"                 \
     : (gameId) == SUSAMUNE_MOD_GAME_ID_PAL ? "pal"                \
                                            : (const char *)0)

#define SUSAMUNE_MOD_FILE_FMT "mod_%s.bin"

// Portable compile-time checks (no C11 dependency). The reset-safe file
// ceiling has to fit inside the loader's unchanged staging allocation.
typedef char susamune_mod_header_size_check
    [(sizeof(struct SusamuneModHeader) == SUSAMUNE_MOD_HEADER_SIZE) ? 1 : -1];
typedef char susamune_mod_window_size_check
    [(SUSAMUNE_MEM2_MODBIN_SIZE >= SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE) ? 1 : -1];
typedef char susamune_mod_blob_scratch_check
    [(SUSAMUNE_MOD_SCRATCH_OFFSET + SUSAMUNE_SCRATCH == SUSAMUNE_MOD_UPPER_OFFSET) ? 1 : -1];
typedef char susamune_mod_working_cap_check
    [(SUSAMUNE_MOD_BLOB_MAX_SIZE == SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE + SUSAMUNE_MOD_UPPER_SIZE) ? 1 : -1];
typedef char susamune_mod_attachment_offset_check
    [(SUSAMUNE_MOD_ATTACHMENT_HEAP_OFFSET ==
      SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE) ? 1 : -1];
typedef char susamune_mod_attachment_bounds_check
    [(SUSAMUNE_MOD_ATTACHMENT_HEAP_OFFSET +
      SUSAMUNE_MOD_ATTACHMENT_HEAP_SIZE <= SUSAMUNE_MOD_SCRATCH_OFFSET) ? 1 : -1];
typedef char susamune_mod_attachment_alignment_check
    [(((SUSAMUNE_MOD_BASE_JP | SUSAMUNE_MOD_BASE_US |
        SUSAMUNE_MOD_BASE_PAL | SUSAMUNE_MOD_ATTACHMENT_HEAP_OFFSET |
        SUSAMUNE_MOD_ATTACHMENT_HEAP_SIZE) & 31u) == 0) ? 1 : -1];
typedef char susamune_mod_staging_vault_check
    [(SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE ==
      SUSAMUNE_GHOST_ASSET_VAULT_OFFSET) ? 1 : -1];
typedef char susamune_mod_file_capacity_check
    [(SUSAMUNE_MOD_HEADER_SIZE + SUSAMUNE_MOD_BLOB_MAX_SIZE <=
      SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE) ? 1 : -1];

#define SUSAMUNE_MOD_PPC_PTR  ((struct SusamuneModHeader *)SUSAMUNE_MEM2_MODBIN_PPC_BASE)
#define SUSAMUNE_MOD_PHYS_PTR ((struct SusamuneModHeader *)SUSAMUNE_MEM2_MODBIN_PHYS_BASE)

#endif  // SUSAMUNE_MOD_BIN_H
