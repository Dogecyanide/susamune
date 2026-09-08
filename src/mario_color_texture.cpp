#include "susamune/mario_color_texture.hxx"

#if defined(__powerpc__)
#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"
#endif

namespace MarioColorTexture {
namespace {

unsigned read16(const unsigned char *p) { return p[0] * 256u + p[1]; }
void write16(unsigned char *p, unsigned value) {
    p[0] = value >> 8;
    p[1] = value;
}

unsigned tint(unsigned value, unsigned x, unsigned y,
              const unsigned char colors[7][3], unsigned enabled) {
    const unsigned r = (value >> 11) * 255u / 31u;
    const unsigned g = ((value >> 5) & 63u) * 255u / 63u;
    const unsigned b = (value & 31u) * 255u / 31u;
    const bool red = r > g * 3u / 2u && r > b * 3u / 2u;
    const bool blue = b > r * 3u / 2u && b > g;
    int part = -1;
    if (y >= 160) {
        if (x >= 192) { if (red) part = 0; }
        else if (x >= 128) part = 3;
        else if (x < 64) part = 4;
        else if (y < 208) part = 1;
        // The lower middle strip is bare forearm skin.
    } else if (x < 128) {
        if (blue) part = 2;
        else if (y < 64 && red) part = 1;
    } else if (x >= 192 && y >= 100) {
        // The Sunshine shirt borrows this region from the head atlas.
        // Only its own shape uses the recoloured copy; keep the Shine design.
        const bool yellow = r > b * 3u / 2u && g > b * 3u / 2u;
        if (!yellow && r + g + b > 96) part = 6;
    }
    if (part < 0 || !(enabled & (1u << part))) return value;
    unsigned light = r > g ? r : g;
    if (b > light) light = b;
    const unsigned char *rgb = colors[part];
    return ((rgb[0] * light * 31u / 65025u) << 11) |
           ((rgb[1] * light * 63u / 65025u) << 5) |
           (rgb[2] * light * 31u / 65025u);
}

} // namespace

void recolor(const unsigned char *source, unsigned char *destination,
             const unsigned char colors[7][3], unsigned enabled) {
    unsigned offset = 0;
    for (unsigned ty = 0; ty < 256; ty += 8) {
        for (unsigned tx = 0; tx < 256; tx += 8) {
            for (unsigned sub = 0; sub < 4; ++sub, offset += 8) {
                const unsigned char *src = source + offset;
                unsigned char *dst = destination + offset;
                unsigned a = read16(src), b = read16(src + 2);
                const bool fourColors = a > b;
                const unsigned x = tx + (sub & 1u) * 4u;
                const unsigned y = ty + (sub >> 1) * 4u;
                a = tint(a, x, y, colors, enabled);
                b = tint(b, x, y, colors, enabled);
                const bool swap = fourColors ? a < b : a > b;
                if (swap) { const unsigned temp = a; a = b; b = temp; }
                // Equal endpoints would switch a four-colour block to alpha mode.
                if (fourColors && a == b) {
                    if (a < 65535) ++a; else --b;
                }
                write16(dst, a);
                write16(dst + 2, b);
                for (unsigned row = 0; row < 4; ++row) {
                    unsigned indices = src[4 + row];
                    if (swap) {
                        unsigned mapped = 0;
                        for (unsigned shift = 0; shift < 8; shift += 2) {
                            unsigned index = (indices >> shift) & 3u;
                            if (fourColors || index < 2) index ^= 1u;
                            mapped |= index << shift;
                        }
                        indices = mapped;
                    }
                    dst[4 + row] = indices;
                }
            }
        }
    }
}

} // namespace MarioColorTexture
