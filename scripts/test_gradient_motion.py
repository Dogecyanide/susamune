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
namespace NativeHudPrecision {unsigned count=6;bool extra;unsigned normalDigits(){return count;}bool extraDigit(){return extra;}}
class CreationExtras {
public:
 u8 mNativeGradient;u8 mColors[SUSAMUNE_CREATION_COLOR_COUNT][3];J2DPane*mHudPictures[32];
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
API unsigned wordMode(unsigned options){return GradientMotion::wordMotion(options);}
API unsigned setWordMode(unsigned options,unsigned mode){return GradientMotion::withWordMotion(options,mode);}
API unsigned wordStops(unsigned options){return GradientMotion::wordStops(options);}
API unsigned wordSpeed(unsigned options){return GradientMotion::wordSpeed(options);}
J2DPane panes[32];
API void precision(unsigned count,unsigned extra,unsigned stops){NativeHudPrecision::count=count;NativeHudPrecision::extra=extra;extras.mNativeGradient=stops;}
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

    def setUp(self):
        self.lib.precision(6, 0, 0)

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

    def test_ping_pong_returns_along_the_same_palette(self):
        palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        self.assertEqual(self.sample(palette, 0, 3, 0), palette[0])
        self.assertEqual(self.sample(palette, 0, 3, 256), palette[1])
        self.assertEqual(self.sample(palette, 0, 3, 512), palette[2])
        for phase in (1, 127, 255, 400, 511):
            self.assertEqual(self.sample(palette, 1, 3, phase), self.sample(palette, 1, 3, 1024 - phase))

    def test_wave_moves_brightness_without_changing_palette_hues(self):
        palette = [(240, 120, 60)] * 4
        self.assertEqual(self.sample(palette, 0, 4, 0), (150, 75, 37))
        self.assertEqual(self.sample(palette, 2, 4, 0), palette[2])
        for phase in (0, 127, 512, 1023):
            self.assertEqual(self.sample(palette, 1, 4, phase), self.sample(palette, 0, 4, phase + 256))

    def test_custom_word_modes_preserve_stops_and_speed(self):
        for stops in range(6):
            for speed in range(3):
                options = stops | (speed << 5)
                for mode in range(10):
                    result = self.lib.setWordMode(options, mode)
                    self.assertEqual(self.lib.wordMode(result), mode)
                    self.assertEqual(self.lib.wordStops(result), stops)
                    self.assertEqual(self.lib.wordSpeed(result), speed)
                    self.assertEqual(self.lib.setWordMode(result, 0), options)

    def test_speed_is_wall_clock_and_wraps_at_eight_four_two_seconds(self):
        for speed, seconds in enumerate((8, 4, 2)):
            period = 40500000 * seconds
            self.assertEqual(self.lib.clockPhase(speed, 0), 0)
            self.assertIn(self.lib.clockPhase(speed, period // 2), (511, 512))
            self.assertEqual(self.lib.clockPhase(speed, period), 0)
            self.assertEqual(self.lib.clockPhase(speed, period * 1000000), 0)

    def test_shimmer_is_a_travelling_highlight_over_the_chosen_palette(self):
        palette = [(120, 40, 0)] * 6
        self.assertEqual(self.sample(palette, 0, 5, 0), palette[0])
        self.assertEqual(self.sample(palette, 0, 5, 128), (221, 201, 191))
        self.assertEqual(self.sample(palette, 3, 5, 128), palette[3])
        self.assertEqual(self.sample(palette, 3, 5, 512), (221, 201, 191))

    def test_steps_holds_whole_palette_colours_between_discrete_changes(self):
        palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        for phase in (0, 100, 255):
            self.assertEqual(self.sample(palette, 0, 6, phase), palette[0])
        self.assertEqual(self.sample(palette, 0, 6, 256), palette[1])
        self.assertEqual(self.sample(palette, 3, 6, 256), palette[0])

    def test_new_modes_are_bounded_distinct_and_never_mutate_palette(self):
        palette = [(120, 40, 15)] * 9
        signatures = []
        for mode in (7, 8, 9):
            samples = [self.sample(palette, slot, mode, phase)
                       for phase in range(0, 1024, 16) for slot in range(9)]
            self.assertTrue(all(0 <= channel <= 255 for value in samples for channel in value))
            self.assertGreater(len(set(samples)), 3)
            signatures.append(samples)
        self.assertNotEqual(signatures[0], signatures[1])
        self.assertNotEqual(signatures[1], signatures[2])

    def test_three_decimal_gradient_reaches_endpoint_only_on_extra_digit(self):
        out = (C.c_ubyte * 6)()
        for stops in range(1, 6):
            self.lib.precision(7, 0, stops)
            self.assertTrue(self.lib.nativeGradient(11, 0, 0, 0, out))
            self.assertEqual(tuple(out), (63, 64, 65) * 2)
            self.assertTrue(self.lib.nativeGradient(16, 0, 0, 0, out))
            self.assertEqual(tuple(out), (92, 93, 94) * 2)
            self.lib.precision(7, 1, stops)
            self.assertTrue(self.lib.nativeGradient(16, 0, 0, 0, out))
            self.assertEqual(tuple(out), (98, 99, 100) * 2)
        self.lib.precision(7, 0, 0)
        self.assertFalse(self.lib.nativeGradient(16, 0, 0, 0, out))
        self.lib.precision(6, 0, 5)
        self.assertFalse(self.lib.nativeGradient(16, 0, 0, 0, out))

    def test_three_decimal_motion_uses_distinct_last_two_positions_and_preserves_countdown(self):
        out = (C.c_ubyte * 6)()
        for motion in (1, 2, 3, 4):
            self.lib.precision(6, 0, 5)
            self.assertTrue(self.lib.nativeGradient(20, motion, 0, 0, out))
            countdown = tuple(out)
            self.lib.precision(7, 0, 5)
            self.assertTrue(self.lib.nativeGradient(20, motion, 0, 0, out))
            self.assertEqual(tuple(out), countdown)
            self.assertTrue(self.lib.nativeGradient(16, motion, 0, 0, out))
            second_decimal = tuple(out)
            self.lib.precision(7, 1, 5)
            self.assertTrue(self.lib.nativeGradient(16, motion, 0, 0, out))
            self.assertNotEqual(tuple(out), second_decimal)
        self.lib.precision(7, 1, 5)
        self.assertTrue(self.lib.nativeGradient(16, 0, 1, 0, out))
        self.assertEqual(tuple(out), (63, 64, 65, 98, 99, 100))

    def test_native_scope_keeps_static_direction_and_excludes_label_background_warning(self):
        out = (C.c_ubyte * 6)()
        self.assertFalse(self.lib.nativeGradient(11, 0, 0, 0, out))
        self.assertTrue(self.lib.nativeGradient(11, 0, 1, 0, out))
        self.assertEqual(tuple(out), (63, 64, 65, 98, 99, 100))
        for motion in (1, 2, 3, 4):
            self.assertTrue(self.lib.nativeGradient(11, motion, 0, 0, out))
            self.assertEqual(tuple(out[:3]), tuple(out[3:]))
            self.assertFalse(self.lib.nativeGradient(24, motion, 1, 0, out))
            self.assertFalse(self.lib.nativeGradient(0, motion, 1, 0, out))
            self.assertFalse(self.lib.nativeGradient(11, motion, 1, 1, out))


if __name__ == "__main__":
    unittest.main()
