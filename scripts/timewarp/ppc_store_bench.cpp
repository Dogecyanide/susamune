#define bench poolBench
#include "ppc_pool_bench.cpp"
#undef bench
#include "../../src/state_store.cpp"
#include "../../src/state_import.cpp"
#if TIMEWARP_QUICK_REPLAY
#include "../../src/state_quick_replay.cpp"
#endif

static StateStore::Store Store;
static StateStore::Identity Candidate;
static StateImport::Cursor Cursor;
static unsigned Generation;
#if TIMEWARP_QUICK_REPLAY
static const unsigned ReplayScratch = 0x71500000, ReplayScratchBytes = 0x4e000;
static StateCodec::ReadSpan ReplayInput;
static StateCodec::PreparedQuickSource ReplaySource;
static StateQuickReplay::Plan *ReplayPlan;
static unsigned ReplayCalls;
static void replayEncode(void *, unsigned index, StateCodec::PreparedQuickBlock &block) {
    ++ReplayCalls;
#if SUSAMUNE_QUICK_CHECKSUM_REUSE
    StateCodec::encodePreparedQuickBlockDeferred((void *)Work, ReplaySource, index, block);
#else
    StateCodec::encodePreparedQuickBlock((void *)Work, ReplaySource, index, block);
#endif
}
#if SUSAMUNE_QUICK_CHECKSUM_REUSE
static unsigned replayChecksum(void *, unsigned index, const StateCodec::PreparedQuickBlock &block) {
    return StateCodec::checksumPreparedQuickBlock((void *)Work, ReplaySource, index, block);
}
#endif
static bool replayAdmitted(void *) { return true; }
static void replayStats() {
    const StateQuickReplay::Stats stats = StateQuickReplay::stats(*ReplayPlan);
    Box[24] = stats.cachedBytes; Box[25] = stats.spilledBlocks;
    Box[26] = stats.replayRawBytes; Box[27] = stats.movedBytes;
    Box[28] = StateQuickReplay::workspaceSize(); Box[29] = ReplayCalls;
}
static bool replayGuards() {
    return *(volatile unsigned *)(ReplayScratch - 4) == Canary &&
        *(volatile unsigned *)(ReplayScratch + StateQuickReplay::workspaceSize()) == Canary &&
        *(volatile unsigned *)(ReplayScratch + ReplayScratchBytes) == Canary;
}
#endif

static bool resetStore() {
    Store = {}; Candidate = {}; Cursor = {}; Generation = 0;
    memset(Memory.banks[0], 0, TW_CHUNK_DIRECTORY_BYTES);
    setGuards();
#if TIMEWARP_QUICK_REPLAY
    ReplayPlan = nullptr; ReplaySource = {}; ReplayInput = {}; ReplayCalls = 0;
    *(volatile unsigned *)(ReplayScratch - 4) = Canary;
    *(volatile unsigned *)(ReplayScratch + StateQuickReplay::workspaceSize()) = Canary;
    *(volatile unsigned *)(ReplayScratch + ReplayScratchBytes) = Canary;
#endif
    return StateStore::init(Store, Stage, 73);
}
static unsigned storeRun(unsigned command, unsigned slot, unsigned size, unsigned tag) {
    if (command == 1) return resetStore() ? 0 : 90;
    if (slot >= 3) return 91;
    if (command == 2) return StateStore::begin(Store, slot, Store.roots[slot]) ? 0 : 92;
    if (command == 3) {
        if (!size || size > InputLimit) return 93;
        StateCodec::ReadSpan source = {(void *)Input, size};
        const StateCodec::Result r = tag == 2 ? StateStore::produceDeflate(Store, (void *)Work,
            0x4e000, &source, 1, false) : StateStore::produceQuick(Store, (void *)Work, 0x4e000, &source, 1);
        Candidate = {++Generation, 100 + Generation, r.rawBytes, r.compressedBytes, r.adler32,
            r.status == StateCodec::SUCCESS ? StateStore::pendingChecksum(Store) : 0,
            tag == 2 ? StateStore::DEFLATE : StateStore::QUICK};
        Box[5] = r.compressedBytes; Box[6] = r.rawBytes; Box[7] = r.adler32; Box[8] = Candidate.checksum;
        return r.status;
    }
    if (command == 4) {
        if (!StateStore::seal(Store, Candidate, (void *)Work, 0x4e000)) return 94;
        return StateStore::commit(Store, Candidate) ? 0 : 95;
    }
    if (command == 5) return StateStore::abort(Store) ? 0 : 96;
    if (command == 6 || command == 7) {
        const StateStore::Identity identity = Store.roots[slot];
        const unsigned pin = StateStore::pin(Store, slot, identity);
        if (!pin) return 97;
        unsigned status = 0;
        if (command == 6) {
            unsigned count = 0, offset = 0, left = OutputSize;
            const StateCodec::ReadSpan *source = StateStore::spans(Store, pin, count);
            unsigned char *next = (unsigned char *)Output;
            if (!source || size >= identity.packed) status = 98;
            for (unsigned n = 0; !status && n < count && left; ++n) {
                const unsigned length = source[n].size;
                if (offset + length > size) {
                    const unsigned skip = size > offset ? size - offset : 0;
                    const unsigned copied = length - skip < left ? length - skip : left;
                    memcpy(next, (const unsigned char *)source[n].data + skip, copied);
                    next += copied; left -= copied;
                }
                offset += length;
            }
            Box[5] = next - (unsigned char *)Output; Box[6] = identity.packed;
        } else {
            if (!identity.raw || identity.raw > InputLimit) status = 99;
            else {
                StateCodec::WriteSpan output = {(void *)Input, identity.raw};
                memset((void *)Input, 0xa7, identity.raw);
                ProtectFirst = tag ? Input + 0x4000d : 0; ProtectLast = tag ? ProtectFirst + 31 : 0;
                status = StateStore::restore(Store, pin, identity, (void *)Work, 0x4e000,
                    &output, 1, copy, nullptr, direct);
            }
        }
        if (!StateStore::unpin(Store, pin)) return 100;
        return status;
    }
    if (command == 8) {
        Candidate = {++Generation, 100 + Generation, Box[24], Box[25], Box[26], Box[27], Box[28]};
        Cursor = {};
        return StateStore::begin(Store, slot, Store.roots[slot]) &&
            StateImport::begin(Store, Cursor, Candidate.packed) ? 0 : 101;
    }
    if (command == 9) {
        if (!size || size > 0x4e000 || size > OutputSize) return 102;
        const StateImport::Status status = StateImport::append(Store, Cursor, (void *)Output, size);
        Box[29] = Cursor.offset; Box[30] = status;
        memset((void *)Output, 0xdb, size);
        return status == StateImport::MORE || status == StateImport::COMPLETE ? 0 : 103;
    }
    if (command == 10) return StateStore::clear(Store, slot, Store.roots[slot], ++Generation) ? 0 : 104;
#if TIMEWARP_QUICK_REPLAY
    if (command == 11) {
        if (!size || size > InputLimit) return 106;
        ReplayInput = {(void *)Input, size}; ReplayCalls = 0;
        StateCodec::WriteSpan destinations[TW_BANK_MAX + 2]; unsigned count = 0;
        for (unsigned i = 0; i < Memory.count; ++i) destinations[count++] = {Memory.banks[i], Memory.sizes[i]};
        destinations[count++] = {Stage.staging, Stage.size};
        destinations[count++] = {(void *)ReplayScratch, ReplayScratchBytes};
        if (StateCodec::prepareQuickSource((void *)Work, 0x4e000, &ReplayInput, 1,
            destinations, count, ReplaySource) != StateCodec::SUCCESS) return 107;
        const StateQuickReplay::Source source = {nullptr, size, replayEncode, replayAdmitted
#if SUSAMUNE_QUICK_CHECKSUM_REUSE
            , replayChecksum
#endif
        };
        const StateQuickReplay::Status status = StateQuickReplay::prepare(Store, slot, Store.roots[slot],
            source, (void *)ReplayScratch, ReplayScratchBytes, ReplayPlan);
        if (status != StateQuickReplay::READY) return 110 + status;
        const StateCodec::Result result = StateQuickReplay::result(*ReplayPlan);
        Candidate = {++Generation, 100 + Generation, result.rawBytes, result.compressedBytes, result.adler32,
            StateQuickReplay::checksum(*ReplayPlan), StateStore::QUICK};
        Box[5] = result.compressedBytes; Box[6] = result.rawBytes;
        Box[7] = result.adler32; Box[8] = Candidate.checksum; replayStats();
        return 0;
    }
    if (command == 12) {
        if (!ReplayPlan || !StateQuickReplay::commit(*ReplayPlan, Candidate)) return 114;
        replayStats(); return 0;
    }
#endif
    return 105;
}
extern "C" void bench() {
    for (unsigned n = 0; n < 32; ++n) Box[n] = 0;
    Box[4] = resetStore() ? 0 : 90; Box[11] = 3; Box[0] = 0x54575042;
    unsigned seen = 0;
    for (;;) {
        const unsigned sequence = Box[1]; if (sequence == seen) continue; seen = sequence;
        Box[4] = storeRun(Box[2], Box[12], Box[13], Box[14]);
        const TWChunkPool *pool = TWChunkDirectory(&Memory);
        Box[9] = guards();
#if TIMEWARP_QUICK_REPLAY
        Box[9] = Box[9] && replayGuards();
#endif
        Box[10] = pool->highWater; Box[15] = pool->slots[3].count;
        Box[16] = TWSControl(&Stage)->stagePeak; Box[17] = TWSControl(&Stage)->copiedBytes;
        for (unsigned n = 0; n < 3; ++n) Box[18 + n] = Store.roots[n].generation;
        unsigned live = 0, aligned = 0;
        for (unsigned n = 0; n < TW_CHUNK_DESCRIPTORS; ++n) {
            const TWChunk *chunk = &pool->chunks[n];
            if (chunk->refs) { ++live; aligned += TWChunkAlign(chunk->size); }
        }
        Box[21] = live; Box[22] = aligned;
        asm volatile("sync" ::: "memory"); Box[3] = sequence;
    }
}
