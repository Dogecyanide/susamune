#include "susamune/ghost_fludd.hxx"
#include "Dolphin/math.h"
#include "Dolphin/mem.h"
#include "SMS/Player/Mario.hxx"
#include "SMS/Player/Watergun.hxx"
#include "SMS/Player/Yoshi.hxx"
#include "JSystem/J3D/J3DJoint.hxx"
#include "susamune/retail_input.hxx"

#pragma clang section text="" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

#if defined(__powerpc__)
// Retail hooks enter this owner at +1568 in every region; keep the prefix charged.
asm(".pushsection .foxtrot.text,\"ax\",@progbits\n.space 1568,0\n.popsection");
#endif

extern "C" f32 ghostSquareRoot(f32) asm("sqrtf__3stdFf");

extern "C" u8 ghostRetailWaterEmit(void *, const TWaterEmitInfo &)
    asm("emitRequest__18TModelWaterManagerFRC14TWaterEmitInfo");

namespace GhostFludd {
namespace {
TMario *sEmitter;
TVec3f sPosition, sDirection;
f32 sPower;
bool sEmitted, sBurst, sHoverEmitted;
u8 sNozzle;

bool finite(f32 value) { return value >= -1000000.0f && value <= 1000000.0f; }

bool captureYoshi(SusamuneGhostFluddSample &sample, TMario *mario) {
    TYoshi *yoshi = mario->mYoshi;
    if (!yoshi || yoshi->mState != TYoshi::MOUNTED) return false;
    MActor *actor = yoshi->mActor;
    if (!actor || !actor->mBckInfo || !actor->mModel ||
        !actor->mModel->mModelData || actor->mModel->mModelData->getJointNum() <= 21)
        return true;
    const s32 index = actor->getCurAnmIdx(MActor::BCK);
    const J3DFrameCtrl *frame = actor->getFrameCtrl(MActor::BCK);
    if (index < 0 || index >= 26 || !frame ||
        !finite(frame->mCurFrame) || frame->mCurFrame < 0 || frame->mCurFrame >= 4096)
        return true;
    u8 *p = reinterpret_cast<u8 *>(&sample);
    p[0] = SUSAMUNE_GHOST_VISUAL_YOSHI |
        (sEmitted && sEmitter == mario ? SUSAMUNE_GHOST_FLUDD_SPRAYING |
            (sBurst ? SUSAMUNE_GHOST_FLUDD_BURST : 0) : 0);
    p[1] = static_cast<u8>(index);
    u32 phase = static_cast<u32>(frame->mCurFrame * 16.0f + 0.5f);
    if (phase > 65535) phase = 65535;
    p[2] = static_cast<u8>(phase >> 8); p[3] = static_cast<u8>(phase);
    const f32 blend = actor->mBckInfo->getMotionBlendRatio();
    if (index == 15 && finite(blend) && blend > 0)
        p[4] = blend >= 1 ? 255 : static_cast<u8>(blend * 255.0f + 0.5f);
    const u8 *raw = reinterpret_cast<const u8 *>(yoshi);
    const J3DJoint *upper = actor->mModel->mModelData->mJoints[18];
    const void *calc = upper ? *reinterpret_cast<void *const *>(
        reinterpret_cast<const u8 *>(upper) + 0x58) : nullptr;
    if (calc && calc == *reinterpret_cast<void *const *>(raw + 0x54)) p[5] = 3;
    else if (calc && calc == *reinterpret_cast<void *const *>(raw + 0x58)) p[5] = 4;
    const J3DFrameCtrl *upperFrame = reinterpret_cast<const J3DFrameCtrl *>(raw + 0x5c);
    if (p[5] && upperFrame->mNumFrames > 0 && finite(upperFrame->mCurFrame)) {
        f32 ratio = upperFrame->mCurFrame / upperFrame->mNumFrames;
        if (ratio < 0) ratio = 0;
        p[6] = ratio >= 1 ? 255 : static_cast<u8>(ratio * 255.0f + 0.5f);
    }
    if (mario->mFludd && mario->mFludd->mCurrentNozzle < 6) {
        const TNozzleBase *nozzle = mario->mFludd->mNozzleList[mario->mFludd->mCurrentNozzle];
        if (nozzle) p[7] = static_cast<u8>(nozzle->getGunAngle() / 256);
    }
    return true;
}

void pack(SusamuneGhostFluddSample &out, TMario *mario, u8 nozzle,
          const TVec3f &position, const TVec3f &direction, bool spray, f32 power) {
    memset(&out, 0, sizeof(out));
    if (!finite(direction.x) || !finite(direction.y) || !finite(direction.z)) return;
    const f32 flat = ghostSquareRoot(direction.x * direction.x + direction.z * direction.z);
    if (flat + fabsf(direction.y) < 0.0001f) return;
    const f32 offset[3] = {position.x - mario->mTranslation.x,
                           position.y - mario->mTranslation.y,
                           position.z - mario->mTranslation.z};
    for (u32 i = 0; i < 3; ++i) {
        if (!finite(offset[i]) || offset[i] < -254.0f || offset[i] > 254.0f) return;
    }
    for (u32 i = 0; i < 3; ++i) {
        out.offset[i] = (s8)(offset[i] * 0.5f + (offset[i] < 0 ? -0.5f : 0.5f));
    }
    const f32 turnScale = 651.8986469f;
    const u32 yaw = (s32)(atan2f(direction.x, direction.z) * turnScale) & 4095u;
    const u32 pitch = (s32)(atan2f(direction.y, flat) * turnScale) & 4095u;
    out.aim[0] = (u8)(yaw >> 4);
    out.aim[1] = (u8)((yaw << 4) | (pitch >> 8));
    out.aim[2] = (u8)pitch;
    out.mode = nozzle | SUSAMUNE_GHOST_FLUDD_PRESENT |
        (spray ? SUSAMUNE_GHOST_FLUDD_SPRAYING : 0);
    if (spray && finite(power) && power > 0)
        out.power = (u8)(power >= 255 ? 255 : power + 0.5f);
}
}

void beginFrame() { sEmitter = nullptr; sEmitted = sBurst = sHoverEmitted = false; }
bool hoverEmitted() { return sHoverEmitted; }

void direction(const SusamuneGhostFluddSample &sample, TVec3f &out) {
    const u32 yaw = (sample.aim[0] << 4) | (sample.aim[1] >> 4);
    s32 pitch = ((sample.aim[1] & 15) << 8) | sample.aim[2];
    if (pitch & 2048) pitch -= 4096;
    const f32 angle = 0.001533980788f;
    const f32 flat = cosf(pitch * angle);
    out.set(sinf(yaw * angle) * flat, sinf(pitch * angle), cosf(yaw * angle) * flat);
}

void capture(SusamuneGhostFluddSample &sample) {
    memset(&sample, 0, sizeof(sample));
    TMario *mario = gpMarioOriginal;
    if (!RetailInput::stageDirector() || !mario) return;
    if (captureYoshi(sample, mario)) return;
    if (!mario->mAttributes.mHasFludd ||
        !mario->mFludd || mario->mFludd->mCurrentNozzle >= 6) return;
    TWaterGun *gun = mario->mFludd;
    if (sEmitted && sEmitter == mario) {
        pack(sample, mario, sNozzle, sPosition, sDirection, true, sPower);
        if (sample.mode && sBurst) sample.mode |= SUSAMUNE_GHOST_FLUDD_BURST;
    } else {
        Mtx *matrix = gun->getEmitMtx(0);
        if (!matrix) return;
        TVec3f position, direction;
        position.set((*matrix)[0][3], (*matrix)[1][3], (*matrix)[2][3]);
        direction.set((*matrix)[0][0], (*matrix)[1][0], (*matrix)[2][0]);
        pack(sample, mario, gun->mCurrentNozzle, position, direction, false, 0);
    }
}

void observe(const TWaterEmitInfo &info, u8 emitted) {
    TMario *mario = gpMarioOriginal;
    if (!emitted || !RetailInput::stageDirector() || !mario || !mario->mFludd ||
        mario->mFludd->mEmitInfo != &info) return;
    if (mario->mFludd->mCurrentNozzle == TWaterGun::Hover) sHoverEmitted = true;
    const TWaterGun *gun = mario->mFludd;
    const bool burst =
        (gun->mCurrentNozzle == TWaterGun::Spray &&
         gun->mNozzleDeformBomb.mSprayState == TNozzleTrigger::ACTIVE) ||
        (gun->mCurrentNozzle == TWaterGun::Yoshi &&
         gun->mNozzleYoshiDeformBomb.mSprayState == TNozzleTrigger::ACTIVE);
    if (sEmitted && sBurst && !burst) return;
    // Observe the actual accepted emission, not R: an empty tank, nozzle switch
    // or full retail particle pool can suppress water despite held input.
    sEmitter = mario;
    sNozzle = mario->mFludd->mCurrentNozzle;
    sPosition = info.mPos.get();
    sDirection = info.mDir.get();
    sPower = info.mPow.get();
    sBurst = burst;
    sEmitted = true;
}
}

#pragma clang section text=".foxtrot.text"
extern "C" u8 susamuneGhostWaterEmit(void *manager, const TWaterEmitInfo &info) {
    const u8 emitted = ghostRetailWaterEmit(manager, info);
    GhostFludd::observe(info, emitted);
    return emitted;
}
