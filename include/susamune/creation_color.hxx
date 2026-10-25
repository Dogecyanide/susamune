#ifndef SUSAMUNE_CREATION_COLOR_HXX
#define SUSAMUNE_CREATION_COLOR_HXX

#include <Dolphin/types.h>

namespace CreationColor {

// Hundredths keep repeated edits independent of RGB byte rounding.
struct Hsl { u16 channel[3]; };

Hsl fromRgb(const u8 *rgb);
void toRgb(const Hsl &hsl, u8 *rgb);
u16 adjusted(u16 value, int channel, int delta);
u16 display(const Hsl &hsl, int channel);
// Presets are authoring commands; their RGB results use existing colour slots.
// 1 Sunset, 2 Ocean, 3 Rainbow, 4 Blend ends, 5 One colour.
void gradient(u8 preset, u16 index, u16 count, const u8 *first,
              const u8 *last, u8 *rgb);

}  // namespace CreationColor

#endif
