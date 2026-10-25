#include "susamune/state_quick_replay.hxx"

#if TIMEWARP_QUICK_REPLAY
namespace StateQuickReplay {
namespace {
const unsigned int kMissing = ~0u;
struct Recipe { unsigned int id, block; };
const unsigned int kAdlerCacheOffset = TWR_CONTROL_OFFSET + TWR_CONTROL_BYTES;
const unsigned int kAdlerCacheEntries = (TW_CHUNK_DIRECTORY_BYTES - kAdlerCacheOffset - 32) / 8;
const unsigned int kAdlerCacheMagic = 0x54574131;
struct AdlerEntry { unsigned int id, adler; };
struct AdlerCache {
    unsigned int magic, epoch, generations[3], directoryHash, count, checksum;
    AdlerEntry entries[kAdlerCacheEntries];
};
static_assert(kAdlerCacheEntries == 204 && sizeof(AdlerCache) == 1664, "charged directory cache budget");
static_assert(kAdlerCacheOffset + sizeof(AdlerCache) <= TW_CHUNK_DIRECTORY_BYTES, "cache fits reader tail");
}
struct Plan {
    unsigned int fingerprint;
    StateStore::Store *store;
    Source source;
    TWStageToken token;
    StateStore::Identity identities[3];
    unsigned int generations[3], directoryHash, phase, finalHighWater;
    unsigned int cacheUsable, cacheFingerprint;
    StateCodec::Result encoded;
    unsigned int crc, recipeCount, moveCount;
    Stats statistics;
    TWChunkSlot root;
    TWChunk chunks[TW_CHUNK_DESCRIPTORS];
    unsigned int destinations[TW_CHUNK_DESCRIPTORS];
    unsigned short recipeForId[TW_CHUNK_DESCRIPTORS], moves[TW_CHUNK_DESCRIPTORS];
    Recipe recipes[TW_CHUNK_BLOCKS];
    unsigned int rawAdlers[TW_CHUNK_BLOCKS];
    mutable unsigned char comparison[TW_CHUNK_RAW_BYTES + 8];
};
static_assert(sizeof(Plan) <= 0x4E000, "replay plan fits the existing transfer tail");
static_assert(__builtin_offsetof(Plan, comparison) % __alignof__(AdlerCache) == 0,
              "cache publication scratch alignment");

namespace {
void clear(void *p, unsigned int n) {
    unsigned char *bytes = static_cast<unsigned char *>(p);
    while (n--) *bytes++ = 0;
}
bool same(const StateStore::Identity &a, const StateStore::Identity &b) {
    return a.generation == b.generation && a.tag == b.tag && a.raw == b.raw &&
        a.packed == b.packed && a.adler == b.adler && a.checksum == b.checksum && a.kind == b.kind;
}
unsigned int fingerprint(const Plan &p) {
    const unsigned char *start = reinterpret_cast<const unsigned char *>(&p);
    return TWChunkHash(start + sizeof(p.fingerprint),
        __builtin_offsetof(Plan, comparison) - sizeof(p.fingerprint));
}
bool intact(const Plan &p) { return p.phase == 1 && p.fingerprint == fingerprint(p); }
unsigned int crcBytes(const Plan &p, unsigned int crc, const void *data, unsigned int size) {
    return TWCrcSharedUpdate(p.store->memory->pool->banks[0] + TWS_CRC_OFFSET,
                            crc, data, size);
}
AdlerCache &adlerCache(const Plan &p) {
    return *reinterpret_cast<AdlerCache *>(p.store->memory->pool->banks[0] + kAdlerCacheOffset);
}
unsigned int cacheChecksum(const Plan &p, const AdlerCache &cache) {
    unsigned int crc = crcBytes(p, ~0u, &cache, __builtin_offsetof(AdlerCache, checksum));
    return ~crcBytes(p, crc, cache.entries, sizeof(cache.entries));
}
unsigned int cacheDirectoryHash(const Plan &p, const TWChunkPool &pool) {
    // Begin changes only target; every retained descriptor and root stays bound.
    const unsigned char *bytes = reinterpret_cast<const unsigned char *>(&pool);
    const unsigned int offset = __builtin_offsetof(TWChunkPool, target);
    unsigned int crc = crcBytes(p, ~0u, bytes, offset);
    return ~crcBytes(p, crc, bytes + offset + sizeof(pool.target), sizeof(pool) - offset - sizeof(pool.target));
}
bool cacheValid(const Plan &p) {
    const AdlerCache &cache = adlerCache(p);
    const TWChunkPool *pool = TWChunkDirectory(p.store->memory->pool);
    if (cache.magic != kAdlerCacheMagic || cache.epoch != p.token.epoch ||
        cache.count > kAdlerCacheEntries || cache.directoryHash != cacheDirectoryHash(p, *pool) ||
        cache.checksum != cacheChecksum(p, cache)) return false;
    for (unsigned int i = 0; i < 3; ++i)
        if (cache.generations[i] != p.generations[i]) return false;
    for (unsigned int i = 0; i < cache.count; ++i) {
        const unsigned int id = cache.entries[i].id;
        if (id >= TW_CHUNK_DESCRIPTORS || !pool->chunks[id].refs ||
            pool->chunks[id].reserved != TW_CHUNK_QUICK) return false;
    }
    return true;
}
bool findAdler(const AdlerCache &cache, unsigned int id, unsigned int &adler) {
    for (unsigned int i = 0; i < cache.count; ++i)
        if (cache.entries[i].id == id) { adler = cache.entries[i].adler; return true; }
    return false;
}
void publishCache(Plan &p, const TWChunkPool &pool) {
    AdlerCache &next = *reinterpret_cast<AdlerCache *>(p.comparison);
    clear(&next, sizeof(next));
    unsigned int ignored;
    for (unsigned int i = 0; i < p.root.count && next.count < kAdlerCacheEntries; ++i) {
        const unsigned int id = p.root.ids[i] - 1;
        if (!findAdler(next, id, ignored)) next.entries[next.count++] = {id, p.rawAdlers[i]};
    }
    const AdlerCache &old = adlerCache(p);
    if (p.cacheUsable) for (unsigned int i = 0; i < old.count && next.count < kAdlerCacheEntries; ++i) {
        const AdlerEntry &entry = old.entries[i];
        if (pool.chunks[entry.id].refs && pool.chunks[entry.id].reserved == TW_CHUNK_QUICK &&
            !findAdler(next, entry.id, ignored)) next.entries[next.count++] = entry;
    }
    next.magic = kAdlerCacheMagic; next.epoch = p.token.epoch;
    for (unsigned int i = 0; i < 3; ++i) next.generations[i] = TWSControl(p.store->memory)->generations[i];
    next.directoryHash = cacheDirectoryHash(p, pool);
    next.checksum = cacheChecksum(p, next);
    StateSlotPoolCopyForward(reinterpret_cast<unsigned char *>(&adlerCache(p)),
                            reinterpret_cast<const unsigned char *>(&next), sizeof(next));
}
unsigned int combineAdler(unsigned int a, unsigned int b, unsigned int length) {
    const unsigned int base = 65521, remainder = length % base;
    unsigned int low = a & 65535, high = (remainder * low) % base;
    low += (b & 65535) + base - 1;
    high += (a >> 16) + (b >> 16) + base - remainder;
    if (low >= base) low -= base;
    if (low >= base) low -= base;
    if (high >= base * 2) high -= base * 2;
    if (high >= base) high -= base;
    return low | (high << 16);
}
const unsigned char *address(const Plan &p, const TWChunk &chunk) {
    return chunk.offset == kMissing ? nullptr : TWSData(p.store->memory, &chunk);
}
bool sameBlock(const unsigned char *a, const unsigned char *header,
               const unsigned char *payload, unsigned int size) {
    return a && TWChunkEqual(a, header, 8) && TWChunkEqual(a + 8, payload, size - 8);
}
bool blockValid(const Plan &p, unsigned int index, const StateCodec::PreparedQuickBlock &b) {
    unsigned int raw;
    const unsigned int expected = p.source.rawBytes - index * TW_CHUNK_RAW_BYTES;
    return b.payloadBytes && b.payloadBytes <= TW_CHUNK_RAW_BYTES &&
        TWQuickSeparate(b.payload, b.payloadBytes, &p, sizeof(p)) &&
        TWSExternal(p.store->memory, b.payload, b.payloadBytes) &&
        TWChunkHeader(b.header, b.payloadBytes + 8, &raw) && raw == b.rawBytes &&
        raw == (expected < TW_CHUNK_RAW_BYTES ? expected : TW_CHUNK_RAW_BYTES);
}
unsigned int crcProduct(unsigned int a, unsigned int b) {
    unsigned int result = 0;
    for (unsigned int mask = 0x80000000u; mask; mask >>= 1) {
        if (a & mask) result ^= b;
        b = (b >> 1) ^ (0xedb88320u & (0u - (b & 1u)));
    }
    return result;
}
struct VerifyCache {
    unsigned int seen[TW_CHUNK_DESCRIPTORS / 32];
    unsigned int crc[TW_CHUNK_DESCRIPTORS], shift[TW_CHUNK_DESCRIPTORS], powers[18];
};
static_assert(sizeof(VerifyCache) <= sizeof(Plan::comparison), "verification reuses comparison scratch");
bool payloadsUnchanged(const Plan &p, const TWChunkPool &pool) {
    unsigned int occupied = 0;
    for (unsigned int i = 0; i < 3; ++i) occupied += pool.slots[i].count != 0;
    if (occupied < 2) {
        for (unsigned int i = 0; i < 3; ++i)
            if (TWSChecksum(p.store->memory, &pool.slots[i]) != p.identities[i].checksum) return false;
        return true;
    }
    // Each verification is fresh. Shared descriptors are read once, then their
    // exact CRCs are combined in each root's original order.
    VerifyCache &cache = *reinterpret_cast<VerifyCache *>(p.comparison);
    clear(cache.seen, sizeof(cache.seen));
    cache.powers[0] = 1u << 23;
    for (unsigned int i = 1; i < 18; ++i) cache.powers[i] = crcProduct(cache.powers[i - 1], cache.powers[i - 1]);
    const unsigned char frame[8] = {0x4D,0x53,0x4C,0x34,0,2,0,0};
    const unsigned int prefix = ~crcBytes(p, ~0u, frame, sizeof(frame));
    for (unsigned int slot = 0; slot < 3; ++slot) {
        const TWChunkSlot &root = pool.slots[slot];
        unsigned int crc = root.count && TWChunkKind(&pool, &root) == TW_CHUNK_QUICK ? prefix : 0;
        for (unsigned int n = 0; n < root.count; ++n) {
            const unsigned int id = root.ids[n] - 1, bit = 1u << (id & 31);
            if (!(cache.seen[id >> 5] & bit)) {
                const TWChunk &chunk = pool.chunks[id];
                cache.crc[id] = ~crcBytes(p, ~0u, TWSData(p.store->memory, &chunk), chunk.size);
                unsigned int shift = 0x80000000u, size = chunk.size;
                for (unsigned int i = 0; size; ++i, size >>= 1)
                    if (size & 1u) shift = crcProduct(cache.powers[i], shift);
                cache.shift[id] = shift; cache.seen[id >> 5] |= bit;
            }
            crc = crcProduct(cache.shift[id], crc) ^ cache.crc[id];
        }
        if (crc != p.identities[slot].checksum) return false;
    }
    return true;
}
bool unchanged(const Plan &p, bool payloads) {
    const StateStore::Store &s = *p.store;
    if (!StateStore::valid(s) || !s.pending || s.sealed || s.pin ||
        !TWRIdle(s.memory) || !TWSTokenMatches(s.memory, p.token)) return false;
    const TWChunkPool *pool = TWChunkDirectory(s.memory->pool);
    if (pool->slots[3].count || p.directoryHash != TWChunkHash(
            reinterpret_cast<const unsigned char *>(pool), sizeof(*pool))) return false;
    const TWStageControl *control = TWSControl(s.memory);
    for (unsigned int i = 0; i < 3; ++i)
        if (!same(s.roots[i], p.identities[i]) || control->generations[i] != p.generations[i]) return false;
    if (p.cacheUsable && (adlerCache(p).checksum != p.cacheFingerprint || !cacheValid(p))) return false;
    return !payloads || payloadsUnchanged(p, *pool);
}
Status place(Plan &p) {
    const TWChunkPool *old = TWChunkDirectory(p.store->memory->pool);
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) p.chunks[i].refs = 0;
    for (unsigned int slot = 0; slot < 3; ++slot) if (slot != p.token.slot)
        for (unsigned int i = 0; i < old->slots[slot].count; ++i)
            ++p.chunks[old->slots[slot].ids[i] - 1].refs;
    for (unsigned int i = 0; i < p.root.count; ++i) ++p.chunks[p.root.ids[i] - 1].refs;
    unsigned int cursor = TW_CHUNK_DIRECTORY_BYTES, previous = 0;
    for (;;) {
        unsigned int selected = kMissing, source = kMissing;
        for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i)
            if (p.chunks[i].refs && p.chunks[i].offset >= previous && p.chunks[i].offset < source) {
                selected = i; source = p.chunks[i].offset;
            }
        if (selected == kMissing) break;
        const unsigned int size = TWChunkAlign(p.chunks[selected].size);
        cursor = TWChunkPlacement(p.store->memory->pool, cursor, size);
        if (cursor == kMissing) return FULL;
        if (cursor > source) return INVALID;
        p.destinations[selected] = cursor;
        p.moves[p.moveCount++] = selected;
        if (cursor != source) p.statistics.movedBytes += p.chunks[selected].size;
        cursor += size; previous = source + size;
    }
    for (unsigned int i = 0; i < p.recipeCount; ++i) {
        const unsigned int id = p.recipes[i].id;
        if (p.chunks[id].offset != kMissing) continue;
        const unsigned int size = TWChunkAlign(p.chunks[id].size);
        cursor = TWChunkPlacement(p.store->memory->pool, cursor, size);
        if (cursor == kMissing) return FULL;
        p.destinations[id] = cursor; cursor += size;
    }
    p.finalHighWater = cursor;
    return READY;
}
Status build(Plan &p) {
    const TWStageMemory *memory = p.store->memory;
    const TWChunkPool *pool = TWChunkDirectory(memory->pool);
    p.directoryHash = TWChunkHash(reinterpret_cast<const unsigned char *>(pool), sizeof(*pool));
    for (unsigned int i = 0; i < 3; ++i) {
        p.identities[i] = p.store->roots[i];
        p.generations[i] = TWSControl(memory)->generations[i];
    }
    p.cacheUsable = cacheValid(p);
    if (p.cacheUsable) p.cacheFingerprint = adlerCache(p).checksum;
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        p.chunks[i] = pool->chunks[i]; p.recipeForId[i] = 65535;
        p.destinations[i] = kMissing;
    }
    const unsigned char frame[8] = {0x4D,0x53,0x4C,0x34,0,2,0,0};
    unsigned int powers[18]; powers[0] = 1u << 23;
    for (unsigned int i = 1; i < 18; ++i) powers[i] = crcProduct(powers[i-1], powers[i-1]);
    p.crc = crcBytes(p, ~0u, frame, sizeof(frame));
    p.encoded = {StateCodec::SUCCESS, 8, p.source.rawBytes, 1};
    const unsigned int count = (p.source.rawBytes + TW_CHUNK_RAW_BYTES - 1) / TW_CHUNK_RAW_BYTES;
    const unsigned int capacity = TWBankCapacity(memory->pool);
    unsigned int cacheCursor = pool->highWater;
    bool spilling = false;
    for (unsigned int index = 0; index < count; ++index) {
        StateCodec::PreparedQuickBlock block;
        p.source.encode(p.source.context, index, block);
        if (!blockValid(p, index, block)) return INVALID;
        const unsigned int size = block.payloadBytes + 8;
        const unsigned char *header = block.header, *payload = block.payload;
        // One payload pass supplies the lookup key and the complete stream CRC.
        const unsigned int hash = ~crcBytes(p, crcBytes(p, ~0u, header, 8), payload, block.payloadBytes);
        unsigned int shift = 0x80000000u, length = size;
        for (unsigned int bit = 0; length; ++bit, length >>= 1)
            if (length & 1u) shift = crcProduct(powers[bit], shift);
        p.crc = ~(crcProduct(shift, ~p.crc) ^ hash);
        p.encoded.compressedBytes += size;
        unsigned int selected = kMissing, freeId = kMissing;
        bool copied = false;
        for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
            const TWChunk &c = p.chunks[i];
            if (!c.refs) { if (freeId == kMissing) freeId = i; continue; }
            if (c.reserved != TW_CHUNK_QUICK || c.size != size || c.hash != hash) continue;
            if (c.offset != kMissing) {
                if (sameBlock(address(p, c), header, payload, size)) { selected = i; break; }
            } else {
                if (!copied) {
                    StateSlotPoolCopyForward(p.comparison, header, 8);
                    StateSlotPoolCopyForward(p.comparison + 8, payload, size - 8);
                    header = p.comparison; payload = p.comparison + 8; copied = true;
                }
                StateCodec::PreparedQuickBlock prior;
                p.source.encode(p.source.context, p.recipes[p.recipeForId[i]].block, prior);
                if (!blockValid(p, p.recipes[p.recipeForId[i]].block, prior)) return INVALID;
                if (prior.payloadBytes + 8 == size && TWChunkEqual(header, prior.header, 8) &&
                    TWChunkEqual(payload, prior.payload, size - 8)) { selected = i; break; }
            }
        }
        if (selected == kMissing) {
            if (freeId == kMissing) return INVALID;
            selected = freeId;
            TWChunk &c = p.chunks[selected];
            c = {kMissing, size, hash, 1, TW_CHUNK_QUICK};
            if (!spilling) {
                unsigned int offset = TWChunkPlacement(memory->pool, cacheCursor, TWChunkAlign(size));
                if (offset == kMissing) {
                    offset = cacheCursor < capacity ? capacity : cacheCursor;
                    if (offset - capacity > memory->size || TWChunkAlign(size) > memory->size - (offset - capacity))
                        spilling = true;
                }
                if (!spilling) {
                    c.offset = offset;
                    unsigned char *destination = TWSAddressUnchecked(memory, offset);
                    StateSlotPoolCopyForward(destination, header, 8);
                    StateSlotPoolCopyForward(destination + 8, payload, size - 8);
                    cacheCursor = offset + TWChunkAlign(size);
                    p.statistics.cachedBytes += size;
                }
            }
            p.recipeForId[selected] = p.recipeCount;
            p.recipes[p.recipeCount++] = {selected, index};
            if (c.offset == kMissing) {
                ++p.statistics.spilledBlocks;
                p.statistics.replayRawBytes += block.rawBytes;
            }
        }
        unsigned int rawAdler = block.adler32;
        if (p.source.checksum) {
            bool reused = false;
            for (unsigned int i = 0; i < p.root.count; ++i)
                if (p.root.ids[i] == selected + 1) { rawAdler = p.rawAdlers[i]; reused = true; break; }
            // A CRC match alone never reaches this point: selection compares all bytes.
            if (!reused && p.cacheUsable && p.recipeForId[selected] == 65535)
                reused = findAdler(adlerCache(p), selected, rawAdler);
            if (!reused) rawAdler = p.source.checksum(p.source.context, index, block);
        }
        p.rawAdlers[p.root.count] = rawAdler;
        p.encoded.adler32 = combineAdler(p.encoded.adler32, rawAdler, block.rawBytes);
        p.root.ids[p.root.count++] = selected + 1;
    }
    p.crc = ~p.crc;
    p.root.rawBytes = p.encoded.rawBytes; p.root.packedBytes = p.encoded.compressedBytes;
    return place(p);
}
}

unsigned int workspaceSize() { return (sizeof(Plan) + 31u) & ~31u; }
Status prepare(StateStore::Store &s, unsigned int slot, const StateStore::Identity &expected,
               const Source &source, void *scratch, unsigned int scratchBytes, Plan *&out) {
    out = nullptr;
    if (!source.encode || !source.admitted || !source.rawBytes || source.rawBytes > 0x2000000u ||
        !scratch || (reinterpret_cast<TWBankAddress>(scratch) & 31u) || scratchBytes < workspaceSize() ||
        !StateStore::valid(s) || !TWSExternal(s.memory, scratch, scratchBytes) ||
        !TWQuickSeparate(scratch, scratchBytes, &s, sizeof(s)) ||
        !TWQuickSeparate(scratch, scratchBytes, &source, sizeof(source)) ||
        !TWQuickSeparate(scratch, scratchBytes, s.memory, sizeof(*s.memory)) ||
        !TWQuickSeparate(scratch, scratchBytes, s.memory->pool, sizeof(*s.memory->pool)) ||
        (s.nativeScratch && !TWQuickSeparate(scratch, scratchBytes, s.nativeScratch, s.nativeBytes))) return INVALID;
    if (!source.admitted(source.context)) return SOURCE_BUSY;
    if (!StateStore::beginDeferredPayload(s, slot, expected)) return INVALID;
    Plan &p = *static_cast<Plan *>(scratch);
    clear(&p, sizeof(p)); p.store = &s; p.source = source; p.token = s.transaction;
    Status status = build(p);
    if (status == READY && !unchanged(p, false)) status = INVALID;
    if (status == FULL && !unchanged(p, true)) status = INVALID;
    if (status == READY && !source.admitted(source.context)) status = SOURCE_BUSY;
    if (status != READY) { StateStore::abort(s); return status; }
    p.phase = 1; p.fingerprint = fingerprint(p); out = &p;
    return READY;
}
StateCodec::Result result(const Plan &p) { return p.encoded; }
unsigned int checksum(const Plan &p) { return p.crc; }
Stats stats(const Plan &p) { return p.statistics; }
bool abort(Plan &p) {
    if (!intact(p) || !TWSTokenMatches(p.store->memory, p.token) || !StateStore::abort(*p.store)) return false;
    p.phase = 2; return true;
}
bool commit(Plan &p, const StateStore::Identity &identity) {
    if (!intact(p) || !identity.generation || identity.kind != StateStore::QUICK ||
        identity.raw != p.encoded.rawBytes || identity.packed != p.encoded.compressedBytes ||
        identity.adler != p.encoded.adler32 || identity.checksum != p.crc || !unchanged(p, true)) return false;
    // Old chunks were covered by the root CRCs; only novel cached bytes need a hash pass.
    for (unsigned int i = 0; i < p.recipeCount; ++i) {
        const TWChunk &c = p.chunks[p.recipes[i].id];
        if (c.offset == kMissing) continue;
        const unsigned char *bytes = address(p, c);
        if (!bytes || ~crcBytes(p, ~0u, bytes, c.size) != c.hash) return false;
    }
    if (!p.source.admitted(p.source.context)) return false;
    // No fallible allocator, ownership callback or cancellation after this point.
    const TWStageMemory *memory = p.store->memory;
    for (unsigned int i = 0; i < p.moveCount; ++i) {
        const unsigned int id = p.moves[i];
        if (p.destinations[id] != p.chunks[id].offset)
            StateSlotPoolCopyForward(TWSAddressUnchecked(memory, p.destinations[id]),
                TWSAddressUnchecked(memory, p.chunks[id].offset), p.chunks[id].size);
    }
    for (unsigned int i = 0; i < p.recipeCount; ++i) {
        const unsigned int id = p.recipes[i].id;
        if (p.chunks[id].offset != kMissing) continue;
        StateCodec::PreparedQuickBlock block;
        p.source.encode(p.source.context, p.recipes[i].block, block);
        unsigned char *destination = TWSAddressUnchecked(memory, p.destinations[id]);
        StateSlotPoolCopyForward(destination, block.header, 8);
        StateSlotPoolCopyForward(destination + 8, block.payload, p.chunks[id].size - 8);
    }
    TWChunkPool *pool = TWChunkDirectory(memory->pool);
    for (unsigned int i = 0; i < TW_CHUNK_DESCRIPTORS; ++i) {
        if (p.chunks[i].refs) { pool->chunks[i] = p.chunks[i]; pool->chunks[i].offset = p.destinations[i]; }
        else clear(&pool->chunks[i], sizeof(TWChunk));
    }
    p.root.metadataTag = identity.tag; pool->slots[p.token.slot] = p.root;
    pool->highWater = p.finalHighWater; pool->target = 3;
    TWStageControl *control = TWSControl(memory);
    control->finalHighWater = p.finalHighWater; control->copiedBytes = p.statistics.movedBytes;
    ++control->generations[p.token.slot]; control->active = 0;
    p.store->roots[p.token.slot] = identity;
    p.store->pending = p.store->sealed = 0; p.store->candidate = {};
    publishCache(p, *pool);
    p.phase = 2;
    return true;
}
}
#endif
