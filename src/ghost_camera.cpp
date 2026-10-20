#include "susamune/ghost_camera.hxx"
#include "susamune/ghost.hxx"
#include "susamune/addresses.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/settings.hxx"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "Dolphin/MTX.h"
#include "Dolphin/OS.h"
#include "Dolphin/math.h"
#include "Dolphin/string.h"
#include "Dolphin/mem.h"

extern "C" void susamunePracticeCameraPerform(CPolarSubCamera *, u32, JDrama::TGraphics *);

extern "C" f32 retailSquareRoot(f32) asm("sqrtf__3stdFf");

namespace GhostCamera {
namespace {
const u32 kCameraPerform = SUSAMUNE_MEM1_ADDR(0x80352f70u, 0x80023004u, 0x800230bcu);
const u32 kCameraVtable = SUSAMUNE_MEM1_ADDR(0x803e4820u, 0x803acde8u, 0x803a5168u);
CPolarSubCamera *sOwner;
TMarDirector *sDirector;
const void *sHeap;
u32 sGeneration, sOwnerGeneration, sRenderedGeneration;
TVec3f sPosition, sTarget, sUp;
f32 sFovy;
u8 sRenderSaved[0x138];
View sRendered;
bool sRenderedValid;
Mtx sDrawView;
Mtx44 sDrawProjection;
bool sDrawValid;

bool ready() {
    const u32 address = reinterpret_cast<u32>(gpCamera);
    return RetailInput::stageDirector() == gpMarDirector && gpMarDirector &&
        gpMarDirector->_260 && address >= 0x80000000u &&
        address <= 0x81800000u - sizeof(CPolarSubCamera);
}

void readRendered(CPolarSubCamera *camera) {
    // The director draws the prepared scene before preparing its next one.
    if (!sDrawValid) {
        memcpy(sDrawView, camera->mTRSMatrix, sizeof(sDrawView));
        memcpy(sDrawProjection, reinterpret_cast<u8 *>(camera) + 0x16c,
               sizeof(sDrawProjection));
        sDrawValid = true;
    }
    const f32 (*m)[4] = camera->mTRSMatrix;
    View v;
    memcpy(v.position, &camera->mWorldTranslation, sizeof(v.position));
    v.fovy = camera->mProjectionFovy;
    const f32 trace = m[0][0] + m[1][1] + m[2][2];
    if (trace > 0) {
        const f32 s = retailSquareRoot(trace + 1) * 2;
        v.rotation[3] = s * 0.25f;
        v.rotation[0] = (m[2][1] - m[1][2]) / s;
        v.rotation[1] = (m[0][2] - m[2][0]) / s;
        v.rotation[2] = (m[1][0] - m[0][1]) / s;
    } else {
        u32 i = m[1][1] > m[0][0] ? 1 : 0;
        if (m[2][2] > m[i][i]) i = 2;
        const u32 j = (i+1)%3, k = (j+1)%3;
        const f32 s = retailSquareRoot(1 + m[i][i] - m[j][j] - m[k][k]) * 2;
        v.rotation[i] = s * 0.25f;
        v.rotation[j] = (m[i][j] + m[j][i]) / s;
        v.rotation[k] = (m[i][k] + m[k][i]) / s;
        v.rotation[3] = (m[k][j] - m[j][k]) / s;
    }
    SusamuneGhostCameraSample checked;
    sRenderedValid = encode(v, 0, SUSAMUNE_GHOST_CAMERA_CUT, &checked);
    if (sRenderedValid) sRendered = v;
    sRenderedGeneration = sGeneration;
}

void apply(CPolarSubCamera *camera, const View &view) {
    restore();
    sOwner = camera;
    sDirector = gpMarDirector;
    sHeap = gpApplication.mCurrentHeap;
    sOwnerGeneration = sGeneration;
    sPosition = camera->mTranslation;
    sTarget = camera->mTargetPos;
    sUp = camera->mUpVector;
    sFovy = camera->mProjectionFovy;
    memcpy(sRenderSaved, reinterpret_cast<u8 *>(camera)+0x124, sizeof(sRenderSaved));
    f32 m[3][3];
    matrix(view, m);
    TVec3f position, target, up;
    memcpy(&position, view.position, sizeof(position));
    target.set(position.x - m[2][0]*1000, position.y - m[2][1]*1000,
               position.z - m[2][2]*1000);
    up.set(m[1][0], m[1][1], m[1][2]);
    camera->mTranslation = camera->mWorldTranslation = position;
    camera->mTargetPos = target;
    camera->mUpVector = up;
    camera->mProjectionFovy = view.fovy;
    *reinterpret_cast<TVec3f *>(reinterpret_cast<u8 *>(camera)+0x148) = target;
    C_MTXPerspective(reinterpret_cast<f32 (*)[4]>(reinterpret_cast<u8 *>(camera)+0x16c),
                     view.fovy, camera->mProjectionAspect, camera->mProjectionNear,
                     camera->mProjectionFar);
    C_MTXLookAt(camera->mTRSMatrix, reinterpret_cast<const Vec *>(&position),
                reinterpret_cast<const Vec *>(&up), reinterpret_cast<const Vec *>(&target));
    camera->mAngleYaw = static_cast<s16>(static_cast<s32>(atan2f(-m[2][0], -m[2][2])*10430.37835f+32768));
    camera->mAnglePitch = static_cast<s16>(atan2f(m[2][1], retailSquareRoot(m[2][0]*m[2][0]+m[2][2]*m[2][2]))*10430.37835f);
}
}

void restore() {
    if (!sOwner) return;
    if (sOwnerGeneration == sGeneration && sOwner == gpCamera &&
        sDirector == gpMarDirector && sHeap == gpApplication.mCurrentHeap && ready()) {
        sOwner->mTranslation = sPosition;
        sOwner->mTargetPos = sTarget;
        sOwner->mUpVector = sUp;
        sOwner->mProjectionFovy = sFovy;
        memcpy(reinterpret_cast<u8 *>(sOwner)+0x124, sRenderSaved, sizeof(sRenderSaved));
    }
    sOwner = nullptr;
}

void onStageSetup() {
    // The old heap may already have been reused; discard without dereferencing.
    sOwner = nullptr;
    ++sGeneration;
    sRenderedValid = false;
    sDrawValid = false;
}

void beginFrame() { sDrawValid = false; }

bool renderMatrices(Mtx view, Mtx44 projection) {
    if (!sDrawValid || !ready()) return false;
    memcpy(view, sDrawView, sizeof(sDrawView));
    memcpy(projection, sDrawProjection, sizeof(sDrawProjection));
    return true;
}

bool captureView(View *out) {
    if (!out || !sRenderedValid || sRenderedGeneration != sGeneration || !ready()) return false;
    *out = sRendered;
    return true;
}

extern "C" void susamuneGhostCameraPerform(CPolarSubCamera *camera, u32 cue,
                                          JDrama::TGraphics *graphics) {
    if (cue & 3u) restore();
    View view;
    const bool recorded = camera == gpCamera && (cue & 0x14u) && ready() &&
        gSettings.get(SETTING_GHOST_CAMERA) == 1 && Ghost::recordedCameraView(&view);
    if (recorded) {
        if (cue & ~0x14u) susamunePracticeCameraPerform(camera, cue & ~0x14u, graphics);
        apply(camera, view);
        // Recorded Watch owns draw only; Free continues through the existing hook.
        reinterpret_cast<void (*)(CPolarSubCamera *, u32, JDrama::TGraphics *)>(kCameraPerform)(
            camera, cue & 0x14u, graphics);
    } else susamunePracticeCameraPerform(camera, cue, graphics);
    if (camera == gpCamera && (cue & 0x14u) && ready()) readRendered(camera);
}

void init() {
    u32 *table = reinterpret_cast<u32 *>(kCameraVtable);
    for (u32 i = 0; i < 32; ++i) {
        if (table[i] != reinterpret_cast<u32>(&susamunePracticeCameraPerform)) continue;
        table[i] = reinterpret_cast<u32>(&susamuneGhostCameraPerform);
        DCFlushRange(table+i, sizeof(u32));
        break;
    }
    onStageSetup();
}
}
