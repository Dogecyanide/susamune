#ifndef SUSAMUNE_STATE_POOL_RUNTIME_HXX
#define SUSAMUNE_STATE_POOL_RUNTIME_HXX
#include "susamune/state_pool_memory.h"
#include "susamune/susamune_cfg.h"

// The old launcher still owns the extra bank for file patches.
inline StatePoolMemory statePoolMemory() {
#if IS_EMULATOR
    StatePoolMemory memory = {{
        reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_SNAPSHOT_PPC_BASE),
        reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE)},
        {SUSAMUNE_STATE_POOL_SIZE, SUSAMUNE_STATE_POOL_EXTRA_SIZE}};
#else
    const volatile SusamuneCfg *cfg = SUSAMUNE_CFG_PPC_PTR;
    const bool expanded = cfg->magic == SUSAMUNE_CFG_MAGIC && cfg->version == SUSAMUNE_CFG_VERSION &&
        (cfg->flags & SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION) != 0;
    StatePoolMemory memory = {{
        reinterpret_cast<unsigned char *>(SUSAMUNE_MEM2_SNAPSHOT_PPC_BASE),
        reinterpret_cast<unsigned char *>(SUSAMUNE_STATE_POOL_EXTRA_PPC_BASE)},
        {SUSAMUNE_STATE_POOL_SIZE, expanded ? SUSAMUNE_STATE_POOL_EXTRA_SIZE : 0}};
#endif
    return memory;
}
#endif
