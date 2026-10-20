#ifndef SUSAMUNE_MOD_QUICK_H
#define SUSAMUNE_MOD_QUICK_H

/* Bounded independent-block transport reader. Source bytes stay immutable and exclusively owned
 * across both passes. This checks structure, not an external payload checksum. */
enum {
    SUSAMUNE_MOD_QUICK_OK,
    SUSAMUNE_MOD_QUICK_INVALID,
    SUSAMUNE_MOD_QUICK_CORRUPT,
    SUSAMUNE_MOD_QUICK_COMMIT_FAILED,
    SUSAMUNE_MOD_QUICK_BLOCK = 0x20000
};
typedef __UINTPTR_TYPE__ SusamuneModQuickAddress;
typedef char SusamuneModQuickWordIs32[sizeof(unsigned int) == 4 ? 1 : -1];

static inline int SusamuneModQuickRange(const void *bytes, unsigned int size) {
    return bytes && size && (SusamuneModQuickAddress)bytes <= ~(SusamuneModQuickAddress)0 - size;
}

static inline unsigned int SusamuneModQuickWord(const unsigned char *p) {
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16) |
           ((unsigned int)p[2] << 8) | p[3];
}

static inline int SusamuneModQuickLength(const unsigned char *bytes, unsigned int size,
                                    unsigned int *cursor, unsigned int initial,
                                    unsigned int limit, unsigned int *length) {
    unsigned int total = initial;
    if (total > limit) return 0;
    if (initial == 15) {
        unsigned int more;
        do {
            if (*cursor == size) return 0;
            more = bytes[(*cursor)++];
            if (more > limit - total) return 0;
            total += more;
        } while (more == 255);
    }
    *length = total;
    return 1;
}

/* Offset validation uses counts; the dry pass needs no history buffer. */
static inline int SusamuneModQuickLz4(const unsigned char *bytes, unsigned int size,
                                 unsigned char *out, unsigned int raw) {
    unsigned int i;
    unsigned int input = 0, output = 0;
    while (input < size) {
        const unsigned int token = bytes[input++];
        unsigned int literals, match;
        if (!SusamuneModQuickLength(bytes, size, &input, token >> 4, raw - output, &literals) ||
            literals > size - input) return 0;
        if (out) for (i = 0; i < literals; ++i) out[output + i] = bytes[input + i];
        input += literals;
        output += literals;
        if (input == size) return output == raw;
        /* Standard LZ4 leaves twelve bytes after the last match starts and
         * five final literals. See the vendored LZ4 MFLIMIT/LASTLITERALS. */
        if (size - input < 2 || raw - output < 12) return 0;
        const unsigned int distance = bytes[input] | ((unsigned int)bytes[input + 1] << 8);
        input += 2;
        if (!distance || distance > output ||
            !SusamuneModQuickLength(bytes, size, &input, token & 15, raw - output - 9, &match)) return 0;
        match += 4;
        if (out) for (i = 0; i < match; ++i)
            out[output + i] = out[output + i - distance];
        output += match;
    }
    return 0;
}

static inline int SusamuneModQuickPass(const unsigned char *bytes, unsigned int packed,
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
        if (count != expected || !length || length > packed - input) return 0;
        if (word & 0x80000000u) {
            if (length != count) return 0;
            if (out) for (i = 0; i < count; ++i) out[output + i] = bytes[input + i];
        } else if (length >= count ||
            !SusamuneModQuickLz4(bytes + input, length, out ? out + output : 0, count)) return 0;
        input += length;
        output += count;
    }
    return input == packed;
}

static inline int SusamuneModQuickValidate(const void *source, unsigned int packed,
                                      unsigned int initialized) {
    if (!SusamuneModQuickRange(source, packed) || !initialized) return SUSAMUNE_MOD_QUICK_INVALID;
    return SusamuneModQuickPass((const unsigned char *)source, packed, 0, initialized) ?
        SUSAMUNE_MOD_QUICK_OK : SUSAMUNE_MOD_QUICK_CORRUPT;
}

/* Byte-output reference for ordinary memory. Starlet MEM1 must use mod_v4's
 * word writer. Only initialized bytes are written; BSS remains caller-owned. */
static inline int SusamuneModQuickDecode(const void *source, unsigned int packed,
                                    void *destination, unsigned int initialized,
                                    unsigned int destinationBytes) {
    if (!SusamuneModQuickRange(source, packed) || !initialized || initialized > destinationBytes ||
        !SusamuneModQuickRange(destination, destinationBytes)) return SUSAMUNE_MOD_QUICK_INVALID;
    const SusamuneModQuickAddress a = (SusamuneModQuickAddress)source, b = (SusamuneModQuickAddress)destination;
    if (a < b + destinationBytes && b < a + packed) return SUSAMUNE_MOD_QUICK_INVALID;
    const int checked = SusamuneModQuickValidate(source, packed, initialized);
    if (checked != SUSAMUNE_MOD_QUICK_OK) return checked;
    return SusamuneModQuickPass((const unsigned char *)source, packed,
        (unsigned char *)destination, initialized) ? SUSAMUNE_MOD_QUICK_OK : SUSAMUNE_MOD_QUICK_COMMIT_FAILED;
}

#endif
