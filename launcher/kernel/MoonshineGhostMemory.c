#include "global.h"
#include "MoonshineGhostMemory.h"
#include "susamune/ghost_memory.h"
#include "susamune/susamune_cfg.h"
extern u32 GAME_ID;
void MoonshineGhostMemoryInit(void) {
    const struct MoonshineGhostMemoryProof *p=(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE;
    struct SusamuneCfg *cfg=SUSAMUNE_CFG_PHYS_PTR;
    sync_before_read((void*)p,sizeof(*p));
    if(cfg->magic!=SUSAMUNE_CFG_MAGIC || cfg->version!=SUSAMUNE_CFG_VERSION)return;
    cfg->flags&=~MOONSHINE_GHOST_MEMORY_FLAG;
    if(MoonshineGhostMemoryProofValid(p,GAME_ID))cfg->flags|=MOONSHINE_GHOST_MEMORY_FLAG;
    /* Boot only: the PPC has not acquired this cache line yet. */
    sync_after_write(cfg,32);
}
