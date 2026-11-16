#pragma once
#include <Dolphin/types.h>
#include <JSystem/JUtility/JUTColor.hxx>
class J2DOrthoGraph;

namespace JapaneseUi {
#if defined(SUSAMUNE_VERSION_JP)
bool available();
bool enabled();
void toggle();
const char *text(const char *english);
const char *translated(const char *english);
int format(char *out, size_t capacity, const char *format, ...);
int width(const char *text, int size);
const char *fitLine(const char *text, char *out, unsigned int capacity,
                    int maxWidth, int size);
bool draw(const char *text, int x, int y, int sx, int sy,
          JUtility::TColor color, J2DOrthoGraph *ortho);
#else
inline bool available() { return false; }
inline bool enabled() { return false; }
inline void toggle() {}
inline const char *text(const char *english) { return english; }
inline const char *translated(const char *english) { return english; }
#endif
}
