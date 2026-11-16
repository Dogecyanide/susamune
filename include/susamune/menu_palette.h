#ifndef MOONSHINE_MENU_PALETTE_H
#define MOONSHINE_MENU_PALETTE_H
#include "susamune/susamune_cfg.h"
#include "susamune/layout_profile.h"

#define MOONSHINE_MENU_PALETTE_MAGIC 0x4D50414Cu
#define MOONSHINE_MENU_PALETTE_VERSION 1u
#define MOONSHINE_MENU_PALETTE_FLAG 0x20000000u
#define MOONSHINE_MENU_PALETTE_OFFSET 0x7800u
#define MOONSHINE_MENU_PALETTE_SIZE 64u

enum MoonshineMenuColour {
    MENU_PAPER, MENU_HEADER, MENU_CATEGORIES, MENU_SIDEBAR,
    MENU_TRIM, MENU_TRIM_LIGHT, MENU_SELECTED_TAB, MENU_HIGHLIGHT,
    MENU_TEXT, MENU_MUTED_TEXT, MENU_VALUE_TEXT, MENU_SELECTED_TEXT,
    MENU_TITLE_TEXT, MENU_SIDEBAR_TEXT, MENU_SPINE, MENU_FOOTER,
    MENU_COLOUR_COUNT
};
struct MoonshineMenuPalette {
    unsigned int magic;
    unsigned short version, custom;
    unsigned char rgb[MENU_COLOUR_COUNT][3];
    unsigned char reserved[8];
};
#define MOONSHINE_MENU_DEFAULT_VALUES { \
    {230,230,190},{230,230,190},{77,139,91},{61,135,113}, \
    {187,133,37},{255,236,162},{49,110,76},{49,110,76}, \
    {65,48,25},{108,88,48},{36,107,78},{255,248,209}, \
    {36,107,78},{255,249,219},{143,85,40},{77,139,91} \
}
extern const unsigned char MoonshineMenuDefaults[MENU_COLOUR_COUNT][3];

static inline void MoonshineMenuPaletteInit(struct MoonshineMenuPalette *p) {
    unsigned i,c;
    p->magic=MOONSHINE_MENU_PALETTE_MAGIC;p->version=MOONSHINE_MENU_PALETTE_VERSION;p->custom=0;
    for(i=0;i<MENU_COLOUR_COUNT;++i)for(c=0;c<3;++c)p->rgb[i][c]=MoonshineMenuDefaults[i][c];
    for(i=0;i<sizeof(p->reserved);++i)p->reserved[i]=0;
}
static inline int MoonshineMenuPaletteValid(const struct MoonshineMenuPalette *p) {
    unsigned i;
    if(!p||p->magic!=MOONSHINE_MENU_PALETTE_MAGIC||p->version!=MOONSHINE_MENU_PALETTE_VERSION)return 0;
    for(i=0;i<sizeof(p->reserved);++i)if(p->reserved[i])return 0;
    return 1;
}
#define MOONSHINE_MENU_PALETTE_PHYS_PTR ((struct MoonshineMenuPalette *)(SUSAMUNE_MEM2_CFG_PHYS_BASE + MOONSHINE_MENU_PALETTE_OFFSET))
#if IS_EMULATOR
#define MOONSHINE_MENU_PALETTE_BASE (SUSAMUNE_DOLPHIN_RUNTIME_PPC_BASE + MOONSHINE_MENU_PALETTE_OFFSET)
#else
#define MOONSHINE_MENU_PALETTE_BASE (SUSAMUNE_MEM2_CFG_PPC_BASE + MOONSHINE_MENU_PALETTE_OFFSET)
#endif
#define MOONSHINE_MENU_PALETTE_STAGE ((struct MoonshineMenuPalette *)MOONSHINE_MENU_PALETTE_BASE)
#define MOONSHINE_MENU_PALETTE_LIVE ((struct MoonshineMenuPalette *)(MOONSHINE_MENU_PALETTE_BASE + MOONSHINE_MENU_PALETTE_SIZE))
typedef char menu_palette_size[(sizeof(struct MoonshineMenuPalette)==MOONSHINE_MENU_PALETTE_SIZE)?1:-1];
typedef char menu_palette_gap[(MOONSHINE_MENU_PALETTE_OFFSET >= MOONSHINE_LAYOUT_MAILBOX_OFFSET + MOONSHINE_LAYOUT_MAILBOX_SIZE && MOONSHINE_MENU_PALETTE_OFFSET + 2*MOONSHINE_MENU_PALETTE_SIZE <= SUSAMUNE_SPLIT_STATS_CFG_OFFSET)?1:-1];
typedef char menu_palette_alignment[(MOONSHINE_MENU_PALETTE_OFFSET%32==0 && MOONSHINE_MENU_PALETTE_SIZE%32==0)?1:-1];
#endif
