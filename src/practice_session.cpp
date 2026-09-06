#include "susamune/practice_session.hxx"
#include "susamune/actions.hxx"
#include "susamune/addresses.hxx"
#include "susamune/binds.hxx"
#include "susamune/crash_report.hxx"
#include "susamune/features.hxx"
#include "susamune/ghost.hxx"
#include "susamune/ghost_storage.h"
#include "susamune/iling.hxx"
#include "susamune/menu.hxx"
#include "susamune/records.hxx"
#include "susamune/savestate.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"
#include "Dolphin/math.h"
#include "Dolphin/MTX.h"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"
#include "Dolphin/string.h"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/CardManager.hxx"

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

extern SavestateManager *gSavestateMgr;

namespace {

const u32 kPadRead = SUSAMUNE_MEM1_ADDR(0x80011bd8u, 0x802c8b9cu, 0x802c0c30u);
const u32 kStickMode = SUSAMUNE_MEM1_ADDR(0x80408ad0u, 0x8040cc10u, 0x80404370u);
const u32 kCameraPerform = SUSAMUNE_MEM1_ADDR(0x80352f70u, 0x80023004u, 0x800230bcu);
const u32 kCameraVtable = SUSAMUNE_MEM1_ADDR(0x803e4820u, 0x803acde8u, 0x803a5168u);
const u32 kDirectorMovement = SUSAMUNE_MEM1_ADDR(0x800eda30u, 0x8029a4acu, 0x80292344u);
const u32 kHitCheck = SUSAMUNE_MEM1_ADDR(0x801151f8u, 0x8021b900u, 0x80213854u);
const u32 kHitClear = SUSAMUNE_MEM1_ADDR(0x80114dd8u, 0x8021b4e0u, 0x80213434u);
const u32 kHitCheckCall = SUSAMUNE_MEM1_ADDR(0x800ed07cu, 0x80299af8u, 0x80291990u);
const u32 kHitClearCall = SUSAMUNE_MEM1_ADDR(0x800ed088u, 0x80299b04u, 0x8029199cu);
const u32 kChangeState = SUSAMUNE_MEM1_ADDR(0x800ec404u, 0x80298e80u, 0x80290d18u);
const u32 kChangeStateCall = SUSAMUNE_MEM1_ADDR(0x800ed290u, 0x80299d0cu, 0x80291ba4u);
const u32 kMaxFrames = 4096;
const u8 kSpinFrames = 9;

struct Frame {
    SusamunePracticeInput input;
    u32 fingerprint;
};
static_assert(sizeof(Frame) == 16, "practice frame size");
static_assert(sizeof(Frame) * kMaxFrames == SUSAMUNE_PRACTICE_TAPE_SIZE,
              "practice frames must exactly fill their reserved window");
Frame *const sFrames = reinterpret_cast<Frame *>(SUSAMUNE_PRACTICE_TAPE_PPC_BASE);

bool tapeStorageReady() {
#if IS_EMULATOR
    return true;
#else
    volatile SusamuneGhostStorageMailbox *mailbox = SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    DCInvalidateRange((void *)&mailbox->response, sizeof(mailbox->response));
    // The memory contract exists even when SD storage is unavailable.
    return mailbox->response.responseMagic == SUSAMUNE_GHOST_STORAGE_MAGIC &&
           mailbox->response.protocolVersion == SUSAMUNE_GHOST_STORAGE_VERSION;
#endif
}

struct PadHistory {
    u8 shared[80];
    u8 controls[80];
    u8 meaning[0x4c];
};
static_assert(sizeof(JUTGamePad::CButton) == 48 &&
              sizeof(JUTGamePad::CStick) == 16,
              "practice decoder layout");
static_assert(__builtin_offsetof(TMarioGamePad, _A4) == 0xa4 &&
              sizeof(TMarioGamePad) == 0xf0, "practice meaning layout");

PadHistory sBeforeRead;
PadHistory sSeedPad;
TMarioGamePad *sReadPad;
SusamunePracticeInput sPhysical;
SusamunePracticeInput sConsumed;
bool sHaveRead;
bool sConsumedFrame;
bool sPadHookReady;
bool sCameraHookReady;
bool sMovementHookReady;
bool sCollisionHooksReady;
bool sStateHookReady;
bool sPaused;
bool sPausePending;
bool sBorrowedPause;
bool sStepQueued;
bool sStepping;
bool sFreeze;
bool sModal;
bool sAssisted;
bool sFreeCamera;
bool sCameraWaitButtons;
bool sCameraApplied;
bool sRecord;
bool sReplay;
bool sOwnLoad;
bool sSeedValid;
bool sFrameInjected;
bool sSpinApplied;
bool sSpinClockwise;
u8 sSpinRemaining;
u8 sLoadKind;
u8 sMenuAction;
u16 sLoadWait;
u32 sStageGeneration;
u32 sSeedGeneration;
u32 sTapeSeed;
u32 sCount;
u32 sCursor;
u32 sSteps;
u32 sSettingsHash;
u32 sTapeHash;
u32 sSeedStage;
u32 sTapeStage;
u32 sSeedHeap;
u16 sPriorButtons;
u16 sStripButtons;
const char *sStatus = "Save a state before recording";

alignas(32) u32 sPadReadTail[2];
alignas(32) u32 sMovementTail[2];

struct CameraView {
    TVec3f position;
    TVec3f target;
    TVec3f up;
    f32 fovy;
};
CameraView sCameraSaved;
CameraView sCameraView;
u8 sCameraRenderSaved[0x138];
static_assert(__builtin_offsetof(CPolarSubCamera, mWorldTranslation) == 0x124 &&
              __builtin_offsetof(CPolarSubCamera, mProjectionMatrix) == 0x16c &&
              __builtin_offsetof(CPolarSubCamera, mTRSMatrix) == 0x1ec &&
              __builtin_offsetof(CPolarSubCamera, mAngleYaw) == 0x258,
              "retail camera render offsets");
CPolarSubCamera *sCamera;
u32 sCameraGeneration;
f32 sYaw;
f32 sPitch;

bool mem1(const void *ptr, u32 size) {
    const u32 address = reinterpret_cast<u32>(ptr);
    return address >= 0x80003100u && address < 0x81800000u &&
           size <= 0x81800000u - address;
}

bool stageReady() {
    return gpApplication.mContext == TApplication::CONTEXT_DIRECT_STAGE &&
           mem1(gpMarDirector, sizeof(TMarDirector)) &&
           gpMarDirector->_260 != 0 &&
           mem1(gpApplication.mGamePads[0], sizeof(TMarioGamePad)) &&
           mem1(gpMarioOriginal, sizeof(TMario));
}

bool normalStage() {
    return stageReady() && gpMarDirector->mCurState == TMarDirector::STATE_NORMAL;
}

bool controlStage() {
    return stageReady() &&
           (gpMarDirector->mCurState == TMarDirector::STATE_NORMAL ||
            gpMarDirector->mCurState == TMarDirector::STATE_PAUSE_MENU);
}

bool observerTransition() {
    return Ghost::observerLoading() || Ghost::observerCleanupPending();
}

bool actionableStage(bool secondaryTick = false) {
    if (!normalStage() || observerTransition()) return false;
    if (Ghost::observerActive()) return true;
    const TMarioGamePad *pad = gpApplication.mGamePads[0];
    const u16 flags = *reinterpret_cast<const u16 *>(
        reinterpret_cast<const u8 *>(pad) + 0xe2);
    // Secondary ticks decode the pad again and decrement its disabled counter.
    return (flags & 2u) && !(flags & 0x99u) && !pad->mState.mDisable &&
           static_cast<s32>(pad->_E8) <= (secondaryTick ? 1 : 0) &&
           gpMarDirector->mDemoState == 0 && !(gpMarioOriginal->mState & 0x1000u);
}

void message(const char *text) {
    sStatus = text;
    if (gMenu) gMenu->toast(text);
}

void invalidate() {
    sAssisted = true;
    ILing::invalidateForAssist();
    Records::invalidateAttempt();
    Ghost::invalidateForAssist();
}

bool activatePendingPause(bool secondaryTick = false) {
    if (!sPausePending || sModal || !actionableStage(secondaryTick)) return false;
    sPausePending = false;
    sPaused = true;
    sStepQueued = false;
    sFreeze = true;
    invalidate();
    message("Gameplay paused - press Step to advance");
    return true;
}

u32 hashBytes(u32 hash, const void *data, u32 count) {
    const u8 *bytes = static_cast<const u8 *>(data);
    for (u32 i = 0; i < count; ++i) hash = (hash ^ bytes[i]) * 16777619u;
    return hash;
}

u32 settingsHash() {
    u32 hash = 2166136261u;
    for (int i = 0; i < SETTING_COUNT; ++i) {
        const u8 value = gSettings.get(static_cast<SettingId>(i));
        hash = (hash ^ value) * 16777619u;
    }
    const f32 cadence = SMSGetVSyncTimesPerSec();
    hash = hashBytes(hash, &cadence, sizeof(cadence));
    return hashBytes(hash, reinterpret_cast<const void *>(kStickMode), 4);
}

u32 fingerprint() {
    if (!stageReady()) return 0;
    const TMario *mario = gpMarioOriginal;
    u32 hash = hashBytes(2166136261u, &mario->mTranslation, sizeof(TVec3f));
    hash = hashBytes(hash, &mario->mSpeed, sizeof(TVec3f));
    hash = hashBytes(hash, &mario->mState, sizeof(mario->mState));
    hash = hashBytes(hash, &mario->mSubState, sizeof(mario->mSubState));
    hash = hashBytes(hash, &mario->mSubStateTimer, sizeof(mario->mSubStateTimer));
    hash = hashBytes(hash, &mario->mHealth, sizeof(mario->mHealth));
    hash = hashBytes(hash, reinterpret_cast<const void *>(SUSAMUNE_ADDR_LIBC_RAND_SEED), 4);
    if (TFlagManager::smInstance) {
        const s32 coins = TFlagManager::smInstance->getFlag(0x40002);
        hash = hashBytes(hash, &coins, sizeof(coins));
    }
    return hash;
}

void capturePad(PadHistory &out, TMarioGamePad *pad) {
    memcpy(out.shared, &JUTGamePad::mPadButton[0], 48);
    memcpy(out.shared + 48, &JUTGamePad::mPadMStick[0], 16);
    memcpy(out.shared + 64, &JUTGamePad::mPadSStick[0], 16);
    memcpy(out.controls, &pad->mButtons, sizeof(out.controls));
    memcpy(out.meaning, &pad->_A4, sizeof(out.meaning));
}

void restorePad(const PadHistory &in, TMarioGamePad *pad) {
    memcpy(&JUTGamePad::mPadButton[0], in.shared, 48);
    memcpy(&JUTGamePad::mPadMStick[0], in.shared + 48, 16);
    memcpy(&JUTGamePad::mPadSStick[0], in.shared + 64, 16);
    memcpy(&pad->mButtons, in.controls, sizeof(in.controls));
    memcpy(&pad->_A4, in.meaning, sizeof(in.meaning));
}

SusamunePracticeInput snapshot(const PADStatus &pad) {
    SusamunePracticeInput out;
    out.buttons = pad.mButton;
    out.stickX = static_cast<s8>(pad.mStickX);
    out.stickY = static_cast<s8>(pad.mStickY);
    out.substickX = static_cast<s8>(pad.mSubStickX);
    out.substickY = static_cast<s8>(pad.mSubStickY);
    out.triggerL = pad.mTriggerLeft;
    out.triggerR = pad.mTriggerRight;
    out.analogA = pad.mAnalogA;
    out.analogB = pad.mAnalogB;
    out.error = static_cast<s8>(pad.mCurError);
    out.flags = 0;
    return out;
}

void inject(const SusamunePracticeInput &input, TMarioGamePad *pad) {
    restorePad(sBeforeRead, pad);
    PADStatus raw = {};
    raw.mButton = input.buttons;
    raw.mStickX = static_cast<u8>(input.stickX);
    raw.mStickY = static_cast<u8>(input.stickY);
    raw.mSubStickX = static_cast<u8>(input.substickX);
    raw.mSubStickY = static_cast<u8>(input.substickY);
    raw.mTriggerLeft = input.triggerL;
    raw.mTriggerRight = input.triggerR;
    raw.mAnalogA = input.analogA;
    raw.mAnalogB = input.analogB;
    const JUTGamePad::EStickMode mode = static_cast<JUTGamePad::EStickMode>(
        *reinterpret_cast<const u32 *>(kStickMode));
    const u32 main = JUTGamePad::mPadMStick[0].update(
        input.stickX, input.stickY, mode,
        JUTGamePad::WhichStick_ControlStick);
    const u32 sub = JUTGamePad::mPadSStick[0].update(
        input.substickX, input.substickY, mode,
        JUTGamePad::WhichStick_CStick);
    JUTGamePad::mPadButton[0].update(&raw, (main << 24) | (sub << 16));
    pad->mButtons = JUTGamePad::mPadButton[0];
    pad->mControlStick = JUTGamePad::mPadMStick[0];
    pad->mCStick = JUTGamePad::mPadSStick[0];
}

void restoreCamera() {
    if (!sCameraApplied) return;
    if (sCameraGeneration == sStageGeneration && sCamera == gpCamera &&
        stageReady() && mem1(sCamera, sizeof(CPolarSubCamera))) {
        sCamera->mTranslation = sCameraSaved.position;
        sCamera->mTargetPos = sCameraSaved.target;
        sCamera->mUpVector = sCameraSaved.up;
        sCamera->mProjectionFovy = sCameraSaved.fovy;
        memcpy(reinterpret_cast<u8 *>(sCamera) + 0x124,
               sCameraRenderSaved, sizeof(sCameraRenderSaved));
    }
    sCameraApplied = false;
}

void readView(CameraView &out, CPolarSubCamera *camera) {
    out.position = camera->mTranslation;
    out.target = camera->mTargetPos;
    out.up = camera->mUpVector;
    out.fovy = camera->mProjectionFovy;
}

void applyCamera() {
    if (sCameraApplied || !sFreeCamera || sCamera != gpCamera ||
        sCameraGeneration != sStageGeneration || !stageReady()) return;
    readView(sCameraSaved, sCamera);
    memcpy(sCameraRenderSaved, reinterpret_cast<u8 *>(sCamera) + 0x124,
           sizeof(sCameraRenderSaved));
    sCamera->mTranslation = sCameraView.position;
    sCamera->mTargetPos = sCameraView.target;
    sCamera->mUpVector = sCameraView.up;
    sCamera->mProjectionFovy = sCameraView.fovy;
    sCamera->mWorldTranslation = sCameraView.position;
    *reinterpret_cast<TVec3f *>(reinterpret_cast<u8 *>(sCamera) + 0x148) =
        sCameraView.target;
    // Retail draw cues copy these cached matrices; they do not rebuild them.
    C_MTXPerspective(reinterpret_cast<f32 (*)[4]>(
                         reinterpret_cast<u8 *>(sCamera) + 0x16c),
                     sCameraView.fovy, sCamera->mProjectionAspect,
                     sCamera->mProjectionNear, sCamera->mProjectionFar);
    C_MTXLookAt(sCamera->mTRSMatrix,
                reinterpret_cast<const Vec *>(&sCameraView.position),
                reinterpret_cast<const Vec *>(&sCameraView.up),
                reinterpret_cast<const Vec *>(&sCameraView.target));
    sCamera->mAngleYaw = static_cast<s16>(static_cast<s32>(sYaw * 10430.37835f + 32768.0f));
    sCamera->mAnglePitch = static_cast<s16>(-sPitch * 10430.37835f);
    sCameraApplied = true;
}

f32 axis(s8 value) {
    const int magnitude = value < 0 ? -static_cast<int>(value) : value;
    if (magnitude < 12) return 0.0f;
    return static_cast<f32>(value) / 80.0f;
}

f32 cameraSpeedScale() {
    static const f32 scales[] = {0.25f, 0.5f, 1.0f, 2.0f, 4.0f};
    const u8 choice = gSettings.get(SETTING_FREE_CAMERA_SPEED);
    return scales[choice < 5 ? choice : 2];
}

void stripControlInput(SusamunePracticeInput &input, u16 buttons) {
    input.buttons &= ~buttons;
    if (buttons & JUTGamePad::L) input.triggerL = 0;
    if (buttons & JUTGamePad::R) input.triggerR = 0;
    if (buttons & JUTGamePad::A) input.analogA = 0;
    if (buttons & JUTGamePad::B) input.analogB = 0;
}

void consumeControlInput() {
    stripControlInput(sConsumed, sStripButtons);
    u16 held = sPhysical.buttons;
    // Digital clicks release before the analog trigger has returned to rest.
    if (sPhysical.triggerL >= 30) held |= JUTGamePad::L;
    if (sPhysical.triggerR >= 30) held |= JUTGamePad::R;
    sStripButtons &= held;
}

void spinInput(u8 index, bool clockwise, SusamunePracticeInput &input) {
    static const s8 directions[8][2] = {
        {0, 80}, {57, 57}, {80, 0}, {57, -57},
        {0, -80}, {-57, -57}, {-80, 0}, {-57, 57},
    };
    const u8 direction = clockwise ? index & 7u : (8u - index) & 7u;
    input.stickX = directions[direction][0];
    input.stickY = directions[direction][1];
}

void updateCamera() {
    if (!sFreeCamera || sModal || !controlStage()) return;
    if (sCameraWaitButtons) {
        if (sPhysical.buttons) return;
        sCameraWaitButtons = false;
    }
    const f32 turn = 0.035f;
    sYaw -= axis(sPhysical.substickX) * turn;
    if (sYaw > 3.14159265f) sYaw -= 6.2831853f;
    if (sYaw < -3.14159265f) sYaw += 6.2831853f;
    sPitch += axis(sPhysical.substickY) * turn;
    sPitch = Clamp(sPitch, -1.45f, 1.45f);
    const f32 forwardX = sinf(sYaw);
    const f32 forwardZ = cosf(sYaw);
    const f32 speed = cameraSpeedScale() *
                     ((sPhysical.buttons & JUTGamePad::X) ? 75.0f : 20.0f);
    const f32 advance = axis(sPhysical.stickY) * speed;
    const f32 strafe = axis(sPhysical.stickX) * speed *
        (gSettings.get(SETTING_FREE_CAMERA_STRAFE_REVERSE) ? -1.0f : 1.0f);
    // LookAt's screen-right is forward crossed with world-up.
    sCameraView.position.x += forwardX * advance - forwardZ * strafe;
    sCameraView.position.z += forwardZ * advance + forwardX * strafe;
    sCameraView.position.y += (static_cast<int>(sPhysical.triggerR) -
                              static_cast<int>(sPhysical.triggerL)) * speed / 255.0f;
    sCameraView.position.x = Clamp(sCameraView.position.x, -1000000.0f, 1000000.0f);
    sCameraView.position.y = Clamp(sCameraView.position.y, -1000000.0f, 1000000.0f);
    sCameraView.position.z = Clamp(sCameraView.position.z, -1000000.0f, 1000000.0f);
    sCameraView.target.set(sCameraView.position.x + forwardX * cosf(sPitch) * 1000.0f,
                          sCameraView.position.y + sinf(sPitch) * 1000.0f,
                          sCameraView.position.z + forwardZ * cosf(sPitch) * 1000.0f);
    sCameraView.up.set(0.0f, 1.0f, 0.0f);
}

bool installEntry(u32 address, void *target, u32 *tail) {
    const u32 original = *reinterpret_cast<const u32 *>(address);
    // Only these position-independent first instructions can be relocated.
    if (original != 0x7c0802a6u && (original & 0xffff0000u) != 0x94210000u)
        return false;
    tail[0] = original;
    tail[1] = branchWord(reinterpret_cast<u32>(&tail[1]), address + 4);
    DCFlushRange(tail, 8);
    ICInvalidateRange(tail, 8);
    writeGameCode(address, branchWord(address, reinterpret_cast<u32>(target)));
    return true;
}

bool installCall(u32 address, u32 originalTarget, void *target) {
    if (*reinterpret_cast<const u32 *>(address) !=
        (branchWord(address, originalTarget) | 1u)) return false;
    writeGameCode(address, branchWord(address, reinterpret_cast<u32>(target)) | 1u);
    return true;
}

void stopTape(const char *reason) {
    if (sRecord || sReplay || sLoadKind)
        CrashReport::note(SUSAMUNE_CRASH_EVENT_REPLAY, 0, sReplay ? sCursor : sCount);
    if (sRecord) sTapeHash = hashBytes(2166136261u, sFrames, sCount * sizeof(Frame));
    sRecord = false;
    sReplay = false;
    sLoadKind = 0;
    sLoadWait = 0;
    sFrameInjected = false;
    if (reason) message(reason);
}

} // namespace

extern "C" u32 susamunePracticeReadPad() {
    restoreCamera();
    sHaveRead = stageReady();
    sReadPad = sHaveRead ? gpApplication.mGamePads[0] : nullptr;
    if (sReadPad) capturePad(sBeforeRead, sReadPad);
    const u32 result = reinterpret_cast<u32 (*)()>(sPadReadTail)();
    sPhysical = snapshot(JUTGamePad::mPadStatus[0]);
    sConsumed = sPhysical;
    sFrameInjected = false;
    const u16 pressed = static_cast<u16>(sPhysical.buttons & ~sPriorButtons);
    sPriorButtons = sPhysical.buttons;
    if ((sRecord || sReplay) && sPhysical.error != 0)
        stopTape("Controller disconnected - input stopped");
    if (sReplay && (pressed & (JUTGamePad::B | JUTGamePad::START))) {
        sStripButtons |= pressed & (JUTGamePad::B | JUTGamePad::START);
        stopTape("Input playback stopped");
        gBinds.suppressUntilRelease();
    }
    if (sReplay && sReadPad && sCursor < sCount &&
        (!gMenu || !gMenu->shown()) && !WarpWheel::shown() &&
        !StageLoader::resultOwnsInput() && normalStage()) {
        sConsumed = sFrames[sCursor].input;
        inject(sConsumed, sReadPad);
        sFrameInjected = true;
    } else if (sFreeCamera && sPaused && sReadPad &&
               (!gMenu || !gMenu->shown())) {
        SusamunePracticeInput neutral = {};
        inject(neutral, sReadPad);
        sConsumed = neutral;
    }
    return result;
}

extern "C" void susamunePracticeCameraPerform(CPolarSubCamera *camera,
                                               u32 cue, JDrama::TGraphics *graphics) {
    if (cue & 3u) restoreCamera();
    if (sFreeCamera && camera == sCamera && (cue & 0x14u)) {
        if (cue & ~0x14u)
            reinterpret_cast<void (*)(CPolarSubCamera *, u32, JDrama::TGraphics *)>(
                kCameraPerform)(camera, cue & ~0x14u, graphics);
        applyCamera();
        cue &= 0x14u;
    }
    reinterpret_cast<void (*)(CPolarSubCamera *, u32, JDrama::TGraphics *)>(
        kCameraPerform)(camera, cue, graphics);
}

extern "C" void susamunePracticeMovement(TMarDirector *director) {
    restoreCamera();
    reinterpret_cast<void (*)(TMarDirector *)>(sMovementTail)(director);
}

extern "C" void susamunePracticeHitCheck(void *checker) {
    restoreCamera();
    if (!sFreeze) reinterpret_cast<void (*)(void *)>(kHitCheck)(checker);
}

extern "C" void susamunePracticeHitClear(void *checker) {
    restoreCamera();
    if (!sFreeze) reinterpret_cast<void (*)(void *)>(kHitClear)(checker);
}

extern "C" s32 susamunePracticeChangeState(TMarDirector *director) {
    if (sBorrowedPause) return TApplication::CONTEXT_DIRECT_MAIN_LOOP;
    const s32 result = reinterpret_cast<s32 (*)(TMarDirector *)>(kChangeState)(director);
    const bool secondaryTick = (director->mGameState & 0x4000u) == 0;
    if (result <= TApplication::CONTEXT_DIRECT_MAIN_LOOP &&
        activatePendingPause(secondaryTick)) {
        sReadPad = gpApplication.mGamePads[0];
        sHaveRead = true;
        // Keep nextStateInitialize's newly enabled pad flags across the hold.
        capturePad(sBeforeRead, sReadPad);
        // changeState can finish an intro between two ticks of this frame.
        director->mCurState = TMarDirector::STATE_STAGE_EXIT_2;
        sBorrowedPause = true;
        Ghost::frameControl(true, true);
    }
    return result;
}

namespace PracticeSession {

void init() {
    sPadHookReady = installEntry(kPadRead,
        reinterpret_cast<void *>(&susamunePracticeReadPad), sPadReadTail);
    sMovementHookReady = installEntry(kDirectorMovement,
        reinterpret_cast<void *>(&susamunePracticeMovement), sMovementTail);
    const bool checkReady = installCall(kHitCheckCall, kHitCheck,
        reinterpret_cast<void *>(&susamunePracticeHitCheck));
    const bool clearReady = installCall(kHitClearCall, kHitClear,
        reinterpret_cast<void *>(&susamunePracticeHitClear));
    sCollisionHooksReady = checkReady && clearReady;
    sStateHookReady = installCall(kChangeStateCall, kChangeState,
        reinterpret_cast<void *>(&susamunePracticeChangeState));
    u32 *table = reinterpret_cast<u32 *>(kCameraVtable);
    for (u32 i = 0; i < 32; ++i) {
        if (table[i] != kCameraPerform) continue;
        table[i] = reinterpret_cast<u32>(&susamunePracticeCameraPerform);
        DCFlushRange(&table[i], sizeof(table[i]));
        sCameraHookReady = sMovementHookReady;
        break;
    }
}

void beforeStageSetup() {
    sCameraWaitButtons = false;
    restoreCamera();
    ++sStageGeneration;
    sFreeCamera = false;
    sCamera = nullptr;
    sPaused = false;
    sBorrowedPause = false;
    sStepQueued = false;
    sSpinRemaining = 0;
    sMenuAction = 0;
    sFreeze = false;
    sAssisted = false;
    sHaveRead = false;
    sSeedValid = false;
    sSteps = 0;
    sCount = 0;
    sCursor = 0;
    stopTape(nullptr);
    sStatus = sPausePending ? "Frame advance armed - waiting for Mario control" :
                             "Save a state before recording";
}

void beforeDirect(bool modalOwnsInput) {
    restoreCamera();
    sConsumedFrame = false;
    sStepping = false;
    sSpinApplied = false;
    sModal = modalOwnsInput;
    const bool injectedBeforeDirect = sFrameInjected;
    activatePendingPause();
    if (!controlStage()) {
        sCameraWaitButtons = false;
        sPaused = false;
        sStepQueued = false;
        sSpinRemaining = 0;
        sMenuAction = 0;
        sFreeze = false;
        sFreeCamera = false;
        if (sRecord || sReplay) stopTape("Input session ended: scene transition");
        return;
    }
    if (sAssisted) invalidate();
    if ((sRecord || sReplay) && settingsHash() != sSettingsHash)
        stopTape("Settings changed - record again");
    if ((sRecord || sReplay) && actionsFastForwardActive())
        stopTape("Input session stopped: fast-forward");
    if (sReplay && sModal) stopTape("Input playback stopped: menu opened");
    if (sRecord && sModal) stopTape("Input recording stopped: menu opened");
    if (((injectedBeforeDirect && !sReplay) || (sModal && sFreeCamera)) &&
        sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        inject(sPhysical, sReadPad);
        sReadPad->updateMeaning();
        sConsumed = sPhysical;
        sFrameInjected = false;
    }
    if (sMenuAction && !sModal && !(sPhysical.buttons & JUTGamePad::A)) {
        if (sMenuAction == 2) {
            sPaused = false;
            sStepQueued = false;
            sSpinRemaining = 0;
            if (!Ghost::observerActive()) sFreeCamera = false;
            message("Gameplay resumed");
            CrashReport::note(SUSAMUNE_CRASH_EVENT_PRACTICE, 0, sSteps);
        }
        sMenuAction = 0;
    }
    if (sPaused && normalStage() && !sModal && !sMenuAction && sStepQueued &&
        !actionsFastForwardActive()) {
        sStepping = true;
        sStepQueued = false;
        sMenuAction = 0;
    }
    if ((sStripButtons || (sStepping && sSpinRemaining)) && !sModal && sHaveRead &&
        sReadPad == gpApplication.mGamePads[0] && !sReplay) {
        consumeControlInput();
        if (sStepping && sSpinRemaining && !sFreeCamera) {
            spinInput(kSpinFrames - sSpinRemaining, sSpinClockwise, sConsumed);
            sSpinApplied = true;
        }
        inject(sConsumed, sReadPad);
        sReadPad->updateMeaning();
    }
    sFreeze = sPaused && !sStepping && normalStage();
    if (sFreeze && !sModal && sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        restorePad(sBeforeRead, sReadPad);
    }
    if (sFreeCamera && !sPaused &&
        gpMarDirector->mCurState != TMarDirector::STATE_PAUSE_MENU &&
        !Ghost::observerActive())
        sFreeCamera = false;
    updateCamera();
}

bool freezeRequested() { return sFreeze; }
bool ownsGameplayInput() { return sPaused || sFreeCamera || sReplay || sLoadKind != 0; }

void afterDirect(s32 appState, bool gameplayActive) {
    if (sBorrowedPause) {
        if (stageReady() && gpMarDirector->mCurState == TMarDirector::STATE_STAGE_EXIT_2)
            gpMarDirector->mCurState = TMarDirector::STATE_NORMAL;
        sBorrowedPause = false;
    }
    restoreCamera();
    // Retail keeps looping for WAIT (0) and DEFAULT (1).
    if (!stageReady() || appState > TApplication::CONTEXT_DIRECT_MAIN_LOOP) {
        sCameraWaitButtons = false;
        if (sRecord || sReplay) stopTape("Input session ended: scene transition");
        sFreeCamera = false;
        sPaused = false;
        sStepQueued = false;
        sSpinRemaining = 0;
        sMenuAction = 0;
        sFreeze = false;
        return;
    }
    sModal = sModal || WarpWheel::shown() || WarpWheel::promptPending();
    if ((sRecord || sReplay) && sModal)
        stopTape("Input session ended: overlay opened");
    if (sFreeze && !sModal && sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        restorePad(sBeforeRead, sReadPad);
    }
    if ((sRecord || sReplay) && !normalStage())
        stopTape("Input session ended: pause or scene change");
    sConsumedFrame = sHaveRead && gameplayActive && !sFreeze && !sModal &&
                     !actionsFastForwardActive();
    if (sStepping && sConsumedFrame) ++sSteps;
    if (!sConsumedFrame) return;
    if (sConsumed.error != 0) {
        sConsumedFrame = false;
        if (sRecord || sReplay) stopTape("Controller disconnected - input stopped");
        return;
    }
    if (sSpinApplied && sSpinRemaining) --sSpinRemaining;
    if (sRecord) {
        if (sCount == kMaxFrames) {
            stopTape("Input recording full");
        } else {
            sFrames[sCount].input = sConsumed;
            sFrames[sCount].fingerprint = fingerprint();
            ++sCount;
            if (sCount == kMaxFrames) stopTape("Input recording full");
        }
    } else if (sReplay && sFrameInjected) {
        const u32 expected = sFrames[sCursor].fingerprint;
        ++sCursor;
        if (fingerprint() != expected) {
            stopTape("Replay diverged - see frame counter");
            CrashReport::note(SUSAMUNE_CRASH_EVENT_REPLAY, 3, sCursor);
            sPaused = true;
        } else if (sCursor == sCount) {
            stopTape("Playback finished - fingerprints matched");
            sPaused = true;
        }
    }
}

void afterDraw() {
    restoreCamera();
    if (!sLoadKind || (gMenu && gMenu->shown()) || WarpWheel::shown() ||
        StageLoader::resultOwnsInput()) return;
    if (sPhysical.buttons) return;
    if (!normalStage() || !sSeedValid || sSeedStage != sStageGeneration ||
        sSeedHeap != reinterpret_cast<u32>(gpApplication.mCurrentHeap)) {
        stopTape("Save a new gameplay state first");
        return;
    }
    if (gpCardManager && gpCardManager->getLastStatus() == CARD_ERROR_BUSY) {
        if (++sLoadWait >= 600) stopTape("Memory card busy - input canceled");
        return;
    }
    const u8 kind = sLoadKind;
    sOwnLoad = true;
    const bool loaded = gSavestateMgr && gSavestateMgr->loadState();
    sOwnLoad = false;
    sLoadKind = 0;
    sLoadWait = 0;
    if (!loaded) {
        stopTape("Couldn't load recording's savestate");
        return;
    }
    restorePad(sSeedPad, gpApplication.mGamePads[0]);
    sHaveRead = false;
    sPaused = false;
    sFreeCamera = false;
    sCursor = 0;
    if (kind == 1) {
        sCount = 0;
        sTapeHash = 0;
        sTapeSeed = sSeedGeneration;
        sTapeStage = sStageGeneration;
        sSettingsHash = settingsHash();
        sRecord = true;
        message("Recording inputs - Stop keeps this take");
    } else {
        sReplay = true;
        message("Input playback - B or Start stops");
    }
    CrashReport::note(SUSAMUNE_CRASH_EVENT_REPLAY, kind, sCount);
    invalidate();
    gBinds.suppressUntilRelease();
}

void onSavestateSaved() {
    ++sSeedGeneration;
    sSeedValid = normalStage();
    sSeedStage = sStageGeneration;
    sSeedHeap = reinterpret_cast<u32>(gpApplication.mCurrentHeap);
    if (sSeedValid) capturePad(sSeedPad, gpApplication.mGamePads[0]);
    if (sRecord || sReplay || sLoadKind) stopTape("Savestate replaced - input stopped");
}

void onSavestateLoaded() {
    sCameraWaitButtons = false;
    sMenuAction = 0;
    restoreCamera();
    sCamera = nullptr;
    sFreeCamera = false;
    sStepQueued = false;
    sSpinRemaining = 0;
    sHaveRead = false;
    if (!sOwnLoad) stopTape(nullptr);
    invalidate();
}

bool requestPauseToggle(bool fromMenu) {
    if (!available() || !sCollisionHooksReady || !sStateHookReady) {
        message("Frame advance is unavailable");
        return false;
    }
    if (gBinds.wasPressed(BIND_PRACTICE_PAUSE))
        sStripButtons |= gBinds.get(BIND_PRACTICE_PAUSE);
    if (sPausePending) {
        sPausePending = false;
        message("Buffered frame pause canceled");
        return true;
    }
    if (!sPaused && !actionableStage()) {
        if (sRecord || sReplay) stopTape(nullptr);
        sPausePending = true;
        message("Frame advance armed - waiting for Mario control");
        return true;
    }
    if (sRecord || sReplay) stopTape("Input stopped for frame advance");
    sMenuAction = 0;
    if (fromMenu && sPaused) {
        sMenuAction = 2;
        sStepQueued = false;
        message("Release A to resume gameplay");
        return true;
    }
    sPaused = !sPaused;
    sStepQueued = false;
    if (!sPaused) {
        sSpinRemaining = 0;
        if (!Ghost::observerActive()) { sFreeCamera = false; restoreCamera(); }
    }
    else invalidate();
    message(sPaused ? "Frame advance paused - clocks stay live" : "Gameplay resumed");
    CrashReport::note(SUSAMUNE_CRASH_EVENT_PRACTICE, sPaused ? 1 : 0, sSteps);
    return true;
}

bool requestStep(bool fromMenu) {
    if (!available() || !sCollisionHooksReady || !sStateHookReady) {
        message("Frame advance is unavailable");
        return false;
    }
    if (!fromMenu) sStripButtons |= gBinds.get(BIND_PRACTICE_STEP);
    if (!sPaused && !actionableStage()) {
        if (sRecord || sReplay) stopTape(nullptr);
        sPausePending = true;
        message("Frame advance armed - waiting for Mario control");
        return true;
    }
    if (!sPaused) {
        if (sRecord || sReplay) stopTape(nullptr);
        sPausePending = false;
        sPaused = true;
        sStepQueued = false;
        sMenuAction = 0;
        invalidate();
        message("Gameplay paused - press Step again to advance");
        return true;
    }
    sStepQueued = true;
    sMenuAction = fromMenu ? 1 : 0;
    if (fromMenu) message("Release A to advance one frame");
    invalidate();
    return true;
}

bool requestSpin(bool clockwise, bool fromMenu) {
    if (!sPaused || !normalStage() || sFreeCamera || Ghost::observerActive() ||
        observerTransition()) {
        message("Queue spin needs frame hold without free camera");
        return false;
    }
    sSpinClockwise = clockwise;
    sSpinRemaining = kSpinFrames;
    sStepQueued = false;
    sMenuAction = fromMenu ? 1 : 0;
    invalidate();
    message("Spin queued: Step each direction; hold A to jump");
    return true;
}

void recenterCamera() {
    restoreCamera();
    if (!controlStage() || !mem1(gpCamera, sizeof(CPolarSubCamera))) return;
    sCamera = gpCamera;
    sCameraGeneration = sStageGeneration;
    readView(sCameraView, sCamera);
    sCameraView.position = sCamera->mWorldTranslation;
    sCameraView.target = *reinterpret_cast<const TVec3f *>(
        reinterpret_cast<const u8 *>(sCamera) + 0x148);
    const f32 dx = sCameraView.target.x - sCameraView.position.x;
    const f32 dy = sCameraView.target.y - sCameraView.position.y;
    const f32 dz = sCameraView.target.z - sCameraView.position.z;
    const Vec horizontal = {dx, 0.0f, dz};
    sYaw = atan2f(dx, dz);
    sPitch = atan2f(dy, PSVECMag(&horizontal));
}

bool requestFreeCameraToggle() {
    if (gBinds.wasPressed(BIND_FREE_CAMERA))
        sStripButtons |= gBinds.get(BIND_FREE_CAMERA);
    if (sFreeCamera) {
        sCameraWaitButtons = false;
        restoreCamera();
        sFreeCamera = false;
        message("Free camera off");
        CrashReport::note(SUSAMUNE_CRASH_EVENT_PRACTICE, 2, 0);
        return true;
    }
    if (!sCameraHookReady || !controlStage() || observerTransition() ||
        !mem1(gpCamera, sizeof(CPolarSubCamera))) {
        message("Free camera needs a loaded gameplay scene");
        return false;
    }
    if (!sPaused && normalStage() && !Ghost::observerActive()) {
        if (!available() || !sCollisionHooksReady) {
            message("Free camera couldn't pause gameplay");
            return false;
        }
        if (sRecord || sReplay) stopTape(nullptr);
        sPausePending = false;
        sPaused = true;
        sStepQueued = false;
        sMenuAction = 0;
    }
    recenterCamera();
    sFreeCamera = true;
    sSpinRemaining = 0;
    sCameraWaitButtons = true;
    invalidate();
    message("Free camera: sticks move/look, L/R height, X boost");
    CrashReport::note(SUSAMUNE_CRASH_EVENT_PRACTICE, 2, 1);
    return true;
}

bool requestRecord() {
    if (!tapeStorageReady()) {
        message("Input sessions need a matching launcher");
        return false;
    }
    if (!available() || !normalStage() || !sSeedValid ||
        sSeedStage != sStageGeneration || Ghost::observerStatsSuppressed()) {
        message("Save a normal gameplay state first");
        return false;
    }
    stopTape(nullptr);
    sLoadKind = 1;
    message("Close menu: reload savestate and record");
    return true;
}

bool requestPlayback() {
    if (!tapeStorageReady()) {
        message("Input sessions need a matching launcher");
        return false;
    }
    if (!available() || !normalStage() || sCount == 0 ||
        !sSeedValid || sTapeSeed != sSeedGeneration ||
        sTapeStage != sStageGeneration || Ghost::observerStatsSuppressed()) {
        message("Record a take with this savestate first");
        return false;
    }
    if (sRecord) stopTape(nullptr);
    if (settingsHash() != sSettingsHash ||
        hashBytes(2166136261u, sFrames, sCount * sizeof(Frame)) != sTapeHash) {
        message("Recording changed or damaged - record again");
        return false;
    }
    stopTape(nullptr);
    sLoadKind = 2;
    message("Close menu: replay from saved state");
    return true;
}

void requestStop() {
    if (gBinds.wasPressed(BIND_PRACTICE_STOP))
        sStripButtons |= gBinds.get(BIND_PRACTICE_STOP);
    sSpinRemaining = 0;
    stopTape("Input session stopped");
    gBinds.suppressUntilRelease();
}

void releaseForDeparture() {
    sCameraWaitButtons = false;
    const bool restoreInput = sFrameInjected || sPaused || sFreeCamera || sFreeze;
    restoreCamera();
    if (sRecord || sReplay || sLoadKind)
        stopTape("Input session ended: warp requested");
    if (restoreInput && sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        inject(sPhysical, sReadPad);
        sReadPad->updateMeaning();
    }
    sPaused = false;
    sFreeCamera = false;
    sStepQueued = false;
    sSpinRemaining = 0;
    sStepping = false;
    sFreeze = false;
    sConsumedFrame = false;
    sHaveRead = false;
    sFrameInjected = false;
    sMenuAction = 0;
    sStripButtons = 0;
}

bool paused() { return sPaused; }
bool pausePending() { return sPausePending; }
bool freeCamera() { return sFreeCamera; }
bool recording() { return sRecord; }
bool replaying() { return sReplay; }
bool assisted() { return sAssisted; }
bool available() { return sPadHookReady; }
u32 stepCount() { return sSteps; }
u32 queuedSpinFrames() { return sSpinRemaining; }
u32 recordedFrames() { return sCount; }
u32 replayFrame() { return sCursor; }
u32 capacityFrames() { return kMaxFrames; }
const char *status() { return sStatus; }

bool consumedInput(SusamunePracticeInput *out) {
    if (!out || !sConsumedFrame) return false;
    *out = sConsumed;
    return true;
}

void draw(Menu *menu) {
    if (!menu || menu->shown() || menu->hasToast() ||
        (!sPaused && !sPausePending && !sFreeCamera && !sRecord && !sReplay && !sLoadKind)) return;
    char text[96];
    if (sPausePending) snprintf(text, sizeof(text), "FRAME ADVANCE ARMED - waiting for Mario control");
    else if (sRecord) snprintf(text, sizeof(text), "INPUT REC  %lu / %lu", sCount, kMaxFrames);
    else if (sReplay) snprintf(text, sizeof(text), "INPUT PLAY  %lu / %lu", sCursor, sCount);
    else if (sFreeCamera) snprintf(text, sizeof(text), "CAMERA ON  %.2fx  X boost  Mario input OFF",
                                  cameraSpeedScale());
    else if (sSpinRemaining) snprintf(text, sizeof(text), "SPIN %s  %u directions left  Step + A: jump",
                                     sSpinClockwise ? "CW" : "CCW", sSpinRemaining);
    else snprintf(text, sizeof(text), "FRAME ADVANCE  %lu   Playback %lu", sSteps, sCursor);
    menu->fillBox(42, 388, 556, 40, JUtility::TColor(8, 17, 31, 225));
    menu->drawText(text, 50, 394, 16, 16, JUtility::TColor(130, 225, 255, 255));
    menu->drawText(sFreeCamera ? "Turn camera Off to step with A or other Mario inputs" :
                   "Practice only - gameplay clocks are unchanged", 50, 413, 12, 12,
                   JUtility::TColor(235, 235, 235, 255));
}

} // namespace PracticeSession
