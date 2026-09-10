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
#include "susamune/qft_timer.hxx"
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
PadHistory sStatePad;
enum SavedTakeFlags {
    SAVED_PAD = 1, SAVED_RNG = 2, SAVED_TAKE = 4,
    SAVED_RECORDING = 8, SAVED_PAUSED = 16,
};
const u32 kSavedTakeVersion = 1;
PadHistory sModalPad;
bool sModalPadValid;
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
bool sFrameInjected;
u8 sLoadKind;
u8 sMenuAction;
u16 sLoadWait;
u32 sStageGeneration;
u32 sTapeSeed;
u32 sTapeSlot;
u32 sLoadSlot;
u32 sLoadGeneration;
u32 sCount;
u32 sCursor;
u32 sSteps;
u32 sSettingsHash;
u32 sTapeHash;
u32 sTapeStage;
u32 sTapeStart;
u32 sOriginKey[2];
bool sTakeAttached;
u32 sTakePosition;
u32 sPendingReleases;
bool sOwnRestoreValid;
u16 sPriorButtons;
u16 sStripButtons;
u16 sStartRelease;
u16 sLoadHoldButtons;
bool sLoadHoldActive;
bool sLoadHoldPending;
char sReplayFailure[64];
const char *sStatus = "Save a state before recording";

bool seedMatches(u32 slot, u32 generation) {
    if (!gSavestateMgr || slot >= SavestateManager::kSlotCount || !generation)
        return false;
    const SavestateManager::SlotInfo info = gSavestateMgr->slotInfo(slot);
    PracticeSession::SavestateData data;
    return info.valid && info.generation == generation &&
           gSavestateMgr->practiceData(slot, &data) && (data.flags & SAVED_PAD);
}

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

bool introStage() {
    return stageReady() &&
           gpMarDirector->mCurState <= TMarDirector::STATE_GAME_STARTING;
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
    gQFTTimer.markPracticeAssisted();
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

bool activatePendingLoadHold(bool secondaryTick = false) {
    if (!sLoadHoldPending || sModal || !actionableStage(secondaryTick)) return false;
    sLoadHoldPending = false;
    sLoadHoldActive = true;
    sFreeze = true;
    return true;
}

u32 hashBytes(u32 hash, const void *data, u32 count) {
    const u8 *bytes = static_cast<const u8 *>(data);
    for (u32 i = 0; i < count; ++i) hash = (hash ^ bytes[i]) * 16777619u;
    return hash;
}

bool validSavedTake(const PracticeSession::SavestateData &data) {
    if (data.version != kSavedTakeVersion || (data.releases & ~0x1fffffu) ||
        (data.flags & ~31u) || data.frames > kMaxFrames ||
        !(data.stateKey[0] | data.stateKey[1])) return false;
    if (!(data.flags & SAVED_PAD))
        return !data.flags && !data.frames && !data.padHash && !data.releases &&
               !data.originKey[0] && !data.originKey[1];
    if (data.flags & SAVED_TAKE)
        return (data.flags & SAVED_RNG) && (data.originKey[0] | data.originKey[1]);
    return !(data.flags & SAVED_RECORDING) && !data.frames &&
           !data.originKey[0] && !data.originKey[1];
}

bool findTakeStart() {
    if (!gSavestateMgr || !(sOriginKey[0] | sOriginKey[1])) return false;
    for (u32 slot = 0; slot < SavestateManager::kSlotCount; ++slot) {
        PracticeSession::SavestateData data;
        if (!gSavestateMgr->practiceData(slot, &data) ||
            data.stateKey[0] != sOriginKey[0] || data.stateKey[1] != sOriginKey[1] ||
            !(data.flags & SAVED_RNG) || !(data.flags & SAVED_PAD)) continue;
        sTapeSlot = slot;
        sTapeSeed = gSavestateMgr->slotInfo(slot).generation;
        return sTapeSeed != 0;
    }
    return false;
}

bool replayPresentationSetting(SettingId id) {
    if (id >= SETTING_FAVORITES_0 && id <= SETTING_FAVORITES_10) return true;
    switch (id) {
    case SETTING_RNG_FAVORITES:
    case SETTING_NATIVE_TIMER_X:
    case SETTING_NATIVE_TIMER_Y:
    case SETTING_NATIVE_TIMER_SCALE:
    case SETTING_FREE_CAMERA_SPEED:
    case SETTING_FREE_CAMERA_STRAFE_REVERSE:
    case SETTING_FREE_CAMERA_SENSITIVITY:
    case SETTING_FREE_CAMERA_HIDE_HUD:
    case SETTING_METADATA_HORIZONTAL:
    case SETTING_GHOST_INPUTS:
        return true;
    default:
        return false;
    }
}

u32 settingsHash() {
    u32 hash = 2166136261u;
    for (int i = 0; i < SETTING_COUNT; ++i) {
        const SettingId id = static_cast<SettingId>(i);
        // Keep new settings guarded until their consumers are audited.
        if (replayPresentationSetting(id)) continue;
        const u8 value = gSettings.get(id);
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

// Retail buttons have twelve digital and eight stick-direction bits.
const u32 kDigitalButtons = 0x1f7fu;
const u32 kFrameFingerprintMask = 0x7fffffffu;
static_assert((kDigitalButtons & 0xe080u) == 0, "tape metadata button bits");

u32 packReleases(u32 buttons, bool analog) {
    return (buttons & 0x7fu) | ((buttons >> 1) & 0xf80u) |
           ((buttons >> 4) & 0xf000u) | ((buttons >> 8) & 0xf0000u) |
           (analog ? 0x100000u : 0);
}

u32 releaseButtons(u32 packed) {
    return (packed & 0x7fu) | ((packed & 0xf80u) << 1) |
           ((packed & 0xf000u) << 4) | ((packed & 0xf0000u) << 8);
}

u32 buttonMeanings(u32 buttons) {
    u32 meanings = 0;
    if (buttons & 0x1000u) meanings |= 1u;
    if (buttons & 0x100u) meanings |= 0x300a0u;
    if (buttons & 0x200u) meanings |= 0x50940u;
    if (buttons & 0x400u) meanings |= 0x200000u;
    if (buttons & 0x800u) meanings |= 0x4000u;
    if (buttons & 0x10u) meanings |= 0x1000u;
    if (buttons & 0x20u) meanings |= 0x400u;
    if (buttons & 0x40u) meanings |= 0xa000u;
    if (buttons & 0x08000008u) meanings |= 0x80002u;
    if (buttons & 0x04000004u) meanings |= 0x100004u;
    if (buttons & 0x01000001u) meanings |= 8u;
    if (buttons & 0x02000002u) meanings |= 0x10u;
    return meanings;
}

void applyReleases(TMarioGamePad *pad, u32 packed) {
    const u32 released = releaseButtons(packed);
    JUTGamePad::mPadButton[0].mInput &= ~released;
    pad->mButtons.mInput &= ~released;
    // A/B and D-pad/stick meanings can share a source; keep the held source.
    pad->mMeaning &= ~(buttonMeanings(released) & ~buttonMeanings(pad->mButtons.mInput));
    if (packed & 0x100000u) {
        pad->_DC &= ~1u;
        pad->mMeaning &= ~0x200u;
    }
    pad->mFrameMeaning = pad->_D8 = 0;
}

void retainPausedReleases(TMarioGamePad *pad) {
    const u32 held = pad->mButtons.mInput;
    const u16 analog = pad->_DC;
    restorePad(sBeforeRead, pad);
    const u32 released = packReleases(
        (pad->mButtons.mInput | JUTGamePad::mPadButton[0].mInput) & ~held,
        (pad->_DC & ~analog & 1u) != 0);
    applyReleases(pad, released);
    sPendingReleases |= released;
    capturePad(sBeforeRead, pad);
}

void writeFrame(Frame &frame, const SusamunePracticeInput &input, u32 hash, u32 releases) {
    frame.input = input;
    frame.input.error = static_cast<s8>(releases);
    frame.input.flags = static_cast<u8>(releases >> 8);
    frame.input.buttons = (input.buttons & kDigitalButtons) |
        ((releases >> 9) & 0x80u) | ((releases >> 4) & 0xe000u);
    // One diagnostic hash bit completes the lossless 21-bit release mask.
    frame.fingerprint = (hash & kFrameFingerprintMask) | ((releases & 0x100000u) << 11);
}

u32 frameReleases(const Frame &frame) {
    return static_cast<u8>(frame.input.error) | (static_cast<u32>(frame.input.flags) << 8) |
        ((frame.input.buttons & 0x80u) << 9) | ((frame.input.buttons & 0xe000u) << 4) |
        ((frame.fingerprint >> 11) & 0x100000u);
}

SusamunePracticeInput frameInput(const Frame &frame) {
    SusamunePracticeInput input = frame.input;
    input.buttons &= kDigitalButtons;
    input.error = 0;
    input.flags = 0;
    return input;
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

void inject(const SusamunePracticeInput &input, TMarioGamePad *pad, u32 releases = 0) {
    restorePad(sBeforeRead, pad);
    if (releases) applyReleases(pad, releases);
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

void retainModalHistory() {
    if (!sHaveRead || sReadPad != gpApplication.mGamePads[0]) return;
    if (sModal && normalStage() && (sRecord || sTakeAttached)) {
        if (!sModalPadValid) sModalPad = sBeforeRead;
        PadHistory menuPad;
        capturePad(menuPad, sReadPad);
        sBeforeRead = sModalPad;
        retainPausedReleases(sReadPad);
        sModalPad = sBeforeRead;
        sModalPadValid = true;
        restorePad(menuPad, sReadPad);
    } else if (sModalPadValid && !sModal) {
        sBeforeRead = sModalPad;
        inject(sPhysical, sReadPad);
        sReadPad->updateMeaning();
        sConsumed = sPhysical;
        sModalPadValid = false;
    }
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

f32 cameraScale(SettingId id) {
    static const f32 scales[] = {0.25f, 0.5f, 1.0f, 2.0f, 4.0f};
    const u8 choice = gSettings.get(id);
    return scales[choice < 5 ? choice : 2];
}

f32 cameraSpeedScale() { return cameraScale(SETTING_FREE_CAMERA_SPEED); }

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

void updateCamera() {
    if (!sFreeCamera || sModal || !controlStage()) return;
    if (sCameraWaitButtons) {
        if (sPhysical.buttons) return;
        sCameraWaitButtons = false;
    }
    const f32 turn = 0.035f * cameraScale(SETTING_FREE_CAMERA_SENSITIVITY);
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
    sStartRelease = 0;
    if (reason) message(reason);
}

void queueTapeLoad(u8 kind, u32 slot, u32 generation) {
    stopTape(nullptr);
    sLoadSlot = slot;
    sLoadGeneration = generation;
    sLoadKind = kind;
    sPausePending = false;
    sStepQueued = false;
    sMenuAction = 0;
    const bool menu = gMenu && gMenu->shown();
    sStartRelease = menu ? static_cast<u16>(JUTGamePad::A) :
        gBinds.get(kind == 1 ? BIND_PRACTICE_RECORD : BIND_PRACTICE_REPLAY);
    sStartRelease &= sPhysical.buttons;
    message(menu ? (kind == 1 ? "Release A to reload and record" : "Release A to replay") :
                   "Release the shortcut buttons to begin");
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
        sPaused = true;
        sPausePending = sStepQueued = false;
        stopTape("Input playback stopped - paused for editing");
        gBinds.suppressUntilRelease();
    }
    if (sReplay && sReadPad && sCursor < sCount &&
        (!gMenu || !gMenu->shown()) && !WarpWheel::shown() &&
        !StageLoader::resultOwnsInput() && normalStage()) {
        sConsumed = frameInput(sFrames[sCursor]);
        inject(sConsumed, sReadPad, frameReleases(sFrames[sCursor]));
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
    bool pauseActivated = false;
    bool loadActivated = false;
    if (result <= TApplication::CONTEXT_DIRECT_MAIN_LOOP) {
        pauseActivated = activatePendingPause(secondaryTick);
        loadActivated = activatePendingLoadHold(secondaryTick);
    }
    if (pauseActivated || loadActivated) {
        sReadPad = gpApplication.mGamePads[0];
        sHaveRead = true;
        // Keep nextStateInitialize's newly enabled pad flags across the hold.
        capturePad(sBeforeRead, sReadPad);
        gQFTTimer.beginPracticePause();
        // changeState can finish an intro between two ticks of this frame.
        director->mCurState = TMarDirector::STATE_STAGE_EXIT_2;
        sBorrowedPause = true;
        Ghost::frameControl(true, true);
    }
    return result;
}

namespace PracticeSession {

bool captureSavestate(SavestateData &out,
                      StateCodec::ReadSpan (&spans)[kSavestateSpanCount]) {
    memset(&out, 0, sizeof(out));
    memset(spans, 0, sizeof(spans));
    out.version = kSavedTakeVersion;
    const u64 stamp = static_cast<u64>(OSGetTime());
    out.stateKey[0] = static_cast<u32>(stamp >> 32);
    out.stateKey[1] = static_cast<u32>(stamp);
    if (!(out.stateKey[0] | out.stateKey[1])) out.stateKey[1] = 1;
    if (!normalStage() || Ghost::observerStatsSuppressed()) return true;
    if (sModalPadValid) sStatePad = sModalPad;
    else capturePad(sStatePad, gpApplication.mGamePads[0]);
    out.flags = SAVED_PAD | (gSettings.getBool(SETTING_SAVE_RNG_STATE) ? SAVED_RNG : 0) |
                (sPaused ? SAVED_PAUSED : 0);
    out.padHash = hashBytes(2166136261u, &sStatePad, sizeof(sStatePad));
    out.savedFingerprint = fingerprint();
    out.releases = sPendingReleases;
    spans[0] = {&sStatePad, sizeof(sStatePad)};
    if (sTakeAttached && (out.flags & SAVED_RNG) &&
        (sOriginKey[0] | sOriginKey[1]) && settingsHash() == sSettingsHash) {
        if (!tapeStorageReady() || sCount > kMaxFrames || sTakePosition > sCount) return false;
        out.flags |= SAVED_TAKE | ((sRecord || sReplay) ? SAVED_RECORDING : 0);
        out.frames = sTakePosition;
        out.settingsHash = sSettingsHash;
        out.startFingerprint = sTapeStart;
        out.frameHash = hashBytes(2166136261u, sFrames, out.frames * sizeof(Frame));
        out.originKey[0] = sOriginKey[0];
        out.originKey[1] = sOriginKey[1];
        out.steps = sSteps;
        spans[1] = {sFrames, out.frames * static_cast<u32>(sizeof(Frame))};
    }
    return validSavedTake(out);
}

bool savestateRestoreSpans(const SavestateData &data,
                          StateCodec::WriteSpan (&spans)[kSavestateSpanCount]) {
    memset(spans, 0, sizeof(spans));
    if (!validSavedTake(data) || ((data.flags & SAVED_TAKE) && !tapeStorageReady())) return false;
    if (data.flags & SAVED_PAD) spans[0] = {&sStatePad, sizeof(sStatePad)};
    if (data.frames) spans[1] = {sFrames, data.frames * static_cast<u32>(sizeof(Frame))};
    return true;
}

bool copySavestateBytes(void *destination, const void *, u32 size) {
    if (!sOwnLoad) return false;
    const __UINTPTR_TYPE__ address = reinterpret_cast<__UINTPTR_TYPE__>(destination);
    const __UINTPTR_TYPE__ begin = reinterpret_cast<__UINTPTR_TYPE__>(sFrames);
    return address >= begin && address - begin <= SUSAMUNE_PRACTICE_TAPE_SIZE &&
           size <= SUSAMUNE_PRACTICE_TAPE_SIZE - (address - begin);
}

bool restoreSavestate(const SavestateData &data, u32 slot, u32 generation) {
    if (!validSavedTake(data)) __builtin_trap();
    const bool padValid = (data.flags & SAVED_PAD) && normalStage() &&
        hashBytes(2166136261u, &sStatePad, sizeof(sStatePad)) == data.padHash;
    if (padValid) {
        restorePad(sStatePad, gpApplication.mGamePads[0]);

    }
    sHaveRead = sFrameInjected = sConsumedFrame = false;
    sPendingReleases = padValid ? data.releases : 0;
    if ((data.flags & SAVED_PAD) && !padValid) {
        stopTape(nullptr);
        sTakeAttached = false;
        sPaused = true;
        message("Savestate controller history is damaged - TAS stopped");
        return false;
    }
    if (sOwnLoad) {
        sOwnRestoreValid = padValid;
        return padValid;
    }
    sCount = sCursor = 0;
    sTapeSeed = sTapeHash = 0;
    sOriginKey[0] = sOriginKey[1] = 0;
    sTakeAttached = false;
    if (!(data.flags & SAVED_TAKE)) return true;
    if (!padValid || fingerprint() != data.savedFingerprint ||
        hashBytes(2166136261u, sFrames, data.frames * sizeof(Frame)) != data.frameHash) {
        sPaused = true;
        message("TAS checkpoint inputs are damaged - recording stopped");
        return false;
    }
    sCount = data.frames;
    sTakePosition = data.frames;
    sTapeHash = data.frameHash;
    sSettingsHash = data.settingsHash;
    sTapeStart = data.startFingerprint;
    sOriginKey[0] = data.originKey[0];
    sOriginKey[1] = data.originKey[1];
    sTapeStage = sStageGeneration;
    sTapeSlot = SavestateManager::kSlotCount;
    findTakeStart();
    sSteps = data.steps;
    sPaused = sPaused || (data.flags & SAVED_PAUSED);
    sTakeAttached = true;
    if (settingsHash() != sSettingsHash) {
        sPaused = true;
        message("TAS saved; restore its gameplay settings to continue");
        return false;
    }
    sRecord = (data.flags & SAVED_RECORDING) && sCount < kMaxFrames;
    sStripButtons |= gBinds.get(BIND_SAVESTATE_LOAD);
    message(sRecord ? "TAS checkpoint loaded - recording continues" : "TAS checkpoint loaded");
    gBinds.suppressUntilRelease();
    return true;
}

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
    cancelLoadHold();
    sCameraWaitButtons = false;
    restoreCamera();
    ++sStageGeneration;
    sFreeCamera = false;
    sCamera = nullptr;
    sPaused = false;
    sBorrowedPause = false;
    sStepQueued = false;
    sMenuAction = 0;
    sFreeze = false;
    sAssisted = false;
    sHaveRead = false;
    sModalPadValid = false;
    sSteps = 0;
    sPendingReleases = 0;
    sCount = 0;
    sCursor = 0;
    sTakeAttached = false;
    sOriginKey[0] = sOriginKey[1] = 0;
    stopTape(nullptr);
    sStatus = sPausePending ? "Frame advance armed - waiting for Mario control" :
                             "Save a state before recording";
}

void beforeDirect(bool modalOwnsInput) {
    restoreCamera();
    sConsumedFrame = false;
    sStepping = false;
    sModal = modalOwnsInput;
    if (sLoadHoldButtons && (sPhysical.error != 0 ||
        (sPhysical.buttons & sLoadHoldButtons) != sLoadHoldButtons))
        cancelLoadHold();
    const bool injectedBeforeDirect = sFrameInjected;
    activatePendingPause();
    activatePendingLoadHold();
    if (!controlStage()) {
        if (!introStage()) cancelLoadHold();
        sCameraWaitButtons = false;
        sPaused = false;
        sStepQueued = false;
        sMenuAction = 0;
        sFreeze = false;
        sFreeCamera = false;
        if (sRecord || sReplay) stopTape("Input session ended: scene transition");
        return;
    }
    if (assisted()) {
        ILing::invalidateForAssist();
        Records::invalidateAttempt();
        Ghost::invalidateForAssist();
    }
    if ((sRecord || sReplay) && settingsHash() != sSettingsHash)
        stopTape("Settings changed - record again");
    if ((sRecord || sReplay) && actionsFastForwardActive())
        stopTape("Input session stopped: fast-forward");
    if (sReplay && sModal) stopTape("Input playback stopped: menu opened");
    if (((injectedBeforeDirect && !sReplay) || (sModal && sFreeCamera)) &&
        sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        inject(sPhysical, sReadPad);
        sReadPad->updateMeaning();
        sConsumed = sPhysical;
        sFrameInjected = false;
    }
    retainModalHistory();
    if (sMenuAction && !sModal && !(sPhysical.buttons & JUTGamePad::A)) {
        if (sMenuAction == 2) {
            sPaused = false;
            sStepQueued = false;
            if (!Ghost::observerActive()) sFreeCamera = false;
            message("Gameplay resumed");
            CrashReport::note(SUSAMUNE_CRASH_EVENT_PRACTICE, 0, sSteps);
        }
        sMenuAction = 0;
    }
    if (!sLoadHoldActive && !sLoadKind && sPaused && normalStage() && !sModal && !sMenuAction && sStepQueued &&
        !actionsFastForwardActive()) {
        sStepping = true;
        sStepQueued = false;
        sMenuAction = 0;
    }
    if (sStripButtons && !sModal && sHaveRead &&
        sReadPad == gpApplication.mGamePads[0] && !sReplay) {
        consumeControlInput();
        inject(sConsumed, sReadPad);
        sReadPad->updateMeaning();
    }
    sFreeze = (sPaused || sLoadKind || sLoadHoldActive) && !sStepping && normalStage();
    if (sFreeze && !sModal && sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        retainPausedReleases(sReadPad);
    }
    if (sFreeCamera && !sPaused &&
        gpMarDirector->mCurState != TMarDirector::STATE_PAUSE_MENU &&
        !Ghost::observerActive())
        sFreeCamera = false;
    updateCamera();
}

bool freezeRequested() { return sFreeze; }
bool ownsGameplayInput() { return sPaused || sFreeCamera || sReplay || sLoadKind != 0 || sLoadHoldActive; }

void afterDirect(s32 appState, bool gameplayActive) {
    gQFTTimer.endPracticePause();
    if (sBorrowedPause) {
        if (stageReady() && gpMarDirector->mCurState == TMarDirector::STATE_STAGE_EXIT_2)
            gpMarDirector->mCurState = TMarDirector::STATE_NORMAL;
        sBorrowedPause = false;
    }
    restoreCamera();
    // Retail keeps looping for WAIT (0) and DEFAULT (1).
    if (!stageReady() || appState > TApplication::CONTEXT_DIRECT_MAIN_LOOP) {
        cancelLoadHold();
        sCameraWaitButtons = false;
        if (sRecord || sReplay) stopTape("Input session ended: scene transition");
        sFreeCamera = false;
        sPaused = false;
        sStepQueued = false;
        sMenuAction = 0;
        sFreeze = false;
        return;
    }
    sModal = sModal || WarpWheel::shown() || WarpWheel::promptPending();
    if (sReplay && sModal)
        stopTape("Input session ended: overlay opened");
    if (sFreeze && !sModal && sHaveRead && sReadPad == gpApplication.mGamePads[0]) {
        restorePad(sBeforeRead, sReadPad);
    }
    if ((sRecord || sReplay) && !controlStage())
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
    if (sRecord) {
        if (sCount == kMaxFrames) {
            stopTape("Input recording full");
        } else {
            writeFrame(sFrames[sCount], sConsumed, fingerprint(), sPendingReleases);
            ++sCount;
            sTakePosition = sCount;
            sTakeAttached = true;
            if (sCount == kMaxFrames) stopTape("Input recording full");
        }
    } else if (sReplay && sFrameInjected) {
        const u32 expected = sFrames[sCursor].fingerprint & kFrameFingerprintMask;
        ++sCursor;
        sTakePosition = sCursor;
        sTakeAttached = true;
        if ((fingerprint() & kFrameFingerprintMask) != expected) {
            snprintf(sReplayFailure, sizeof(sReplayFailure),
                     "Replay stopped at frame %lu: game state differed", sCursor);
            stopTape(sReplayFailure);
            sTakeAttached = false;
            CrashReport::note(SUSAMUNE_CRASH_EVENT_REPLAY, 3, sCursor);
            sPaused = true;
        } else if (sCursor == sCount) {
            stopTape("Playback finished - fingerprints matched");
            sPaused = true;
        }
    } else if (!sReplay) {
        sTakeAttached = false;
    }
    sPendingReleases = 0;
}

void afterDraw() {
    restoreCamera();
    if (!sLoadKind) return;
    // Only the command press must release; gameplay buttons may remain held.
    sStartRelease &= sPhysical.buttons;
    if ((gMenu && gMenu->shown()) || WarpWheel::shown() || WarpWheel::promptPending() ||
        StageLoader::resultOwnsInput() || SavestateManager::diskBusy()) return;
    if (sPhysical.error != 0) {
        stopTape("Controller disconnected - input canceled");
        return;
    }
    if (sStartRelease) return;
    const u32 slot = sLoadSlot;
    const u32 generation = sLoadGeneration;
    if (!normalStage() || !seedMatches(slot, generation)) {
        stopTape("Save a new gameplay state first");
        return;
    }
    if (sLoadKind == 2 && settingsHash() != sSettingsHash) {
        stopTape("Settings changed since recording - record again");
        return;
    }
    if (gpCardManager && gpCardManager->getLastStatus() == CARD_ERROR_BUSY) {
        if (++sLoadWait >= 600) stopTape("Memory card busy - input canceled");
        return;
    }
    const u8 kind = sLoadKind;
    SavestateData seedData;
    if (!gSavestateMgr->practiceData(slot, &seedData)) {
        stopTape("TAS start state is unavailable");
        return;
    }
    const bool recordPaused = kind == 1 && (sPaused || (seedData.flags & SAVED_PAUSED));
    sOwnRestoreValid = false;
    sOwnLoad = true;
    const bool loaded = gSavestateMgr->loadSlot(slot, generation);
    sOwnLoad = false;
    sLoadKind = 0;
    sLoadWait = 0;
    if (!loaded) {
        stopTape("Couldn't load recording's savestate");
        return;
    }
    if (!sOwnRestoreValid) {
        stopTape(nullptr);
        sPaused = true;
        return;
    }
    sHaveRead = false;
    sPaused = recordPaused;
    sPausePending = false;
    sStepQueued = false;
    sMenuAction = 0;
    sStripButtons = 0;
    sStartRelease = 0;
    sPriorButtons = sPhysical.buttons;
    sFreeCamera = false;
    sCursor = 0;
    sTakePosition = 0;
    if (kind == 1) {
        sCount = 0;
        sTapeHash = 0;
        sTapeSeed = generation;
        sTapeSlot = slot;
        sTapeStage = sStageGeneration;
        sOriginKey[0] = seedData.stateKey[0];
        sOriginKey[1] = seedData.stateKey[1];
        sTakeAttached = true;
        sTapeStart = fingerprint();
        sSettingsHash = settingsHash();
        sRecord = true;
        message("Recording inputs - Stop keeps this take");
    } else {
        if (fingerprint() != sTapeStart) {
            stopTape("Replay start differs - save a new state and record");
            sPaused = true;
            return;
        }
        sReplay = true;
        message("Input playback - B or Start stops");
    }
    CrashReport::note(SUSAMUNE_CRASH_EVENT_REPLAY, kind, sCount);
    invalidate();
    gBinds.suppressUntilRelease();
}

void onSavestateSaved(u32 slot, u32 generation) {
    if (slot >= SavestateManager::kSlotCount || !generation) return;
    const bool replacedTake = sTapeSlot == slot && sTapeSeed &&
                              sTapeSeed != generation;
    const bool replacedRequest = sLoadKind && sLoadSlot == slot &&
                                 sLoadGeneration != generation;
    if (replacedRequest || (replacedTake && sReplay))
        stopTape("Recording's savestate replaced - input stopped");
    if (replacedTake) {
        sTapeSeed = 0;
        sTapeSlot = SavestateManager::kSlotCount;
    }
}

void onSavestateCleared(u32 slot, u32 generation) {
    if (slot >= SavestateManager::kSlotCount || !generation) return;
    const bool removedTake = sTapeSlot == slot && sTapeSeed == generation;
    const bool removedRequest = sLoadKind && sLoadSlot == slot &&
                                sLoadGeneration == generation;
    if (removedRequest || (removedTake && sReplay))
        stopTape("Recording's savestate cleared - input stopped");
    if (removedTake) {
        sTapeSeed = 0;
        sTapeSlot = SavestateManager::kSlotCount;
    }
}

void onSavestateLoaded() {
    sModalPadValid = false;
    sPendingReleases = 0;
    const bool held = !sOwnLoad && sLoadHoldButtons && sPhysical.error == 0 &&
        (sPhysical.buttons & sLoadHoldButtons) == sLoadHoldButtons;
    sLoadHoldActive = held && controlStage();
    sLoadHoldPending = held && introStage();
    if (!sLoadHoldActive && !sLoadHoldPending) sLoadHoldButtons = 0;
    // An intro must finish enabling Mario before the previous pause can resume.
    if (sLoadHoldPending && sPaused) {
        sPausePending = true;
        sPaused = false;
    }
    sCameraWaitButtons = false;
    sMenuAction = 0;
    restoreCamera();
    sCamera = nullptr;
    sFreeCamera = false;
    sStepQueued = false;
    sHaveRead = false;
    if (!sOwnLoad) {
        stopTape(nullptr);
        sTakeAttached = false;
    }
    invalidate();
}

void armLoadHold(u16 buttons) {
    sLoadHoldButtons = buttons;
    sLoadHoldActive = false;
    sLoadHoldPending = false;
}

void cancelLoadHold() {
    sLoadHoldButtons = 0;
    sLoadHoldActive = false;
    sLoadHoldPending = false;
}

bool holdingLoad() { return sLoadHoldActive; }

bool requestPauseToggle(bool fromMenu) {
    if (!available() || !sCollisionHooksReady || !sStateHookReady) {
        message("Frame advance is unavailable");
        return false;
    }
    if (!fromMenu)
        sStripButtons |= gBinds.get(BIND_PRACTICE_PAUSE);
    if (sPausePending) {
        sPausePending = false;
        message("Buffered frame pause canceled");
        return true;
    }
    if (!sPaused && !actionableStage()) {
        if (sReplay) stopTape(nullptr);
        sPausePending = true;
        message("Frame advance armed - waiting for Mario control");
        return true;
    }
    if (sReplay) stopTape("Input playback stopped for frame advance");
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
        if (!Ghost::observerActive()) { sFreeCamera = false; restoreCamera(); }
    }
    else invalidate();
    message(sPaused ? "Paused - hold your inputs, then press Step" : "Gameplay resumed");
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
        if (sReplay) stopTape(nullptr);
        sPausePending = true;
        message("Frame advance armed - waiting for Mario control");
        return true;
    }
    if (!sPaused) {
        if (sReplay) stopTape(nullptr);
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
        if (sReplay) stopTape(nullptr);
        sPausePending = false;
        sPaused = true;
        sStepQueued = false;
        sMenuAction = 0;
    }
    recenterCamera();
    sFreeCamera = true;
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
    const u32 slot = gSavestateMgr ? gSavestateMgr->activeSlot() :
                                   SavestateManager::kSlotCount;
    const u32 generation = gSavestateMgr ?
        gSavestateMgr->slotInfo(slot).generation : 0;
    if (!available() || !normalStage() || !seedMatches(slot, generation) ||
        Ghost::observerStatsSuppressed()) {
        message("Save a new gameplay state in Save to first");
        return false;
    }
    SavestateData seedData;
    if (!gSavestateMgr->practiceData(slot, &seedData) ||
        !(seedData.flags & SAVED_RNG) || !gSettings.getBool(SETTING_SAVE_RNG_STATE)) {
        message("Turn on Save RNG state, then save a new state");
        return false;
    }
    queueTapeLoad(1, slot, generation);
    return true;
}

bool requestPlayback() {
    if (!tapeStorageReady()) {
        message("Input sessions need a matching launcher");
        return false;
    }
    if (!available() || !normalStage() || sCount == 0 ||
        sTapeStage != sStageGeneration || Ghost::observerStatsSuppressed()) {
        message("Record a take with this savestate first");
        return false;
    }
    if (!findTakeStart()) {
        message("Import this TAS's start state into a memory slot to replay");
        return false;
    }
    if (sRecord) stopTape(nullptr);
    if (settingsHash() != sSettingsHash) {
        message("Settings changed since recording - record again");
        return false;
    }
    if (hashBytes(2166136261u, sFrames, sCount * sizeof(Frame)) != sTapeHash) {
        message("Input recording is damaged - record again");
        return false;
    }
    queueTapeLoad(2, sTapeSlot, sTapeSeed);
    return true;
}

bool requestContinue() {
    if (!available() || !normalStage() || !sTakeAttached || !tapeStorageReady() ||
        Ghost::observerStatsSuppressed() || sTakePosition >= kMaxFrames || sTakePosition > sCount) {
        message("Load a TAS checkpoint before continuing");
        return false;
    }
    if (settingsHash() != sSettingsHash) {
        message("Restore this TAS's gameplay settings to continue");
        return false;
    }
    if (sRecord || sReplay) stopTape(nullptr);
    if (hashBytes(2166136261u, sFrames, sCount * sizeof(Frame)) != sTapeHash) {
        message("Input recording is damaged - load a checkpoint");
        return false;
    }
    sCount = sTakePosition;
    sTapeHash = hashBytes(2166136261u, sFrames, sCount * sizeof(Frame));
    sRecord = true;
    sPaused = true;
    sPausePending = sStepQueued = false;
    sStripButtons |= JUTGamePad::A;
    invalidate();
    message("TAS editing resumed - Step or Resume when ready");
    return true;
}

void requestStop() {
    if (sReplay) {
        sPaused = true;
        sPausePending = sStepQueued = false;
    }
    if (gBinds.wasPressed(BIND_PRACTICE_STOP))
        sStripButtons |= gBinds.get(BIND_PRACTICE_STOP);
    stopTape("Input session stopped");
    gBinds.suppressUntilRelease();
}

void releaseForDeparture() {
    sModalPadValid = false;
    sPendingReleases = 0;
    cancelLoadHold();
    sPausePending = false;
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
    sStepping = false;
    sFreeze = false;
    sConsumedFrame = false;
    sHaveRead = false;
    sFrameInjected = false;
    sMenuAction = 0;
    sStripButtons = 0;
}

bool paused() { return sPaused || sLoadHoldActive; }
bool manualPaused() { return sPaused; }
bool pausePending() { return sPausePending; }
bool freeCamera() { return sFreeCamera; }
bool hideHud() {
    return sFreeCamera && controlStage() &&
           gSettings.getBool(SETTING_FREE_CAMERA_HIDE_HUD);
}
bool recording() { return sRecord; }
bool replaying() { return sReplay; }
bool starting() { return sLoadKind != 0; }
bool assisted() { return sAssisted; }
bool available() { return sPadHookReady; }
u32 stepCount() { return sSteps; }
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
        (!sPausePending && !sFreeCamera && !sRecord && !sReplay && !sLoadKind)) return;
    char text[96];
    if (sPausePending) snprintf(text, sizeof(text), "FRAME ADVANCE ARMED - waiting for Mario control");
    else if (sRecord) snprintf(text, sizeof(text), "INPUT REC  %lu / %lu", sCount, kMaxFrames);
    else if (sReplay) snprintf(text, sizeof(text), "INPUT PLAY  %lu / %lu", sCursor, sCount);
    else if (sFreeCamera) snprintf(text, sizeof(text), "CAMERA ON  %.2fx  X boost  Mario input OFF",
                                  cameraSpeedScale());
    else snprintf(text, sizeof(text), sStartRelease ?
        "INPUT SESSION - release the command buttons" : "INPUT SESSION - waiting to load state");
    menu->fillBox(42, 388, 556, 40, JUtility::TColor(8, 17, 31, 225));
    menu->drawText(text, 50, 394, 16, 16, JUtility::TColor(130, 225, 255, 255));
    menu->drawText(sFreeCamera ? "Turn camera Off to step with A or other Mario inputs" :
                   sRecord ? "Save checkpoints to keep inputs. Use Stop to finish the take." :
                   sReplay ? "B or Start stops playback." :
                   "Other gameplay buttons can stay held. Stop cancels this request.", 50, 413, 12, 12,
                   JUtility::TColor(235, 235, 235, 255));
}

} // namespace PracticeSession
