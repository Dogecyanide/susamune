#ifndef MOONSHINE_KANA_TEXT_H
#define MOONSHINE_KANA_TEXT_H

/* Local editable text uses CP932; service JSON is converted to UTF-8. */
static inline unsigned MoonshineKanaCode(const char *text, unsigned bytes) {
    unsigned a, b;
    if (!text || !bytes) return 0;
    a = (unsigned char)text[0];
    if (a >= 32 && a <= 126) return a;
    if (bytes < 2) return 0;
    b = (unsigned char)text[1];
    if (a == 0x82 && b >= 0x9f && b <= 0xf1) return 0x3041 + b - 0x9f;
    if (a == 0x83 && b >= 0x40 && b <= 0x93 && b != 0x7f)
        return 0x30a1 + b - 0x40 - (b > 0x7f);
    if (a == 0x81) {
        switch (b) {
        case 0x41: return 0x3001; case 0x42: return 0x3002;
        case 0x45: return 0x30fb; case 0x5b: return 0x30fc;
        case 0x75: return 0x300c; case 0x76: return 0x300d;
        case 0x48: return 0xff1f; case 0x49: return 0xff01;
        }
    }
    return 0;
}
static inline int MoonshineKanaValid(const char *text, unsigned capacity) {
    unsigned i = 0;
    if (!text) return 0;
    while (i < capacity) {
        unsigned code;
        if (!text[i]) return 1;
        code = MoonshineKanaCode(text + i, capacity - i);
        if (!code) return 0;
        i += code < 128 ? 1 : 2;
    }
    return 0;
}
static inline unsigned MoonshineKanaJson(char *out, unsigned capacity, const char *text) {
    unsigned used = 0;
    if (!out || !capacity || !text) return 0;
    while (*text) {
        unsigned code = MoonshineKanaCode(text, text[1] ? 2 : 1);
        unsigned count = code >= 128 ? 3 : (code == '"' || code == 92) ? 2 : 1;
        if (!code || count >= capacity - used) return 0;
        if (code >= 128) {
            out[used++] = (char)(0xe0 | (code >> 12));
            out[used++] = (char)(0x80 | ((code >> 6) & 63));
            out[used++] = (char)(0x80 | (code & 63));
            text += 2;
        } else {
            if (count == 2) out[used++] = 92;
            out[used++] = *text++;
        }
    }
    out[used] = 0;
    return used + 1;
}
#endif
