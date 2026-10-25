#include "susamune/state_store.hxx"

namespace StateStore {
namespace {
const unsigned int kMagic = 0x54575431;
bool same(const Identity &a, const Identity &b) {
    return a.generation == b.generation && a.tag == b.tag && a.raw == b.raw &&
        a.packed == b.packed && a.adler == b.adler && a.checksum == b.checksum && a.kind == b.kind;
}
bool separate(const void *a, unsigned int an, const void *b, unsigned int bn) {
    return TWQuickSeparate(a, an, b, bn);
}
bool outside(const Store &s, const void *bytes, unsigned int size) {
    return TWSExternal(s.memory, bytes, size) && separate(bytes, size, &s, sizeof(s)) &&
        separate(bytes, size, s.memory, sizeof(*s.memory)) &&
        separate(bytes, size, s.memory->pool, sizeof(*s.memory->pool)) &&
        (!s.nativeScratch || separate(bytes, size, s.nativeScratch, s.nativeBytes));
}
bool layout(const Store &s) {
    return s.magic == kMagic && s.memory && TWSLayout(s.memory) &&
        TWSExternal(s.memory, &s, sizeof(s)) && s.pending <= 1 && s.sealed <= 1 &&
        s.pending == TWSControl(s.memory)->active && (!s.sealed || s.pending) &&
        s.pin == (TWRControl(s.memory)->active ? TWRControl(s.memory)->sequence : 0);
}
bool identityValid(const Identity &i) {
    return i.generation && i.raw && i.raw <= 0x2000000u && i.packed && i.kind <= DEFLATE;
}
bool bound(const Store &s, unsigned int slot, const Identity &i) {
    const TWChunkPool *pool = TWChunkDirectory(s.memory->pool);
    const TWChunkSlot &root = pool->slots[slot];
    if (!root.count) return !i.raw && !i.packed && !i.adler && !i.checksum && !i.kind && !i.tag;
    return identityValid(i) && root.metadataTag == i.tag && root.packedBytes == i.packed &&
        root.rawBytes == (i.kind == QUICK ? i.raw : i.packed) && TWChunkKind(pool, &root) == i.kind;
}
bool writable(const Store &s) {
    return layout(s) && s.pending && !s.sealed && !s.pin && TWSTokenMatches(s.memory, s.transaction);
}
bool workspaceValid(const Store &s, const void *work, unsigned int size) {
    return outside(s, work, size);
}
bool outputsValid(const Store &s, const StateCodec::WriteSpan *output, unsigned int count) {
    if (!output || !count || count > StateCodec::kMaxSpans ||
        !outside(s, output, count * sizeof(*output))) return false;
    for (unsigned int n = 0; n < count; ++n)
        if (!outside(s, output[n].data, output[n].size)) return false;
    return true;
}
unsigned int borrow(Store &s, unsigned int slot, const Identity &i) {
    const unsigned int generation = slot == 3 ? s.transaction.generation + 1 :
        TWSControl(s.memory)->generations[slot];
    s.pin = TWRBuild(s.memory, slot, generation, i.tag, i.raw, i.packed, i.adler, i.checksum,
                     s.transaction, s.nativeScratch, s.nativeBytes);
    return s.pin;
}
}

bool init(Store &s, const TWStageMemory &memory, unsigned int epoch,
          void *nativeScratch, unsigned int nativeBytes) {
    if (!epoch || !TWSMemoryValid(&memory) || !TWSExternal(&memory, &s, sizeof(s)) ||
        !separate(&s, sizeof(s), &memory, sizeof(memory)) ||
        !separate(&s, sizeof(s), memory.pool, sizeof(*memory.pool)) ||
        (nativeScratch && !separate(&s, sizeof(s), nativeScratch, nativeBytes)) ||
        !TWRTable(&memory, nativeScratch, nativeBytes)) return false;
    // Explicit initialization has no fallback that discards occupied roots.
    const TWChunkPool *old = TWChunkDirectory(memory.pool);
    if (old->magic || TWSControl(&memory)->magic || TWRControl(&memory)->magic) return false;
    if (!TWChunkInit(memory.pool) || !TWSAttach(&memory, epoch)) return false;
    s = {};
    s.memory = &memory; s.nativeScratch = nativeScratch; s.nativeBytes = nativeBytes; s.magic = kMagic;
    return true;
}
bool valid(const Store &s) {
    if (!layout(s) || !TWSValid(s.memory)) return false;
    for (unsigned int i = 0; i < 3; ++i) if (!bound(s, i, s.roots[i])) return false;
    return true;
}
bool begin(Store &s, unsigned int slot, const Identity &expected) {
    if (!valid(s) || s.pending || s.pin || slot >= 3 || !same(expected, s.roots[slot])) return false;
    if (!TWRBegin(s.memory, slot, TWSControl(s.memory)->generations[slot], expected.tag, &s.transaction)) return false;
    s.pending = 1; s.sealed = 0; s.candidate = {};
    for (unsigned int n = 0; n < 3; ++n)
        if (TWSControl(s.memory)->rootChecksums[n] != s.roots[n].checksum) {
            abort(s); return false;
        }
    return true;
}
bool beginDeferredPayload(Store &s, unsigned int slot, const Identity &expected) {
    if (!valid(s) || s.pending || s.pin || slot >= 3 || !same(expected, s.roots[slot]) ||
        !TWRIdle(s.memory)) return false;
    const unsigned int checksums[3] = {s.roots[0].checksum, s.roots[1].checksum, s.roots[2].checksum};
    if (!TWSBeginWithChecksums(s.memory, slot, TWSControl(s.memory)->generations[slot],
                              expected.tag, &s.transaction, checksums)) return false;
    s.pending = 1; s.sealed = 0; s.candidate = {};
    return true;
}
bool abort(Store &s) {
    if (!layout(s) || !s.pending || s.pin || !TWRAbort(s.memory, s.transaction)) return false;
    s.pending = s.sealed = 0; s.candidate = {};
    return true;
}
StateCodec::Result produceQuick(Store &s, void *workspace, unsigned int workspaceBytes,
                               const StateCodec::ReadSpan *source, unsigned int sourceCount,
                               StateCodec::ZeroRange zero) {
    if (!writable(s) || !workspaceValid(s, workspace, workspaceBytes) ||
        TWChunkDirectory(s.memory->pool)->slots[3].count)
        return {StateCodec::INVALID_ARGUMENT, 0, 0, 0};
    return TWQuickProduce(s.memory, s.transaction, workspace, workspaceBytes, source, sourceCount, zero);
}
bool appendQuick(Store &s, const unsigned char *header, unsigned int headerSize,
                 const unsigned char *payload, unsigned int payloadSize) {
    return writable(s) && TWRAppendParts(s.memory, s.transaction, header, headerSize, payload, payloadSize);
}
bool appendOpaque(Store &s, const void *bytes, unsigned int size) {
    if (!writable(s) || !outside(s, bytes, size)) return false;
    unsigned char *destination = TWSReserveOpaque(s.memory, s.transaction, size);
    if (!destination) return false;
    StateSlotPoolCopyForward(destination, static_cast<const unsigned char *>(bytes), size);
    return true;
}
unsigned int reserveOpaque(Store &s, unsigned int size,
                           StateCodec::WriteSpan (&output)[TW_BANK_MAX + 1]) {
    if (!writable(s) || !size || size > 0x2000000u || !outside(s, output, sizeof(output)) ||
        TWChunkDirectory(s.memory->pool)->slots[3].count) return 0;
    for (unsigned int i = 0; i <= TW_BANK_MAX; ++i) output[i] = {nullptr, 0};
    unsigned int count = 0;
    while (size) {
        const unsigned int part = size < TW_CHUNK_RAW_BYTES ? size : TW_CHUNK_RAW_BYTES;
        unsigned char *bytes = TWSReserveOpaque(s.memory, s.transaction, part);
        if (!bytes) return 0;
        if (count && static_cast<unsigned char *>(output[count - 1].data) + output[count - 1].size == bytes)
            output[count - 1].size += part;
        else {
            if (count == TW_BANK_MAX + 1) return 0;
            output[count++] = {bytes, part};
        }
        size -= part;
    }
    return count;
}
unsigned int pendingChecksum(const Store &s) {
    return layout(s) && s.pending && TWSValid(s.memory)
        ? TWSChecksum(s.memory, &TWChunkDirectory(s.memory->pool)->slots[3]) : 0;
}
StateCodec::Result produceDeflate(Store &s, void *workspace, unsigned int workspaceBytes,
    const StateCodec::ReadSpan *source, unsigned int sourceCount, bool compact, StateCodec::ZeroRange zero) {
    if (!writable(s) || !workspaceValid(s, workspace, workspaceBytes))
        return {StateCodec::INVALID_ARGUMENT, 0, 0, 0};
    const StateCodec::Result measured = StateCodec::compress(workspace, workspaceBytes,
        source, sourceCount, nullptr, 0, compact, false, zero);
    if (measured.status != StateCodec::SUCCESS) return measured;
    StateCodec::WriteSpan output[TW_BANK_MAX + 1];
    const unsigned int count = reserveOpaque(s, measured.compressedBytes, output);
    if (!count) return {StateCodec::OUTPUT_FULL, measured.compressedBytes, measured.rawBytes, measured.adler32};
    const StateCodec::Result result = StateCodec::compress(workspace, workspaceBytes,
        source, sourceCount, output, count, compact, false, zero);
    if (result.status != StateCodec::SUCCESS || result.rawBytes != measured.rawBytes ||
        result.adler32 != measured.adler32 || result.compressedBytes != measured.compressedBytes)
        return {StateCodec::CODEC_ERROR, result.compressedBytes, result.rawBytes, result.adler32};
    return result;
}
StateCodec::Result repack(Store &s, unsigned int slot, const Identity &expected,
    void *workspace, unsigned int workspaceBytes, void *packWorkspace,
    unsigned int packWorkspaceBytes, bool compact) {
    StateCodec::Result result = {StateCodec::INVALID_ARGUMENT, 0, 0, 0};
    if (!writable(s) || s.transaction.slot != slot ||
        !workspaceValid(s, workspace, workspaceBytes) || !workspaceValid(s, packWorkspace, packWorkspaceBytes))
        return result;
    unsigned int sequence = pin(s, slot, expected), count;
    if (!sequence) return result;
    const StateCodec::ReadSpan *source = spans(s, sequence, count);
    if (source) result = StateCodec::repack(workspace, workspaceBytes, packWorkspace,
        packWorkspaceBytes, source, count, nullptr, 0, expected.raw, expected.adler, compact);
    if (!unpin(s, sequence)) return {StateCodec::CODEC_ERROR, 0, 0, 0};
    if (result.status != StateCodec::SUCCESS || result.compressedBytes >= expected.packed) return result;
    const StateCodec::Result measured = result;
    StateCodec::WriteSpan output[TW_BANK_MAX + 1];
    const unsigned int outputCount = reserveOpaque(s, measured.compressedBytes, output);
    if (!outputCount) return {StateCodec::OUTPUT_FULL, measured.compressedBytes, measured.rawBytes, measured.adler32};
    sequence = pin(s, slot, expected);
    if (!sequence) return {StateCodec::CORRUPT_STREAM, 0, 0, 0};
    source = spans(s, sequence, count);
    result = {StateCodec::CORRUPT_STREAM, 0, 0, 0};
    if (source) result = StateCodec::repack(workspace, workspaceBytes, packWorkspace,
        packWorkspaceBytes, source, count, output, outputCount, expected.raw, expected.adler, compact);
    const bool unchanged = check(s, sequence, expected);
    if (!unpin(s, sequence) || !unchanged || result.status != StateCodec::SUCCESS ||
        result.rawBytes != measured.rawBytes || result.adler32 != measured.adler32 ||
        result.compressedBytes != measured.compressedBytes)
        return {StateCodec::CODEC_ERROR, result.compressedBytes, result.rawBytes, result.adler32};
    return result;
}
bool seal(Store &s, const Identity &i, void *workspace, unsigned int workspaceBytes) {
    if (!writable(s) || !identityValid(i) || !workspaceValid(s, workspace, workspaceBytes) || !TWSValid(s.memory)) return false;
    const TWChunkPool *pool = TWChunkDirectory(s.memory->pool);
    const TWChunkSlot &root = pool->slots[3];
    if (!root.count || root.packedBytes != i.packed || TWChunkKind(pool, &root) != i.kind ||
        root.rawBytes != (i.kind == QUICK ? i.raw : i.packed) || !borrow(s, 3, i)) return false;
    const TWRootReadControl *reader = TWRControl(s.memory);
    unsigned int prefix = 0, prefixBytes = 0;
    for (unsigned int n = 0; n < reader->spanCount && prefixBytes < 2; ++n) {
        const unsigned char *p = static_cast<const unsigned char *>(reader->table[n].data);
        for (unsigned int b = 0; b < reader->table[n].size && prefixBytes < 2; ++b, ++prefixBytes)
            prefix = (prefix << 8) | p[b];
    }
    const bool framing = i.kind == QUICK || (prefixBytes == 2 && (prefix >> 8 & 15u) == 8 &&
        (prefix >> 12) <= 7 && !(prefix & 32u) && prefix % 31u == 0);
    const bool accepted = framing && TWRCheck(s.memory, s.pin, i.adler, s.nativeScratch, s.nativeBytes) &&
        StateCodec::validate(workspace, workspaceBytes, reader->table, reader->spanCount, i.raw, i.adler) == StateCodec::SUCCESS;
    if (!unpin(s, s.pin) || !accepted) return false;
    s.candidate = i; s.sealed = 1;
    return true;
}
bool commit(Store &s, const Identity &i, bool requireSaving) {
    if (!valid(s) || !s.pending || !s.sealed || s.pin || !same(i, s.candidate)) return false;
    if (requireSaving && (!TWSPreflight(s.memory, s.transaction,
        i.kind == QUICK ? i.raw : i.packed, i.packed, i.checksum) ||
        TWSControl(s.memory)->finalHighWater >= TWSControl(s.memory)->startHighWater)) return false;
    const unsigned int slot = s.transaction.slot;
    if (!TWRCommit(s.memory, s.transaction, i.kind == QUICK ? i.raw : i.packed,
                   i.packed, i.checksum, i.tag)) return false;
    s.roots[slot] = i; s.pending = s.sealed = 0; s.candidate = {};
    return true;
}
bool capacityRefused(const Store &s) {
    if (!valid(s) || !s.pending || !s.sealed || s.pin || !identityValid(s.candidate) || !TWRIdle(s.memory))
        return false;
    const Identity &i = s.candidate;
    return TWSPreflightStatus(s.memory, s.transaction, i.kind == QUICK ? i.raw : i.packed,
        i.packed, i.checksum) == TWS_PREFLIGHT_FULL;
}
bool clear(Store &s, unsigned int slot, const Identity &expected, unsigned int generation) {
    if (!valid(s) || s.pending || s.pin || slot >= 3 || !generation || !same(expected, s.roots[slot]) ||
        !TWRClear(s.memory, slot, TWSControl(s.memory)->generations[slot], expected.tag)) return false;
    s.roots[slot] = {}; s.roots[slot].generation = generation;
    return true;
}
unsigned int pin(Store &s, unsigned int slot, const Identity &expected) {
    if (!valid(s) || s.pin || slot >= 3 || !same(expected, s.roots[slot]) || !identityValid(expected)) return 0;
    return borrow(s, slot, expected);
}
bool check(const Store &s, unsigned int sequence, const Identity &expected) {
    if (!layout(s) || !sequence || sequence != s.pin || !identityValid(expected)) return false;
    const TWRootReadControl *reader = TWRControl(s.memory);
    return reader->root < 3 && same(expected, s.roots[reader->root]) &&
        TWRCheck(s.memory, sequence, expected.adler, s.nativeScratch, s.nativeBytes);
}
bool unpin(Store &s, unsigned int sequence) {
    if (!layout(s) || !sequence || s.pin != sequence || !TWRRelease(s.memory, sequence)) return false;
    s.pin = 0; return true;
}
const StateCodec::ReadSpan *spans(const Store &s, unsigned int sequence, unsigned int &count) {
    count = 0;
    if (!layout(s) || !sequence || sequence != s.pin) return nullptr;
    const TWRootReadControl *reader = TWRControl(s.memory);
    if (reader->root >= 3 || !check(s, sequence, s.roots[reader->root])) return nullptr;
    count = reader->spanCount; return reader->table;
}
StateCodec::Status validateRestore(const Store &s, unsigned int sequence,
    const Identity &i, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount) {
    if (!check(s, sequence, i) || !workspaceValid(s, workspace, workspaceBytes) ||
        !outputsValid(s, output, outputCount)) return StateCodec::INVALID_ARGUMENT;
    const TWRootReadControl *r = TWRControl(s.memory);
    return StateCodec::validateRestore(workspace, workspaceBytes, r->table, r->spanCount,
                                      output, outputCount, i.raw, i.adler);
}
StateCodec::Status restore(const Store &s, unsigned int sequence,
    const Identity &i, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy, void *context, StateCodec::DirectBytes direct) {
    if (!check(s, sequence, i) || !workspaceValid(s, workspace, workspaceBytes) ||
        !outputsValid(s, output, outputCount)) return StateCodec::INVALID_ARGUMENT;
    const TWRootReadControl *r = TWRControl(s.memory);
    return StateCodec::decompressVerified(workspace, workspaceBytes, r->table, r->spanCount,
                                          output, outputCount, i.raw, i.adler, copy, context, direct);
}
StateCodec::Status restoreSlot(Store &s, unsigned int slot,
    const Identity &i, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy, void *context, StateCodec::DirectBytes direct) {
    if (!layout(s) || s.pending || !workspaceValid(s, workspace, workspaceBytes) ||
        !outputsValid(s, output, outputCount)) return StateCodec::INVALID_ARGUMENT;
    const unsigned int sequence = pin(s, slot, i);
    if (!sequence) return StateCodec::CORRUPT_STREAM;
    // Pin validates the complete packed CRC and builds this exact span table.
    // No caller or callback runs before the decoder receives those same bytes.
    const TWRootReadControl *r = TWRControl(s.memory);
    const StateCodec::Status result = StateCodec::decompressVerified(workspace, workspaceBytes,
        r->table, r->spanCount, output, outputCount, i.raw, i.adler, copy, context, direct);
    return unpin(s, sequence) ? result : StateCodec::COMMIT_FAILED;
}
StateCodec::Status restoreSlotExperimental(Store &s, unsigned int slot,
    const Identity &i, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy, void *context, StateCodec::DirectBytes direct) {
    if (i.kind != QUICK)
        return restoreSlot(s, slot, i, workspace, workspaceBytes, output, outputCount, copy, context, direct);
    if (!valid(s) || s.pending || s.pin || slot >= 3 || !same(i, s.roots[slot]) ||
        !identityValid(i) || !workspaceValid(s, workspace, workspaceBytes) ||
        !outputsValid(s, output, outputCount)) return StateCodec::INVALID_ARGUMENT;
    s.pin = TWRBuild(s.memory, slot, TWSControl(s.memory)->generations[slot],
        i.tag, i.raw, i.packed, i.adler, i.checksum, s.transaction,
        s.nativeScratch, s.nativeBytes, false);
    if (!s.pin) return StateCodec::CORRUPT_STREAM;
    const unsigned int sequence = s.pin;
    const TWRootReadControl *r = TWRControl(s.memory);
    const StateCodec::Status result = StateCodec::decompressExperimental(workspace, workspaceBytes,
        r->table, r->spanCount, output, outputCount, i.raw, i.adler, copy, context, direct);
    return unpin(s, sequence) ? result : StateCodec::COMMIT_FAILED;
}
bool exportPlan(const Store &s, unsigned int sequence, const Identity &i,
                unsigned int metadataCrc, SusamuneStateExportPlan &plan) {
    if (!check(s, sequence, i) || s.pending ||
        !separate(&plan, sizeof(plan), &i, sizeof(i)) ||
        !TWBankExternalBuffer(s.memory->pool, &plan, sizeof(plan)) ||
        !separate(&plan, sizeof(plan), &s, sizeof(s)) ||
        !separate(&plan, sizeof(plan), s.memory, sizeof(*s.memory)) ||
        !separate(&plan, sizeof(plan), s.memory->pool, sizeof(*s.memory->pool)) ||
        (s.nativeScratch && !separate(&plan, sizeof(plan), s.nativeScratch, s.nativeBytes))) return false;
    const TWChunkPool *pool = TWChunkDirectory(s.memory->pool);
    const TWChunkSlot &root = pool->slots[TWRControl(s.memory)->root];
    plan = {};
    plan.magic = SUSAMUNE_STATE_EXPORT_PLAN; plan.version = SUSAMUNE_STATE_EXPORT_PLAN_VERSION;
    plan.count = root.count; plan.rawBytes = i.raw; plan.packedBytes = i.packed; plan.metadataCrc = metadataCrc;
    plan.kind = i.kind;
    for (unsigned int n = 0; n < root.count; ++n) {
        const TWChunk &chunk = pool->chunks[root.ids[n] - 1];
        plan.blocks[n] = {chunk.offset, chunk.size};
    }
    plan.checksum = SusamuneStateExportPlanCrc(&plan);
    return true;
}
}
