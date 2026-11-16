#pragma once

namespace LiveColours {
enum { Message = 36, Bytes = 22, PacketBytes = 24 };
struct Palette { unsigned char mask, rgb[7][3]; };
static_assert(sizeof(Palette) == Bytes, "appearance wire size");
inline bool valid(const Palette &p) { return !(p.mask & 0x80); }
inline bool same(const Palette &a, const Palette &b) {
    const auto *x = reinterpret_cast<const unsigned char *>(&a);
    const auto *y = reinterpret_cast<const unsigned char *>(&b);
    for (unsigned i = 0; i < Bytes; ++i) if (x[i] != y[i]) return false;
    return true;
}
inline void encode(unsigned char *out, unsigned player, const Palette &p) {
    out[0] = Message; out[1] = player;
    const auto *bytes = reinterpret_cast<const unsigned char *>(&p);
    for (unsigned i = 0; i < Bytes; ++i) out[i + 2] = bytes[i];
}
inline bool decode(const void *data, unsigned bytes, Palette &out) {
    if (!data || bytes != PacketBytes) return false;
    const auto *p = static_cast<const unsigned char *>(data);
    if (p[0] != Message || p[1] >= 4 || (p[2] & 0x80)) return false;
    auto *dest = reinterpret_cast<unsigned char *>(&out);
    for (unsigned i = 0; i < Bytes; ++i) dest[i] = p[i + 2];
    return true;
}
}
