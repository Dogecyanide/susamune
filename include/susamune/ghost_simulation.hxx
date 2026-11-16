#pragma once
#include "susamune/ghost_simulation_settings.h"

class TMario;

namespace GhostSimulation {
enum { kSchema = SUSAMUNE_GHOST_SIMULATION_SCHEMA,
       kSnapshotSize = SUSAMUNE_GHOST_SIMULATION_SIZE, kSettingCount = 40,
       kValueCount = SUSAMUNE_GHOST_SIMULATION_VALUE_COUNT };
// Wire ordinals are independent of persistent setting IDs. Keep existing slots fixed.
enum Field {
    FAST_TEXT = 0,
    FLUDD_SECRETS = 1,
    AREA_LOCK = 2,
    INFINITE_LIVES = 3,
    DISABLE_BLUE_COIN = 4,
    FMV_SKIPS = 5,
    UNLOCK_YOSHI = 6,
    UNLOCK_NOZZLES = 7,
    FREE_PAUSE = 8,
    EXIT_AREA_EVERYWHERE = 9,
    ANY_FRUIT_YOSHI = 10,
    INFINITE_JUICE = 11,
    INTRO_SKIP = 12,
    RESPAWN_SHINES = 13,
    FAST_PIANTISSIMO = 14,
    SAVE_RNG_STATE = 15,
    NOZZLE_LOCK = 16,
    FORCE_PLAZA_EVENTS = 17,
    NEVER_PAUSE_IGT = 18,
    SHADOW_MARIO_HP = 19,
    STAGE_INTRO_SKIP = 20,
    DEATHLESS_BLOOPER = 21,
    NO_SHINE_ANIM = 22,
    FRUIT_NEVER_TIMEOUT = 23,
    DISABLE_Z_MENU = 24,
    DISABLE_WARPS = 25,
    DISABLE_THIRD_CHOMPLET_AGGRO = 26,
    PATTERN_SELECTOR = 27,
    FORCE_BOX_GAME = 28,
    YOSHI_NOZZLE_SAVE_PROMPT = 29,
    DISABLE_RETAIL_PAUSE = 30,
    KING_BOO_ALWAYS_FRUIT = 31,
    PETEY_NO_TORNADO = 32,
    PETEY_ROUTE = 33,
    RICCO_CRANE_SPEED = 34,
    RICCO_FRUIT_MACHINE = 35,
    GELATO_RED_COIN_FISH_PATTERN = 36,
    GELATO_BLUE_BIRD_PATTERN = 37,
    GAMEPLAY_SPEED = 38,
    SLOWDOWN_PRESET = 39,
    EFFECTIVE_FAST_TEXT = 40,
    PATTERN_0 = 41,
    PATTERN_1 = 42,
    PATTERN_2 = 43,
    FAST_FORWARD_ACTIVE = 44,
    FREE_CAMERA_ACTIVE = 45,
    SIRENA_PINEAPPLE_REMOVED = 46,
    CADENCE_F32_BE = 48,
    STICK_MODE_U32_BE = 52,
};
struct Snapshot { unsigned char bytes[kSnapshotSize]; };
static_assert(sizeof(Snapshot) == 64, "simulation settings wire size");
// Byte 47 and 56..63 are zero. Pineapple uses 255 when flag state is unavailable.
void capture(Snapshot &out);
struct SettingsLease { unsigned char original[kSettingCount], patterns[3]; bool active; };
bool beginSettings(SettingsLease &,const unsigned char *recorded);
void restoreSettings(SettingsLease &);


struct CameraObservation {
    short yaw;
    unsigned short mode, tickCount;
    bool varied, valid;
};
// Reset before direct(), observe immediately before the retail Mario MOVE call.
void beginFrame();
void observeMovement(TMario *mario, unsigned int cue);
void readCamera(CameraObservation &out);
}

