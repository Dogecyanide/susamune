#include "susamune/state_storage.hxx"
#include "susamune/state_pool_runtime.hxx"
#include "susamune/state_export_plan.h"
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
u32 sSession, sSequence, sConfig, sImportSize, sImportOffset, sProjectReplyCrc;
u32 sImportStageOffset;
SusamuneStateRequest sPending;
bool sAvailable, sResultReady, sCatalogReady, sTapeTransfer;
bool sResultTaken, sSharedBackend, sTransferFailed, sKeepOwner;
bool sCancelRequested, sCancelPublished, sAbandoned;
u32 sResultGeneration;
enum TransferPhase { TRANSFER_NONE, TRANSFER_LOCAL, TRANSFER_SUBMIT,
    TRANSFER_REMOTE, TRANSFER_BORROWED, TRANSFER_CONSUME, TRANSFER_RELEASE };
u8 sTransferPhase;
TransferLease::Token sTransferToken;
TransferLease::Borrow sTransferBorrow;
Result sResult;
StatePoolMemory sMemory;

bool headerValid(const SusamuneStateArchiveHeader *header) {
    return SusamuneStateHeaderValidCapacity(header, archiveCapacity());
}
bool projectValid(const SusamuneTasManifest *project) {
    return SusamuneTasManifestValidCapacity(project, archiveCapacity());
}

bool transferSucceeded(bool success) {
    if (!success && TransferLease::mode() == TransferLease::FAILED) sTransferFailed = true;
    return success;
}

void finishTransfer() {
    if (sTransferPhase == TRANSFER_CONSUME) {
        if (!transferSucceeded(TransferLease::consumed(sTransferToken, sTransferBorrow))) return;
        sTransferPhase = sKeepOwner ? TRANSFER_LOCAL : TRANSFER_RELEASE;
    }
    if (sTransferPhase == TRANSFER_RELEASE &&
        transferSucceeded(TransferLease::release(sTransferToken))) {
        sTransferToken = {}; sTransferBorrow = {};
        sTransferPhase = TRANSFER_NONE;
    }
}

void readBackend() {
#if !IS_EMULATOR
    DCInvalidateRange(&sMailbox->response, sizeof(sMailbox->response));
    const SusamuneStateResponse &r = sMailbox->response;
    sAvailable = r.magic == SUSAMUNE_STATE_STORAGE_MAGIC &&
        r.version == SUSAMUNE_STATE_STORAGE_VERSION && r.available && r.configId &&
        sMemory.sizes[0] == SUSAMUNE_STATE_POOL_SIZE;
    if (sAvailable) sConfig = r.configId;
#endif
}

bool transferReady() {
#if !IS_EMULATOR
    TransferLease::poll();
    const TransferLease::Mode mode = TransferLease::init();
    if (mode == TransferLease::FAILED ||
        (sSharedBackend && mode != TransferLease::SHARED)) sTransferFailed = true;
    if (sTransferFailed) return false;
    if (mode == TransferLease::SHARED && !sSharedBackend) {
        if (!quiet()) { sTransferFailed = true; return false; }
        sSharedBackend = true;
        if (!statePoolSharedMemory(sMemory)) { sTransferFailed = true; return false; }
        readBackend();
        sCatalogReady = false;
        DCInvalidateRange(&sMailbox->request, sizeof(sMailbox->request));
        sSequence = sMailbox->request.seq;
    }
    return mode == TransferLease::SHARED || TransferLease::legacyAllowed();
#else
    return true;
#endif
}

bool requestIdle() {
    if (!transferReady()) return false;
    finishTransfer();
    return sAvailable && !sPending.command && !sResultReady && !sResultTaken &&
        !sTransferFailed && (sTransferPhase == TRANSFER_NONE || sTransferPhase == TRANSFER_LOCAL);
}

bool claimTransfer() {
    if (!requestIdle()) return false;
    if (!sSharedBackend || sTransferPhase == TRANSFER_LOCAL) return true;
    TransferLease::Token token;
    if (!transferSucceeded(TransferLease::claim(TransferLease::STATE, token))) return false;
    sTransferToken = token;
    sTransferPhase = TRANSFER_LOCAL;
    return true;
}

void submitTransfer() {
    if (sTransferPhase == TRANSFER_SUBMIT && transferSucceeded(TransferLease::submit(
            sTransferToken, sPending.seq, sPending.session, sPending.command)))
        sTransferPhase = TRANSFER_REMOTE;
    if (sTransferPhase == TRANSFER_REMOTE && sCancelRequested && !sCancelPublished)
        sCancelPublished = transferSucceeded(TransferLease::cancel(sTransferToken));
}

void syncPool(u32 offset, u32 size, bool finished) {
    const StatePoolMemory &memory = sMemory;
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
    const u32 capacity = stagingSize() - sImportStageOffset;
    const u32 first = sImportSize < capacity ? sImportSize : capacity;
    void *a = static_cast<u8 *>(stagingBase()) + sImportStageOffset;
    if (finished) {
        DCInvalidateRange(a, first);
    } else {
        DCFlushRange(a, first);
    }
    if (sImportSize > first) syncPool(sImportOffset, sImportSize - first, finished);
}

bool submit(u32 command, u32 id, u32 offset, u32 size, u32 crc, u32 windowSize = 0,
            const SusamuneTasRequest *project = nullptr) {
    if (project && (!SusamuneTasRequestValid(project) || !project->projectId ||
        project->componentId != id)) return false;
    if (!claimTransfer()) return false;
    memset(&sPending, 0, sizeof(sPending));
    if (++sSequence == 0) ++sSequence;
    sPending.seq = sSequence;
    sPending.command = command;
    sPending.id = id;
    sPending.session = sSession;
    sPending.poolOffset = offset;
    sPending.packedSize = size;
    sPending.expectedHeaderCrc = crc;
    sPending.reserved = windowSize;
    sCancelRequested = sCancelPublished = sAbandoned = false;
    memset(&sMailbox->tasRequest, 0, sizeof(sMailbox->tasRequest));
    if (project) sMailbox->tasRequest = *project;
    sTapeTransfer = project && project->role == SUSAMUNE_TAS_TAPE_ROLE;
    DCFlushRange(&sMailbox->tasRequest, sizeof(sMailbox->tasRequest));
    if (command == SUSAMUNE_STATE_CMD_IMPORT || command == SUSAMUNE_STATE_CMD_READ_WINDOW ||
        command == SUSAMUNE_STATE_CMD_TAS_COMMIT) {
        // Project verification borrows the first chunk as ARM-only scratch.
        const bool tail = command == SUSAMUNE_STATE_CMD_READ_WINDOW &&
            (windowSize & SUSAMUNE_STATE_WINDOW_TAIL);
        sImportStageOffset = tail ? SUSAMUNE_TRANSFER_IMPORT_WINDOW_OFFSET : 0;
        sImportSize = command == SUSAMUNE_STATE_CMD_TAS_COMMIT ? SUSAMUNE_STATE_CHUNK_SIZE :
            command == SUSAMUNE_STATE_CMD_READ_WINDOW ? windowSize & SUSAMUNE_STATE_WINDOW_SIZE_MASK : size;
        sImportOffset = offset;
        syncImport(false);
    }
    memcpy(&sMailbox->request, &sPending, sizeof(sPending));
    DCFlushRange(&sMailbox->request, sizeof(sPending));
    if (sSharedBackend) { sTransferPhase = TRANSFER_SUBMIT; submitTransfer(); }
    return true;
}
}

void init() {
    if (!quiet()) return;
    sAvailable = sResultReady = sCatalogReady = false;
    memset(&sPending, 0, sizeof(sPending));
    sConfig = sImportSize = sImportOffset = sImportStageOffset = sProjectReplyCrc = 0;
    if (!sSharedBackend) sMemory = statePoolMemory();
#if !IS_EMULATOR
    if (!transferReady()) return;
    readBackend();
    if (!sAvailable) return;
    const u64 now = OSGetTime();
    sSession = static_cast<u32>(now ^ (now >> 32));
    if (!sSession) sSession = 1;
    DCInvalidateRange(&sMailbox->request, sizeof(sMailbox->request));
    sSequence = sMailbox->request.seq;
    // A reinjected mod must retire any preceding client's worker before reuse.
    if (!sSharedBackend && sSequence != sMailbox->response.ackSeq)
        submit(SUSAMUNE_STATE_CMD_CANCEL, 0, 0, 0, 0);
#endif
}

void update() {
    if (!transferReady()) return;
    finishTransfer();
    if (!sPending.command) return;
    submitTransfer();
    DCInvalidateRange(&sMailbox->response, sizeof(sMailbox->response));
    if (sMailbox->response.ackSeq != sPending.seq) return;
    DCInvalidateRange(&sMailbox->receipt, sizeof(sMailbox->receipt));
    const SusamuneStateReceipt &r = sMailbox->receipt;
    if (r.seq != sPending.seq || r.session != sPending.session ||
        r.command != sPending.command || r.id != sPending.id) return;
    if (sSharedBackend) {
        if (sTransferPhase != TRANSFER_REMOTE ||
            !transferSucceeded(TransferLease::take(sTransferToken, sTransferBorrow))) return;
        sTransferPhase = TRANSFER_BORROWED;
    }
    if (sResultGeneration == 0xffffffffu) { sTransferFailed = true; return; }
    syncImport(true);
    sImportSize = 0;
    memset(&sResult, 0, sizeof(sResult));
    sResult.command = sPending.command;
    sResult.status = sMailbox->response.status;
    sResult.id = sMailbox->response.resultId;
    sResult.token.generation = ++sResultGeneration;
    const bool window = sPending.command == SUSAMUNE_STATE_CMD_READ_WINDOW;
    const bool payload = window || sPending.command == SUSAMUNE_STATE_CMD_IMPORT || sPending.command == SUSAMUNE_STATE_CMD_EXPORT;
    if (sResult.status == SUSAMUNE_STATE_OK &&
        (payload || sPending.command == SUSAMUNE_STATE_CMD_RENAME || sPending.command == SUSAMUNE_STATE_CMD_DELETE)) {
        DCInvalidateRange(&sMailbox->header, sizeof(sMailbox->header));
        DCInvalidateRange(sMailbox->resultName, sizeof(sMailbox->resultName));
        const SusamuneStateArchiveHeader &h = sMailbox->header;
        if (!headerValid(&h) || (sTapeTransfer && !SusamuneTasTapeHeaderValid(&h)) || h.headerCrc != r.headerCrc ||
            h.metadataSize != r.metadataSize || h.packedSize != r.packedSize ||
            !SusamuneStateNameValid(sMailbox->resultName) ||
            SusamuneStateCrc(sMailbox->resultName, sizeof(sMailbox->resultName)) != r.reserved ||
            (sPending.command == SUSAMUNE_STATE_CMD_EXPORT &&
             (!sResult.id || sResult.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID)) ||
            (payload && (h.configId != sConfig || h.packedSize != sPending.packedSize)) ||
            (sPending.command != SUSAMUNE_STATE_CMD_EXPORT &&
             (h.headerCrc != sPending.expectedHeaderCrc || sResult.id != sPending.id))) {
            sResult.status = SUSAMUNE_STATE_BAD_FILE;
        } else {
            if (payload) {
                DCInvalidateRange(sMailbox->metadata, h.metadataSize);
                if (SusamuneStateCrc(sMailbox->metadata, h.metadataSize) != h.metadataCrc)
                    sResult.status = SUSAMUNE_STATE_BAD_FILE;
                else sResult.metadata = sMailbox->metadata;
            }
            if (sResult.status == SUSAMUNE_STATE_OK) {
                sResult.header = h;
                memcpy(sResult.name, sMailbox->resultName, sizeof(sResult.name));
                if (window) {
                    DCInvalidateRange(&sMailbox->window, sizeof(sMailbox->window));
                    sResult.window = sMailbox->window;
                    const u32 size = sPending.reserved & SUSAMUNE_STATE_WINDOW_SIZE_MASK;
                    bool valid = sResult.window.offset == sPending.poolOffset &&
                        sResult.window.size == size && sMailbox->response.transferred == size;
                    for (u32 i = 0; i < 5; ++i) valid = valid && !sResult.window.reserved[i];
                    if (!valid) sResult.status = SUSAMUNE_STATE_BAD_FILE;
                }
            }
        }
    } else if (sPending.command == SUSAMUNE_STATE_CMD_TAS_READ ||
               sPending.command == SUSAMUNE_STATE_CMD_TAS_COMMIT ||
               sPending.command == SUSAMUNE_STATE_CMD_TAS_RENAME) {
        if (sResult.status == SUSAMUNE_STATE_OK) {
            DCInvalidateRange(&sMailbox->tasProject, sizeof(sMailbox->tasProject));
            const SusamuneTasManifest &project = sMailbox->tasProject;
            if (!projectValid(&project) || project.projectId != sPending.id ||
                project.projectId != sResult.id || project.checksum != r.headerCrc ||
                (sPending.command == SUSAMUNE_STATE_CMD_TAS_COMMIT && project.checksum != sProjectReplyCrc) ||
                (sPending.command == SUSAMUNE_STATE_CMD_TAS_READ &&
                 sPending.expectedHeaderCrc && project.checksum != sPending.expectedHeaderCrc))
                sResult.status = SUSAMUNE_STATE_BAD_FILE;
            else sResult.project = project;
        }
    } else if (sPending.command == SUSAMUNE_STATE_CMD_TAS_BEGIN ||
               sPending.command == SUSAMUNE_STATE_CMD_TAS_DELETE) {
        if (sResult.status == SUSAMUNE_STATE_OK &&
            (!sResult.id || sResult.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
             (sPending.command == SUSAMUNE_STATE_CMD_TAS_DELETE && sResult.id != sPending.id)))
            sResult.status = SUSAMUNE_STATE_BAD_FILE;
    } else if (sPending.command == SUSAMUNE_STATE_CMD_CATALOG ||
               sPending.command == SUSAMUNE_STATE_CMD_TAS_CATALOG) {
        sCatalogReady = false;
        if (sResult.status == SUSAMUNE_STATE_OK) {
            DCInvalidateRange(&sMailbox->catalog, sizeof(sMailbox->catalog));
            const SusamuneStateCatalog &c = sMailbox->catalog;
            bool valid = c.count <= SUSAMUNE_STATE_CATALOG_COUNT && c.afterId == sPending.id && c.more <= 1;
            u32 prior = c.afterId;
            for (u32 i = 0; valid && i < c.count; ++i) {
                const SusamuneStateCatalogEntry &e = c.entries[i];
                valid = e.id > prior && e.id <= SUSAMUNE_STATE_MAX_ARCHIVE_ID &&
                    e.packedSize && e.packedSize <= archiveCapacity() +
                    (sPending.command == SUSAMUNE_STATE_CMD_TAS_CATALOG ? SUSAMUNE_TAS_TAPE_MAX_BYTES : 0) &&
                    SusamuneStateNameValid(e.name);
                prior = e.id;
            }
            valid = valid && c.nextId == prior;
            sCatalogReady = valid;
            if (!valid) sResult.status = SUSAMUNE_STATE_BAD_FILE;
        }
    }
    memset(&sPending, 0, sizeof(sPending));
    sResultReady = true;
    if (sAbandoned) discardCancelledResult();
}
bool available() { return sAvailable; }
bool busy() {
    return sPending.command || sTransferFailed || sTransferPhase == TRANSFER_CONSUME ||
        sTransferPhase == TRANSFER_RELEASE;
}
bool quiet() {
    return !busy() && !sResultReady && !sResultTaken && sTransferPhase == TRANSFER_NONE;
}
void *stagingBase() { return reinterpret_cast<void *>(kStaging); }
u32 stagingSize() { return TransferLease::sharedMap() ? SUSAMUNE_TRANSFER_STAGE_SIZE : SUSAMUNE_STATE_STAGING_SIZE; }
u32 archiveCapacity() {
    return TransferLease::sharedMap() ? SUSAMUNE_TRANSFER_POOL_SIZE : SUSAMUNE_STATE_POOL_EXPANDED_SIZE;
}
void *tailWindowBase() {
    return TransferLease::sharedMap() ? static_cast<u8 *>(stagingBase()) +
        SUSAMUNE_TRANSFER_IMPORT_WINDOW_OFFSET : nullptr;
}
u32 tailWindowSize() {
    return TransferLease::sharedMap() ? SUSAMUNE_TRANSFER_IMPORT_WINDOW_SIZE : 0;
}
u32 configId() { return sConfig; }

static bool publishExport(const SusamuneStateArchiveHeader &source, const void *metadata, u32 offset,
                          const SusamuneTasRequest *project, bool tape,
                          BuildExportPlan builder = nullptr, void *context = nullptr) {
    const StatePoolMemory &memory = sMemory;
    if (!requestIdle() || !metadata || (builder && (!sSharedBackend || tape || offset)) ||
        (project && (!SusamuneTasRequestValid(project) || !project->projectId || project->componentId ||
                     (project->role == SUSAMUNE_TAS_TAPE_ROLE) != tape)) ||
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
    if (!headerValid(&h)) return false;
    if (tape && (!project || offset || !SusamuneTasTapeMetadataValid(&h,
        static_cast<const SusamuneTasTakeData *>(metadata)))) return false;
    if (!claimTransfer()) return false;
    if (builder) {
        SusamuneStateExportPlan &plan = *static_cast<SusamuneStateExportPlan *>(stagingBase());
        bool valid = builder(context, plan, h.metadataCrc) &&
            SusamuneStateExportPlanValid(&plan, &h, StatePoolMemoryCapacity(&memory));
        for (u32 i = 0; valid && i < plan.count; ++i) {
            StatePoolMemorySpan span;
            valid = StatePoolMemorySpanAt(&memory, plan.blocks[i].offset, plan.blocks[i].size, &span) &&
                span.size == plan.blocks[i].size;
        }
        if (!valid) { releaseOwner(); return false; }
        for (u32 i = 0; i < plan.count; ++i)
            syncPool(plan.blocks[i].offset, plan.blocks[i].size, false);
        DCFlushRange(&plan, sizeof(plan));
    }
    memcpy(&sMailbox->header, &h, sizeof(h));
    memcpy(sMailbox->metadata, metadata, h.metadataSize);
    DCFlushRange(&sMailbox->header, sizeof(h));
    DCFlushRange(sMailbox->metadata, h.metadataSize);
    if (tape) DCFlushRange(stagingBase(), h.packedSize);
    else if (!builder) syncPool(offset, h.packedSize, false);
    const bool submitted = submit(SUSAMUNE_STATE_CMD_EXPORT, 0, offset, h.packedSize, 0,
                                  builder ? SUSAMUNE_STATE_EXPORT_PLAN : 0, project);
    if (!submitted && builder) releaseOwner();
    return submitted;
}
bool startExport(const SusamuneStateArchiveHeader &source, const void *metadata, u32 offset,
                 const SusamuneTasRequest *project) {
    return publishExport(source, metadata, offset, project, false);
}
bool startPlannedExport(const SusamuneStateArchiveHeader &source, const void *metadata,
                        BuildExportPlan builder, void *context, const SusamuneTasRequest *project) {
    if (!builder) return false;
    return publishExport(source, metadata, 0, project, false, builder, context);
}
bool startTapeExport(const SusamuneStateArchiveHeader &source, const SusamuneTasTakeData &take,
                     const void *frames, const void *transitions, const SusamuneTasRequest &project) {
    if (!requestIdle() || !SusamuneTasTakeValid(&take) ||
        (take.frames && !frames) || (take.transitionCount && !transitions) ||
        !SusamuneTasRequestValid(&project) || !project.projectId || project.componentId ||
        project.role != SUSAMUNE_TAS_TAPE_ROLE) return false;
    SusamuneStateArchiveHeader h = source;
    h.metadataSize = sizeof(take);
    h.packedSize = h.rawSize = SusamuneTasTakeBytes(&take);
    h.snapshotVersion = SUSAMUNE_TAS_TAPE_SNAPSHOT;
    h.sceneKey = take.startScene;
    if (!claimTransfer()) return false;
    u8 *payload = static_cast<u8 *>(stagingBase());
    memset(payload, 0, 4);
    if (take.frames) memcpy(payload + 4, frames, take.frames * 16);
    if (take.transitionCount) memcpy(payload + 4 + take.frames * 16, transitions, take.transitionCount * 16);
    if (publishExport(h, &take, 0, &project, true)) return true;
    releaseOwner();
    return false;
}
bool startTapeImport(const SusamuneTasManifest &project) {
    if (!transferReady() || !projectValid(&project)) return false;
    SusamuneTasRequest context = {};
    context.projectId = project.projectId; context.componentId = project.tape.componentId;
    context.projectGeneration = project.generation; context.role = SUSAMUNE_TAS_TAPE_ROLE;
    context.expectedProjectCrc = project.checksum;
    context.checksum = SusamuneTasRequestCrc(&context);
    return startImport(context.componentId, project.tape.headerCrc, project.tape.packedBytes, 0, &context);
}
bool tapePayload(const Result &result, SusamuneTasTakeData &take, const void *&frames, const void *&transitions) {
    frames = transitions = nullptr;
    if (!sResultTaken || !result.token.generation || result.token.generation != sResult.token.generation ||
        result.status != SUSAMUNE_STATE_OK || result.command != SUSAMUNE_STATE_CMD_IMPORT ||
        result.metadata != sMailbox->metadata || result.metadata != sResult.metadata ||
        memcmp(&result.header, &sResult.header, sizeof(result.header)) ||
        !SusamuneTasTapeHeaderValid(&result.header)) return false;
    const SusamuneTasTakeData &info = *static_cast<const SusamuneTasTakeData *>(result.metadata);
    const u8 *payload = static_cast<const u8 *>(stagingBase());
    if (!SusamuneTasTapeMetadataValid(&result.header, &info) ||
        SusamuneStateCrc(&info, sizeof(info)) != result.header.metadataCrc ||
        payload[0] || payload[1] || payload[2] || payload[3] ||
        SusamuneStateCrc(payload, result.header.packedSize) != result.header.payloadCrc) return false;
    take = info; frames = payload + 4; transitions = payload + 4 + info.frames * 16;
    return true;
}
bool startImport(u32 id, u32 crc, u32 size, u32 offset, const SusamuneTasRequest *project) {
    if (!requestIdle()) return false;
    const StatePoolMemory &memory = sMemory;
    const u32 tail = size > stagingSize() ? size - stagingSize() : 0;
    if (!id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID || !size) return false;
    if (size > StatePoolMemoryCapacity(&memory) || !StatePoolMemoryRangeValid(&memory, offset, tail)) return false;
    return submit(SUSAMUNE_STATE_CMD_IMPORT, id, offset, size, crc, 0, project);
}
bool startWindow(u32 id, u32 crc, u32 packed, u32 offset, u32 size, const SusamuneTasRequest *project) {
    if (!requestIdle() || !id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID || !packed ||
        packed > archiveCapacity() || !size || size > stagingSize() || offset > packed || size > packed - offset) return false;
    return submit(SUSAMUNE_STATE_CMD_READ_WINDOW, id, offset, packed, crc, size, project);
}
bool startImportWindow(u32 id, u32 crc, u32 packed, u32 offset, u32 size,
                       const SusamuneTasRequest *project) {
    if (!requestIdle() || !sSharedBackend || !id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
        !packed || packed > archiveCapacity() || !size || size > tailWindowSize() ||
        offset > packed || size > packed - offset) return false;
    return submit(SUSAMUNE_STATE_CMD_READ_WINDOW, id, offset, packed, crc,
        size | SUSAMUNE_STATE_WINDOW_TAIL, project);
}
bool refresh(u32 afterId) {
    if (afterId > SUSAMUNE_STATE_MAX_ARCHIVE_ID) return false;
    if (!submit(SUSAMUNE_STATE_CMD_CATALOG, afterId, 0, 0, 0)) return false;
    sCatalogReady = false;
    return true;
}
bool rename(u32 id, u32 crc, const char *name) {
    if (!requestIdle() || !id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
        !SusamuneStateNameValid(name) || !name[0]) return false;
    if (!claimTransfer()) return false;
    memset(sMailbox->requestName, 0, sizeof(sMailbox->requestName));
    for (u32 i = 0; name[i]; ++i) sMailbox->requestName[i] = name[i];
    DCFlushRange(sMailbox->requestName, sizeof(sMailbox->requestName));
    if (!submit(SUSAMUNE_STATE_CMD_RENAME, id, 0, 0, crc)) return false;
    sCatalogReady = false;
    return true;
}
bool remove(u32 id, u32 crc) {
    if (!id || id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
        !submit(SUSAMUNE_STATE_CMD_DELETE, id, 0, 0, crc)) return false;
    sCatalogReady = false;
    return true;
}
bool cancel() {
    if (!sPending.command || sPending.command == SUSAMUNE_STATE_CMD_CANCEL ||
        sPending.command == SUSAMUNE_STATE_CMD_RENAME || sPending.command == SUSAMUNE_STATE_CMD_DELETE ||
        sPending.command >= SUSAMUNE_STATE_CMD_TAS_BEGIN) return false;
    if (sSharedBackend) {
        sCancelRequested = true;
        submitTransfer();
        return !sTransferFailed;
    }
    // Keep the imported range owned until cancellation's own receipt arrives.
    memset(&sPending, 0, sizeof(sPending));
    return submit(SUSAMUNE_STATE_CMD_CANCEL, 0, 0, 0, 0);
}
bool takeResult(Result &out) {
    if (!sResultReady || sResultTaken || sResult.command >= SUSAMUNE_STATE_CMD_TAS_BEGIN) return false;
    out = sResult;
    sResultReady = false;
    sResultTaken = true;
    return true;
}
bool consumeResult(ResultToken token, bool keepOwner) {
    if (!sResultTaken || !token.generation || token.generation != sResult.token.generation) return false;
    sResultTaken = false;
    if (sSharedBackend) {
        sKeepOwner = keepOwner;
        sTransferPhase = TRANSFER_CONSUME;
        finishTransfer();
    }
    return true;
}
bool consumeResult(const Result &result, bool keepOwner) { return consumeResult(result.token, keepOwner); }
bool releaseOwner() {
    if (sPending.command || sResultReady || sResultTaken) return false;
    if (sTransferPhase == TRANSFER_LOCAL) sTransferPhase = TRANSFER_RELEASE;
    if (sTransferPhase == TRANSFER_CONSUME) sKeepOwner = false;
    finishTransfer();
    return sTransferPhase == TRANSFER_NONE;
}
void abandon() {
    cancel();
    sAbandoned = true;
    discardCancelledResult();
    if (!sPending.command && !sResultReady && !sResultTaken) releaseOwner();
}
void discardCancelledResult() {
    if (sResultReady && (sAbandoned || sResult.command == SUSAMUNE_STATE_CMD_CANCEL)) {
        sResultReady = false;
        sResultTaken = true;
        consumeResult(sResult.token);
        sAbandoned = false;
    }
}
bool takeProjectResult(Result &out) {
    if (!sResultReady || sResultTaken || sResult.command < SUSAMUNE_STATE_CMD_TAS_BEGIN) return false;
    out = sResult;
    sResultReady = false;
    sResultTaken = true;
    return true;
}
bool projectName(const char *name) {
    if (!requestIdle() || !SusamuneStateNameValid(name) || !name[0] || !claimTransfer()) return false;
    memset(sMailbox->requestName, 0, sizeof(sMailbox->requestName));
    for (u32 i = 0; name[i]; ++i) sMailbox->requestName[i] = name[i];
    DCFlushRange(sMailbox->requestName, sizeof(sMailbox->requestName));
    return true;
}
bool projectBegin(const char *name) {
    return projectName(name) && submit(SUSAMUNE_STATE_CMD_TAS_BEGIN, 0, 0, 0, 0);
}
bool projectRead(u32 id, u32 crc) {
    return id && id <= SUSAMUNE_STATE_MAX_ARCHIVE_ID &&
        submit(SUSAMUNE_STATE_CMD_TAS_READ, id, 0, 0, crc);
}
bool projectCommit(const SusamuneTasManifest &project, u32 previousCrc) {
    if (!requestIdle() || !projectValid(&project) || !claimTransfer()) return false;
    sProjectReplyCrc = project.checksum;
    sMailbox->tasProject = project;
    DCFlushRange(&sMailbox->tasProject, sizeof(sMailbox->tasProject));
    return submit(SUSAMUNE_STATE_CMD_TAS_COMMIT, project.projectId, 0, 0, previousCrc);
}
bool projectCatalog(u32 afterId) {
    if (afterId > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
        !submit(SUSAMUNE_STATE_CMD_TAS_CATALOG, afterId, 0, 0, 0)) return false;
    sCatalogReady = false;
    return true;
}
bool projectRename(u32 id, u32 crc, const char *name) {
    return id && id <= SUSAMUNE_STATE_MAX_ARCHIVE_ID && projectName(name) &&
        submit(SUSAMUNE_STATE_CMD_TAS_RENAME, id, 0, 0, crc);
}
bool projectDelete(u32 id, u32 crc) {
    return id && id <= SUSAMUNE_STATE_MAX_ARCHIVE_ID &&
        submit(SUSAMUNE_STATE_CMD_TAS_DELETE, id, 0, 0, crc);
}
bool catalogReady() { return sCatalogReady; }
const SusamuneStateCatalog &catalog() { return sMailbox->catalog; }
}
