#ifndef SUSAMUNE_GRADIENT_OPTIONS_H
#define SUSAMUNE_GRADIENT_OPTIONS_H
#define SUSAMUNE_GRADIENT_MOTION_COUNT 10u
/* A0 stores one high motion bit per word; C0 stores two. Old files retain A0. */
static inline unsigned SusamuneWordMotion(unsigned options, unsigned extra, unsigned word) {
    unsigned motion = (options >> 3) & 3;
    if ((extra & 0xf8) == 0xa0 || (extra & 0xc0) == 0xc0)
        motion |= ((extra >> word) & 1) << 2;
    if ((extra & 0xc0) == 0xc0) motion |= ((extra >> (word + 3)) & 1) << 3;
    return motion;
}
static inline unsigned char SusamuneWordMotionExtra(unsigned extra, unsigned word, unsigned motion) {
    if ((extra & 0xc0) != 0xc0 && (extra & 0xf8) != 0xa0) extra = 0xa0;
    if (motion >= 8 && (extra & 0xc0) != 0xc0) extra = 0xc0 | (extra & 7);
    extra = (extra & ~(1u << word)) | (((motion >> 2) & 1u) << word);
    if ((extra & 0xc0) == 0xc0)
        extra = (extra & ~(1u << (word + 3))) | (((motion >> 3) & 1u) << (word + 3));
    return (unsigned char)extra;
}
#endif
