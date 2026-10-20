#ifndef SUSAMUNE_MOD_V4_H
#define SUSAMUNE_MOD_V4_H

#include "mod_quick.h"
#include "japanese_ui.h"

#ifndef SUSAMUNE_MOD_MAGIC
#error Include susamune/mod_bin.h before this implementation header
#endif

/* V4 big-endian wire reader. All words are read as bytes, including on ARM.
 * Source and mappings remain immutable/exclusive until installation returns.
 * CRC is corruption detection, not authentication. Publish hooks separately. */
enum {
    SUSAMUNE_MOD_V4_OK, SUSAMUNE_MOD_V4_INVALID, SUSAMUNE_MOD_V4_CRC,
    SUSAMUNE_MOD_V4_QUICK, SUSAMUNE_MOD_V4_COMMIT_FAILED,
    SUSAMUNE_MOD_V4_RAW = 0, SUSAMUNE_MOD_V4_PACKED = 1, SUSAMUNE_MOD_V4_XIP = 2,
    SUSAMUNE_MOD_V4_HEADER = 64, SUSAMUNE_MOD_V4_DESCRIPTOR = 32
};

static inline unsigned int SusamuneModV4Base(unsigned int game) {
    return SUSAMUNE_MOD_BASE_FOR_GAME_ID(game);
}
static inline unsigned int SusamuneModV4Stage(unsigned int flags) {
    return flags ? SUSAMUNE_MOD_DOLPHIN_STAGING_PPC_BASE : SUSAMUNE_MEM2_MODBIN_PPC_BASE;
}
static inline unsigned int SusamuneModV4Align(unsigned int value) {
    return (value + 31u) & ~31u;
}
static inline unsigned int SusamuneModV4Crc(const unsigned char *p, unsigned int size,
                                     unsigned int zeroBegin, unsigned int zeroEnd) {
    unsigned int bit, i;
    unsigned int crc = 0xffffffffu;
    for (i = 0; i < size; ++i) {
        crc ^= i >= zeroBegin && i < zeroEnd ? 0u : p[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
static inline int SusamuneModV4Zero(const unsigned char *p, unsigned int size) {
    unsigned int i;
    for (i = 0; i < size; ++i) if (p[i]) return 0;
    return 1;
}
static inline int SusamuneModV4Overlap(const void *a, unsigned int an,
                                 const void *b, unsigned int bn) {
    return (SusamuneModQuickAddress)a < (SusamuneModQuickAddress)b + bn &&
        (SusamuneModQuickAddress)b < (SusamuneModQuickAddress)a + an;
}

static inline unsigned int SusamuneModV4NativeWord(unsigned int bigEndian) {
#if !defined(__BYTE_ORDER__) || !defined(__ORDER_LITTLE_ENDIAN__) || !defined(__ORDER_BIG_ENDIAN__)
#error Native word order must be explicit
#elif __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return __builtin_bswap32(bigEndian);
#elif __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    return bigEndian;
#else
#error Unsupported native word order
#endif
}
/* Starlet byte/halfword accesses to MEM1 are unreliable. Volatile words also
 * prevent the optimizer from replacing these accesses with narrower ones. */
static inline void SusamuneModV4Store(unsigned char *out, unsigned int word) {
    *(volatile unsigned int *)out = SusamuneModV4NativeWord(word);
}
static inline unsigned int SusamuneModV4Load(const unsigned char *out) {
    return SusamuneModV4NativeWord(*(const volatile unsigned int *)out);
}
typedef struct {
    unsigned char *base;
    unsigned int produced;
    unsigned int pending;
} SusamuneModV4Writer;

static inline void SusamuneModV4Emit(SusamuneModV4Writer *out, unsigned int byte) {
    out->pending = (out->pending << 8) | byte;
    ++out->produced;
    if (!(out->produced & 3u)) {
        SusamuneModV4Store(out->base + out->produced - 4u, out->pending);
        out->pending = 0;
    }
}
static inline unsigned int SusamuneModV4History(const SusamuneModV4Writer *out, unsigned int index) {
    const unsigned int committed = out->produced & ~3u;
    if (index >= committed)
        return (out->pending >> ((out->produced - index - 1u) * 8u)) & 255u;
    return (SusamuneModV4Load(out->base + (index & ~3u)) >> ((3u - (index & 3u)) * 8u)) & 255u;
}

static inline int SusamuneModV4Lz4Words(const unsigned char *bytes, unsigned int size,
                                 unsigned char *destination, unsigned int raw) {
    unsigned int i;
    SusamuneModV4Writer out = {destination, 0, 0};
    unsigned int input = 0;
    while (input < size) {
        const unsigned int token = bytes[input++];
        unsigned int literals, match;
        if (!SusamuneModQuickLength(bytes, size, &input, token >> 4,
                               raw - out.produced, &literals) || literals > size - input) return 0;
        for (i = 0; i < literals; ++i) SusamuneModV4Emit(&out, bytes[input++]);
        if (input == size) return out.produced == raw && !(out.produced & 3u);
        if (size - input < 2 || raw - out.produced < 12) return 0;
        const unsigned int distance = bytes[input] | ((unsigned int)bytes[input + 1] << 8);
        input += 2;
        if (!distance || distance > out.produced ||
            !SusamuneModQuickLength(bytes, size, &input, token & 15,
                               raw - out.produced - 9, &match)) return 0;
        match += 4;
        for (i = 0; i < match; ++i)
            SusamuneModV4Emit(&out, SusamuneModV4History(&out, out.produced - distance));
    }
    return 0;
}

static inline int SusamuneModV4QuickWords(const unsigned char *bytes, unsigned int packed,
                                   unsigned char *out, unsigned int raw) {
    unsigned int i;
    if (packed < 8 || SusamuneModQuickWord(bytes) != 0x4D534C34u ||
        SusamuneModQuickWord(bytes + 4) != SUSAMUNE_MOD_QUICK_BLOCK) return 0;
    unsigned int input = 8, output = 0;
    while (output < raw) {
        if (packed - input < 8) return 0;
        const unsigned int count = SusamuneModQuickWord(bytes + input);
        const unsigned int word = SusamuneModQuickWord(bytes + input + 4);
        const unsigned int length = word & 0x7fffffffu;
        const unsigned int expected = raw - output < SUSAMUNE_MOD_QUICK_BLOCK ?
            raw - output : SUSAMUNE_MOD_QUICK_BLOCK;
        input += 8;
        if (count != expected || (count & 3u) || !length || length > packed - input) return 0;
        if (word & 0x80000000u) {
            if (length != count) return 0;
            for (i = 0; i < count; i += 4)
                SusamuneModV4Store(out + output + i, SusamuneModQuickWord(bytes + input + i));
        } else if (length >= count ||
            !SusamuneModV4Lz4Words(bytes + input, length, out + output, count)) return 0;
        input += length;
        output += count;
    }
    return input == packed;
}

/* sourceVma is the canonical PPC mapping, even when called through ARM's
 * physical alias. The caller owns the truthful pointer-to-mapping binding. */
static inline int SusamuneModV4Validate(const void *source, unsigned int fileSize,
                                  unsigned int game, unsigned int flags,
                                  unsigned int sourceVma) {
    unsigned int i, order;
    const unsigned char *p = (const unsigned char *)source;
    const unsigned int base = SusamuneModV4Base(game);
    const unsigned int ceiling = game == SUSAMUNE_MOD_GAME_ID_JP ? SUSAMUNE_JP_UI_OFFSET : SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE;
    if (!base || flags > 1 || sourceVma != SusamuneModV4Stage(flags) ||
        fileSize < 128u || fileSize > ceiling || (fileSize & 31u) ||
        !SusamuneModQuickRange(source, fileSize)) return SUSAMUNE_MOD_V4_INVALID;
    const unsigned int code = SusamuneModQuickWord(p + 16);
    const unsigned int count = SusamuneModQuickWord(p + 20);
    const unsigned int sections = SusamuneModQuickWord(p + 32);
    if (SusamuneModQuickWord(p) != SUSAMUNE_MOD_MAGIC || SusamuneModQuickWord(p + 4) != SUSAMUNE_MOD_VERSION_V4 ||
        SusamuneModQuickWord(p + 8) != game || SusamuneModQuickWord(p + 12) != base ||
        SusamuneModQuickWord(p + 24) != SUSAMUNE_ARENA_RESERVE_SIZE ||
        SusamuneModQuickWord(p + 28) > SUSAMUNE_MOD_BLOB_MAX_SIZE ||
        SusamuneModQuickWord(p + 44) != flags || !SusamuneModV4Zero(p + 48, 16) ||
        (sections < 2 || sections > 4) || (code & 31u) ||
        code < sections * 32u || code > fileSize - 64u ||
        count > (fileSize - 64u - code) / 8u) return SUSAMUNE_MOD_V4_INVALID;
    const unsigned int exact = 64u + code + count * 8u;
    if (SusamuneModV4Align(exact) != fileSize ||
        !SusamuneModV4Zero(p + exact, fileSize - exact)) return SUSAMUNE_MOD_V4_INVALID;
    if (SusamuneModV4Crc(p, 64, 40, 44) != SusamuneModQuickWord(p + 40) ||
        SusamuneModV4Crc(p + 64, fileSize - 64, 0, 0) != SusamuneModQuickWord(p + 36))
        return SUSAMUNE_MOD_V4_CRC;

    unsigned int cursor = sections * 32u, total = 0;
    for (order = 0; order < sections; ++order) {
        const unsigned int index = sections >= 3 && order < 3 ? (order == 0 ? 2u : order - 1u) : order;
        const unsigned char *d = p + 64u + index * 32u;
        const unsigned int target = SusamuneModQuickWord(d);
        const unsigned int init = SusamuneModQuickWord(d + 4);
        const unsigned int memory = SusamuneModQuickWord(d + 8);
        const unsigned int offset = SusamuneModQuickWord(d + 12);
        const unsigned int stored = SusamuneModQuickWord(d + 16);
        const unsigned int kind = SusamuneModQuickWord(d + 20);
        if (offset != cursor || cursor > code || stored > code - cursor ||
            SusamuneModQuickWord(d + 28)) return SUSAMUNE_MOD_V4_INVALID;
        if (index == 2) {
            if (kind != SUSAMUNE_MOD_V4_XIP || !init || (init & 31u) ||
                init != memory || init != stored ||
                target != sourceVma + 64u + offset) return SUSAMUNE_MOD_V4_INVALID;
        } else if (index == 3) {
            if (target != (flags ? SUSAMUNE_MENU_CODE_DOLPHIN_PPC_BASE : SUSAMUNE_MENU_CODE_CONSOLE_PPC_BASE) ||
                !init || (init & 31u) || memory != init || memory > SUSAMUNE_MENU_CODE_SIZE ||
                kind != SUSAMUNE_MOD_V4_PACKED) return SUSAMUNE_MOD_V4_INVALID;
        } else {
            const unsigned int cap = index ? SUSAMUNE_MOD_UPPER_SIZE : SUSAMUNE_MOD_MEM1_WORKING_CAP_SIZE;
            if (target != (index ? SUSAMUNE_MOD_UPPER_OFFSET : 0u) || memory > cap || init > memory ||
                ((init | memory) & 3u) || kind > SUSAMUNE_MOD_V4_PACKED ||
                (kind == SUSAMUNE_MOD_V4_RAW && stored != init)) return SUSAMUNE_MOD_V4_INVALID;
            total += memory;
        }
        const unsigned char *payload = p + 64u + offset;
        if (SusamuneModV4Crc(payload, stored, 0, 0) != SusamuneModQuickWord(d + 24))
            return SUSAMUNE_MOD_V4_CRC;
        if (kind == SUSAMUNE_MOD_V4_PACKED &&
            SusamuneModQuickValidate(payload, stored, init) != SUSAMUNE_MOD_QUICK_OK)
            return SUSAMUNE_MOD_V4_QUICK;
        const unsigned int end = cursor + stored;
        cursor = SusamuneModV4Align(end);
        if (cursor > code || !SusamuneModV4Zero(p + 64u + end, cursor - end))
            return SUSAMUNE_MOD_V4_INVALID;
    }
    if (cursor != code || total != SusamuneModQuickWord(p + 28)) return SUSAMUNE_MOD_V4_INVALID;
    for (i = 0; i < count; ++i) {
        const unsigned int address = SusamuneModQuickWord(p + 64u + code + i * 8u);
        if ((address & 3u) || address < 0x80000000u || address >= base)
            return SUSAMUNE_MOD_V4_INVALID;
    }
    return SUSAMUNE_MOD_V4_OK;
}

/* Installs the two MEM1 spans and optional fixed menu-code span. The source,
 * attachment heap, timer scratch and hooks remain untouched. */
static inline int SusamuneModV4InstallMapped(const void *source, unsigned int fileSize,
                                 unsigned int game, unsigned int flags,
                                 unsigned int sourceVma, void *mem1,
                                 unsigned int mem1Bytes, unsigned int mem1Vma,
                                 void *menu, unsigned int menuBytes, unsigned int menuVma) {
    unsigned int i, index;
    if (mem1Vma != SusamuneModV4Base(game) || mem1Bytes < SUSAMUNE_MOD_REGION_SIZE ||
        ((SusamuneModQuickAddress)mem1 & 3u) ||
        !SusamuneModQuickRange(mem1, mem1Bytes) || !SusamuneModQuickRange(source, fileSize) ||
        SusamuneModV4Overlap(source, fileSize, mem1, mem1Bytes)) return SUSAMUNE_MOD_V4_INVALID;
    const int status = SusamuneModV4Validate(source, fileSize, game, flags, sourceVma);
    if (status != SUSAMUNE_MOD_V4_OK) return status;
    const unsigned char *p = (const unsigned char *)source;
    const unsigned int extra = SusamuneModQuickWord(p + 32) == 4;
    if (extra && (!menu || menuBytes != SUSAMUNE_MENU_CODE_SIZE ||
        menuVma != (flags ? SUSAMUNE_MENU_CODE_DOLPHIN_PPC_BASE : SUSAMUNE_MENU_CODE_CONSOLE_PPC_BASE) ||
        ((SusamuneModQuickAddress)menu & 31u) || !SusamuneModQuickRange(menu, menuBytes) ||
        SusamuneModV4Overlap(source, fileSize, menu, menuBytes) ||
        SusamuneModV4Overlap(mem1, mem1Bytes, menu, menuBytes))) return SUSAMUNE_MOD_V4_INVALID;
    for (index = 0; index < (extra ? 4u : 2u); ++index) {
        if (index == 2) continue;
        const unsigned char *d = p + 64u + index * 32u;
        unsigned char *out = index == 3 ? (unsigned char *)menu :
            (unsigned char *)mem1 + SusamuneModQuickWord(d);
        const unsigned int init = SusamuneModQuickWord(d + 4);
        const unsigned int memory = SusamuneModQuickWord(d + 8);
        const unsigned int stored = SusamuneModQuickWord(d + 16);
        const unsigned char *payload = p + 64u + SusamuneModQuickWord(d + 12);
        if (SusamuneModQuickWord(d + 20) == SUSAMUNE_MOD_V4_PACKED) {
            if (!SusamuneModV4QuickWords(payload, stored, out, init)) return SUSAMUNE_MOD_V4_COMMIT_FAILED;
        } else {
            for (i = 0; i < init; i += 4) SusamuneModV4Store(out + i, SusamuneModQuickWord(payload + i));
        }
        for (i = init; i < memory; i += 4) SusamuneModV4Store(out + i, 0);
    }
    return SUSAMUNE_MOD_V4_OK;
}

static inline int SusamuneModV4Install(const void *source, unsigned int fileSize,
                                 unsigned int game, unsigned int flags,
                                 unsigned int sourceVma, void *mem1,
                                 unsigned int mem1Bytes, unsigned int mem1Vma) {
    return SusamuneModV4InstallMapped(source, fileSize, game, flags, sourceVma,
        mem1, mem1Bytes, mem1Vma, 0, 0, 0);
}

#endif
