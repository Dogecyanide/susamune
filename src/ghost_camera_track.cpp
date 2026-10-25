#include "susamune/ghost_camera.hxx"
#include "Dolphin/math.h"
#include "Dolphin/string.h"
#include "Dolphin/mem.h"

extern "C" f32 retailSquareRoot(f32) asm("sqrtf__3stdFf");

namespace GhostCamera {
namespace {
bool finite(f32 value) {
    union { f32 value; u32 bits; } number = {value};
    return (number.bits & 0x7f800000u) != 0x7f800000u;
}
void put16(u8 *p, s32 n) { p[0] = n >> 8; p[1] = n; }
void put24(u8 *p, s32 n) { p[0] = n >> 16; p[1] = n >> 8; p[2] = n; }
s32 get24(const u8 *p) {
    u32 n = (u32(p[0]) << 16) | (u32(p[1]) << 8) | p[2];
    return static_cast<s32>(n << 8) >> 8;
}
SusamuneGhostCameraHeader *header(void *bank) {
    return static_cast<SusamuneGhostCameraHeader *>(prefix(bank));
}
SusamuneGhostCameraSample *keys(void *bank) {
    return reinterpret_cast<SusamuneGhostCameraSample *>(header(bank) + 1);
}
bool sane(const SusamuneGhostCameraHeader *h) {
    return h && h->magic == SUSAMUNE_GHOST_CAMERA_MAGIC && h->version == 1 &&
        h->headerSize == 32 && h->count <= SUSAMUNE_GHOST_CAMERA_MAX_COUNT &&
        !(h->flags & ~SUSAMUNE_GHOST_CAMERA_TRUNCATED);
}
void normalize(f32 *q) {
    f32 n = 0;
    for (u32 i = 0; i < 4; ++i) n += q[i] * q[i];
    const f32 scale = 1.0f / retailSquareRoot(n);
    for (u32 i = 0; i < 4; ++i) q[i] *= scale;
}
}

void *prefix(void *bank) {
    return bank ? static_cast<u8 *>(bank) + SUSAMUNE_GHOST_CAMERA_BANK_OFFSET : nullptr;
}
const void *prefix(const void *bank) { return prefix(const_cast<void *>(bank)); }

void reset(void *bank) {
    if (!bank) return;
    SusamuneGhostCameraHeader *h = header(bank);
    memset(h, 0, sizeof(*h));
    h->magic = SUSAMUNE_GHOST_CAMERA_MAGIC;
    h->version = 1;
    h->headerSize = sizeof(*h);
}

u32 prefixSize(const void *bank) {
    const SusamuneGhostCameraHeader *h = header(const_cast<void *>(bank));
    return sane(h) ? 32 + h->count * 24 : 0;
}

bool encode(const View &view, u32 qf, u8 flags, SusamuneGhostCameraSample *out) {
    if (!finite(view.fovy) || !(view.fovy >= 1 && view.fovy <= 179) || (flags & 0x80)) return false;
    f32 norm = 0;
    for (u32 i = 0; i < 4; ++i) {
        if (!finite(view.rotation[i])) return false;
        norm += view.rotation[i] * view.rotation[i];
    }
    if (!finite(norm) || !(norm > 0.9f && norm < 1.1f)) return false;
    for (u32 i = 0; i < 3; ++i)
        if (!finite(view.position[i]) ||
            !(view.position[i] >= -2097151.0f && view.position[i] <= 2097151.0f)) return false;
    u8 *p = out->bytes;
    p[0] = qf >> 24; p[1] = qf >> 16; p[2] = qf >> 8; p[3] = qf;
    for (u32 i = 0; i < 3; ++i) {
        const f32 n = view.position[i] * 4;
        put24(p + 4 + i * 3, static_cast<s32>(n + (n < 0 ? -0.5f : 0.5f)));
    }
    const f32 scale = 32767.0f / retailSquareRoot(norm);
    for (u32 i = 0; i < 4; ++i) {
        const f32 n = view.rotation[i] * scale;
        put16(p + 13 + i * 2, static_cast<s32>(n + (n < 0 ? -0.5f : 0.5f)));
    }
    put16(p + 21, static_cast<s32>(view.fovy * 256 + 0.5f));
    p[23] = flags;
    return true;
}

void decode(const SusamuneGhostCameraSample &sample, View *out) {
    const u8 *p = sample.bytes;
    for (u32 i = 0; i < 3; ++i) out->position[i] = get24(p + 4 + 3*i) * 0.25f;
    for (u32 i = 0; i < 4; ++i)
        out->rotation[i] = static_cast<s16>((u32(p[13 + 2*i]) << 8) | p[14 + 2*i]) / 32767.0f;
    normalize(out->rotation);
    out->fovy = ((u32(p[21]) << 8) | p[22]) / 256.0f;
}

void matrix(const View &v, f32 m[3][3]) {
    const f32 x=v.rotation[0], y=v.rotation[1], z=v.rotation[2], w=v.rotation[3];
    m[0][0]=1-2*(y*y+z*z); m[0][1]=2*(x*y-z*w); m[0][2]=2*(x*z+y*w);
    m[1][0]=2*(x*y+z*w); m[1][1]=1-2*(x*x+z*z); m[1][2]=2*(y*z-x*w);
    m[2][0]=2*(x*z-y*w); m[2][1]=2*(y*z+x*w); m[2][2]=1-2*(x*x+y*y);
}

void capture(void *bank, u32 qf, u8 segment) {
    SusamuneGhostCameraHeader *h = header(bank);
    if (!sane(h) || segment >= 64) return;
    View view;
    if (!captureView(&view)) return;
    SusamuneGhostCameraSample sample;
    bool cut = h->count == 0;
    if (h->count) {
        const SusamuneGhostCameraSample &last = keys(bank)[h->count - 1];
        const u32 previous = SusamuneGhostReadBe32(last.bytes);
        if (qf <= previous) return;
        cut = (last.bytes[23] & 63) != segment;
        View old;
        decode(last, &old);
        f32 distance = 0, dot = 0;
        for (u32 i = 0; i < 3; ++i) {
            const f32 d = view.position[i] - old.position[i]; distance += d*d;
        }
        for (u32 i = 0; i < 4; ++i) dot += view.rotation[i] * old.rotation[i];
        cut = cut || distance > 250000.0f || fabsf(dot) < 0.7071f || fabsf(view.fovy-old.fovy)>15;
        if (!cut && qf - previous < SUSAMUNE_GHOST_CAMERA_INTERVAL_QF) return;
    }
    if (!encode(view, qf, segment | (cut ? 0x40 : 0), &sample)) return;
    if (h->count == SUSAMUNE_GHOST_CAMERA_MAX_COUNT) {
        h->flags |= SUSAMUNE_GHOST_CAMERA_TRUNCATED;
        return;
    }
    keys(bank)[h->count++] = sample;
}

void trim(void *bank, u32 endQf, u16 segments) {
    SusamuneGhostCameraHeader *h = header(bank);
    if (!sane(h)) return;
    while (h->count) {
        const u8 *p = keys(bank)[h->count - 1].bytes;
        if (SusamuneGhostReadBe32(p) <= endQf && (p[23] & 63) < segments) break;
        --h->count;
    }
}

bool evaluate(const void *bank, u32 qf, u8 segment, View *out) {
    const SusamuneGhostCameraHeader *h = header(const_cast<void *>(bank));
    if (!out || !sane(h) || !h->count) return false;
    const SusamuneGhostCameraSample *samples = reinterpret_cast<const SusamuneGhostCameraSample *>(h + 1);
    u32 lo = 0, hi = h->count;
    while (lo < hi) {
        const u32 mid = lo + (hi-lo)/2;
        if (SusamuneGhostReadBe32(samples[mid].bytes) <= qf) lo = mid+1;
        else hi = mid;
    }
    u32 index = lo ? lo-1 : 0;
    if ((samples[index].bytes[23] & 63) != segment) {
        if (index+1 >= h->count || (samples[index+1].bytes[23] & 63) != segment) return false;
        ++index;
    }
    const u32 firstQf = SusamuneGhostReadBe32(samples[index].bytes);
    if ((h->flags & SUSAMUNE_GHOST_CAMERA_TRUNCATED) && index+1 == h->count && qf > firstQf)
        return false;
    decode(samples[index], out);
    if (index+1 == h->count || qf <= firstQf ||
        samples[index+1].bytes[23] != segment) return true;
    View next;
    decode(samples[index+1], &next);
    const u32 nextQf = SusamuneGhostReadBe32(samples[index+1].bytes);
    const f32 t = static_cast<f32>(qf-firstQf) / static_cast<f32>(nextQf-firstQf);
    for (u32 i=0;i<3;++i) out->position[i] += (next.position[i]-out->position[i])*t;
    out->fovy += (next.fovy-out->fovy)*t;
    f32 dot=0;
    for (u32 i=0;i<4;++i) dot += out->rotation[i]*next.rotation[i];
    for (u32 i=0;i<4;++i)
        out->rotation[i] += ((dot<0 ? -next.rotation[i] : next.rotation[i])-out->rotation[i])*t;
    normalize(out->rotation);
    return true;
}
static_assert(SUSAMUNE_GHOST_CAMERA_BANK_OFFSET + SUSAMUNE_GHOST_CAMERA_MAX_SIZE <= 0x695e0,
              "camera exceeds the existing pose-bank tail");
}
