#include "susamune/collision_viewer.hxx"
#include "susamune/game_wireframe.hxx"
#include "susamune/menu.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"
#include "JSystem/JDrama/JDREfbCtrl.hxx"
#include "Dolphin/OS.h"

extern "C" u32 collisionEfbVtable[9] asm("__vt__Q26JDrama11TEfbCtrlTex");
extern "C" void collisionRetailEfbPerform(JDrama::TEfbCtrlTex *, u32, JDrama::TGraphics *)
    asm("perform__Q26JDrama11TEfbCtrlTexFUlPQ26JDrama9TGraphics");
extern "C" void GXGetProjectionv(f32 *);
extern "C" void ReInitializeGX();

namespace {
// Scene archive names use Shift-JIS on all three regions.
const char kNormalScene[] = "\x92\xca\x8f\xed\x83\x56\x81\x5b\x83\x93\x95\x60\x89\xe6\x83\x58\x83\x65\x81\x5b\x83\x57";

bool normalScene(const JDrama::TEfbCtrlTex *object) {
    const char *name = object->mKeyName;
    const u32 address = reinterpret_cast<u32>(name);
    if (address < 0x80000000u || address > 0x81800000u - sizeof(kNormalScene)) return false;
    for (unsigned i = 0; i < sizeof(kNormalScene); ++i)
        if (name[i] != kNormalScene[i]) return false;
    return true;
}

extern "C" void collisionScenePerform(JDrama::TEfbCtrlTex *object, u32 cue,
                                      JDrama::TGraphics *graphics) {
    // Later composite/HUD passes no longer have the world's depth buffer.
    const bool normalCopy = (cue & 8u) && normalScene(object);
    if (normalCopy) GameWireframe::endWorld();
    if (normalCopy && gSettings.get(SETTING_COLLISION_VIEWER) &&
        !StageLoader::modal() &&
        (!gMenu || !gMenu->shown()) && !WarpWheel::shown()) {
        f32 saved[7];
        GXGetProjectionv(saved);
        if (CollisionViewer::drawWorld()) {
            // ZBufferCatch just installed these defaults; indirect draws follow.
            ReInitializeGX();
            Mtx44 projection = {};
            const u8 type = saved[0] == 0 ? GX_PERSPECTIVE : GX_ORTHOGRAPHIC;
            projection[0][0] = saved[1];
            projection[0][type == GX_PERSPECTIVE ? 2 : 3] = saved[2];
            projection[1][1] = saved[3];
            projection[1][type == GX_PERSPECTIVE ? 2 : 3] = saved[4];
            projection[2][2] = saved[5];
            projection[2][3] = saved[6];
            GXSetProjection(projection, type);
        }
    }
    collisionRetailEfbPerform(object, cue, graphics);
}
}

void CollisionViewer::init() {
    for (unsigned i = 0; i < 9; ++i) {
        if (collisionEfbVtable[i] != reinterpret_cast<u32>(&collisionRetailEfbPerform) &&
            collisionEfbVtable[i] != reinterpret_cast<u32>(&collisionScenePerform)) continue;
        collisionEfbVtable[i] = reinterpret_cast<u32>(&collisionScenePerform);
        DCFlushRange(collisionEfbVtable + i, sizeof(u32));
        GameWireframe::init();
        break;
    }
    beginFrame();
}
