#ifndef MOONSHINE_DISC_CACHE_MEMORY_H
#define MOONSHINE_DISC_CACHE_MEMORY_H
#include "susamune/ghost_memory.h"
#define MS_CACHE_PROOF_MAGIC 0x4D434831u
#define MS_CACHE_PROOF_ABI 1u
struct MoonshineCacheMemoryProof { unsigned word[16]; };
enum { MCP_MAGIC, MCP_ABI, MCP_NONCE, MCP_GAME, MCP_LAYOUT, MCP_LOW, MCP_HIGH, MCP_IPC_HIGH, MCP_CHECKSUM=15 };
static inline unsigned MoonshineCacheMemoryChecksum(const struct MoonshineCacheMemoryProof *p) {
    unsigned h=2166136261u,i,shift;
    for(i=1;i<MCP_CHECKSUM;++i)for(shift=24;;shift-=8){h=(h^((p->word[i]>>shift)&255u))*16777619u;if(!shift)break;}
    return h;
}
static inline int MoonshineCacheMemoryProofValid(const struct MoonshineCacheMemoryProof *p,
    const struct MoonshineGhostMemoryProof *boot,unsigned game,unsigned layout) {
    unsigned i;const unsigned *w;
    if(!p||!MoonshineGhostMemoryProofValid(boot,game))return 0;
    w=p->word;
    for(i=MCP_IPC_HIGH+1;i<MCP_CHECKSUM;++i)if(w[i])return 0;
    return layout==NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID && w[MCP_MAGIC]==MS_CACHE_PROOF_MAGIC &&
        w[MCP_ABI]==MS_CACHE_PROOF_ABI && w[MCP_NONCE]==boot->word[MGM_NONCE] &&
        w[MCP_GAME]==game && w[MCP_LAYOUT]==layout &&
        w[MCP_LOW]>=0x90000800u && w[MCP_LOW]<=0x93030000u &&
        w[MCP_HIGH]>=0x93380000u && w[MCP_HIGH]<=0x933E0000u &&
        w[MCP_IPC_HIGH]==0x93400000u && w[MCP_CHECKSUM]==MoonshineCacheMemoryChecksum(p);
}
#endif
