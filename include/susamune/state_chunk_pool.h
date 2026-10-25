#ifndef TIMEWARP_STATE_CHUNK_POOL_H
#define TIMEWARP_STATE_CHUNK_POOL_H

#include "state_multibank_memory.h"

/* Callers own all banks exclusively, validate
 * encoded streams separately, and retain metadata until Commit succeeds. */
enum {
    TW_CHUNK_SLOTS = 3,
    TW_CHUNK_BLOCKS = 256,
    TW_CHUNK_DESCRIPTORS = TW_CHUNK_BLOCKS * (TW_CHUNK_SLOTS + 1),
    TW_CHUNK_DIRECTORY_BYTES = 0x8000,
    TW_CHUNK_RAW_BYTES = 0x20000,
    TW_CHUNK_MAGIC = 0x54574331,
    TW_CHUNK_QUICK = 0,
    TW_CHUNK_OPAQUE = 1
};

typedef struct TWChunk {
    unsigned int offset, size, hash;
    unsigned short refs, reserved;
} TWChunk;

typedef struct TWChunkSlot {
    unsigned int count, packedBytes, rawBytes, metadataTag;
    unsigned short ids[TW_CHUNK_BLOCKS];
} TWChunkSlot;

typedef struct TWChunkPool {
    unsigned int magic, sizes[TW_BANK_MAX], bankCount, highWater, target;
    TWChunkSlot slots[TW_CHUNK_SLOTS + 1];
    TWChunk chunks[TW_CHUNK_DESCRIPTORS];
} TWChunkPool;

#ifdef __cplusplus
static_assert(sizeof(TWChunk) == 16, "chunk descriptor budget");
static_assert(sizeof(TWChunkPool) <= TW_CHUNK_DIRECTORY_BYTES, "directory budget");
#endif

static inline unsigned int TWChunkAlign(unsigned int size) {
    return (size + 31u) & ~31u;
}

static inline unsigned int TWChunkWord(const unsigned char *p) {
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16) |
           ((unsigned int)p[2] << 8) | p[3];
}

static inline int TWChunkMemoryValid(const TWBankMemory *memory) {
    if (!TWBankValid(memory) || memory->sizes[0] < TW_CHUNK_DIRECTORY_BYTES ||
        !TWBankExternalBuffer(memory, memory, sizeof(*memory)) ||
        (memory->sizes[0] & 31u)) return 0;
    for (unsigned int i = 0; i < memory->count; ++i)
        if ((memory->sizes[i] & 31u) || ((TWBankAddress)memory->banks[i] & 31u)) return 0;
    return 1;
}

static inline TWChunkPool *TWChunkDirectory(const TWBankMemory *memory) {
    return TWChunkMemoryValid(memory) ? (TWChunkPool *)memory->banks[0] : 0;
}

static inline const unsigned char *TWChunkData(const TWBankMemory *memory,
                                              const TWChunk *chunk) {
    TWBankSpan span;
    if (!chunk || !chunk->refs || chunk->reserved > TW_CHUNK_OPAQUE ||
        chunk->size < (chunk->reserved ? 1u : 9u) ||
        chunk->size > TW_CHUNK_RAW_BYTES + (chunk->reserved ? 0u : 8u) ||
        chunk->offset < TW_CHUNK_DIRECTORY_BYTES || (chunk->offset & 31u) ||
        !TWBankSpanAt(memory, chunk->offset, TWChunkAlign(chunk->size), &span) ||
        span.size != TWChunkAlign(chunk->size)) return 0;
    return span.data;
}

static inline int TWChunkLayoutValid(const TWBankMemory *memory,
                                     const TWChunkPool *pool) {
    if (!pool || pool->bankCount != memory->count) return 0;
    for (unsigned int i = 0; i < TW_BANK_MAX; ++i)
        if (pool->sizes[i] != memory->sizes[i]) return 0;
    return pool->magic == TW_CHUNK_MAGIC &&
        pool->highWater >= TW_CHUNK_DIRECTORY_BYTES && !(pool->highWater & 31u) &&
        pool->highWater <= TWBankCapacity(memory) && pool->target <= TW_CHUNK_SLOTS;
}

static inline int TWChunkHeader(const unsigned char *bytes, unsigned int size,
                                unsigned int *raw) {
    if (!bytes || size < 9 || size > TW_CHUNK_RAW_BYTES + 8) return 0;
    *raw = TWChunkWord(bytes);
    const unsigned int packed = TWChunkWord(bytes + 4);
    return *raw && *raw <= TW_CHUNK_RAW_BYTES &&
        (packed & 0x7fffffffu) == size - 8 &&
        ((packed & 0x80000000u) ? size - 8 == *raw : size - 8 < *raw);
}

static inline unsigned int TWChunkHash(const unsigned char *bytes, unsigned int size) {
    unsigned int value = 2166136261u;
    while (size >= 4) {
        value = (value ^ bytes[0]) * 16777619u;
        value = (value ^ bytes[1]) * 16777619u;
        value = (value ^ bytes[2]) * 16777619u;
        value = (value ^ bytes[3]) * 16777619u;
        bytes += 4; size -= 4;
    }
    while (size--) value = (value ^ *bytes++) * 16777619u;
    return value;
}

static inline int TWChunkEqual(const unsigned char *a, const unsigned char *b,
                               unsigned int size) {
    typedef unsigned int Word __attribute__((__may_alias__));
    if (!(((TWBankAddress)a | (TWBankAddress)b) & 3u)) {
        while (size >= sizeof(Word)) {
            if (*(const Word *)a != *(const Word *)b) return 0;
            a += sizeof(Word); b += sizeof(Word); size -= sizeof(Word);
        }
    }
    for (unsigned int i = 0; i < size; ++i) if (a[i] != b[i]) return 0;
    return 1;
}

static inline unsigned int TWChunkKind(const TWChunkPool *pool, const TWChunkSlot *slot) {
    return slot->count && slot->ids[0] && slot->ids[0] <= TW_CHUNK_DESCRIPTORS
        ? pool->chunks[slot->ids[0] - 1].reserved : TW_CHUNK_QUICK;
}

static inline int TWChunkValid(const TWBankMemory *memory) {
    const TWChunkPool *pool = TWChunkDirectory(memory);
    if (!TWChunkLayoutValid(memory, pool)) return 0;
    unsigned short refs[TW_CHUNK_DESCRIPTORS] = {0};
    for (unsigned int s = 0; s <= TW_CHUNK_SLOTS; ++s) {
        const TWChunkSlot *slot = &pool->slots[s];
        if (slot->count > TW_CHUNK_BLOCKS ||
            (s == TW_CHUNK_SLOTS && pool->target == TW_CHUNK_SLOTS && slot->count)) return 0;
        const unsigned int kind = TWChunkKind(pool, slot);
        unsigned int packed = slot->count && kind == TW_CHUNK_QUICK ? 8 : 0, raw = 0;
        for (unsigned int i = 0; i < slot->count; ++i) {
            const unsigned int id = slot->ids[i];
            if (!id || id > TW_CHUNK_DESCRIPTORS) return 0;
            const TWChunk *chunk = &pool->chunks[id - 1];
            const unsigned char *bytes = TWChunkData(memory, chunk);
            unsigned int blockRaw = chunk->size;
            if (!bytes || chunk->reserved != kind || (kind == TW_CHUNK_QUICK &&
                (!TWChunkHeader(bytes, chunk->size, &blockRaw) ||
                 (i + 1 < slot->count && blockRaw != TW_CHUNK_RAW_BYTES)))) return 0;
            ++refs[id - 1];
            packed += chunk->size;
            raw += blockRaw;
        }
        if (packed != slot->packedBytes || raw != slot->rawBytes) return 0;
    }
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        const TWChunk *a = &pool->chunks[i];
        if (a->refs != refs[i] || a->reserved > TW_CHUNK_OPAQUE) return 0;
        if (!a->refs) {
            if (a->offset || a->size || a->hash || a->reserved) return 0;
            continue;
        }
        if (!TWChunkData(memory, a) || (a->offset & 31u) ||
            a->offset > pool->highWater || TWChunkAlign(a->size) > pool->highWater - a->offset)
            return 0;
        for (unsigned int j = 0; j < i; ++j) {
            const TWChunk *b = &pool->chunks[j];
            if (b->refs && a->offset < b->offset + TWChunkAlign(b->size) &&
                b->offset < a->offset + TWChunkAlign(a->size)) return 0;
        }
    }
    return 1;
}

static inline int TWChunkInit(const TWBankMemory *memory) {
    TWChunkPool *pool = TWChunkDirectory(memory);
    if (!pool) return 0;
    for (unsigned int i = 0; i < TW_CHUNK_DIRECTORY_BYTES; ++i) memory->banks[0][i] = 0;
    pool->magic = TW_CHUNK_MAGIC;
    for (unsigned int i = 0; i < TW_BANK_MAX; ++i) pool->sizes[i] = memory->sizes[i];
    pool->bankCount = memory->count;
    pool->highWater = TW_CHUNK_DIRECTORY_BYTES;
    pool->target = TW_CHUNK_SLOTS;
    return 1;
}

static inline void TWChunkRelease(TWChunkPool *pool, TWChunkSlot *slot) {
    for (unsigned int i = 0; i < slot->count; ++i) {
        TWChunk *chunk = &pool->chunks[slot->ids[i] - 1];
        if (!--chunk->refs) { chunk->offset = chunk->size = chunk->hash = 0; chunk->reserved = 0; }
    }
    unsigned char *bytes = (unsigned char *)slot;
    for (unsigned int i = 0; i < sizeof(*slot); ++i) bytes[i] = 0;
}

static inline int TWChunkBegin(const TWBankMemory *memory, unsigned int target) {
    if (target >= TW_CHUNK_SLOTS || !TWChunkValid(memory)) return 0;
    TWChunkPool *pool = TWChunkDirectory(memory);
    if (pool->target != TW_CHUNK_SLOTS) return 0;
    pool->target = target;
    return 1;
}

static inline int TWChunkAbort(const TWBankMemory *memory) {
    if (!TWChunkValid(memory)) return 0;
    TWChunkPool *pool = TWChunkDirectory(memory);
    if (pool->target == TW_CHUNK_SLOTS) return 0;
    TWChunkRelease(pool, &pool->slots[TW_CHUNK_SLOTS]);
    pool->target = TW_CHUNK_SLOTS;
    return 1;
}

static inline unsigned int TWChunkPlacement(const TWBankMemory *memory,
                                            unsigned int offset, unsigned int size) {
    const unsigned int capacity = TWBankCapacity(memory);
    while (size && offset < capacity && size <= capacity - offset) {
        TWBankSpan span;
        if (!TWBankSpanAt(memory, offset, size, &span)) return ~0u;
        if (span.size == size) return offset;
        offset += span.size;
    }
    return ~0u;
}

/* Stable descriptor IDs let compaction move payloads without rewriting tapes. */
static inline int TWChunkCompact(const TWBankMemory *memory) {
    if (!TWChunkValid(memory)) return 0;
    TWChunkPool *pool = TWChunkDirectory(memory);
    unsigned int cursor = TW_CHUNK_DIRECTORY_BYTES, previous = 0;
    for (;;) {
        unsigned int selected = TW_CHUNK_DESCRIPTORS, source = ~0u;
        for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
            const TWChunk *chunk = &pool->chunks[i];
            if (chunk->refs && chunk->offset >= previous && chunk->offset < source) {
                selected = i; source = chunk->offset;
            }
        }
        if (selected == TW_CHUNK_DESCRIPTORS) break;
        TWChunk *chunk = &pool->chunks[selected];
        const unsigned int size = TWChunkAlign(chunk->size);
        cursor = TWChunkPlacement(memory, cursor, size);
        if (cursor == ~0u || cursor > source ||
            !TWBankMove(memory, cursor, source, chunk->size)) __builtin_trap();
        previous = source + size;
        chunk->offset = cursor;
        cursor += size;
    }
    pool->highWater = cursor;
    return 1;
}

/* No old slot is reclaimed to admit a candidate. Failure requires Abort. */
static inline int TWChunkAppendHashed(const TWBankMemory *memory,
                                      const unsigned char *bytes, unsigned int size,
                                      unsigned int hash) {
    TWChunkPool *pool = TWChunkDirectory(memory);
    unsigned int raw;
    if (!TWChunkLayoutValid(memory, pool) || pool->target >= TW_CHUNK_SLOTS ||
        !TWBankExternalBuffer(memory, bytes, size) ||
        !TWChunkHeader(bytes, size, &raw)) return 0;
    TWChunkSlot *slot = &pool->slots[TW_CHUNK_SLOTS];
    if (slot->count >= TW_CHUNK_BLOCKS || TWChunkKind(pool, slot) != TW_CHUNK_QUICK ||
        (slot->count && slot->rawBytes != slot->count * TW_CHUNK_RAW_BYTES)) return 0;
    unsigned int freeId = TW_CHUNK_DESCRIPTORS, selected = TW_CHUNK_DESCRIPTORS;
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        const TWChunk *chunk = &pool->chunks[i];
        if (chunk->reserved > TW_CHUNK_OPAQUE) return 0;
        if (!chunk->refs) {
            if (chunk->offset || chunk->size || chunk->hash || chunk->reserved) return 0;
            if (freeId == TW_CHUNK_DESCRIPTORS) freeId = i;
            continue;
        }
        const unsigned char *data = TWChunkData(memory, chunk);
        if (!data || chunk->refs > TW_CHUNK_DESCRIPTORS ||
            chunk->offset > pool->highWater ||
            TWChunkAlign(chunk->size) > pool->highWater - chunk->offset) return 0;
        if (selected == TW_CHUNK_DESCRIPTORS && chunk->reserved == TW_CHUNK_QUICK && chunk->size == size &&
            chunk->hash == hash && TWChunkEqual(data, bytes, size)) selected = i;
    }
    if (selected == TW_CHUNK_DESCRIPTORS) {
        if (freeId == TW_CHUNK_DESCRIPTORS) return 0;
        unsigned int offset = TWChunkPlacement(memory, pool->highWater, TWChunkAlign(size));
        if (offset == ~0u) {
            if (!TWChunkCompact(memory)) return 0;
            offset = TWChunkPlacement(memory, pool->highWater, TWChunkAlign(size));
            if (offset == ~0u) return 0;
        }
        if (!TWBankCopyIn(memory, offset, bytes, size)) return 0;
        selected = freeId;
        TWChunk *chunk = &pool->chunks[selected];
        chunk->offset = offset; chunk->size = size; chunk->hash = hash;
        pool->highWater = offset + TWChunkAlign(size);
    }
    if (pool->chunks[selected].refs >= TW_CHUNK_DESCRIPTORS) return 0;
    ++pool->chunks[selected].refs;
    slot->ids[slot->count++] = (unsigned short)(selected + 1);
    slot->packedBytes += size + (slot->count == 1 ? 8 : 0);
    slot->rawBytes += raw;
    return 1;
}

static inline int TWChunkAppend(const TWBankMemory *memory,
                                const unsigned char *bytes, unsigned int size) {
    unsigned int raw;
    if (!TWBankExternalBuffer(memory, bytes, size) ||
        !TWChunkHeader(bytes, size, &raw)) return 0;
    return TWChunkAppendHashed(memory, bytes, size, TWChunkHash(bytes, size));
}

static inline int TWChunkCommit(const TWBankMemory *memory, unsigned int rawBytes,
                                unsigned int packedBytes, unsigned int metadataTag) {
    if (!TWChunkValid(memory)) return 0;
    TWChunkPool *pool = TWChunkDirectory(memory);
    TWChunkSlot *pending = &pool->slots[TW_CHUNK_SLOTS];
    if (pool->target >= TW_CHUNK_SLOTS || !pending->count ||
        pending->rawBytes != rawBytes || pending->packedBytes != packedBytes) return 0;
    TWChunkSlot *slot = &pool->slots[pool->target];
    TWChunkRelease(pool, slot);
    *slot = *pending;
    slot->metadataTag = metadataTag;
    unsigned char *bytes = (unsigned char *)pending;
    for (unsigned int i = 0; i < sizeof(*pending); ++i) bytes[i] = 0;
    pool->target = TW_CHUNK_SLOTS;
    return 1;
}

static inline int TWChunkClear(const TWBankMemory *memory, unsigned int slot) {
    if (slot >= TW_CHUNK_SLOTS || !TWChunkValid(memory)) return 0;
    TWChunkPool *pool = TWChunkDirectory(memory);
    if (pool->target != TW_CHUNK_SLOTS || !pool->slots[slot].count) return 0;
    TWChunkRelease(pool, &pool->slots[slot]);
    return 1;
}

#endif
