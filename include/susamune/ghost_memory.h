#ifndef MOONSHINE_GHOST_MEMORY_H
#define MOONSHINE_GHOST_MEMORY_H
#include "susamune/mem2_map.h"
#define MOONSHINE_GHOST_MEMORY_FLAG 0x40000000u
#define MOONSHINE_GHOST_MEMORY_MAGIC 0x4d474d31u
#define MOONSHINE_GHOST_MEMORY_ABI 1u
#define MOONSHINE_GHOST_UPPER_PPC_BASE 0x93400000u
#define MOONSHINE_GHOST_UPPER_PHYS_BASE 0x13400000u
#define MOONSHINE_GHOST_UPPER_SIZE 0x001e0000u
#define MOONSHINE_GHOST_CORE_SIZE 0x8000u
#if MOONSHINE_GHOST_CORE_SIZE != SUSAMUNE_UPPER_MENU_CODE_SIZE || MOONSHINE_GHOST_UPPER_PPC_BASE != SUSAMUNE_UPPER_MENU_CODE_CONSOLE_PPC_BASE
#error Optional code prefix must match the admitted memory layout
#endif
#define MOONSHINE_GHOST_PRIMARY_PART_SIZE ((MOONSHINE_GHOST_UPPER_SIZE-MOONSHINE_GHOST_CORE_SIZE)/2u)
#define MOONSHINE_GHOST_ARAM_BYTES 0x60000u
#define MOONSHINE_GHOST_ARAM_START (0x1000000u-MOONSHINE_GHOST_ARAM_BYTES)
#define MOONSHINE_GHOST_TAIL_PART_SIZE (MOONSHINE_GHOST_ARAM_BYTES/2u)
#define MOONSHINE_GHOST_QF_BANK_BYTES (MOONSHINE_GHOST_PRIMARY_PART_SIZE+MOONSHINE_GHOST_TAIL_PART_SIZE)
#define MOONSHINE_GHOST_UPPER_DOLPHIN_BASE 0x71c20000u
#define MOONSHINE_GHOST_TAIL_DOLPHIN_BASE 0x71f00000u
#define MOONSHINE_GHOST_PROOF_OFFSET (SUSAMUNE_GHOST_TRACKS_OFFSET+SUSAMUNE_GHOST_TRACKS_SIZE)
#define MOONSHINE_GHOST_FRAME_HEADER_OFFSET (MOONSHINE_GHOST_PROOF_OFFSET+64u)
#define MOONSHINE_GHOST_FRAME_DATA_OFFSET (MOONSHINE_GHOST_FRAME_HEADER_OFFSET+32u)
#define MOONSHINE_GHOST_FRAME_CAPACITY 256u
#define MOONSHINE_GHOST_MEMORY_RUNTIME_OFFSET (MOONSHINE_GHOST_FRAME_DATA_OFFSET+MOONSHINE_GHOST_FRAME_CAPACITY*13u)
#define MOONSHINE_GHOST_MEMORY_RUNTIME_BYTES 128u
#define MOONSHINE_GHOST_PROOF_PPC_BASE (SUSAMUNE_CONSOLE_GHOST_RECORD_PPC_BASE+MOONSHINE_GHOST_PROOF_OFFSET)
#define MOONSHINE_GHOST_PROOF_PHYS_BASE (SUSAMUNE_CONSOLE_GHOST_RECORD_PHYS_BASE+MOONSHINE_GHOST_PROOF_OFFSET)
struct MoonshineGhostMemoryProof { unsigned int word[16]; };
enum MoonshineGhostMemoryField {
    MGM_MAGIC, MGM_ABI, MGM_NONCE, MGM_IOS, MGM_PLATFORM, MGM_PHYSICAL, MGM_SIMULATED,
    MGM_ARENA_LOW, MGM_ARENA_HIGH, MGM_IPC_LOW, MGM_IPC_HIGH, MGM_IOS_LOW,
    MGM_LOADER_HIGH, MGM_LOADER_IPC_HIGH, MGM_GAME, MGM_CHECKSUM
};
static inline unsigned int MoonshineGhostMemoryChecksum(const struct MoonshineGhostMemoryProof *p) {
    unsigned int h=2166136261u,i,shift;
    for(i=1;i<MGM_CHECKSUM;++i)for(shift=24;;shift-=8){h=(h^((p->word[i]>>shift)&255u))*16777619u;if(!shift)break;}
    return h;
}
static inline int MoonshineGhostMemoryProofValid(const struct MoonshineGhostMemoryProof *p,unsigned int game) {
    const unsigned int *w;
    if(!p)return 0;
    w=p->word;
    return (game==0x474d534au||game==0x474d5345u||game==0x474d5350u) &&
        w[MGM_MAGIC]==MOONSHINE_GHOST_MEMORY_MAGIC && w[MGM_ABI]==MOONSHINE_GHOST_MEMORY_ABI &&
        w[MGM_NONCE] && w[MGM_GAME]==game && w[MGM_IOS]==0x003a1820u && !w[MGM_PLATFORM] &&
        w[MGM_PHYSICAL]==0x04000000u && w[MGM_SIMULATED]==0x04000000u &&
        w[MGM_ARENA_LOW]==0x90000800u && w[MGM_ARENA_HIGH]==0x935e0000u &&
        w[MGM_IPC_LOW]==0x935e0000u && w[MGM_IPC_HIGH]==0x93600000u &&
        w[MGM_IOS_LOW]==0x93600000u &&
        w[MGM_LOADER_HIGH]>=0x93000000u && w[MGM_LOADER_HIGH]<=0x933e0000u &&
        w[MGM_LOADER_IPC_HIGH]==0x93400000u && w[MGM_CHECKSUM]==MoonshineGhostMemoryChecksum(p);
}
// A writable BAT must map the complete range to its expected physical RAM.
static inline int MoonshineGhostMemoryBat(unsigned int upper,unsigned int lower,unsigned int start,unsigned int bytes) {
    const unsigned int blocks=(upper>>2)&0x7ffu;
    const unsigned int mask=(blocks<<17)|0x1ffffu;
    const unsigned int base=upper&0xfffe0000u, physical=lower&0xfffe0000u;
    return bytes && start<=0xffffffffu-(bytes-1u) && (upper&2u) && (lower&3u)==2u &&
        !(blocks&(blocks+1u)) && !(base&mask) && !(physical&mask) &&
        start>=base && start-base<=mask && bytes-1u<=mask-(start-base) &&
        physical+(start-base)==(start&0x7fffffffu);
}
#if MOONSHINE_GHOST_MEMORY_RUNTIME_OFFSET+MOONSHINE_GHOST_MEMORY_RUNTIME_BYTES>SUSAMUNE_GHOST_SEGMENT_TABLE_OFFSET
#error Ghost memory metadata overlaps the segment table
#endif
#if MOONSHINE_GHOST_UPPER_DOLPHIN_BASE<0x71c00000u+SUSAMUNE_JP_UI_SIZE || MOONSHINE_GHOST_UPPER_DOLPHIN_BASE+MOONSHINE_GHOST_UPPER_SIZE>0x71e3f000u || MOONSHINE_GHOST_TAIL_DOLPHIN_BASE<0x71e3f000u+SUSAMUNE_MEM2_MODBIN_SIZE || MOONSHINE_GHOST_TAIL_DOLPHIN_BASE+MOONSHINE_GHOST_ARAM_BYTES>0x72000000u
#error Ghost extra storage overlaps existing Dolphin owners
#endif
#endif
