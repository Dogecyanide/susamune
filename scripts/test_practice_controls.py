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
            'extern "C" void susamunePracticeClampPad(', "bool observerTransition()", "void cameraStick(",
            "f32 cameraScale(", "f32 cameraSpeedScale()", "void updateCamera()"))
        source.write_text(r'''
#include "susamune/practice_input.h"
#include "Dolphin/PAD.h"
typedef unsigned char u8;
typedef float f32;
extern "C" { int _fltused; }
struct Vec { float x,y,z; void set(float a,float b,float c) { x=a;y=b;z=c; } };
struct CameraView { Vec position,target,up; float fovy; };
struct JUTGamePad { enum { X=0x400 }; };
static const int SETTING_FREE_CAMERA_SPEED=1;
static const int SETTING_FREE_CAMERA_STRAFE_REVERSE=2;
static const int SETTING_FREE_CAMERA_SENSITIVITY=3;
typedef int SettingId;
struct Settings { u8 choice,reverse,sensitivity; u8 get(int id) { return id==1?choice:id==2?reverse:sensitivity; } } gSettings;
static CameraView sCameraView;
static SusamunePracticeInput sPhysical;
static s8 sCameraSticks[4];
static unsigned clampCalls;
extern "C" void *memcpy(void *d,const void *s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void PADClamp(PADStatus *pad) {
    ++clampCalls;
    for(unsigned port=0;port<4;++port) {
        if(pad[port].mCurError) continue;
        s8 *axes=reinterpret_cast<s8*>(&pad[port].mStickX);
        for(unsigned i=0;i<4;++i){int v=axes[i];axes[i]=(s8)(v>15?v-15:v<-15?v+15:0);}
        pad[port].mTriggerLeft/=2;pad[port].mTriggerRight/=2;
    }
}
static bool sFreeCamera,sModal,sCameraWaitButtons,sControl,sNormal,sPaused;
static bool sStepQueued,sSpinClockwise;
static u8 sSpinRemaining,sMenuAction;
static const u8 kSpinFrames=9;
static unsigned invalidations;
static float sYaw,sPitch;
static float (*sine)(float),(*cosine)(float),(*squareRoot)(float);
float sinf(float x) { return sine(x); }
float cosf(float x) { return cosine(x); }
float retailSquareRoot(float x) { return squareRoot(x); }
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
extern "C" __declspec(dllexport) unsigned rawClamp(const SusamunePracticeInput *in,
    SusamunePracticeInput *out,s8 *raw,unsigned wrapped) {
    PADStatus pad[4];memcpy(pad,in,sizeof(pad));clampCalls=0;
    if(wrapped)susamunePracticeClampPad(pad);else PADClamp(pad);
    memcpy(out,pad,sizeof(pad));memcpy(raw,sCameraSticks,4);return clampCalls;
}
extern "C" __declspec(dllexport) void trig(float (*s)(float),float (*c)(float),float (*r)(float)) {
    sine=s;cosine=c;squareRoot=r;
}
extern "C" __declspec(dllexport) void camera(float yaw,unsigned choice,unsigned flags,
    const SusamunePracticeInput *input,float *out) {
    sPhysical=*input;sCameraSticks[0]=input->stickX;sCameraSticks[1]=input->stickY;sCameraSticks[2]=input->substickX;sCameraSticks[3]=input->substickY;sYaw=yaw;sPitch=0;sFreeCamera=true;
    sModal=flags&1;sCameraWaitButtons=flags&2;sControl=!(flags&4);
    gSettings.choice=(u8)choice;gSettings.reverse=(flags&8)!=0;
    gSettings.sensitivity=(flags&16)?(flags>>5):2;sCameraView.position.set(0,0,0);
    sCameraView.target.set(0,0,0);updateCamera();
    out[0]=sCameraView.position.x;out[1]=sCameraView.position.y;
    out[2]=sCameraView.position.z;out[3]=sCameraView.target.x;
    out[4]=sCameraView.target.y;out[5]=sCameraView.target.z;
    out[6]=sYaw;out[7]=sPitch;out[8]=sCameraWaitButtons;
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
        cls.sine, cls.cosine, cls.square_root = callback(math.sin), callback(math.cos), callback(math.sqrt)
        cls.lib.trig.argtypes = [callback, callback, callback]
        cls.lib.trig(cls.sine, cls.cosine, cls.square_root)
        cls.lib.camera.argtypes = [C.c_float, C.c_uint, C.c_uint, C.POINTER(Input),
                                  C.POINTER(C.c_float)]

    def test_raw_camera_capture_precedes_unchanged_retail_clamp_for_all_ports(self):
        for error in (0, -1):
            source = (Input * 4)(*[Input(buttons=0x1300 + i, stickX=70, stickY=5,
                substickX=-6, substickY=-65, triggerL=120, triggerR=180,
                error=error if i == 0 else 0) for i in range(4)])
            expected, actual = (Input * 4)(), (Input * 4)()
            raw = (C.c_byte * 4)()
            self.assertEqual(self.lib.rawClamp(source, expected, raw, 0), 1)
            self.assertEqual(self.lib.rawClamp(source, actual, raw, 1), 1)
            self.assertEqual(bytes(actual), bytes(expected))
            self.assertEqual(list(raw), [70, 5, -6, -65])
            if not error:
                self.assertEqual((actual[0].stickX, actual[0].stickY), (55, 0))

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

    def test_look_sensitivity_changes_both_angles_without_scaling_movement(self):
        for choice, scale in enumerate((.25, .5, 1, 2, 4)):
            out = self.camera(flags=16 | choice << 5, substickX=80, substickY=80, triggerR=255)
            self.assertAlmostEqual(out[6], -.035 * scale / math.sqrt(2), places=6)
            self.assertAlmostEqual(out[7], .035 * scale / math.sqrt(2), places=6)
            self.assertAlmostEqual(out[1], 20)
        self.assertAlmostEqual(self.camera(flags=16 | 255 << 5, substickX=80)[6], -.035, places=6)

    def test_camera_modal_release_latch_and_deadzone(self):
        for flags in (1, 4):
            self.assertEqual(self.camera(flags=flags, stickX=80)[:3], [0, 0, 0])
        out = self.camera(flags=2, buttons=0x44, triggerL=255, stickX=80)
        self.assertEqual(out[:3], [0, 0, 0])
        self.assertEqual(out[8], 1)
        self.assertNotEqual(self.camera(flags=2, stickX=80)[0], 0)
        for x in range(-12, 13):
            for y in range(-12, 13):
                if x*x + y*y <= 144:
                    self.assertEqual(self.camera(stickX=x, stickY=y)[:3], [0, 0, 0])

    def test_radial_input_preserves_shallow_angles_in_all_quadrants(self):
        for x, y in ((1, 80), (11, 70), (30, 60), (60, 30), (80, 1)):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    mx, _, mz, *_ = self.camera(stickX=x*sx, stickY=y*sy)
                    self.assertNotEqual(mx, 0)
                    self.assertAlmostEqual(-mx/mz, x*sx/(y*sy), places=5)
                    look = self.camera(substickX=x*sx, substickY=y*sy)
                    self.assertAlmostEqual(-look[6]/look[7], x*sx/(y*sy), places=5)

    def test_radial_response_caps_diagonal_speed_and_eases_from_rest(self):
        for x, y in ((80, 0), (0, 80), (80, 80), (-128, 127)):
            out = self.camera(stickX=x, stickY=y, substickX=x, substickY=y)
            self.assertAlmostEqual(math.hypot(out[0], out[2]), 20, places=5)
            self.assertAlmostEqual(math.hypot(out[6], out[7]), .035, places=6)
        speeds = [self.camera(stickY=y)[2] / 20 for y in range(12, 81)]
        self.assertEqual(speeds[0], 0)
        self.assertLess(speeds[1], .001)
        self.assertAlmostEqual(speeds[-1], 1)
        self.assertTrue(all(a < b for a, b in zip(speeds, speeds[1:])))
        self.assertLess(speeds[17], .25)
        self.assertGreater(speeds[51], .75)
        self.assertEqual(self.camera(stickY=0)[:3], [0, 0, 0])

    def test_disconnected_controller_cannot_move_the_camera(self):
        self.assertEqual(self.camera(error=-1, stickY=80, triggerR=255)[:3], [0, 0, 0])

    def test_automated_spins_are_removed_but_wire_ids_stay_reserved(self):
        practice = (ROOT / "src/practice_session.cpp").read_text()
        main = (ROOT / "src/main.cpp").read_text()
        menu = (ROOT / "src/menu.cpp").read_text()
        binds = (ROOT / "include/susamune/binds_list.h").read_text()
        for token in ("requestSpin", "spinInput", "sSpinRemaining", "Queue clockwise spin"):
            self.assertNotIn(token, practice + main + menu)
        for token in ("BIND_PRACTICE_SPIN_CW", "BIND_PRACTICE_SPIN_CCW"):
            self.assertIn(token, binds)
            self.assertNotIn(token, main)


if __name__ == "__main__":
    unittest.main()
