#ifndef SUSAMUNE_COLLISION_GEOMETRY_H
#define SUSAMUNE_COLLISION_GEOMETRY_H
enum SusamuneCollisionColor {
    SUSAMUNE_COLLISION_FLOOR, SUSAMUNE_COLLISION_SLIPPERY,
    SUSAMUNE_COLLISION_VERY_SLIPPERY, SUSAMUNE_COLLISION_SLIDER,
    SUSAMUNE_COLLISION_NO_SLIP,
    SUSAMUNE_COLLISION_WET, SUSAMUNE_COLLISION_WATER,
    SUSAMUNE_COLLISION_SAND, SUSAMUNE_COLLISION_WARP,
    SUSAMUNE_COLLISION_WALL, SUSAMUNE_COLLISION_CEILING,
    SUSAMUNE_COLLISION_OOB, SUSAMUNE_COLLISION_CURRENT
};
static inline unsigned SusamuneCollisionPlane(unsigned type, float normalY) {
    return type == 0x801 || normalY > 0.2f ? 0 : normalY < -0.2f ? 1 : 2;
}
static inline unsigned SusamuneCollisionColorFor(unsigned type, unsigned plane) {
    if (type == 0x600 || type == 0x800) return SUSAMUNE_COLLISION_OOB;
    if (plane == 2) return SUSAMUNE_COLLISION_WALL;
    if (plane == 1) return SUSAMUNE_COLLISION_CEILING;
    if ((type & 0x3fff) == 1) return SUSAMUNE_COLLISION_VERY_SLIPPERY;
    if (type == 2 || type == 0x8002) return SUSAMUNE_COLLISION_SLIPPERY;
    if (type == 0xc || type == 0x800c || type == 0xa00c) return SUSAMUNE_COLLISION_SLIDER;
    if (type == 3 || type == 0x8003) return SUSAMUNE_COLLISION_NO_SLIP;
    if ((type & 0x3fff) == 4 || type == 0x500) return SUSAMUNE_COLLISION_WET;
    if ((type >= 0x100 && type <= 0x105) || type == 0x4104) return SUSAMUNE_COLLISION_WATER;
    if ((type & 0x3fff) == 0x701) return SUSAMUNE_COLLISION_SAND;
    if (type >= 0x200 && type <= 0x203) return SUSAMUNE_COLLISION_WARP;
    return SUSAMUNE_COLLISION_FLOOR;
}
static inline int SusamuneCollisionArrayMember(unsigned address, unsigned base,
                                               unsigned count, unsigned stride) {
    return address >= base && (address - base) % stride == 0 &&
        (address - base) / stride < count;
}
/* Common-plane rejection only; GX clips crossing triangles before division. */
static inline unsigned SusamuneCollisionOutcode(float x, float y, float z, float w) {
    return (x < -w ? 1u : 0u) | (x > w ? 2u : 0u) |
        (y < -w ? 4u : 0u) | (y > w ? 8u : 0u) |
        (z < -w ? 16u : 0u) | (z > 0 ? 32u : 0u);
}
#endif
