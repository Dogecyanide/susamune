#include "susamune/model_editor_preview.hxx"
#include "susamune/addresses.hxx"
#include "susamune/menu.hxx"
#include "susamune/retail_input.hxx"
#include "Dolphin/math.h"
#include "Dolphin/mem.h"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/System/MarDirector.hxx"

#pragma clang section text="" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

extern "C" void susamunePracticeCameraPerform(CPolarSubCamera *, u32, JDrama::TGraphics *);

namespace ModelEditorPreview {
void restorePracticeCamera();
namespace {
bool sRequested, sApplied;
f32 sYaw, sPitch;
CPolarSubCamera *sCamera;
TMarDirector *sDirector;
TVec3f sPosition, sTarget, sUp;
f32 sFovy;
u8 sRender[0x138];
static_assert(__builtin_offsetof(CPolarSubCamera, mWorldTranslation) == 0x124 &&
              __builtin_offsetof(CPolarSubCamera, mTRSMatrix) == 0x1ec &&
              __builtin_offsetof(CPolarSubCamera, mAngleYaw) == 0x258,
              "colour-preview camera range changed");

bool ready() {
    return RetailInput::stageDirector() == gpMarDirector && gpMarDirector &&
        gpMarDirector->_260 && gpMarioOriginal && gpCamera;
}
f32 stick(u8 sample) {
    const int value = static_cast<s8>(sample);
    return value < -16 ? (value + 16) / 64.0f :
           value > 16 ? (value - 16) / 64.0f : 0.0f;
}
}  // namespace

void begin(bool fludd) {
    restore();
    sRequested = ready();
    if (!sRequested) return;
    sYaw = gpMarioOriginal->mAngle.y * 0.00009587379924f +
        (fludd ? 3.14159265f : 0.0f);
    sPitch = 0.20f;
}

void end() {
    restore();
    sRequested = false;
}

bool wanted() {
    return sRequested && ready() && gMenu && gMenu->shown();
}

void update() {
    if (!wanted()) return;
    const PADStatus &pad = JUTGamePad::mPadStatus[0];
    if (pad.mCurError) return;
    sYaw -= stick(pad.mStickX) * 0.045f;
    if (sYaw > 3.14159265f) sYaw -= 6.2831853f;
    if (sYaw < -3.14159265f) sYaw += 6.2831853f;
    sPitch += stick(pad.mStickY) * 0.025f;
    if (sPitch < -0.10f) sPitch = -0.10f;
    if (sPitch > 0.70f) sPitch = 0.70f;
}

void apply(CPolarSubCamera *camera) {
    if (sApplied || !wanted() || camera != gpCamera) return;
    sCamera = camera;
    sDirector = gpMarDirector;
    sPosition = camera->mTranslation;
    sTarget = camera->mTargetPos;
    sUp = camera->mUpVector;
    sFovy = camera->mProjectionFovy;
    memcpy(sRender, reinterpret_cast<u8 *>(camera) + 0x124, sizeof(sRender));

    // Aim at his feet so the character occupies the area above the editor.
    TVec3f target = gpMarioOriginal->mTranslation;
    TVec3f position;
    const f32 radius = 460.0f * cosf(sPitch);
    position.set(target.x + sinf(sYaw) * radius,
                 target.y + sinf(sPitch) * 460.0f,
                 target.z + cosf(sYaw) * radius);
    const TVec3f up = {0.0f, 1.0f, 0.0f};
    camera->mTranslation = position;
    camera->mTargetPos = target;
    camera->mUpVector = up;
    camera->mProjectionFovy = 45.0f;
    camera->mWorldTranslation = position;
    *reinterpret_cast<TVec3f *>(reinterpret_cast<u8 *>(camera) + 0x148) = target;
    C_MTXPerspective(reinterpret_cast<f32 (*)[4]>(
        reinterpret_cast<u8 *>(camera) + 0x16c), 45.0f,
        camera->mProjectionAspect, camera->mProjectionNear, camera->mProjectionFar);
    C_MTXLookAt(camera->mTRSMatrix, reinterpret_cast<const Vec *>(&position),
        reinterpret_cast<const Vec *>(&up), reinterpret_cast<const Vec *>(&target));
    camera->mAngleYaw = static_cast<s16>(sYaw * 10430.37835f);
    camera->mAnglePitch = static_cast<s16>(sPitch * 10430.37835f);
    sApplied = true;
}

void restore() {
    if (!sApplied) return;
    if (ready() && sCamera == gpCamera && sDirector == gpMarDirector) {
        sCamera->mTranslation = sPosition;
        sCamera->mTargetPos = sTarget;
        sCamera->mUpVector = sUp;
        sCamera->mProjectionFovy = sFovy;
        memcpy(reinterpret_cast<u8 *>(sCamera) + 0x124, sRender, sizeof(sRender));
    }
    sApplied = false;
}

void restoreAll() {
    restore();
    restorePracticeCamera();
}

void perform(CPolarSubCamera *camera, u32 cue, JDrama::TGraphics *graphics) {
    if (wanted() && camera == gpCamera && (cue & 0x14u)) {
        if (cue & ~0x14u)
            susamunePracticeCameraPerform(camera, cue & ~0x14u, graphics);
        apply(camera);
        reinterpret_cast<void (*)(CPolarSubCamera *, u32, JDrama::TGraphics *)>(
            SUSAMUNE_MEM1_ADDR(0x80352f70u, 0x80023004u, 0x800230bcu))(
                camera, cue & 0x14u, graphics);
        return;
    }
    susamunePracticeCameraPerform(camera, cue, graphics);
}

void drawHint(Menu *menu) {
    if (!menu || !wanted()) return;
    const char *text = "Main stick: rotate preview";
    menu->fillBox(151, 8, 338, 21, JUtility::TColor(18, 55, 57, 220));
    menu->drawText(text, 320 - Menu::textWidth(text, 14) / 2, 11, 14, 14,
                   JUtility::TColor(255, 245, 204, 255));
}
}  // namespace ModelEditorPreview
