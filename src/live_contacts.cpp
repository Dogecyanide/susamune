#include "susamune/live_contacts.hxx"
#if TIMEWARP_LIVE_RACING
#include "susamune/settings.hxx"
#include "susamune/susamune_cfg.h"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
#include "Dolphin/string.h"
namespace LiveContacts {
namespace {
#if IS_EMULATOR
SusamuneOnlineContacts local;
#endif
SusamuneOnlineContacts *book() {
#if IS_EMULATOR
    return &local;
#else
    const auto *cfg = SUSAMUNE_CFG_PPC_PTR;
    if (cfg->magic != SUSAMUNE_CFG_MAGIC || !(cfg->flags & SUSAMUNE_ONLINE_NAME_FLAG)) return nullptr;
    if (SUSAMUNE_ONLINE_NAME_PPC_PTR->contactsAbi != 1) return nullptr;
    auto *value = SUSAMUNE_ONLINE_CONTACTS_PPC_PTR;
    DCInvalidateRange(value, sizeof(*value));
    return value->magic == SUSAMUNE_ONLINE_CONTACTS_MAGIC ? value : nullptr;
#endif
}
void changed(SusamuneOnlineContacts *value) {
#if !IS_EMULATOR
    DCStoreRange(value, sizeof(*value));
    gSettings.markDirty();
#endif
}
}
const char *name(unsigned slot) {
    const auto *value = book();
    return value && slot < SUSAMUNE_ONLINE_CONTACTS_COUNT && value->rows[slot].name[0] ?
        value->rows[slot].name : nullptr;
}
bool copy(unsigned slot, char *out) {
    if (!name(slot)) return false;
    const auto &row = book()->rows[slot];
    LiveP2P::Code code = {};
    memcpy(code.endpoint.ip, row.code, 4);
    code.endpoint.port = row.code[4] << 8 | row.code[5];
    code.secret = row.code[6] << 8 | row.code[7];
    return LiveP2P::encode(code, out);
}
void forget(unsigned slot) {
    if (!name(slot)) return;
    auto *value = book();
    memset(&value->rows[slot], 0, sizeof(value->rows[slot]));
    changed(value);
}
void remember(const char *name, const LiveP2P::Code &code) {
    auto *value = book();
    char encoded[LiveP2P::CODE_CHARS + 1];
    if (!value || !name || !name[0] || !LiveP2P::encode(code, encoded)) return;
    SusamuneOnlineContact next = {};
    for (unsigned i = 0; i < sizeof(next.name) - 1 && name[i]; ++i) {
        if ((unsigned char)name[i] < 32 || (unsigned char)name[i] > 126) return;
        next.name[i] = name[i];
    }
    memcpy(next.code, code.endpoint.ip, 4);
    next.code[4] = code.endpoint.port >> 8; next.code[5] = code.endpoint.port;
    next.code[6] = code.secret >> 8; next.code[7] = code.secret;
    unsigned slot = SUSAMUNE_ONLINE_CONTACTS_COUNT;
    for (unsigned i = 0; i < SUSAMUNE_ONLINE_CONTACTS_COUNT; ++i) {
        if (!memcmp(&value->rows[i], &next, sizeof(next))) return;
        if (!strcmp(value->rows[i].name, next.name)) { slot = i; break; }
        if (!value->rows[i].name[0] && slot == SUSAMUNE_ONLINE_CONTACTS_COUNT) slot = i;
    }
    if (slot == SUSAMUNE_ONLINE_CONTACTS_COUNT) {
        memmove(value->rows + 1, value->rows, sizeof(next) * (SUSAMUNE_ONLINE_CONTACTS_COUNT - 1));
        slot = 0;
    }
    value->rows[slot] = next;
    changed(value);
}
}
#endif
