"""Exercise the production camera basis and queued physical stick inputs."""

import ctypes as C
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class Input(C.Structure):
    _fields_ = [("buttons", C.c_ushort), ("stickX", C.c_byte),
                ("stickY", C.c_byte), ("substickX", C.c_byte),
                ("substickY", C.c_byte), ("triggerL", C.c_ubyte),
                ("triggerR", C.c_ubyte), ("analogA", C.c_ubyte),
                ("analogB", C.c_ubyte), ("error", C.c_byte),
                ("flags", C.c_ubyte)]


class PracticeControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "controls.cpp"
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            "bool observerTransition()", "f32 axis(s8 value)",
            "f32 cameraSpeedScale()", "void spinInput(", "void updateCamera()",
            "bool requestSpin("))
        source.write_text(r'''
#include "susamune/practice_input.h"
typedef unsigned char u8;
typedef signed char s8;
typedef float f32;
extern "C" { int _fltused; }
struct Vec { float x,y,z; void set(float a,float b,float c) { x=a;y=b;z=c; } };
struct CameraView { Vec position,target,up; float fovy; };
struct JUTGamePad { enum { X=0x400 }; };
static const int SETTING_FREE_CAMERA_SPEED=1;
static const int SETTING_FREE_CAMERA_STRAFE_REVERSE=2;
struct Settings { u8 choice,reverse; u8 get(int id) { return id==1?choice:reverse; } } gSettings;
static CameraView sCameraView;
static SusamunePracticeInput sPhysical;
static bool sFreeCamera,sModal,sCameraWaitButtons,sControl,sNormal,sPaused;
static bool sStepQueued,sSpinClockwise;
static u8 sSpinRemaining,sMenuAction;
static const u8 kSpinFrames=9;
static unsigned invalidations;
static float sYaw,sPitch;
static float (*sine)(float),(*cosine)(float);
float sinf(float x) { return sine(x); }
float cosf(float x) { return cosine(x); }
float Clamp(float x,float lo,float hi) { return x<lo?lo:(x>hi?hi:x); }
bool controlStage() { return sControl; }
bool normalStage() { return sNormal; }
void message(const char *) {}
void invalidate() { ++invalidations; }
namespace Ghost {
static bool active,loading,cleanup;
bool observerActive() { return active; }
bool observerLoading() { return loading; }
bool observerCleanupPending() { return cleanup; }
}
''' + functions + r'''
extern "C" __declspec(dllexport) void trig(float (*s)(float),float (*c)(float)) {
    sine=s;cosine=c;
}
extern "C" __declspec(dllexport) void camera(float yaw,unsigned choice,unsigned flags,
    const SusamunePracticeInput *input,float *out) {
    sPhysical=*input;sYaw=yaw;sPitch=0;sFreeCamera=true;
    sModal=flags&1;sCameraWaitButtons=flags&2;sControl=!(flags&4);
    gSettings.choice=(u8)choice;gSettings.reverse=(flags&8)!=0;sCameraView.position.set(0,0,0);
    sCameraView.target.set(0,0,0);updateCamera();
    out[0]=sCameraView.position.x;out[1]=sCameraView.position.y;
    out[2]=sCameraView.position.z;out[3]=sCameraView.target.x;
    out[4]=sCameraView.target.y;out[5]=sCameraView.target.z;
    out[6]=sYaw;out[7]=sPitch;out[8]=sCameraWaitButtons;
}
extern "C" __declspec(dllexport) void spin(unsigned index,int cw,SusamunePracticeInput *input) {
    spinInput((u8)index,cw!=0,*input);
}
extern "C" __declspec(dllexport) unsigned queue(unsigned flags,int cw,int fromMenu) {
    sPaused=flags&1;sNormal=flags&2;sFreeCamera=flags&4;Ghost::active=flags&8;
    Ghost::loading=flags&16;Ghost::cleanup=flags&32;sSpinRemaining=0;
    sStepQueued=true;sMenuAction=0;invalidations=0;
    bool ok=requestSpin(cw!=0,fromMenu!=0);
    return sSpinRemaining|(sMenuAction<<8)|(ok<<16)|(invalidations<<17)|
           (sStepQueued<<18)|(sSpinClockwise<<19);
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        callback = C.CFUNCTYPE(C.c_float, C.c_float)
        cls.sine, cls.cosine = callback(math.sin), callback(math.cos)
        cls.lib.trig.argtypes = [callback, callback]
        cls.lib.trig(cls.sine, cls.cosine)
        cls.lib.camera.argtypes = [C.c_float, C.c_uint, C.c_uint, C.POINTER(Input),
                                  C.POINTER(C.c_float)]
        cls.lib.spin.argtypes = [C.c_uint, C.c_int, C.POINTER(Input)]
        cls.lib.queue.argtypes = [C.c_uint, C.c_int, C.c_int]
        cls.lib.queue.restype = C.c_uint

    def camera(self, yaw=0, choice=2, flags=0, **controls):
        raw = Input(**controls)
        out = (C.c_float * 9)()
        self.lib.camera(yaw, choice, flags, C.byref(raw), out)
        return list(out)

    def test_strafe_follows_lookat_screen_right_for_every_heading(self):
        for degree in range(-180, 181, 5):
            yaw = math.radians(degree)
            x, _, z, *_ = self.camera(yaw, stickX=80)
            self.assertAlmostEqual(x, -math.cos(yaw) * 20, places=4)
            self.assertAlmostEqual(z, math.sin(yaw) * 20, places=4)
            self.assertAlmostEqual(x * math.sin(yaw) + z * math.cos(yaw), 0, places=4)

    def test_speed_scales_translation_height_and_existing_boost(self):
        for choice, scale in enumerate((.25, .5, 1, 2, 4)):
            for boost, base in ((0, 20), (0x400, 75)):
                out = self.camera(choice=choice, stickY=80, triggerR=255, buttons=boost)
                self.assertAlmostEqual(out[2], base * scale)
                self.assertAlmostEqual(out[1], base * scale)
        self.assertAlmostEqual(self.camera(choice=255, stickY=80)[2], 20)

    def test_look_right_agrees_with_strafe_right_and_speed_does_not_change_turning(self):
        for choice in range(5):
            out = self.camera(choice=choice, substickX=80)
            self.assertLess(out[3], 0)
            self.assertAlmostEqual(out[6], -.035, places=6)

    def test_reverse_sideways_changes_only_main_stick_lateral_motion(self):
        for degree in range(-180, 181, 15):
            yaw = math.radians(degree)
            normal = self.camera(yaw, stickX=80)
            reverse = self.camera(yaw, flags=8, stickX=80)
            self.assertAlmostEqual(normal[0], -reverse[0], places=4)
            self.assertAlmostEqual(normal[2], -reverse[2], places=4)
            for controls in ({"stickY": 80}, {"substickX": 80},
                             {"substickY": 80}, {"triggerR": 255}):
                self.assertEqual(self.camera(yaw, **controls),
                                 self.camera(yaw, flags=8, **controls))

    def test_camera_modal_release_latch_and_deadzone(self):
        for flags in (1, 4):
            self.assertEqual(self.camera(flags=flags, stickX=80)[:3], [0, 0, 0])
        out = self.camera(flags=2, buttons=0x44, triggerL=255, stickX=80)
        self.assertEqual(out[:3], [0, 0, 0])
        self.assertEqual(out[8], 1)
        self.assertNotEqual(self.camera(flags=2, stickX=80)[0], 0)
        for value in range(-11, 12):
            self.assertEqual(self.camera(stickX=value, stickY=value)[:3], [0, 0, 0])

    def test_rotation_uses_only_real_stick_fields_and_completes_one_circle(self):
        for clockwise in (0, 1):
            values = []
            for index in range(9):
                raw = Input(0x142, 1, 2, -33, 44, 55, 66, 77, 88, -1, 9)
                before = bytes(raw)
                self.lib.spin(index, clockwise, C.byref(raw))
                self.assertEqual(bytes(raw)[:2] + bytes(raw)[4:], before[:2] + before[4:])
                values.append((raw.stickX, raw.stickY))
            self.assertEqual(values[0], values[-1])
            self.assertEqual(len(set(values)), 8)
            self.assertEqual(values[1][0] > 0, bool(clockwise))

    def test_full_circle_covers_every_retail_angle_quadrant(self):
        vectors = []
        for i in range(8):
            raw = Input()
            self.lib.spin(i, 1, C.byref(raw))
            vectors.append(math.atan2(raw.stickX, raw.stickY))
        for heading in range(0, 65536, 17):
            quadrants = set()
            for angle in vectors:
                value = ((round(angle * 32768 / math.pi) + heading + 32768) % 65536) - 32768
                if value < -24576 or value > 24576:
                    quadrants.add(0)
                if -24576 <= value <= -8192:
                    quadrants.add(1)
                if -8192 < value < 8192:
                    quadrants.add(2)
                if 8192 <= value <= 24576:
                    quadrants.add(3)
            self.assertEqual(len(quadrants), 4)

    def test_queue_requires_player_frame_hold_and_waits_for_menu_A_release(self):
        for flags in range(64):
            result = self.lib.queue(flags, 1, 1)
            if flags == 3:
                self.assertEqual(result & 255, 9)
                self.assertEqual((result >> 8) & 255, 1)
                self.assertTrue(result & (1 << 16))
                self.assertTrue(result & (1 << 17))
                self.assertFalse(result & (1 << 18))
            else:
                self.assertEqual(result & 255, 0)
                self.assertFalse(result & (1 << 16))


if __name__ == "__main__":
    unittest.main()
