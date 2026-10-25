#include "susamune/state_work_lease.hxx"
#include "susamune/transfer_lease.hxx"

namespace StateWorkLease {
namespace {
enum Phase { IDLE, LEGACY_WORK, SHARED_WORK, RELEASING };
unsigned char sPhase;
TransferLease::Token sToken;
}

void update() {
    if (sPhase != RELEASING) return;
    TransferLease::poll();
    if (TransferLease::release(sToken)) {
        sToken = {};
        sPhase = IDLE;
    }
}

bool quiet() { return sPhase == IDLE; }
unsigned int epoch() { return sPhase == SHARED_WORK ? sToken.epoch : 0; }

Guard::Guard(bool needed) : mHeld(needed ? 0 : 2) {
    // SD restores already retain the STATE owner through their final read.
    if (!needed) return;
    update();
    if (!quiet()) return;
    TransferLease::poll();
    const TransferLease::Mode mode = TransferLease::init();
#if IS_EMULATOR
    if (mode == TransferLease::UNAVAILABLE) {
#else
    if (TransferLease::legacyAllowed()) {
#endif
        sPhase = LEGACY_WORK;
    } else if (mode == TransferLease::SHARED &&
               TransferLease::claim(TransferLease::CODEC, sToken)) {
        sPhase = SHARED_WORK;
    } else return;
    mHeld = true;
}

Guard::~Guard() {
    if (mHeld != 1) return;
    if (sPhase == LEGACY_WORK) sPhase = IDLE;
    else {
        // A transient publication read cannot discard the only release token.
        sPhase = RELEASING;
        update();
    }
}
}
