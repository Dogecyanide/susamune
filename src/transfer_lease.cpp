#include "susamune/transfer_lease.hxx"
#include "susamune/transfer_publication.h"
#include "susamune/transfer_layout.h"
#include "susamune/state_storage.h"
#include <Dolphin/OS.h>

namespace TransferLease {
namespace {
TWLeasePpc sPpc;
[[maybe_unused]] TWLeaseControl sControl;
[[maybe_unused]] TWLeasePublisher sPublisher;
Mode sMode;
unsigned int sOwner;
bool sShared;

class Guard {
    bool enabled;
public:
    Guard() : enabled(OSDisableInterrupts()) {}
    ~Guard() { OSRestoreInterrupts(enabled); }
};

#if !IS_EMULATOR
#ifndef SUSAMUNE_TRANSFER_CLIENT_WIRE
#define SUSAMUNE_TRANSFER_CLIENT_WIRE SUSAMUNE_TRANSFER_PPC_PTR
#endif
volatile TWLeaseControl *wire() { return SUSAMUNE_TRANSFER_CLIENT_WIRE; }
unsigned int load(const volatile unsigned int *word) { return *word; }
void store(volatile unsigned int *word, unsigned int value) { *word = value; }
void flush(volatile void *line, unsigned int size) { DCFlushRange((void *)line, size); }
void invalidate(volatile void *line, unsigned int size) { DCInvalidateRange((void *)line, size); }
void barrier() {
#if defined(__powerpc__)
    __asm__ volatile("sync" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}
const TWLeasePublicationIo kIo = {load, store, flush, invalidate, barrier};

bool read() {
    return TWLeasePublicationRead(&sControl.response, &wire()->response,
        &wire()->responsePublication, &kIo);
}
bool capable() {
    const TWLeaseLine &r = sControl.response;
    return r.magic == TW_LEASE_MAGIC && r.epoch && r.phase == TW_WIRE_CAPABLE &&
        !r.ticket && !r.owner && !r.seq && !r.session &&
        r.command == SUSAMUNE_TRANSFER_RUNTIME_ABI;
}
bool writable() {
    if (sPublisher.issued != 0xffffffffu) return true;
    sMode = FAILED;
    return false;
}
bool publish() {
    if (TWLeasePublicationWrite(&sPublisher, &wire()->request,
        &wire()->requestPublication, &sControl.request, &kIo)) return true;
    sMode = FAILED;
    return false;
}
bool current() {
    if (!read()) return false;
    if (sControl.response.magic != TW_LEASE_MAGIC ||
        sControl.response.epoch != sPpc.key.epoch ||
        (sControl.response.phase != TW_WIRE_READY && sControl.response.phase != TW_WIRE_DONE)) {
        sMode = FAILED;
        return false;
    }
    return true;
}
#endif

TWLeaseToken key(const Token &token) { return {token.epoch, token.ticket}; }
bool held(const Token &token) {
    return sMode == SHARED && token.owner == sOwner && TWLeaseOwned(&sPpc, key(token));
}
}

Mode init() {
    Guard guard;
    if (sMode != UNINITIALIZED) return sMode;
#if IS_EMULATOR
    sMode = UNAVAILABLE;
#else
    if (!TWLeasePublicationResume(&sPublisher, &wire()->requestPublication, &kIo)) {
        sMode = FAILED;
        return sMode;
    }
    if (!read()) {
        invalidate(&wire()->responsePublication, 32); barrier();
        sMode = wire()->responsePublication.generation || wire()->responsePublication.issued ||
            sPublisher.issued ? FAILED : LEGACY;
        return sMode;
    }
    sMode = capable() ? CAPABLE : FAILED;
#endif
    return sMode;
}
Mode mode() { Guard guard; return sMode; }
bool legacyAllowed() { Guard guard; return sMode == LEGACY || sMode == CAPABLE; }
bool sharedMap() { Guard guard; return sShared; }

bool activate(bool ghostQuiet, bool stateQuiet, bool localQuiet) {
    Guard guard;
#if !IS_EMULATOR
    if (sMode != CAPABLE || !ghostQuiet || !stateQuiet || !localQuiet || !read()) return false;
    if (!capable()) { sMode = FAILED; return false; }
    if (!writable() || !TWLeaseAttach(&sPpc, &sControl)) return false;
    sMode = ACTIVATING;
    return publish();
#else
    (void)ghostQuiet; (void)stateQuiet; (void)localQuiet;
    return false;
#endif
}
void poll() {
    Guard guard;
#if !IS_EMULATOR
    if ((sMode != ACTIVATING && sMode != SHARED) || !read()) return;
    const TWLeaseLine &r = sControl.response;
    if (r.magic != TW_LEASE_MAGIC || r.epoch != sPpc.key.epoch || r.phase == TW_WIRE_DRAINING) {
        sMode = FAILED;
        return;
    }
    if (sMode == ACTIVATING) {
        if (TWLeaseAttached(&sPpc, &sControl)) {
            // All prior writers retired before READY; do this once per epoch.
            DCInvalidateRange(reinterpret_cast<void *>(SUSAMUNE_TRANSFER_POOL_THIRD_PPC_BASE),
                              SUSAMUNE_TRANSFER_POOL_THIRD_SIZE);
            DCInvalidateRange(reinterpret_cast<void *>(SUSAMUNE_TRANSFER_POOL_FOURTH_PPC_BASE),
                              SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE);
            DCInvalidateRange(reinterpret_cast<void *>(SUSAMUNE_TRANSFER_POOL_FIFTH_PPC_BASE),
                              SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE);
            sShared = true; sMode = SHARED;
        }
        else if (!capable() || !TWLeaseSame(&sPpc.key, &r)) sMode = FAILED;
    } else if (r.phase != TW_WIRE_READY && r.phase != TW_WIRE_DONE) sMode = FAILED;
    else TWLeasePoll(&sPpc, &sControl);
#endif
}
bool claim(Owner owner, Token &token) {
    Guard guard;
    token = {};
#if !IS_EMULATOR
    TWLeaseToken raw;
    if (sMode != SHARED || owner < GHOST || owner > CODEC || !current() || !writable() ||
        !TWLeaseClaim(&sPpc, &sControl, owner == GHOST ? TW_OWNER_GHOST : TW_OWNER_STATE, &raw)) return false;
    sOwner = owner;
    if (!publish()) return false;
    token = {raw.epoch, raw.ticket, sOwner};
    return true;
#else
    (void)owner;
    return false;
#endif
}
bool owns(const Token &token) { Guard guard; return held(token); }
bool submit(const Token &token, unsigned int seq, unsigned int session, unsigned int command) {
    Guard guard;
#if !IS_EMULATOR
    if (!held(token) || sOwner == CODEC || (sOwner == GHOST && session) ||
        !current() || !writable() || !TWLeaseSubmit(&sPpc, &sControl, key(token), seq, session, command)) return false;
    return publish();
#else
    (void)token; (void)seq; (void)session; (void)command;
    return false;
#endif
}
bool cancel(const Token &token) {
    Guard guard;
#if !IS_EMULATOR
    const unsigned int command = sPpc.key.command;
    const bool cancellable = sOwner == STATE &&
        ((command >= SUSAMUNE_STATE_CMD_EXPORT && command <= SUSAMUNE_STATE_CMD_CANCEL) ||
         command == SUSAMUNE_STATE_CMD_READ_WINDOW);
    if (!held(token) || !current() || !writable() ||
        !TWLeaseCancel(&sPpc, &sControl, key(token), cancellable)) return false;
    return publish();
#else
    (void)token;
    return false;
#endif
}
bool take(const Token &token, Borrow &borrow) {
    Guard guard;
    borrow = {};
#if !IS_EMULATOR
    TWLeaseToken raw;
    if (!held(token) || !current() || !TWLeaseTake(&sPpc, &raw)) return false;
    borrow = {raw.epoch, raw.ticket, sOwner};
    return true;
#else
    (void)token;
    return false;
#endif
}
bool consumed(const Token &token, const Borrow &borrow) {
    Guard guard;
#if !IS_EMULATOR
    const TWLeaseToken raw = {borrow.epoch, borrow.ticket};
    if (!held(token) || borrow.owner != sOwner || !current() || !writable() ||
        !TWLeaseConsumed(&sPpc, &sControl, raw)) return false;
    return publish();
#else
    (void)token; (void)borrow;
    return false;
#endif
}
bool release(const Token &token) {
    Guard guard;
#if !IS_EMULATOR
    if (!held(token) || !current() || !writable() || !TWLeaseRelease(&sPpc, &sControl, key(token))) return false;
    if (!publish()) return false;
    sOwner = 0;
    return true;
#else
    (void)token;
    return false;
#endif
}
}
