#pragma once

#include "JSystem/JUtility/JUTTexture.hxx"
#include "JSystem/JUtility/JUTColor.hxx"

class Menu;
class J2DOrthoGraph;

namespace MenuTheme {
enum ImageMode { Fit, PaperTile, PointRight };
void frame(Menu *, J2DOrthoGraph *, bool sidebar);
void page(bool active);
JUtility::TColor footerColor();
void category(Menu *, const char *, int index, int x, int width, bool selected);
void shoulder(Menu *, bool right);
void image(const ResTIMG *, int x, int y, int w, int h, u8 alpha = 255,
           ImageMode mode = Fit);
}
