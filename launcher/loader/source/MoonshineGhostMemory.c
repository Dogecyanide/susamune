#include <gccore.h>
#include <ogc/lwp_watchdog.h>
#include <string.h>
#include "global.h"
#include "MoonshineGhostMemory.h"
#include "susamune/ghost_memory.h"
#include "susamune/disc_cache_memory.h"
extern void *__SYS_GetIPCBufferHi(void);
void MoonshineGhostMemoryInvalidate(void) {
    struct MoonshineGhostMemoryProof *p=(void*)MOONSHINE_GHOST_PROOF_PPC_BASE;
    memset(p,0,sizeof(*p));DCFlushRange(p,sizeof(*p));
    memset((void*)NIN_MEM2_DISC_CACHE_PROOF_PPC_BASE,0,96);
    DCFlushRange((void*)NIN_MEM2_DISC_CACHE_PROOF_PPC_BASE,96);
}
void MoonshineGhostMemoryPublish(u32 gameID) {
    struct MoonshineGhostMemoryProof p;
    struct MoonshineGhostMemoryProof *out=(void*)MOONSHINE_GHOST_PROOF_PPC_BASE;
    memset(&p,0,sizeof(p));
    p.word[MGM_ABI]=MOONSHINE_GHOST_MEMORY_ABI;p.word[MGM_NONCE]=gettime()|1u;
    p.word[MGM_GAME]=gameID;p.word[MGM_PLATFORM]=IsWiiU()?1u:0u;
    p.word[MGM_IOS]=*(volatile u32*)0xc0003140;
    p.word[MGM_PHYSICAL]=*(volatile u32*)0xc0003118;p.word[MGM_SIMULATED]=*(volatile u32*)0xc000311c;
    p.word[MGM_ARENA_LOW]=*(volatile u32*)0xc0003124;p.word[MGM_ARENA_HIGH]=*(volatile u32*)0xc0003128;
    p.word[MGM_IPC_LOW]=*(volatile u32*)0xc0003130;p.word[MGM_IPC_HIGH]=*(volatile u32*)0xc0003134;
    p.word[MGM_IOS_LOW]=*(volatile u32*)0xc0003148;
    p.word[MGM_LOADER_HIGH]=(u32)SYS_GetArena2Hi();p.word[MGM_LOADER_IPC_HIGH]=(u32)__SYS_GetIPCBufferHi();
    p.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&p);
    /* Publish only after the final loader read into the ghost/asset buffers. */
    p.word[MGM_MAGIC]=MOONSHINE_GHOST_MEMORY_MAGIC;
    if(!MoonshineGhostMemoryProofValid(&p,gameID))p.word[MGM_MAGIC]=0;
    memcpy(out,&p,sizeof(p));DCFlushRange(out,sizeof(p));
}

void MoonshineCacheMemoryPublish(u32 gameID) {
    const struct MoonshineGhostMemoryProof *boot=(void*)MOONSHINE_GHOST_PROOF_PPC_BASE;
    struct MoonshineCacheMemoryProof p;
    memset(&p,0,sizeof(p));p.word[MCP_MAGIC]=MS_CACHE_PROOF_MAGIC;p.word[MCP_ABI]=MS_CACHE_PROOF_ABI;
    p.word[MCP_NONCE]=boot->word[MGM_NONCE];p.word[MCP_GAME]=gameID;
    p.word[MCP_LAYOUT]=NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID;
    p.word[MCP_LOW]=(u32)SYS_GetArena2Lo();p.word[MCP_HIGH]=(u32)SYS_GetArena2Hi();
    p.word[MCP_IPC_HIGH]=(u32)__SYS_GetIPCBufferHi();p.word[MCP_CHECKSUM]=MoonshineCacheMemoryChecksum(&p);
    if(MoonshineCacheMemoryProofValid(&p,boot,gameID,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID)) {
        // Retire cached loader lines before ARM owns these bytes for the session.
#define CACHE_RELEASE(base,bytes) DCFlushRange((void*)((base)|0x80000000u),bytes); DCInvalidateRange((void*)((base)|0x80000000u),bytes);
        NIN_MEM2_DISC_CACHE_EXTRA_BANKS(CACHE_RELEASE)
#undef CACHE_RELEASE
    }else p.word[MCP_MAGIC]=0;
    memcpy((void*)NIN_MEM2_DISC_CACHE_PROOF_PPC_BASE,&p,sizeof(p));
    DCFlushRange((void*)NIN_MEM2_DISC_CACHE_PROOF_PPC_BASE,sizeof(p));
}
