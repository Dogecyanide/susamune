"""Check the actual presentation sampler and native gradient selection."""
import ctypes as C
import _ctypes
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class GradientMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-gradient-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        (folder / "Dolphin").mkdir()
        (folder / "Dolphin/types.h").write_text(
            "typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;")
        motion = (ROOT / "src/gradient_motion.cpp").read_text()
        extras = (ROOT / "src/creation_extras.cpp").read_text()
        code = r'''
#include "susamune/gradient_motion.hxx"
#include "susamune/susamune_cfg.h"
#define API extern "C" __declspec(dllexport)
enum SettingId {SETTING_QFT_GRADIENT_MOTION,SETTING_QFT_GRADIENT_SPEED,
 SETTING_NATIVE_GRADIENT_MOTION,SETTING_NATIVE_GRADIENT_SPEED,SETTING_NATIVE_VERTICAL_GRADIENT};
struct Settings {u8 values[5];u8 get(SettingId id){return values[id];}
 bool getBool(SettingId id){return get(id)!=0;}}gSettings;
unsigned long long now;
unsigned long long OSGetTime(){return now;}
#define OS_TIMER_CLOCK 40500000u
struct J2DPane{};
class CreationExtras {
public:
 u8 mColors[SUSAMUNE_CREATION_COLOR_COUNT][3];J2DPane*mHudPictures[32];
 bool nativeTimerGradient(const J2DPane*,u8[2][3])const;
}extras;
bool warning;bool rngControlInvalidatesIl(){return warning;}
'''
        code += motion[motion.index("namespace GradientMotion"):]
        code += "\n".join(function(extras, name) for name in (
            "nativeTimerColorSlot", "copyRgb", "CreationExtras::nativeTimerGradient"))
        code += r'''
API void sample(const u8*p,unsigned count,unsigned slot,unsigned mode,unsigned phase,u8*out){
 GradientMotion::sample((const u8(*)[3])p,count,slot,mode,phase,out);}
API unsigned clockPhase(unsigned speed,unsigned long long ticks){
 gSettings.values[1]=speed;now=ticks;return GradientMotion::phase(false);}
J2DPane panes[32];
API bool nativeGradient(unsigned pane,unsigned motion,unsigned vertical,unsigned invalid,u8*out){
 for(unsigned i=0;i<32;++i)extras.mHudPictures[i]=panes+i;
 for(unsigned i=0;i<SUSAMUNE_CREATION_COLOR_COUNT;++i)
  for(unsigned c=0;c<3;++c)extras.mColors[i][c]=i*7+c;
 gSettings.values[2]=motion;gSettings.values[3]=1;gSettings.values[4]=vertical;warning=invalid;now=40500000;
 return extras.nativeTimerGradient(panes+pane,(u8(*)[3])out);
}
'''
        cpp = folder / "fixture.cpp"
        cpp.write_text(code)
        dll = cpp.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-fno-builtin",
                        "-O2", "-I", str(folder), "-I", str(ROOT / "include"),
                        str(cpp), "-o", str(dll)], check=True, text=True,
                       env={**os.environ, "TEMP": str(folder), "TMP": str(folder)})
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.sample.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_void_p]
        cls.lib.clockPhase.argtypes = [C.c_uint, C.c_ulonglong]
        cls.lib.nativeGradient.argtypes = [C.c_uint, C.c_uint, C.c_uint, C.c_uint, C.c_void_p]
        cls.lib.nativeGradient.restype = C.c_bool

    def sample(self, palette, slot, mode, phase):
        source = bytes(c for color in palette for c in color)
        out = (C.c_ubyte * 3)()
        self.lib.sample(source, len(palette), slot, mode, phase, out)
        return tuple(out)

    def test_off_is_exact_and_does_not_modify_palette(self):
        palette = [(0, 7, 255), (83, 128, 240), (255, 0, 1)]
        for slot in range(3):
            for phase in (0, 1, 256, 512, 1023):
                self.assertEqual(self.sample(palette, slot, 0, phase), palette[slot])

    def test_flow_interpolates_and_closes_cycle_without_palette_loss(self):
        palette = [(255, 0, 0), (0, 0, 255)]
        self.assertEqual(self.sample(palette, 0, 1, 0), palette[0])
        self.assertEqual(self.sample(palette, 0, 1, 256), (128, 0, 128))
        self.assertEqual(self.sample(palette, 0, 1, 512), palette[1])
        self.assertLessEqual(max(abs(a - b) for a, b in zip(
            self.sample(palette, 0, 1, 1023), self.sample(palette, 0, 1, 0))), 1)

    def test_pulse_preserves_hues_and_chosen_brightness_ceiling(self):
        for phase, expected in ((0, (180, 90, 45)), (512, (240, 120, 60)), (1024, (180, 90, 45))):
            self.assertEqual(self.sample([(240, 120, 60)], 0, 2, phase), expected)

    def test_speed_is_wall_clock_and_wraps_at_eight_four_two_seconds(self):
        for speed, seconds in enumerate((8, 4, 2)):
            period = 40500000 * seconds
            self.assertEqual(self.lib.clockPhase(speed, 0), 0)
            self.assertIn(self.lib.clockPhase(speed, period // 2), (511, 512))
            self.assertEqual(self.lib.clockPhase(speed, period), 0)
            self.assertEqual(self.lib.clockPhase(speed, period * 1000000), 0)

    def test_native_scope_keeps_static_direction_and_excludes_label_background_warning(self):
        out = (C.c_ubyte * 6)()
        self.assertFalse(self.lib.nativeGradient(11, 0, 0, 0, out))
        self.assertTrue(self.lib.nativeGradient(11, 0, 1, 0, out))
        self.assertEqual(tuple(out), (63, 64, 65, 98, 99, 100))
        for motion in (1, 2):
            self.assertTrue(self.lib.nativeGradient(11, motion, 0, 0, out))
            self.assertEqual(tuple(out[:3]), tuple(out[3:]))
            self.assertFalse(self.lib.nativeGradient(24, motion, 1, 0, out))
            self.assertFalse(self.lib.nativeGradient(0, motion, 1, 0, out))
            self.assertFalse(self.lib.nativeGradient(11, motion, 1, 1, out))


if __name__ == "__main__":
    unittest.main()
