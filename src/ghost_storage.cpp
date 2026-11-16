#include "susamune/ghost_recording_native.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_trace_share.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/ghost_storage.hxx"

#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
#include "susamune/ghost.hxx"
#include "susamune/ghost_camera.h"
#include "susamune/crash_report.hxx"
#include "susamune/iling.hxx"
#include "susamune/menu.hxx"
#include "susamune/records.hxx"
#include "susamune/records_persistence.hxx"
#include "susamune/transfer_lease.hxx"
#include "susamune/transfer_layout.h"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/dolphin_ghost_web.hxx"
#include "susamune/dolphin_ghost_library.hxx"
#include "susamune/dolphin_ghost_account.hxx"
#include "susamune/dolphin_http.hxx"
#endif

namespace GhostStorage {
namespace {

const u32 kTimeoutFrames = 30u * 60u;
const u32 kCatalogBytes = sizeof(SusamuneGhostCatalogPage);

const char kUnavailable[] = "Ghost storage unavailable";
const char kDolphinUnavailable[] = "Ghost storage unavailable in Dolphin";
const char kReady[] = "Ghost storage ready";
const char kRefreshing[] = "Refreshing ghost slots";
const char kSaving[] = "Saving ghost";
const char kLoading[] = "Loading ghost";
const char kDeleting[] = "Deleting ghost";
const char kExportingShare[] = "Exporting .smsghost file";
const char kImportingShare[] = "Scanning imported ghosts";
const char kSaved[] = "Ghost saved";
const char kLoaded[] = "Ghost loaded";
const char kRaceLoaded[] = "Ghost ready - restart to race";
const char kDeleted[] = "Ghost deleted";
const char kExportedShare[] = "Ghost exported to share folder";
const char kExportExists[] = "Export filename already exists";
const char kImportedShare[] = "Imported ghosts refreshed";
const char kSaveChanged[] = "Ghost changed; confirm save again";
const char kLoadIgnored[] = "Stale ghost load ignored";
const char kNoRecording[] = "No ghost ready to save";
const char kCatalogNeeded[] = "Refresh ghost slots first";
const char kBusy[] = "Ghost storage busy";
const char kBadSlot[] = "Invalid ghost slot";
const char kOccupied[] = "Ghost slot occupied";
const char kEmpty[] = "Ghost slot is empty";
const char kUnsafe[] = "Ghost slot is unsafe";
const char kExportFailed[] = "Could not prepare ghost file";
const char kImportFailed[] = "Loaded ghost failed validation";
const char kTimeout[] = "Ghost storage timed out; still waiting";
const char kProtocol[] = "Ghost storage protocol error";
const char kInvalidRequest[] = "Ghost storage request rejected";
const char kFileTooLarge[] = "Ghost file is too large";
const char kInvalidFile[] = "Ghost file is corrupt";
const char kForwardVersion[] = "Ghost version is unsupported";
const char kQuota[] = "Ghost storage is full";
const char kNotFound[] = "Ghost slot was not found";
const char kIoError[] = "Ghost storage I/O error";
const char kCatalogInvalid[] = "Ghost catalog failed validation";
const char kEmptyName[] = "Empty slot";
const char kUnsafeName[] = "Unsafe ghost";
const char kUnnamedName[] = "Unnamed ghost";

enum LoadDestination {
    LOAD_DESTINATION_RACE,
    LOAD_DESTINATION_OBSERVER_PRIMARY,
    LOAD_DESTINATION_OBSERVER_SECONDARY,
    LOAD_DESTINATION_EXPORT,
};

SusamuneGhostCatalogPage *const sPages =
    reinterpret_cast<SusamuneGhostCatalogPage *>(
        SUSAMUNE_GHOST_CATALOG_CACHE_PPC_BASE);
static_assert(2 * kCatalogBytes <= SUSAMUNE_GHOST_CATALOG_CACHE_SIZE,
              "ghost pages exceed the fixed cache");
const char *sStatus = kUnavailable;
u32 sSequence, sPendingSequence, sPendingRecordToken, sPendingDurationQf;
u32 sWaitFrames, sEpoch, sPendingEpoch, sPendingSlot;
u32 sOffsets[2];
u16 sPendingCommand, sPendingProfile;
u8 sPendingLoadDestination, sProfile;
Identity sPendingIdentity, sLoadedIdentity;
bool sLoadedValid, sAvailable, sReady[2], sRefreshQueued[2], sCachedRefresh[2];
bool sImportScanQueued, sTimedOut;
bool sWebOpen, sWebReady;
GhostServiceAccountInfo sWebAccount;
static_assert(sizeof(GhostServicePage) <= kCatalogBytes, "Online page exceeds imported cache");

#if !IS_EMULATOR
const char *statusForCode(s32 status);
void clearCatalog(bool imported);
enum TransferPhase { TRANSFER_NONE, TRANSFER_LOCAL, TRANSFER_SUBMIT,
    TRANSFER_REMOTE, TRANSFER_READING, TRANSFER_CONSUME, TRANSFER_RELEASE };
TransferLease::Token sTransferToken;
TransferLease::Borrow sTransferBorrow;
u8 sTransferPhase;
bool sSharedBackend, sTransferFailed;

void *transferPayload() {
    return sTransferPhase != TRANSFER_NONE
        ? reinterpret_cast<void *>(SUSAMUNE_TRANSFER_STAGE_PPC_BASE)
        : (void *)SUSAMUNE_GHOST_STORAGE_DATA_PPC_PTR;
}

void readBackend() {
    volatile SusamuneGhostStorageMailbox *mailbox = SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    DCInvalidateRange((void *)&mailbox->response, sizeof(mailbox->response));
    SusamuneGhostStorageResponse response;
    memcpy(&response, (const void *)&mailbox->response, sizeof(response));
    sAvailable = false;
    if (response.responseMagic == SUSAMUNE_GHOST_STORAGE_MAGIC &&
        response.protocolVersion == SUSAMUNE_GHOST_STORAGE_VERSION &&
        (response.flags & ~(SUSAMUNE_GHOST_RESPONSE_READY |
                            SUSAMUNE_GHOST_RESPONSE_BUSY)) == 0 &&
        !(response.flags & SUSAMUNE_GHOST_RESPONSE_BUSY)) {
        sSequence = response.ackSeq;
        sAvailable = (response.flags & SUSAMUNE_GHOST_RESPONSE_READY) != 0;
        sStatus = sAvailable ? kReady : statusForCode(response.status);
    }
}

bool transferReady() {
    TransferLease::poll();
    const TransferLease::Mode mode = TransferLease::init();
    if (mode == TransferLease::FAILED ||
        (sSharedBackend && mode != TransferLease::SHARED)) sTransferFailed = true;
    if (sTransferFailed) { sStatus = kProtocol; return false; }
    if (mode == TransferLease::SHARED && !sSharedBackend) {
        // Activation may reset the ordinary mailbox only while every reader is idle.
        if (busy()) { sTransferFailed = true; sStatus = kProtocol; return false; }
        sSharedBackend = true;
        readBackend();
        clearCatalog(false); clearCatalog(true);
        sRefreshQueued[0] = sRefreshQueued[1] = sAvailable;
        sCachedRefresh[0] = sCachedRefresh[1] = false;
    }
    return mode == TransferLease::SHARED || TransferLease::legacyAllowed();
}

bool transferSucceeded(bool result) {
    if (!result && TransferLease::mode() == TransferLease::FAILED) {
        sTransferFailed = true;
        sStatus = kProtocol;
    }
    return result;
}

bool claimTransfer() {
    if (!transferReady() || !sAvailable || busy()) return false;
    if (!sSharedBackend) return true;
    TransferLease::Token token;
    if (!transferSucceeded(TransferLease::claim(TransferLease::GHOST, token))) return false;
    sTransferToken = token;
    sTransferPhase = TRANSFER_LOCAL;
    return true;
}

void finishTransfer() {
    if (sTransferPhase == TRANSFER_CONSUME) {
        if (!transferSucceeded(TransferLease::consumed(sTransferToken, sTransferBorrow))) return;
        sTransferPhase = TRANSFER_RELEASE;
    }
    if (sTransferPhase == TRANSFER_RELEASE &&
        transferSucceeded(TransferLease::release(sTransferToken))) {
        sTransferToken = {}; sTransferBorrow = {};
        sTransferPhase = TRANSFER_NONE;
    }
}

void submitTransfer() {
    if (sTransferPhase == TRANSFER_SUBMIT && transferSucceeded(TransferLease::submit(
            sTransferToken, sPendingSequence, 0, sPendingCommand)))
        sTransferPhase = TRANSFER_REMOTE;
}
#endif

#if IS_EMULATOR && TIMEWARP_LIVE_RACING
void *transferPayload() { return reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE); }
bool claimTransfer() { return sAvailable && !busy() && DolphinGhostLibrary::ready(); }
#endif

void notify(const char *status) {
    sStatus = status;
    if (gMenu) gMenu->toast(status);
}

void observeLoadedPlayback() {
    if (!Ghost::playbackPinned()) sLoadedValid = false;
}

u8 activeProfile() {
    const int profile = ILing::pbProfile();
    if (profile == 4) return SUSAMUNE_GHOST_HOVERLESS_PROFILE;
    return profile >= 0 && profile < (int)SUSAMUNE_GHOST_PROFILE_COUNT
        ? static_cast<u8>(profile) : 0;
}

void clearCatalog(bool imported) {
    memset(&sPages[imported], 0, kCatalogBytes);
    sReady[imported] = false;
}

void observeProfile() {
    const u8 profile = activeProfile();
    if (profile == sProfile) return;
    if (sPendingCommand == SUSAMUNE_GHOST_CMD_LOAD &&
        sPendingProfile != SUSAMUNE_GHOST_IMPORTED_PROFILE &&
        sPendingLoadDestination != LOAD_DESTINATION_RACE) Ghost::stopObserver();
    sProfile = profile;
    sOffsets[0] = 0;
    clearCatalog(false);
    sRefreshQueued[0] = sAvailable;
    sCachedRefresh[0] = false;
}

__attribute__((noinline)) const char *webStatus(s32 status) {
    volatile s32 code = status;
    if (code == GHOST_SERVICE_NETWORK) return "Could not connect to Delfino Ghosts";
    if (code == GHOST_SERVICE_TLS) return "Secure connection failed; check system date";
    if (code == GHOST_SERVICE_CLOCK) return "Set the system date before connecting";
    if (code == GHOST_SERVICE_RANDOM) return IS_EMULATOR?"Run Dolphin data setup before connecting":"Wii secure connection unavailable";
    if (code == GHOST_SERVICE_RESPONSE) return "Delfino Ghosts response was not usable";
    if (code == GHOST_SERVICE_HASH) return "Download changed; refresh and retry";
    if (code == GHOST_SERVICE_CANCELLED) return "Download cancelled";
    if (code == GHOST_SERVICE_TIMEOUT) return "Connection timed out; try again";
    if (code == GHOST_SERVICE_STARTUP) return "Network not ready; check connection";
    if (code == GHOST_SERVICE_DNS) return "Could not find Delfino Ghosts; retry";
    if (code == GHOST_SERVICE_RATE_LIMIT) return "Service busy; please wait before retrying";
    if (code == GHOST_SERVICE_UNAVAILABLE) return "Delfino Ghosts temporarily unavailable";
    if (code == GHOST_SERVICE_SORT_UNSUPPORTED) return "Level sorting is not available yet";
    if (code == GHOST_SERVICE_LINK_REQUIRED) return "Link your Delfino Ghosts account first";
    if (code == GHOST_SERVICE_LINK_EXPIRED) return "Link expired; request a new code";
    if (code == GHOST_SERVICE_UPLOAD_REJECTED) return "Upload refused; check ghost or account limits";
    if (code == GHOST_SERVICE_ACCOUNT_LIMIT) return "Account full; manage uploads on the website";
    return kProtocol;
}

const char *statusForCode(s32 status) {
    if (status <= GHOST_SERVICE_NETWORK && status >= GHOST_SERVICE_ACCOUNT_LIMIT) return webStatus(status);
    switch (status) {
    case SUSAMUNE_GHOST_STATUS_OK: return kReady;
    case SUSAMUNE_GHOST_STATUS_INVALID_REQUEST: return kInvalidRequest;
    case SUSAMUNE_GHOST_STATUS_INVALID_SLOT: return kBadSlot;
    case SUSAMUNE_GHOST_STATUS_PAYLOAD_TOO_LARGE: return kFileTooLarge;
    case SUSAMUNE_GHOST_STATUS_INVALID_FILE: return kInvalidFile;
    case SUSAMUNE_GHOST_STATUS_FORWARD_VERSION: return kForwardVersion;
    case SUSAMUNE_GHOST_STATUS_QUOTA_EXCEEDED: return kQuota;
    case SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE: return kUnavailable;
    case SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE: return kUnsafe;
    case SUSAMUNE_GHOST_STATUS_NOT_FOUND: return kNotFound;
    case SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED: return kOccupied;
    default:
        return status >= SUSAMUNE_GHOST_STATUS_IO_BASE ? kIoError : kProtocol;
    }
}

#if defined(SUSAMUNE_VERSION_JP)
const u32 kGameId = SUSAMUNE_GHOST_GAME_ID_JP;
const u8 kRegion = SUSAMUNE_GHOST_REGION_JP;
#elif defined(SUSAMUNE_VERSION_US)
const u32 kGameId = SUSAMUNE_GHOST_GAME_ID_US;
const u8 kRegion = SUSAMUNE_GHOST_REGION_US;
#elif defined(SUSAMUNE_VERSION_PAL)
const u32 kGameId = SUSAMUNE_GHOST_GAME_ID_PAL;
const u8 kRegion = SUSAMUNE_GHOST_REGION_PAL;
#else
#error "Unknown game version"
#endif

#include "susamune/ghost_catalog_validation.inc"

// Keep catalog validation tables outside the fixed update input.
__attribute__((noinline))
bool sanitizeSlot(const SusamuneGhostSlotInfo &raw,
                  SusamuneGhostSlotInfo *out, bool imported) {
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
    return DolphinGhostWeb::sanitizeSlot(raw,out,imported);
#else
    return validateCatalogSlot(raw,out,imported,kGameId,kRegion);
#endif
}

bool validLeaf(const char *leaf) {
    u32 length = 0;
    while (length < SUSAMUNE_GHOST_IMPORT_LEAF_SIZE && leaf[length]) {
        const u8 ch = static_cast<u8>(leaf[length]);
        if (ch < 0x20 || ch > 0x7e || ch == '/' || ch == '\\' ||
            ch == ':' || ch == '*' || ch == '?' || ch == '"' ||
            ch == '<' || ch == '>' || ch == '|') return false;
        length++;
    }
    if (length <= 9 || length >= SUSAMUNE_GHOST_IMPORT_LEAF_SIZE) return false;
    const char suffix[] = ".smsghost";
    for (u32 i = 0; i < 9; i++) {
        u8 ch = static_cast<u8>(leaf[length - 9 + i]);
        if (ch >= 'A' && ch <= 'Z') ch += 'a' - 'A';
        if (ch != suffix[i]) return false;
    }
    for (u32 i = length; i < SUSAMUNE_GHOST_IMPORT_LEAF_SIZE; i++)
        if (leaf[i]) return false;
    return true;
}

bool zeroBytes(const void *data, u32 size) {
    const u8 *bytes = static_cast<const u8 *>(data);
    for (u32 i = 0; i < size; i++) if (bytes[i]) return false;
    return true;
}

bool adoptCatalog(const SusamuneGhostStorageResponse &response) {
#if IS_EMULATOR && !TIMEWARP_LIVE_RACING
    (void)response;
    return false;
#else
    const bool imported = response.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
    SusamuneGhostCatalogPage *page = &sPages[imported];
    clearCatalog(imported);
#if !IS_EMULATOR
    DCInvalidateRange(transferPayload(), kCatalogBytes);
#endif
    memcpy(page, transferPayload(), kCatalogBytes);
    const u64 totalDuration = (static_cast<u64>(page->totalDurationQfHi) << 32) |
                              page->totalDurationQfLo;
    const u32 remaining = page->first < page->totalCount
        ? page->totalCount - page->first : 0;
    const u32 expectedCount = remaining < SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES
        ? remaining : SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES;
    bool valid = response.payloadSize == kCatalogBytes &&
        page->magic == SUSAMUNE_GHOST_CATALOG_PAGE_MAGIC &&
        page->version == SUSAMUNE_GHOST_CATALOG_PAGE_VERSION &&
        page->first == sPendingSlot && page->flags == 0 &&
        page->count == expectedCount && response.slotCount == page->count &&
        totalDuration <= static_cast<u64>(page->totalCount) *
                         SUSAMUNE_GHOST_MAX_DURATION_QF;
    u64 pageDuration = 0;
    for (u32 i = 0; valid && i < SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES; i++) {
        SusamuneGhostCatalogEntry &entry = page->entries[i];
        if (i >= page->count) {
            valid = zeroBytes(&entry, sizeof(entry));
            continue;
        }
        SusamuneGhostSlotInfo raw = entry.info;
        valid = entry.id != SUSAMUNE_GHOST_SLOT_AUTO &&
            (imported ? validLeaf(entry.leaf) :
                        zeroBytes(entry.leaf, sizeof(entry.leaf))) &&
            sanitizeSlot(raw, &entry.info, imported) &&
            (entry.info.flags & (SUSAMUNE_GHOST_SLOT_PRESENT |
                                 SUSAMUNE_GHOST_SLOT_UNSAFE)) != 0;
        for (u32 previous = 0; valid && previous < i; previous++) {
            valid = imported
                ? memcmp(entry.leaf, page->entries[previous].leaf,
                         sizeof(entry.leaf)) != 0
                : entry.id != page->entries[previous].id;
        }
        pageDuration += entry.info.durationQf;
    }
    if (!valid || pageDuration > totalDuration) {
        clearCatalog(imported);
        return false;
    }
    sReady[imported] = true;
    // Deleting the final row of the final page should return to existing rows.
    if (!page->count && page->first && page->totalCount) {
        sOffsets[imported] = ((page->totalCount - 1) /
            SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES) * SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES;
        sRefreshQueued[imported] = sAvailable;
        sCachedRefresh[imported] = false;
    } else if (!page->totalCount && page->first) {
        sOffsets[imported] = 0;
        sRefreshQueued[imported] = sAvailable;
        sCachedRefresh[imported] = false;
    }
    return true;
#endif
}

bool responseShapeIsValid(const SusamuneGhostStorageResponse &response,
                          u16 command) {
    if (response.profile != sPendingProfile ||
        (response.flags & ~(SUSAMUNE_GHOST_RESPONSE_READY |
                            SUSAMUNE_GHOST_RESPONSE_BUSY)) != 0 ||
        (response.flags & SUSAMUNE_GHOST_RESPONSE_BUSY) != 0) return false;
    if (response.status != SUSAMUNE_GHOST_STATUS_OK)
        return response.payloadSize == 0 && response.slotCount == 0;
    if (!(response.flags & SUSAMUNE_GHOST_RESPONSE_READY)) return false;
    if (command == SUSAMUNE_GHOST_CMD_WEB_LIST)
        return response.payloadSize == sizeof(GhostServicePage) && !response.slotCount && !response.slot;
    if(command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT)
        return response.payloadSize==sizeof(GhostServiceAccountInfo) && !response.slotCount && response.slot==sPendingSlot;
    if (command == SUSAMUNE_GHOST_CMD_LIST ||
        command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN)
        return response.payloadSize == kCatalogBytes &&
               response.slotCount <= SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES &&
               response.slot == 0;
    if (response.slotCount != 0 ||
        response.slot == SUSAMUNE_GHOST_SLOT_AUTO) return false;
    if (command != SUSAMUNE_GHOST_CMD_SAVE && response.slot != sPendingSlot)
        return false;
    if (command == SUSAMUNE_GHOST_CMD_LOAD)
        return response.payloadSize >= SUSAMUNE_GHOST_FILE_HEADER_SIZE &&
               response.payloadSize <= SUSAMUNE_GHOST_MAX_FILE_SIZE;
    return response.payloadSize == 0;
}

#if !IS_EMULATOR
void beginRequest(u16 command, u16 profile, u32 slot, u32 payloadSize,
                  u32 recordToken, const char *status, u32 durationQf = 0,
                  u32 expectedGeneration = 0, u32 flags = 0) {
    volatile SusamuneGhostStorageMailbox *mailbox = SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    if (++sSequence == 0) sSequence++;
    CrashReport::note(SUSAMUNE_CRASH_EVENT_STORAGE, command, slot);
    mailbox->request.requestMagic = SUSAMUNE_GHOST_STORAGE_MAGIC;
    mailbox->request.protocolVersion = SUSAMUNE_GHOST_STORAGE_VERSION;
    mailbox->request.command = command;
    mailbox->request.requestSeq = sSequence;
    mailbox->request.profile = profile;
    mailbox->request.reserved = 0;
    mailbox->request.slot = slot;
    mailbox->request.payloadSize = payloadSize;
    mailbox->request.flags = flags;
    mailbox->request.expectedGeneration = expectedGeneration;
    DCFlushRange((void *)&mailbox->request, sizeof(mailbox->request));
    sPendingCommand = command;
    sPendingSequence = sSequence;
    sPendingRecordToken = recordToken;
    sPendingDurationQf = durationQf;
    sPendingProfile = profile;
    sPendingSlot = slot;
    sPendingEpoch = sEpoch;
    sWaitFrames = 0;
    sTimedOut = false;
    sStatus = status;
    if (sTransferPhase == TRANSFER_LOCAL) {
        sTransferPhase = TRANSFER_SUBMIT;
        submitTransfer();
    }
}
#endif

#if IS_EMULATOR && TIMEWARP_LIVE_RACING
void beginRequest(u16 command,u16 profile,u32 slot,u32 payloadSize,u32 recordToken,
                  const char *status,u32 durationQf=0,u32 generation=0,u32 flags=0) {
    SusamuneGhostStorageRequest request={};
    if(++sSequence==0)++sSequence;
    request.requestMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;request.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;
    request.command=command;request.requestSeq=sSequence;request.profile=profile;request.slot=slot;
    request.payloadSize=payloadSize;request.flags=flags;request.expectedGeneration=generation;
    if(!(command>=SUSAMUNE_GHOST_CMD_WEB_UPLOAD?DolphinGhostAccount::begin(request):DolphinGhostLibrary::begin(request))){notify(kBusy);return;}
    sPendingCommand=command;sPendingSequence=sSequence;sPendingRecordToken=recordToken;
    sPendingDurationQf=durationQf;sPendingProfile=profile;sPendingSlot=slot;
    sPendingEpoch=sEpoch;sWaitFrames=0;sTimedOut=false;sStatus=status;
}
#endif

bool beginRefresh(bool imported, u16 command = SUSAMUNE_GHOST_CMD_LIST,
                  bool cached = false) {
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
    if (!claimTransfer()) return false;
    clearCatalog(imported);
    beginRequest(command, imported ? SUSAMUNE_GHOST_IMPORTED_PROFILE : sProfile,
                 sOffsets[imported], 0, 0,
                 command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN ? kImportingShare : kRefreshing,
                 0, 0, cached ? SUSAMUNE_GHOST_REQUEST_CACHED_LIST : 0);
    return true;
#else
    (void)command;
    (void)cached;
    return false;
#endif
}

__attribute__((noinline)) bool requestImportedRefresh(u16 command) {
    observeProfile();
    if (!sAvailable) {
        sStatus = IS_EMULATOR ? kDolphinUnavailable : kUnavailable;
        return false;
    }
    if (command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN) sOffsets[1] = 0;
    clearCatalog(true);
    sRefreshQueued[1] = true;
    sCachedRefresh[1] = false;
    sImportScanQueued = command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN;
    if (busy()) return true;
    if (beginRefresh(true, command)) {
        sRefreshQueued[1] = false;
        sImportScanQueued = false;
    }
    return true;
}

void queueNamespaceRefresh(u16 profile, bool cached = false) {
    const bool imported = profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
    if (!imported && profile != sProfile) return;
    clearCatalog(imported);
    sRefreshQueued[imported] = sAvailable;
    sCachedRefresh[imported] = cached;
}

bool observerLoadDestination(u8 destination) {
    return destination == LOAD_DESTINATION_OBSERVER_PRIMARY ||
           destination == LOAD_DESTINATION_OBSERVER_SECONDARY;
}

void cancelFailedObserverLoad(u8 destination) {
    if (observerLoadDestination(destination)) Ghost::stopObserver();
}

void completeRequest(const SusamuneGhostStorageResponse &response) {
    const u16 command = sPendingCommand;
    const u16 requestProfile = sPendingProfile;
    const u32 requestSlot = sPendingSlot;
    const u32 requestEpoch = sPendingEpoch;
    const u32 recordToken = sPendingRecordToken;
    const u32 durationQf = sPendingDurationQf;
    const u8 loadDestination = sPendingLoadDestination;
    sPendingCommand = SUSAMUNE_GHOST_CMD_NONE;
    sPendingRecordToken = 0;
    sPendingDurationQf = 0;
    sPendingLoadDestination = LOAD_DESTINATION_RACE;
    sWaitFrames = 0;
    sTimedOut = false;
    sAvailable = (response.flags & SUSAMUNE_GHOST_RESPONSE_READY) != 0;

    if (!responseShapeIsValid(response, command)) {
        sAvailable = false;
        cancelFailedObserverLoad(loadDestination);
        notify(kProtocol);
        clearCatalog(requestProfile == SUSAMUNE_GHOST_IMPORTED_PROFILE);
        return;
    }
    if (response.status != SUSAMUNE_GHOST_STATUS_OK) {
        if (command == SUSAMUNE_GHOST_CMD_SAVE) GhostRecording::publicationResult(sPendingSequence, false);
        if(response.status==GHOST_SERVICE_LINK_REQUIRED || response.status==GHOST_SERVICE_LINK_EXPIRED)sWebAccount.linked=0;
        cancelFailedObserverLoad(loadDestination);
        const char *status = command == SUSAMUNE_GHOST_CMD_EXPORT &&
            response.status == SUSAMUNE_GHOST_STATUS_SLOT_OCCUPIED
                ? kExportExists : statusForCode(response.status);
        if (command == SUSAMUNE_GHOST_CMD_LIST) sStatus = status;
        else notify(status);
        if (command != SUSAMUNE_GHOST_CMD_LIST && !sWebOpen)
            queueNamespaceRefresh(requestProfile);
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_WEB_LIST) {
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
        if (sWebOpen) {
#if !IS_EMULATOR
            DCInvalidateRange(transferPayload(), sizeof(GhostServicePage));
#endif
            const auto *page = static_cast<const GhostServicePage *>(transferPayload());
            if (page->magic != GHOST_SERVICE_PAGE_MAGIC || page->count > GHOST_SERVICE_PAGE_COUNT ||
                page->next[sizeof(page->next)-1]) { notify(kProtocol); return; }
            memcpy(&sPages[1], page, sizeof(*page));
            sWebReady = true;
            sStatus = page->count ? "Select a ghost to download" : "No compatible ghosts found";
        }
#endif
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD) {
        notify("Downloaded - available in Imported ghosts");
        if (!sWebOpen) queueNamespaceRefresh(SUSAMUNE_GHOST_IMPORTED_PROFILE);
        return;
    }
    if(command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT) {
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
#if !IS_EMULATOR
        DCInvalidateRange(transferPayload(),sizeof(sWebAccount));
#endif
        const auto *info=static_cast<const GhostServiceAccountInfo*>(transferPayload());
        if(info->magic!=GHOST_SERVICE_ACCOUNT_MAGIC || info->linked>1 || info->pending>1 ||
            info->code[sizeof(info->code)-1] || info->user[sizeof(info->user)-1]){notify(kProtocol);return;}
        sWebAccount=*info;
        sStatus=info->linked?"Account linked - ready to upload":info->pending?"Approve the code, then choose Check link":"Choose Link account to upload ghosts";
#endif
        return;
    }
    if(command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD) {notify("Ghost published on Delfino Ghosts");return;}
    if (command == SUSAMUNE_GHOST_CMD_LIST ||
        command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN) {
        const bool imported = requestProfile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
        const bool stale = (!imported && requestProfile != sProfile) ||
                           requestSlot != sOffsets[imported];
        if (stale) {
            sRefreshQueued[imported] = sAvailable;
            return;
        }
        sStatus = adoptCatalog(response)
            ? command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN ? kImportedShare : kReady
            : kCatalogInvalid;
        if (command == SUSAMUNE_GHOST_CMD_IMPORT_SCAN) notify(sStatus);
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_SAVE) {
        GhostRecording::publicationResult(sPendingSequence, true);
        Records::onGhostSaved(durationQf);
        RecordsPersistence::checkpoint();
        Ghost::releaseSavedRecording(recordToken);
        notify(kSaved);
        queueNamespaceRefresh(requestProfile, true);
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_DELETE) {
        if (sLoadedValid && sameIdentity(sLoadedIdentity, sPendingIdentity)) {
            if (Ghost::playbackPinned()) Ghost::clearPlayback();
            sLoadedValid = false;
        }
        notify(kDeleted);
        queueNamespaceRefresh(requestProfile);
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_EXPORT) {
        notify(kExportedShare);
        return;
    }
    if (command == SUSAMUNE_GHOST_CMD_LOAD) {
        if (requestEpoch != sEpoch || !identityValid(sPendingIdentity) ||
            response.generation != sPendingIdentity.generation) {
            cancelFailedObserverLoad(loadDestination);
            notify(kLoadIgnored);
            queueNamespaceRefresh(requestProfile);
            return;
        }
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
#if !IS_EMULATOR
        DCInvalidateRange(transferPayload(), response.payloadSize);
#endif
        const bool streamed = (sPendingIdentity.flags & SUSAMUNE_GHOST_SLOT_STREAMED) != 0;
        if(loadDestination==LOAD_DESTINATION_EXPORT) {
            notify(streamed&&GhostTraceShare::begin(transferPayload(),response.payloadSize)
                ? "Exporting MSGT recording..." : kExportFailed);
            return;
        }
        const bool accepted = streamed
            ? GhostRecording::loadManifest(transferPayload(), response.payloadSize,
                loadDestination != LOAD_DESTINATION_RACE,
                loadDestination == LOAD_DESTINATION_OBSERVER_SECONDARY)
            : loadDestination == LOAD_DESTINATION_RACE
            ? Ghost::importPlayback(transferPayload(),
                                    response.payloadSize,
                                    requestProfile == SUSAMUNE_GHOST_IMPORTED_PROFILE)
            : Ghost::importObserverTrack(transferPayload(),
                  response.payloadSize, loadDestination == LOAD_DESTINATION_OBSERVER_SECONDARY);
        if (!accepted) {
            cancelFailedObserverLoad(loadDestination);
            notify(streamed ? kImportFailed : "MSGT recording required");
            queueNamespaceRefresh(requestProfile);
            return;
        }
#endif
        if (observerLoadDestination(loadDestination)) {
            notify(kLoaded);
        } else {
            sLoadedIdentity = sPendingIdentity;
            sLoadedValid = true;
            notify(kRaceLoaded);
        }
    }
}

#if !IS_EMULATOR
void pollResponse() {
    volatile SusamuneGhostStorageMailbox *mailbox = SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    DCInvalidateRange((void *)&mailbox->response, sizeof(mailbox->response));
    SusamuneGhostStorageResponse response;
    memcpy(&response, (const void *)&mailbox->response, sizeof(response));
    if (response.responseMagic == SUSAMUNE_GHOST_STORAGE_MAGIC &&
        response.protocolVersion == SUSAMUNE_GHOST_STORAGE_VERSION &&
        response.ackSeq == sPendingSequence &&
        (sTransferPhase == TRANSFER_NONE ||
         (sTransferPhase == TRANSFER_REMOTE &&
          TransferLease::take(sTransferToken, sTransferBorrow)))) {
        if (sTransferPhase == TRANSFER_REMOTE) sTransferPhase = TRANSFER_READING;
        completeRequest(response);
        if (sTransferPhase == TRANSFER_READING) {
            sTransferPhase = TRANSFER_CONSUME;
            finishTransfer();
        }
        return;
    }
    if (sWaitFrames != 0xffffffffu) sWaitFrames++;
    const bool web = sPendingCommand >= SUSAMUNE_GHOST_CMD_WEB_LIST;
    if(web && (response.flags&SUSAMUNE_GHOST_RESPONSE_BUSY)) {
        sStatus=response.generation==GHOST_WEB_STARTUP?"Starting Wii network...":
            response.generation==GHOST_WEB_DNS?"Finding Delfino Ghosts...":
            response.generation==GHOST_WEB_TCP?"Connecting to Delfino Ghosts...":
            response.generation==GHOST_WEB_TLS?"Securing connection...":
            response.generation==GHOST_WEB_VALIDATE?"Checking ghost data...":
            sPendingCommand==SUSAMUNE_GHOST_CMD_WEB_UPLOAD?"Uploading ghost...":"Receiving ghost data...";
    }
    if (!web && !sTimedOut && sWaitFrames > kTimeoutFrames) {
        sTimedOut = true;
        cancelFailedObserverLoad(sPendingLoadDestination);
        notify(kTimeout);
    }
}
#endif

#if IS_EMULATOR && TIMEWARP_LIVE_RACING
void pollResponse() {
    SusamuneGhostStorageResponse response;bool done;
    if(sPendingCommand>=SUSAMUNE_GHOST_CMD_WEB_UPLOAD){
        DolphinGhostAccount::update();done=DolphinGhostAccount::take(&response);
    }else{DolphinGhostLibrary::update();done=DolphinGhostLibrary::take(&response);}
    if(done)completeRequest(response);
}
#endif

__attribute__((noinline)) bool requestIdle() {
#if !IS_EMULATOR
    if (!transferReady()) { sStatus = kBusy; return false; }
#endif
    if (!sAvailable) {
        sStatus = IS_EMULATOR ? kDolphinUnavailable : kUnavailable;
        return false;
    }
    if (busy()) {
        sStatus = sTimedOut ? kTimeout : kBusy;
        return false;
    }
    return true;
}

__attribute__((noinline)) const SusamuneGhostSlotInfo *catalogEntry(
    bool imported, int slot) {
    if (!sReady[imported] || slot < 0 ||
        static_cast<u32>(slot) >= sPages[imported].count) return nullptr;
    return &sPages[imported].entries[slot].info;
}

bool copyLiteral(char *out, u32 size, const char *text, u32 length) {
    if (!out || size == 0) return false;
    const u32 count = length < size ? length : size - 1;
    if (count) memcpy(out, text, count);
    out[count] = '\0';
    return true;
}

bool copyVisibleName(char *out, u32 size, const char *text, u32 length) {
    for (u32 i = 0; i < length; i++)
        if (text[i] != ' ') return copyLiteral(out, size, text, length);
    return copyLiteral(out, size, kUnnamedName, sizeof(kUnnamedName) - 1);
}

__attribute__((noinline)) bool copyCatalogName(bool imported, int slot,
                                                char *out, u32 size) {
    if (!out || size == 0) return false;
    out[0] = '\0';
    const SusamuneGhostSlotInfo *info = catalogEntry(imported, slot);
    if (!info) return false;
    if (info->flags & SUSAMUNE_GHOST_SLOT_UNSAFE)
        return copyLiteral(out, size, kUnsafeName, sizeof(kUnsafeName) - 1);
    if (!(info->flags & SUSAMUNE_GHOST_SLOT_PRESENT))
        return copyLiteral(out, size, kEmptyName, sizeof(kEmptyName) - 1);
    return copyVisibleName(out, size, info->name, info->nameLength);
}

__attribute__((noinline)) bool requestIdentity(const Identity &identity,
    u16 command, const char *status, u8 destination = LOAD_DESTINATION_RACE) {
    observeProfile();
    if (!requestIdle()) return false;
    if (!identityValid(identity)) {
        sStatus = kBadSlot;
        return false;
    }
    if ((identity.flags & SUSAMUNE_GHOST_SLOT_UNSAFE) &&
        command != SUSAMUNE_GHOST_CMD_DELETE) {
        sStatus = kUnsafe;
        return false;
    }
    const bool imported = identity.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
    if (imported && (command == SUSAMUNE_GHOST_CMD_EXPORT || command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD)) {
        sStatus = kInvalidRequest;
        return false;
    }
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
    if (!claimTransfer()) { sStatus = kBusy; return false; }
    const bool upload=command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD;
    const u32 payloadSize = imported ? sizeof(identity.leaf) : upload ? sizeof(GhostServiceUpload) : 0;
    if (imported) {
        memcpy(transferPayload(), identity.leaf, payloadSize);
        DCFlushRange(transferPayload(), payloadSize);
    }
    if(upload) {
        memcpy(transferPayload(),&uploadDraft().upload,payloadSize);
        DCFlushRange(transferPayload(),payloadSize);
    }
    sPendingIdentity = identity;
    sPendingLoadDestination = destination;
    beginRequest(command, identity.profile, identity.id, payloadSize, 0,
                 status, 0, identity.generation);
    return true;
#else
    (void)status;
    (void)destination;
    return false;
#endif
}

__attribute__((noinline)) bool loadTrack(bool imported, int slot, u8 destination) {
    Identity identity;
    if (!copyIdentity(imported, slot, &identity)) {
        sStatus = kCatalogNeeded;
        return false;
    }
    return requestIdentity(identity, SUSAMUNE_GHOST_CMD_LOAD, kLoading, destination);
}

__attribute__((noinline)) bool requestPersonalCommand(int slot, u16 command,
                                                       const char *status) {
    Identity identity;
    if (!copyIdentity(false, slot, &identity)) {
        sStatus = kCatalogNeeded;
        return false;
    }
    return requestIdentity(identity, command, status);
}

}  // namespace

void init() {
    // Never abandon a live transfer through a second initialization call.
    if (!quiet()) return;
    memset(sPages, 0, 2 * kCatalogBytes);
    memset(&sPendingIdentity, 0, sizeof(sPendingIdentity));
    memset(&sLoadedIdentity, 0, sizeof(sLoadedIdentity));
    sSequence = sPendingSequence = sPendingRecordToken = sPendingDurationQf = 0;
    sWaitFrames = sPendingEpoch = sPendingSlot = 0;
    sEpoch = 1;
    sPendingCommand = SUSAMUNE_GHOST_CMD_NONE;
    sPendingProfile = 0;
    sPendingLoadDestination = LOAD_DESTINATION_RACE;
    sProfile = activeProfile();
    sOffsets[0] = sOffsets[1] = 0;
    sReady[0] = sReady[1] = sRefreshQueued[0] = sRefreshQueued[1] = false;
    sCachedRefresh[0] = sCachedRefresh[1] = false;
    sLoadedValid = sAvailable = sImportScanQueued = sTimedOut = false;
    sWebOpen = sWebReady = false;
    sStatus = IS_EMULATOR ? kDolphinUnavailable : kUnavailable;
#if !IS_EMULATOR
    if (transferReady()) {
        readBackend();
        sRefreshQueued[0] = sRefreshQueued[1] = sAvailable;
    }
#endif
}

const GhostServicePage *onlinePage() {
    return sWebOpen && sWebReady ? reinterpret_cast<const GhostServicePage *>(&sPages[1]) : nullptr;
}

bool browseOnline(bool nextPage, int level) {
#if !IS_EMULATOR
    if (!requestIdle()) return false;
    if (!sSharedBackend) { sStatus = "Update Moonshine launcher for online ghosts"; return false; }
    GhostServiceQuery query = {};
    const auto *current = onlinePage();
    query.filter=current ? current->reserved >> 8 : 0;
    if(level != -2) {
        if(level < -1 || level >= ILing::count())return false;
        query.filter=level<0?0:ILing::ghostBrowseFilter(level);nextPage=false;
    }
    if (nextPage) {
        const auto *page = onlinePage();
        if (!page || !page->next[0]) return false;
        memcpy(query.cursor, page->next, sizeof(query.cursor));
    }
    if (!claimTransfer()) { sStatus = kBusy; return false; }
    if(!sWebOpen){clearCatalog(true);sWebReady=false;}
    sWebOpen = true; sRefreshQueued[1] = sImportScanQueued = false;
    memcpy(transferPayload(), &query, sizeof(query));
    DCFlushRange(transferPayload(), sizeof(query));
    beginRequest(SUSAMUNE_GHOST_CMD_WEB_LIST, SUSAMUNE_GHOST_IMPORTED_PROFILE, 0,
        sizeof(query), 0, "Connecting to Delfino Ghosts...");
    return true;
#elif TIMEWARP_LIVE_RACING
    if(busy()) { sStatus=kBusy; return false; }
    GhostServiceQuery query={};const auto *current=onlinePage();
    query.filter=current?current->reserved>>8:0;
    if(level!=-2){
        if(level < -1 || level>=ILing::count())return false;
        query.filter=level<0?0:ILing::ghostBrowseFilter(level);nextPage=false;
    }
    if(nextPage){if(!current || !current->next[0])return false;memcpy(query.cursor,current->next,sizeof(query.cursor));}
    if(!DolphinGhostWeb::begin(query)){sStatus=kBusy;return false;}
    if(!sWebOpen){clearCatalog(true);sWebReady=false;}
    sWebOpen=true;sPendingCommand=SUSAMUNE_GHOST_CMD_WEB_LIST;
    sStatus="Connecting to Delfino Ghosts...";return true;
#else
    (void)nextPage; (void)level; sStatus = "Visit Delfino Ghosts on your PC"; return false;
#endif
}

bool downloadOnline(int row) {
#if !IS_EMULATOR
    const auto *page = onlinePage();
    if (!page || row < 0 || static_cast<u32>(row) >= page->count || !requestIdle()) return false;
    if (!claimTransfer()) { sStatus = kBusy; return false; }
    memcpy(transferPayload(), &page->entries[row], sizeof(GhostServiceEntry));
    DCFlushRange(transferPayload(), sizeof(GhostServiceEntry));
    beginRequest(SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD, SUSAMUNE_GHOST_IMPORTED_PROFILE, 0,
        sizeof(GhostServiceEntry), 0, "Downloading ghost...");
    return true;
#elif TIMEWARP_LIVE_RACING
    const auto *page=onlinePage();
    if(!page || row<0 || static_cast<u32>(row)>=page->count || busy())return false;
    if(!DolphinGhostWeb::download(page->entries[row])){sStatus=kBusy;return false;}
    sPendingCommand=SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD;sStatus="Downloading ghost...";return true;
#else
    (void)row; return false;
#endif
}
const GhostServiceAccountInfo *accountInfo(){return &sWebAccount;}
bool accountAction(unsigned action) {
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
    if(action>GHOST_ACCOUNT_UNLINK || !requestIdle())return false;
#if !IS_EMULATOR
    if(!sSharedBackend){sStatus="Update Moonshine launcher for online ghosts";return false;}
#endif
    if(!claimTransfer()){sStatus=kBusy;return false;}
    sRefreshQueued[0]=sRefreshQueued[1]=sImportScanQueued=false;
    beginRequest(SUSAMUNE_GHOST_CMD_WEB_ACCOUNT,SUSAMUNE_GHOST_IMPORTED_PROFILE,action,0,0,"Checking account...");
    return true;
#else
    (void)action;sStatus="Visit Delfino Ghosts on your PC";return false;
#endif
}
bool uploadOnline(const Identity &identity) {
    return requestIdentity(identity,SUSAMUNE_GHOST_CMD_WEB_UPLOAD,"Preparing upload...");
}
UploadDraft &uploadDraft() {
    // Upload and imported browsing are mutually exclusive modal pages.
    static_assert(sizeof(UploadDraft)<=sizeof(sPages[1]),"upload draft exceeds catalog cache");
    return *reinterpret_cast<UploadDraft *>(&sPages[1]);
}
bool beginUploadDraft() {
    if(busy())return false;
    sRefreshQueued[0]=sRefreshQueued[1]=sImportScanQueued=false;
    sReady[1]=sWebReady=sWebOpen=false;
    memset(&uploadDraft(),0,sizeof(UploadDraft));
    return true;
}

void closeOnline() {
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
    if(sPendingCommand<SUSAMUNE_GHOST_CMD_WEB_UPLOAD)DolphinGhostWeb::close();
#endif
    sWebOpen = sWebReady = false;
    clearCatalog(true); sRefreshQueued[1] = sAvailable; sImportScanQueued = true;
#if !IS_EMULATOR
    if (sTransferPhase == TRANSFER_REMOTE &&
        sPendingCommand >= SUSAMUNE_GHOST_CMD_WEB_LIST)
        TransferLease::cancel(sTransferToken);
#endif
}

void update() {
    GhostRecording::poll();
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
    if(!sAvailable && DolphinGhostLibrary::ready()){sAvailable=true;sRefreshQueued[0]=sRefreshQueued[1]=true;sImportScanQueued=true;}
    if(sPendingCommand==SUSAMUNE_GHOST_CMD_WEB_LIST || sPendingCommand==SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD){
        const bool downloading=sPendingCommand==SUSAMUNE_GHOST_CMD_WEB_DOWNLOAD;
        DolphinGhostWeb::update();
        auto *page=reinterpret_cast<GhostServicePage *>(&sPages[1]);
        const int result=DolphinGhostWeb::take(page);
        if(result==1){
            const unsigned phase=DolphinGhostWeb::phase();
            sStatus=phase==GHOST_WEB_VALIDATE?"Saving downloaded ghost...":
                phase==GHOST_WEB_DNS?"Finding Delfino Ghosts...":
                phase==GHOST_WEB_TCP?"Connecting to Delfino Ghosts...":
                phase==GHOST_WEB_TLS?"Securing connection...":"Starting network...";
        }else{
            sPendingCommand=SUSAMUNE_GHOST_CMD_NONE;
            if(sWebOpen && downloading){sStatus=result?statusForCode(result):"Downloaded - available in Imported ghosts";}
            else if(sWebOpen){sWebReady=!result;sStatus=result?webStatus(result):
                page->count?"Select a ghost to download":"No compatible ghosts found";}
        }
        return;
    }
#endif
#if !IS_EMULATOR
    if (!transferReady()) return;
    if (sTransferPhase == TRANSFER_CONSUME || sTransferPhase == TRANSFER_RELEASE) {
        finishTransfer();
        return;
    }
    if (sTransferPhase == TRANSFER_LOCAL || sTransferPhase == TRANSFER_READING) return;
    submitTransfer();
#endif
    const GhostTraceShare::Result exporting=GhostTraceShare::poll();
    if(exporting==GhostTraceShare::RUNNING){sStatus="Exporting MSGT recording...";return;}
    if(exporting==GhostTraceShare::SAVED){notify(kExportedShare);return;}
    if(exporting==GhostTraceShare::FAILED){notify(kExportFailed);return;}
    observeProfile();
    observeLoadedPlayback();
    if (sPendingCommand != SUSAMUNE_GHOST_CMD_NONE) {
        if (sPendingCommand == SUSAMUNE_GHOST_CMD_LOAD &&
            observerLoadDestination(sPendingLoadDestination) &&
            !Ghost::observerPreparing() && sPendingEpoch == sEpoch) {
            if (++sEpoch == 0) sEpoch++;
        }
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
        pollResponse();
#endif
        return;
    }
    unsigned queuedToken=0;
    if (GhostRecording::takeQueuedSave(sProfile, queuedToken)) {
        if (!saveNew(queuedToken)) notify(sStatus);
        return;
    }
    if (GhostRecording::queuedSave()) { sStatus=kSaving;return; }
    for (int imported = 0; imported < 2; imported++) {
        if (imported && sWebOpen) continue;
        if (!sRefreshQueued[imported]) continue;
        const u16 command = imported && sImportScanQueued
            ? SUSAMUNE_GHOST_CMD_IMPORT_SCAN : SUSAMUNE_GHOST_CMD_LIST;
        const bool cached = sCachedRefresh[imported];
        if (beginRefresh(imported != 0, command, cached)) {
            sRefreshQueued[imported] = false;
            sCachedRefresh[imported] = false;
            if (imported) sImportScanQueued = false;
        }
        return;
    }
}

void onSavestateLoaded() {
    if (++sEpoch == 0) sEpoch++;
    observeLoadedPlayback();
    if (sPendingCommand == SUSAMUNE_GHOST_CMD_LOAD) {
        cancelFailedObserverLoad(sPendingLoadDestination);
        sStatus = kLoadIgnored;
    }
}

bool refreshPage(bool imported, u32 offset) {
    observeProfile();
    if (!sAvailable) {
        sStatus = IS_EMULATOR ? kDolphinUnavailable : kUnavailable;
        return false;
    }
    if (offset % SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES != 0) {
        sStatus = kBadSlot;
        return false;
    }
    const bool cached = offset != sOffsets[imported] &&
        (!sRefreshQueued[imported] || sCachedRefresh[imported]);
    sOffsets[imported] = offset;
    if (imported) sImportScanQueued = false;
    clearCatalog(imported);
    sRefreshQueued[imported] = true;
    sCachedRefresh[imported] = cached;
    if (busy()) return true;
    if (beginRefresh(imported, SUSAMUNE_GHOST_CMD_LIST, cached)) {
        sRefreshQueued[imported] = false;
        sCachedRefresh[imported] = false;
    }
    return true;
}

bool refresh() { return refreshPage(false, sOffsets[0]); }
bool refreshImported() { return requestImportedRefresh(SUSAMUNE_GHOST_CMD_LIST); }
bool scanImports() { return requestImportedRefresh(SUSAMUNE_GHOST_CMD_IMPORT_SCAN); }

bool identityValid(const Identity &identity) {
    const bool imported = identity.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE;
    const u16 knownFlags = SUSAMUNE_GHOST_SLOT_PRESENT |
        SUSAMUNE_GHOST_SLOT_UNSAFE | SUSAMUNE_GHOST_SLOT_IMPORTED | SUSAMUNE_GHOST_SLOT_STREAMED;
    if (identity.id == SUSAMUNE_GHOST_SLOT_AUTO ||
        identity.region >= SUSAMUNE_GHOST_REGION_COUNT ||
        (identity.flags & ~knownFlags) != 0 ||
        !(identity.flags & (SUSAMUNE_GHOST_SLOT_PRESENT | SUSAMUNE_GHOST_SLOT_UNSAFE)) ||
        !zeroBytes(identity.reserved, sizeof(identity.reserved)) ||
        !safeText(identity.name, sizeof(identity.name), identity.nameLength, false))
        return false;
    if (imported)
        return (identity.flags & SUSAMUNE_GHOST_SLOT_IMPORTED) && validLeaf(identity.leaf);
    return identity.profile == activeProfile() && identity.region == kRegion &&
        !(identity.flags & SUSAMUNE_GHOST_SLOT_IMPORTED) &&
        zeroBytes(identity.leaf, sizeof(identity.leaf));
}

bool sameIdentity(const Identity &a, const Identity &b) {
    if (a.profile != b.profile || a.region != b.region) return false;
    return a.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE
        ? memcmp(a.leaf, b.leaf, sizeof(a.leaf)) == 0 : a.id == b.id;
}

bool copyIdentity(bool imported, int row, Identity *out) {
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    out->id = SUSAMUNE_GHOST_SLOT_AUTO;
    observeProfile();
    const SusamuneGhostSlotInfo *info = catalogEntry(imported, row);
    if (!info) return false;
    const SusamuneGhostCatalogEntry &entry = sPages[imported].entries[row];
    out->id = entry.id;
    out->generation = info->generation;
    out->flags = info->flags;
    out->profile = imported ? SUSAMUNE_GHOST_IMPORTED_PROFILE : sProfile;
    out->region = imported && !(info->flags & SUSAMUNE_GHOST_SLOT_UNSAFE)
        ? info->region : kRegion;
    out->nameLength = info->nameLength;
    memcpy(out->name, info->name, sizeof(out->name));
    memcpy(out->leaf, entry.leaf, sizeof(out->leaf));
    return identityValid(*out);
}

bool copyIdentityName(const Identity &identity, char *out, u32 size) {
    if (!out || !size) return false;
    out[0] = '\0';
    if (!identityValid(identity)) return false;
    if (identity.flags & SUSAMUNE_GHOST_SLOT_UNSAFE)
        return copyLiteral(out, size, kUnsafeName, sizeof(kUnsafeName) - 1);
    return copyVisibleName(out, size, identity.name, identity.nameLength);
}

bool isLoaded(const Identity &identity) {
    return sLoadedValid && Ghost::playbackPinned() &&
           sameIdentity(identity, sLoadedIdentity) &&
           identity.generation == sLoadedIdentity.generation;
}

bool saveNew(u32 expectedSelectionToken) {
    observeProfile();
    if (!requestIdle()) return false;
    if (GhostRecording::ownsSession() && !GhostRecording::selectForSave(expectedSelectionToken)) {
        sStatus = kSaveChanged; return false;
    }
    if (!Ghost::hasSaveableTrack()) { sStatus = kNoRecording; return false; }
#if !IS_EMULATOR || TIMEWARP_LIVE_RACING
    if (expectedSelectionToken) {
        char currentName[SUSAMUNE_GHOST_NAME_SIZE];
        u32 currentToken = 0;
        if (!Ghost::copySaveableName(currentName, sizeof(currentName), &currentToken) ||
            currentToken != expectedSelectionToken) {
            sStatus = kSaveChanged;
            return false;
        }
    }
    if (GhostRecording::ownsSession() && GhostRecording::selectionPending()) {
        char name[48];unsigned token=0;
        if (!GhostRecording::copySelection(name,sizeof(name),&token) ||
            !GhostRecording::queueSave(token,sProfile)) { sStatus=kSaveChanged;return false; }
        sStatus=kSaving;return true;
    }
    if (!claimTransfer()) { sStatus = kBusy; return false; }
    u32 size = 0, recordToken = 0;
    unsigned streamSelection=0,streamOwner=0;
    bool prepared;
    if (GhostRecording::ownsSession()) {
        prepared=GhostRecording::exportManifest(transferPayload(),sProfile,ILing::pbProfileName(ILing::pbProfile()),&streamOwner,&streamSelection);
        size=MS_RECORDING_MANIFEST_BYTES;recordToken=streamOwner;
    } else prepared=Ghost::exportLatest(transferPayload(),
            SUSAMUNE_GHOST_STORAGE_PAYLOAD_SIZE, sProfile, ILing::pbProfileName(ILing::pbProfile()),
            &size, &recordToken);
    if (!prepared || size < SUSAMUNE_GHOST_FILE_HEADER_SIZE ||
            size > SUSAMUNE_GHOST_MAX_FILE_SIZE) {
        sStatus = kExportFailed;
#if !IS_EMULATOR
        if (sTransferPhase == TRANSFER_LOCAL) {
            sTransferPhase = TRANSFER_RELEASE;
            finishTransfer();
        }
#endif
        return false;
    }
    DCFlushRange(transferPayload(), size);
    const SusamuneGhostFileHeader *header = reinterpret_cast<const SusamuneGhostFileHeader *>(
        transferPayload());
    u32 sequence=sSequence+1;if(!sequence)++sequence;
    if (streamSelection && !GhostRecording::publicationStarted(streamSelection,sequence)) {
        sStatus=kSaveChanged;
#if !IS_EMULATOR
        if (sTransferPhase==TRANSFER_LOCAL){sTransferPhase=TRANSFER_RELEASE;finishTransfer();}
#endif
        return false;
    }
    beginRequest(SUSAMUNE_GHOST_CMD_SAVE, sProfile, SUSAMUNE_GHOST_SLOT_AUTO,
                 size, recordToken, kSaving, header->durationQf);
    if (streamSelection && (sPendingCommand!=SUSAMUNE_GHOST_CMD_SAVE || sPendingSequence!=sequence)) {
        GhostRecording::publicationResult(sequence,false);return false;
    }
    return true;
#else
    (void)expectedSelectionToken;
    return false;
#endif
}

// Occupied page rows must never become overwrite requests.
bool save(int slot) { return save(slot, 0); }
bool save(int slot, u32 token) {
    if (slot != -1) { sStatus = kOccupied; return false; }
    return saveNew(token);
}
bool load(const Identity &identity) {
    return requestIdentity(identity, SUSAMUNE_GHOST_CMD_LOAD, kLoading);
}
bool loadObserver(const Identity &identity, bool secondary) {
    return requestIdentity(identity, SUSAMUNE_GHOST_CMD_LOAD, kLoading,
        secondary ? LOAD_DESTINATION_OBSERVER_SECONDARY : LOAD_DESTINATION_OBSERVER_PRIMARY);
}
bool remove(const Identity &identity) {
    return requestIdentity(identity, SUSAMUNE_GHOST_CMD_DELETE, kDeleting);
}
bool exportShare(const Identity &identity) {
#if IS_EMULATOR
    (void)identity;
    sStatus = "Close Dolphin; use manage_data.py export-ghost";
    return false;
#else
    if(identity.profile==SUSAMUNE_GHOST_IMPORTED_PROFILE){sStatus=kInvalidRequest;return false;}
    if(identity.flags&SUSAMUNE_GHOST_SLOT_STREAMED)
        return requestIdentity(identity,SUSAMUNE_GHOST_CMD_LOAD,"Preparing MSGT export...",LOAD_DESTINATION_EXPORT);
    return requestIdentity(identity, SUSAMUNE_GHOST_CMD_EXPORT, kExportingShare);
#endif
}
bool load(int slot) { return loadTrack(false, slot, LOAD_DESTINATION_RACE); }
bool loadObserver(int slot, bool secondary) {
    return loadTrack(false, slot,
        secondary ? LOAD_DESTINATION_OBSERVER_SECONDARY : LOAD_DESTINATION_OBSERVER_PRIMARY);
}
bool remove(int slot) {
    return requestPersonalCommand(slot, SUSAMUNE_GHOST_CMD_DELETE, kDeleting);
}
bool exportShare(int slot) {
    Identity identity;
    if (!copyIdentity(false, slot, &identity)) { sStatus = kCatalogNeeded; return false; }
    return exportShare(identity);
}

bool importShare(int slot) { (void)slot; return scanImports(); }
bool loadImported(int slot) { return loadTrack(true, slot, LOAD_DESTINATION_RACE); }
bool loadImportedObserver(int slot, bool secondary) {
    return loadTrack(true, slot,
        secondary ? LOAD_DESTINATION_OBSERVER_SECONDARY : LOAD_DESTINATION_OBSERVER_PRIMARY);
}
bool removeImported(int slot) {
    Identity identity;
    if (!copyIdentity(true, slot, &identity)) { sStatus = kCatalogNeeded; return false; }
    return remove(identity);
}
bool busy() {
    if (GhostRecordingNative::watchWaiting() || GhostRecordingNative::fileBusy() || GhostRecording::queuedSave() || GhostTraceShare::busy() || GhostTraceFlat::active()) return true;
#if !IS_EMULATOR
    if (sTransferPhase != TRANSFER_NONE || sTransferFailed) return true;
#endif
    return sPendingCommand != SUSAMUNE_GHOST_CMD_NONE;
}
bool quiet() { return !busy(); }
bool timedOut() { return busy() && sTimedOut; }
bool available() { return sAvailable; }
bool catalogReady() { return sReady[0]; }
bool importedCatalogReady() { return sReady[1]; }
int profile() { return sProfile; }
u32 pageOffset(bool imported) { return sOffsets[imported]; }
u32 pageCount(bool imported) { return sReady[imported] ? sPages[imported].count : 0; }
u32 totalCount(bool imported) { return sReady[imported] ? sPages[imported].totalCount : 0; }
int loadedSlot() {
    return sLoadedValid && sLoadedIdentity.profile == sProfile && Ghost::playbackPinned() &&
        sLoadedIdentity.id <= 0x7fffffffu ? static_cast<int>(sLoadedIdentity.id) : -1;
}
bool loadedImported() {
    return sLoadedValid && sLoadedIdentity.profile == SUSAMUNE_GHOST_IMPORTED_PROFILE &&
        Ghost::playbackPinned();
}
int loadedImportedSlot() {
    return loadedImported() && sLoadedIdentity.id <= 0x7fffffffu
        ? static_cast<int>(sLoadedIdentity.id) : -1;
}
u64 totalDurationQf() {
    return sReady[0] ? (static_cast<u64>(sPages[0].totalDurationQfHi) << 32) |
        sPages[0].totalDurationQfLo : 0;
}
u64 importedTotalDurationQf() {
    return sReady[1] ? (static_cast<u64>(sPages[1].totalDurationQfHi) << 32) |
        sPages[1].totalDurationQfLo : 0;
}
u32 importedOverflowCount() { return 0; }
const char *statusText() { return sStatus; }
bool copySlotName(int slot, char *out, u32 size) {
    return copyCatalogName(false, slot, out, size);
}
bool copyImportedSlotName(int slot, char *out, u32 size) {
    return copyCatalogName(true, slot, out, size);
}
const SusamuneGhostSlotInfo *slot(int slot) { return catalogEntry(false, slot); }
const SusamuneGhostSlotInfo *importedSlot(int slot) { return catalogEntry(true, slot); }

}  // namespace GhostStorage
