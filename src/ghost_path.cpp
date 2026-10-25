#include "susamune/ghost_path.hxx"
#include "susamune/ghost_camera.hxx"
#include "susamune/menu.hxx"

#pragma clang section text=".foxtrot.text"
namespace GhostPath {
namespace {

const u32 kMaxEdges = 96;
struct Point { f32 x, y, z; };
struct Clip { f32 x, y, z, w; };

f32 coordinate(const u8 *p) {
    const u32 value = (static_cast<u32>(p[0]) << 16) |
                      (static_cast<u32>(p[1]) << 8) | p[2];
    return static_cast<s32>((value ^ 0x800000u) - 0x800000u) * 0.125f;
}

Point position(const SusamuneGhostPoseSample &pose) {
    return {coordinate(pose.x), coordinate(pose.y) + 8.0f, coordinate(pose.z)};
}

Clip project(const Point &p, const Mtx view, const Mtx44 projection) {
    f32 v[4] = {0, 0, 0, 1};
    for (unsigned i = 0; i < 3; ++i)
        v[i] = view[i][0] * p.x + view[i][1] * p.y +
               view[i][2] * p.z + view[i][3];
    f32 c[4];
    for (unsigned i = 0; i < 4; ++i)
        c[i] = projection[i][0] * v[0] + projection[i][1] * v[1] +
               projection[i][2] * v[2] + projection[i][3];
    return {c[0], c[1], c[2], c[3]};
}

bool clipPlane(f32 a, f32 b, f32 &first, f32 &last) {
    if (a < 0 && b < 0) return false;
    if (a < 0 || b < 0) {
        const f32 t = a / (a - b);
        if (a < 0) { if (t > first) first = t; }
        else if (t < last) last = t;
    }
    return first <= last;
}

bool screenLine(const Clip &a, const Clip &b, s16 (&xy)[4]) {
    f32 first = 0, last = 1;
    // GX uses -w <= z <= 0. Clip before division, including the camera plane.
    if (!clipPlane(a.w - 0.01f, b.w - 0.01f, first, last) ||
        !clipPlane(a.x + a.w, b.x + b.w, first, last) ||
        !clipPlane(a.w - a.x, b.w - b.x, first, last) ||
        !clipPlane(a.y + a.w, b.y + b.w, first, last) ||
        !clipPlane(a.w - a.y, b.w - b.y, first, last) ||
        !clipPlane(a.z + a.w, b.z + b.w, first, last) ||
        !clipPlane(-a.z, -b.z, first, last)) return false;
    for (unsigned i = 0; i < 2; ++i) {
        const f32 t = i ? last : first;
        const f32 w = a.w + (b.w - a.w) * t;
        const f32 x = (a.x + (b.x - a.x) * t) / w;
        const f32 y = (a.y + (b.y - a.y) * t) / w;
        xy[i * 2] = static_cast<s16>((x + 1.0f) * 320.0f);
        xy[i * 2 + 1] = static_cast<s16>((1.0f - y) * 240.0f);
    }
    return true;
}

} // namespace

void draw(Menu *menu, const SusamuneGhostPoseSample *poses, u32 count,
          bool secondary) {
    if (!menu || !poses || count < 2 || count > SUSAMUNE_GHOST_MAX_SAMPLE_COUNT)
        return;
    Mtx view;
    Mtx44 projection;
    if (!GhostCamera::renderMatrices(view, projection)) return;
    const u32 edges = count - 1 < kMaxEdges ? count - 1 : kMaxEdges;
    const JUtility::TColor color = secondary
        ? JUtility::TColor(255, 185, 65, 160)
        : JUtility::TColor(70, 220, 255, 160);
    Point previous = position(poses[0]);
    Clip a = project(previous, view, projection);
    for (u32 i = 1; i <= edges; ++i) {
        const Point current = position(poses[i * (count - 1) / edges]);
        const Clip b = project(current, view, projection);
        const f32 dx = current.x - previous.x, dy = current.y - previous.y;
        const f32 dz = current.z - previous.z;
        s16 xy[4];
        // Do not span large pose jumps or long decimation gaps with a chord.
        if (dx * dx + dy * dy + dz * dz <= 1600.0f * 1600.0f &&
            screenLine(a, b, xy)) menu->strokePoly(xy, 2, color);
        previous = current;
        a = b;
    }
}

} // namespace GhostPath
