#pragma once

#include "JSystem/JUtility/JUTTexture.hxx"
#include "JSystem/JUtility/JUTColor.hxx"
#include "susamune/menu_theme_assets.hxx"

class Menu;
class J2DOrthoGraph;

namespace MenuTheme {
enum ImageMode { Fit, PaperTile, PointRight, LeanLeft, LeanRight };
void begin(J2DOrthoGraph *);
void panel(Menu *, int x, int y, int w, int h, const char *title,
           MenuThemeAssets::Asset icon = MenuThemeAssets::Palm);
void selection(Menu *, int x, int y, int w, int h, bool hand = false);
JUtility::TColor textColor(bool muted = false);
void hand(int x, int y, int w, int h);
void frame(Menu *, J2DOrthoGraph *, bool sidebar);
void page(bool active);
JUtility::TColor footerColor();
void category(Menu *, const char *, int index, int x, int width, bool selected);
void shoulder(Menu *, bool right);
void image(const ResTIMG *, int x, int y, int w, int h, u8 alpha = 255,
           ImageMode mode = Fit);
}
