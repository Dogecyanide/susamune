#ifndef SUSAMUNE_STATE_POOL_RUNTIME_HXX
#define SUSAMUNE_STATE_POOL_RUNTIME_HXX
#include "susamune/state_pool_memory.h"
#include "susamune/susamune_cfg.h"
#include "susamune/transfer_lease.hxx"
#include "susamune/transfer_layout.h"

// Capabilities select the pool and scratch together; latch this at boot.
inline StatePoolMemory statePoolMemory() {
#if IS_EMULATOR
    StatePoolMemory memory = {{
        reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_SNAPSHOT_PPC_BASE),
        reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE)},
        {SUSAMUNE_STATE_POOL_SIZE, SUSAMUNE_STATE_POOL_EXTRA_SIZE}};
#else
    const volatile SusamuneCfg *cfg = SUSAMUNE_CFG_PPC_PTR;
    const bool valid = cfg->magic == SUSAMUNE_CFG_MAGIC && cfg->version == SUSAMUNE_CFG_VERSION;
    const bool expanded = valid && (cfg->flags & SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION) != 0;
    const bool relocated = valid && (cfg->flags & SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED) != 0;
    StatePoolMemory memory = {{
        reinterpret_cast<unsigned char *>(SUSAMUNE_MEM2_SNAPSHOT_PPC_BASE),
        reinterpret_cast<unsigned char *>(SUSAMUNE_STATE_POOL_EXTRA_PPC_BASE)},
        {relocated ? SUSAMUNE_STATE_POOL_SIZE : SUSAMUNE_STATE_POOL_LEGACY_SIZE,
         expanded ? SUSAMUNE_STATE_POOL_EXTRA_SIZE : 0}};
#endif
    return memory;
}

// Upgrade the boot-latched map only after both workers acknowledge activation.
inline bool statePoolSharedMemory(StatePoolMemory &memory) {
#if IS_EMULATOR
    (void)memory;
    return false;
#else
    if (!TransferLease::sharedMap() || !StatePoolMemoryValid(&memory) ||
        memory.banks[0] != reinterpret_cast<unsigned char *>(SUSAMUNE_MEM2_SNAPSHOT_PPC_BASE) ||
        memory.banks[1] != reinterpret_cast<unsigned char *>(SUSAMUNE_STATE_POOL_EXTRA_PPC_BASE) ||
        memory.sizes[0] != SUSAMUNE_STATE_POOL_SIZE ||
        memory.sizes[1] != SUSAMUNE_STATE_POOL_EXTRA_SIZE ||
        (memory.sizes[2] && (memory.sizes[2] != SUSAMUNE_TRANSFER_POOL_THIRD_SIZE ||
            memory.banks[2] != reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_THIRD_PPC_BASE))) ||
        (memory.sizes[3] && (memory.sizes[3] != SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE ||
            memory.banks[3] != reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_FOURTH_PPC_BASE))) ||
        (memory.sizes[4] && (memory.sizes[4] != SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE ||
            memory.banks[4] != reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_FIFTH_PPC_BASE)))) return false;
    StatePoolMemory shared = memory;
    shared.banks[2] = reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_THIRD_PPC_BASE);
    shared.sizes[2] = SUSAMUNE_TRANSFER_POOL_THIRD_SIZE;
    shared.banks[3] = reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_FOURTH_PPC_BASE);
    shared.sizes[3] = SUSAMUNE_TRANSFER_POOL_FOURTH_SIZE;
    shared.banks[4] = reinterpret_cast<unsigned char *>(SUSAMUNE_TRANSFER_POOL_FIFTH_PPC_BASE);
    shared.sizes[4] = SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE;
    if (!StatePoolMemoryValid(&shared)) return false;
    memory = shared;
    return true;
#endif
}

inline void *stateCodecWorkspace(const StatePoolMemory &memory) {
    if (memory.sizes[0] == SUSAMUNE_STATE_POOL_SIZE)
        return reinterpret_cast<void *>(SUSAMUNE_STATE_CODEC_PPC_BASE);
    if (memory.sizes[0] == SUSAMUNE_STATE_POOL_LEGACY_SIZE)
        return memory.banks[0] + SUSAMUNE_STATE_POOL_LEGACY_SIZE;
    return nullptr;
}
#endif
