#ifndef SUSAMUNE_MENU_NATIVE_ICON_H
#define SUSAMUNE_MENU_NATIVE_ICON_H

#include "susamune/menu_native_icon.hxx"

// Bounded subset of the loader's own-disc Yaz0/RARC extraction.
namespace MenuNativeIcon {
typedef unsigned char Byte;
typedef unsigned int Word;
enum { ModelBytes = 51104 };
struct Workspace {
    Byte input[0x400], history[0x1000], metadata[0x5000], model[ModelBytes];
};
static_assert(sizeof(Workspace) == WorkspaceBytes, "icon extraction must fit the existing upload gap");
typedef bool (*Read)(void *, Word, Byte *, Word);

inline Word be16(const Byte *p) { return (Word(p[0]) << 8) | p[1]; }
inline Word be32(const Byte *p) {
    return (Word(p[0]) << 24) | (Word(p[1]) << 16) | (Word(p[2]) << 8) | p[3];
}
inline void put16(Byte *p, Word v) { p[0] = v >> 8; p[1] = v; }
inline bool range(Word p, Word n, Word limit) { return p <= limit && n <= limit - p; }
inline bool name(const Byte *p, Word size, Word offset, const char *expected) {
    do {
        if (offset >= size || p[offset++] != static_cast<Byte>(*expected)) return false;
    } while (*expected++);
    return true;
}

struct Decoder {
    Workspace &w;
    Read read;
    void *context;
    Word size, inputAt, buffered, used, outputSize, outputAt, data, modelAt;
    Byte *input;
    bool ready;

    bool next(Byte &value) {
        if (used == buffered) {
            if (inputAt >= size) return false;
            // RARC table offsets are no longer needed after the member is selected.
            input = ready ? w.metadata : w.input;
            Word capacity = ready ? sizeof(w.metadata) : sizeof(w.input);
            buffered = size - inputAt < capacity ? size - inputAt : capacity;
            if (!read(context, inputAt, input, buffered)) return false;
            inputAt += buffered;
            used = 0;
        }
        value = input[used++];
        return true;
    }

    bool tables() {
        const Byte *m = w.metadata;
        if (be32(m + 4) != outputSize ||
            !range(data, be32(m + 0x10), outputSize)) return false;
        const Word nodes = be32(m + 0x20), files = be32(m + 0x28);
        const Word nt = be32(m + 0x24), ft = be32(m + 0x2c);
        const Word strings = be32(m + 0x34), stringBytes = be32(m + 0x30);
        if (!nodes || nodes > 1024 || !files || files > 4096 ||
            !range(0x20, nt, data) || !range(0x20 + nt, nodes * 16, data) ||
            !range(0x20, ft, data) || !range(0x20 + ft, files * 20, data) ||
            !range(0x20, strings, data) || !range(0x20 + strings, stringBytes, data))
            return false;
        const Byte *names = m + 0x20 + strings;
        Word nodeIndex = ~0u;
        for (Word i = 0; i < nodes; ++i) {
            const Byte *n = m + 0x20 + nt + i * 16;
            if (name(names, stringBytes, be32(n + 4), "mapobj")) {
                if (nodeIndex != ~0u) return false;
                nodeIndex = i;
            }
        }
        if (nodeIndex == ~0u) return false;
        const Byte *n = m + 0x20 + nt + nodeIndex * 16;
        const Word first = be32(n + 12), count = be16(n + 10);
        if (!range(first, count, files)) return false;
        modelAt = ~0u;
        for (Word i = first; i < first + count; ++i) {
            const Byte *f = m + 0x20 + ft + i * 20;
            const Word flags = be32(f + 4), offset = be32(f + 8), bytes = be32(f + 12);
            if (flags & 0x02000000) continue;
            if (!range(offset, bytes, outputSize - data)) return false;
            if (name(names, stringBytes, flags & 0xffffff, "srotdram.bmd")) {
                if (modelAt != ~0u || (flags & 0x04000000) || bytes != ModelBytes)
                    return false;
                modelAt = data + offset;
            }
        }
        ready = modelAt != ~0u;
        return ready;
    }

    bool emit(Byte value) {
        if (outputAt >= outputSize) return false;
        if (!ready) {
            if (outputAt >= sizeof(w.metadata)) return false;
            w.metadata[outputAt] = value;
        } else if (outputAt >= modelAt && outputAt - modelAt < ModelBytes) {
            w.model[outputAt - modelAt] = value;
        }
        w.history[outputAt++ & 0xfff] = value;
        if (outputAt == 0x20) {
            if (be32(w.metadata) != 0x52415243 || be32(w.metadata + 8) != 0x20 ||
                !range(0x20, be32(w.metadata + 12), sizeof(w.metadata))) return false;
            data = 0x20 + be32(w.metadata + 12);
            if (data < 0x40) return false;
        }
        return outputAt != data || tables();
    }

    bool decode() {
        Byte h[16], code = 0, mask = 0;
        for (Word i = 0; i < sizeof(h); ++i) if (!next(h[i])) return false;
        outputSize = be32(h + 4);
        if (be32(h) != 0x59617a30 || be32(h + 8) || be32(h + 12) ||
            outputSize < ModelBytes || outputSize > 8 * 1024 * 1024) return false;
        while (!ready || outputAt < modelAt + ModelBytes) {
            if (!mask) { if (!next(code)) return false; mask = 0x80; }
            Byte a, b;
            if (!next(a)) return false;
            if (code & mask) {
                if (!emit(a)) return false;
            } else {
                if (!next(b)) return false;
                const Word distance = ((a & 15) << 8 | b) + 1;
                Word length = a >> 4;
                if (!length) { if (!next(b)) return false; length = Word(b) + 18; }
                else length += 2;
                if (distance > outputAt || length > outputSize - outputAt) return false;
                while (length--) if (!emit(w.history[(outputAt - distance) & 0xfff])) return false;
            }
            mask >>= 1;
        }
        return true;
    }
};

inline Word crc32(const Byte *p, Word size) {
    Word crc = ~0u;
    while (size--) {
        crc ^= *p++;
        for (unsigned b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
    }
    return ~crc;
}

inline const Byte *booTexture(const Byte *model) {
    if (be32(model) != 0x4a334432 || be32(model + 4) != 0x626d6433 ||
        be32(model + 8) != ModelBytes) return 0;
    Word at = 32, sections = be32(model + 12);
    if (!sections || sections > 32) return 0;
    while (sections--) {
        if (!range(at, 8, ModelBytes)) return 0;
        const Byte *s = model + at;
        const Word bytes = be32(s + 4);
        if (bytes < 8 || !range(at, bytes, ModelBytes)) return 0;
        if (be32(s) == 0x54455831) {
            if (bytes < 20) return 0;
            const Word count = be16(s + 8), headers = be32(s + 12), strings = be32(s + 16);
            if (!count || count > 256 || !range(headers, count * 32, bytes) ||
                !range(strings, 4 + count * 4, bytes) || be16(s + strings) != count) return 0;
            for (Word i = 0; i < count; ++i) {
                const Word offset = be16(s + strings + 6 + i * 4);
                if (!name(s + strings, bytes - strings, offset, "L_srotdram00")) continue;
                const Byte *t = s + headers + i * 32;
                const Word image = be32(t + 28), atHeader = headers + i * 32;
                if (t[0] != 14 || be16(t + 2) != 128 || be16(t + 4) != 512 ||
                    t[8] || !range(atHeader, image, bytes) ||
                    !range(atHeader + image, 32768, bytes)) return 0;
                return t + image;
            }
            return 0;
        }
        at += bytes;
    }
    return 0;
}

struct Color { Word r, g, b, a; };
inline Color rgb565(Word p) {
    return {((p >> 11) & 31) * 255 / 31, ((p >> 5) & 63) * 255 / 63,
            (p & 31) * 255 / 31, 255};
}
inline Color cmpr(const Byte *image, Word x, Word y) {
    const Word block = (y / 8 * 16 + x / 8) * 32 + ((y & 4) / 4 * 2 + (x & 4) / 4) * 8;
    const Byte *p = image + block;
    const Word first = be16(p), second = be16(p + 2);
    const Color a = rgb565(first), b = rgb565(second);
    const Word index = (p[4 + (y & 3)] >> (6 - 2 * (x & 3))) & 3;
    if (!index) return a;
    if (index == 1) return b;
    if (first <= second) return index == 3 ? Color{0, 0, 0, 0}
        : Color{(a.r + b.r) / 2, (a.g + b.g) / 2, (a.b + b.b) / 2, 255};
    const Word aw = index == 2 ? 2 : 1, bw = 3 - aw;
    return {(a.r * aw + b.r * bw) / 3, (a.g * aw + b.g * bw) / 3,
            (a.b * aw + b.b * bw) / 3, 255};
}
inline Word rgb5a3(const Color &c) {
    return c.a >= 224 ? 0x8000 | (c.r >> 3) << 10 | (c.g >> 3) << 5 | (c.b >> 3)
        : (c.a >> 5) << 12 | (c.r >> 4) << 8 | (c.g >> 4) << 4 | (c.b >> 4);
}
inline Word pixel(Word width, Word x, Word y) {
    return 32 + ((y / 4 * ((width + 3) / 4) + x / 4) * 16 + (y & 3) * 4 + (x & 3)) * 2;
}
inline void header(Byte *out, Word width, Word height) {
    for (Word i = 0; i < 32; ++i) out[i] = 0;
    out[0] = 5; out[1] = 2;
    put16(out + 2, width); put16(out + 4, height);
    out[20] = out[21] = out[24] = 1;
    out[31] = 32;
}
inline bool extract(Read read, void *context, Word inputBytes, Workspace &w, Byte *out, Word capacity) {
    if (!read || capacity < BooBytes || inputBytes < 16 || inputBytes > 8 * 1024 * 1024) return false;
    Decoder decoder = {w, read, context, inputBytes, 0, 0, 0, 0, 0, 0, 0, w.input, false};
    if (!decoder.decode() || crc32(w.model, ModelBytes) != 0xc3886e6e) return false;
    const Byte *image = booTexture(w.model);
    if (!image) return false;
    header(out, 32, 32);
    for (Word y = 0; y < 32; ++y) for (Word x = 0; x < 32; ++x) {
        Color sum = {0, 0, 0, 0};
        Word count = 0;
        for (Word dy = 0; dy < 4; ++dy) for (Word dx = 0; dx < 4; ++dx) {
            const Color c = cmpr(image, x * 4 + dx, 384 + y * 4 + dy);
            // The slot symbol's uniform cream paper is not part of the drawing.
            if (!c.a || (c.r >= 248 && c.g >= 248 && c.b >= 220 && c.b <= 240)) continue;
            sum.r += c.r; sum.g += c.g; sum.b += c.b; ++count;
        }
        if (count) { sum.r /= count; sum.g /= count; sum.b /= count; sum.a = count * 255 / 16; }
        put16(out + pixel(32, x, y), rgb5a3(sum));
    }
    return true;
}

inline bool shrinkRgb5a3(const Byte *source, Word bytes, Byte *out, Word capacity,
                        Word width, Word height) {
    if (!source || !out || bytes < 32 || !width || !height || width > 256 || height > 256 ||
        capacity < 32 + ((width + 3) & ~3u) * ((height + 3) & ~3u) * 2 ||
        source[0] != 5 || source[8] || be32(source + 28) < 32) return false;
    const Word sw = be16(source + 2), sh = be16(source + 4);
    if (sw < width || sh < height || sw > 256 || sh > 256 ||
        !range(be32(source + 28), ((sw + 3) & ~3u) * ((sh + 3) & ~3u) * 2, bytes))
        return false;
    const Byte *image = source + be32(source + 28) - 32;
    for (Word i = 32; i < 32 + ((width + 3) & ~3u) * ((height + 3) & ~3u) * 2; ++i)
        out[i] = 0;
    header(out, width, height);
    for (Word y = 0; y < height; ++y) for (Word x = 0; x < width; ++x) {
        Color sum = {0, 0, 0, 0};
        Word count = 0;
        for (Word sy = y * sh / height; sy < (y + 1) * sh / height; ++sy)
        for (Word sx = x * sw / width; sx < (x + 1) * sw / width; ++sx) {
            const Word p = be16(image + pixel(sw, sx, sy));
            const Color c = p & 0x8000
                ? Color{((p >> 10) & 31) * 255 / 31, ((p >> 5) & 31) * 255 / 31, (p & 31) * 255 / 31, 255}
                : Color{((p >> 8) & 15) * 17, ((p >> 4) & 15) * 17, (p & 15) * 17, ((p >> 12) & 7) * 255 / 7};
            sum.r += c.r * c.a; sum.g += c.g * c.a; sum.b += c.b * c.a; sum.a += c.a;
            ++count;
        }
        if (sum.a) { sum.r /= sum.a; sum.g /= sum.a; sum.b /= sum.a; sum.a /= count; }
        put16(out + pixel(width, x, y), rgb5a3(sum));
    }
    return true;
}
inline bool shrinkController(const Byte *source, Word bytes, Byte *out, Word capacity) {
    return source && bytes >= 32 && be16(source + 2) == 120 && be16(source + 4) == 104 &&
        shrinkRgb5a3(source, bytes, out, capacity, 40, 36);
}
inline bool shrinkPianta(const Byte *source, Word bytes, Byte *out, Word capacity) {
    return source && bytes >= 32 && be16(source + 2) >= 82 && be16(source + 2) <= 83 &&
        be16(source + 4) >= 104 && be16(source + 4) <= 106 &&
        shrinkRgb5a3(source, bytes, out, capacity, 24, 32);
}
inline bool shrinkMario(const Byte *source, Word bytes, Byte *out, Word capacity) {
    return source && bytes >= 32 && be16(source + 2) == 34 && be16(source + 4) == 44 &&
        shrinkRgb5a3(source, bytes, out, capacity, 17, 22);
}
inline bool shrinkGlasses(const Byte *source, Word bytes, Byte *out, Word capacity) {
    if (!source || !out || bytes < 32 || capacity < GlassesBytes || source[0] != 2 ||
        source[8] || be16(source + 2) != 100 || be16(source + 4) != 36 ||
        be32(source + 28) < 32 || !range(be32(source + 28), 3744, bytes)) return false;
    const Byte *pixels = source + be32(source + 28);
    for (Word i = 0; i < GlassesBytes; ++i) out[i] = 0;
    header(out, 50, 18); out[0] = 2;
    for (Word y = 0; y < 18; ++y) for (Word x = 0; x < 50; ++x) {
        Word alpha = 0, light = 0;
        for (Word dy = 0; dy < 2; ++dy) for (Word dx = 0; dx < 2; ++dx) {
            const Word sx = x * 2 + dx, sy = y * 2 + dy;
            const Byte p = pixels[(sy / 4 * 13 + sx / 8) * 32 + (sy & 3) * 8 + (sx & 7)];
            alpha += p >> 4; light += (p & 15) * (p >> 4);
        }
        out[32 + (y / 4 * 7 + x / 8) * 32 + (y & 3) * 8 + (x & 7)] =
            alpha ? (alpha / 4) << 4 | light / alpha : 0;
    }
    return true;
}
inline bool shrinkTitle(const Byte *source, Word bytes, Byte *out, Word capacity) {
    if (!source || !out || bytes < 32 || capacity < TitleBytes || source[0] != 0 ||
        source[8] || be32(source + 28) < 32) return false;
    const Word sw = be16(source + 2), sh = be16(source + 4);
    if (!sw || !sh || sw > 220 || sh > 24 || ((sw | sh) & 1) ||
        !range(be32(source + 28), ((sw + 7) / 8) * ((sh + 7) / 8) * 32, bytes))
        return false;
    const Word width = sw / 2, height = sh / 2;
    const Byte *pixels = source + be32(source + 28);
    for (Word i = 0; i < TitleBytes; ++i) out[i] = 0;
    header(out, width, height); out[0] = 0;
    for (Word y = 0; y < height; ++y) for (Word x = 0; x < width; ++x) {
        Word sum = 0;
        for (Word dy = 0; dy < 2; ++dy) for (Word dx = 0; dx < 2; ++dx) {
            const Word sx = x * 2 + dx, sy = y * 2 + dy;
            const Word p = (sy / 8 * ((sw + 7) / 8) + sx / 8) * 64 +
                           (sy & 7) * 8 + (sx & 7);
            sum += (pixels[p / 2] >> ((p & 1) ? 0 : 4)) & 15;
        }
        const Word p = (y / 8 * ((width + 7) / 8) + x / 8) * 64 +
                       (y & 7) * 8 + (x & 7);
        out[32 + p / 2] |= ((sum + 2) / 4) << ((p & 1) ? 0 : 4);
    }
    return true;
}
}
#endif
