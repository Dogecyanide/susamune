#include "susamune/hoverless.hxx"
#include "susamune/emulator_persistence.hxx"
#include "susamune/menu.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"

namespace Hoverless {
namespace {
const char kHoverlessSavePending[] = "Hoverless save pending";
const char kHoverlessSaveFailed[] = "Hoverless save failed";
bool sAvailable, sDirty, sPending;
u8 sProfile = SUSAMUNE_HOVERLESS_INHERIT_PROFILE;
u32 sSequence, sWait, sRetry;
}
void init() {
    sAvailable = sDirty = sPending = false;
    sProfile = SUSAMUNE_HOVERLESS_INHERIT_PROFILE;
    sSequence = sWait = sRetry = 0;
}
void adopt(const volatile SusamuneCfg *cfg) {
    if (!cfg || !(cfg->flags & SUSAMUNE_HOVERLESS_FLAG)) return;
    volatile SusamuneHoverlessCfg *p = SUSAMUNE_HOVERLESS_PPC_PTR;
    DCInvalidateRange((void *)p, sizeof(*p));
    if (p->magic != SUSAMUNE_HOVERLESS_MAGIC || p->version != SUSAMUNE_HOVERLESS_VERSION ||
        p->rule != SUSAMUNE_HOVERLESS_RULE || p->count != SUSAMUNE_ILING_PB_MAX_SLOTS ||
        !(p->flags & SUSAMUNE_HOVERLESS_WRITABLE) || !SusamuneHoverlessProfileValid(p->activeProfile)) return;
    for (u32 i = 0; i < p->count; ++i)
        if (p->values[i] < -1 || p->values[i] > SUSAMUNE_ILING_PB_MAX_QF) return;
    memcpy(SUSAMUNE_HOVERLESS_VALUES, (const void *)p->values, sizeof(p->values));
    sProfile = p->activeProfile;
    sSequence = p->saveSeq;
    sAvailable = true;
}
bool available() { return sAvailable; }
int selectedProfile(int legacy) { return sAvailable && sProfile != SUSAMUNE_HOVERLESS_INHERIT_PROFILE ? sProfile : legacy; }
s32 *values() { return sAvailable ? reinterpret_cast<s32 *>(SUSAMUNE_HOVERLESS_VALUES) : nullptr; }
void dirty() { if (sAvailable) sDirty = true; }
void setProfile(int profile) { if (sAvailable) { sProfile = profile; dirty(); } }
void service() {
    if (!sAvailable) return;
    volatile SusamuneHoverlessCfg *p = SUSAMUNE_HOVERLESS_PPC_PTR;
    if (sPending) {
        u32 error = 0;
#if IS_EMULATOR
        const EmulatorPersistence::SaveResult result = EmulatorPersistence::poll(sSequence, &error);
        const bool done = result != EmulatorPersistence::SAVE_PENDING;
        if (result == EmulatorPersistence::SAVE_ERROR && !error) error = 1;
#else
        DCInvalidateRange((void *)&p->ackSeq, 32);
        const bool done = p->ackSeq == sSequence;
        error = p->status;
#endif
        if (!done) { if (++sWait == 300 && gMenu) gMenu->toast(kHoverlessSavePending); return; }
        sPending = false;
        if (error) { sDirty = true; sRetry = 300; if (gMenu) gMenu->toast(kHoverlessSaveFailed); }
    }
    if (sRetry) { --sRetry; return; }
    if (!sDirty) return;
#if IS_EMULATOR
    if (!EmulatorPersistence::lock()) return;
#endif
    memcpy((void *)p->values, SUSAMUNE_HOVERLESS_VALUES, sizeof(p->values));
    p->activeProfile = sProfile;
    p->saveSeq = ++sSequence;
    DCStoreRange((void *)p->values, sizeof(p->values));
    DCStoreRange((void *)p, 32);
#if IS_EMULATOR
    sSequence = EmulatorPersistence::commit();
#endif
    sPending = true; sDirty = false; sWait = 0;
}
}
