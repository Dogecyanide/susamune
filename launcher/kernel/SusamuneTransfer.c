#include "SusamuneTransfer.h"
#include "SusamuneGhost.h"
#include "SusamuneStateStorage.h"
#include "DI.h"
#include "susamune/transfer_publication.h"
#include "susamune/mod_bin.h"
#include "string.h"

extern u32 GAME_ID;
#ifndef TRANSFER_WIRE
#define TRANSFER_WIRE SUSAMUNE_TRANSFER_PHYS_PTR
#endif
enum { TRANSFER_OFF, TRANSFER_LEGACY, TRANSFER_ACTIVATING,
       TRANSFER_SHARED, TRANSFER_RETIRING, TRANSFER_FAILED };
static TWLeaseArm Arm;
static TWLeaseControl Control;
static TWLeasePublisher Publisher;
static u32 Mode, ActivationMask;
static bool SharedMap, Dispatching;

static unsigned int LoadWord(const volatile unsigned int *word) { return *word; }
static void StoreWord(volatile unsigned int *word, unsigned int value) { *word = value; }
static void Flush(volatile void *line, unsigned int size) { sync_after_write((void *)line, size); }
static void Invalidate(volatile void *line, unsigned int size) { sync_before_read((void *)line, size); }
static void Barrier(void) { __asm__ volatile("" ::: "memory"); }
static const TWLeasePublicationIo PublicationIo = {LoadWord, StoreWord, Flush, Invalidate, Barrier};

static bool Publish(void)
{
    if (TWLeasePublicationWrite(&Publisher, &TRANSFER_WIRE->response,
            &TRANSFER_WIRE->responsePublication, &Control.response, &PublicationIo)) return true;
    Mode = TRANSFER_FAILED;
    return false;
}

static bool ReadRequest(void)
{
    return TWLeasePublicationRead(&Control.request, &TRANSFER_WIRE->request,
        &TRANSFER_WIRE->requestPublication, &PublicationIo);
}

bool SusamuneTransferActive(void) { return SharedMap; }
u8 *SusamuneTransferStageBase(void) { return (u8 *)SUSAMUNE_TRANSFER_STAGE_PHYS_BASE; }
u32 SusamuneTransferStageSize(void)
{
    return SharedMap ? SUSAMUNE_TRANSFER_STAGE_SIZE : SUSAMUNE_STATE_STAGING_SIZE;
}
u8 *SusamuneTransferGhostBase(void)
{
    return (u8 *)(SharedMap ? SUSAMUNE_TRANSFER_STAGE_PHYS_BASE : SUSAMUNE_GHOST_FILE_TRANSFER_PHYS_BASE);
}
u32 SusamuneTransferPoolSize(void)
{
    return SharedMap ? SUSAMUNE_TRANSFER_POOL_SIZE : SUSAMUNE_STATE_POOL_EXPANDED_SIZE;
}
u8 *SusamuneTransferPoolPiece(u32 offset, u32 *size)
{
    u32 base, capacity;
    if (offset >= SusamuneTransferPoolSize()) { *size = 0; return NULL; }
    if (offset < SUSAMUNE_STATE_POOL_SIZE) {
        base = SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE; capacity = SUSAMUNE_STATE_POOL_SIZE;
    } else {
        offset -= SUSAMUNE_STATE_POOL_SIZE;
        if (offset < SUSAMUNE_STATE_POOL_EXTRA_SIZE) {
            base = SUSAMUNE_STATE_POOL_EXTRA_PHYS_BASE; capacity = SUSAMUNE_STATE_POOL_EXTRA_SIZE;
        } else {
            offset -= SUSAMUNE_STATE_POOL_EXTRA_SIZE;
            if (offset < SUSAMUNE_TRANSFER_POOL_THIRD_SIZE) {
                base = SUSAMUNE_TRANSFER_POOL_THIRD_PHYS_BASE; capacity = SUSAMUNE_TRANSFER_POOL_THIRD_SIZE;
            } else {
                offset -= SUSAMUNE_TRANSFER_POOL_THIRD_SIZE;
                if (offset < SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE) {
                    base = SUSAMUNE_TRANSFER_POOL_FOURTH_PHYS_BASE; capacity = SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE;
                } else {
                    offset -= SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE;
                    base = SUSAMUNE_TRANSFER_POOL_FIFTH_PHYS_BASE; capacity = SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE;
                }
            }
        }
    }
    if (*size > capacity - offset) *size = capacity - offset;
    return (u8 *)(base + offset);
}
bool SusamuneTransferPoolRange(u32 offset, u32 size)
{
    u32 capacity = SusamuneTransferPoolSize();
    return size && offset <= capacity && size <= capacity - offset;
}
bool SusamuneTransferImportRange(u32 offset, u32 size)
{
    u32 capacity = SusamuneTransferPoolSize(), stage = SusamuneTransferStageSize();
    return size && size <= capacity && offset <= capacity &&
        (size <= stage || size - stage <= capacity - offset);
}
bool SusamuneTransferWindowRange(u32 packed, u32 offset, u32 size)
{
    return packed && packed <= SusamuneTransferPoolSize() && size &&
        size <= SusamuneTransferStageSize() && offset <= packed && size <= packed - offset;
}

bool SusamuneTransferAllows(u32 owner, u32 seq, u32 session, u32 command)
{
    if (Mode == TRANSFER_OFF || Mode == TRANSFER_LEGACY) return true;
    return Mode == TRANSFER_SHARED && Dispatching && Arm.busy && Arm.key.owner == owner &&
        Arm.key.seq == seq && Arm.key.session == session && Arm.key.command == command;
}
bool SusamuneTransferCancelled(u32 owner)
{
    return Mode == TRANSFER_SHARED && Arm.key.owner == owner && TWLeaseCancelRequested(&Arm, &Control);
}
bool SusamuneTransferRetireFailed(void)
{
    return Mode == TRANSFER_FAILED || SusamuneGhostRetireFailed() || SusamuneStateStorageRetireFailed();
}

void SusamuneTransferBeginRetire(void)
{
    if (Mode == TRANSFER_OFF || Mode == TRANSFER_RETIRING || Mode == TRANSFER_FAILED) return;
    Mode = TRANSFER_RETIRING; Dispatching = false;
    TWLeaseResetBegin(&Arm, &Control);
    Publish();
}
bool SusamuneTransferRetireStep(void)
{
    if (Mode == TRANSFER_OFF) return true;
    if (Mode != TRANSFER_RETIRING || SusamuneTransferRetireFailed()) return false;
    if (Arm.resetMask & 1u) {
        if (SusamuneGhostRetire()) TWLeaseRetired(&Arm, TW_OWNER_GHOST, 1);
    } else if (Arm.resetMask & 2u) {
        if (SusamuneStateStorageRetire()) TWLeaseRetired(&Arm, TW_OWNER_STATE, 1);
    }
    return !Arm.resetMask && !SusamuneTransferRetireFailed();
}
bool SusamuneTransferResumeLegacy(void)
{
    if (Mode == TRANSFER_OFF) return true;
    if (Mode != TRANSFER_RETIRING || SusamuneTransferRetireFailed() ||
        !SusamuneGhostQuiescent() || !SusamuneStateStorageQuiescent() ||
        !TWLeaseResetPublish(&Arm, &Control)) return false;
    SharedMap = false;
    SusamuneGhostInit(); SusamuneStateStorageInit();
    Mode = TRANSFER_LEGACY;
    return Publish();
}
void SusamuneTransferInit(void)
{
    if (Mode != TRANSFER_OFF || SUSAMUNE_MOD_REGION_TAG(GAME_ID) == NULL) return;
    memset((void *)TRANSFER_WIRE, 0, sizeof(*TRANSFER_WIRE));
    sync_after_write((void *)TRANSFER_WIRE, sizeof(*TRANSFER_WIRE));
    Mode = TRANSFER_RETIRING;
    TWLeaseResetBegin(&Arm, &Control);
    if (!SusamuneGhostQuiescent() || !SusamuneStateStorageQuiescent()) { Mode = TRANSFER_FAILED; return; }
    TWLeaseRetired(&Arm, TW_OWNER_GHOST, 1); TWLeaseRetired(&Arm, TW_OWNER_STATE, 1);
    if (!TWLeaseResetPublish(&Arm, &Control)) { Mode = TRANSFER_FAILED; return; }
    Mode = TRANSFER_LEGACY;
    Publish();
}

static bool ActivationRequest(void)
{
    return Control.request.phase == TW_WIRE_ACTIVATE &&
        Control.request.command == SUSAMUNE_TRANSFER_RUNTIME_ABI && TWLeaseSame(&Arm.key, &Control.request);
}
static bool RequestReady(void)
{
    const TWLeaseLine *q = &Control.request;
    if (q->owner == TW_OWNER_GHOST)
        return !q->session && q->phase != TW_WIRE_CANCEL && SusamuneGhostRequestReady(q->seq, q->command);
    if (q->owner == TW_OWNER_STATE)
        return SusamuneStateStorageRequestReady(q->seq, q->session, q->command);
    return false;
}
static void Complete(void)
{
    TWLeaseToken token;
    bool receipt;
    if (!Arm.busy || !SusamuneGhostQuiescent() || !SusamuneStateStorageQuiescent()) return;
    receipt = Arm.key.owner == TW_OWNER_GHOST ? SusamuneGhostReceiptReady(Arm.key.seq, Arm.key.command) :
        SusamuneStateStorageReceiptReady(Arm.key.seq, Arm.key.session, Arm.key.command);
    token.epoch = Arm.key.epoch; token.ticket = Arm.key.ticket;
    if (TWLeaseFinish(&Arm, &Control, token, 1, 1, receipt)) Publish();
}
bool SusamuneTransferPending(void)
{
    if (Mode == TRANSFER_ACTIVATING || (Mode == TRANSFER_SHARED && Arm.busy)) return true;
    if (Mode != TRANSFER_LEGACY && Mode != TRANSFER_SHARED) return false;
    if (!ReadRequest()) return false;
    if (Mode == TRANSFER_LEGACY) return ActivationRequest();
    return Control.request.magic == TW_LEASE_MAGIC && Control.request.epoch == Arm.epoch && Control.request.ticket > Arm.lastTicket &&
        (Control.request.phase == TW_WIRE_ARM || Control.request.phase == TW_WIRE_CANCEL) && RequestReady();
}
void SusamuneTransferService(void)
{
    if (Mode == TRANSFER_LEGACY) {
        if (!ReadRequest() || !ActivationRequest()) return;
        Mode = TRANSFER_ACTIVATING; ActivationMask = 3;
    }
    if (Mode == TRANSFER_ACTIVATING) {
        if (SusamuneTransferRetireFailed()) { Mode = TRANSFER_FAILED; return; }
        if (ActivationMask & 1u) { if (SusamuneGhostRetire()) ActivationMask &= ~1u; return; }
        if (ActivationMask & 2u) { if (SusamuneStateStorageRetire()) ActivationMask &= ~2u; return; }
        if (!ReadRequest() || !ActivationRequest() || !DIReserveScratchTail()) return;
        // No worker retains the old staging/payload ranges after retirement.
        sync_after_write((void *)SUSAMUNE_TRANSFER_POOL_THIRD_PHYS_BASE, SUSAMUNE_TRANSFER_POOL_THIRD_SIZE);
        sync_before_read((void *)SUSAMUNE_TRANSFER_POOL_THIRD_PHYS_BASE, SUSAMUNE_TRANSFER_POOL_THIRD_SIZE);
        sync_after_write((void *)SUSAMUNE_TRANSFER_POOL_FOURTH_PHYS_BASE, SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE);
        sync_before_read((void *)SUSAMUNE_TRANSFER_POOL_FOURTH_PHYS_BASE, SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE);
        if (!TWLeaseActivate(&Arm, &Control, SusamuneGhostQuiescent(), SusamuneStateStorageQuiescent())) return;
        SharedMap = true;
        SusamuneGhostInit(); SusamuneStateStorageInit();
        Mode = TRANSFER_SHARED;
        Publish();
        return;
    }
    if (Mode != TRANSFER_SHARED) return;
    if (SusamuneTransferRetireFailed()) { Mode = TRANSFER_FAILED; return; }
    ReadRequest();
    if (!Arm.busy) {
        if (!RequestReady() || !TWLeaseStart(&Arm, &Control, Control.request.owner,
                Control.request.seq, Control.request.session, Control.request.command)) return;
    }
    Dispatching = true;
    if (Arm.key.owner == TW_OWNER_GHOST) SusamuneGhostService();
    else SusamuneStateStorageService();
    Dispatching = false;
    Complete();
}
