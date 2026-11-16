#ifndef SUSAMUNE_JAPANESE_UI_H
#define SUSAMUNE_JAPANESE_UI_H

#include "mem2_map.h"

/* Immutable after the loader writes it, like the patch prefix before it, so it
 * survives warm resets; it no longer shares the mod staging window. */
#define SUSAMUNE_JP_UI_PPC_BASE (SUSAMUNE_JP_UI_PHYS_BASE + 0x80000000u)
#define SUSAMUNE_JP_UI_DOLPHIN_BASE 0x71C00000u
// Export validates this gap separately from the relocated DOL.
#define SUSAMUNE_JP_UI_DISC_OFFSET 0x00C00000u
#define SUSAMUNE_JP_UI_MAGIC 0x4D4A5549u
#define SUSAMUNE_JP_UI_VERSION 2u
#define SUSAMUNE_JP_UI_FILENAME "ja_ui.bin"

static inline unsigned int SusamuneJpUiWord(const unsigned char *p)
{
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16) |
           ((unsigned int)p[2] << 8) | p[3];
}

static inline unsigned int SusamuneJpUiHalf(const unsigned char *p)
{
    return ((unsigned int)p[0] << 8) | p[1];
}

/* A null destination validates the exact same stream used by the texture cache. */
static inline int SusamuneJpUiGlyph(const unsigned char *p, unsigned int size,
    const unsigned char *tree, unsigned char *out)
{
    unsigned int i=0,bit=0;
    if(!size || size>64)return 0;
    if(size==64){if(out)for(i=0;i<64;++i)out[i]=p[i];return 1;}
    for(i=0;i<64;++i) {
        unsigned int node=0;
        while(!(node&0x8000)) {
            unsigned int branch;
            if(bit>=size*8)return 0;
            branch=(p[bit/8]>>(7-bit%8))&1;++bit;
            node=SusamuneJpUiHalf(tree+node*4+branch*2);
        }
        if(out)out[i]=node&255;
    }
    return (bit+7)/8==size && !(p[size-1]&((1u<<((8-bit%8)%8))-1));
}

/* Header and catalogue are immutable after this complete validation. */
static inline int SusamuneJpUiValid(const unsigned char *p, unsigned int bytes)
{
    unsigned int size, count, texts, textBytes, glyphs, glyphCount, pixels, tree, nodes;
    unsigned int i, crc = 0xFFFFFFFFu, last = 0;
    if (bytes < 64 || bytes > SUSAMUNE_JP_UI_SIZE ||
        SusamuneJpUiWord(p) != SUSAMUNE_JP_UI_MAGIC ||
        SusamuneJpUiWord(p + 4) != SUSAMUNE_JP_UI_VERSION) return 0;
    size = SusamuneJpUiWord(p + 8);
    count = SusamuneJpUiWord(p + 20);
    texts = SusamuneJpUiWord(p + 24);
    textBytes = SusamuneJpUiWord(p + 28);
    glyphs = SusamuneJpUiWord(p + 32);
    glyphCount = SusamuneJpUiWord(p + 36);
    pixels = SusamuneJpUiWord(p + 40);
    tree = SusamuneJpUiWord(p + 56);nodes = SusamuneJpUiWord(p + 60);
    if (size != bytes || SusamuneJpUiWord(p + 16) != 64 ||
        !count || count > 4096 || texts != 64 + count * 8 ||
        !textBytes || textBytes > 65535 || glyphs != texts + textBytes ||
        !glyphCount || glyphCount > 2048 ||
        !nodes || nodes>255 || tree!=glyphs+glyphCount*6 ||
        pixels != ((tree + nodes * 4 + 31) & ~31u) ||
        pixels >= size || size - pixels > 65536 || (size & 31) ||
        SusamuneJpUiWord(p + 44) != 16 || SusamuneJpUiWord(p + 48) != 64 ||
        SusamuneJpUiWord(p + 52) != glyphs + glyphCount * 4) return 0;
    for (i = 0; i < size; ++i) {
        unsigned int j;
        crc ^= i >= 12 && i < 16 ? 0 : p[i];
        for (j = 0; j < 8; ++j) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1)));
    }
    if ((crc ^ 0xFFFFFFFFu) != SusamuneJpUiWord(p + 12) || p[texts + textBytes - 1]) return 0;
    for(i=0;i<nodes*2;++i) {
        unsigned int child=SusamuneJpUiHalf(p+tree+i*2);
        if(child&0x8000){if(child>0x80ff)return 0;}
        else if(child<=i/2 || child>=nodes)return 0;
    }
    for (i = 0; i < count; ++i) {
        unsigned int key = SusamuneJpUiWord(p + 64 + i * 8);
        unsigned int offset = SusamuneJpUiHalf(p + 70 + i * 8);
        if ((i && key <= last) || offset >= textBytes) return 0;
        last = key;
    }
    last = 0;
    for (i = 0; i < glyphCount; ++i) {
        const unsigned char *g = p + glyphs + i * 4;
        unsigned int code = SusamuneJpUiHalf(g);
        unsigned int offset = SusamuneJpUiHalf(p+glyphs+glyphCount*4+i*2);
        if (code <= last || g[2] > 24 || offset > size-pixels ||
            g[3] > size-pixels-offset || !SusamuneJpUiGlyph(p+pixels+offset,g[3],p+tree,0)) return 0;
        last = code;
    }
    return 1;
}

#endif
