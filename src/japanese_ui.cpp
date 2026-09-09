#include "susamune/japanese_ui.hxx"
#if defined(SUSAMUNE_VERSION_JP)
#include "susamune/japanese_ui.h"
#include <Dolphin/GX.h>
#include <Dolphin/mem.h>
#include <Dolphin/OS.h>
#include <Dolphin/DVD.h>
#include <Dolphin/printf.h>
#include <J2D/J2DOrthoGraph.hxx>

namespace {
const u8 *sAsset;
bool sChecked;
u16 sCacheIds[64];
u8 sCache[64][128] __attribute__((aligned(32)));
unsigned int sNext;

#if IS_EMULATOR
bool loadDiscAsset() {
    // Retail DVD DMA cannot target Dolphin's virtual-memory aperture.
    DVDFileInfo file = {};
    file.mStart = SUSAMUNE_JP_UI_DISC_OFFSET;
    file.mLen = SUSAMUNE_JP_UI_SIZE;
    u8 *bounce = &sCache[0][0];
    if (DVDReadPrio(&file, bounce, 64, 0, 2) != 64) return false;
    const unsigned int bytes = SusamuneJpUiWord(bounce + 8);
    if (SusamuneJpUiWord(bounce) != SUSAMUNE_JP_UI_MAGIC ||
        bytes < 64 || bytes > SUSAMUNE_JP_UI_SIZE || (bytes & 31)) return false;
    volatile u8 *dst = reinterpret_cast<volatile u8 *>(SUSAMUNE_JP_UI_DOLPHIN_BASE);
    for (unsigned int offset = 0; offset < bytes;) {
        unsigned int count = bytes - offset;
        if (count > sizeof(sCache)) count = sizeof(sCache);
        if (DVDReadPrio(&file, bounce, count, offset, 2) != (s32)count) return false;
        for (unsigned int i = 0; i < count; ++i) dst[offset + i] = bounce[i];
        offset += count;
    }
    return true;
}
#endif

bool ready() {
    if (!sChecked) {
        sChecked = true;
#if IS_EMULATOR
        if (!loadDiscAsset()) return false;
        const u8 *p = reinterpret_cast<const u8 *>(SUSAMUNE_JP_UI_DOLPHIN_BASE);
#else
        const u8 *p = reinterpret_cast<const u8 *>(SUSAMUNE_JP_UI_PPC_BASE);
#endif
        if (SusamuneJpUiValid(p, SusamuneJpUiWord(p + 8))) sAsset = p;
    }
    return sAsset != nullptr;
}

unsigned int word(unsigned int offset) { return SusamuneJpUiWord(sAsset + offset); }

unsigned int nextCode(const u8 *&p) {
    unsigned int code = *p++;
    if (((code >= 0x81 && code <= 0x9F) || (code >= 0xE0 && code <= 0xFC)) && *p)
        code = (code << 8) | *p++;
    return code;
}

int glyph(unsigned int code) {
    unsigned int lo = 0, hi = word(36);
    const u8 *table = sAsset + word(32);
    while (lo < hi) {
        const unsigned int mid = (lo + hi) / 2;
        const unsigned int value = SusamuneJpUiHalf(table + mid * 4);
        if (value < code) lo = mid + 1;
        else hi = mid;
    }
    return lo < word(36) && SusamuneJpUiHalf(table + lo * 4) == code ? (int)lo : -1;
}

int units(const char *str) {
    if (!ready() || !str) return -1;
    int total = 0;
    bool japanese = false;
    const u8 *p = reinterpret_cast<const u8 *>(str);
    while (*p) {
        const unsigned int code = nextCode(p);
        const int i = glyph(code);
        if (i < 0) return -1;
        japanese |= code > 255;
        total += sAsset[word(32) + i * 4 + 2];
    }
    return japanese ? total : -1;
}

u8 *image(int id) {
    for (unsigned int i = 0; i < 64; ++i)
        if (sCacheIds[i] == id + 1) return sCache[i];
    // GX may still sample an earlier string when the bounded cache wraps.
    if (sNext == 64) {
        GXDrawDone();
        for (unsigned int i = 0; i < 64; ++i) sCacheIds[i] = 0;
        sNext = 0;
    }
    const unsigned int slot = sNext++;
    const u8 *src = sAsset + word(40) + id * 64;
    u8 *dst = sCache[slot];
    for (unsigned int i = 0; i < 64; ++i) {
        dst[2*i] = ((src[i] >> 6) * 5 << 4) | (((src[i] >> 4) & 3) * 5);
        dst[2*i+1] = (((src[i] >> 2) & 3) * 5 << 4) | ((src[i] & 3) * 5);
    }
    sCacheIds[slot] = id + 1;
    DCFlushRange(dst, 128);
    GXInvalidateTexAll();
    return dst;
}

void vertex(float x, float y, u32 rgba, u16 s, u16 t) {
    volatile float *f = reinterpret_cast<volatile float *>(0xCC008000);
    volatile u32 *w = reinterpret_cast<volatile u32 *>(0xCC008000);
    volatile u16 *h = reinterpret_cast<volatile u16 *>(0xCC008000);
    *f = x; *f = y; *f = 0; *w = rgba; *h = s; *h = t;
}
}

namespace JapaneseUi {
const char *text(const char *english) {
    if (!english || !ready()) return english;
    unsigned int hash = 0x811C9DC5, fingerprint = 5381;
    for (const u8 *p = reinterpret_cast<const u8 *>(english); *p; ++p) {
        hash = (hash ^ *p) * 0x01000193u;
        fingerprint = ((fingerprint * 33) ^ *p) & 0xFFFF;
    }
    unsigned int lo = 0, hi = word(20);
    while (lo < hi) {
        const unsigned int mid = (lo + hi) / 2;
        if (word(64 + mid * 8) < hash) lo = mid + 1;
        else hi = mid;
    }
    if (lo == word(20)) return english;
    const u8 *entry = sAsset + 64 + lo * 8;
    return SusamuneJpUiWord(entry) == hash && SusamuneJpUiHalf(entry + 4) == fingerprint
        ? reinterpret_cast<const char *>(sAsset + word(24) + SusamuneJpUiHalf(entry + 6)) : english;
}

int format(char *out, size_t capacity, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    int result = vsnprintf(out, capacity, text(fmt), args);
    va_end(args);
    if (out && capacity) {
        const u8 *p = reinterpret_cast<const u8 *>(out);
        while (*p) {
            const u8 *start = p;
            const unsigned int code = nextCode(p);
            if (p - start == 1 && ((code >= 0x81 && code <= 0x9F) || (code >= 0xE0 && code <= 0xFC))) {
                out[start - reinterpret_cast<const u8 *>(out)] = 0;
                break;
            }
        }
    }
    return result;
}

int width(const char *str, int size) {
    const int u = units(str);
    return u < 0 ? -1 : u * size / 24;
}

bool draw(const char *str, int x, int y, int sx, int sy,
          JUtility::TColor color, J2DOrthoGraph *ortho) {
    if (units(str) < 0 || !ortho) return false;
    ortho->setup2D();
    GXSetNumChans(1);
    GXSetNumTevStages(1);
    GXSetNumTexGens(1);
    GXSetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GXSetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    // Coverage belongs in alpha; multiplying RGB too squares thin-stroke opacity.
    GXSetTevColorIn(GX_TEVSTAGE0, GX_CC_ZERO, GX_CC_RASC, GX_CC_ONE, GX_CC_ZERO);
    GXSetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_SET);
    GXClearVtxDesc();
    GXSetVtxDesc(GX_VA_POS, GX_DIRECT);
    GXSetVtxDesc(GX_VA_CLR0, GX_DIRECT);
    GXSetVtxDesc(GX_VA_TEX0, GX_DIRECT);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XYZ, GX_F32, 0);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_CLR0, GX_CLR_RGBA, GX_RGBA8, 0);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0, GX_TEX_ST, GX_U16, 15);
    const u32 rgba = ((u32)color.r << 24) | ((u32)color.g << 16) | ((u32)color.b << 8) | color.a;
    const u8 *p = reinterpret_cast<const u8 *>(str);
    int advance = 0;
    while (*p) {
        const int id = glyph(nextCode(p));
        GXTexObj tex;
        GXInitTexObj(&tex, image(id), 16, 16, GX_TF_I4, GX_CLAMP, GX_CLAMP, GX_DISABLE);
        GXInitTexObjLOD(&tex, GX_LINEAR, GX_LINEAR, 0, 0, 0, GX_DISABLE, GX_DISABLE, GX_ANISO_1);
        GXLoadTexObj(&tex, GX_TEXMAP0);
        const int px = x + advance * sx / 24;
        GXBegin(GX_QUADS, GX_VTXFMT0, 4);
        vertex(px, y, rgba, 0, 0);
        vertex(px + sx, y, rgba, 32768, 0);
        vertex(px + sx, y + sy, rgba, 32768, 32768);
        vertex(px, y + sy, rgba, 0, 32768);
        advance += sAsset[word(32) + id * 4 + 2];
    }
    return true;
}
}
#endif
