"""Exercise Secret/Reds identity through production save, finish and reset paths."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_iling_attempt_lifecycle import function

ROOT = Path(__file__).resolve().parents[1]


class SecretRestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-secret-reset-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / "src/iling.cpp").read_text()
        sequence = (ROOT / "include/SMS/System/GameSequence.hxx").read_text()
        warp = (ROOT / "src/warp_wheel.cpp").read_text()
        code = r'''
#include "susamune/iling.hxx"
#define memcpy __builtin_memcpy
extern "C" void*memset(void*d,int v,__SIZE_TYPE__ n){
volatile u8*p=(volatile u8*)d;while(n--)*p++=(u8)v;return d;}
struct TGameSequence {
''' + sequence[sequence.index("    enum Area {"):sequence.index("    void set(")] + r'''
u8 mAreaID,mEpisodeID;u16 mFlags;};
namespace LevelWarp {struct Dest {enum {POST_CORONA=0x80};u8 area,episode,gameInt3;};u8 parentArea(u8);}
'''
        code += re.search(r"(?:constexpr|const) u8 kParentAreas\[\].*?\n};", warp, re.S).group(0)
        code += function(warp, "LevelWarp::parentArea")
        code += source[source.index("enum FinishKind {"):source.index("constexpr u8 kGroupFirst")]
        for name in ("kEntryPinnaEyg", "kEntryPinna8", "kEntrySirena8", "kEntryGelatoGbs",
                     "kEntryGelato4Inside", "kEntryBowser", "kEntryCorona",
                     "kEntryFullRedsFirst", "kEntryFullRedsLast"):
            code += re.search(r"const int " + name + r" = \d+;", source).group(0) + "\n"
        code += "const int kOverlayFlagCount=2;\n"
        for name in ("AttemptState", "SavedAttemptData"):
            code += re.search(r"struct " + name + r" \{.*?\n\};", source, re.S).group(0) + "\n"
        code += r'''
static_assert(sizeof(SavedAttemptData)==sizeof(ILing::SavestateData),"sidecar unchanged");
static AttemptState sAttemptState,sSavedAttemptState;
''' + source[source.index("#define sRunning "):source.index("#define sCustomPbProfileNames ")] + r'''
static bool sHaveSavedAttempt,sPinnaEygRestart,sSavedPinnaEygRestart;
static bool sHaveSetupShineCount,sHaveSetupMovieFlag,sTemporaryRocketActive;
static bool sRocketEquipPending,sBowserNozzleShieldPending,sBowserNozzleShieldActive;
static u8 sSavedSecondNozzle,sActivePbProfile;
static s32 sSavedSecondNozzleFlag,sSavedBowserNozzleFlag;
static int sFanfareDelay,sAchievementChimeBlockFrames,sBannerFrames;
static int recordEntry,splitEntry,resultEntry,splitEligible,results,streakMode;
struct TApplication {enum {CONTEXT_DIRECT_STAGE=5,CONTEXT_DIRECT_MOVIE=6,CONTEXT_DIRECT_SHINE_SELECT=7};
int mContext;TGameSequence mCurrentScene,mPrevScene;}gpApplication;
struct TMarDirector {enum{STATE_GAME_STARTING=2,STATE_NORMAL=4,STATE_PAUSE_MENU=5,STATE_SAVE_CARD=6};
int _260,mCurState;struct Console{bool mIsTimerMoving;}*mGCConsole;}director,*gpMarDirector=&director;
struct TFlagManager {
static TFlagManager*smInstance;struct{u8 m1Type[0x80];}Type1Flag;int values[0x40100];
int getFlag(u32 id){return values[id];}bool getBool(u32 id){return getFlag(id)!=0;}
void setFlag(u32 id,int v){values[id]=v;}void setBool(bool v,u32 id){setFlag(id,v);}
}flags;TFlagManager*TFlagManager::smInstance=&flags;
struct TWaterGun {enum{Spray,Rocket};u8 mSecondNozzle;int mCurrentWater;
struct Nozzle{struct Params{struct Amount{int get(){return 100;}}mAmountMax;}mEmitParams;}*mNozzleList[1];
void changeNozzle(int,bool){}};
struct Mario{TWaterGun*mFludd;}*gpMarioOriginal=0;
static u32 lastShine;
#define SUSAMUNE_ADDR_LAST_SHINE_ID (&lastShine)
struct Timer {
u32 serial;bool finish;u32 attemptSerial(){return serial;}
bool practiceAssisted(){return false;}
bool consumeShine(s32*qf){if(!finish)return false;finish=false;*qf=1000;return true;}
bool consumeTransition(s32*,u16*){return false;}bool consumeBowser(s32*){return false;}
bool consumeCustom(bool,s32*){return false;}
}gQFTTimer;
enum {SETTING_ILING_POPUP,SETTING_ILING_FANFARE,SETTING_STAGE_INTRO_SKIP};
struct Settings{bool getBool(int){return false;}}gSettings;
enum {SUSAMUNE_HOVERLESS_PROFILE=4,BGM_GET_SHINE=0};
namespace MSBgm{void stopBGM(int,int){}}
namespace Hoverless{void service(){}}
namespace GhostFludd{bool hoverEmitted(){return false;}}
namespace Records{void onILAttemptEnded(){}void onILAttemptStarted(int e){recordEntry=e;}
void invalidateAttempt(u8){}}
namespace StageLoader{
bool onSavestateLoaded(){return streakMode;}bool active(){return streakMode;}
bool fastAnyStart(int){return false;}void onILAttemptEnded(){}
void invalidatePlaylistBest(){}void onILAttemptStarted(int,bool=false){}
}
namespace SplitStats{void onILAttemptEnded(){splitEntry=-1;}
void onILAttemptStarted(int e,bool ok){splitEntry=e;splitEligible=ok;}
void invalidateAttempt(){splitEligible=false;}}
namespace FinishBreakdown{void invalidate(){}}
void restorePlazaSetupState(){}bool isPlazaEntry(int){return false;}
void applyPlazaOverlay(int){}
u8 liveGlobalAssistReasons(){return 0;}u8 liveRejectionCause(){return REJECT_PRACTICE;}
void servicePBSave(){}bool pbRecordingEnabled(){return true;}
void startPbFanfare(){}
bool secretAttemptUsedFludd(){return false;}void captureGhostRace(int){}
void invalidateForAssist(u8){sRecordsEligible=false;}
void recordResult(int e,s32){resultEntry=e;++results;}
'''
        for name in ("validEntry", "pbSlot", "entryFinish", "isBonusShine",
                     "sameDest", "parentOrSelf", "sameCourse", "sessionStartChanged",
                     "fullRedsBaseShine", "sceneMatches", "acceptsAnySelectedOrigin",
                     "acceptsSkipOrigin", "isPinnaOneRouteScene", "isPinnaEightReturn",
                     "acceptsSelectedOriginScene", "isInternalScene", "stageObjectsLive",
                     "entryForStartScene", "entryForChildMode", "entryForResult",
                     "readOverlayFlag", "writeOverlayFlag", "applyOverlayFlag",
                     "restoreOverlayFlags", "applyEntryOverlay", "restorePlazaStoryFlags",
                     "clearAttempt", "clearAttemptForRetry", "armAttempt",
                     "beginAttemptScene", "beforeStageSetup"):
            code += function(source, name)
        code += "namespace ILing {\n"
        for name in ("captureSavestate", "restoreSavestate", "onSavestateLoaded", "update"):
            code += function(source, name)
        code += r'''
}
static ILing::SavestateData slots[3];
#define API extern "C" __declspec(dllexport)
API int count(){return kEntryCount;}
API int slot(int e){return pbSlot(e);}
API void reset(){
sAttemptState={};sSavedAttemptState={};sSelectedEntry=-1;sHaveSavedAttempt=false;
sHaveSetupShineCount=sHaveSetupMovieFlag=sTemporaryRocketActive=false;
sRocketEquipPending=sBowserNozzleShieldPending=sBowserNozzleShieldActive=false;
sPinnaEygRestart=false;sActivePbProfile=0;streakMode=0;flags={};
gpApplication.mContext=TApplication::CONTEXT_DIRECT_STAGE;
gpApplication.mCurrentScene={1,0,0};gpApplication.mPrevScene={1,0,0};
director={1,TMarDirector::STATE_NORMAL,0};gQFTTimer={1,false};
recordEntry=splitEntry=resultEntry=-1;results=splitEligible=0;
}
API void select(int e,int completed){
gpApplication.mCurrentScene={kEntries[e].start.area,kEntries[e].start.episode,0};
for(int i=0;i<0x40100;++i)flags.values[i]=completed;
armAttempt(kEntries[e],e);applyEntryOverlay(e);beforeStageSetup();
// setupObjects/setMario consumed the overlay, as in ILing::update's carry path.
restoreOverlayFlags();++gQFTTimer.serial;ILing::update();
}
API void child(int e){gpApplication.mCurrentScene={kEntries[e].start.area,kEntries[e].start.episode,0};}
API void save(int slot){ILing::captureSavestate(slots[slot]);}
API void load(int slot){ILing::restoreSavestate(slots[slot]);}
API void reload(){gQFTTimer.finish=false;beforeStageSetup();++gQFTTimer.serial;ILing::update();}
API void finish(int e){lastShine=kEntries[e].result;gQFTTimer.finish=true;ILing::update();}
API void leave(){gpApplication.mCurrentScene={1,0,0};beforeStageSetup();}
API void title(){gpApplication.mContext=0;ILing::update();gpApplication.mContext=TApplication::CONTEXT_DIRECT_STAGE;}
API void cancel(){clearAttempt();}
API void streak(int mode){streakMode=mode;}
API int value(int i){switch(i){
case 0:return sRunning;case 1:return sRecordsEligible;case 2:return sSelectedEntry;
case 3:return sSecretOnly;case 4:return recordEntry;case 5:return splitEntry;
case 6:return splitEligible;case 7:return resultEntry;case 8:return results;
case 9:return sOverlayCount;default:return -999;}}
API int flag(int e){return flags.getFlag(0x10000u+kEntries[e].result);}
'''
        path = Path(cls.temp.name) / "secret_restart.cpp"
        path.write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib", "-fuse-ld=lld",
            "-Wl,/noentry", "-O2", "-I", str(ROOT / "include"), "-I", str(ROOT / "src"),
            str(path), "-o", str(path.with_suffix(".dll"))], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(path.with_suffix(".dll")))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.by_slot = {cls.lib.slot(e): e for e in range(cls.lib.count())}
        cls.pairs = [(cls.by_slot[70 + i], cls.by_slot[red])
                     for i, red in enumerate((8, 9, 18, 28, 38, 39, 48, 49, 58, 68))]

    def setUp(self):
        self.lib.reset()

    def assert_reset_identity(self, entry, secret):
        self.lib.reload()
        self.assertEqual([self.lib.value(i) for i in range(7)],
                         [1, 1, entry, int(secret), entry, entry, 1])

    def test_all_red_secrets_survive_save_load_reset_with_clean_records_and_splits(self):
        for secret, red in self.pairs:
            self.lib.reset(); self.lib.select(red, 0); self.lib.save(0)
            self.assertEqual(self.lib.flag(secret), 0)
            self.lib.load(0)
            self.assertEqual([self.lib.value(i) for i in (0, 1, 2, 9)], [0, 0, red, 0])
            self.lib.finish(red)
            self.assertEqual(self.lib.value(8), 0, "Loaded attempt must not publish a result")
            self.assert_reset_identity(red, False)
            self.assertEqual(self.lib.flag(secret), 1, "setMario needs replay-mode flag on retry")

    def test_all_fluddless_secrets_remain_secret_on_completed_files(self):
        for secret, red in self.pairs:
            self.lib.reset(); self.lib.select(secret, 1); self.lib.save(0); self.lib.load(0)
            self.assert_reset_identity(secret, True)
            self.assertEqual(self.lib.flag(secret), 0)

    def test_shine_finish_disarms_then_keeps_both_modes_on_retry(self):
        for secret, red in self.pairs:
            for entry, is_secret in ((secret, True), (red, False)):
                self.lib.reset(); self.lib.select(entry, int(is_secret)); self.lib.finish(entry)
                self.assertEqual([self.lib.value(i) for i in (0, 1, 2, 7, 8)],
                                 [0, 0, entry, entry, 1])
                self.assert_reset_identity(entry, is_secret)

    def test_three_slots_and_second_capture_keep_their_own_mode(self):
        secret, red = self.pairs[0]
        for slot, entry in enumerate((red, secret, self.pairs[4][1])):
            self.lib.select(entry, 0); self.lib.save(slot)
        for slot, entry in enumerate((red, secret, self.pairs[4][1])):
            self.lib.child(entry); self.lib.load(slot)
            self.assertEqual(self.lib.value(2), entry)
        self.lib.child(red); self.lib.load(0); self.lib.save(2); self.lib.load(2)
        self.assert_reset_identity(red, False)

    def test_leaving_title_or_explicit_cancel_drops_retained_mode(self):
        secret, red = self.pairs[0]
        for boundary in ("leave", "title", "cancel"):
            self.lib.reset(); self.lib.select(red, 0); self.lib.save(0); self.lib.load(0)
            getattr(self.lib, boundary)()
            self.lib.child(red); self.lib.reload()
            self.assertNotEqual(self.lib.value(2), red, boundary)

    def test_full_red_route_restored_inside_secret_becomes_local_red_retry(self):
        for i, (secret, red) in enumerate(self.pairs):
            self.lib.reset(); self.lib.select(self.by_slot[126 + i], 0)
            self.lib.child(red); self.lib.save(0); self.lib.load(0)
            self.assert_reset_identity(red, False)

    def test_streak_restore_keeps_existing_disqualification_and_route(self):
        secret, red = self.pairs[0]
        self.lib.select(red, 0); self.lib.save(0); self.lib.streak(1); self.lib.load(0)
        self.assertEqual([self.lib.value(i) for i in (0, 1, 2)], [1, 0, red])

    def test_ordinary_stage_does_not_keep_a_secret_retry_identity(self):
        ordinary = self.by_slot[50]
        self.lib.select(ordinary, 0); self.lib.save(0); self.lib.load(0)
        self.assertEqual([self.lib.value(i) for i in (0, 1, 2)], [0, 0, -1])


if __name__ == "__main__":
    unittest.main()
