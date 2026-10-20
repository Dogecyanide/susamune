#ifndef SUSAMUNE_COLLISION_PROJECTION_H
#define SUSAMUNE_COLLISION_PROJECTION_H
// Clip in homogeneous camera space before dividing by depth.
static inline int SusamuneCollisionClip(float a[3], float b[3], float nearPlane, float farPlane) {
    float lo = 0, hi = 1;
    const float av[6] = {a[2]-nearPlane, farPlane-a[2], a[2]+a[0], a[2]-a[0], a[2]+a[1], a[2]-a[1]};
    const float bv[6] = {b[2]-nearPlane, farPlane-b[2], b[2]+b[0], b[2]-b[0], b[2]+b[1], b[2]-b[1]};
    unsigned int i;
    for (i = 0; i < 6; ++i) {
        if (av[i] < 0 && bv[i] < 0) return 0;
        if (av[i] < 0 || bv[i] < 0) {
            const float t = av[i] / (av[i] - bv[i]);
            if (av[i] < 0) { if (t > lo) lo = t; }
            else if (t < hi) hi = t;
        }
    }
    if (lo > hi) return 0;
    for (i = 0; i < 3; ++i) {
        const float delta = b[i] - a[i];
        b[i] = a[i] + delta * hi;
        a[i] += delta * lo;
    }
    return 1;
}
#endif
