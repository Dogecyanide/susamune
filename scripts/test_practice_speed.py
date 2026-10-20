"""Run the production practice-speed scheduler without emulating the game."""

import ctypes
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class PracticeSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="practice-speed-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "speed.cpp"
        production = ROOT / "src/practice_session.cpp"
        history = production.read_text().split("struct SpeedStickHistory {", 1)[1].split("} sSpeedStick;", 1)[0]
        history = "struct SpeedStickHistory {" + history + "} sSpeedStick;\n"
        functions = "\n".join(function_source(production, name) for name in (
            "void updateSpeedStickHistory(bool held)", "void resetGameplaySpeed()",
            "void prepareGameplaySpeed()", "void applyGameplaySpeed()"))
        il_source = ROOT / "src/iling.cpp"
        il_functions = "\n".join(function_source(il_source, name) for name in (
            "u8 liveGlobalAssistReasons()", "void invalidateForAssist(u8 reasons)"))
        il_update = function_source(il_source, "void update()")
        il_gate = il_update[il_update.index("    const u8 globalAssistReasons"):
                            il_update.index("    if (secretAttemptUsedFludd())")]
        source.write_text(r'''
#include "Dolphin/types.h"
#include "susamune/practice_input.h"
extern "C" { int _fltused=0; }
static u16 sPhysicalPressed,sSpeedPresses,sSpeedPriorButtons;
static u8 sRaisedTriggerL,sRaisedTriggerR,sSpeedTriggerL,sSpeedTriggerR,sSpeedPriorTriggerL,sSpeedPriorTriggerR;
static u8 sSpeedPhase,sSpeedChoice,percent;
static bool sModal,sFreeze,sStepping,sFreeCamera,sHaveRead,sAssisted,sReplay,sRecord,observer;
static bool hooksReady,actionable,fastForward;
static bool sCollisionHooksReady,sStateHookReady;
static SusamunePracticeInput sPhysical,sConsumed,injected;
static unsigned calls,invalidations,retained;
struct TMarioGamePad { float _A8,_AC; void updateMeaning() {} } pad,other;
static TMarioGamePad *sReadPad;
static struct {TMarioGamePad *mGamePads[1];} gpApplication={{&pad}};
template<class T>struct Param{T value;T get(){return value;}};
struct TMario {
    TMarioGamePad *mController;
    s16 *_530;u8 _534;u16 _536,_A0;float _368;
    struct {s16 y;}mAngle;
    struct {Param<s16>mStickRotateTime;}mControllerParams;
    struct {Param<s16>mSinkTime;Param<float>mSinkMoveMin,mSinkMoveMax;}mGraffitoParams;
} mario,otherMario;
static TMario *gpMarioOriginal=&mario;
struct CPolarSubCamera {s16 mAngleYaw;} camera;
static CPolarSubCamera *gpCamera=&camera;
static s16 retailHistory[60];
namespace Ghost {bool observerActive(){return observer;}}
bool mem1(const void *ptr,u32){return ptr!=nullptr;}
s16 matan(float z,float x) {
    // Retail matan(z,x), not libc atan2(y,x); these octants are exact.
    if (x==0) return z<0?-32768:0;
    if (z==0) return x<0?-16384:16384;
    return x>0?(z>0?8192:24576):(z>0?-8192:-24576);
}
enum {SETTING_GAMEPLAY_SPEED,SETTING_STAGE_INTRO_SKIP};
static struct {u8 get(int){return percent;}bool getBool(int id){return id==SETTING_GAMEPLAY_SPEED&&percent;}} gSettings;
namespace PracticeSession {bool available(){return hooksReady;}bool assisted(){return sAssisted;}}
bool actionableStage(){return actionable;}
bool actionsFastForwardActive(){return fastForward;}
void invalidate(){sAssisted=true;++invalidations;}
void inject(const SusamunePracticeInput &input,TMarioGamePad *){injected=input;++calls;}
void retainPausedReleases(TMarioGamePad *){++retained;}
''' + history + functions + r'''
namespace Assist {enum {OTHER=0x80};}
namespace Records {static unsigned invalidations;void invalidateAttempt(u8){++invalidations;}}
namespace StageLoader {void invalidatePlaylistBest(){}}
namespace SplitStats {void invalidateAttempt(){}}
namespace Eligibility {
static bool sRunning,sAwaitingStageSetup,sRecordsEligible;
static u8 sRejectionCause,sAssistReasons;
enum {REJECT_PRACTICE};
u8 liveRejectionCause(){return REJECT_PRACTICE;}
''' + il_functions + r'''
void update() {
''' + il_gate + r'''
}
}
extern "C" __declspec(dllexport) void ilReset() {
    Eligibility::sRunning=Eligibility::sRecordsEligible=true;
    Eligibility::sAwaitingStageSetup=false;
    Eligibility::sRejectionCause=Eligibility::sAssistReasons=0;
    Records::invalidations=0;
}
extern "C" __declspec(dllexport) unsigned ilTick(unsigned speed,unsigned modal) {
    percent=speed;sModal=modal;sFreeze=false;
    applyGameplaySpeed();Eligibility::update();
    return Eligibility::sRecordsEligible | (Records::invalidations<<8);
}
extern "C" __declspec(dllexport) unsigned ilReason(){return Eligibility::sAssistReasons;}
extern "C" __declspec(dllexport) void reset(unsigned speed) {
    resetGameplaySpeed();percent=speed;
    sPhysicalPressed=sRaisedTriggerL=sRaisedTriggerR=0;
    sSpeedPriorButtons=sSpeedPriorTriggerL=sSpeedPriorTriggerR=0;
    sModal=sFreeze=sStepping=sFreeCamera=sAssisted=sReplay=false;
    sRecord=observer=false;
    sHaveRead=hooksReady=actionable=sCollisionHooksReady=sStateHookReady=true;
    fastForward=false;sReadPad=&pad;
    sPhysical={};sConsumed={};injected={};calls=invalidations=retained=0;
    mario={};gpMarioOriginal=&mario;gpCamera=&camera;camera.mAngleYaw=0;
    mario.mController=&pad;mario._530=retailHistory;
    mario.mControllerParams.mStickRotateTime.value=24;
    mario.mGraffitoParams.mSinkTime.value=100;
    mario.mGraffitoParams.mSinkMoveMin.value=0.3f;
    mario.mGraffitoParams.mSinkMoveMax.value=0.5f;
    pad._A8=pad._AC=0;
    for(unsigned i=0;i<60;++i)retailHistory[i]=1234;
}
extern "C" __declspec(dllexport) unsigned sample(unsigned buttons,unsigned trigger,unsigned invalid) {
    sPhysical.buttons=buttons;sPhysical.triggerR=trigger;sPhysical.error=invalid?-1:0;
    prepareGameplaySpeed();return sPhysicalPressed | (sRaisedTriggerR<<16);
}
extern "C" __declspec(dllexport) unsigned tick(unsigned flags,unsigned buttons,
    unsigned pressed,unsigned trigger,unsigned raised) {
    sModal=flags&1;sFreeze=flags&2;sStepping=flags&4;sFreeCamera=flags&8;
    hooksReady=!(flags&16);actionable=!(flags&32);fastForward=flags&64;
    sHaveRead=!(flags&128);sReadPad=flags&256?&other:&pad;
    sConsumed={};sConsumed.error=flags&512?-1:0;sReplay=flags&1024;
    sRecord=flags&8192;observer=flags&16384;
    sCollisionHooksReady=!(flags&2048);sStateHookReady=!(flags&4096);
    sConsumed.buttons=buttons;sConsumed.triggerR=trigger;
    sPhysicalPressed=pressed;sRaisedTriggerR=raised;
    applyGameplaySpeed();return sFreeze;
}
extern "C" __declspec(dllexport) void speed(unsigned value){percent=value;}
extern "C" __declspec(dllexport) void stick(int x,int y,int yaw) {
    pad._A8=x/128.0f;pad._AC=y/128.0f;camera.mAngleYaw=yaw;
}
extern "C" __declspec(dllexport) int historyValue(int index) {
    if(index==-1)return mario._534;
    if(index==-2)return sSpeedStick.owner!=nullptr;
    if(index==-3)return sSpeedStick.count;
    return retailHistory[index];
}
extern "C" __declspec(dllexport) void historyConfig(int index,int value) {
    switch(index){
    case 0:mario.mControllerParams.mStickRotateTime.value=value;break;
    case 1:mario._534=value;break;
    case 2:mario._A0=value;break;
    case 3:mario.mController=value?&other:&pad;break;
    case 4:gpCamera=value?nullptr:&camera;break;
    case 5:mario._530=value?nullptr:retailHistory;break;
    case 6:mario._368=value;break;
    case 7:sSpeedStick.owner=&otherMario;break;
    }
}
extern "C" __declspec(dllexport) void discardHistory(){resetGameplaySpeed();}
extern "C" __declspec(dllexport) void nativeAngle(int angle) {
    retailHistory[mario._534++]=angle;
    const int limit=mario.mControllerParams.mStickRotateTime.value;
    if(mario._534>=limit){
        for(int i=0;i<limit;++i)retailHistory[i]=retailHistory[i+1];
        mario._534=limit-1;
    }
}
extern "C" __declspec(dllexport) unsigned state(unsigned index) {
    switch(index){case 0:return sSpeedPresses;case 1:return sSpeedTriggerR;
    case 2:return sConsumed.buttons;case 3:return sConsumed.triggerR;
    case 4:return calls;case 5:return sAssisted;case 7:return retained;default:return invalidations;}
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            "-I", str(ROOT / "include"), str(source), "-o", str(library),
        ], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)
        cls.dll.tick.argtypes = [ctypes.c_uint] * 5
        cls.dll.tick.restype = ctypes.c_uint
        cls.dll.ilTick.argtypes = [ctypes.c_uint, ctypes.c_uint]
        cls.dll.ilTick.restype = ctypes.c_uint
        cls.dll.sample.argtypes = [ctypes.c_uint] * 3
        cls.dll.sample.restype = ctypes.c_uint
        cls.dll.stick.argtypes = [ctypes.c_int] * 3
        cls.dll.historyValue.argtypes = [ctypes.c_int]
        cls.dll.historyValue.restype = ctypes.c_int
        cls.dll.historyConfig.argtypes = [ctypes.c_int] * 2
        cls.dll.nativeAngle.argtypes = [ctypes.c_int]
        for name in ("reset", "speed", "state"):
            getattr(cls.dll, name).argtypes = [ctypes.c_uint]
            getattr(cls.dll, name).restype = ctypes.c_uint

    def tick(self, flags=0, buttons=0, pressed=0, trigger=0, raised=0):
        return self.dll.tick(flags, buttons, pressed, trigger, raised)

    def test_every_percentage_has_exact_bounded_cadence(self):
        for percent in range(1, 100):
            self.dll.reset(percent)
            advanced = sum(not self.tick() for _ in range(1000))
            self.assertEqual(advanced, percent * 10, percent)
            self.assertEqual(self.dll.state(6), 1)

    def test_default_and_out_of_range_do_not_hold_or_assist(self):
        for value in (0, 100, 255):
            self.dll.reset(value)
            self.assertFalse(any(self.tick() for _ in range(120)))
            self.assertEqual(self.dll.state(5), 0)

    def test_other_owners_and_transitions_clear_queued_input(self):
        for guard in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 2048, 4096):
            self.dll.reset(25)
            self.tick()
            self.assertTrue(self.tick(buttons=0x100, pressed=0x100))
            self.assertEqual(self.dll.state(0), 0x100)
            self.assertEqual(self.tick(flags=guard), bool(guard & 2))
            self.assertEqual(self.dll.state(7), 1)
            self.assertEqual(self.dll.state(0), 0)
            self.assertEqual(self.dll.state(1), 0)
            self.assertFalse(self.tick())
            self.assertEqual(self.dll.state(2), 0)

    def test_short_button_and_trigger_taps_reach_one_simulation_frame(self):
        self.dll.reset(25)
        self.assertFalse(self.tick())
        self.assertTrue(self.tick(buttons=0x100, pressed=0x100, trigger=255, raised=255))
        self.assertTrue(self.tick())
        self.assertTrue(self.tick())
        self.assertFalse(self.tick())
        self.assertEqual([self.dll.state(i) for i in (0, 1, 2, 3, 4)],
                         [0, 0, 0x100, 255, 1])
        for _ in range(4):
            self.tick()
        self.assertEqual(self.dll.state(2), 0)
        self.assertEqual(self.dll.state(4), 1)
        self.assertEqual(self.dll.state(7), 6)

    def test_prepare_tracks_physical_edges_separately_from_retail_history(self):
        self.dll.reset(25)
        self.assertEqual(self.dll.sample(0x100, 255, 0), 0x00ff0100)
        self.assertEqual(self.dll.sample(0x100, 255, 0), 0)
        self.assertEqual(self.dll.sample(0, 80, 0), 0)
        self.assertEqual(self.dll.sample(0x100, 130, 0), 0x00820100)
        self.tick()
        self.tick(buttons=0x100, pressed=0x100, trigger=255, raised=255)
        self.assertEqual(self.dll.state(0), 0x100)
        self.assertEqual(self.dll.sample(0x200, 255, 1), 0)
        self.assertEqual(self.dll.state(0), 0)

    def test_held_buttons_and_replay_do_not_create_extra_presses(self):
        for flags in (0, 1024):
            self.dll.reset(25)
            self.tick()
            self.tick(flags, buttons=0x100, pressed=0x100 if flags else 0)
            for _ in range(3):
                self.tick(flags)
            self.assertEqual(self.dll.state(0), 0)
            self.assertEqual(self.dll.state(2), 0)
            self.assertEqual(self.dll.state(4), 0)

    def test_normal_speed_cannot_requalify_a_slowed_attempt(self):
        self.dll.reset(50)
        self.tick()
        self.tick(buttons=0x100, pressed=0x100)
        self.dll.speed(0)
        self.assertFalse(self.tick())
        self.assertEqual(self.dll.state(0), 0)
        self.assertEqual(self.dll.state(5), 1)

    def test_speed_enabled_only_in_paused_menu_still_invalidates_whole_il(self):
        self.dll.reset(0)
        self.dll.ilReset()
        self.assertEqual(self.dll.ilTick(0, 1), 1)
        self.assertEqual(self.dll.ilTick(50, 1), 0x100)
        self.assertEqual(self.dll.state(5), 0)
        self.assertNotEqual(self.dll.ilReason(), 0)
        self.assertEqual(self.dll.ilTick(0, 1), 0x100)
        self.assertEqual(self.dll.ilTick(0, 0), 0x100)

    def test_spin_samples_survive_between_simulation_frames_without_moving_mario(self):
        self.dll.reset(10)
        self.assertFalse(self.tick())
        # One quick revolution happens entirely between two gameplay updates.
        revolution = ((0, 80), (80, 80), (80, 0), (80, -80),
                      (0, -80), (-80, -80), (-80, 0), (-80, 80), (0, 80))
        expected = [-32768, 24576, 16384, 8192, 0, -8192, -16384, -24576, -32768]
        for x, y in revolution:
            self.dll.stick(x, y, 0)
            self.assertTrue(self.tick())
            self.assertEqual(self.dll.historyValue(-1), 0)
            self.assertEqual(self.dll.historyValue(0), 1234)
        self.assertFalse(self.tick())
        self.assertEqual(self.dll.historyValue(-1), len(expected))
        self.assertEqual([self.dll.historyValue(i) for i in range(len(expected))], expected)
        self.assertEqual(self.dll.historyValue(-2), 0)

    def test_stick_history_keeps_the_retail_real_time_window_at_every_speed(self):
        for percent in (1, 10, 25, 50, 99):
            for limit in (2, 24, 59):
                self.dll.reset(percent)
                self.dll.historyConfig(0, limit)
                expected = []
                for frame in range(205):
                    yaw = frame * 101
                    self.dll.stick(0, -80, yaw)
                    frozen = self.tick()
                    if not frozen:
                        self.assertEqual(self.dll.historyValue(-1), len(expected), (percent, limit, frame))
                        self.assertEqual([self.dll.historyValue(i) for i in range(len(expected))], expected)
                        self.dll.nativeAngle(yaw)
                    expected.append(yaw)
                    expected = expected[-(limit - 1):]

    def test_neutral_and_camera_relative_deadzone_samples_match_retail(self):
        self.dll.reset(10)
        self.tick()
        self.dll.stick(80, 0, 1234)
        self.tick()
        self.dll.stick(7, -7, 1234)
        self.tick()
        self.assertEqual(self.dll.historyValue(-3), 0)
        self.dll.stick(8, 0, 1234)
        for _ in range(7):
            self.tick()
        self.assertFalse(self.tick())
        self.assertEqual(self.dll.historyValue(-1), 7)
        self.assertEqual([self.dll.historyValue(i) for i in range(7)], [17618] * 7)
        # Sinking applies its native scale before the integer deadzone.
        self.dll.reset(25)
        self.tick()
        self.dll.historyConfig(6, 50)
        self.dll.stick(16, 0, 0)
        self.tick()
        self.assertEqual(self.dll.historyValue(-3), 0)
        self.dll.stick(32, 0, 0)
        self.tick()
        self.assertEqual(self.dll.historyValue(-3), 1)

    def test_tas_and_observer_inputs_never_acquire_unrecorded_spin_samples(self):
        for flags in (1024, 8192, 16384):
            self.dll.reset(10)
            self.tick()
            self.dll.stick(80, 0, 0)
            for _ in range(9):
                self.tick(flags=flags)
            self.assertFalse(self.tick(flags=flags))
            self.assertEqual(self.dll.historyValue(-1), 0)
            self.assertEqual(self.dll.historyValue(-2), 0)

    def test_history_owner_and_parameter_checks_discard_unusable_samples(self):
        invalid = ((0, 0), (0, 1), (0, 60), (0, 32767), (1, 24),
                   (2, 1), (3, 1), (4, 1), (5, 1))
        for field, value in invalid:
            self.dll.reset(25)
            self.tick()
            self.dll.stick(80, 0, 0)
            self.tick()
            self.assertEqual(self.dll.historyValue(-2), 1)
            self.dll.historyConfig(field, value)
            self.tick()
            self.assertEqual(self.dll.historyValue(-2), 0, (field, value))
        self.dll.reset(50)
        self.tick()
        self.dll.stick(80, 0, 0)
        self.tick()
        self.dll.historyConfig(7, 1)
        self.tick()
        self.assertEqual(self.dll.historyValue(-1), 0)

    def test_resets_and_other_input_owners_drop_private_history_without_restoring_ram(self):
        for guard in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 2048, 4096):
            self.dll.reset(25)
            self.tick()
            self.dll.stick(80, 0, 0)
            self.tick()
            self.assertEqual(self.dll.historyValue(-2), 1)
            self.tick(flags=guard)
            self.assertEqual(self.dll.historyValue(-2), 0)
            self.assertEqual(self.dll.historyValue(-1), 0)
            self.assertEqual(self.dll.historyValue(0), 1234)
        self.dll.reset(25)
        self.tick()
        self.dll.stick(80, 0, 0)
        self.tick()
        self.dll.discardHistory()
        self.assertEqual(self.dll.historyValue(-2), 0)
        self.assertEqual(self.dll.historyValue(0), 1234)

    def test_normal_speed_preserves_native_spin_history_and_discards_slowed_input(self):
        for speed in (0, 100, 255):
            self.dll.reset(speed)
            self.dll.historyConfig(1, 3)
            baseline = [self.dll.historyValue(i) for i in range(60)]
            for frame in range(120):
                self.dll.stick(80, 0, frame * 101)
                self.assertFalse(self.tick(buttons=0x100, pressed=0x100))
            self.assertEqual(self.dll.historyValue(-1), 3)
            self.assertEqual([self.dll.historyValue(i) for i in range(60)], baseline)
            self.assertEqual(self.dll.state(4), 0)
            self.assertEqual(self.dll.state(5), 0)
            self.dll.reset(25)
            self.tick()
            self.dll.stick(80, 0, 0)
            self.tick(buttons=0x100, pressed=0x100)
            self.assertEqual(self.dll.historyValue(-2), 1)
            self.dll.speed(speed)
            self.assertFalse(self.tick())
            self.assertEqual(self.dll.historyValue(-2), 0)
            self.assertEqual(self.dll.historyValue(-1), 0)
            self.assertEqual(self.dll.historyValue(0), 1234)
            self.assertEqual(self.dll.state(0), 0)
            self.assertEqual(self.dll.state(4), 0)

    def test_lifecycle_discards_pre_load_and_pre_warp_input(self):
        for file, call in (("main.cpp", "beforeStageSetup"),
                           ("savestate.cpp", "onSavestateLoaded"),
                           ("warp_wheel.cpp", "releaseForDeparture")):
            text = (ROOT / "src" / file).read_text()
            self.assertRegex(text, r"PracticeSession::resetGameplaySpeed\(\);\s*"
                                   r"PracticeSession::" + call + r"\(\);")

    def test_extension_surrounds_original_before_direct_without_changing_its_owner(self):
        main = (ROOT / "src/main.cpp").read_text()
        for argument in ("false", "practiceModal"):
            self.assertIn("PracticeSession::prepareGameplaySpeed();\n" +
                          ("        " if argument == "false" else "    ") +
                          "PracticeSession::beforeDirect(" + argument + ");\n" +
                          ("        " if argument == "false" else "    ") +
                          "PracticeSession::applyGameplaySpeed();", main)
        production = ROOT / "src/practice_session.cpp"
        for name in ("void beforeDirect(bool modalOwnsInput)", "void beforeStageSetup()",
                     "void onSavestateLoaded()", "void releaseForDeparture()"):
            self.assertNotIn("GameplaySpeed", function_source(production, name))
        extension = production.read_text().split('// Keep the timer-facing owner', 1)[1]
        self.assertIn('#pragma clang section text="" rodata="" data="" bss=""', extension)


if __name__ == "__main__":
    unittest.main()
