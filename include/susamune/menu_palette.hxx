#pragma once
#include "susamune/menu_palette.h"
#include "JSystem/JUtility/JUTColor.hxx"
namespace MenuPalette {
void reset();
void adopt();
void stage();
JUtility::TColor colour(unsigned role, JUtility::TColor fallback);
const char *names();
}
