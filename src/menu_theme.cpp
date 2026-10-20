#include "susamune/menu_theme.hxx"
#include "susamune/menu_theme_assets.hxx"
#include "susamune/menu.hxx"
#include "susamune/build_branding.hxx"
#include "susamune/creation_extras.hxx"
#include "susamune/glyphs.hxx"
#include "susamune/retail_input.hxx"
#include "SMS/System/MarDirector.hxx"
#include "Dolphin/string.h"

namespace {
using Color = JUtility::TColor;
J2DOrthoGraph *sOrtho;
bool sPage;
bool sDarkPaper;
s16 sSelectedX, sSelectedY, sSelectedH;
u16 sPatternFrame;
u32 sLastTick;

unsigned pose(unsigned interval) {
    return (sPatternFrame / interval) % 2 == 0;
}

int iconBob() {
    static const s8 steps[] = {0, -1, -3, -1};
    return steps[(sPatternFrame / 45) & 3];
}

bool rgb(Color c, int r, int g, int b) {
    return c.r == r && c.g == g && c.b == b;
}

Color ink(Color c) {
    switch ((u32(c.r) << 16) | (u32(c.g) << 8) | c.b) {
    case 0xFFFFFF: case 0xEEF2FC: case 0xE6EEFA: case 0xDCE6F0: case 0xEBF0FF:
        return sDarkPaper ? Color(255, 249, 219, c.a) : Color(65, 48, 25, c.a);
    case 0xC8CEDC: case 0xC8D2E1: case 0xBED2E1:
        return sDarkPaper ? Color(233, 225, 194, c.a) : Color(84, 64, 32, c.a);
    case 0x788296: case 0xBECDE1: case 0xBECDDC:
    case 0x687288:
        return sDarkPaper ? Color(207, 205, 178, c.a) : Color(108, 88, 48, c.a);
    case 0x5AAAFF: case 0xFFE164: case 0x78DC96:
        return sDarkPaper ? Color(153, 235, 181, c.a) : Color(36, 107, 78, c.a);
    }
    if (c.r > 200 && c.g < 130 && c.b < 130)
        return sDarkPaper ? Color(255, 152, 139, c.a) : Color(158, 42, 35, c.a);
    return c;
}

void vertex(s16 x, s16 y, u32 color, float u, float v) {
    volatile u16 *h = reinterpret_cast<volatile u16 *>(0xCC008000);
    volatile u32 *w = reinterpret_cast<volatile u32 *>(0xCC008000);
    volatile float *f = reinterpret_cast<volatile float *>(0xCC008000);
    *h = x; *h = y; *h = 0; *w = color; *f = u; *f = v;
}
}

namespace MenuTheme {
void image(const ResTIMG *t, int x, int y, int w, int h, u8 alpha, ImageMode mode) {
    if (!t || !sOrtho || w <= 0 || h <= 0) return;
    const bool paper = mode == PaperTile;
    const bool right = mode == PointRight;
    if (!paper) {
        const int tw = right ? t->mHeight : t->mWidth;
        const int th = right ? t->mWidth : t->mHeight;
        int fitW = w, fitH = h;
        if (w * th > h * tw) fitW = h * tw / th;
        else fitH = w * th / tw;
        x += (w - fitW) / 2; y += (h - fitH) / 2;
        w = fitW; h = fitH;
    }
    sOrtho->setup2D();
    GXTexObj object;
    const u8 *data = reinterpret_cast<const u8 *>(t);
    const u8 wrap = paper ? GX_REPEAT : GX_CLAMP;
    if (t->mHasPalette) {
        GXTlutObj palette;
        GXInitTlutObj(&palette, const_cast<u8 *>(data + t->mPaletteOffset),
                      static_cast<GXTlutFmt>(t->mPaletteFormat), t->mPaletteColors);
        GXLoadTlut(&palette, GX_TLUT0);
        GXInitTexObjCI(&object, const_cast<u8 *>(data + t->mTextureOffset),
                       t->mWidth, t->mHeight, t->mFormat,
                       wrap, wrap, GX_FALSE, GX_TLUT0);
    } else {
        GXInitTexObj(&object, const_cast<u8 *>(data + t->mTextureOffset),
                     t->mWidth, t->mHeight, static_cast<GXTexFmt>(t->mFormat),
                     wrap, wrap, GX_FALSE);
    }
    GXInitTexObjLOD(&object, GX_LINEAR, GX_LINEAR, 0, 0, 0,
                    GX_FALSE, GX_FALSE, GX_ANISO_1);
    GXLoadTexObj(&object, GX_TEXMAP0);
    GXSetNumChans(1);
    GXSetNumTevStages(1);
    GXSetNumTexGens(1);
    GXSetTexCoordGen2(GX_TEXCOORD0, GX_TG_MTX2x4, GX_TG_TEX0,
                      GX_IDENTITY, GX_FALSE, GX_DTTIDENTITY);
    GXSetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GXSetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    if (paper) {
        // guide_1.blo remaps this opaque I4 tile through its parchment colours.
        const u8 *rgb = gCreationExtras.menuBackground();
        GXColor low = {0, 0, 0, 0};
        u8 *channels = &low.r;
        for (int i = 0; i < 3; ++i)
            channels[i] = rgb[i] > 170 + i * 10 ? rgb[i] - 170 - i * 10 : 0;
        GXSetTevColor(GX_TEVREG0, low);
        GXSetTevColor(GX_TEVREG1, GXColor{rgb[0], rgb[1], rgb[2], 255});
        GXSetTevColorIn(GX_TEVSTAGE0, GX_CC_C0, GX_CC_C1, GX_CC_TEXC, GX_CC_ZERO);
        GXSetTevAlphaIn(GX_TEVSTAGE0, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_A1);
    }
    GXSetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_SET);
    GXClearVtxDesc();
    GXSetVtxDesc(GX_VA_POS, GX_DIRECT);
    GXSetVtxDesc(GX_VA_CLR0, GX_DIRECT);
    GXSetVtxDesc(GX_VA_TEX0, GX_DIRECT);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XYZ, GX_S16, 0);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_CLR0, GX_CLR_RGBA, GX_RGBA8, 0);
    GXSetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0, GX_TEX_ST, GX_F32, 0);
    GXBegin(GX_QUADS, GX_VTXFMT0, 4);
    const u32 rgba = 0xFFFFFF00u | alpha;
    const float u = paper ? float(w) / t->mWidth : 1.0f;
    const float v = paper ? float(h) / t->mHeight : 1.0f;
    vertex(x, y, rgba, 0, right ? 1.0f : 0.0f);
    vertex(x + w, y, rgba, right ? 0.0f : u, 0);
    vertex(x + w, y + h, rgba, u, right ? 0.0f : v);
    vertex(x, y + h, rgba, right ? 1.0f : 0.0f, v);
}

void page(bool active) {
    sPage = active;
    sSelectedH = 0;
}

Color footerColor() { return ink(Color(104, 114, 136, 255)); }

}

void Menu::drawMenuText(const char *text, int x, int y, int sx, int sy, Color color) {
    if (sPage) {
        if (sSelectedH && y >= sSelectedY && y < sSelectedY + sSelectedH &&
            x < sSelectedX + 22 && text[0] == '>' && !text[1])
            return;
        color = ink(color);
        while (sx > 11 && x + Menu::textWidth(text, sx) > 594) {
            --sx;
            if (sy > 11) --sy;
        }
    }
    drawText(text, x, y, sx, sy, color);
}

void Menu::fillMenuBox(int x, int y, int w, int h, Color color) {
    if (sPage) {
        if (rgb(color, 90, 170, 255) && color.a == 60) {
            color = Color(236, 189, 69, 130);
            if (w >= 100 && h >= 18 && h <= 40) {
                sSelectedX = x; sSelectedY = y;
                sSelectedH = h;
                fillBox(x, y, w, h, color);
                MenuTheme::image(MenuThemeAssets::get(MenuThemeAssets::Hand, pose(45)),
                                 x - 19, y + 5, 28, 26, 255, MenuTheme::PointRight);
                return;
            }
        } else if (color.a >= 220 && color.r < 80 && color.g < 80 && color.b < 100) {
            const u8 *rgb = gCreationExtras.menuBackground();
            color = Color(rgb[0], rgb[1], rgb[2], 255);
        } else {
            color = ink(color);
        }
    }
    fillBox(x, y, w, h, color);
}

namespace MenuTheme {
void frame(Menu *menu, J2DOrthoGraph *ortho, bool sidebar) {
    sOrtho = ortho;
    page(false);
    const u8 *background = gCreationExtras.menuBackground();
    sDarkPaper = 3 * background[0] + 6 * background[1] + background[2] < 1400;
    // The retail Guide advances on UI ticks, including while gameplay is held.
    if (TMarDirector *director = RetailInput::stageDirector()) {
        const u32 elapsed = director->unk5C - sLastTick;
        sLastTick = director->unk5C;
        if (elapsed <= 8) sPatternFrame = (sPatternFrame + elapsed) % 541;
    }
    MenuThemeAssets::service();
    menu->fillBox(0, 0, 640, 480, Color(4, 19, 21, 155));
    menu->fillBox(30, 24, 588, 412, Color(54, 85, 60, 255));
    menu->fillBox(24, 18, 588, 412, Color(background[0], background[1], background[2], 255));
    image(MenuThemeAssets::get(MenuThemeAssets::Paper), 24, 18, 588, 412,
          255, PaperTile);
    menu->fillBox(24, 75, 588, 60, Color(77, 139, 91, 47));
    menu->fillBox(24, 74, 588, 1, Color(164, 131, 64, 255));
    menu->fillBox(24, 135, 588, 1, Color(164, 131, 64, 255));
    image(MenuThemeAssets::get(MenuThemeAssets::Shine), 38, 25 + iconBob(), 39, 39);
    menu->drawText("MOONSHINE", 88, 28, 24, 24, ink(Color(90, 170, 255, 255)));
    menu->drawText(BuildBranding::version(nullptr), 90, 56, 12, 12,
                   footerColor());
    image(MenuThemeAssets::get(MenuThemeAssets::Palm, pose(90)), 551, 22, 45, 48);
    if (sidebar) {
        menu->fillBox(24, 136, 124, 266, Color(61, 135, 113, 255));
        menu->fillBox(148, 136, 2, 266, Color(145, 140, 79, 255));
        if (const ResTIMG *postcard = MenuThemeAssets::get(MenuThemeAssets::Postcard))
            image(postcard, 31, 178, 110, 110 * postcard->mHeight / postcard->mWidth);
        menu->drawText("Isle Delfino", 35, 150, 16, 16, Color(255, 249, 219, 255));
        image(MenuThemeAssets::get(MenuThemeAssets::Fish, pose(90)), 42, 334, 37, 48);
        image(MenuThemeAssets::get(MenuThemeAssets::Boat, pose(90)), 87, 339, 48, 36);
    }
    menu->fillBox(24, 402, 588, 1, Color(164, 131, 64, 255));
}

void shoulder(Menu *menu, bool right) {
    menu->drawText(right ? SUSAMUNE_GLYPH_R : SUSAMUNE_GLYPH_L,
                   right ? 576 : 34, 94, 26, 26, Color(255, 255, 255, 255));
}

void category(Menu *menu, const char *name, int index, int x, int width, bool selected) {
    using namespace MenuThemeAssets;
    static const Asset icons[] = {
        TabShine, TabPad, TabMario, TabCoin, TabGhost, TabGlasses, TabPianta, Boat
    };
    if (selected) {
        for (int inset = 0; inset < 3; ++inset) {
            const int left = x - 2 + inset * 2, right = x + width + 2 - inset * 2;
            const int top = 77 + inset * 2, bottom = 133 - inset * 2;
            const s16 border[] = {
                (s16)(left + 5), (s16)top, (s16)(right - 5), (s16)(top + 1),
                (s16)right, (s16)(top + 6), (s16)(right - 1), (s16)(bottom - 4),
                (s16)(right - 5), (s16)bottom, (s16)(left + 4), (s16)(bottom - 1),
                (s16)left, (s16)(bottom - 6), (s16)(left + 1), (s16)(top + 5)
            };
            menu->fillPoly(border, 8, inset == 0 ? Color(213, 145, 31, 255) :
                inset == 1 ? Color(255, 237, 153, 255) : Color(49, 110, 76, 255));
        }
    }
    const Asset asset = icons[index >= 0 && index < 8 ? index : 0];
    image(get(asset, selected && asset == Boat ? pose(90) : 0),
          x + (width - 42) / 2, 80 + (selected && asset != Boat ? iconBob() : 0),
          42, 27, selected ? 255 : 210);
    menu->drawText(name, x + (width - Menu::textWidth(name, 18)) / 2, 110, 18, 18,
                   selected ? Color(255, 248, 209, 255) : ink(Color(255, 255, 255, 255)));
}
}

