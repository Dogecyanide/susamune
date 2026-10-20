#ifndef TIMEWARP_STATE_ROOT_READER_H
#define TIMEWARP_STATE_ROOT_READER_H

#include "state_staged_transaction.h"
#include "susamune/state_codec.hxx"

enum {
    TWR_MAGIC = 0x54575231,
    TWR_SPANS = TW_CHUNK_BLOCKS + 1,
    TWR_TABLE_BYTES = TWR_SPANS * sizeof(StateCodec::ReadSpan) + 8,
    TWR_CONTROL_OFFSET = (TWS_CONTROL_OFFSET + sizeof(TWStageControl) + 31) & ~31,
    TWR_CONTROL_BYTES = 128
};
struct TWRootReadControl {
    unsigned int magic, sequence, active, root, generation, tag;
    unsigned int raw, packed, adler, checksum, rootSignature, spanCount;
    TWStageToken candidate;
    StateCodec::ReadSpan *table;
};
static_assert(sizeof(TWRootReadControl) <= TWR_CONTROL_BYTES, "reader control budget");
static_assert(TWR_CONTROL_OFFSET + TWR_CONTROL_BYTES <= TW_CHUNK_DIRECTORY_BYTES,
              "reader and staged plans must fit the charged directory");
#if __SIZEOF_POINTER__ == 4
static_assert(TWR_TABLE_BYTES <= TWS_INPUT_BYTES, "PPC reader table budget");
#endif

static inline TWRootReadControl *TWRControl(const TWStageMemory *memory) {
    return TWSMemoryValid(memory) ? reinterpret_cast<TWRootReadControl *>(
        memory->pool->banks[0] + TWR_CONTROL_OFFSET) : nullptr;
}
static inline int TWRIdle(const TWStageMemory *memory) {
    const TWRootReadControl *c = TWRControl(memory);
    return c && !c->active && (!c->magic || c->magic == TWR_MAGIC);
}

/* The same exclusive owner must route all pool mutations through these guards
 * until release. Existing low-level allocator calls do not acquire a lease. */
static inline int TWRBegin(const TWStageMemory *m, unsigned int slot, unsigned int generation,
                          unsigned int tag, TWStageToken *token) {
    return TWRIdle(m) && TWSBegin(m, slot, generation, tag, token);
}
static inline int TWRAppend(const TWStageMemory *m, TWStageToken token,
                           const unsigned char *bytes, unsigned int size) {
    return TWRIdle(m) && TWSAppend(m, token, bytes, size);
}
static inline int TWRAppendParts(const TWStageMemory *m, TWStageToken token,
    const unsigned char *header, unsigned int headerSize,
    const unsigned char *payload, unsigned int payloadSize) {
    return TWRIdle(m) && TWSAppendParts(m, token, header, headerSize, payload, payloadSize);
}
static inline int TWRAbort(const TWStageMemory *m, TWStageToken token) {
    return TWRIdle(m) && TWSAbort(m, token);
}
static inline int TWRCommit(const TWStageMemory *m, TWStageToken token, unsigned int raw,
                           unsigned int packed, unsigned int checksum, unsigned int tag) {
    return TWRIdle(m) && TWSCommit(m, token, raw, packed, checksum, tag);
}
static inline int TWRCompact(const TWStageMemory *m) {
    return TWRIdle(m) && !TWSControl(m)->active && TWChunkCompact(m->pool);
}
static inline int TWRClear(const TWStageMemory *m, unsigned int slot,
                          unsigned int generation, unsigned int tag) {
    if (!TWRIdle(m) || !TWSValid(m) || slot >= 3 || TWSControl(m)->active ||
        generation != TWSControl(m)->generations[slot] || generation == ~0u ||
        tag != TWChunkDirectory(m->pool)->slots[slot].metadataTag || !TWChunkClear(m->pool, slot)) return 0;
    ++TWSControl(m)->generations[slot];
    return 1;
}

/* Native tests provide descriptor-only scratch because host pointers are wider.
 * PPC always uses the reserved table; encoded payloads remain in owned banks. */
static inline StateCodec::ReadSpan *TWRTable(const TWStageMemory *m, void *nativeScratch,
                                           unsigned int nativeBytes) {
#if __SIZEOF_POINTER__ == 4
    (void)nativeScratch; (void)nativeBytes;
    return reinterpret_cast<StateCodec::ReadSpan *>(m->pool->banks[0] + TWS_INPUT_OFFSET);
#else
    const TWBankAddress address = reinterpret_cast<TWBankAddress>(nativeScratch);
    const TWBankAddress adapter = reinterpret_cast<TWBankAddress>(m);
    const TWBankAddress banks = reinterpret_cast<TWBankAddress>(m->pool);
    if (nativeBytes < TWR_TABLE_BYTES ||
        (reinterpret_cast<TWBankAddress>(nativeScratch) & (__alignof__(StateCodec::ReadSpan) - 1)) ||
        !TWSExternal(m, nativeScratch, TWR_TABLE_BYTES)) return nullptr;
    if ((address < adapter + sizeof(*m) && adapter < address + TWR_TABLE_BYTES) ||
        (address < banks + sizeof(*m->pool) && banks < address + TWR_TABLE_BYTES)) return nullptr;
    return reinterpret_cast<StateCodec::ReadSpan *>(nativeScratch);
#endif
}

static inline unsigned int TWRBuild(const TWStageMemory *m, unsigned int root,
    unsigned int generation, unsigned int tag, unsigned int raw, unsigned int packed,
    unsigned int adler, unsigned int checksum, TWStageToken candidate,
    void *nativeScratch, unsigned int nativeBytes, bool verifyPayload = true) {
    if (!TWRIdle(m) || !TWSValid(m) || root > 3) return 0;
    TWRootReadControl *control = TWRControl(m);
    if (control->magic && control->sequence == ~0u) return 0;
    TWChunkPool *pool = TWChunkDirectory(m->pool);
    const TWChunkSlot *slot = &pool->slots[root];
    const unsigned int prefix = TWChunkKind(pool, slot) == TW_CHUNK_QUICK ? 1u : 0u;
    if (!raw || raw > 0x2000000u || !slot->count || slot->count > TW_CHUNK_BLOCKS ||
        (prefix && slot->rawBytes != raw) ||
        slot->packedBytes != packed || (verifyPayload && TWSChecksum(m, slot) != checksum)) return 0;
    if (root < 3) {
        if (TWSControl(m)->generations[root] != generation || slot->metadataTag != tag) return 0;
    } else if (!TWSTokenMatches(m, candidate) || generation != candidate.generation + 1u ||
               generation == 0) return 0;
    StateCodec::ReadSpan *spans = TWRTable(m, nativeScratch, nativeBytes);
    if (!spans) return 0;
    unsigned char *frame = reinterpret_cast<unsigned char *>(spans) + TWR_SPANS * sizeof(*spans);
    const unsigned char header[8] = {0x4d,0x53,0x4c,0x34,0,2,0,0};
    for (unsigned int i = 0; i < 8; ++i) frame[i] = header[i];
    if (prefix) spans[0] = {frame, 8};
    for (unsigned int i = 0; i < slot->count; ++i) {
        const TWChunk *chunk = &pool->chunks[slot->ids[i] - 1];
        spans[i + prefix] = {TWSData(m, chunk), chunk->size};
    }
    if (!control->magic) control->sequence = 0;
    control->magic = TWR_MAGIC; ++control->sequence; control->active = 1;
    control->root = root; control->generation = generation; control->tag = tag;
    control->raw = raw; control->packed = packed; control->adler = adler;
    control->checksum = checksum; control->candidate = candidate;
    control->rootSignature = TWChunkHash(reinterpret_cast<const unsigned char *>(slot), sizeof(*slot));
    control->spanCount = slot->count + prefix; control->table = spans;
    return control->sequence;
}

/* Recheck binding and the exact borrowed table immediately before decode. */
static inline int TWRCheck(const TWStageMemory *m, unsigned int sequence, unsigned int expectedAdler,
                          void *nativeScratch, unsigned int nativeBytes) {
    const TWRootReadControl *c = TWRControl(m);
    if (!c || c->magic != TWR_MAGIC || !c->active || c->sequence != sequence ||
        !TWSValid(m) || c->root > 3 || c->adler != expectedAdler ||
        c->table != TWRTable(m, nativeScratch, nativeBytes)) return 0;
    const TWChunkPool *pool = TWChunkDirectory(m->pool);
    const TWChunkSlot *root = &pool->slots[c->root];
    const unsigned int prefix = TWChunkKind(pool, root) == TW_CHUNK_QUICK ? 1u : 0u;
    if (c->rootSignature != TWChunkHash(reinterpret_cast<const unsigned char *>(root), sizeof(*root)) ||
        c->checksum != TWSChecksum(m, root) || c->spanCount != root->count + prefix ||
        (prefix && c->raw != root->rawBytes) || c->packed != root->packedBytes) return 0;
    if (c->root < 3) {
        if (c->generation != TWSControl(m)->generations[c->root] || c->tag != root->metadataTag) return 0;
    } else if (!TWSTokenMatches(m, c->candidate) || c->generation != c->candidate.generation + 1) return 0;
    const unsigned char *frame = reinterpret_cast<const unsigned char *>(c->table) + TWR_SPANS * sizeof(*c->table);
    const unsigned char header[8] = {0x4d,0x53,0x4c,0x34,0,2,0,0};
    if (prefix && (c->table[0].data != frame || c->table[0].size != 8 || !TWChunkEqual(frame, header, 8))) return 0;
    for (unsigned int i = 0; i < root->count; ++i) {
        const TWChunk *chunk = &pool->chunks[root->ids[i] - 1];
        if (c->table[i + prefix].data != TWSData(m, chunk) || c->table[i + prefix].size != chunk->size) return 0;
    }
    return 1;
}
static inline int TWRRelease(const TWStageMemory *m, unsigned int sequence) {
    TWRootReadControl *c = TWRControl(m);
    if (!c || c->magic != TWR_MAGIC || !c->active || c->sequence != sequence) return 0;
    c->active = 0; c->table = nullptr; c->spanCount = 0;
    return 1;
}
#endif
