#include "susamune/native_timer_color.hxx"
#include "susamune/creation_extras.hxx"
#include "JSystem/J2D/J2DScreen.hxx"
#include "JSystem/J2D/J2DPicture.hxx"

extern "C" void *retailPictureVtable[] asm("__vt__10J2DPicture");
extern "C" u32 *retailGxState asm("gx");

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace NativeTimerColor {
namespace {
constexpr unsigned kDrawSelfSlot = 8;
typedef void (*DrawSelf)(J2DPicture *, int, int, Mtx *);
void **sVtable;

void drawPicture(J2DPicture *picture, int x, int y, Mtx *matrix) {
    bool custom = false;
    u8 gradient[2][3];
    const bool vertical = gCreationExtras.nativeTimerGradient(picture, gradient);
    const bool recolor = vertical || (gCreationExtras.nativeTimerRgb(picture, &custom) && custom);
    const JUtility::TColor white = picture->mColorMask;
    JUtility::TColor corners[4];
    if (vertical) {
        picture->mColorMask.r = picture->mColorMask.g = picture->mColorMask.b = 255;
        for (unsigned i = 0; i < 4; ++i) {
            corners[i] = picture->mVertexColors[i];
            for (unsigned c = 0; c < 3; ++c) {
                unsigned value = gradient[i / 2][c] * gCreationExtras.nativeTimerStyle().textBrightness / 100;
                if (value > 255) value = 255;
                (&picture->mVertexColors[i].r)[c] = (u8)value;
            }
        }
    }
    const JUtility::TColor black = picture->mColorOverlay;
    u32 swap = 0, rg = 0, ba = 0;
    if (recolor) {
        // Retail digit art stores its black outline and shading in red.
        picture->mColorOverlay.r = picture->mColorOverlay.g = picture->mColorOverlay.b = 0;
        swap = retailGxState[0x170 / 4];
        rg = retailGxState[0x1B8 / 4];
        ba = retailGxState[0x1BC / 4];
        GXSetTevSwapModeTable(GX_TEV_SWAP1, GX_CH_RED, GX_CH_RED, GX_CH_RED, GX_CH_ALPHA);
        GXSetTevSwapMode(GX_TEVSTAGE0, swap & 3, GX_TEV_SWAP1);
    }
    reinterpret_cast<DrawSelf>(retailPictureVtable[kDrawSelfSlot])(picture, x, y, matrix);
    if (vertical) {
        picture->mColorMask = white;
        for (unsigned i = 0; i < 4; ++i) picture->mVertexColors[i] = corners[i];
    }
    if (recolor) {
        picture->mColorOverlay = black;
        GXSetTevSwapMode(GX_TEVSTAGE0, swap & 3, (swap >> 2) & 3);
        GXSetTevSwapModeTable(GX_TEV_SWAP1, rg & 3, (rg >> 2) & 3,
                             ba & 3, (ba >> 2) & 3);
    }
}
}

bool beginDraw(J2DScreen *screen) {
    if (sVtable || !screen) return false;
    J2DPane *digit = screen->search('t_n1');
    if (!digit || digit->mTypeMagic != 'PIC1') return false;
    void **table = *reinterpret_cast<void ***>(digit);
    if (table == retailPictureVtable) return false;
    // The checked layout draw lends one shared table, changing only makeMatrix.
    for (unsigned i = 0; i < 10; ++i)
        if (table[i] != retailPictureVtable[i]) return false;
    sVtable = table;
    sVtable[kDrawSelfSlot] = reinterpret_cast<void *>(drawPicture);
    return true;
}

void endDraw() {
    if (!sVtable) return;
    sVtable[kDrawSelfSlot] = retailPictureVtable[kDrawSelfSlot];
    sVtable = nullptr;
}
}
