"""Exercise QFT's practice hold accounting and existing ghost clocks together."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class PracticeTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        timer = ROOT / "src/qft_timer.cpp"
        functions = "\n".join(function_source(timer, signature) for signature in (
            "s32 clampQf(", "s32 liveQf()", "s32 frozenDisplayQf()", "s32 compactQf()",
            "s32 sunshineQf(", "s32 qfToMillis(", "s32 qfToRoundedCentis(",
            "void updateBigTimer(", "void QFTTimer::update()",
            "void captureSection()", "void QFTTimer::beginFrame()",
            "void QFTTimer::onStageSetup(", "void QFTTimer::markPracticeAssisted()",
            "bool QFTTimer::practiceAssisted()",
            "void QFTTimer::beginPracticePause()", "void QFTTimer::endPracticePause()",
            "bool QFTTimer::currentQf(", "u32 QFTTimer::attemptSerial()",
            "void QFTTimer::captureSavestate(", "void QFTTimer::restoreSavestate(",
            "void QFTTimer::onSavestateSaved()", "void QFTTimer::onSavestateLoaded()"))
        ghost = ROOT / "src/ghost.cpp"
        functions += function_source(ghost, "s32 recordQf(").replace(
            "sAttemptSerial", "sGhostAttemptSerial")
        functions += function_source(ghost, "s32 observerQf(")
        functions += function_source(ghost, "void afterDirect(s32 appState)")
        source = Path(cls.folder.name) / "timer.cpp"
        source.write_text(r'''
#include "susamune/qft_timer.hxx"
#include "susamune/ghost_clock.h"
struct TimerState {u8 stopped,restart,stopReason,pad;s32 offsetQf,freezeQf,freezeFrames;};
static TimerState state;
static const int kSectionHistoryCount=16;
''' + function_source(timer, "struct SavedTimerData {") + r''';
#define memcpy __builtin_memcpy
static QFTTimer::SavestateData sSavedTimer,slots[3],candidate;
static volatile TimerState *sState=&state;
static s32 death,plant,transition;
static u16 target;
static volatile s32 *sDeathQf=&death,*sPlantQf=&plant,*sTransitionQf=&transition;
static volatile u16 *sTransitionTarget=&target;
struct J2DPane {};
struct TGCConsole2 {bool mIsTimerMoving;s32 value;
    void startAppearTimer(int,int){}void setTimer(s32 v){value=v;}};
static TGCConsole2 console;
class TMarDirector {public:enum {STATE_NORMAL=4,STATE_GAME_STARTING=2};s32 unk5C;TGCConsole2 *mGCConsole;u8 mCurState;u8 _260;};
struct TApplication {enum {CONTEXT_DIRECT_MAIN_LOOP=1};struct {u8 mAreaID;} mPrevScene;};
static TApplication gpApplication;
struct TGameSequence {enum {AREA_OPTION=15,AREA_DOLPIC=1};};
static const int STOP_NONE=0;
static TMarDirector director,other;
static TMarDirector *gpMarDirector=&director,*sStageDirector=&director,*sPracticeDirector;
static bool sStageReady,sStagePending,sResetRequested,sPracticeHolding,sHaveSavedState;
static bool sPracticeAssisted,sBigShown;
static u8 sBigUpdatePass;
static u32 sAttemptSerial,sPracticeSerial;
static s32 sPracticeStartQf,sPracticeFreezeQf,sPracticeDeathQf,sPracticePlantQf,sPracticeTransitionQf;
static u16 sPracticeTransitionTarget;
static bool sFinalConsumed,sBigRaised,sRetailTimerOwned;
static J2DPane *sBigTimerPane;
static const int kMaxQf=107892;
static s32 sSectionQf[16],sLastSectionQf;
static u8 sSectionCount,sSectionNext;
J2DPane *bigTimerPane(void *) {return nullptr;}
QFTTimer gQFTTimer;
static bool holding,sPaused,sLoadHoldActive;
namespace PracticeSession {bool freezeRequested(){return holding;}
''' + function_source(ROOT / "src/practice_session.cpp", "bool paused()") + r'''}
void restoreBigTimerPosition(){}
void ensureCoreHooks(){}
void applyFreezeConfig(){}
void resetSections(){sSectionCount=sSectionNext=0;sLastSectionQf=0;}
enum {SETTING_TIMER_SUNSHINE_VISIBILITY=1,SUNSHINE_ALWAYS=0,SUNSHINE_SHINE_ONLY=1};
static struct Settings {u8 get(int){return 0;}} gSettings;
bool finalStop(){return state.stopped&&state.stopReason!=0;}
void hideBigTimer(){}
bool missionCounterOnScreen(TGCConsole2*){return false;}
void raiseBigTimer(TGCConsole2*){}
static s32 nativeDrawn;
static SusamuneGhostClock sRecordClock;
static bool sFrameAssisted,sFrameFrozen;
static u32 sGhostAttemptSerial;
static const int SUSAMUNE_GHOST_RUN_TAS=1;
static struct {u32 runFlags;} sRecord;
enum {OBSERVER_ACTIVE_ONE=1,OBSERVER_ACTIVE_TWO=2};
static int sObserverPhase;
static bool sObserverClockReady;
static s32 sObserverBaseQf,sObserverLastQf,sObserverLastLiveQf,sObserverQfOffset,sObserverEndQf;
static bool sObserverMarioBaselineFinalized=true,sObserverMarioOwned=true;
bool observerRunning(){return true;}
void releaseObserverMario(bool){}
''' + functions + r'''
extern "C" __declspec(dllexport) void reset(s32 qf,s32 offset) {
    gpMarDirector=sStageDirector=&director;director.unk5C=qf;director.mCurState=4;director._260=1;
    console={false,-1};director.mGCConsole=&console;sBigShown=sRetailTimerOwned=false;
    state={0,0,0,0,offset,0,0};sStageReady=true;sStagePending=sResetRequested=false;
    sPracticeHolding=sPracticeAssisted=holding=sPaused=sLoadHoldActive=false;
    sAttemptSerial=sGhostAttemptSerial=7;sHaveSavedState=false;
    death=plant=-1;transition=0;target=0xffff;
    sRecordClock={};sFrameAssisted=true;sFrameFrozen=false;sRecord.runFlags=0;
    sObserverPhase=OBSERVER_ACTIVE_ONE;sObserverClockReady=true;
    sObserverBaseQf=0;sObserverEndQf=107892;sObserverLastLiveQf=sObserverLastQf=liveQf();
    sObserverQfOffset=0;sSectionCount=1;sSectionNext=1;sLastSectionQf=81;sSectionQf[0]=81;
}
extern "C" __declspec(dllexport) void tickBegin(unsigned held){holding=held!=0;gQFTTimer.beginFrame();}
extern "C" __declspec(dllexport) void stage(unsigned fresh) {
    gpApplication.mPrevScene.mAreaID=fresh?15:2;gQFTTimer.onStageSetup(&director);
    director.unk5C=0;gQFTTimer.beginFrame();
}
extern "C" __declspec(dllexport) void ghostAfter() {afterDirect(1);}
extern "C" __declspec(dllexport) void begin() {sPaused=true;gQFTTimer.beginPracticePause();}
extern "C" __declspec(dllexport) void holdLoad(unsigned active) {sLoadHoldActive=active!=0;}
extern "C" __declspec(dllexport) void advance(s32 qf) {director.unk5C+=qf;}
extern "C" __declspec(dllexport) void end() {gQFTTimer.endPracticePause();}
extern "C" __declspec(dllexport) s32 value(int which) {
    switch(which) {
    case 0:return liveQf();case 1:return compactQf();case 2:return frozenDisplayQf();
    case 3:return state.offsetQf+death;case 4:return state.offsetQf+plant;
    case 5:return state.offsetQf+transition;case 6:return director.unk5C;
    case 7:return state.offsetQf;case 8:return sLastSectionQf;case 9:return sSectionQf[0];
    case 10:return sPracticeHolding;case 11:return state.freezeFrames;
    case 12:return gQFTTimer.practiceAssisted();default:return -999;
    }
}
extern "C" __declspec(dllexport) void events(s32 freeze,s32 d,s32 p,s32 t) {
    state.freezeQf=freeze;state.freezeFrames=60;death=d;plant=p;transition=t;target=6;
}
extern "C" __declspec(dllexport) void stop() {
    state.offsetQf=liveQf();state.stopped=1;
}
extern "C" __declspec(dllexport) void boundary(unsigned which) {
    if(which==0)++sAttemptSerial;
    if(which==1)gpMarDirector=&other;
    if(which==2)sStageReady=false;
}
extern "C" __declspec(dllexport) void save() {gQFTTimer.onSavestateSaved();}
extern "C" __declspec(dllexport) void saveSlot(unsigned slot,unsigned commit) {
    gQFTTimer.captureSavestate(candidate);
    if(commit)slots[slot]=candidate;
}
extern "C" __declspec(dllexport) void renderFrame(unsigned paused,unsigned held,s32 ticks) {
    sPaused=paused!=0;holding=held!=0;gQFTTimer.beginFrame();
    if(holding)gQFTTimer.beginPracticePause();
    gQFTTimer.update();nativeDrawn=console.value;
    director.unk5C+=ticks;
    gQFTTimer.endPracticePause();gQFTTimer.update();
}
extern "C" __declspec(dllexport) s32 display(unsigned which) {
    if(which==0)return nativeDrawn;
    if(which==1)return qfToRoundedCentis(compactQf());
    if(which==2)return console.value;
    return qfToMillis(compactQf());
}
extern "C" __declspec(dllexport) void ownNative(unsigned yes) {
    console.mIsTimerMoving=yes!=0;console.value=54321;
}
extern "C" __declspec(dllexport) void section(s32 qf) {
    sLastSectionQf=qf;sSectionQf[0]=qf;
}
extern "C" __declspec(dllexport) void loadSlot(unsigned slot,s32 qf) {
    director.unk5C=qf;gQFTTimer.restoreSavestate(slots[slot]);
}
extern "C" __declspec(dllexport) void load(s32 qf) {
    director.unk5C=qf;gQFTTimer.onSavestateLoaded();
}
extern "C" __declspec(dllexport) s32 ghost(unsigned held,unsigned watcher) {
    sFrameFrozen=held!=0;
    if(watcher){sObserverPhase=watcher;return observerQf();}
    return recordQf(liveQf());
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self):
        self.lib.reset(100, -4)

    def hold(self, ticks=4):
        self.lib.begin()
        self.lib.advance(ticks)
        self.lib.end()

    def test_hold_stays_fixed_steps_and_resumed_play_advance_normally(self):
        for _ in range(900):
            self.hold()
            self.assertEqual((self.lib.value(0), self.lib.value(1)), (96, 92))
        self.assertEqual(self.lib.value(6), 3700)  # shared director clock stays live
        self.lib.advance(4)
        self.assertEqual(self.lib.value(0), 100)
        self.hold()
        self.assertEqual(self.lib.value(0), 100)
        self.lib.advance(120)
        self.assertEqual(self.lib.value(0), 220)

    def test_already_captured_results_and_section_baselines_do_not_drift(self):
        self.lib.events(80, 81, 82, 84)
        before = [self.lib.value(i) for i in (2, 3, 4, 5, 8, 9)]
        for _ in range(100):
            self.hold(5)
            self.assertEqual([self.lib.value(i) for i in (2, 3, 4, 5, 8, 9)], before)

    def test_new_event_during_hold_has_the_held_time(self):
        self.lib.begin()
        self.lib.advance(4)
        self.lib.events(104, 104, 104, 104)
        self.lib.end()
        self.assertEqual([self.lib.value(i) for i in (0, 3, 4, 5)], [96] * 4)

    def test_visual_event_freeze_does_not_expire_during_a_hold(self):
        self.lib.events(80, -1, -1, 84)
        before = 92
        for _ in range(100):
            self.lib.tickBegin(1)
            self.hold()
            self.assertEqual(self.lib.value(1), before)
            self.assertEqual(self.lib.value(11), 60)
        self.lib.tickBegin(0)
        self.lib.advance(4)
        self.assertEqual(self.lib.value(11), 59)
        self.assertEqual(self.lib.value(1), 96)

    def test_TAS_marker_survives_a_continued_area_and_resets_with_a_new_attempt(self):
        self.assertEqual(self.lib.value(12), 0)
        self.hold()
        self.assertEqual(self.lib.value(12), 1)
        self.lib.stage(0)
        self.assertEqual(self.lib.value(12), 1)
        self.lib.stage(1)
        self.assertEqual(self.lib.value(12), 0)

    def test_screenshot_native_11_88_and_compact_11_845_use_the_same_held_frame(self):
        self.lib.reset(1428, -4)
        self.lib.renderFrame(1, 1, 4)
        self.assertEqual(self.lib.display(3), 11845)
        self.assertEqual(self.lib.display(0), 1185)
        self.assertEqual(self.lib.display(2), 1185)

    def test_load_hold_without_manual_pause_aligns_native_and_compact_until_release(self):
        self.lib.reset(1428, -4)
        self.lib.holdLoad(1)
        for _ in range(120):
            self.lib.renderFrame(0, 1, 4)
            self.assertEqual(self.lib.display(3), 11845)
            self.assertEqual(self.lib.display(0), 1185)
            self.assertEqual(self.lib.display(2), 1185)
        self.lib.holdLoad(0)
        self.lib.renderFrame(0, 0, 4)
        self.assertGreater(self.lib.display(3), 11845)
        self.assertEqual(self.lib.display(0), self.lib.display(1))

    def test_native_and_compact_match_each_hold_step_and_resume_draw_phase(self):
        self.lib.renderFrame(0, 0, 4)
        self.assertEqual(self.lib.display(0), self.lib.display(1))
        for _ in range(5):
            self.lib.renderFrame(1, 1, 4)
            self.assertEqual(self.lib.display(0), self.lib.display(1))
            self.assertEqual(self.lib.display(2), self.lib.display(1))
            self.lib.renderFrame(1, 0, 4)
            self.assertEqual(self.lib.display(0), self.lib.display(1))
            self.assertEqual(self.lib.display(2), self.lib.display(1))
        self.lib.renderFrame(0, 0, 4)
        self.assertEqual(self.lib.display(0), self.lib.display(1))

    def test_saved_held_timer_resumes_both_displays_at_its_own_frame(self):
        self.lib.renderFrame(1, 1, 4)
        expected=self.lib.display(1)
        self.lib.saveSlot(0, 1)
        saved_director=self.lib.value(6)
        self.lib.renderFrame(1, 0, 4)
        self.lib.renderFrame(1, 1, 4)
        self.lib.loadSlot(0, saved_director)
        self.lib.renderFrame(1, 1, 4)
        self.assertEqual([self.lib.display(i) for i in range(3)], [expected]*3)

    def test_native_final_captures_and_retail_mission_timer_stay_unchanged(self):
        self.lib.stop()
        self.lib.renderFrame(1, 1, 4)
        self.assertEqual(self.lib.display(0), self.lib.display(1))
        self.lib.reset(100, -4)
        self.lib.events(80, -1, -1, 84)
        self.lib.renderFrame(0, 0, 4)
        self.assertEqual(self.lib.display(0), self.lib.display(1))
        self.lib.ownNative(1)
        self.lib.renderFrame(1, 1, 4)
        self.assertEqual((self.lib.display(0), self.lib.display(2)), (54321,54321))

    def test_finished_timer_does_not_rewind_while_paused(self):
        self.lib.stop()
        for _ in range(10):
            self.hold()
            self.assertEqual(self.lib.value(0), 96)

    def test_nested_begin_and_repeated_end_do_not_double_subtract(self):
        self.lib.begin()
        self.lib.advance(1)
        self.lib.begin()
        self.lib.advance(3)
        self.lib.end()
        self.lib.end()
        self.assertEqual(self.lib.value(0), 96)

    def test_attempt_or_director_change_cannot_apply_old_frame_offset(self):
        for boundary in range(3):
            self.setUp()
            self.lib.begin()
            self.lib.advance(4)
            self.lib.boundary(boundary)
            self.lib.end()
            self.assertEqual(self.lib.value(7), -4)

    def test_save_load_restores_adjusted_time_and_cancels_pending_hold(self):
        self.hold(40)
        self.lib.save()
        self.lib.advance(20)
        self.hold(40)
        self.lib.begin()
        self.lib.advance(4)
        self.lib.load(140)
        self.lib.end()
        self.assertEqual(self.lib.value(0), 96)
        self.assertEqual(self.lib.value(10), 0)
        self.hold()
        self.assertEqual(self.lib.value(0), 96)

    def test_three_slots_restore_their_own_clock_sections_and_assistance(self):
        for slot, (qf, offset, assisted) in enumerate(((100, -4, 0), (200, -44, 1), (500, 12, 0))):
            self.lib.reset(qf, offset)
            if assisted:
                self.hold(40)
            if slot == 2:
                self.lib.stop()
            self.lib.section(81 + slot * 11)
            self.lib.saveSlot(slot, 1)
        for slot, (qf, value, assisted) in enumerate(((100, 96, 0), (240, 156, 1), (500, 512, 0))):
            self.lib.reset(900, 99)
            self.lib.events(1000, 1001, 1002, 1004)
            self.lib.begin()
            self.lib.loadSlot(slot, qf)
            self.lib.end()
            self.assertEqual((self.lib.value(0), self.lib.value(8), self.lib.value(9),
                              self.lib.value(10), self.lib.value(12)),
                             (value, 81 + slot * 11, 81 + slot * 11, 0, assisted))

    def test_failed_slot_save_does_not_replace_sidecar_or_change_live_time(self):
        self.lib.saveSlot(1, 1)
        self.hold(40)
        self.lib.advance(28)
        before = [self.lib.value(i) for i in range(13)]
        self.lib.saveSlot(1, 0)
        self.assertEqual([self.lib.value(i) for i in range(13)], before)
        self.lib.loadSlot(1, 100)
        self.assertEqual((self.lib.value(0), self.lib.value(12)), (96, 0))

    def test_actual_watch_call_order_keeps_step_elapsed_before_next_hold(self):
        for watcher in (1, 2):
            self.setUp()
            self.assertEqual(self.lib.ghost(0, watcher), 96)
            self.lib.advance(4)
            self.lib.ghostAfter()
            self.assertEqual(self.lib.ghost(1, watcher), 100)
            for _ in range(25):
                self.hold()
                self.lib.ghostAfter()
                self.assertEqual(self.lib.ghost(1, watcher), 100)
            self.assertEqual(self.lib.ghost(0, watcher), 100)
            self.lib.advance(4)
            self.lib.ghostAfter()
            self.assertEqual(self.lib.ghost(1, watcher), 104)

    def test_recording_and_both_watch_modes_do_not_omit_time_twice(self):
        for watcher in (0, 1, 2):
            self.setUp()
            self.assertEqual(self.lib.ghost(0, watcher), 96)
            for _ in range(25):
                self.assertEqual(self.lib.ghost(1, watcher), 96)
                self.hold()
                self.assertEqual(self.lib.ghost(1, watcher), 96)
            self.lib.ghost(0, watcher)
            self.lib.advance(4)
            self.assertEqual(self.lib.ghost(0, watcher), 100)
            self.hold()
            self.assertEqual(self.lib.ghost(1, watcher), 100)


if __name__ == "__main__":
    unittest.main()
