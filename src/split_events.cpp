#include "susamune/split_events.hxx"

#include "susamune/addresses.hxx"
#include "susamune/features.hxx"
#include "susamune/ghost.hxx"
#include "susamune/iling.hxx"
#include "susamune/qft_timer.hxx"
#include "susamune/settings.hxx"
#include "susamune/split_stats.hxx"

#include "Dolphin/OS.h"
#include "Dolphin/string.h"
#include "SMS/Enemy/Conductor.hxx"
#include "SMS/Enemy/SpineBase.hxx"
#include "SMS/Enemy/SpineEnemy.hxx"
#include "SMS/Manager/EnemyManager.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/Manager/PollutionManager.hxx"
#include "SMS/MapObj/MapObjRail.hxx"
#include "SMS/MoveBG/ResetFruit.hxx"
#include "SMS/MoveBG/Shine.hxx"
#include "SMS/NPC/NpcBase.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/Strategic/LiveActor.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"

extern "C" void susamuneSplitSpineUpdate(TSpineBase<TLiveActor> *spine);
extern "C" void susamuneSplitStartDemo(
    TMarDirector *director, const char *name, const TVec3f *position,
    s32 camera, f32 blend, bool flag, s32 (*callback)(u32, u32),
    u32 callbackArg, JDrama::TActor *actor,
    const JDrama::TFlagT<u16> *demoFlag);
extern "C" void susamuneSplitOpenTalk(void *talk, TBaseNPC *npc);
extern "C" bool susamuneSplitRailCheck(TRailMapObj *rail);
extern "C" void susamuneSplitBathtubQuake(void *bathtub,
                                            const void *position);
extern "C" void susamuneSplitPeteyHipDrop(void *petey);
extern "C" void susamuneSplitGessoTentacleDamage(void *gesso);
extern "C" bool susamuneSplitEelToothMessage(void *tooth,
                                               THitActor *sender, u32 message);
extern "C" bool susamuneSplitFenceMessage(void *fence,
                                            THitActor *sender, u32 message);
extern "C" bool susamuneSplitRevolvingFenceMessage(void *fence,
                                                     THitActor *sender,
                                                     u32 message);

extern "C" void susamuneSplitStreamingMovie(TMarDirector *director, u8 movie);
extern "C" void susamuneSplitItemAppear(void *actor);

extern "C" void susamuneSplitSandCastle(void *actor);

extern "C" bool susamuneSplitMirrorMessage(void *actor, THitActor *sender, u32 message);

extern "C" void susamuneSplitHanachanDamage(void *actor);

extern "C" void susamuneSplitTinKoopaHit(void *actor);

namespace {

static_assert(__builtin_offsetof(TBaseNPC, mDummyConnectActor) == 0x1D4,
              "dummy NPC actor layout drifted");

static_assert(__builtin_offsetof(TRailMapObj, mControlState) == 0x140,
              "rail control-state layout drifted");

struct CarryDesc {
    u16 route;
    u8 parentArea;
    u8 parentEpisode;
    u8 childArea;
    u8 childEpisode;
};

const CarryDesc kCarryRoutes[] = {
    {SplitStats::ROUTE_AIRSTRIP_1, 0, 0, 0, 1},
    {SplitStats::ROUTE_RICCO_1, 3, 0, 0x3B, 0},
    {SplitStats::ROUTE_RICCO_2, 3, 1, 0x1E, 0},
    {SplitStats::ROUTE_RICCO_4, 3, 3, 0x30, 0},
    {SplitStats::ROUTE_BIANCO_2, 2, 0, 0x37, 0},
    {SplitStats::ROUTE_BIANCO_3_FULL, 2, 2, 0x2F, 0},
    {SplitStats::ROUTE_BIANCO_6_FULL, 2, 5, 0x2E, 0},
    {SplitStats::ROUTE_PIANTA_5_FULL, 8, 4, 0x2A, 0},
    {SplitStats::ROUTE_PINNA_1, 0x0D, 6, 0x3A, 1},
    {SplitStats::ROUTE_PINNA_8, 0x0D, 5, 0x3A, 0},
    {SplitStats::ROUTE_PINNA_2_FULL, 5, 1, 0x32, 0},
    {SplitStats::ROUTE_PINNA_EYG, 5, 2, 0x29, 0},
    {SplitStats::ROUTE_SIRENA_2_FULL, 6, 1, 7, 0},
    {SplitStats::ROUTE_SIRENA_2_FULL, 7, 0, 0x33, 0},
    {SplitStats::ROUTE_SIRENA_3, 6, 2, 7, 1},
    {SplitStats::ROUTE_SIRENA_4_FULL, 6, 3, 7, 2},
    {SplitStats::ROUTE_SIRENA_4_FULL, 7, 2, 0x0E, 0},
    {SplitStats::ROUTE_SIRENA_4_FULL, 0x0E, 0, 0x28, 0},
    {SplitStats::ROUTE_SIRENA_5, 6, 4, 7, 2},
    {SplitStats::ROUTE_SIRENA_5, 7, 2, 0x0E, 1},
    {SplitStats::ROUTE_SIRENA_5, 0x0E, 1, 0x38, 0},
    {SplitStats::ROUTE_SIRENA_7, 6, 6, 7, 3},
    {SplitStats::ROUTE_NOKI_4_FULL, 9, 3, 0x39, 0},
    {SplitStats::ROUTE_NOKI_6_FULL, 9, 5, 0x1F, 0},
    {SplitStats::ROUTE_CORONA, 0x34, 0, 0x3C, 0},
    {SplitStats::ROUTE_BIANCO_3_FULL_REDS, 2, 2, 0x2F, 0},
    {SplitStats::ROUTE_BIANCO_6_FULL_REDS, 2, 5, 0x2E, 0},
    {SplitStats::ROUTE_RICCO_4_FULL_REDS, 3, 3, 0x30, 0},
    {SplitStats::ROUTE_PIANTA_5_FULL_REDS, 8, 4, 0x2A, 0},
    {SplitStats::ROUTE_PINNA_2_FULL_REDS, 5, 1, 0x32, 0},
    {SplitStats::ROUTE_SIRENA_2_FULL_REDS, 6, 1, 7, 0},
    {SplitStats::ROUTE_SIRENA_2_FULL_REDS, 7, 0, 0x33, 0},
    {SplitStats::ROUTE_SIRENA_4_FULL_REDS, 6, 3, 7, 2},
    {SplitStats::ROUTE_SIRENA_4_FULL_REDS, 7, 2, 0x0E, 0},
    {SplitStats::ROUTE_SIRENA_4_FULL_REDS, 0x0E, 0, 0x28, 0},
    {SplitStats::ROUTE_NOKI_6_FULL_REDS, 9, 5, 0x1F, 0},
    {SplitStats::ROUTE_GELATO_1_FULL, 0x04, 0, 0x20, 0},
    {SplitStats::ROUTE_GELATO_1_FULL_REDS, 0x04, 0, 0x20, 0},
    {SplitStats::ROUTE_GELATO_4, 0x04, 3, 0x21, 0},
    {SplitStats::ROUTE_PINNA_6_FULL, 0x0D, 3, 0x29, 0},
    {SplitStats::ROUTE_PINNA_6_FULL_REDS, 0x0D, 3, 0x29, 0},
    {SplitStats::ROUTE_PINNA_6_FULL_REDS, 5, 5, 0x0D, 3},
    {SplitStats::ROUTE_NOKI_8, 0x09, 7, 0x2C, 0},
};

const int kPiantaCount = 10;

const u32 kMarioDiveStatus = 0x0080088Au;
const u32 kMarioSpinLeftStatus = 0x00000895u;
const u32 kMarioSpinRightStatus = 0x00000896u;
const u32 kMarioBounceStatus = 0x00000884u;
const u32 kMarioSurfStatus = 0x00810446u;
const u32 kMarioHangRoofStatus = 0x08200348u;
const u32 kMarioRolloutStatus = 0x02000889u;
const u32 kMarioLedgeGrabStatus = 0x3800034Bu;
const u32 kMarioWallKickStatus = 0x02000886u;
const u32 kMarioThrowObjectStatus = 0x820008ABu;
const u32 kBossGessoVtable =
    SUSAMUNE_MEM1_ADDR(0x803D7334u, 0x803B2AFCu, 0x803AA91Cu);
const u32 kEmarioVtable =
    SUSAMUNE_MEM1_ADDR(0x803D2C5Cu, 0x803AE404u, 0x803A6784u);
const u32 kEnemyMarioVtable =
    SUSAMUNE_MEM1_ADDR(0x803D376Cu, 0x803AEF24u, 0x803A72A4u);
const u32 kShineVtable =
    SUSAMUNE_MEM1_ADDR(0x803C11E4u, 0x803C97ECu, 0x803C0FDCu);
const u32 kGatekeeperVtable =
    SUSAMUNE_MEM1_ADDR(0x803DFDF4u, 0x803BB71Cu, 0x803B353Cu);
const u32 kPeteyVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8E0Cu, 0x803B45D4u, 0x803AC3F4u);
const u32 kPeteyManagerVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8DB8u, 0x803B4580u, 0x803AC3A0u);
const u32 kFireWanwanVtable =
    SUSAMUNE_MEM1_ADDR(0x803D87C0u, 0x803B3F88u, 0x803ABDA8u);
const u32 kBossWanwanVtable =
    SUSAMUNE_MEM1_ADDR(0x803DA9C0u, 0x803B6178u, 0x803ADF98u);
const u32 kTamaNokoVtable =
    SUSAMUNE_MEM1_ADDR(0x803DBF54u, 0x803B770Cu, 0x803AF52Cu);
const u32 kTinKoopaVtable =
    SUSAMUNE_MEM1_ADDR(0x803DA2E0u, 0x803B5AA8u, 0x803AD8C8u);
const u32 kBossTelesaVtable =
    SUSAMUNE_MEM1_ADDR(0x803DC364u, 0x803B7B1Cu, 0x803AF93Cu);
const u32 kCannonVtable =
    SUSAMUNE_MEM1_ADDR(0x803DCFFCu, 0x803B8924u, 0x803B0744u);
const u32 kBossEelVtable =
    SUSAMUNE_MEM1_ADDR(0x803DD4F4u, 0x803B8E1Cu, 0x803B0C3Cu);
const u32 kMantaManagerVtable =
    SUSAMUNE_MEM1_ADDR(0x803E177Cu, 0x803BD0A4u, 0x803B4EC4u);
const u32 kBWLeashVtable =
    SUSAMUNE_MEM1_ADDR(0x803DAC80u, 0x803B6438u, 0x803AE258u);
const u32 kBWLeashNodeVtable =
    SUSAMUNE_MEM1_ADDR(0x803DACA4u, 0x803B645Cu, 0x803AE27Cu);
const u32 kFireWanwanTailVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8968u, 0x803B4130u, 0x803ABF50u);
const u32 kBWPicketVtable =
    SUSAMUNE_MEM1_ADDR(0x803DABCCu, 0x803B6384u, 0x803AE1A4u);
const u32 kFireWanwanManagerVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8A1Cu, 0x803B41E4u, 0x803AC004u);
const u32 kTinKoopaManagerVtable =
    SUSAMUNE_MEM1_ADDR(0x803DA0A4u, 0x803B586Cu, 0x803AD68Cu);

const u32 kBGKAppearVtable =
    SUSAMUNE_MEM1_ADDR(0x803DFDD4u, 0x803BB6FCu, 0x803B351Cu);
const u32 kBGKSleepVtable =
    SUSAMUNE_MEM1_ADDR(0x803DFDE4u, 0x803BB70Cu, 0x803B352Cu);
const u32 kPeteyBreakSleepVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8C38u, 0x803B4400u, 0x803AC220u);
const u32 kFireWanwanDieVtable =
    SUSAMUNE_MEM1_ADDR(0x803D8740u, 0x803B3F08u, 0x803ABD28u);
const u32 kBossWanwanDieVtable =
    SUSAMUNE_MEM1_ADDR(0x803DA8ECu, 0x803B60A4u, 0x803ADEC4u);
const u32 kTamaNokoHitWaterVtable =
    SUSAMUNE_MEM1_ADDR(0x803DBEE4u, 0x803B769Cu, 0x803AF4BCu);
const u32 kCannonDamageDemoVtable =
    SUSAMUNE_MEM1_ADDR(0x803DCF8Cu, 0x803B88B4u, 0x803B06D4u);
const u32 kBossEelWaitAppearVtable =
    SUSAMUNE_MEM1_ADDR(0x803DD4E4u, 0x803B8E0Cu, 0x803B0C2Cu);

TMarDirector *sStageDirector;
u32 sAttemptSerial;
u16 sActiveRoute = SplitStats::ROUTE_INVALID;
u16 sArmedCarryRoute = SplitStats::ROUTE_INVALID;
bool sAttemptInvalid;
bool sRetailDirectOpen;
bool sCarryAttempt;
bool sBlockNextAttempt;

TTakeActor *sPreHeldObject;
TVec3f sPreMarioPosition;
u16 sPreMarioHealth;
s32 sPrePollutionDegree;
bool sPreStateValid;
bool sPrePollutionValid;
bool sCoconutThrowArmed;

TSpineEnemy *sTinKoopa;
TSpineEnemy *sBossGesso;
TSpineEnemy *sBossEel;
TSpineEnemy *sPetey;
u8 sGatekeeperHits;
u8 sHanachanHits;
u8 sTinKoopaHits;
u8 sMirrorsCleared;
void *sClearedMirrors[3];
u8 sPeteyHits;
u8 sBossGessoHits;
u8 sBossGessoHealth;
u8 sPeteyHealth;
u8 sBossTelesaHits;
u8 sFireWanwanDeaths;
u8 sEelCleanedCount;
bool sPeteyWakeSeen;
bool sTamaNokoWakeSeen;
bool sTamaNokoKillSeen;
bool sBossWanwanWaterSeen;
bool sCannonKilledSeen;
bool sEelActivatedSeen;
bool sTinKoopaFourthSeen;
bool sBossGessoHealthValid;
bool sPeteyHealthValid;
bool sMantaPinkSeen;
bool sNoki2FirstWallkick;
TLiveActor *sDeadFireWanwans[3];
u8 sGenericTalkCount;
void *sCleanedEelTeeth[8];
u8 sFireWanwanManagerKills;
bool sFireWanwanManagerValid;
void *sBathtub;
int sBowserGripsDead;
bool sBowserGripsValid;

s32 sLastRedCoinCount;
s32 sPreGoldCoins;
s32 sPreBalloons;
TResetFruit *sCoconut;
TBaseNPC *sRecoveredPiantas[kPiantaCount];
u8 sRecoveredPiantaCount;
u8 sCleanedPiantaCount;

u32 sCoinRedTakenTrampoline[2] = {0x7C0802A6u, 0};
u32 sEmitHappyEffectTrampoline[2] = {0x7C0802A6u, 0};
u32 sChangePlayerStatusTrampoline[2] = {0x7C0802A6u, 0};
u32 sSpineUpdateTrampoline[2] = {0x7C0802A6u, 0};
u32 sStartDemoTrampoline[2] = {0x9421FFC8u, 0};
u32 sOpenTalkTrampoline[2] = {0x7C0802A6u, 0};
u32 sRailCheckTrampoline[2] = {0x7C0802A6u, 0};
u32 sBathtubQuakeTrampoline[2] = {0x7C0802A6u, 0};
u32 sPeteyHipDropTrampoline[2] = {0, 0};
u32 sGessoTentacleDamageTrampoline[2] = {0, 0};
u32 sEelToothMessageTrampoline[2] = {0, 0};
u32 sFenceMessageTrampoline[2] = {0, 0};
u32 sRevolvingFenceMessageTrampoline[2] = {0, 0};
u32 sStreamingMovieTrampoline[2] = {0x7C0802A6u, 0};
u32 sItemAppearTrampoline[2] = {0x7C0802A6u, 0};
u32 sSandCastleTrampoline[2] = {0x7C0802A6u, 0};
u32 sMirrorMessageTrampoline[2] = {0x7C0802A6u, 0};
u32 sHanachanDamageTrampoline[2] = {0x7C0802A6u, 0};
u32 sTinKoopaHitTrampoline[2] = {0x7C0802A6u, 0};
bool sTrampolinesReady;

const u32 kCoinRedTaken =
    SUSAMUNE_MEM1_ADDR(0x801962C8u, 0x801BE428u, 0x801B62E0u);
const u32 kRecoverNerve =
    SUSAMUNE_MEM1_ADDR(0x80170928u, 0x8020C2B4u, 0x80204198u);
const u32 kEmitHappyEffect =
    SUSAMUNE_MEM1_ADDR(0x8017A274u, 0x80215B0Cu, 0x8020D9F0u);
const u32 kChangePlayerStatus =
    SUSAMUNE_MEM1_ADDR(0x80133424u, 0x80254034u, 0x8024BDC0u);
const u32 kSpineUpdate =
    SUSAMUNE_MEM1_ADDR(0x80111BD0u, 0x8003C8A8u, 0x8003C6F8u);
const u32 kStartDemo =
    SUSAMUNE_MEM1_ADDR(0x800ED7C0u, 0x8029A23Cu, 0x802920D4u);
const u32 kOpenTalk =
    SUSAMUNE_MEM1_ADDR(0x80214CF0u, 0x80153824u, 0x80148758u);
const u32 kRailCheck =
    SUSAMUNE_MEM1_ADDR(0x801C8CB4u, 0x801F1428u, 0x801E9300u);
const u32 kBathtubQuake =
    SUSAMUNE_MEM1_ADDR(0x801D3248u, 0x801FB674u, 0x801F3558u);
const u32 kGetNumGripsDead =
    SUSAMUNE_MEM1_ADDR(0x801D31C4u, 0x801FB5F0u, 0x801F34D4u);
const u32 kPeteyHipDrop =
    SUSAMUNE_MEM1_ADDR(0x802A8790u, 0x80095A0Cu, 0x8008F0ACu);
const u32 kGessoTentacleDamage =
    SUSAMUNE_MEM1_ADDR(0x8028B4F8u, 0x800786A0u, 0x80071D40u);
const u32 kEelToothMessage =
    SUSAMUNE_MEM1_ADDR(0x802E9194u, 0x800D7080u, 0x800D0720u);
const u32 kFenceMessage =
    SUSAMUNE_MEM1_ADDR(0x801C60ECu, 0x801EE7C4u, 0x801E669Cu);
const u32 kRevolvingFenceMessage =
    SUSAMUNE_MEM1_ADDR(0x801C5AB0u, 0x801EE188u, 0x801E6060u);
const u32 kStreamingMovie =
    SUSAMUNE_MEM1_ADDR(0x800ED5C8u, 0x8029A044u, 0x80291EDCu);
const u32 kItemAppear =
    SUSAMUNE_MEM1_ADDR(0x80196E08u, 0x801BEF68u, 0x801B6E20u);
const u32 kSandCastle =
    SUSAMUNE_MEM1_ADDR(0x801A9DECu, 0x801D2294u, 0x801CA14Cu);
const u32 kMirrorMessage =
    SUSAMUNE_MEM1_ADDR(0x801A968Cu, 0x801D1AB0u, 0x801C9968u);
const u32 kHanachanDamage =
    SUSAMUNE_MEM1_ADDR(0x802FF7ECu, 0x800ED9FCu, 0x800E709Cu);
const u32 kTinKoopaHit =
    SUSAMUNE_MEM1_ADDR(0x802B2B84u, 0x800A002Cu, 0x800996CCu);
const u32 kCurrentNpc =
    SUSAMUNE_MEM1_ADDR(0x8040A3E8u, 0x8040DFA8u, 0x80405670u);

typedef void (*CoinRedTakenFn)(void *, void *);
typedef void *(*RecoverNerveFn)();
typedef void (*EmitHappyEffectFn)(TBaseNPC *);
typedef int (*ChangePlayerStatusFn)(TMario *, u32, u32, bool);
typedef void (*SpineUpdateFn)(TSpineBase<TLiveActor> *);
typedef void (*StartDemoFn)(TMarDirector *, const char *, const TVec3f *, s32,
                            f32, bool, s32 (*)(u32, u32), u32,
                            JDrama::TActor *, const JDrama::TFlagT<u16> *);
typedef void (*OpenTalkFn)(void *, TBaseNPC *);
typedef bool (*RailCheckFn)(TRailMapObj *);
typedef void (*BathtubQuakeFn)(void *, const void *);
typedef int (*GetNumGripsDeadFn)(const void *);
typedef void (*PeteyHipDropFn)(void *);
typedef void (*GessoTentacleDamageFn)(void *);
typedef bool (*ReceiveMessageFn)(void *, THitActor *, u32);

u32 objectVtable(const void *object) {
    return object ? *reinterpret_cast<const u32 *>(object) : 0;
}

u32 nerveVtable(const TNerveBase<TLiveActor> *nerve) {
    return objectVtable(nerve);
}

void clearAttemptState() {
    sActiveRoute = SplitStats::ROUTE_INVALID;
    sLastRedCoinCount = 0;
    sCoconut = nullptr;
    sRecoveredPiantaCount = 0;
    sCleanedPiantaCount = 0;
    for (int i = 0; i < kPiantaCount; ++i)
        sRecoveredPiantas[i] = nullptr;
    sPreHeldObject = nullptr;
    sPreStateValid = false;
    sPrePollutionValid = false;
    sCoconutThrowArmed = false;
    sTinKoopa = nullptr;
    sBossGesso = nullptr;
    sBossEel = nullptr;
    sPetey = nullptr;
    sGatekeeperHits = 0;
    sHanachanHits = sTinKoopaHits = sMirrorsCleared = 0;
    for (int i = 0; i < 3; ++i) sClearedMirrors[i] = nullptr;
    sPeteyHits = 0;
    sBossGessoHits = 0;
    sBossGessoHealth = 0;
    sPeteyHealth = 0;
    sBossTelesaHits = 0;
    sFireWanwanDeaths = 0;
    sEelCleanedCount = 0;
    sPeteyWakeSeen = false;
    sTamaNokoWakeSeen = false;
    sTamaNokoKillSeen = false;
    sBossWanwanWaterSeen = false;
    sCannonKilledSeen = false;
    sEelActivatedSeen = false;
    sTinKoopaFourthSeen = false;
    sBossGessoHealthValid = false;
    sPeteyHealthValid = false;
    sMantaPinkSeen = false;
    sNoki2FirstWallkick = false;
    sGenericTalkCount = 0;
    sFireWanwanManagerKills = 0;
    sFireWanwanManagerValid = false;
    sBathtub = nullptr;
    sBowserGripsDead = 0;
    sBowserGripsValid = false;
    for (int i = 0; i < 8; ++i)
        sCleanedEelTeeth[i] = nullptr;
    for (int i = 0; i < 3; ++i)
        sDeadFireWanwans[i] = nullptr;
}

bool stageIdentityValid() {
    return sStageDirector && gpMarDirector == sStageDirector &&
           gpApplication.mContext == TApplication::CONTEXT_DIRECT_STAGE &&
           sStageDirector->_260 != 0 && !sAttemptInvalid &&
           gQFTTimer.attemptSerial() == sAttemptSerial &&
           !Ghost::observerStatsSuppressed();
}

u16 findActiveRoute() {
    for (u16 route = 0; route < SplitStats::ROUTE_COUNT; ++route)
        if (SplitStats::routeActive(route)) return route;
    return SplitStats::ROUTE_INVALID;
}

u8 routeParentEpisode(u16 route, u8 area, u8 fallback) {
    const bool selectable = route >= SplitStats::ROUTE_BIANCO_3_FULL_REDS ||
        route == SplitStats::ROUTE_GELATO_HIDDEN ||
        route == SplitStats::ROUTE_NOKI_HIDDEN ||
        route == SplitStats::ROUTE_PIANTA_HIDDEN;
    if (selectable && area >= 2 && area <= 9 && area != 7) {
        const int selected = ILing::activeParentEpisode(area);
        if (selected >= 0 && selected < 8) return static_cast<u8>(selected);
    }
    if (selectable && area == 0x0D) {
        const int selected = ILing::activeParentEpisode(5);
        // Pinna park uses its own retail scenario table.
        const u8 parkEpisodes[8] = {0, 0, 1, 0, 2, 3, 4, 5};
        if (selected >= 0 && selected < 8)
            return parkEpisodes[selected];
    }
    if (selectable && (area == 7 || area == 0x0E)) {
        const int selected = ILing::activeParentEpisode(6);
        const u8 hotelEpisodes[8] = {0, 0, 1, 2, 2, 0, 3, 4};
        if (selected >= 0 && selected < 8)
            return area == 7 ? hotelEpisodes[selected] : selected == 4;
    }
    return fallback;
}

bool routeScene(u16 route, u8 area, u8 episode) {
    return stageIdentityValid() && sActiveRoute == route &&
           sStageDirector->mAreaID == area &&
           sStageDirector->mEpisodeID == routeParentEpisode(route, area, episode);
}

bool hookScene(u16 route, u8 area, u8 episode) {
    return sRetailDirectOpen && routeScene(route, area, episode);
}

bool publishEventAt(u16 route, u8 event, s32 qf) {
    if (route != sActiveRoute) return false;
    return SplitStats::onRouteEvent(route, event, qf);
}

bool publishEvent(u16 route, u8 event) {
    s32 qf;
    if (gQFTTimer.currentQf(&qf))
        return publishEventAt(route, event, qf);
    return false;
}

struct RedDesc {
    u16 route;
    u8 area, episode, first, count;
    u8 coins[4];
};
const RedDesc kRedRoutes[] = {
    {SplitStats::ROUTE_BIANCO_4, 0x02, 3, 0, 3, {1, 5, 8, 0}},
    {SplitStats::ROUTE_RICCO_6, 0x03, 5, 1, 2, {4, 8, 0, 0}},
    {SplitStats::ROUTE_PINNA_3, 0x0D, 1, 0, 3, {4, 6, 7, 0}},
    {SplitStats::ROUTE_NOKI_3, 0x2C, 0, 0, 2, {4, 8, 0, 0}},
    {SplitStats::ROUTE_BIANCO_3_REDS, 0x2F, 0, 0, 3, {2, 5, 8, 0}},
    {SplitStats::ROUTE_BIANCO_6_REDS, 0x2E, 0, 0, 3, {3, 6, 8, 0}},
    {SplitStats::ROUTE_BIANCO_8, 0x02, 7, 0, 3, {2, 5, 8, 0}},
    {SplitStats::ROUTE_RICCO_4_REDS, 0x30, 0, 0, 4, {1, 4, 6, 8}},
    {SplitStats::ROUTE_GELATO_1_REDS, 0x20, 0, 0, 3, {3, 5, 8, 0}},
    {SplitStats::ROUTE_GELATO_4, 0x21, 0, 2, 3, {2, 7, 8, 0}},
    {SplitStats::ROUTE_GELATO_4_INSIDE, 0x21, 0, 0, 3, {2, 7, 8, 0}},
    {SplitStats::ROUTE_GELATO_6, 0x04, 5, 0, 3, {1, 4, 8, 0}},
    {SplitStats::ROUTE_PINNA_2_REDS, 0x32, 0, 0, 3, {2, 5, 7, 0}},
    {SplitStats::ROUTE_PINNA_6_REDS, 0x29, 0, 0, 4, {2, 3, 6, 8}},
    {SplitStats::ROUTE_SIRENA_2_REDS, 0x33, 0, 1, 4, {3, 5, 6, 8}},
    {SplitStats::ROUTE_SIRENA_4_REDS, 0x28, 0, 0, 3, {3, 6, 8, 0}},
    {SplitStats::ROUTE_SIRENA_8, 0x07, 4, 0, 4, {2, 3, 6, 8}},
    {SplitStats::ROUTE_NOKI_6_REDS, 0x1F, 0, 1, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_NOKI_8, 0x2C, 0, 1, 1, {8, 0, 0, 0}},
    {SplitStats::ROUTE_PIANTA_5_REDS, 0x2A, 0, 0, 4, {2, 3, 6, 8}},
    {SplitStats::ROUTE_PIANTA_8, 0x08, 7, 0, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_AIRSTRIP_REDS, 0x14, 0, 0, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_PACHINKO, 0x16, 0, 0, 3, {4, 6, 8, 0}},
    {SplitStats::ROUTE_LILY_PAD, 0x18, 0, 0, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_GRASS_SECRET, 0x17, 0, 0, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_BIANCO_3_FULL_REDS, 0x2F, 0, 1, 3, {2, 5, 8, 0}},
    {SplitStats::ROUTE_BIANCO_6_FULL_REDS, 0x2E, 0, 1, 3, {3, 6, 8, 0}},
    {SplitStats::ROUTE_RICCO_4_FULL_REDS, 0x30, 0, 2, 4, {1, 4, 6, 8}},
    {SplitStats::ROUTE_GELATO_1_FULL_REDS, 0x20, 0, 2, 3, {3, 5, 8, 0}},
    {SplitStats::ROUTE_PINNA_2_FULL_REDS, 0x32, 0, 1, 3, {2, 5, 7, 0}},
    {SplitStats::ROUTE_PINNA_6_FULL_REDS, 0x29, 0, 2, 4, {2, 3, 6, 8}},
    {SplitStats::ROUTE_SIRENA_2_FULL_REDS, 0x33, 0, 3, 4, {3, 5, 6, 8}},
    {SplitStats::ROUTE_SIRENA_4_FULL_REDS, 0x28, 0, 3, 3, {3, 6, 8, 0}},
    {SplitStats::ROUTE_NOKI_6_FULL_REDS, 0x1F, 0, 3, 4, {2, 4, 6, 8}},
    {SplitStats::ROUTE_PIANTA_5_FULL_REDS, 0x2A, 0, 2, 4, {2, 3, 6, 8}},
};

void noteRedSwitch() {
    if (!TFlagManager::smInstance ||
        !TFlagManager::smInstance->Type5Flag.mRedCoinSwitchPressed) return;
    if (routeScene(SplitStats::ROUTE_SIRENA_2_REDS, 0x33, 0) ||
        routeScene(SplitStats::ROUTE_NOKI_6_REDS, 0x1F, 0))
        publishEvent(sActiveRoute, 0);
    else if (routeScene(SplitStats::ROUTE_SIRENA_2_FULL_REDS, 0x33, 0) ||
             routeScene(SplitStats::ROUTE_NOKI_6_FULL_REDS, 0x1F, 0))
        publishEvent(sActiveRoute, 2);
}

void noteRedCoin() {
    if (!sRetailDirectOpen || !stageIdentityValid() ||
        !TFlagManager::smInstance) return;
    noteRedSwitch();
    const s32 count = TFlagManager::smInstance->Type6Flag.mRedCoinCount;
    const s32 before = sLastRedCoinCount;
    if (count <= before) return;
    sLastRedCoinCount = count;
    for (u32 r = 0; r < sizeof(kRedRoutes) / sizeof(kRedRoutes[0]); ++r) {
        const RedDesc &desc = kRedRoutes[r];
        if (!routeScene(desc.route, desc.area, desc.episode)) continue;
        for (u8 i = 0; i < desc.count; ++i)
            if (before < desc.coins[i] && count >= desc.coins[i])
                publishEvent(sActiveRoute, desc.first + i);
        return;
    }
}

int recoveredPiantaIndex(TBaseNPC *npc) {
    for (int i = 0; i < sRecoveredPiantaCount; ++i)
        if (sRecoveredPiantas[i] == npc) return i;
    return -1;
}

void notePiantaRecovered(TBaseNPC *npc) {
    if (!hookScene(SplitStats::ROUTE_PIANTA_6, 8, 5) || !npc ||
        sRecoveredPiantaCount >= kPiantaCount ||
        recoveredPiantaIndex(npc) >= 0) return;
    sRecoveredPiantas[sRecoveredPiantaCount++] = npc;
}

void notePiantaHappy(TBaseNPC *npc) {
    if (!hookScene(SplitStats::ROUTE_PIANTA_6, 8, 5) || !npc) return;
    const int index = recoveredPiantaIndex(npc);
    if (index < 0) return;
    sRecoveredPiantas[index] = nullptr;
    ++sCleanedPiantaCount;
    if (sCleanedPiantaCount == 2) publishEvent(sActiveRoute, 0);
    else if (sCleanedPiantaCount == 5) publishEvent(sActiveRoute, 1);
    else if (sCleanedPiantaCount == 7) publishEvent(sActiveRoute, 2);
    else if (sCleanedPiantaCount == 10) publishEvent(sActiveRoute, 3);
}

TEnemyManager *findManager(u32 managerVtable) {
    if (!gpConductor) return nullptr;
    for (auto it = gpConductor->_10.begin(); it != gpConductor->_10.end(); ++it) {
        TEnemyManager *manager = reinterpret_cast<TEnemyManager *>(*it);
        if (manager && objectVtable(manager) == managerVtable) return manager;
    }
    return nullptr;
}

void *findManagedActor(u32 managerVtable, u32 actorVtable) {
    TEnemyManager *manager = findManager(managerVtable);
    if (!manager) return nullptr;
    for (u32 i = 0; i < manager->mObjCount; ++i) {
        void *actor = manager->mObjAry[i];
        if (objectVtable(actor) == actorVtable) return actor;
    }
    return nullptr;
}

bool isShadowRoute(u16 route) {
    return route == SplitStats::ROUTE_DELFINO_SHADOW_MARIO ||
           route == SplitStats::ROUTE_BIANCO_7 ||
           route == SplitStats::ROUTE_GELATO_7 ||
           route == SplitStats::ROUTE_PIANTA_7 ||
           route == SplitStats::ROUTE_PINNA_7 ||
           route == SplitStats::ROUTE_SIRENA_7 ||
           route == SplitStats::ROUTE_NOKI_7 ||
           route == SplitStats::ROUTE_RICCO_7;
}

u8 shadowEvent(u16 route) {
    return route == SplitStats::ROUTE_SIRENA_7 ? 1 : 0;
}

const CarryDesc *carryForRoute(u16 route) {
    for (u32 i = 0; i < sizeof(kCarryRoutes) / sizeof(kCarryRoutes[0]); ++i)
        if (kCarryRoutes[i].route == route) return &kCarryRoutes[i];
    return nullptr;
}

bool publishTransition(u16 route, u8 event, u8 target) {
    s32 qf;
    u16 capturedTarget;
    if (!gQFTTimer.transitionEntryQf(&qf, &capturedTarget) ||
        capturedTarget != target ||
        gpApplication.mNextScene.mAreaID != target ||
        gpApplication.mNextScene.mEpisodeID != 0) return false;
    if (!publishEventAt(route, event, qf)) return false;
    if (carryForRoute(route)) sArmedCarryRoute = route;
    return true;
}

bool hundredCourseTransition(u16 route, u8 before, u8 after) {
    if (before == after) return false;
    if (route == SplitStats::ROUTE_PINNA_100)
        return (before == 5 || before == 0x0D) &&
               (after == 5 || after == 0x0D);
    if (route == SplitStats::ROUTE_SIRENA_100)
        return (before == 6 || before == 7 || before == 0x0E) &&
               (after == 6 || after == 7 || after == 0x0E);
    return false;
}

void armCarryTransition() {
    if (sActiveRoute == SplitStats::ROUTE_RICCO_1 &&
        routeScene(sActiveRoute, 3, 0) &&
        gpApplication.mNextScene.mAreaID == 0x3B &&
        gpApplication.mNextScene.mEpisodeID == 0) {
        sArmedCarryRoute = sActiveRoute;
        return;
    }
    if (sActiveRoute == SplitStats::ROUTE_PINNA_1 &&
        routeScene(sActiveRoute, 0x0D, 6) &&
        gpApplication.mNextScene.mAreaID == 0x3A &&
        gpApplication.mNextScene.mEpisodeID == 1) {
        sArmedCarryRoute = sActiveRoute;
        return;
    }
    const volatile u16 *capturedTarget =
        reinterpret_cast<volatile u16 *>(SUSAMUNE_ADDR_QFT_TRANSITION_TARGET);
    if (*capturedTarget == 0xffff) return;
    if (*capturedTarget == gpApplication.mNextScene.mAreaID &&
        hundredCourseTransition(sActiveRoute, sStageDirector->mAreaID,
                                gpApplication.mNextScene.mAreaID)) {
        sArmedCarryRoute = sActiveRoute;
        return;
    }
    for (u32 i = 0; i < sizeof(kCarryRoutes) / sizeof(kCarryRoutes[0]); ++i) {
        const CarryDesc &desc = kCarryRoutes[i];
        if (desc.route == sActiveRoute &&
            routeScene(desc.route, desc.parentArea, desc.parentEpisode) &&
            gpApplication.mNextScene.mAreaID == desc.childArea &&
            gpApplication.mNextScene.mEpisodeID ==
                routeParentEpisode(desc.route, desc.childArea, desc.childEpisode)) {
            sArmedCarryRoute = desc.route;
            return;
        }
    }
}

bool isSpinStatus(u32 status) {
    return status == kMarioSpinLeftStatus || status == kMarioSpinRightStatus;
}

void noteMarioStatus(TMario *mario, u32 status) {
    if (mario != gpMarioAddress || !sRetailDirectOpen ||
        !stageIdentityValid()) return;
    if (status == kMarioThrowObjectStatus &&
        routeScene(SplitStats::ROUTE_GELATO_8_GBS, 4, 0) && sCoconut &&
        (mario->mHeldObject == sCoconut || sPreHeldObject == sCoconut))
        sCoconutThrowArmed = true;
    if (sStageDirector->mCurState != TMarDirector::STATE_NORMAL) return;

    switch (sActiveRoute) {
    case SplitStats::ROUTE_NOKI_HIDDEN: {
        const TBGCheckData *floor = mario->mFloorTriangle;
        if (routeScene(sActiveRoute, 9, 6) && status == kMarioBounceStatus &&
            floor && !floor->mOwner && floor->mType == 7 &&
            floor->mValue == 30300)
            publishEvent(sActiveRoute, 0);
        break;
    }
    case SplitStats::ROUTE_RICCO_1:
        if (routeScene(sActiveRoute, 3, 0) && status == kMarioDiveStatus &&
            mario->mTranslation.x > 0.0f &&
            mario->mTranslation.y > 1500.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_RICCO_2:
    case SplitStats::ROUTE_RICCO_2_RACE: {
        if (!routeScene(sActiveRoute, 0x1E, 0) ||
            status != kMarioDiveStatus) break;
        const u8 first = sActiveRoute == SplitStats::ROUTE_RICCO_2 ? 1 : 0;
        if (mario->mTranslation.y > 1250.0f &&
            publishEvent(sActiveRoute, first)) break;
        if (mario->mTranslation.x < -3000.0f &&
            publishEvent(sActiveRoute, first + 1)) break;
        if (mario->mTranslation.z > 6500.0f)
            publishEvent(sActiveRoute, first + 2);
        break;
    }
    case SplitStats::ROUTE_RICCO_3:
        if (!routeScene(sActiveRoute, 3, 2)) break;
        if (isSpinStatus(status) && mario->mTranslation.y > 600.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_RICCO_4:
    case SplitStats::ROUTE_RICCO_4_FULL_REDS:
    case SplitStats::ROUTE_RICCO_4_SECRET:
        if (!isSpinStatus(status)) break;
        if (routeScene(sActiveRoute, 3, 3) &&
            mario->mTranslation.z > 0.0f &&
            mario->mTranslation.z < 400.0f &&
            mario->mTranslation.y >= 1550.0f) {
            publishEvent(sActiveRoute, 0);
        } else if (sActiveRoute != SplitStats::ROUTE_RICCO_4_FULL_REDS &&
                   routeScene(sActiveRoute, 0x30, 0) &&
                   mario->mTranslation.x > 10000.0f) {
            publishEvent(sActiveRoute,
                sActiveRoute == SplitStats::ROUTE_RICCO_4 ? 2 : 0);
        }
        break;
    case SplitStats::ROUTE_RICCO_5:
        if (!routeScene(sActiveRoute, 3, 4)) break;
        if (isSpinStatus(status) && mario->mTranslation.y > 2000.0f)
            publishEvent(sActiveRoute, 0);
        else if (status == kMarioBounceStatus &&
                 mario->mTranslation.x > 6000.0f)
            publishEvent(sActiveRoute, 1);
        break;
    case SplitStats::ROUTE_RICCO_6:
        if (routeScene(sActiveRoute, 3, 5) && status == kMarioSurfStatus)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_BIANCO_1:
    case SplitStats::ROUTE_BIANCO_2:
        if (routeScene(sActiveRoute, 2, 0) &&
            status == kMarioRolloutStatus &&
            mario->mTranslation.y >= 3200.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_BIANCO_3_FULL:
        if (routeScene(sActiveRoute, 2, 2) &&
            status == kMarioWallKickStatus &&
            mario->mTranslation.x > 13000.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_BIANCO_6_FULL:
    case SplitStats::ROUTE_BIANCO_6_SECRET: {
        if (!routeScene(sActiveRoute, 0x2E, 0)) break;
        const bool full = sActiveRoute == SplitStats::ROUTE_BIANCO_6_FULL;
        const u8 first = full ? 2 : 0;
        if (status == kMarioLedgeGrabStatus &&
            mario->mTranslation.z < 5000.0f)
            publishEvent(sActiveRoute, first);
        else if (status == kMarioRolloutStatus &&
                 mario->mTranslation.y > 15000.0f)
            publishEvent(sActiveRoute, first + 1);
        break;
    }
    case SplitStats::ROUTE_PIANTA_3:
        if (routeScene(sActiveRoute, 8, 2) &&
            status == kMarioLedgeGrabStatus &&
            mario->mTranslation.y > 3000.0f)
            publishEvent(sActiveRoute, 1);
        break;
    case SplitStats::ROUTE_PIANTA_5_FULL:
    case SplitStats::ROUTE_PIANTA_5_FULL_REDS:
        if (routeScene(sActiveRoute, 8, 4) && isSpinStatus(status) &&
            mario->mTranslation.y < -3000.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_HONEY_SKIP:
        if (routeScene(sActiveRoute, 1, 7) && isSpinStatus(status) &&
            mario->mTranslation.y < 2000.0f)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_NOKI_1:
        if (!routeScene(sActiveRoute, 9, 0)) break;
        if (status == kMarioWallKickStatus &&
            mario->mTranslation.y > 3500.0f)
            publishEvent(sActiveRoute, 0);
        else if (status == kMarioLedgeGrabStatus &&
                 mario->mTranslation.y > 8000.0f)
            publishEvent(sActiveRoute, 2);
        break;
    case SplitStats::ROUTE_NOKI_2:
        if (!routeScene(sActiveRoute, 9, 1)) break;
        if (status == kMarioWallKickStatus) {
            if (!sNoki2FirstWallkick && mario->mTranslation.y > 3000.0f) {
                if (publishEvent(sActiveRoute, 0))
                    sNoki2FirstWallkick = true;
            } else if (sNoki2FirstWallkick &&
                       mario->mTranslation.y > 7000.0f) {
                publishEvent(sActiveRoute, 1);
            }
        }
        break;
    case SplitStats::ROUTE_NOKI_6_FULL:
    case SplitStats::ROUTE_NOKI_6_FULL_REDS:
    case SplitStats::ROUTE_NOKI_6_SECRET: {
        if (sActiveRoute == SplitStats::ROUTE_NOKI_6_FULL_REDS ||
            !routeScene(sActiveRoute, 0x1F, 0)) break;
        const bool full = sActiveRoute == SplitStats::ROUTE_NOKI_6_FULL;
        const u8 first = full ? 2 : 0;
        if (status == kMarioRolloutStatus &&
            mario->mTranslation.y > 9000.0f)
            publishEvent(sActiveRoute, first);
        else if (status == kMarioWallKickStatus &&
                 mario->mTranslation.y > 10000.0f)
            publishEvent(sActiveRoute, first + 1);
        break;
    }
    }
}

bool actorAlreadyCounted(TLiveActor *actor) {
    for (int i = 0; i < sFireWanwanDeaths; ++i)
        if (sDeadFireWanwans[i] == actor) return true;
    return false;
}

bool enteredNerve(u32 before, s32 beforeTimer, u32 after, u32 target) {
    return (before != target && after == target) ||
           (before == target && beforeTimer == 0);
}

void noteGatekeeper(u32, u32, u32, u8 healthBefore, u8 healthAfter) {
    if (healthAfter >= healthBefore) return;
    const u8 first = sActiveRoute == SplitStats::ROUTE_AIRSTRIP_1 ||
                     sActiveRoute == SplitStats::ROUTE_BIANCO_1 ? 1 : 0;
    for (u8 i = healthAfter; i < healthBefore && sGatekeeperHits < 3; ++i)
        publishEvent(sActiveRoute, first + sGatekeeperHits++);
}

void notePeteyDamage(u8 healthBefore, u8 healthAfter) {
    if (healthAfter >= healthBefore) return;
    const u8 hits = healthBefore - healthAfter;
    for (u8 i = 0; i < hits; ++i) {
        ++sPeteyHits;
        if (sActiveRoute == SplitStats::ROUTE_BIANCO_2)
            publishEvent(sActiveRoute, sPeteyHits + 1);
        else if (sActiveRoute == SplitStats::ROUTE_BIANCO_5)
            publishEvent(sActiveRoute, sPeteyHits);
    }
}

void notePetey(u32 nerveBefore, s32 nerveTimerBefore, u32 nerveAfter) {
    if (!sPeteyWakeSeen && enteredNerve(nerveBefore, nerveTimerBefore,
                                        nerveAfter,
                                        kPeteyBreakSleepVtable)) {
        sPeteyWakeSeen = true;
        if (routeScene(SplitStats::ROUTE_BIANCO_5, 2, 4))
            publishEvent(sActiveRoute, 0);
    }
}

void noteBossGesso(u8 before, u8 after) {
    if (after >= before) return;
    sBossGessoHits += before - after;
    if ((sActiveRoute == SplitStats::ROUTE_RICCO_1 ||
         sActiveRoute == SplitStats::ROUTE_RICCO_5) &&
        sBossGessoHits >= 2)
        publishEvent(sActiveRoute, 2);
}

void noteBossTelesa(u8 before, u8 after) {
    if (after >= before) return;
    const u8 hits = before - after;
    for (u8 i = 0; i < hits; ++i) {
        ++sBossTelesaHits;
        if (sActiveRoute == SplitStats::ROUTE_SIRENA_5)
            publishEvent(sActiveRoute, 1 + sBossTelesaHits);
    }
}

bool healthActor(u32 vtable) {
    return vtable == kGatekeeperVtable || vtable == kBossTelesaVtable;
}

bool routeUsesSpine(u16 route) {
    switch (route) {
    case SplitStats::ROUTE_RICCO_1:
    case SplitStats::ROUTE_RICCO_5:
    case SplitStats::ROUTE_RICCO_7:
    case SplitStats::ROUTE_AIRSTRIP_1:
    case SplitStats::ROUTE_BIANCO_1:
    case SplitStats::ROUTE_BIANCO_PLANT:
    case SplitStats::ROUTE_DELFINO_SHADOW_MARIO:
    case SplitStats::ROUTE_TRAVEL_SKIP:
    case SplitStats::ROUTE_BIANCO_5:
    case SplitStats::ROUTE_BIANCO_7:
    case SplitStats::ROUTE_GELATO_PLANT:
    case SplitStats::ROUTE_GELATO_7:
    case SplitStats::ROUTE_PIANTA_1:
    case SplitStats::ROUTE_PIANTA_4:
    case SplitStats::ROUTE_PIANTA_7:
    case SplitStats::ROUTE_PINNA_1:
    case SplitStats::ROUTE_PINNA_4:
    case SplitStats::ROUTE_PINNA_7:
    case SplitStats::ROUTE_SIRENA_5:
    case SplitStats::ROUTE_SIRENA_7:
    case SplitStats::ROUTE_NOKI_1:
    case SplitStats::ROUTE_NOKI_4_FULL:
    case SplitStats::ROUTE_NOKI_4_EEL:
    case SplitStats::ROUTE_NOKI_7:
        return true;
    default:
        return false;
    }
}

bool spineActorRelevant(u16 route, u32 vtable) {
    switch (route) {
    case SplitStats::ROUTE_RICCO_1:
    case SplitStats::ROUTE_RICCO_5:
        return vtable == kBossGessoVtable;
    case SplitStats::ROUTE_AIRSTRIP_1:
    case SplitStats::ROUTE_BIANCO_1:
    case SplitStats::ROUTE_BIANCO_PLANT:
    case SplitStats::ROUTE_TRAVEL_SKIP:
    case SplitStats::ROUTE_GELATO_PLANT:
        return vtable == kGatekeeperVtable;
    case SplitStats::ROUTE_BIANCO_5:
        return vtable == kPeteyVtable;
    case SplitStats::ROUTE_PIANTA_1:
        return vtable == kFireWanwanVtable;
    case SplitStats::ROUTE_PIANTA_4:
        return vtable == kBossWanwanVtable;
    case SplitStats::ROUTE_PINNA_1:
        return vtable == kTinKoopaVtable;
    case SplitStats::ROUTE_PINNA_4:
        return vtable == kTamaNokoVtable;
    case SplitStats::ROUTE_SIRENA_5:
        return vtable == kBossTelesaVtable;
    case SplitStats::ROUTE_NOKI_1:
        return vtable == kCannonVtable;
    case SplitStats::ROUTE_NOKI_4_FULL:
    case SplitStats::ROUTE_NOKI_4_EEL:
        return vtable == kBossEelVtable;
    default:
        return false;
    }
}

void noteSpineUpdate(TLiveActor *actor, u32 vtable, u32 nerveBefore,
                     u32 previousBefore, s32 nerveTimerBefore, u32 nerveAfter,
                     u8 healthBefore, u8 healthAfter, bool deadBefore,
                     bool deadAfter) {
    if (!actor) return;

    TSpineEnemy *enemy = reinterpret_cast<TSpineEnemy *>(actor);
    if (vtable == kGatekeeperVtable) {
        noteGatekeeper(nerveBefore, previousBefore, nerveAfter,
                       healthBefore, healthAfter);
    } else if (vtable == kBossGessoVtable) {
        sBossGesso = enemy;
    } else if (vtable == kPeteyVtable) {
        notePetey(nerveBefore, nerveTimerBefore, nerveAfter);

    } else if (vtable == kFireWanwanVtable) {
        if (sActiveRoute == SplitStats::ROUTE_PIANTA_1 &&
            !actorAlreadyCounted(actor) &&
            enteredNerve(nerveBefore, nerveTimerBefore, nerveAfter,
                         kFireWanwanDieVtable) &&
            sFireWanwanDeaths < 3) {
            sDeadFireWanwans[sFireWanwanDeaths] = actor;
            publishEvent(sActiveRoute, sFireWanwanDeaths++);
        }
    } else if (vtable == kBossWanwanVtable) {
        if (!sBossWanwanWaterSeen &&
            enteredNerve(nerveBefore, nerveTimerBefore, nerveAfter,
                         kBossWanwanDieVtable)) {
            sBossWanwanWaterSeen = true;
            if (sActiveRoute == SplitStats::ROUTE_PIANTA_4)
                publishEvent(sActiveRoute, 1);
        }
    } else if (vtable == kTamaNokoVtable) {
        if (!sTamaNokoWakeSeen &&
            enteredNerve(nerveBefore, nerveTimerBefore, nerveAfter,
                         kTamaNokoHitWaterVtable)) {
            sTamaNokoWakeSeen = true;
            if (sActiveRoute == SplitStats::ROUTE_PINNA_4)
                publishEvent(sActiveRoute, 0);
        }
        if (!sTamaNokoKillSeen && !deadBefore && deadAfter) {
            sTamaNokoKillSeen = true;
            if (sActiveRoute == SplitStats::ROUTE_PINNA_4)
                publishEvent(sActiveRoute, 1);
        }
    } else if (vtable == kTinKoopaVtable) {
        sTinKoopa = enemy;
    } else if (vtable == kBossTelesaVtable) {
        noteBossTelesa(healthBefore, healthAfter);
    } else if (vtable == kCannonVtable) {
        if (!sCannonKilledSeen &&
            enteredNerve(nerveBefore, nerveTimerBefore, nerveAfter,
                         kCannonDamageDemoVtable)) {
            sCannonKilledSeen = true;
            if (sActiveRoute == SplitStats::ROUTE_NOKI_1)
                publishEvent(sActiveRoute, 3);
        }
    } else if (vtable == kBossEelVtable) {
        sBossEel = enemy;
        if (!sEelActivatedSeen && nerveBefore == kBossEelWaitAppearVtable &&
            nerveAfter != kBossEelWaitAppearVtable) {
            sEelActivatedSeen = true;
            if (sActiveRoute == SplitStats::ROUTE_NOKI_4_FULL)
                publishEvent(sActiveRoute, 1);
            else if (sActiveRoute == SplitStats::ROUTE_NOKI_4_EEL)
                publishEvent(sActiveRoute, 0);
        }
    }
}

bool isChainTail(const TTakeActor *actor) {
    const u32 vtable = objectVtable(actor);
    return vtable == kBWLeashVtable || vtable == kBWLeashNodeVtable ||
           vtable == kFireWanwanTailVtable || vtable == kBWPicketVtable;
}

void updateHeldObject() {
    if (!gpMarioAddress) return;
    TTakeActor *held = gpMarioAddress->mHeldObject;

    if (routeScene(SplitStats::ROUTE_GELATO_8_GBS, 4, 0)) {
        if (held && held != sPreHeldObject &&
            held->mObjectID == TResetFruit::COCONUT) {
            sCoconut = reinterpret_cast<TResetFruit *>(held);
            publishEvent(sActiveRoute, 0);
        } else if (sCoconut && sPreHeldObject == sCoconut &&
                   held != sCoconut) {
            if (sCoconutThrowArmed &&
                sCoconut->mTranslation.z > 10000.0f) {
                publishEvent(sActiveRoute, 1);
            }
            sCoconutThrowArmed = false;
        }
    } else if (routeScene(SplitStats::ROUTE_SIRENA_3, 7, 1)) {
        if (held && held != sPreHeldObject &&
            held->mObjectID >= TResetFruit::COCONUT &&
            held->mObjectID <= TResetFruit::BANANA)
            publishEvent(sActiveRoute, 1);
    } else if (routeScene(SplitStats::ROUTE_PIANTA_4, 8, 3)) {
        if (held && held != sPreHeldObject && isChainTail(held))
            publishEvent(sActiveRoute, 0);
    } else if (routeScene(SplitStats::ROUTE_NOKI_2, 9, 1)) {
        if (held && held != sPreHeldObject)
            publishEvent(sActiveRoute, 2);
    }
}

void noteTalk(TBaseNPC *npc) {
    if (!npc || !sRetailDirectOpen || !stageIdentityValid()) return;
    const u32 talkActor = objectVtable(npc->mDummyConnectActor);
    if (isShadowRoute(sActiveRoute) &&
        (talkActor == kEmarioVtable || talkActor == kEnemyMarioVtable)) {
        publishEvent(sActiveRoute, shadowEvent(sActiveRoute));
        return;
    }
    switch (sActiveRoute) {
    case SplitStats::ROUTE_GELATO_5:
        if (routeScene(sActiveRoute, 4, 4) && talkActor == kEnemyMarioVtable)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_PINNA_8:
        // Retail scripts name the ride attendant and park director separately.
        if (routeScene(sActiveRoute, 0x0D, 5) && npc->mKeyName &&
            strcmp(npc->mKeyName, "\x8c\x57\x88\xf5\x83\x7d\x81\x5b\x83\x8c") == 0)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_PIANTA_2:
        if (routeScene(sActiveRoute, 8, 1)) publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_PIANTA_5_FULL:
    case SplitStats::ROUTE_PIANTA_5_SECRET: {
        if (!routeScene(sActiveRoute, 0x2A, 0)) break;
        const u8 first = sActiveRoute == SplitStats::ROUTE_PIANTA_5_FULL ? 2 : 0;
        bool matches = false;
        if (sGenericTalkCount == 0)
            matches = npc->mTranslation.x < -2000.0f;
        else if (sGenericTalkCount == 1)
            matches = npc->mTranslation.x >= 2500.0f;
        else if (sGenericTalkCount == 2)
            matches = npc->mTranslation.y > 6000.0f;
        if (matches && publishEvent(sActiveRoute, first + sGenericTalkCount))
            ++sGenericTalkCount;
        break;
    }
    case SplitStats::ROUTE_PINNA_1:
        if (routeScene(sActiveRoute, 0x0D, 6) && npc->mKeyName &&
            strcmp(npc->mKeyName, "\x83\x7d\x81\x5b\x83\x8c\x82\x61") == 0)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_SIRENA_1:
        if (routeScene(sActiveRoute, 6, 0)) publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_SIRENA_2_FULL:
    case SplitStats::ROUTE_SIRENA_2_FULL_REDS:
        if (routeScene(sActiveRoute, 6, 1)) publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_SIRENA_3:
        if (routeScene(sActiveRoute, 6, 2)) publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_SIRENA_4_FULL:
    case SplitStats::ROUTE_SIRENA_4_FULL_REDS:
        if ((routeScene(sActiveRoute, 6, 3) ||
             routeScene(sActiveRoute, 7, 2)) && sGenericTalkCount < 2 &&
            publishEvent(sActiveRoute, sGenericTalkCount))
            ++sGenericTalkCount;
        break;
    case SplitStats::ROUTE_SIRENA_5:
        if ((routeScene(sActiveRoute, 6, 4) ||
             routeScene(sActiveRoute, 7, 2) ||
             routeScene(sActiveRoute, 0x0E, 1)) &&
            sGenericTalkCount < 2 &&
            publishEvent(sActiveRoute, sGenericTalkCount))
            ++sGenericTalkCount;
        break;
    case SplitStats::ROUTE_SIRENA_7:
        if (routeScene(sActiveRoute, 6, 6)) publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_NOKI_5:
        if (routeScene(sActiveRoute, 9, 4)) publishEvent(sActiveRoute, 0);
        break;
    }
}

void updateTransitions() {
    armCarryTransition();
    switch (sActiveRoute) {
    case SplitStats::ROUTE_BIANCO_3_FULL_REDS:
        if (routeScene(sActiveRoute, 2, 2)) publishTransition(sActiveRoute, 0, 0x2F);
        break;
    case SplitStats::ROUTE_BIANCO_6_FULL_REDS:
        if (routeScene(sActiveRoute, 2, 5)) publishTransition(sActiveRoute, 0, 0x2E);
        break;
    case SplitStats::ROUTE_GELATO_1_FULL:
    case SplitStats::ROUTE_GELATO_1_FULL_REDS:
        if (routeScene(sActiveRoute, 4, 0)) publishTransition(sActiveRoute, 1, 0x20);
        break;
    case SplitStats::ROUTE_GELATO_4:
        if (routeScene(sActiveRoute, 4, 3)) publishTransition(sActiveRoute, 1, 0x21);
        break;
    case SplitStats::ROUTE_PINNA_6_FULL:
    case SplitStats::ROUTE_PINNA_6_FULL_REDS:
        if (routeScene(sActiveRoute, 0x0D, 3)) publishTransition(sActiveRoute, 1, 0x29);
        break;
    case SplitStats::ROUTE_NOKI_8:
        if (routeScene(sActiveRoute, 9, 7)) publishTransition(sActiveRoute, 0, 0x2C);
        break;
    case SplitStats::ROUTE_RICCO_2:
        if (routeScene(sActiveRoute, 3, 1))
            publishTransition(sActiveRoute, 0, 0x1E);
        break;
    case SplitStats::ROUTE_RICCO_4:
    case SplitStats::ROUTE_RICCO_4_FULL_REDS:
        if (routeScene(sActiveRoute, 3, 3))
            publishTransition(sActiveRoute, 1, 0x30);
        break;
    case SplitStats::ROUTE_BIANCO_2:
        if (routeScene(sActiveRoute, 2, 0))
            publishTransition(sActiveRoute, 1, 0x37);
        break;
    case SplitStats::ROUTE_BIANCO_3_FULL:
        if (routeScene(sActiveRoute, 2, 2))
            publishTransition(sActiveRoute, 1, 0x2F);
        break;
    case SplitStats::ROUTE_BIANCO_6_FULL:
        if (routeScene(sActiveRoute, 2, 5))
            publishTransition(sActiveRoute, 1, 0x2E);
        break;
    case SplitStats::ROUTE_PIANTA_5_FULL:
    case SplitStats::ROUTE_PIANTA_5_FULL_REDS:
        if (routeScene(sActiveRoute, 8, 4))
            publishTransition(sActiveRoute, 1, 0x2A);
        break;
    case SplitStats::ROUTE_PINNA_2_FULL:
    case SplitStats::ROUTE_PINNA_2_FULL_REDS:
        if (routeScene(sActiveRoute, 5, 1))
            publishTransition(sActiveRoute, 0, 0x32);
        break;
    case SplitStats::ROUTE_PINNA_EYG:
        if (routeScene(sActiveRoute, 5, 2))
            publishTransition(sActiveRoute, 1, 0x29);
        break;
    case SplitStats::ROUTE_SIRENA_2_FULL:
    case SplitStats::ROUTE_SIRENA_2_FULL_REDS:
        if (routeScene(sActiveRoute, 7, 0))
            publishTransition(sActiveRoute, 1, 0x33);
        break;
    case SplitStats::ROUTE_SIRENA_4_FULL:
    case SplitStats::ROUTE_SIRENA_4_FULL_REDS:
        if (routeScene(sActiveRoute, 0x0E, 0))
            publishTransition(sActiveRoute, 2, 0x28);
        break;
    case SplitStats::ROUTE_NOKI_4_FULL:
        if (routeScene(sActiveRoute, 9, 3))
            publishTransition(sActiveRoute, 0, 0x39);
        break;
    case SplitStats::ROUTE_NOKI_6_FULL:
    case SplitStats::ROUTE_NOKI_6_FULL_REDS:
        if (routeScene(sActiveRoute, 9, 5))
            publishTransition(sActiveRoute, 1, 0x1F);
        break;
    case SplitStats::ROUTE_CORONA:
        if (routeScene(sActiveRoute, 0x34, 0))
            publishTransition(sActiveRoute, 2, 0x3C);
        break;
    }
}

bool crossedAbove(f32 before, f32 after, f32 boundary) {
    return before <= boundary && after > boundary;
}

bool crossedBelow(f32 before, f32 after, f32 boundary) {
    return before >= boundary && after < boundary;
}

void updatePositionAndDamage() {
    if (!sPreStateValid || !gpMarioAddress) return;
    const TVec3f &now = gpMarioAddress->mTranslation;
    switch (sActiveRoute) {
    case SplitStats::ROUTE_GELATO_1_FULL:
    case SplitStats::ROUTE_GELATO_1_SECRET: {
        if (!routeScene(sActiveRoute, 0x20, 0)) break;
        const u8 first = sActiveRoute == SplitStats::ROUTE_GELATO_1_FULL ? 2 : 0;
        if (crossedAbove(sPreMarioPosition.x, now.x, 6400.0f))
            publishEvent(sActiveRoute, first);
        if (crossedAbove(sPreMarioPosition.x, now.x, 13560.0f))
            publishEvent(sActiveRoute, first + 1);
        break;
    }
    case SplitStats::ROUTE_PIANTA_HIDDEN:
        if (routeScene(sActiveRoute, 8, 7) &&
            crossedAbove(sPreMarioPosition.y, now.y, 9700.0f))
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_BIANCO_3_FULL:
    case SplitStats::ROUTE_BIANCO_3_SECRET:
        if (routeScene(sActiveRoute, 0x2F, 0) &&
            crossedAbove(sPreMarioPosition.x, now.x, 0.0f))
            publishEvent(sActiveRoute,
                sActiveRoute == SplitStats::ROUTE_BIANCO_3_FULL ? 2 : 0);
        break;
    case SplitStats::ROUTE_BIANCO_6_FULL:
        if (routeScene(sActiveRoute, 2, 5) &&
            crossedBelow(sPreMarioPosition.z, now.z, -2000.0f))
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_PIANTA_3:
        if (routeScene(sActiveRoute, 8, 2) &&
            gpMarioAddress->mHealth < sPreMarioHealth)
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_PINNA_2_FULL:
    case SplitStats::ROUTE_PINNA_2_SECRET:
        if (routeScene(sActiveRoute, 0x32, 0) &&
            crossedAbove(sPreMarioPosition.z, now.z, 3500.0f))
            publishEvent(sActiveRoute,
                sActiveRoute == SplitStats::ROUTE_PINNA_2_FULL ? 1 : 0);
        break;
    case SplitStats::ROUTE_SIRENA_2_FULL:
    case SplitStats::ROUTE_SIRENA_2_SECRET: {
        if (!routeScene(sActiveRoute, 0x33, 0)) break;
        const bool before = sPreMarioPosition.x >= 1100.0f &&
                            sPreMarioPosition.y >= 6000.0f;
        const bool after = now.x >= 1100.0f && now.y >= 6000.0f;
        if (!before && after)
            publishEvent(sActiveRoute,
                sActiveRoute == SplitStats::ROUTE_SIRENA_2_FULL ? 2 : 0);
        break;
    }
    case SplitStats::ROUTE_SIRENA_4_FULL:
    case SplitStats::ROUTE_SIRENA_4_SECRET:
        if (routeScene(sActiveRoute, 0x28, 0) &&
            crossedBelow(sPreMarioPosition.z, now.z, 0.0f))
            publishEvent(sActiveRoute,
                sActiveRoute == SplitStats::ROUTE_SIRENA_4_FULL ? 3 : 0);
        break;
    case SplitStats::ROUTE_NOKI_1:
        if (routeScene(sActiveRoute, 9, 0) &&
            crossedAbove(sPreMarioPosition.y, now.y, 7500.0f))
            publishEvent(sActiveRoute, 1);
        break;
    case SplitStats::ROUTE_NOKI_6_FULL:
    case SplitStats::ROUTE_NOKI_6_FULL_REDS:
        if (routeScene(sActiveRoute, 9, 5) &&
            crossedAbove(sPreMarioPosition.y, now.y, 4000.0f))
            publishEvent(sActiveRoute, 0);
        break;
    case SplitStats::ROUTE_CORONA:
        if (routeScene(sActiveRoute, 0x34, 0) &&
            crossedBelow(sPreMarioPosition.z, now.z, -3500.0f))
            publishEvent(sActiveRoute, 0);
        break;
    }
}

void updateBossGesso() {
    if (!sBossGesso ||
        (!routeScene(SplitStats::ROUTE_RICCO_1, 3, 0) &&
         !routeScene(SplitStats::ROUTE_RICCO_1, 0x3B, 0) &&
         !routeScene(SplitStats::ROUTE_RICCO_5, 3, 4)))
        return;
    const u8 health = sBossGesso->mHealth;
    if (!sBossGessoHealthValid) {
        sBossGessoHealth = health;
        sBossGessoHealthValid = true;
        return;
    }
    noteBossGesso(sBossGessoHealth, health);
    sBossGessoHealth = health;
}

void updatePetey() {
    const bool b2 = routeScene(SplitStats::ROUTE_BIANCO_2, 0x37, 0);
    const bool b5 = routeScene(SplitStats::ROUTE_BIANCO_5, 2, 4);
    if (!b2 && !b5) return;
    if (!sPetey) {
        sPetey = reinterpret_cast<TSpineEnemy *>(
            findManagedActor(kPeteyManagerVtable, kPeteyVtable));
    }
    if (!sPetey) return;

    const u8 health = sPetey->mHealth;
    if (sPeteyHealthValid)
        notePeteyDamage(sPeteyHealth, health);
    sPeteyHealth = health;
    sPeteyHealthValid = true;
}

void updateManta() {
    if (sMantaPinkSeen ||
        !routeScene(SplitStats::ROUTE_SIRENA_1, 6, 0)) return;
    TEnemyManager *manager = findManager(kMantaManagerVtable);
    if (!manager) return;
    const u32 phase = *reinterpret_cast<const u32 *>(
        reinterpret_cast<const u8 *>(manager) + 0x8C);
    if (phase >= 2) {
        sMantaPinkSeen = true;
        publishEvent(sActiveRoute, 1);
    }
}

void updatePiantaOne() {
    if (!routeScene(SplitStats::ROUTE_PIANTA_1, 8, 0)) return;
    TEnemyManager *manager = findManager(kFireWanwanManagerVtable);
    if (!manager) return;
    const u8 killed = static_cast<u8>(*reinterpret_cast<const s32 *>(
        reinterpret_cast<const u8 *>(manager) + 0x6C));
    if (!sFireWanwanManagerValid) {
        sFireWanwanManagerKills = 0;
        sFireWanwanManagerValid = true;
    }
    while (sFireWanwanManagerKills < killed &&
           sFireWanwanManagerKills < 3) {
        publishEvent(sActiveRoute, sFireWanwanManagerKills);
        ++sFireWanwanManagerKills;
    }
}

void updatePollution() {
    if (!sPrePollutionValid || !gpPollution ||
        !routeScene(SplitStats::ROUTE_SIRENA_6, 6, 5)) return;
    const s32 degree = static_cast<s32>(gpPollution->getPollutionDegree());
    if (sPrePollutionDegree >= 18768 && degree < 18768)
        publishEvent(sActiveRoute, 0);
    if (sPrePollutionDegree >= 600 && degree < 600)
        publishEvent(sActiveRoute, 1);
}

void updateBowser() {
    if (!sBathtub ||
        !routeScene(SplitStats::ROUTE_BOWSER, 0x3C, 0)) return;
    const int count = reinterpret_cast<GetNumGripsDeadFn>(
        kGetNumGripsDead)(sBathtub);
    if (!sBowserGripsValid) {
        sBowserGripsDead = count;
        sBowserGripsValid = true;
        return;
    }
    while (sBowserGripsDead < count && sBowserGripsDead < 4) {
        publishEvent(sActiveRoute, static_cast<u8>(sBowserGripsDead));
        ++sBowserGripsDead;
    }
}

void updateCountEvents() {
    if (!TFlagManager::smInstance) return;
    noteRedSwitch();
    const u8 area = sStageDirector->mAreaID;
    const bool hundred =
        (sActiveRoute == SplitStats::ROUTE_BIANCO_100 && area == 2) ||
        (sActiveRoute == SplitStats::ROUTE_RICCO_100 && area == 3) ||
        (sActiveRoute == SplitStats::ROUTE_GELATO_100 && area == 4) ||
        (sActiveRoute == SplitStats::ROUTE_PINNA_100 && (area == 5 || area == 0x0D)) ||
        (sActiveRoute == SplitStats::ROUTE_SIRENA_100 && (area == 6 || area == 7 || area == 0x0E)) ||
        (sActiveRoute == SplitStats::ROUTE_NOKI_100 && area == 9) ||
        (sActiveRoute == SplitStats::ROUTE_PIANTA_100 && area == 8);
    if (hundred) {
        const u8 counts[] = {10, 25, 50, 75, 100};
        const s32 now = TFlagManager::smInstance->Type4Flag.mGoldCoinCount;
        for (u8 i = 0; i < sizeof(counts); ++i)
            if (sPreGoldCoins < counts[i] && now >= counts[i])
                publishEvent(sActiveRoute, i);
    }
    if (routeScene(SplitStats::ROUTE_PINNA_8, 0x0D, 5) ||
        routeScene(SplitStats::ROUTE_PINNA_8, 0x3A, 0)) {
        const u8 counts[] = {6, 11, 20};
        const s32 now = TFlagManager::smInstance->Type6Flag.mBJRBalloonCount;
        for (u8 i = 0; i < sizeof(counts); ++i)
            if (sPreBalloons < counts[i] && now >= counts[i])
                publishEvent(sActiveRoute, i + 1);
    }
}

void samplePreDirect() {
    sPreGoldCoins = TFlagManager::smInstance ?
        TFlagManager::smInstance->Type4Flag.mGoldCoinCount : 0;
    sPreBalloons = TFlagManager::smInstance ?
        TFlagManager::smInstance->Type6Flag.mBJRBalloonCount : 0;
    sPreHeldObject = gpMarioAddress ? gpMarioAddress->mHeldObject : nullptr;
    sPreStateValid = gpMarioAddress != nullptr;
    if (sPreStateValid) {
        sPreMarioPosition = gpMarioAddress->mTranslation;
        sPreMarioHealth = gpMarioAddress->mHealth;
    }
    sPrePollutionValid = gpPollution != nullptr;
    if (sPrePollutionValid)
        sPrePollutionDegree =
            static_cast<s32>(gpPollution->getPollutionDegree());
}

void initTrampoline(u32 *trampoline, u32 site) {
    trampoline[1] = branchWord(reinterpret_cast<u32>(&trampoline[1]),
                               site + 4);
    DCFlushRange(trampoline, 2 * sizeof(u32));
    ICInvalidateRange(trampoline, 2 * sizeof(u32));
}

void installEntryHook(u32 site, const void *wrapper, u32 *trampoline) {
    initTrampoline(trampoline, site);
    writeGameCode(site, branchWord(site, reinterpret_cast<u32>(wrapper)));
}

void installCapturedEntryHook(u32 site, const void *wrapper,
                              u32 *trampoline) {
    trampoline[0] = *reinterpret_cast<volatile const u32 *>(site);
    installEntryHook(site, wrapper, trampoline);
}

bool sceneMatches(const TGameSequence &scene, u8 area, u8 episode) {
    return scene.mAreaID == area && scene.mEpisodeID == episode;
}

}  // namespace

namespace SplitEvents {

void init() {
    if (sTrampolinesReady) return;
    sTrampolinesReady = true;

    installEntryHook(kStreamingMovie,
        reinterpret_cast<const void *>(&susamuneSplitStreamingMovie),
        sStreamingMovieTrampoline);
    installEntryHook(kItemAppear,
        reinterpret_cast<const void *>(&susamuneSplitItemAppear),
        sItemAppearTrampoline);
    installEntryHook(kSandCastle,
        reinterpret_cast<const void *>(&susamuneSplitSandCastle),
        sSandCastleTrampoline);
    installEntryHook(kMirrorMessage,
        reinterpret_cast<const void *>(&susamuneSplitMirrorMessage),
        sMirrorMessageTrampoline);
    installEntryHook(kHanachanDamage,
        reinterpret_cast<const void *>(&susamuneSplitHanachanDamage),
        sHanachanDamageTrampoline);
    installEntryHook(kTinKoopaHit,
        reinterpret_cast<const void *>(&susamuneSplitTinKoopaHit),
        sTinKoopaHitTrampoline);
    initTrampoline(sCoinRedTakenTrampoline, kCoinRedTaken);
    initTrampoline(sEmitHappyEffectTrampoline, kEmitHappyEffect);
    installEntryHook(kChangePlayerStatus,
                     reinterpret_cast<const void *>(
                         &susamuneSplitChangePlayerStatus),
                     sChangePlayerStatusTrampoline);
    installEntryHook(kSpineUpdate,
                     reinterpret_cast<const void *>(&susamuneSplitSpineUpdate),
                     sSpineUpdateTrampoline);
    installEntryHook(kStartDemo,
                     reinterpret_cast<const void *>(&susamuneSplitStartDemo),
                     sStartDemoTrampoline);
    installEntryHook(kOpenTalk,
                     reinterpret_cast<const void *>(&susamuneSplitOpenTalk),
                     sOpenTalkTrampoline);
    installEntryHook(kRailCheck,
                     reinterpret_cast<const void *>(&susamuneSplitRailCheck),
                     sRailCheckTrampoline);
    installEntryHook(kBathtubQuake,
                     reinterpret_cast<const void *>(&susamuneSplitBathtubQuake),
                     sBathtubQuakeTrampoline);
    installCapturedEntryHook(kPeteyHipDrop,
                     reinterpret_cast<const void *>(&susamuneSplitPeteyHipDrop),
                     sPeteyHipDropTrampoline);
    installCapturedEntryHook(kGessoTentacleDamage,
                     reinterpret_cast<const void *>(
                         &susamuneSplitGessoTentacleDamage),
                     sGessoTentacleDamageTrampoline);
    installCapturedEntryHook(kEelToothMessage,
                     reinterpret_cast<const void *>(
                         &susamuneSplitEelToothMessage),
                     sEelToothMessageTrampoline);
    installCapturedEntryHook(kFenceMessage,
                     reinterpret_cast<const void *>(&susamuneSplitFenceMessage),
                     sFenceMessageTrampoline);
    installCapturedEntryHook(kRevolvingFenceMessage,
                     reinterpret_cast<const void *>(
                         &susamuneSplitRevolvingFenceMessage),
                     sRevolvingFenceMessageTrampoline);
}

void beforeStageSetup() {
    sCarryAttempt = false;
    sBlockNextAttempt = false;
    const TGameSequence &previous = gpApplication.mPrevScene;
    const TGameSequence &current = gpApplication.mCurrentScene;
    const bool sameAttempt =
        gQFTTimer.attemptSerial() == sAttemptSerial && !sAttemptInvalid;

    if (sameAttempt && sArmedCarryRoute == sActiveRoute &&
        hundredCourseTransition(sActiveRoute, previous.mAreaID, current.mAreaID))
        sCarryAttempt = true;

    if (sameAttempt && sActiveRoute == SplitStats::ROUTE_AIRSTRIP_1 &&
        sArmedCarryRoute == SplitStats::ROUTE_AIRSTRIP_1 &&
        sceneMatches(current, 0, 1))
        sCarryAttempt = true;
    if (sameAttempt && sActiveRoute == SplitStats::ROUTE_PINNA_1 &&
        sArmedCarryRoute == SplitStats::ROUTE_PINNA_1) {
        sCarryAttempt = true;
    }
    if (sameAttempt && sActiveRoute == SplitStats::ROUTE_RICCO_1 &&
        sArmedCarryRoute == SplitStats::ROUTE_RICCO_1 &&
        sceneMatches(current, 0x3B, 0)) {
        sCarryAttempt = true;
    }
    if (sameAttempt && sActiveRoute == SplitStats::ROUTE_BIANCO_2 &&
        sArmedCarryRoute == SplitStats::ROUTE_BIANCO_2 &&
        sceneMatches(current, 0x37, 0)) {
        // The movie director overwrites mPrevScene before the boss setup.
        sCarryAttempt = true;
    }

    for (u32 i = 0; i < sizeof(kCarryRoutes) / sizeof(kCarryRoutes[0]); ++i) {
        const CarryDesc &desc = kCarryRoutes[i];
        const bool parentToChild =
            sceneMatches(previous, desc.parentArea,
                         routeParentEpisode(desc.route, desc.parentArea, desc.parentEpisode)) &&
            sceneMatches(current, desc.childArea,
                         routeParentEpisode(desc.route, desc.childArea, desc.childEpisode));
        if (parentToChild && sameAttempt && sArmedCarryRoute == desc.route)
            sCarryAttempt = true;

        const bool childReset =
            sceneMatches(previous, desc.childArea,
                         routeParentEpisode(desc.route, desc.childArea, desc.childEpisode)) &&
            sceneMatches(current, desc.childArea,
                         routeParentEpisode(desc.route, desc.childArea, desc.childEpisode));
        if (childReset && sameAttempt && sActiveRoute == desc.route)
            sBlockNextAttempt = true;
    }
    sArmedCarryRoute = SplitStats::ROUTE_INVALID;
    sRetailDirectOpen = false;
}

void onStageSetup(TMarDirector *director) {
    sStageDirector = director;
    const u8 carriedTalks = sCarryAttempt ? sGenericTalkCount : 0;
    clearAttemptState();
    sGenericTalkCount = carriedTalks;
    sAttemptInvalid = !sCarryAttempt;
    sCarryAttempt = false;
}

void beginFrame() {
    sRetailDirectOpen = false;
    const u32 serial = gQFTTimer.attemptSerial();
    if (serial != sAttemptSerial) {
        clearAttemptState();
        sAttemptSerial = serial;
        sAttemptInvalid = sBlockNextAttempt;
        sBlockNextAttempt = false;
    }
    sActiveRoute = findActiveRoute();
    sRetailDirectOpen = stageIdentityValid();
    if (sRetailDirectOpen) samplePreDirect();
}

void update() {
    const bool retailDirectRan = sRetailDirectOpen;
    sRetailDirectOpen = false;
    if (!retailDirectRan || !stageIdentityValid()) return;

    updateCountEvents();
    updateTransitions();
    updateHeldObject();
    updatePositionAndDamage();
    updatePetey();
    updateBossGesso();
    updateManta();
    updatePiantaOne();
    updatePollution();
    updateBowser();
}

void onYoshiMounted() {
    if (!sRetailDirectOpen || !stageIdentityValid()) return;
    if (routeScene(SplitStats::ROUTE_PINNA_EYG, 5, 2) ||
        routeScene(SplitStats::ROUTE_PINNA_6_FULL, 0x0D, 3) ||
        routeScene(SplitStats::ROUTE_PINNA_6_FULL_REDS, 0x0D, 3) ||
        routeScene(SplitStats::ROUTE_SIRENA_ENTER, 1, 8) ||
        routeScene(SplitStats::ROUTE_RICCO_8, 3, 7))
        publishEvent(sActiveRoute, 0);
}

void onNozzleCollected(TItemNozzle *nozzle) {
    if (!sRetailDirectOpen || !stageIdentityValid() || !nozzle) return;
    if (routeScene(SplitStats::ROUTE_CORONA, 0x34, 0))
        publishEvent(sActiveRoute, 1);
    const THitActor *item = reinterpret_cast<const THitActor *>(nozzle);
    if (item->mObjectID != 0x20000022u) return;
    if (routeScene(SplitStats::ROUTE_RICCO_8, 3, 7) ||
        routeScene(SplitStats::ROUTE_GELATO_4, 4, 3) ||
        routeScene(SplitStats::ROUTE_RIGHT_BELL, 1, 2) ||
        routeScene(SplitStats::ROUTE_SHINE_GATE, 1, 2))
        publishEvent(sActiveRoute, 0);
}

void armPinnaOneRetailExit() {
    if (!sRetailDirectOpen || !stageIdentityValid() ||
        sActiveRoute != SplitStats::ROUTE_PINNA_1)
        return;
    const u8 area = sStageDirector->mAreaID;
    const u8 episode = sStageDirector->mEpisodeID;
    if ((area == 0x0D && episode == 0) ||
        (area == 0x3A && episode == 1))
        sArmedCarryRoute = sActiveRoute;
}

void onSavestateLoaded() {
    clearAttemptState();
    sAttemptSerial = gQFTTimer.attemptSerial();
    sAttemptInvalid = true;
    sCarryAttempt = false;
    sBlockNextAttempt = false;
    sArmedCarryRoute = SplitStats::ROUTE_INVALID;
    sRetailDirectOpen = false;
}

}  // namespace SplitEvents

extern "C" void susamuneSplitCoinRedTaken(void *coin, void *collector) {
    reinterpret_cast<CoinRedTakenFn>(sCoinRedTakenTrampoline)(coin, collector);
    noteRedCoin();
}

extern "C" void *susamuneSplitPiantaRecoverNerve() {
    TBaseNPC *npc = *reinterpret_cast<TBaseNPC **>(kCurrentNpc);
    notePiantaRecovered(npc);
    return reinterpret_cast<RecoverNerveFn>(kRecoverNerve)();
}

extern "C" void susamuneSplitEmitHappyEffect(void *npc) {
    TBaseNPC *baseNpc = reinterpret_cast<TBaseNPC *>(npc);
    reinterpret_cast<EmitHappyEffectFn>(sEmitHappyEffectTrampoline)(baseNpc);
    notePiantaHappy(baseNpc);
}

extern "C" int susamuneSplitChangePlayerStatus(void *mario, u32 status,
                                                u32 arg, bool force) {
    TMario *player = reinterpret_cast<TMario *>(mario);
    const int changed = reinterpret_cast<ChangePlayerStatusFn>(
        sChangePlayerStatusTrampoline)(player, status, arg, force);
    if (changed) noteMarioStatus(player, player->mState);
    return changed;
}

extern "C" void susamuneSplitSpineUpdate(TSpineBase<TLiveActor> *spine) {
    if (!sRetailDirectOpen || !routeUsesSpine(sActiveRoute) ||
        !stageIdentityValid()) {
        reinterpret_cast<SpineUpdateFn>(sSpineUpdateTrampoline)(spine);
        return;
    }
    TLiveActor *actor = spine ? spine->mTarget : nullptr;
    const u32 vtable = objectVtable(actor);
    if (!spineActorRelevant(sActiveRoute, vtable)) {
        reinterpret_cast<SpineUpdateFn>(sSpineUpdateTrampoline)(spine);
        return;
    }
    const u32 nerveBefore = spine ? nerveVtable(spine->mNerveCurrent) : 0;
    const u32 previousBefore = spine ? nerveVtable(spine->mNervePrevious) : 0;
    const s32 nerveTimerBefore = spine ? spine->mNerveTimer : 0;
    const bool hasHealth = actor && healthActor(vtable);
    const u8 healthBefore = hasHealth
        ? reinterpret_cast<TSpineEnemy *>(actor)->mHealth : 0;
    const bool deadBefore = actor && actor->mStateFlags.asFlags.mIsObjDead;

    reinterpret_cast<SpineUpdateFn>(sSpineUpdateTrampoline)(spine);

    const u32 nerveAfter = spine ? nerveVtable(spine->mNerveCurrent) : 0;
    const u8 healthAfter = hasHealth
        ? reinterpret_cast<TSpineEnemy *>(actor)->mHealth : 0;
    const bool deadAfter = actor && actor->mStateFlags.asFlags.mIsObjDead;
    noteSpineUpdate(actor, vtable, nerveBefore, previousBefore,
                    nerveTimerBefore, nerveAfter, healthBefore, healthAfter,
                    deadBefore, deadAfter);
}

extern "C" void susamuneSplitStartDemo(
    TMarDirector *director, const char *name, const TVec3f *position,
    s32 camera, f32 blend, bool flag, s32 (*callback)(u32, u32),
    u32 callbackArg, JDrama::TActor *actor,
    const JDrama::TFlagT<u16> *demoFlag) {
    // This accepted queue edge is the single owner of demo-event freezes.
    const u8 before = *(reinterpret_cast<const u8 *>(director) + 0x24C);
    // Retail passes the non-trivial by-value flag through an indirect pointer.
    reinterpret_cast<StartDemoFn>(sStartDemoTrampoline)(
        director, name, position, camera, blend, flag, callback, callbackArg,
        actor, demoFlag);
    const u8 after = *(reinterpret_cast<const u8 *>(director) + 0x24C);
    if (after == before) return;
    if (gSettings.getBool(SETTING_TIMER_FREEZE_DEMO))
        gQFTTimer.freezeEvent();
}

extern "C" void susamuneSplitOpenTalk(void *talk, TBaseNPC *npc) {
    reinterpret_cast<OpenTalkFn>(sOpenTalkTrampoline)(talk, npc);
    noteTalk(npc);
}

extern "C" bool susamuneSplitRailCheck(TRailMapObj *rail) {
    const bool splitRoute = sRetailDirectOpen &&
        (sActiveRoute == SplitStats::ROUTE_SIRENA_2_FULL ||
         sActiveRoute == SplitStats::ROUTE_SIRENA_2_SECRET ||
         sActiveRoute == SplitStats::ROUTE_SIRENA_4_FULL ||
         sActiveRoute == SplitStats::ROUTE_SIRENA_4_SECRET ||
         sActiveRoute == SplitStats::ROUTE_PINNA_EYG ||
         sActiveRoute == SplitStats::ROUTE_PINNA_6_FULL ||
         sActiveRoute == SplitStats::ROUTE_PINNA_6_SECRET);
    if (!gSettings.getBool(SETTING_TIMER_FREEZE_MOVING_PLATFORM) &&
        !splitRoute)
        return reinterpret_cast<RailCheckFn>(sRailCheckTrampoline)(rail);

    const u32 before = rail->mControlState;
    const bool result = reinterpret_cast<RailCheckFn>(
        sRailCheckTrampoline)(rail);
    const u32 after = rail->mControlState;
    if (!(before & 2) || (after & 2) || !(after & 1)) return result;

    if (gSettings.getBool(SETTING_TIMER_FREEZE_MOVING_PLATFORM))
        gQFTTimer.freezeEvent();
    if (!splitRoute || !stageIdentityValid() || !gpMarioAddress) return result;
    if ((sActiveRoute == SplitStats::ROUTE_SIRENA_2_FULL ||
         sActiveRoute == SplitStats::ROUTE_SIRENA_2_SECRET) &&
        routeScene(sActiveRoute, 0x33, 0) &&
        gpMarioAddress->mTranslation.y < 4500.0f) {
        publishEvent(sActiveRoute,
            sActiveRoute == SplitStats::ROUTE_SIRENA_2_FULL ? 3 : 1);
    } else if ((sActiveRoute == SplitStats::ROUTE_SIRENA_4_FULL ||
                sActiveRoute == SplitStats::ROUTE_SIRENA_4_SECRET) &&
               routeScene(sActiveRoute, 0x28, 0)) {
        publishEvent(sActiveRoute,
            sActiveRoute == SplitStats::ROUTE_SIRENA_4_FULL ? 4 : 1);
    } else if (routeScene(SplitStats::ROUTE_PINNA_EYG, 0x29, 0) ||
               routeScene(SplitStats::ROUTE_PINNA_6_FULL, 0x29, 0)) {
        publishEvent(sActiveRoute, 2);
    } else if (routeScene(SplitStats::ROUTE_PINNA_6_SECRET, 0x29, 0)) {
        publishEvent(sActiveRoute, 0);
    }
    return result;
}

extern "C" void susamuneSplitPeteyHipDrop(void *petey) {
    TSpineEnemy *enemy = reinterpret_cast<TSpineEnemy *>(petey);
    const u8 before = enemy->mHealth;
    reinterpret_cast<PeteyHipDropFn>(sPeteyHipDropTrampoline)(petey);
    if (!sRetailDirectOpen || !stageIdentityValid()) return;
    const bool b2 = routeScene(SplitStats::ROUTE_BIANCO_2, 0x37, 0);
    const bool b5 = routeScene(SplitStats::ROUTE_BIANCO_5, 2, 4);
    if (b2 || b5) {
        const u8 after = enemy->mHealth;
        notePeteyDamage(before, after);
        // Keep the per-frame fallback from counting this hit again.
        sPetey = enemy;
        sPeteyHealth = after;
        sPeteyHealthValid = true;
    }
}

extern "C" void susamuneSplitGessoTentacleDamage(void *gesso) {
    s32 qf = 0;
    const bool candidate = hookScene(SplitStats::ROUTE_RICCO_1, 3, 0) &&
                           gQFTTimer.currentQf(&qf);
    reinterpret_cast<GessoTentacleDamageFn>(
        sGessoTentacleDamageTrampoline)(gesso);
    if (candidate) {
        publishEventAt(SplitStats::ROUTE_RICCO_1, 1, qf);
        sArmedCarryRoute = SplitStats::ROUTE_RICCO_1;
    }
}

bool eelToothAlreadyCounted(void *tooth) {
    for (u8 i = 0; i < sEelCleanedCount; ++i)
        if (sCleanedEelTeeth[i] == tooth) return true;
    return false;
}

extern "C" bool susamuneSplitEelToothMessage(void *tooth,
                                               THitActor *sender,
                                               u32 message) {
    const s32 before = *reinterpret_cast<const s32 *>(
        reinterpret_cast<const u8 *>(tooth) + 0x70);
    const bool result = reinterpret_cast<ReceiveMessageFn>(
        sEelToothMessageTrampoline)(tooth, sender, message);
    const s32 after = *reinterpret_cast<const s32 *>(
        reinterpret_cast<const u8 *>(tooth) + 0x70);
    const bool full = sActiveRoute == SplitStats::ROUTE_NOKI_4_FULL;
    if (message != 0xFu || before <= 1 || after != 1 ||
        !sRetailDirectOpen || !stageIdentityValid() ||
        (!full && sActiveRoute != SplitStats::ROUTE_NOKI_4_EEL) ||
        !routeScene(sActiveRoute, 0x39, 0) ||
        eelToothAlreadyCounted(tooth) || sEelCleanedCount >= 8)
        return result;
    sCleanedEelTeeth[sEelCleanedCount++] = tooth;
    if (sEelCleanedCount == 1)
        publishEvent(sActiveRoute, full ? 2 : 1);
    else if (sEelCleanedCount == 8)
        publishEvent(sActiveRoute, full ? 3 : 2);
    return result;
}

bool noteFenceMessage(bool result, THitActor *sender, u32 message) {
    if (result && message == 3 && sender == gpMarioAddress &&
        sRetailDirectOpen && routeScene(SplitStats::ROUTE_RICCO_3, 3, 2))
        publishEvent(sActiveRoute, 1);
    return result;
}

extern "C" bool susamuneSplitFenceMessage(void *fence,
                                            THitActor *sender, u32 message) {
    return noteFenceMessage(reinterpret_cast<ReceiveMessageFn>(
        sFenceMessageTrampoline)(fence, sender, message), sender, message);
}

extern "C" bool susamuneSplitRevolvingFenceMessage(
    void *fence, THitActor *sender, u32 message) {
    return noteFenceMessage(reinterpret_cast<ReceiveMessageFn>(
        sRevolvingFenceMessageTrampoline)(fence, sender, message), sender,
        message);
}

extern "C" void susamuneSplitBathtubQuake(void *bathtub,
                                            const void *position) {
    if (sRetailDirectOpen &&
        routeScene(SplitStats::ROUTE_BOWSER, 0x3C, 0)) {
        sBathtub = bathtub;
        if (!sBowserGripsValid) {
            sBowserGripsDead = 0;
            sBowserGripsValid = true;
        }
    }
    reinterpret_cast<BathtubQuakeFn>(sBathtubQuakeTrampoline)(bathtub,
                                                               position);
}

extern "C" void susamuneSplitItemAppear(void *actor) {
    reinterpret_cast<void (*)(void *)>(sItemAppearTrampoline)(actor);
    if (!sRetailDirectOpen || !stageIdentityValid() ||
        objectVtable(actor) != kShineVtable) return;
    const TShine *shine = static_cast<const TShine *>(actor);
    u32 expected = 0;
    u8 event = 0;
    switch (sActiveRoute) {
    case SplitStats::ROUTE_LIGHTHOUSE: expected = 93; break;
    case SplitStats::ROUTE_LEFT_BELL: expected = 96; break;
    case SplitStats::ROUTE_RIGHT_BELL: expected = 97; event = 1; break;
    case SplitStats::ROUTE_SHINE_GATE: expected = 99; event = 1; break;
    case SplitStats::ROUTE_BEACH_SHINE: expected = 117; break;
    case SplitStats::ROUTE_GOLD_BIRD: expected = 118; break;
    case SplitStats::ROUTE_NOKI_HIDDEN: expected = 59; event = 1; break;
    default: return;
    }
    const bool scene = sActiveRoute == SplitStats::ROUTE_NOKI_HIDDEN ?
        routeScene(sActiveRoute, 9, 6) : routeScene(sActiveRoute, 1, 2);
    if (scene && shine->mMapObjID == expected)
        publishEvent(sActiveRoute, event);
}

extern "C" void susamuneSplitSandCastle(void *actor) {
    const u16 before = static_cast<TMapObjBase *>(actor)->mState;
    reinterpret_cast<void (*)(void *)>(sSandCastleTrampoline)(actor);
    if (sRetailDirectOpen && before != 7 &&
        static_cast<TMapObjBase *>(actor)->mState == 7 &&
        (routeScene(SplitStats::ROUTE_GELATO_1_FULL, 4, 0) ||
         routeScene(SplitStats::ROUTE_GELATO_1_FULL_REDS, 4, 0)))
        publishEvent(sActiveRoute, 0);
}

extern "C" bool susamuneSplitMirrorMessage(void *actor,
                                            THitActor *sender, u32 message) {
    const s32 before = *reinterpret_cast<const s32 *>(
        static_cast<const u8 *>(actor) + 0x19C);
    const bool accepted = reinterpret_cast<ReceiveMessageFn>(
        sMirrorMessageTrampoline)(actor, sender, message);
    const s32 after = *reinterpret_cast<const s32 *>(
        static_cast<const u8 *>(actor) + 0x19C);
    if (accepted && message == 8 && before == 1 && after == 0 &&
        hookScene(SplitStats::ROUTE_GELATO_2, 4, 1) && sMirrorsCleared < 3) {
        for (u8 i = 0; i < sMirrorsCleared; ++i)
            if (sClearedMirrors[i] == actor) return accepted;
        sClearedMirrors[sMirrorsCleared] = actor;
        publishEvent(sActiveRoute, sMirrorsCleared++);
    }
    return accepted;
}

extern "C" void susamuneSplitHanachanDamage(void *actor) {
    TSpineEnemy *enemy = static_cast<TSpineEnemy *>(actor);
    const u8 before = enemy->mHealth;
    reinterpret_cast<void (*)(void *)>(sHanachanDamageTrampoline)(actor);
    if (hookScene(SplitStats::ROUTE_GELATO_3, 4, 2))
        for (u8 health = enemy->mHealth; health < before && sHanachanHits < 3; ++health)
            publishEvent(sActiveRoute, sHanachanHits++);
}

extern "C" void susamuneSplitTinKoopaHit(void *actor) {
    const s32 before = *reinterpret_cast<const s32 *>(
        static_cast<const u8 *>(actor) + 0x1C8);
    reinterpret_cast<void (*)(void *)>(sTinKoopaHitTrampoline)(actor);
    const s32 after = *reinterpret_cast<const s32 *>(
        static_cast<const u8 *>(actor) + 0x1C8);
    if (hookScene(SplitStats::ROUTE_PINNA_1, 0x3A, 1))
        for (s32 hit = after; hit < before && sTinKoopaHits < 4; ++hit)
            publishEvent(sActiveRoute, 1 + sTinKoopaHits++);
}

extern "C" void susamuneSplitStreamingMovie(TMarDirector *director, u8 movie) {
    const bool queuedBefore = (director->mGameState & 0x100) != 0;
    reinterpret_cast<void (*)(TMarDirector *, u8)>(sStreamingMovieTrampoline)(director, movie);
    if (!queuedBefore && (director->mGameState & 0x100) && movie == 2 &&
        director == sStageDirector && hookScene(SplitStats::ROUTE_AIRSTRIP_1, 0, 0) &&
        gpApplication.mNextScene.mAreaID == 0 && gpApplication.mNextScene.mEpisodeID == 1) {
        if (publishEvent(sActiveRoute, 0)) sArmedCarryRoute = sActiveRoute;
    }
}
