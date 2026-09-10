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
                "void beforeDirect(", 'extern "C" s32 susamunePracticeChangeState(',
                "void afterDirect(", "void beforeStageSetup()",
                "void releaseForDeparture()", "void requestStop()"))
        source = Path(cls.folder.name) / "load_hold.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
#include "susamune/practice_input.h"
struct TMarioGamePad {
    u8 prefix[0xe2];u16 flags;u32 padding;s32 _E8;
    struct { bool mDisable; } mState;
    void updateMeaning() {}
};
static_assert(__builtin_offsetof(TMarioGamePad,_E8)==0xe8,"retail pad gate offset");
struct TMarDirector {
    enum { STATE_GAME_STARTING=2,STATE_NORMAL=4,STATE_PAUSE_MENU=5,STATE_STAGE_EXIT_2=12 };
    u32 mCurState,mGameState,mDemoState;
};
struct TApplication { enum { CONTEXT_DIRECT_MAIN_LOOP=1 };TMarioGamePad *mGamePads[1]; };
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
u32 fingerprint() {return 0;}
void message(const char *) {}
void invalidate() {++invalidations;sAssisted=true;}
void restoreCamera() {}
void updateCamera() {}
void stopTape(const char *) {sRecord=sReplay=false;sLoadKind=0;}
void inject(const SusamunePracticeInput &,TMarioGamePad *) {}
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
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.status.restype = C.c_uint

    def start(self, state=4, modes=0, buttons=0x102, bind=2):
        self.lib.reset(state, modes)
        self.lib.physical(buttons, 0)
        self.lib.arm(bind)
        self.lib.loaded()

    def low(self):
        return self.lib.status() & 255

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
