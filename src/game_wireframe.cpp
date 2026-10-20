#include "susamune/game_wireframe.hxx"
#include "susamune/game_wireframe_geometry.h"
#include "susamune/addresses.hxx"
#include "susamune/features.hxx"
#include "susamune/ghost_camera.hxx"
#include "susamune/menu.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"
#include "SMS/System/MarDirector.hxx"
#include "Dolphin/GX.h"

extern "C" void GXCallDisplayList(const void *, u32);
extern "C" void GXGetProjectionv(f32 *);

namespace GameWireframe {
namespace {
// Two inlined GXCallDisplayList calls in J3DShape::draw, identical in all revisions.
const u32 kDescriptorSite = SUSAMUNE_MEM1_ADDR(0x80029ee8u, 0x802e03b4u, 0x802d855cu);
const u32 kDrawSite = SUSAMUNE_MEM1_ADDR(0x80029ff8u, 0x802e04c4u, 0x802d866cu);
constexpr u32 kFrameInputBytes = 4 * 1024 * 1024;
constexpr u32 kFrameOutputBytes = 16 * 1024 * 1024;
u32 sStride, sInputBytes, sOutputBytes;
bool sWorld, sProjectionReady;
f32 sProjection[6];

bool mem1(const void *data, u32 size) {
    const u32 address = reinterpret_cast<u32>(data);
    return address >= 0x80000000u && address < 0x81800000u && size <= 0x81800000u - address;
}

bool enabled() {
    const TMarDirector *director = RetailInput::stageDirector();
    if (!sWorld || gSettings.get(SETTING_COLLISION_VIEWER) != 3 || !director ||
        !director->_260 || director->mCurState < TMarDirector::STATE_GAME_STARTING ||
        StageLoader::modal() || (gMenu && gMenu->shown()) || WarpWheel::shown()) return false;
    if (!sProjectionReady) {
        Mtx view;
        Mtx44 p;
        if (!GhostCamera::renderMatrices(view, p) || p[3][2] != -1) return false;
        sProjection[0] = p[0][0]; sProjection[1] = p[0][2];
        sProjection[2] = p[1][1]; sProjection[3] = p[1][2];
        sProjection[4] = p[2][2]; sProjection[5] = p[2][3];
        sProjectionReady = true;
    }
    f32 p[7];
    GXGetProjectionv(p);
    if (p[0] != 0) return false;
    for (unsigned i = 0; i < 6; ++i) if (p[i + 1] != sProjection[i]) return false;
    return true;
}

struct Fifo {
    bool started = false;
    void begin(unsigned primitive, unsigned count) {
        if (!started) {
            GXBegin(primitive, 0, count);
            started = true;
        } else {
            // Only vertex/header bytes follow: the SDK's dirty/flush state stays clean.
            *reinterpret_cast<volatile u8 *>(0xCC008000) = primitive;
            *reinterpret_cast<volatile u16 *>(0xCC008000) = count;
        }
    }
    void bytes(const unsigned char *data, unsigned size) {
        if (size >= 16) {
            // Count bytes explicitly: the PPC backend miscompiles the pointer-only loop.
            unsigned prefix = (0u - reinterpret_cast<u32>(data)) & 3;
            while (prefix--) {
                *reinterpret_cast<volatile u8 *>(0xCC008000) = *data++;
                --size;
            }
            while (size >= 4) {
                *reinterpret_cast<volatile u32 *>(0xCC008000) = *reinterpret_cast<const u32 *>(data);
                data += 4;
                size -= 4;
            }
        }
        while (size >= 4) {
            *reinterpret_cast<volatile u32 *>(0xCC008000) = GameWireframeGeometry::read32(data);
            data += 4;
            size -= 4;
        }
        while (size--) *reinterpret_cast<volatile u8 *>(0xCC008000) = *data++;
    }
};

extern "C" void wireframeDescriptor(const void *list, u32 size) {
    GXCallDisplayList(list, size);
    sStride = enabled() && mem1(list, size) ?
        GameWireframeGeometry::descriptorStride(static_cast<const u8 *>(list), size) : 0;
}

extern "C" void wireframeDraw(const void *list, u32 size) {
    unsigned bytes;
    if (sStride && size <= kFrameInputBytes - sInputBytes && mem1(list, size)) {
        sInputBytes += size;
        if (GameWireframeGeometry::validate(static_cast<const u8 *>(list), size, sStride,
                kFrameOutputBytes - sOutputBytes, &bytes)) {
            sOutputBytes += bytes;
            Fifo fifo;
            GameWireframeGeometry::emit(static_cast<const u8 *>(list), size, sStride, fifo);
            return;
        }
    }
    GXCallDisplayList(list, size);
}
}

void beginFrame() {
    sStride = sInputBytes = sOutputBytes = 0;
    sWorld = true;
    sProjectionReady = false;
}
void endWorld() { sWorld = false; sStride = 0; }

void init() {
    const u32 descriptor = branchWord(kDescriptorSite, reinterpret_cast<u32>(&wireframeDescriptor)) | 1;
    const u32 draw = branchWord(kDrawSite, reinterpret_cast<u32>(&wireframeDraw)) | 1;
    const u32 retailDescriptor = branchWord(kDescriptorSite, reinterpret_cast<u32>(&GXCallDisplayList)) | 1;
    const u32 retailDraw = branchWord(kDrawSite, reinterpret_cast<u32>(&GXCallDisplayList)) | 1;
    const volatile u32 *a = reinterpret_cast<const volatile u32 *>(kDescriptorSite);
    const volatile u32 *b = reinterpret_cast<const volatile u32 *>(kDrawSite);
    if ((*a != retailDescriptor && *a != descriptor) || (*b != retailDraw && *b != draw) ||
        a[-1] != 0x80630028u || b[-2] != 0x80640008u || b[-1] != 0x80840004u) return;
    writeGameCode(kDescriptorSite, descriptor);
    writeGameCode(kDrawSite, draw);
    beginFrame();
}
}
