#ifndef SUSAMUNE_STATE_POOL_RUNTIME_HXX
#define SUSAMUNE_STATE_POOL_RUNTIME_HXX
#include "susamune/state_pool_memory.h"
#include "susamune/susamune_cfg.h"

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

inline void *stateCodecWorkspace(const StatePoolMemory &memory) {
    if (memory.sizes[0] == SUSAMUNE_STATE_POOL_SIZE)
        return reinterpret_cast<void *>(SUSAMUNE_STATE_CODEC_PPC_BASE);
    if (memory.sizes[0] == SUSAMUNE_STATE_POOL_LEGACY_SIZE)
        return memory.banks[0] + SUSAMUNE_STATE_POOL_LEGACY_SIZE;
    return nullptr;
}
#endif
