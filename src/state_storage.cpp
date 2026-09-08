#include "susamune/state_storage.hxx"
#include "susamune/state_pool_runtime.hxx"
#include <Dolphin/OS.h>
#include <Dolphin/mem.h>

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace StateStorage {
namespace {
#if IS_EMULATOR
const u32 kMailbox = SUSAMUNE_DOLPHIN_STATE_STORAGE_PPC_BASE;
const u32 kStaging = SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE;
#else
const u32 kMailbox = SUSAMUNE_STATE_STORAGE_PPC_BASE;
const u32 kStaging = SUSAMUNE_STATE_STAGING_PPC_BASE;
#endif
SusamuneStateStorageMailbox *const sMailbox = reinterpret_cast<SusamuneStateStorageMailbox *>(kMailbox);
u32 sSession, sSequence, sConfig, sImportSize, sImportOffset;
SusamuneStateRequest sPending;
bool sAvailable, sResultReady, sCatalogReady;
Result sResult;

void syncPool(u32 offset, u32 size, bool finished) {
    const StatePoolMemory memory = statePoolMemory();
    while (size) {
        StatePoolMemorySpan span;
        if (!StatePoolMemorySpanAt(&memory, offset, size, &span)) __builtin_trap();
        if (finished) DCInvalidateRange(span.data, span.size);
        else DCFlushRange(span.data, span.size);
        offset += span.size;
        size -= span.size;
    }
}

void syncImport(bool finished) {
    if (!sImportSize) return;
    const u32 first = sImportSize < SUSAMUNE_STATE_STAGING_SIZE ?
        sImportSize : SUSAMUNE_STATE_STAGING_SIZE;
    void *a = reinterpret_cast<void *>(kStaging);
    if (finished) {
        DCInvalidateRange(a, first);
    } else {
        DCFlushRange(a, first);
    }
    if (sImportSize > first) syncPool(sImportOffset, sImportSize - first, finished);
}

bool submit(u32 command, u32 id, u32 offset, u32 size, u32 crc) {
    if (!sAvailable || sPending.command || sResultReady) return false;
    memset(&sPending, 0, sizeof(sPending));
    if (++sSequence == 0) ++sSequence;
    sPending.seq = sSequence;
    sPending.command = command;
    sPending.id = id;
    sPending.session = sSession;
    sPending.poolOffset = offset;
    sPending.packedSize = size;
    sPending.expectedHeaderCrc = crc;
    if (command == SUSAMUNE_STATE_CMD_IMPORT) {
        sImportSize = size;
        sImportOffset = offset;
        syncImport(false);
    }
    memcpy(&sMailbox->request, &sPending, sizeof(sPending));
    DCFlushRange(&sMailbox->request, sizeof(sPending));
    return true;
}
}

void init() {
    sAvailable = sResultReady = sCatalogReady = false;
    memset(&sPending, 0, sizeof(sPending));
    sConfig = sImportSize = sImportOffset = 0;
#if !IS_EMULATOR
    DCInvalidateRange(&sMailbox->response, sizeof(sMailbox->response));
    const SusamuneStateResponse &r = sMailbox->response;
    if (r.magic != SUSAMUNE_STATE_STORAGE_MAGIC || r.version != SUSAMUNE_STATE_STORAGE_VERSION ||
        !r.available || !r.configId) return;
    sAvailable = true;
    sConfig = r.configId;
    const u64 now = OSGetTime();
    sSession = static_cast<u32>(now ^ (now >> 32));
    if (!sSession) sSession = 1;
    DCInvalidateRange(&sMailbox->request, sizeof(sMailbox->request));
    sSequence = sMailbox->request.seq;
    // A reinjected mod must retire any preceding client's worker before reuse.
    if (sSequence != r.ackSeq) submit(SUSAMUNE_STATE_CMD_CANCEL, 0, 0, 0, 0);
#endif
}

void update() {
    if (!sPending.command) return;
    DCInvalidateRange(&sMailbox->response, sizeof(sMailbox->response));
    if (sMailbox->response.ackSeq != sPending.seq) return;
    DCInvalidateRange(&sMailbox->receipt, sizeof(sMailbox->receipt));
    const SusamuneStateReceipt &r = sMailbox->receipt;
    if (r.seq != sPending.seq || r.session != sPending.session ||
        r.command != sPending.command || r.id != sPending.id) return;
    syncImport(true);
    sImportSize = 0;
    memset(&sResult, 0, sizeof(sResult));
    sResult.command = sPending.command;
    sResult.status = sMailbox->response.status;
    sResult.id = sMailbox->response.resultId;
    if (sResult.status == SUSAMUNE_STATE_OK &&
        (sPending.command == SUSAMUNE_STATE_CMD_IMPORT || sPending.command == SUSAMUNE_STATE_CMD_EXPORT)) {
        DCInvalidateRange(&sMailbox->header, sizeof(sMailbox->header));
        const SusamuneStateArchiveHeader &h = sMailbox->header;
        if (!SusamuneStateHeaderValid(&h) || h.headerCrc != r.headerCrc ||
            h.metadataSize != r.metadataSize || h.packedSize != r.packedSize || h.configId != sConfig ||
            h.packedSize != sPending.packedSize ||
            (sPending.command == SUSAMUNE_STATE_CMD_IMPORT && h.headerCrc != sPending.expectedHeaderCrc)) {
            sResult.status = SUSAMUNE_STATE_BAD_FILE;
        } else {
            DCInvalidateRange(sMailbox->metadata, h.metadataSize);
            if (SusamuneStateCrc(sMailbox->metadata, h.metadataSize) != h.metadataCrc)
                sResult.status = SUSAMUNE_STATE_BAD_FILE;
            else {
                sResult.header = h;
                sResult.metadata = sMailbox->metadata;
            }
        }
    } else if (sPending.command == SUSAMUNE_STATE_CMD_CATALOG) {
        sCatalogReady = false;
        if (sResult.status == SUSAMUNE_STATE_OK) {
            DCInvalidateRange(&sMailbox->catalog, sizeof(sMailbox->catalog));
            const SusamuneStateCatalog &c = sMailbox->catalog;
            bool valid = c.count <= SUSAMUNE_STATE_CATALOG_COUNT && c.afterId == sPending.id && c.more <= 1;
            u32 prior = c.afterId;
            for (u32 i = 0; valid && i < c.count; ++i) {
                const SusamuneStateCatalogEntry &e = c.entries[i];
                valid = e.id > prior && e.id <= SUSAMUNE_STATE_MAX_ARCHIVE_ID &&
                    e.packedSize && e.packedSize <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE && e.name[31] == 0;
                prior = e.id;
            }
            valid = valid && c.nextId == prior;
            sCatalogReady = valid;
            if (!valid) sResult.status = SUSAMUNE_STATE_BAD_FILE;
        }
    }
    memset(&sPending, 0, sizeof(sPending));
    sResultReady = true;
}
bool available() { return sAvailable; }
bool busy() { return sPending.command != 0; }
u32 configId() { return sConfig; }

bool startExport(const SusamuneStateArchiveHeader &source, const void *metadata, u32 offset) {
    const StatePoolMemory memory = statePoolMemory();
    if (!sAvailable || busy() || sResultReady || !metadata || !SusamuneStatePoolRange(offset, source.packedSize) ||
        !StatePoolMemoryRangeValid(&memory, offset, source.packedSize) ||
        !source.metadataSize || source.metadataSize > SUSAMUNE_STATE_METADATA_SIZE) return false;
    SusamuneStateArchiveHeader h = source;
    h.magic = SUSAMUNE_STATE_ARCHIVE_MAGIC;
    h.version = SUSAMUNE_STATE_ARCHIVE_VERSION;
    h.headerSize = sizeof(h);
    h.configId = sConfig;
    h.metadataCrc = SusamuneStateCrc(metadata, h.metadataSize);
    h.payloadCrc = 0;
    h.headerCrc = SusamuneStateHeaderCrc(&h);
    if (!SusamuneStateHeaderValid(&h)) return false;
    memcpy(&sMailbox->header, &h, sizeof(h));
    memcpy(sMailbox->metadata, metadata, h.metadataSize);
    DCFlushRange(&sMailbox->header, sizeof(h));
    DCFlushRange(sMailbox->metadata, h.metadataSize);
    syncPool(offset, h.packedSize, false);
    return submit(SUSAMUNE_STATE_CMD_EXPORT, 0, offset, h.packedSize, 0);
}
bool startImport(u32 id, u32 crc, u32 size, u32 offset) {
    const StatePoolMemory memory = statePoolMemory();
    const u32 tail = size > SUSAMUNE_STATE_STAGING_SIZE ? size - SUSAMUNE_STATE_STAGING_SIZE : 0;
    if (!id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID || !SusamuneStateImportRange(offset, size)) return false;
    if (size > StatePoolMemoryCapacity(&memory) || !StatePoolMemoryRangeValid(&memory, offset, tail)) return false;
    return submit(SUSAMUNE_STATE_CMD_IMPORT, id, offset, size, crc);
}
bool refresh(u32 afterId) {
    if (afterId > SUSAMUNE_STATE_MAX_ARCHIVE_ID) return false;
    if (!submit(SUSAMUNE_STATE_CMD_CATALOG, afterId, 0, 0, 0)) return false;
    sCatalogReady = false;
    return true;
}
bool cancel() {
    if (!busy() || sPending.command == SUSAMUNE_STATE_CMD_CANCEL) return false;
    // Keep the imported range owned until cancellation's own receipt arrives.
    memset(&sPending, 0, sizeof(sPending));
    return submit(SUSAMUNE_STATE_CMD_CANCEL, 0, 0, 0, 0);
}
bool takeResult(Result &out) {
    if (!sResultReady) return false;
    out = sResult;
    sResultReady = false;
    return true;
}
bool catalogReady() { return sCatalogReady; }
const SusamuneStateCatalog &catalog() { return sMailbox->catalog; }
}
