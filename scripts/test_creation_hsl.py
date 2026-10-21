"""Exercise HSL conversion and the production Creation editor input path."""

import ctypes as C
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class CreationHslTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-hsl-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;",
            encoding="ascii")
        creation = (ROOT / "src/creation.cpp").read_text()
        color = (ROOT / "src/creation_color.cpp").read_text()
        layout = (ROOT / "src/layout_editor.cpp").read_text()
        code = r'''
#define private public
#include "susamune/creation.hxx"
#include "susamune/creation_color.hxx"
#undef private
#define API extern "C" __declspec(dllexport)
extern "C" void *memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
class Menu {}; Menu *gMenu;
namespace NumberEditor { const void *owner; unsigned low, high, pending, commit;
 bool active(const void *who){return owner==who;}void cancel(const void *who){if(owner==who)owner=0;}
 void begin(const void *who,const char*,unsigned value,unsigned lo,unsigned hi,const char*){owner=who;low=lo;high=hi;pending=value;commit=0;}
 int update(Menu*,unsigned *value){if(!commit)return 0;*value=pending;owner=0;return 1;}
}
enum SettingId { SETTING_QFT_VERTICAL_GRADIENT, SETTING_NATIVE_VERTICAL_GRADIENT,
 SETTING_QFT_GRADIENT_MOTION, SETTING_QFT_GRADIENT_SPEED,
 SETTING_NATIVE_GRADIENT_MOTION, SETTING_NATIVE_GRADIENT_SPEED };
struct Settings {u8 values[6];u8 get(SettingId id){return values[id];}
 void set(SettingId id,u8 v){values[id]=v;}
 void cycle(SettingId id,int dir){unsigned n=id<2?2:3;values[id]=(values[id]+n+dir)%n;}}gSettings;
struct TMarioGamePad {
 enum{A=1,B=2,X=4,Y=8,Z=16,START=32,L=64,R=128,DPAD_LEFT=256,DPAD_RIGHT=512,
 DPAD_UP=1024,DPAD_DOWN=2048,CSTICK_LEFT=4096,CSTICK_RIGHT=8192,CSTICK_UP=16384,CSTICK_DOWN=32768};
 struct{u32 mInput,mFrameInput,mRapidInput;}mButtons;
};
'''
        code += re.sub(r"^#include[^\n]*", "", color, flags=re.M)
        code += creation[creation.index("enum EditOption"):creation.index("inline int clampi")]
        code += function(creation, "clampi")
        code += "namespace LayoutEditor {" + function(layout, "updatePositionScale") + "}\n"
        code += "\n".join(function(creation, name) for name in (
            "textChannel", "adjustTextChannel", "gradientRange", "applyGradient", "resetOption", "CreationEditor::reset",
            "CreationEditor::begin", "CreationEditor::setScaleLimits", "gradientSetting", "CreationEditor::setGradientDirectionSetting", "CreationEditor::optionEnabled", "CreationEditor::moveOption",
            "CreationEditor::repeatInput", "CreationEditor::update"))
        code += r'''
CreationEditor editor;
CreationStyle style,defaults;
u16 custom;
const u8 white[1][3]={{255,255,255}};
API void begin(u8*rgb,u8*backup,unsigned count,const u8*background,int modes){
 editor.reset();style={91,72,100,217,background[0],background[1],background[2],127,100,255};
 defaults=style;custom=0;
 unsigned caps=CreationEditor::CAP_ALL;
 if(modes)caps|=CreationEditor::CAP_COLOR_MODE;
 if(modes==2)caps|=CreationEditor::CAP_RGB_ENABLES_CUSTOM;
 editor.begin(&style,(u8(*)[3])rgb,(u8(*)[3])backup,count,count,0,caps,modes?&custom:0);
}
API unsigned editing(){return editor.editing();}
API void target(unsigned slot){editor.selectTarget(slot);}
API unsigned adjust(unsigned option,int direction,unsigned fine){
 editor.mOption=(u8)option;TMarioGamePad pad={};
 pad.mButtons.mInput=pad.mButtons.mFrameInput=direction<0?TMarioGamePad::CSTICK_LEFT:TMarioGamePad::CSTICK_RIGHT;
 if(fine)pad.mButtons.mInput|=TMarioGamePad::Y;
 return editor.update(&pad,defaults,white);
}
API unsigned finish(unsigned keep){
 TMarioGamePad pad={};pad.mButtons.mRapidInput=keep?TMarioGamePad::A:TMarioGamePad::B;
 editor.update(&pad,defaults,white);pad.mButtons.mRapidInput=TMarioGamePad::A;
 return editor.update(&pad,defaults,white);
}
API void resetOptionAt(unsigned option){
 editor.mOption=(u8)option;TMarioGamePad pad={};pad.mButtons.mRapidInput=TMarioGamePad::Z;
 editor.update(&pad,defaults,white);pad.mButtons.mRapidInput=TMarioGamePad::A;
 editor.update(&pad,defaults,white);
}
API unsigned mode(){return custom;}
API void enableDirection(unsigned initial){gSettings.values[0]=initial;editor.setGradientDirectionSetting(0);}
API unsigned direction(){return gSettings.values[0];}
API unsigned directionAvailable(){return editor.optionEnabled(OPTION_GRADIENT_DIRECTION);}
API unsigned enableMotion(unsigned native,unsigned motion,unsigned speed){
 gSettings.values[2+native*2]=motion;gSettings.values[3+native*2]=speed;
 editor.setGradientDirectionSetting(native?SETTING_NATIVE_VERTICAL_GRADIENT:SETTING_QFT_VERTICAL_GRADIENT);
 return editor.optionEnabled(OPTION_GRADIENT_MOTION)&&editor.optionEnabled(OPTION_GRADIENT_SPEED);
}
API unsigned motion(unsigned native,unsigned speed){return gSettings.values[2+native*2+speed];}
API unsigned motionAvailable(){return editor.optionEnabled(OPTION_GRADIENT_MOTION);}
API unsigned sizeEntry(unsigned low,unsigned high,unsigned value){
 editor.setScaleLimits(low,high);TMarioGamePad pad={};
 pad.mButtons.mInput=TMarioGamePad::X;editor.update(&pad,defaults,white);
 if(NumberEditor::active(&editor))return 0;
 pad.mButtons.mInput=TMarioGamePad::X|TMarioGamePad::START;pad.mButtons.mRapidInput=TMarioGamePad::START;
 editor.update(&pad,defaults,white);if(NumberEditor::active(&editor))return 0;
 pad.mButtons.mInput=TMarioGamePad::X|TMarioGamePad::A;pad.mButtons.mRapidInput=TMarioGamePad::A;
 editor.update(&pad,defaults,white);
 if(!NumberEditor::active(&editor)||NumberEditor::low!=low||NumberEditor::high!=high)return 0;
 NumberEditor::pending=value;NumberEditor::commit=1;pad={};editor.update(&pad,defaults,white);
 return style.scale;
}
API unsigned sizeStep(unsigned low,unsigned high,unsigned current,int delta){
 editor.setScaleLimits(low,high);style.scale=current;TMarioGamePad pad={};
 pad.mButtons.mInput=pad.mButtons.mFrameInput=delta<0?TMarioGamePad::L:TMarioGamePad::R;
 editor.update(&pad,defaults,white);return style.scale;
}
API unsigned moveOption(int direction){editor.moveOption(direction);return editor.mOption;}
API void selectOption(unsigned option){editor.mOption=(u8)option;}
API unsigned preset(){return sGradientPreset;}
API void enableGradient(unsigned timer,unsigned visible){
 editor.mCapabilities|=CreationEditor::CAP_GRADIENT;
 if(timer)editor.mCapabilities|=CreationEditor::CAP_TIMER_GRADIENT;
 if(visible&&visible<editor.mTargetSlots)editor.mTargetSlots=visible;
}
API unsigned value(unsigned slot,unsigned channel){return sHsl[slot].channel[channel];}
API unsigned background(unsigned channel){return (&style.bgR)[channel];}
API unsigned alpha(){return style.textA;}
API unsigned mixed(unsigned channel){u16 out;return !textChannel(editor.mTextRgb,editor.mTextSlots,editor.mTextTarget,channel,&out);}
API void fromRgb(const u8*rgb,u16*out){const auto hsl=CreationColor::fromRgb(rgb);for(int i=0;i<3;i++)out[i]=hsl.channel[i];}
API unsigned roundtripAllRgb(){
 for(unsigned r=0;r<256;r++)for(unsigned g=0;g<256;g++)for(unsigned b=0;b<256;b++){
  u8 rgb[3]={(u8)r,(u8)g,(u8)b},back[3];
  CreationColor::toRgb(CreationColor::fromRgb(rgb),back);
  if(rgb[0]!=back[0]||rgb[1]!=back[1]||rgb[2]!=back[2])return 1+(r<<16)+(g<<8)+b;
 }
 return 0;
}
'''
        source = work / "fixture.cpp"
        source.write_text(code, encoding="ascii")
        dll = work / "fixture.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(work), "-I", str(ROOT / "include"), str(source), "-o", str(dll)],
                       check=True, env={**os.environ, "TEMP": str(work), "TMP": str(work)})
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)

    def begin(self, colors, background=(0, 0, 0), modes=0):
        self.rgb = (C.c_ubyte * (len(colors) * 3))(*(c for rgb in colors for c in rgb))
        self.backup = (C.c_ubyte * len(self.rgb))()
        bg = (C.c_ubyte * 3)(*background)
        self.lib.begin(self.rgb, self.backup, len(colors), bg, modes)

    def rgb_at(self, slot):
        return tuple(self.rgb[slot * 3:slot * 3 + 3])

    def hsl(self, slot):
        return tuple(self.lib.value(slot, channel) for channel in range(3))

    def adjust(self, option, amount, fine=True):
        step = 1 if fine else 4
        for _ in range(abs(amount) // step):
            self.lib.adjust(option, 1 if amount > 0 else -1, fine)

    def test_every_rgb_color_roundtrips_without_quantization_loss(self):
        self.assertEqual(self.lib.roundtripAllRgb(), 0)

    def test_named_colors_and_neutral_endpoints(self):
        for rgb, expected in (((255, 0, 0), (0, 10000, 5000)),
                              ((0, 255, 0), (12000, 10000, 5000)),
                              ((0, 0, 255), (24000, 10000, 5000)),
                              ((255, 255, 0), (6000, 10000, 5000)),
                              ((0, 255, 255), (18000, 10000, 5000)),
                              ((255, 0, 255), (30000, 10000, 5000)),
                              ((0, 0, 0), (0, 0, 0)), ((255, 255, 255), (0, 0, 10000))):
            with self.subTest(rgb=rgb):
                out = (C.c_ushort * 3)()
                self.lib.fromRgb((C.c_ubyte * 3)(*rgb), out)
                self.assertEqual(tuple(out), expected)

    def test_enter_select_mode_and_opacity_leave_existing_rgb_exact(self):
        colors = [(i, (i * 17) % 256, 255 - i) for i in range(16)]
        self.begin(colors, (19, 71, 221), modes=1)
        original = bytes(self.rgb)
        self.assertEqual(bytes(self.backup), original)
        self.lib.target(7)
        self.lib.adjust(10, 1, 0)
        self.lib.adjust(3, -1, 1)
        self.assertEqual(bytes(self.rgb), original)
        self.assertEqual(self.lib.alpha(), 216)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (19, 71, 221))

    def test_hue_wrap_coarse_fine_and_saturation_lightness_limits(self):
        self.begin([(255, 0, 0)])
        self.adjust(0, -1)
        self.assertEqual(self.hsl(0)[0], 35900)
        self.adjust(0, 4, fine=False)
        self.assertEqual(self.hsl(0)[0], 300)
        self.adjust(1, 4, fine=False)
        self.assertEqual(self.hsl(0)[1], 10000)
        self.adjust(1, -200, fine=False)
        self.assertEqual(self.hsl(0)[1], 0)
        self.adjust(2, 200, fine=False)
        self.assertEqual(self.hsl(0)[2], 10000)
        self.assertEqual(self.rgb_at(0), (255, 255, 255))
        self.adjust(2, -200, fine=False)
        self.assertEqual(self.rgb_at(0), (0, 0, 0))

    def test_black_white_and_grey_retain_hue_across_target_changes(self):
        for option, amount in ((2, 50), (2, -50), (1, -100)):
            with self.subTest(option=option, amount=amount):
                self.begin([(255, 0, 0), (0, 255, 0)])
                self.lib.target(1)
                self.adjust(option, amount)
                self.adjust(0, 240, fine=False)
                self.lib.target(2)
                self.adjust(0, 60, fine=False)
                self.lib.target(1)
                self.adjust(option, -amount)
                self.assertEqual(self.rgb_at(0), (0, 0, 255))
                self.assertEqual(self.rgb_at(1), (0, 255, 255))

    def test_many_inverse_edits_do_not_accumulate_rounding(self):
        colors = [(21, 94, 203), (213, 87, 117)]
        self.begin(colors)
        before = bytes(self.rgb)
        for slot in (1, 2):
            self.lib.target(slot)
            self.adjust(0, 360, fine=False)
            for _ in range(100):
                self.adjust(1, -1)
                self.adjust(1, 1)
                self.adjust(2, -1)
                self.adjust(2, 1)
        self.assertEqual(bytes(self.rgb), before)

    def test_all_changes_one_component_preserving_other_components_and_modes(self):
        self.begin([(255, 0, 0), (20, 40, 60)], modes=2)
        original = [self.hsl(i) for i in range(2)]
        self.assertTrue(self.lib.mixed(0))
        self.lib.adjust(0, 1, 0)
        self.assertEqual(self.lib.mode(), 3)
        for i in range(2):
            self.assertEqual(self.hsl(i), (400, original[i][1], original[i][2]))
        self.assertFalse(self.lib.mixed(0))
        self.assertTrue(self.lib.mixed(1))
        self.lib.target(2)
        self.lib.adjust(10, -1, 0)
        self.assertEqual(self.lib.mode(), 1)

    def test_background_has_independent_latent_hue_and_reset(self):
        self.begin([(17, 61, 202)], (0, 0, 255))
        original = bytes(self.rgb)
        self.adjust(7, 50)
        self.adjust(5, 120, fine=False)
        self.adjust(7, -50)
        self.assertEqual(tuple(self.lib.background(c) for c in range(4)), (255, 0, 0, 127))
        self.assertEqual(bytes(self.rgb), original)
        self.lib.resetOptionAt(5)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (0, 0, 255))

    def test_reset_one_hsl_component_and_cancel_restore_exact_rgb(self):
        self.begin([(24, 117, 201), (0, 255, 0)], (19, 29, 41), modes=2)
        original = bytes(self.rgb)
        self.lib.target(2)
        before = self.hsl(1)
        self.lib.resetOptionAt(0)
        self.assertEqual(self.hsl(1), (0, before[1], before[2]))
        self.assertEqual(self.rgb_at(1), (255, 0, 0))
        self.assertEqual(self.rgb_at(0), (24, 117, 201))
        self.assertEqual(self.lib.mode(), 2)
        self.lib.adjust(7, 1, 0)
        self.assertEqual(self.lib.finish(0), 6)
        self.assertEqual(bytes(self.rgb), original)
        self.assertEqual(self.lib.mode(), 0)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (19, 29, 41))

    def test_maximum_metadata_target_and_reject_over_capacity(self):
        self.begin([(0, 0, 255)] * 256)
        self.assertTrue(self.lib.editing())
        self.lib.target(256)
        self.adjust(0, 120, fine=False)
        self.assertEqual(self.rgb_at(254), (0, 0, 255))
        self.assertEqual(self.rgb_at(255), (255, 0, 0))
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (0, 0, 0))
        self.lib.finish(1)
        self.begin([(255, 255, 255)] * 257)
        self.assertFalse(self.lib.editing())

    def test_gradient_blends_custom_endpoints_and_preserves_unused_text_slots(self):
        self.begin([(255, 0, 0), (9, 9, 9), (0, 0, 255), (33, 44, 55)])
        self.lib.enableGradient(0, 3)
        self.lib.target(2)
        self.lib.adjust(11, -1, 0)  # One colour
        self.lib.adjust(11, -1, 0)  # Blend ends
        self.assertEqual(self.rgb_at(0), (255, 0, 0))
        self.assertEqual(self.rgb_at(1), (128, 0, 128))
        self.assertEqual(self.rgb_at(2), (0, 0, 255))
        self.assertEqual(self.rgb_at(3), (33, 44, 55))
        self.assertEqual(self.lib.finish(0), 6)
        self.assertEqual(self.rgb_at(1), (9, 9, 9))

    def test_gradient_presets_fill_and_reset_existing_colors(self):
        self.begin([(255, 255, 255)] * 9)
        self.lib.enableGradient(0, 9)
        self.lib.adjust(11, 1, 0)  # sunset
        self.assertEqual(self.rgb_at(0), (255, 180, 55))
        self.assertEqual(self.rgb_at(8), (210, 65, 170))
        self.lib.adjust(11, 1, 0)  # ocean
        self.assertEqual(self.rgb_at(0), (70, 245, 205))
        self.assertEqual(self.rgb_at(8), (85, 115, 255))
        self.lib.adjust(11, 1, 0)  # rainbow
        self.assertNotEqual(self.rgb_at(0), self.rgb_at(4))
        self.lib.adjust(11, 1, 0)  # blend original ends
        self.assertEqual(bytes(self.rgb), bytes([255] * 27))
        self.lib.adjust(11, 1, 0)  # solid
        self.assertTrue(all(self.rgb_at(i) == self.rgb_at(0) for i in range(9)))
        self.lib.resetOptionAt(11)
        self.assertEqual(bytes(self.rgb), bytes([255] * 27))

    def test_native_timer_gradient_maps_digit_groups_and_keeps_image_background(self):
        self.begin([(11, 22, 33)] * 15, modes=1)
        original = bytes(self.rgb)
        self.lib.enableGradient(1, 15)
        self.lib.adjust(11, 1, 0)
        self.assertEqual(self.rgb_at(0), self.rgb_at(6))
        self.assertEqual(self.rgb_at(5), self.rgb_at(9))
        self.assertEqual(self.rgb_at(13), (11, 22, 33))
        self.assertEqual(self.rgb_at(14), (11, 22, 33))
        self.assertEqual(self.rgb_at(10), tuple((a+b+1)//2 for a,b in zip(self.rgb_at(1), self.rgb_at(2))))
        self.assertEqual(self.lib.mode(), 0)
        self.lib.finish(0)
        self.assertEqual(bytes(self.rgb), original)

    def test_option_navigation_follows_visible_rows_and_presets_have_no_noop(self):
        self.begin([(255, 0, 0), (0, 0, 255)], modes=1)
        self.lib.enableGradient(0, 2)
        self.lib.selectOption(10)
        self.assertEqual([self.lib.moveOption(1) for _ in range(12)],
                         [11, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(self.lib.moveOption(-1), 9)
        for expected in (1, 2, 3, 4, 5, 1):
            self.assertTrue(self.lib.adjust(11, 1, 0) & 8)
            self.assertEqual(self.lib.preset(), expected)
        self.lib.adjust(11, -1, 0)
        self.assertEqual(self.lib.preset(), 5)
        self.assertEqual(self.rgb_at(0), (255, 0, 0))
        self.assertEqual(self.rgb_at(1), (255, 0, 0))

    def test_option_navigation_reaches_every_gradient_option_once(self):
        self.begin([(255, 0, 0), (0, 0, 255)], modes=1)
        self.lib.enableGradient(0, 2)
        self.lib.enableDirection(0)
        self.assertTrue(self.lib.motionAvailable())
        self.lib.selectOption(10)
        forward = [self.lib.moveOption(1) for _ in range(15)]
        self.assertEqual(forward, [11, 12, 13, 14, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        backward = [self.lib.moveOption(-1) for _ in range(15)]
        self.assertEqual(backward, forward[-2::-1] + [10])
        self.lib.finish(0)

    def test_vertical_direction_keep_cancel_reset_and_other_editor_isolation(self):
        self.begin([(255, 0, 0), (0, 0, 255)])
        self.lib.enableGradient(0, 2)
        self.lib.enableDirection(0)
        self.assertTrue(self.lib.directionAvailable())
        self.lib.selectOption(11)
        self.assertEqual(self.lib.moveOption(1), 12)
        self.lib.adjust(12, 1, 0)
        self.assertEqual(self.lib.direction(), 1)
        self.lib.finish(0)
        self.assertEqual(self.lib.direction(), 0)
        self.begin([(255, 0, 0), (0, 0, 255)])
        self.lib.enableDirection(1)
        self.lib.resetOptionAt(12)
        self.assertEqual(self.lib.direction(), 0)
        self.lib.finish(1)
        self.begin([(255, 255, 255)])
        self.assertFalse(self.lib.directionAvailable())

    def test_size_keypad_retains_previous_target_combo_and_owner_specific_bounds(self):
        self.begin([(255, 255, 255)] * 3)
        self.assertEqual(self.lib.sizeEntry(25, 150, 37), 37)
        self.assertEqual(self.lib.sizeStep(25, 150, 25, -1), 25)
        self.assertEqual(self.lib.sizeStep(25, 150, 25, 1), 27)
        self.assertEqual(self.lib.sizeStep(25, 150, 150, 1), 150)
        self.assertEqual(self.lib.sizeStep(50, 200, 200, 1), 200)

    def test_animation_controls_keep_cancel_reset_and_owner_isolation(self):
        for native in (0, 1):
            self.begin([(255, 0, 0), (0, 0, 255)])
            self.assertTrue(self.lib.enableMotion(native, 0, 1))
            self.lib.adjust(13, 1, 0)
            self.lib.adjust(14, 1, 0)
            self.assertEqual((self.lib.motion(native, 0), self.lib.motion(native, 1)), (1, 2))
            self.lib.finish(0)
            self.assertEqual((self.lib.motion(native, 0), self.lib.motion(native, 1)), (0, 1))
            self.begin([(255, 0, 0), (0, 0, 255)])
            self.lib.enableMotion(native, 1, 2)
            self.lib.adjust(13, 1, 0)
            self.lib.finish(1)
            self.assertEqual((self.lib.motion(native, 0), self.lib.motion(native, 1)), (2, 2))
            self.begin([(255, 0, 0), (0, 0, 255)])
            self.lib.enableMotion(native, 2, 2)
            self.lib.resetOptionAt(13)
            self.lib.resetOptionAt(14)
            self.assertEqual((self.lib.motion(native, 0), self.lib.motion(native, 1)), (0, 1))
            self.lib.finish(1)
        self.begin([(255, 255, 255)])
        self.assertFalse(self.lib.motionAvailable())


if __name__ == "__main__":
    unittest.main()
