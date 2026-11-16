#include "susamune/ghost_simulation.hxx"
#include "susamune/actions.hxx"
#include "susamune/addresses.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/settings.hxx"
#include "susamune/stage_loader.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "Dolphin/mem.h"
#include "susamune/retail_input.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "SMS/Player/Mario.hxx"

#include "susamune/pattern_selector.hxx"

namespace GhostSimulation {
namespace {
const u8 kSettingIds[kSettingCount] = {
    SETTING_FAST_TEXT,
    SETTING_FLUDD_SECRETS,
    SETTING_AREA_LOCK,
    SETTING_INFINITE_LIVES,
    SETTING_DISABLE_BLUE_COIN,
    SETTING_FMV_SKIPS,
    SETTING_UNLOCK_YOSHI,
    SETTING_UNLOCK_NOZZLES,
    SETTING_FREE_PAUSE,
    SETTING_EXIT_AREA_EVERYWHERE,
    SETTING_ANY_FRUIT_YOSHI,
    SETTING_INFINITE_JUICE,
    SETTING_INTRO_SKIP,
    SETTING_RESPAWN_SHINES,
    SETTING_FAST_PIANTISSIMO,
    SETTING_SAVE_RNG_STATE,
    SETTING_NOZZLE_LOCK,
    SETTING_FORCE_PLAZA_EVENTS,
    SETTING_NEVER_PAUSE_IGT,
    SETTING_SHADOW_MARIO_HP,
    SETTING_STAGE_INTRO_SKIP,
    SETTING_DEATHLESS_BLOOPER,
    SETTING_NO_SHINE_ANIM,
    SETTING_FRUIT_NEVER_TIMEOUT,
    SETTING_DISABLE_Z_MENU,
    SETTING_DISABLE_WARPS,
    SETTING_DISABLE_THIRD_CHOMPLET_AGGRO,
    SETTING_PATTERN_SELECTOR,
    SETTING_FORCE_BOX_GAME,
    SETTING_YOSHI_NOZZLE_SAVE_PROMPT,
    SETTING_DISABLE_RETAIL_PAUSE,
    SETTING_KING_BOO_ALWAYS_FRUIT,
    SETTING_PETEY_NO_TORNADO,
    SETTING_PETEY_ROUTE,
    SETTING_RICCO_CRANE_SPEED,
    SETTING_RICCO_FRUIT_MACHINE,
    SETTING_GELATO_RED_COIN_FISH_PATTERN,
    SETTING_GELATO_BLUE_BIRD_PATTERN,
    SETTING_GAMEPLAY_SPEED,
    SETTING_SLOWDOWN_PRESET,
};
static_assert(SLOWDOWN_PRESET + 1 == kSettingCount &&
              SIRENA_PINEAPPLE_REMOVED + 1 == kValueCount,
              "simulation snapshot field mapping");
void putWord(u8 *out, u32 value) {
    out[0] = value >> 24; out[1] = value >> 16;
    out[2] = value >> 8; out[3] = value;
}
}

void restoreSettings(SettingsLease &lease) {
    if(!lease.active)return;
    for(unsigned i=0;i<kSettingCount;++i)
        gSettings.setTransient(static_cast<SettingId>(kSettingIds[i]),lease.original[i]);
    PatternSelector::setPatternsTransient(lease.patterns);
    lease.active=false;
}
bool beginSettings(SettingsLease &lease,const unsigned char *recorded) {
    if(lease.active||!SusamuneGhostSimulationSettingsValid(recorded)||
       gSettings.saveState()==SETTINGS_SAVE_PENDING)return false;
    for(unsigned i=0;i<kSettingCount;++i)
        lease.original[i]=gSettings.get(static_cast<SettingId>(kSettingIds[i]));
    PatternSelector::copyPatterns(lease.patterns);
    lease.active=true;
    PatternSelector::setPatternsTransient(recorded+PATTERN_0);
    for(unsigned i=0;i<kSettingCount;++i)if(!gSettings.setTransient(static_cast<SettingId>(kSettingIds[i]),recorded[i])) {
        restoreSettings(lease);return false;
    }
    return true;
}

void capture(Snapshot &out) {
    memset(out.bytes, 0, sizeof(out.bytes));
    for (u32 i = 0; i < kSettingCount; ++i)
        out.bytes[i] = gSettings.get(static_cast<SettingId>(kSettingIds[i]));
    out.bytes[EFFECTIVE_FAST_TEXT] = out.bytes[FAST_TEXT] && !StageLoader::fastTextSuppressed();
    PatternSelector::copyPatterns(out.bytes + PATTERN_0);
    out.bytes[FAST_FORWARD_ACTIVE] = actionsFastForwardActive();
    out.bytes[FREE_CAMERA_ACTIVE] = PracticeSession::freeCamera();
    out.bytes[SIRENA_PINEAPPLE_REMOVED] = TFlagManager::smInstance
        ? TFlagManager::smInstance->getBool(0x1038B) : 255;
    union { f32 value; u32 bits; } cadence = {SMSGetVSyncTimesPerSec()};
    putWord(out.bytes + CADENCE_F32_BE, cadence.bits);
    const __UINTPTR_TYPE__ mode = SUSAMUNE_MEM1_ADDR(0x80408ad0u, 0x8040cc10u, 0x80404370u);
    putWord(out.bytes + STICK_MODE_U32_BE, *reinterpret_cast<volatile const u32 *>(mode));
}
}

// This latch belongs to the current director call, never to a render override.
namespace GhostSimulation {
namespace {
CameraObservation sCamera;
TMarDirector *sCameraDirector;
CPolarSubCamera *sCameraOwner;
bool sCameraMissing;
static_assert(__builtin_offsetof(CPolarSubCamera, mAngleYaw) == 0x258 &&
              __builtin_offsetof(TMario, _14E) == 0x14e,
              "simulation camera and freeze layout");
bool mem1(const void *p, unsigned bytes) {
    const __UINTPTR_TYPE__ address = reinterpret_cast<__UINTPTR_TYPE__>(p);
    return address >= 0x80000000u && address <= 0x81800000u - bytes;
}
}

void beginFrame() {
    memset(&sCamera, 0, sizeof(sCamera));
    sCameraMissing = false;
}

void observeMovement(TMario *mario, unsigned int cue) {
    TMarDirector *director = RetailInput::stageDirector();
    if (!(cue & 1u) || mario != gpMarioOriginal || !mem1(mario, 0x150) ||
        !director || director != gpMarDirector || !director->_260 ||
        mario->mAttributes.mIsPerforming || static_cast<short>(mario->_14E) > 1) return;
    if (sCamera.tickCount != 0xffff) ++sCamera.tickCount;
    else sCamera.varied = true;
    if (!mem1(gpCamera, 0x25c)) { sCameraMissing = true; return; }
    const int mode = *reinterpret_cast<const int *>(reinterpret_cast<const u8 *>(gpCamera) + 0x50);
    if (mode < 0 || mode > 0x49) { sCameraMissing = true; return; }
    const short yaw = gpCamera->mAngleYaw;
    if (sCamera.valid && (sCamera.yaw != yaw || sCamera.mode != mode)) sCamera.varied = true;
    sCamera.yaw = yaw;
    sCamera.mode = static_cast<unsigned short>(mode);
    sCamera.valid = true;
    sCameraDirector = director;
    sCameraOwner = gpCamera;
}

void readCamera(CameraObservation &out) {
    out = sCamera;
    out.valid = out.valid && !sCameraMissing &&
        sCameraDirector == RetailInput::stageDirector() && sCameraOwner == gpCamera;
}
}
