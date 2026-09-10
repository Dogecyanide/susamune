"""Run production held-Load, intro transitions and lifecycle handling on the host."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class LoadHoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        functions = "\n".join(function_source(ROOT / "src/practice_session.cpp", name)
            for name in (
                "bool normalStage(", "bool controlStage(", "bool introStage(",
                "bool actionableStage(", "bool activatePendingPause(",
                "bool activatePendingLoadHold(", "void armLoadHold(",
                "void cancelLoadHold(", "void onSavestateLoaded()",
                "bool paused()", "bool manualPaused()",
                "u32 hashBytes(", "bool validSceneKey(", "void stopTape(",
                "bool suspendForScene(", "bool activateTimelineArrival(",
                "void beforeDirect(", 'extern "C" s32 susamunePracticeChangeState(',
                "void afterDirect(", "void beforeStageSetup()",
                "void releaseForDeparture()", "void requestStop()"))
        source = Path(cls.folder.name) / "load_hold.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
#include "susamune/practice_input.h"
#include "susamune/tas_storage.h"
static unsigned meaningCalls;
struct TMarioGamePad {
    u8 prefix[0xe2];u16 flags;u32 padding;s32 _E8;
    struct { bool mDisable; } mState;
    void updateMeaning() {++meaningCalls;}
};
static_assert(__builtin_offsetof(TMarioGamePad,_E8)==0xe8,"retail pad gate offset");
struct TMarDirector {
    enum { STATE_GAME_STARTING=2,STATE_NORMAL=4,STATE_PAUSE_MENU=5,STATE_STAGE_EXIT=9,STATE_STAGE_EXIT_2=12 };
    u32 mCurState,mGameState,mDemoState;
};
struct TApplication { enum { CONTEXT_DIRECT_MAIN_LOOP=1,CONTEXT_DIRECT_STAGE=5,CONTEXT_DIRECT_MOVIE=6 };TMarioGamePad *mGamePads[1]; };
struct Mario { u32 mState; };
static TMarioGamePad pad;
static TMarDirector director;
static TMarDirector *gpMarDirector=&director;
static TApplication gpApplication={{&pad}};
static Mario mario,*gpMarioOriginal=&mario;
static SusamunePracticeInput sPhysical,sConsumed;
static bool ready,transition,sPaused,sPausePending,sLoadHoldActive,sLoadHoldPending;
static bool sOwnLoad,sCameraWaitButtons,sFreeCamera,sStepQueued,sHaveRead;
static bool sConsumedFrame,sStepping,sModal,sFrameInjected,sRecord,sReplay,sFreeze;
static bool sBorrowedPause,sAssisted;
static bool sTakeAttached,sModalPadValid;
static u32 sEditRevision;
static SusamuneTasTransition sTransitions[32];
static u32 sTransitionCount,sTransitionCursor,sStartScene,sTransitionFrom,sTapeStage,sTapeHash;
static u8 sTransitionMode;
static u16 sLoadWait,sStartRelease;
static bool sTransitionSetup,sTransitionPaused,sArrivalResume;
static u32 liveScene,liveFingerprint,neutralizations;
static u32 sTakePosition,sOriginKey[2],sPendingReleases;
static u16 sLoadHoldButtons,sStripButtons,sBeforeRead;
static u8 sMenuAction,sLoadKind;
static u32 sSteps,sSettingsHash,sCount,sCursor,sTapeSeed,sStageGeneration;
static unsigned invalidations,retailCalls,begins,ends;
static s32 retailResult;
static u32 retailNext;
static TMarioGamePad *sReadPad;
static void *sCamera;
static const char *sStatus;
static char sReplayFailure[64];
struct Frame { SusamunePracticeInput input;u32 fingerprint; };
static const u32 kMaxFrames=4,kFrameFingerprintMask=0x7fffffffu;
static Frame sFrames[kMaxFrames];
struct SavestateManager { static const u32 kSlotCount=3; };
struct Seed { bool valid; };
static Seed sSeeds[3];
struct Timer { void beginPracticePause() {++begins;} void endPracticePause() {++ends;} } gQFTTimer;
struct JUTGamePad { enum { A=0x100 }; };
const int BIND_PRACTICE_STOP=1;
static struct {bool wasPressed(int){return true;}u16 get(int){return 0x20;}void suppressUntilRelease(){}} gBinds;
static const unsigned SUSAMUNE_CRASH_EVENT_PRACTICE=1,SUSAMUNE_CRASH_EVENT_REPLAY=2;
namespace CrashReport { void note(unsigned,unsigned,unsigned) {} }
namespace ILing { void invalidateForAssist() {} }
namespace Records { void invalidateAttempt() {} }
namespace Ghost {
static bool frozen;
bool observerActive() {return false;}
void frameControl(bool hold,bool) {frozen=hold;}
void invalidateForAssist() {}
}
namespace WarpWheel { bool shown() {return false;} bool promptPending() {return false;} }
bool stageReady() {return ready;}
bool observerTransition() {return transition;}
bool assisted() {return sAssisted;}
bool actionsFastForwardActive() {return false;}
u32 settingsHash() {return 0;}
u32 fingerprint() {return liveFingerprint;}
u32 currentSceneKey(){return liveScene;}
void message(const char *text) {sStatus=text;}
void invalidate() {++invalidations;sAssisted=true;}
void restoreCamera() {}
void updateCamera() {}
void stopTape(const char *);
void inject(const SusamunePracticeInput &,TMarioGamePad *,u32 releases=0) {if(releases==0x1fffff)++neutralizations;}
void writeFrame(Frame &f,const SusamunePracticeInput&i,u32 h,u32){f.input=i;f.fingerprint=h;}
void consumeControlInput() {}
void retainPausedReleases(TMarioGamePad *) {}
void retainModalHistory() {}
void capturePad(u16 &out,TMarioGamePad *p) {out=p->flags;}
void restorePad(u16 value,TMarioGamePad *p) {p->flags=value;}
int snprintf(char *,size_t,const char *,...) {return 0;}
s32 retailChange(TMarDirector *d) {++retailCalls;d->mCurState=retailNext;return retailResult;}
static const size_t kChangeState=reinterpret_cast<size_t>(&retailChange);
''' + functions + r'''
extern "C" __declspec(dllexport) void reset(unsigned state,unsigned modes) {
    ready=true;transition=false;pad={};pad.flags=2;director={};director.mCurState=state;
    sPhysical={};sConsumed={};sPaused=modes&1;sOwnLoad=modes&2;
    sPausePending=sLoadHoldActive=sLoadHoldPending=sCameraWaitButtons=false;
    sFreeCamera=sStepQueued=sHaveRead=sConsumedFrame=sStepping=sModal=false;
    sFrameInjected=sRecord=sReplay=sFreeze=sBorrowedPause=sAssisted=false;
    sLoadHoldButtons=sStripButtons=sBeforeRead=sMenuAction=sLoadKind=0;
    sReadPad=0;sCamera=0;mario.mState=0;
    sSteps=sSettingsHash=sCount=sCursor=sTapeSeed=sStageGeneration=0;
    sTransitionCount=sTransitionCursor=sTransitionFrom=sTapeStage=sTapeHash=0;
    sLoadWait=sStartRelease=sTransitionMode=0;sTransitionSetup=sTransitionPaused=sArrivalResume=false;
    liveScene=sStartScene=0x02000000;liveFingerprint=neutralizations=meaningCalls=0;
    sOriginKey[0]=sOriginKey[1]=sTakePosition=0;sTakeAttached=sModalPadValid=false;
    invalidations=retailCalls=begins=ends=0;Ghost::frozen=false;
}
extern "C" __declspec(dllexport) unsigned stopReplay() {
    sReplay=true;sTakeAttached=true;sTakePosition=sCursor=2;sCount=4;sFrameInjected=true;sHaveRead=true;sReadPad=&pad;
    requestStop();beforeDirect(false);afterDirect(1,!sFreeze);
    return (sPaused?1:0)|(sFreeze?2:0)|(sTakeAttached?4:0)|(sConsumedFrame?8:0)|(sTakePosition<<8);
}
extern "C" __declspec(dllexport) void arm(unsigned buttons) {armLoadHold((u16)buttons);}
extern "C" __declspec(dllexport) void physical(unsigned buttons,int error) {
    sPhysical.buttons=(u16)buttons;sPhysical.error=(s8)error;
}
extern "C" __declspec(dllexport) void loaded() {onSavestateLoaded();}
extern "C" __declspec(dllexport) void before(unsigned modal) {beforeDirect(modal!=0);}
extern "C" __declspec(dllexport) void state(unsigned value) {director.mCurState=value;}
extern "C" __declspec(dllexport) void gates(unsigned flags,int counter,unsigned game,unsigned demo) {
    pad.flags=(u16)flags;pad._E8=counter;director.mGameState=game;director.mDemoState=demo;
}
extern "C" __declspec(dllexport) int change(unsigned next,int result) {
    retailNext=next;retailResult=result;return susamunePracticeChangeState(&director);
}
extern "C" __declspec(dllexport) void after(int result) {afterDirect(result,false);}
extern "C" __declspec(dllexport) void lifecycle(unsigned which) {
    if(which==0)beforeStageSetup();
    if(which==1)releaseForDeparture();
    if(which==2)afterDirect(4,false);
    if(which==3){ready=false;beforeDirect(false);}
}
extern "C" __declspec(dllexport) unsigned status() {
    return sLoadHoldActive|(sLoadHoldPending<<1)|(sFreeze<<2)|(sPaused<<3)|
        (sPausePending<<4)|(sBorrowedPause<<5)|(sStepping<<6)|(sStepQueued<<7)|
        (director.mCurState<<8)|(begins<<16)|(invalidations<<24);
}
extern "C" __declspec(dllexport) unsigned mask() {return sLoadHoldButtons;}
extern "C" __declspec(dllexport) unsigned pauseViews() {return paused()|(manualPaused()<<1);}
extern "C" __declspec(dllexport) void step() {sStepQueued=true;}
extern "C" __declspec(dllexport) void depart(unsigned paused) {
    sRecord=sTakeAttached=true;sOriginKey[1]=77;sPaused=paused!=0;
    sHaveRead=true;sReadPad=&pad;sConsumed.buttons=0x100;
    director.mCurState=9;afterDirect(1,true);
}
extern "C" __declspec(dllexport) void replayZone(unsigned destination,unsigned hash) {
    sReplay=sTakeAttached=true;sOriginKey[1]=77;sCount=3;sCursor=0;
    sTransitions[0]={1,0,sStartScene,destination,hash};sTransitionCount=1;
    sHaveRead=sFrameInjected=true;sReadPad=&pad;
    sFrames[0].fingerprint=liveFingerprint;director.mCurState=9;afterDirect(1,true);
}
extern "C" __declspec(dllexport) void scene(unsigned scene,unsigned hash) {liveScene=scene;liveFingerprint=hash;}
extern "C" __declspec(dllexport) void fullZones() {sTransitionCount=32;sTransitions[31]={0,0,sStartScene,sStartScene,0};}
extern "C" __declspec(dllexport) void endAtZone(){sCount=sCursor;}
extern "C" __declspec(dllexport) unsigned timeline(unsigned field) {
    switch(field){case 0:return sCount;case 1:return sTransitionCount;case 2:return sTransitionMode;
    case 3:return sRecord;case 4:return sReplay;case 5:return sTakeAttached;case 6:return sFrames[0].input.buttons;
    case 7:return sOriginKey[1];case 8:return sCursor;case 9:return neutralizations;case 10:return sTransitions[0].frame;
    case 11:return sTransitions[0].fromScene;case 12:return sTransitions[0].toScene;case 13:return sTransitions[0].startFingerprint;
    case 14:return sStageGeneration;case 15:return sAssisted;case 16:return meaningCalls;default:return 0;}
}
extern "C" __declspec(dllexport) const char*text(){return sStatus;}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.status.restype = C.c_uint
        cls.lib.text.restype = C.c_char_p

    def start(self, state=4, modes=0, buttons=0x102, bind=2):
        self.lib.reset(state, modes)
        self.lib.physical(buttons, 0)
        self.lib.arm(bind)
        self.lib.loaded()

    def low(self):
        return self.lib.status() & 255

    def arrive_zone(self, scene=0x2F000001, fingerprint=123):
        self.lib.lifecycle(0)
        self.lib.state(2)
        self.lib.scene(scene, fingerprint)
        self.lib.change(4, 1)

    def test_zone_entry_input_recorded_before_loading_suspends_tape(self):
        self.lib.reset(4, 0); self.lib.depart(1)
        self.assertEqual([self.lib.timeline(i) for i in (0, 2, 3, 5, 6, 7)], [1, 1, 1, 0, 0x100, 77])
        self.lib.after(5)
        self.assertEqual(self.lib.timeline(0), 1)

    def test_setup_retains_tape_and_origin_then_arrival_gets_exact_marker(self):
        self.lib.reset(4, 0); self.lib.depart(1); self.arrive_zone()
        self.assertEqual([self.lib.timeline(i) for i in (0, 1, 2, 3, 5, 7)], [1, 1, 0, 1, 1, 77])
        self.assertEqual([self.lib.timeline(i) for i in (9, 10, 11, 12, 13, 14, 15)],
                         [1, 1, 0x02000000, 0x2F000001, 123, 1, 1])
        self.assertTrue(self.low() & 32)  # Retail transition cannot consume the arrival tick.
        self.assertEqual(self.lib.timeline(16), 0)  # No extra retail controller-timer decrement.
        self.lib.after(1); self.lib.before(0)
        self.assertTrue(self.low() & 8)

    def test_running_tas_resumes_after_single_arrival_barrier(self):
        self.lib.reset(4, 0); self.lib.depart(0); self.arrive_zone()
        self.assertTrue(self.low() & 32)
        self.lib.after(1); self.lib.before(0)
        self.assertFalse(self.low() & (4 | 8))
        self.assertEqual(self.lib.timeline(0), 1)

    def test_replay_waits_through_load_and_validates_new_scene(self):
        self.lib.reset(4, 0); self.lib.replayZone(0x2F000001, 123)
        self.assertEqual([self.lib.timeline(i) for i in (0, 2, 4, 8)], [3, 2, 1, 1])
        self.arrive_zone()
        self.assertEqual([self.lib.timeline(i) for i in (0, 2, 4, 5, 8)], [3, 0, 1, 1, 1])

    def test_replay_wrong_destination_or_arrival_hash_freezes_and_keeps_take(self):
        for scene, fingerprint in ((0x2F000002, 123), (0x2F000001, 456)):
            with self.subTest(scene=scene, fingerprint=fingerprint):
                self.lib.reset(4, 0); self.lib.replayZone(0x2F000001, 123)
                self.arrive_zone(scene, fingerprint)
                self.assertEqual([self.lib.timeline(i) for i in (0, 2, 4, 5, 7)], [3, 0, 0, 0, 77])
                self.assertTrue(self.low() & 8)
                self.assertTrue(self.low() & 32)
                self.assertIn(b"differed", self.lib.text())

    def test_replay_ending_at_arrival_remains_paused_without_extra_gameplay_frame(self):
        self.lib.reset(4, 0); self.lib.replayZone(0x2F000001, 123); self.lib.endAtZone()
        self.arrive_zone(); self.lib.after(1); self.lib.before(0)
        self.assertEqual([self.lib.timeline(i) for i in (0, 2, 4, 5, 8)], [1, 0, 0, 1, 1])
        self.assertTrue(self.low() & 8)
        self.assertTrue(self.low() & 4)
        self.assertIn(b"finished", self.lib.text())

    def test_arrival_waits_for_real_mario_control_and_not_just_loaded_area(self):
        self.lib.reset(4, 0); self.lib.depart(1); self.lib.lifecycle(0)
        self.lib.scene(0x2F000001, 123); self.lib.gates(0, 0, 0, 0)
        self.lib.change(4, 1)
        self.assertEqual(self.lib.timeline(2), 1)
        self.assertEqual(self.lib.timeline(1), 0)
        self.lib.gates(2, 0, 0, 0); self.lib.change(4, 1)
        self.assertEqual(self.lib.timeline(1), 1)

    def test_manual_warp_and_unexpected_setup_keep_unsaved_prefix(self):
        self.lib.reset(4, 0); self.lib.depart(1)
        self.lib.lifecycle(1)
        self.lib.lifecycle(0)
        self.assertEqual([self.lib.timeline(i) for i in (0, 1, 2, 3, 5, 7)], [1, 0, 0, 0, 0, 77])

    def test_canceled_zone_keeps_unsaved_prefix_detached(self):
        self.lib.reset(4, 0); self.lib.depart(0); self.lib.state(4); self.lib.before(0)
        self.assertEqual([self.lib.timeline(i) for i in (0, 2, 3, 5, 7)], [1, 0, 0, 0, 77])
        self.assertIn(b"canceled", self.lib.text())

    def test_transition_limit_stops_without_erasing_zone_entry_or_older_markers(self):
        self.lib.reset(4, 0); self.lib.fullZones(); self.lib.depart(0)
        self.assertEqual([self.lib.timeline(i) for i in (0, 1, 2, 3, 7)], [1, 32, 0, 0, 77])
        self.assertIn(b"limit", self.lib.text())

    def test_normal_restore_holds_subset_and_release_resumes_without_pausing(self):
        self.start(bind=0x42, buttons=0x142)
        self.lib.before(0)
        self.assertEqual(self.low(), 5)
        self.assertEqual(self.lib.mask(), 0x42)
        self.lib.physical(0x242, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 5)
        self.lib.physical(0x240, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 0)
        self.assertEqual(self.lib.mask(), 0)

    def test_stop_shortcut_freezes_last_replay_frame_and_retains_edit_position(self):
        self.lib.reset(4, 0)
        self.assertEqual(self.lib.stopReplay(), 0x207)

    def test_timer_pause_report_includes_load_hold_without_changing_menu_toggle(self):
        self.start()
        self.assertEqual(self.lib.pauseViews(), 1)
        self.lib.physical(0x100, 0)
        self.lib.before(0)
        self.assertEqual(self.lib.pauseViews(), 0)
        self.start(modes=1)
        self.assertEqual(self.lib.pauseViews(), 3)
        self.lib.physical(0x100, 0)
        self.lib.before(0)
        self.assertEqual(self.lib.pauseViews(), 3)
        self.start(state=2)
        self.assertEqual(self.lib.pauseViews(), 0)
        self.lib.change(4, 1)
        self.assertEqual(self.lib.pauseViews(), 1)

    def test_async_request_does_not_freeze_before_restore(self):
        for state in (0, 1, 2, 4):
            self.lib.reset(state, 0)
            self.lib.physical(0x102, 0)
            self.lib.arm(2)
            self.lib.before(0)
            self.assertEqual(self.low(), 0)
            self.assertEqual(self.lib.mask(), 2)

    def test_intro_finishes_before_hold_activates_at_first_actionable_tick(self):
        for state in (0, 1, 2):
            self.start(state=state)
            self.lib.before(0)
            self.assertEqual(self.low(), 2)
            self.assertEqual(self.lib.change(4, 1), 1)
            self.assertEqual(self.low(), 37)  # active, frozen, borrowed; no frame pause
            self.assertEqual((self.lib.status() >> 8) & 255, 12)
            self.assertEqual((self.lib.status() >> 16) & 255, 1)
            self.lib.after(1)
            self.assertEqual((self.lib.status() >> 8) & 255, 4)
            self.lib.before(0)
            self.assertEqual(self.low(), 5)
            self.lib.physical(0x100, 0)
            self.lib.before(0)
            self.assertEqual(self.low(), 0)

    def test_intro_release_or_disconnect_cancels_before_transition(self):
        for buttons, error in ((0x100, 0), (0x102, -1)):
            self.start(state=2)
            self.lib.physical(buttons, error)
            self.lib.before(0)
            self.lib.change(4, 1)
            self.assertEqual(self.low(), 0)
            self.assertEqual(self.lib.mask(), 0)
            self.assertEqual((self.lib.status() >> 16) & 255, 0)

    def test_intro_respects_disabled_pad_modal_and_secondary_tick_gate(self):
        for flags, counter, game, demo, modal in (
                (0, 0, 0, 0, 0), (2, 2, 0, 0, 0), (2, 1, 0x4000, 0, 0),
                (2, 0, 0, 1, 0), (2, 0, 0, 0, 1)):
            self.start(state=2)
            self.lib.gates(flags, counter, game, demo)
            self.lib.before(modal)
            self.lib.change(4, 1)
            self.assertEqual(self.low(), 2)
            self.lib.gates(2, 1, 0, 0)
            self.lib.before(0)
            self.lib.change(4, 1)
            self.assertEqual(self.low(), 37)

    def test_existing_pause_survives_load_release_and_blocks_step_while_held(self):
        self.start(modes=1)
        self.lib.step()
        self.lib.before(0)
        self.assertEqual(self.low(), 141)
        self.lib.physical(0x100, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 72)  # existing pause, explicitly queued Step
        self.start(modes=1)
        self.lib.physical(0x100, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 12)

    def test_previous_pause_buffers_separately_when_loading_an_intro(self):
        for release in (False, True):
            self.start(state=2, modes=1)
            self.lib.before(0)
            self.assertEqual(self.low(), 18)
            if release:
                self.lib.physical(0x100, 0)
                self.lib.before(0)
            self.lib.change(4, 1)
            self.assertEqual(self.low(), 44 if release else 45)
            self.lib.after(1)
            self.lib.physical(0x100, 0)
            self.lib.before(0)
            self.assertEqual(self.low(), 12)

    def test_replay_unbound_released_and_ineligible_restores_never_arm_hold(self):
        for args in ({"modes": 2}, {"bind": 0}, {"buttons": 0x100},
                     {"state": 7}, {"state": 9}, {"state": 12}):
            self.start(**args)
            self.assertEqual(self.low(), 0)
            self.assertEqual(self.lib.mask(), 0)

    def test_lifecycle_departures_cancel_both_pending_and_active_holds(self):
        for state in (2, 4):
            for path in range(4):
                self.start(state=state)
                self.lib.lifecycle(path)
                self.assertEqual(self.low() & 3, 0)
                self.assertEqual(self.lib.mask(), 0)
        self.start(state=2)
        self.lib.state(7)
        self.lib.before(0)
        self.assertEqual(self.lib.mask(), 0)

    def test_real_app_departure_never_borrows_a_normal_tick(self):
        self.start(state=2)
        self.lib.before(0)
        self.assertEqual(self.lib.change(4, 4), 4)
        self.assertEqual(self.low(), 2)
        self.assertEqual((self.lib.status() >> 16) & 255, 0)
        self.lib.after(4)
        self.assertEqual(self.low(), 0)
        self.assertEqual(self.lib.mask(), 0)

    def test_new_warp_cancels_pause_buffered_in_old_intro(self):
        self.start(state=2, modes=1)
        self.assertEqual(self.low() & 16, 16)
        self.lib.lifecycle(1)
        self.assertEqual(self.low() & 24, 0)
        self.lib.state(4)
        self.lib.before(0)
        self.assertEqual(self.low() & 24, 0)

    def test_first_actionable_rendered_frame_can_activate_without_transition(self):
        self.start(state=2)
        self.lib.state(4)
        self.lib.gates(2, 1, 0x4000, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 2)
        self.lib.gates(2, 0, 0x4000, 0)
        self.lib.before(0)
        self.assertEqual(self.low(), 5)


if __name__ == "__main__":
    unittest.main()
