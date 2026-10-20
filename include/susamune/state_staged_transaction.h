#ifndef TIMEWARP_STATE_STAGED_TRANSACTION_H
#define TIMEWARP_STATE_STAGED_TRANSACTION_H

#include "state_chunk_pool.h"
#include "state_crc.h"

/* Exclusive ownership covers preparation, borrowed bytes and the complete
 * commit. The caller validates decoded state/owners before committing. */
enum {
    TWS_MAGIC = 0x54575331,
    TWS_INPUT_OFFSET = (sizeof(TWChunkPool) + 31) & ~31,
    TWS_INPUT_BYTES = 2080,
    TWS_PLAN_OFFSET = TWS_INPUT_OFFSET + TWS_INPUT_BYTES,
    TWS_REFS_OFFSET = TWS_PLAN_OFFSET + TW_CHUNK_DESCRIPTORS * 4,
    TWS_CRC_OFFSET = TWS_REFS_OFFSET + TW_CHUNK_DESCRIPTORS * 2,
    TWS_CONTROL_OFFSET = TWS_CRC_OFFSET + TW_CRC_WORKSPACE_BYTES,
    TWS_MAX_STAGING = 0x2F0000
};
typedef struct TWStageMemory {
    const TWBankMemory *pool;
    unsigned char *staging;
    unsigned int size;
} TWStageMemory;
typedef struct TWStageToken { unsigned int epoch, sequence, slot, generation, tag; } TWStageToken;
typedef struct TWStageControl {
    unsigned int magic, epoch, sequence, active, startHighWater;
    unsigned int generations[3], rootChecksums[3], rootSignatures[3];
    unsigned int finalHighWater, liveCount, stagePeak, copiedBytes;
} TWStageControl;
#ifdef __cplusplus
static_assert(TWS_CONTROL_OFFSET + sizeof(TWStageControl) <= TW_CHUNK_DIRECTORY_BYTES,
              "staged plan, CRC table and reader table must fit charged directory");
#endif

static inline int TWSMemoryValid(const TWStageMemory *m) {
    if (!m || !TWChunkMemoryValid(m->pool) || m->size > TWS_MAX_STAGING ||
        (m->size & 31u) || (m->size && ((TWBankAddress)m->staging & 31u)) ||
        !TWBankExternalBuffer(m->pool, m->staging, m->size) ||
        !TWBankExternalBuffer(m->pool, m, sizeof(*m))) return 0;
    const TWBankAddress stage = (TWBankAddress)m->staging;
    const TWBankAddress desc = (TWBankAddress)m;
    const TWBankAddress bankDesc = (TWBankAddress)m->pool;
    return (!m->size || ((desc + sizeof(*m) <= stage || stage + m->size <= desc) &&
            (bankDesc + sizeof(*m->pool) <= stage || stage + m->size <= bankDesc))) &&
        m->size <= ~0u - TWBankCapacity(m->pool);
}
static inline TWStageControl *TWSControl(const TWStageMemory *m) {
    return TWSMemoryValid(m) ? (TWStageControl *)(m->pool->banks[0] + TWS_CONTROL_OFFSET) : 0;
}
static inline unsigned int *TWSPlan(const TWStageMemory *m) {
    return (unsigned int *)(m->pool->banks[0] + TWS_PLAN_OFFSET);
}
static inline unsigned short *TWSRefs(const TWStageMemory *m) {
    return (unsigned short *)(m->pool->banks[0] + TWS_REFS_OFFSET);
}
static inline int TWSExternal(const TWStageMemory *m, const void *data, unsigned int size) {
    if (!TWSMemoryValid(m) || !TWBankExternalBuffer(m->pool, data, size)) return 0;
    const TWBankAddress p = (TWBankAddress)data, s = (TWBankAddress)m->staging;
    return !size || !m->size || p + size <= s || s + m->size <= p;
}
static inline const unsigned char *TWSData(const TWStageMemory *m, const TWChunk *c) {
    const unsigned int capacity = TWBankCapacity(m->pool);
    if (!c->refs || c->reserved > TW_CHUNK_OPAQUE || c->size < (c->reserved ? 1u : 9u) ||
        c->size > TW_CHUNK_RAW_BYTES + (c->reserved ? 0u : 8u) ||
        (c->offset & 31u) || c->offset < TW_CHUNK_DIRECTORY_BYTES) return 0;
    if (c->offset < capacity) return TWChunkData(m->pool, c);
    const unsigned int offset = c->offset - capacity;
    return offset <= m->size && TWChunkAlign(c->size) <= m->size - offset
        ? m->staging + offset : 0;
}
static inline int TWSLayout(const TWStageMemory *m) {
    const TWStageControl *c = TWSControl(m);
    if (!c || c->magic != TWS_MAGIC || !c->epoch || c->active > 1) return 0;
    const TWChunkPool *p = TWChunkDirectory(m->pool);
    if (p->magic != TW_CHUNK_MAGIC || p->bankCount != m->pool->count ||
        p->target > 3 || c->active != (p->target < 3) ||
        p->highWater < TW_CHUNK_DIRECTORY_BYTES || (p->highWater & 31u) ||
        p->highWater > TWBankCapacity(m->pool) + m->size) return 0;
    for (unsigned int i = 0; i < TW_BANK_MAX; ++i)
        if (p->sizes[i] != m->pool->sizes[i]) return 0;
    return 1;
}
static inline int TWSValid(const TWStageMemory *m) {
    if (!TWSLayout(m)) return 0;
    const TWChunkPool *p = TWChunkDirectory(m->pool);
    unsigned short *refs = TWSRefs(m);
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) refs[i] = 0;
    for (unsigned int s = 0; s < 4; ++s) {
        const TWChunkSlot *root = &p->slots[s];
        if (root->count > TW_CHUNK_BLOCKS || (s == 3 && p->target == 3 && root->count)) return 0;
        const unsigned int kind = TWChunkKind(p, root);
        unsigned int packed = root->count && kind == TW_CHUNK_QUICK ? 8 : 0, raw = 0;
        for (unsigned int i = 0; i < root->count; ++i) {
            const unsigned int id = root->ids[i];
            if (!id || id > TW_CHUNK_DESCRIPTORS) return 0;
            const TWChunk *chunk = &p->chunks[id - 1];
            unsigned int blockRaw = chunk->size;
            if ((s < 3 && chunk->offset >= TWBankCapacity(m->pool)) ||
                !TWSData(m, chunk) || chunk->reserved != kind || (kind == TW_CHUNK_QUICK &&
                (!TWChunkHeader(TWSData(m, chunk), chunk->size, &blockRaw) ||
                 (i + 1 < root->count && blockRaw != TW_CHUNK_RAW_BYTES)))) return 0;
            ++refs[id - 1]; packed += chunk->size; raw += blockRaw;
        }
        if (packed != root->packedBytes || raw != root->rawBytes) return 0;
    }
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        const TWChunk *a = &p->chunks[i];
        if (a->refs != refs[i] || a->reserved > TW_CHUNK_OPAQUE) return 0;
        if (!a->refs) {
            if (a->offset || a->size || a->hash || a->reserved) return 0;
            continue;
        }
        if (!TWSData(m, a) || a->offset > p->highWater ||
            TWChunkAlign(a->size) > p->highWater - a->offset) return 0;
        for (unsigned int j = 0; j < i; ++j) {
            const TWChunk *b = &p->chunks[j];
            if (b->refs && a->offset < b->offset + TWChunkAlign(b->size) &&
                b->offset < a->offset + TWChunkAlign(a->size)) return 0;
        }
    }
    return 1;
}
static inline unsigned int TWSChecksum(const TWStageMemory *m, const TWChunkSlot *root) {
    const void *table = m->pool->banks[0] + TWS_CRC_OFFSET;
    const unsigned char header[8] = {0x4d,0x53,0x4c,0x34,0,2,0,0};
    unsigned int crc = ~0u;
    if (!root->count) return 0;
    const TWChunkPool *p = TWChunkDirectory(m->pool);
    if (TWChunkKind(p, root) == TW_CHUNK_QUICK)
        crc = TWCrcSharedUpdate(table, crc, header, sizeof(header));
    for (unsigned int i = 0; i < root->count; ++i) {
        const TWChunk *chunk = &p->chunks[root->ids[i] - 1];
        crc = TWCrcSharedUpdate(table, crc, TWSData(m, chunk), chunk->size);
    }
    return ~crc;
}
static inline int TWSAttach(const TWStageMemory *m, unsigned int epoch) {
    TWStageControl *c = TWSControl(m);
    if (!c || c->magic || !epoch || !TWChunkValid(m->pool) || TWChunkDirectory(m->pool)->target != 3) return 0;
    if (!TWCrcSharedInit(m->pool->banks[0] + TWS_CRC_OFFSET, TW_CRC_WORKSPACE_BYTES)) return 0;
    c->magic = TWS_MAGIC; c->epoch = epoch; c->sequence = c->active = 0;
    for (unsigned int i = 0; i < 3; ++i) c->generations[i] = 1;
    return 1;
}
static inline int TWSTokenMatches(const TWStageMemory *m, TWStageToken token) {
    const TWStageControl *c = TWSControl(m);
    const TWChunkPool *p = TWChunkDirectory(m->pool);
    return c && p && c->active && token.slot < 3 && p->target == token.slot &&
        token.epoch == c->epoch && token.sequence == c->sequence &&
        token.generation == c->generations[token.slot] && token.tag == p->slots[token.slot].metadataTag;
}
static inline int TWSBeginWithChecksums(const TWStageMemory *m, unsigned int slot, unsigned int generation,
    unsigned int tag, TWStageToken *token, const unsigned int *expectedChecksums) {
    if (!TWSValid(m) || !TWSExternal(m, token, sizeof(*token)) || slot >= 3 ||
        (expectedChecksums && !TWSExternal(m, expectedChecksums, 3 * sizeof(*expectedChecksums)))) return 0;
    const TWBankAddress output = (TWBankAddress)token;
    const TWBankAddress adapter = (TWBankAddress)m, banks = (TWBankAddress)m->pool;
    if ((output < adapter + sizeof(*m) && adapter < output + sizeof(*token)) ||
        (output < banks + sizeof(*m->pool) && banks < output + sizeof(*token))) return 0;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWStageControl *c = TWSControl(m);
    if (c->active || generation != c->generations[slot] || tag != p->slots[slot].metadataTag ||
        c->sequence == ~0u || generation == ~0u || !TWChunkCompact(m->pool)) return 0;
    for (unsigned int i = 0; i < 3; ++i) {
        c->rootChecksums[i] = expectedChecksums ? expectedChecksums[i] : TWSChecksum(m, &p->slots[i]);
        c->rootSignatures[i] = TWChunkHash((const unsigned char *)&p->slots[i], sizeof(TWChunkSlot));
    }
    c->startHighWater = p->highWater; c->stagePeak = c->copiedBytes = 0;
    c->active = 1; ++c->sequence; p->target = slot;
    token->epoch = c->epoch; token->sequence = c->sequence; token->slot = slot;
    token->generation = generation; token->tag = tag;
    return 1;
}
static inline int TWSBegin(const TWStageMemory *m, unsigned int slot, unsigned int generation,
                          unsigned int tag, TWStageToken *token) {
    return TWSBeginWithChecksums(m, slot, generation, tag, token, 0);
}
/* The encoder borrows its header and payload separately; copy only novel bytes
 * directly into their final candidate block, without another block buffer. */
static inline int TWSAppendParts(const TWStageMemory *m, TWStageToken token,
    const unsigned char *header, unsigned int headerSize,
    const unsigned char *payload, unsigned int payloadSize) {
    unsigned int raw;
    if (!TWSLayout(m) || !TWSTokenMatches(m, token) || headerSize != 8 ||
        !payloadSize || payloadSize > TW_CHUNK_RAW_BYTES ||
        !TWSExternal(m, header, headerSize) || !TWSExternal(m, payload, payloadSize) ||
        !TWChunkHeader(header, headerSize + payloadSize, &raw)) return 0;
    const unsigned int size = headerSize + payloadSize;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWChunkSlot *pending = &p->slots[3];
    if (pending->count >= TW_CHUNK_BLOCKS || TWChunkKind(p, pending) != TW_CHUNK_QUICK ||
        (pending->count && pending->rawBytes != pending->count * TW_CHUNK_RAW_BYTES)) return 0;
    const void *table = m->pool->banks[0] + TWS_CRC_OFFSET;
    const unsigned int hash = ~TWCrcSharedUpdate(table, TWCrcSharedUpdate(table, ~0u, header, headerSize), payload, payloadSize);
    const unsigned int capacity = TWBankCapacity(m->pool);
    unsigned int selected = TW_CHUNK_DESCRIPTORS, freeId = TW_CHUNK_DESCRIPTORS;
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        const TWChunk *chunk = &p->chunks[i];
        if (chunk->reserved > TW_CHUNK_OPAQUE) return 0;
        if (!chunk->refs) {
            if (chunk->offset || chunk->size || chunk->hash || chunk->reserved) return 0;
            if (freeId == TW_CHUNK_DESCRIPTORS) freeId = i;
            continue;
        }
        const unsigned char *data = TWSData(m, chunk);
        if (!data || chunk->refs > TW_CHUNK_DESCRIPTORS || chunk->offset > p->highWater ||
            TWChunkAlign(chunk->size) > p->highWater - chunk->offset) return 0;
        if (selected == TW_CHUNK_DESCRIPTORS && chunk->reserved == TW_CHUNK_QUICK &&
            chunk->size == size && chunk->hash == hash &&
            TWChunkEqual(data, header, headerSize) &&
            TWChunkEqual(data + headerSize, payload, payloadSize)) selected = i;
    }
    if (selected == TW_CHUNK_DESCRIPTORS) {
        if (freeId == TW_CHUNK_DESCRIPTORS) return 0;
        unsigned int offset = TWChunkPlacement(m->pool, p->highWater, TWChunkAlign(size));
        unsigned char *destination;
        if (offset != ~0u) {
            TWBankSpan span;
            if (!TWBankSpanAt(m->pool, offset, TWChunkAlign(size), &span) || span.size != TWChunkAlign(size)) return 0;
            destination = span.data;
        } else {
            offset = p->highWater < capacity ? capacity : p->highWater;
            if (offset - capacity > m->size || TWChunkAlign(size) > m->size - (offset - capacity)) return 0;
            destination = m->staging + offset - capacity;
        }
        StateSlotPoolCopyForward(destination, header, headerSize);
        StateSlotPoolCopyForward(destination + headerSize, payload, payloadSize);
        selected = freeId;
        TWChunk *chunk = &p->chunks[selected];
        chunk->offset = offset; chunk->size = size; chunk->hash = hash;
        p->highWater = offset + TWChunkAlign(size);
        if (p->highWater > capacity) TWSControl(m)->stagePeak = p->highWater - capacity;
    }
    if (p->chunks[selected].refs >= TW_CHUNK_DESCRIPTORS) return 0;
    ++p->chunks[selected].refs;
    pending->ids[pending->count++] = (unsigned short)(selected + 1);
    pending->rawBytes += raw; pending->packedBytes += size + (pending->count == 1 ? 8 : 0);
    return 1;
}
static inline int TWSAppend(const TWStageMemory *m, TWStageToken token,
                           const unsigned char *bytes, unsigned int size) {
    if (size < 9 || size > TW_CHUNK_RAW_BYTES + 8 || !TWSExternal(m, bytes, size)) return 0;
    return TWSAppendParts(m, token, bytes, 8, bytes + 8, size - 8);
}

/* Opaque bytes have no invented framing. Their root rawBytes counts stored
 * bytes; the adapter separately binds the decoded size and Adler checksum. */
static inline unsigned char *TWSReserveOpaque(const TWStageMemory *m, TWStageToken token,
                                              unsigned int size) {
    if (!TWSLayout(m) || !TWSTokenMatches(m, token) || !size || size > TW_CHUNK_RAW_BYTES) return 0;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWChunkSlot *pending = &p->slots[3];
    if (pending->count >= TW_CHUNK_BLOCKS ||
        (pending->count && TWChunkKind(p, pending) != TW_CHUNK_OPAQUE)) return 0;
    unsigned int id = TW_CHUNK_DESCRIPTORS;
    for (unsigned int n = 0; n < TW_CHUNK_DESCRIPTORS; ++n) {
        const TWChunk *c = &p->chunks[n];
        if (!c->refs) {
            if (c->offset || c->size || c->hash || c->reserved) return 0;
            if (id == TW_CHUNK_DESCRIPTORS) id = n;
        } else if (c->refs > TW_CHUNK_DESCRIPTORS || !TWSData(m, c) || c->offset > p->highWater ||
                   TWChunkAlign(c->size) > p->highWater - c->offset) return 0;
    }
    if (id == TW_CHUNK_DESCRIPTORS) return 0;
    const unsigned int capacity = TWBankCapacity(m->pool), aligned = TWChunkAlign(size);
    unsigned int offset = TWChunkPlacement(m->pool, p->highWater, aligned);
    unsigned char *destination;
    if (offset != ~0u) {
        TWBankSpan span;
        if (!TWBankSpanAt(m->pool, offset, aligned, &span) || span.size != aligned) return 0;
        destination = span.data;
    } else {
        offset = p->highWater < capacity ? capacity : p->highWater;
        if (offset - capacity > m->size || aligned > m->size - (offset - capacity)) return 0;
        destination = m->staging + offset - capacity;
    }
    TWChunk *chunk = &p->chunks[id];
    chunk->offset = offset; chunk->size = size; chunk->hash = 0;
    chunk->refs = 1; chunk->reserved = TW_CHUNK_OPAQUE;
    pending->ids[pending->count++] = (unsigned short)(id + 1);
    pending->rawBytes += size; pending->packedBytes += size;
    p->highWater = offset + aligned;
    if (p->highWater > capacity) TWSControl(m)->stagePeak = p->highWater - capacity;
    return destination;
}
static inline int TWSAbort(const TWStageMemory *m, TWStageToken token) {
    if (!TWSValid(m) || !TWSTokenMatches(m, token)) return 0;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWStageControl *c = TWSControl(m);
    TWChunkRelease(p, &p->slots[3]);
    p->highWater = c->startHighWater; p->target = 3; c->active = 0;
    return 1;
}

/* Plans only downward moves, in source order. No destination can overwrite
 * a later source; staging is disjoint and logically follows every pool bank. */
enum TWSPreflightResult { TWS_PREFLIGHT_INVALID, TWS_PREFLIGHT_FITS, TWS_PREFLIGHT_FULL };
static inline enum TWSPreflightResult TWSPreflightStatus(const TWStageMemory *m, TWStageToken token,
    unsigned int raw, unsigned int packed, unsigned int checksum) {
    if (!TWSValid(m) || !TWSTokenMatches(m, token)) return TWS_PREFLIGHT_INVALID;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWStageControl *c = TWSControl(m);
    const TWChunkSlot *pending = &p->slots[3];
    if (!pending->count || pending->rawBytes != raw || pending->packedBytes != packed ||
        TWSChecksum(m, pending) != checksum || c->generations[token.slot] == ~0u) return TWS_PREFLIGHT_INVALID;
    for (unsigned int i = 0; i < 3; ++i)
        if (c->rootSignatures[i] != TWChunkHash((const unsigned char *)&p->slots[i], sizeof(TWChunkSlot)) ||
            c->rootChecksums[i] != TWSChecksum(m, &p->slots[i])) return TWS_PREFLIGHT_INVALID;
    unsigned int *plan = TWSPlan(m);
    unsigned short *refs = TWSRefs(m);
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) { plan[i] = ~0u; refs[i] = 0; }
    for (unsigned int s = 0; s < 4; ++s) if (s != token.slot)
        for (unsigned int i = 0; i < p->slots[s].count; ++i) ++refs[p->slots[s].ids[i] - 1];
    unsigned int cursor = TW_CHUNK_DIRECTORY_BYTES, previous = 0, count = 0;
    for (;;) {
        unsigned int selected = TW_CHUNK_DESCRIPTORS, source = ~0u;
        for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i)
            if (refs[i] && p->chunks[i].offset >= previous && p->chunks[i].offset < source) {
                selected = i; source = p->chunks[i].offset;
            }
        if (selected == TW_CHUNK_DESCRIPTORS) break;
        const TWChunk *chunk = &p->chunks[selected];
        const unsigned int size = TWChunkAlign(chunk->size);
        cursor = TWChunkPlacement(m->pool, cursor, size);
        if (cursor == ~0u) return TWS_PREFLIGHT_FULL;
        if (cursor > source) return TWS_PREFLIGHT_INVALID;
        plan[selected] = cursor; cursor += size; previous = source + size; ++count;
    }
    c->finalHighWater = cursor; c->liveCount = count;
    return TWS_PREFLIGHT_FITS;
}
static inline int TWSPreflight(const TWStageMemory *m, TWStageToken token,
                             unsigned int raw, unsigned int packed, unsigned int checksum) {
    return TWSPreflightStatus(m, token, raw, packed, checksum) == TWS_PREFLIGHT_FITS;
}

/* Only called after preflight, under the same uninterrupted exclusive lease. */
static inline unsigned char *TWSAddressUnchecked(const TWStageMemory *m, unsigned int offset) {
    for (unsigned int i = 0; i < m->pool->count; ++i) {
        if (offset < m->pool->sizes[i]) return m->pool->banks[i] + offset;
        offset -= m->pool->sizes[i];
    }
    return m->staging + offset;
}
static inline int TWSCommit(const TWStageMemory *m, TWStageToken token, unsigned int raw,
                           unsigned int packed, unsigned int checksum, unsigned int tag) {
    if (!TWSPreflight(m, token, raw, packed, checksum)) return 0;
    TWChunkPool *p = TWChunkDirectory(m->pool);
    TWStageControl *c = TWSControl(m);
    const unsigned int *plan = TWSPlan(m);
    TWChunkRelease(p, &p->slots[token.slot]);
    unsigned int previous = 0;
    for (unsigned int pass = 0; pass < c->liveCount; ++pass) {
        unsigned int selected = 0, source = ~0u;
        for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i)
            if (p->chunks[i].refs && p->chunks[i].offset >= previous && p->chunks[i].offset < source) {
                selected = i; source = p->chunks[i].offset;
            }
        TWChunk *chunk = &p->chunks[selected];
        const unsigned int destination = plan[selected];
        StateSlotPoolCopyForward(TWSAddressUnchecked(m, destination), TWSAddressUnchecked(m, source), chunk->size);
        if (destination != source) c->copiedBytes += chunk->size;
        previous = source + TWChunkAlign(chunk->size); chunk->offset = destination;
    }
    p->highWater = c->finalHighWater;
    p->slots[token.slot] = p->slots[3];
    p->slots[token.slot].metadataTag = tag;
    unsigned char *pending = (unsigned char *)&p->slots[3];
    for (unsigned int i = 0; i < sizeof(TWChunkSlot); ++i) pending[i] = 0;
    ++c->generations[token.slot]; p->target = 3; c->active = 0;
    return 1;
}
#endif
