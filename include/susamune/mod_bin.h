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
#define SUSAMUNE_MOD_VERSION_V4 4u
#define SUSAMUNE_MOD_DOLPHIN_STAGING_PPC_BASE 0x71E3F000u

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

#include "mod_v4.h"

/* V3 host tests convert metadata to native words; V4 always remains BE wire.
 * Both console CPUs are BE, so existing V3 structs keep their native ABI. */
static inline unsigned int SusamuneModFileVersion(const struct SusamuneModHeader *h)
{
    const unsigned char *p = (const unsigned char *)h;
    if (!SusamuneModQuickRange(h, SUSAMUNE_MOD_HEADER_SIZE)) return 0;
    if (SusamuneModQuickWord(p) == SUSAMUNE_MOD_MAGIC &&
        SusamuneModQuickWord(p + 4) == SUSAMUNE_MOD_VERSION_V4)
        return SUSAMUNE_MOD_VERSION_V4;
    if (!((SusamuneModQuickAddress)h & 3u) && h->magic == SUSAMUNE_MOD_MAGIC &&
        h->version == SUSAMUNE_MOD_VERSION) return SUSAMUNE_MOD_VERSION;
    return 0;
}

/* Only the first cache line is available before the caller invalidates the file. */
static inline int SusamuneModHeaderValid(const struct SusamuneModHeader *h,
                                        unsigned int gameId)
{
    unsigned int end, version = SusamuneModFileVersion(h);
    if (version == SUSAMUNE_MOD_VERSION_V4) {
        const unsigned char *p = (const unsigned char *)h;
        unsigned int code = SusamuneModQuickWord(p + 16);
        unsigned int count = SusamuneModQuickWord(p + 20);
        unsigned int memory = SusamuneModQuickWord(p + 28);
        unsigned int ceiling = gameId == SUSAMUNE_MOD_GAME_ID_JP
            ? SUSAMUNE_JP_UI_OFFSET : SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE;
        if (!SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId) ||
            SusamuneModQuickWord(p + 8) != gameId ||
            SusamuneModQuickWord(p + 12) != SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId) ||
            SusamuneModQuickWord(p + 24) != SUSAMUNE_ARENA_RESERVE_SIZE ||
            code < 2u * SUSAMUNE_MOD_V4_DESCRIPTOR || (code & 31u) ||
            code > ceiling - SUSAMUNE_MOD_V4_HEADER ||
            memory > SUSAMUNE_MOD_BLOB_MAX_SIZE || (memory & 3u)) return 0;
        end = SUSAMUNE_MOD_V4_HEADER + code;
        return count <= (ceiling - end) / 8u;
    }
    if (version != SUSAMUNE_MOD_VERSION) return 0;
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
    unsigned int version = SusamuneModFileVersion(h);
    if (version == SUSAMUNE_MOD_VERSION_V4) {
        const unsigned char *p = (const unsigned char *)h;
        if (!SusamuneModHeaderValid(h, SusamuneModQuickWord(p + 8))) return 0;
        return SusamuneModV4Align(SUSAMUNE_MOD_V4_HEADER +
            SusamuneModQuickWord(p + 16) + SusamuneModQuickWord(p + 20) * 8u);
    }
    if (version != SUSAMUNE_MOD_VERSION || !SusamuneModHeaderValid(h, h->gameId)) return 0;
    return SUSAMUNE_MOD_HEADER_SIZE + h->codeSize + h->writeCount * 8u;
}

static inline int SusamuneModV3FileValid(const struct SusamuneModHeader *h,
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

/* Loader/kernel entry point: emulator-only cold addresses are never admitted. */
static inline int SusamuneModFileValid(const struct SusamuneModHeader *h,
    unsigned int gameId, unsigned int fileSize)
{
    if (fileSize < SUSAMUNE_MOD_HEADER_SIZE || !SusamuneModQuickRange(h, fileSize) ||
        !SusamuneModHeaderValid(h, gameId)) return 0;
    if (SusamuneModFileVersion(h) == SUSAMUNE_MOD_VERSION_V4)
        return SusamuneModV4Validate(h, fileSize, gameId, 0,
            SUSAMUNE_MEM2_MODBIN_PPC_BASE) == SUSAMUNE_MOD_V4_OK;
    return SusamuneModV3FileValid(h, gameId, fileSize);
}

/* Source remains immutable/exclusive through both passes. Cache maintenance
 * and hook publication belong to the caller after successful installation. */
static inline int SusamuneModInstall(const struct SusamuneModHeader *h,
    unsigned int gameId, unsigned int fileSize, void *mem1,
    unsigned int mem1Bytes, unsigned int mem1Vma)
{
    unsigned int index, i;
    const unsigned char *p = (const unsigned char *)h;
    if (fileSize < SUSAMUNE_MOD_HEADER_SIZE ||
        mem1Vma != SUSAMUNE_MOD_BASE_FOR_GAME_ID(gameId) ||
        mem1Bytes < SUSAMUNE_MOD_REGION_SIZE || ((SusamuneModQuickAddress)mem1 & 3u) ||
        !SusamuneModQuickRange(mem1, mem1Bytes) || !SusamuneModQuickRange(h, fileSize) ||
        SusamuneModV4Overlap(h, fileSize, mem1, mem1Bytes)) return SUSAMUNE_MOD_V4_INVALID;
    if (SusamuneModFileVersion(h) == SUSAMUNE_MOD_VERSION_V4)
        return SusamuneModV4Install(h, fileSize, gameId, 0,
            SUSAMUNE_MEM2_MODBIN_PPC_BASE, mem1, mem1Bytes, mem1Vma);
    if (!SusamuneModFileValid(h, gameId, fileSize)) return SUSAMUNE_MOD_V4_INVALID;
    for (index = 0; index < SUSAMUNE_MOD_SEGMENT_COUNT; ++index) {
        const struct SusamuneModSegment *s = (const struct SusamuneModSegment *)(h + 1) + index;
        const unsigned char *payload = p + SUSAMUNE_MOD_HEADER_SIZE + s->payloadOffset;
        unsigned char *out = (unsigned char *)mem1 + s->offset;
        for (i = 0; i < s->initSize; i += 4u)
            SusamuneModV4Store(out + i, SusamuneModQuickWord(payload + i));
        for (i = s->initSize; i < s->memSize; i += 4u) SusamuneModV4Store(out + i, 0);
    }
    return SUSAMUNE_MOD_V4_OK;
}

/* These accessors require a complete file that passed SusamuneModFileValid. */
static inline unsigned int SusamuneModHeaderBytes(const struct SusamuneModHeader *h)
{
    unsigned int version = SusamuneModFileVersion(h);
    return version == SUSAMUNE_MOD_VERSION_V4 ? SUSAMUNE_MOD_V4_HEADER :
        version == SUSAMUNE_MOD_VERSION ? SUSAMUNE_MOD_HEADER_SIZE : 0;
}

static inline unsigned int SusamuneModSegmentMemory(const struct SusamuneModHeader *h,
    unsigned int index)
{
    if (index >= SUSAMUNE_MOD_SEGMENT_COUNT) return 0;
    if (SusamuneModFileVersion(h) == SUSAMUNE_MOD_VERSION_V4)
        return SusamuneModQuickWord((const unsigned char *)h + SUSAMUNE_MOD_V4_HEADER +
            index * SUSAMUNE_MOD_V4_DESCRIPTOR + 8u);
    return ((const struct SusamuneModSegment *)(h + 1))[index].memSize;
}

static inline unsigned int SusamuneModColdAddress(const struct SusamuneModHeader *h)
{
    const unsigned char *p = (const unsigned char *)h;
    if (SusamuneModFileVersion(h) != SUSAMUNE_MOD_VERSION_V4 ||
        SusamuneModQuickWord(p + 32) < 3u) return 0;
    return SusamuneModQuickWord(p + SUSAMUNE_MOD_V4_HEADER +
        2u * SUSAMUNE_MOD_V4_DESCRIPTOR);
}

static inline unsigned int SusamuneModColdSize(const struct SusamuneModHeader *h)
{
    if (!SusamuneModColdAddress(h)) return 0;
    return SusamuneModQuickWord((const unsigned char *)h + SUSAMUNE_MOD_V4_HEADER +
        2u * SUSAMUNE_MOD_V4_DESCRIPTOR + 16u);
}

static inline unsigned int SusamuneModMenuCodeSize(const struct SusamuneModHeader *h)
{
    const unsigned char *p = (const unsigned char *)h;
    if (SusamuneModFileVersion(h) != SUSAMUNE_MOD_VERSION_V4 ||
        SusamuneModQuickWord(p + 32) != 4u) return 0;
    return SusamuneModQuickWord(p + SUSAMUNE_MOD_V4_HEADER +
        3u * SUSAMUNE_MOD_V4_DESCRIPTOR + 8u);
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
