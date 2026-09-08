"""Run production editor, INI bounds and CARD migration code on the host."""
import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    match = re.search(r"(?:^|\n)[^\n]*\b" + re.escape(name) + r"\([^;]*?\)\s*(?:const\s*)?\{", source)
    if not match:
        raise AssertionError(name)
    start = source.index("{", match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


class NativeTimerCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-native-style-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "typedef unsigned char u8; typedef signed char s8; typedef unsigned short u16;"
            "typedef short s16; typedef unsigned u32; typedef int s32;", encoding="ascii")
        kernel = (ROOT / "launcher/kernel/SusamuneCfg.c").read_text()
        persistence = (ROOT / "src/emulator_persistence.cpp").read_text()
        creation = (ROOT / "src/creation.cpp").read_text()
        extras = (ROOT / "src/creation_extras.cpp").read_text()
        layout = (ROOT / "src/layout_editor.cpp").read_text()
        prelude = r'''
#include "susamune/susamune_cfg.h"
#define private public
#include "susamune/creation.hxx"
#include "susamune/creation_extras.hxx"
#undef private
#define SUSAMUNE_GAME_VERSION 1
#define API extern "C" __declspec(dllexport)
extern "C" void *memset(void *p,int v,unsigned long long n) {u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void *d,const void*s,unsigned long long n) {u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
int strcmp(const char*a,const char*b) {while(*a&&*a==*b){a++;b++;}return (unsigned char)*a-(unsigned char)*b;}
struct TMarioGamePad {
 enum { A=1,B=2,X=4,Y=8,Z=16,START=32,L=64,R=128,DPAD_LEFT=256,DPAD_RIGHT=512,
 DPAD_UP=1024,DPAD_DOWN=2048,CSTICK_LEFT=4096,CSTICK_RIGHT=8192,CSTICK_UP=16384,CSTICK_DOWN=32768 };
 struct {u32 mInput,mFrameInput,mRapidInput;} mButtons;
};
'''
        cfgfuncs = "\n".join(function(kernel, n) for n in (
            "ParseU16", "ParseQftU8", "ParseNativeTimerOffset", "ApplyNativeTimerStyleKey"))
        cfgfuncs += function(kernel, "ApplyNativeTimerModesKey")
        record = persistence[persistence.index("constexpr u32 kRecordMagic"):persistence.index("struct RecordV1")]
        persistfuncs = "\n".join(function(persistence, n) for n in (
            "initBlank", "checksum", "valid", "validV6", "migrateRecordV6"))
        enums = creation[creation.index("enum EditOption"):creation.index("inline int clampi")]
        editorfuncs = "\n".join(function(creation, n) for n in (
            "clampi", "adjustTextChannel", "resetOption", "CreationEditor::reset",
            "CreationEditor::begin", "CreationEditor::optionEnabled", "CreationEditor::moveOption",
            "CreationEditor::repeatInput", "CreationEditor::update"))
        layoutfunc = function(layout, "updatePositionScale")
        code = prelude + cfgfuncs + record + persistfuncs + enums
        code += function(creation, "clampi")
        code += "namespace LayoutEditor {" + layoutfunc + "}\n"
        # clampi already precedes the layout helper.
        code += editorfuncs[editorfuncs.index("\nvoid adjustTextChannel"):]
        code += "struct J2DPane {}; struct J2DPicture : J2DPane {}; bool warning; bool rngControlInvalidatesIl(){return warning;}\n"
        code += "\n".join(function(extras, n) for n in (
            "nativeTimerColorSlot", "clampStyle", "loadStyle", "storeStyle",
            "CreationExtras::adoptWallkick", "CreationExtras::stageWallkickInto",
            "CreationExtras::nativeTimerColorsEnabled", "CreationExtras::nativeTimerRgb"))
        code += r'''
API void parse(SusamuneNativeTimerStyleCfg *cfg,const char *key,const char *value) {
 ApplyNativeTimerStyleKey(cfg,key,value);
}
API int migration() {
 static Record old; memset(&old,0xA5,sizeof(old)); old.magic=kRecordMagic; old.version=6;
 old.payloadSize=kCfgSizeV6; old.gameVersion=1; old.cfg.magic=SUSAMUNE_CFG_MAGIC;
 old.cfg.version=SUSAMUNE_CFG_VERSION; old.cfg.flags=0x4000; old.checksum=checksum(&old);
 if(!validV6(&old)||valid(&old))return 1;
 static SusamuneCfg migrated; migrateRecordV6(&migrated,&old.cfg);
 const u8 *a=(const u8*)&old.cfg,*b=(const u8*)&migrated;
 for(unsigned i=0;i<kCfgSizeV6;i++)
  if(i<__builtin_offsetof(SusamuneCfg,flags)||i>=__builtin_offsetof(SusamuneCfg,flags)+4)
   if(a[i]!=b[i])return 2;
 for(unsigned i=kCfgSizeV6;i<sizeof(migrated);i++)if(b[i])return 3;
 if(migrated.flags!=(0x4000|SUSAMUNE_CFG_FLAG_NATIVE_TIMER_STYLE))return 4;
 old.cfg=migrated; old.version=kRecordVersion; old.payloadSize=sizeof(migrated);
 old.checksum=checksum(&old); if(!valid(&old)||validV6(&old))return 5;
 ((u8*)&old.cfg.nativeTimerStyle)[0]^=1; if(valid(&old))return 6;
 return 0;
}
API int editor(int test) {
 CreationEditor e; e.reset(); CreationStyle s={640,480,100,255,0,0,0,0,100,255};
 const CreationStyle original=s; u8 rgb[2][3]={{20,30,40},{20,30,40}},backup[2][3];
 const u8 defaults[2][3]={{255,255,255},{255,255,255}};
 e.begin(&s,rgb,backup,2,2,0,CreationEditor::CAP_ALL|CreationEditor::CAP_OFFSET_POSITION);
 TMarioGamePad p={};
 if(test==0||test==1){
  p.mButtons.mInput=TMarioGamePad::CSTICK_RIGHT|(test?TMarioGamePad::Y:0);
  p.mButtons.mFrameInput=TMarioGamePad::CSTICK_RIGHT;
  u8 result=e.update(&p,original,defaults,2);
  return rgb[0][0]==(test?21:24)&&rgb[1][0]==rgb[0][0]&&
   (result&CreationEditor::UPDATE_COLOR_CHANGED)?0:1;
 }
 if(test==2){
  p.mButtons.mRapidInput=TMarioGamePad::DPAD_RIGHT|TMarioGamePad::DPAD_DOWN;
  for(int i=0;i<700;i++)e.update(&p,original,defaults,2);
  if(s.x!=1280||s.y!=960)return 2;
  p.mButtons.mRapidInput=TMarioGamePad::DPAD_LEFT|TMarioGamePad::DPAD_UP;
  for(int i=0;i<700;i++)e.update(&p,original,defaults,2);
  return s.x||s.y?3:0;
 }
 p.mButtons.mInput=TMarioGamePad::CSTICK_RIGHT;
 e.update(&p,original,defaults,2);
 p.mButtons.mInput=0;p.mButtons.mRapidInput=TMarioGamePad::B;
 e.update(&p,original,defaults,2);
 p.mButtons.mRapidInput=TMarioGamePad::A;
 u8 result=e.update(&p,original,defaults,2);
 return e.editing()||rgb[0][0]!=20||!(result&CreationEditor::UPDATE_CANCELLED)?4:0;
}
API int modes(int test) {
 CreationEditor e; e.reset(); CreationStyle s={600,430,120,255,0,0,0,0,100,255};
 const CreationStyle original=s; u8 rgb[15][3],backup[15][3]; u16 custom=0x7fff;
 for(unsigned i=0;i<15;i++){rgb[i][0]=i+20;rgb[i][1]=30;rgb[i][2]=40;}
 e.begin(&s,rgb,backup,15,15,0,CreationEditor::CAP_ALL|CreationEditor::CAP_COLOR_MODE,&custom);
 TMarioGamePad p={};
 if(test==0){
  p.mButtons.mInput=p.mButtons.mFrameInput=TMarioGamePad::CSTICK_LEFT;
  if(!(e.update(&p,original,rgb,15)&CreationEditor::UPDATE_MODE_CHANGED)||custom)return 1;
  if(s.x!=600||s.y!=430||s.scale!=120||rgb[7][0]!=27)return 2;
  p.mButtons.mInput=p.mButtons.mFrameInput=TMarioGamePad::CSTICK_RIGHT;
  e.update(&p,original,rgb,15);
  return custom==0x7fff&&rgb[7][0]==27?0:3;
 }
 e.selectTarget(15);
 p.mButtons.mRapidInput=TMarioGamePad::Z;e.update(&p,original,rgb,15);
 p.mButtons.mRapidInput=TMarioGamePad::A;e.update(&p,original,rgb,15);
 if(custom!=0x3fff||rgb[14][0]!=34)return 4;
 if(test==1)return 0;
 if(test==2){
  p.mButtons.mRapidInput=TMarioGamePad::B;e.update(&p,original,rgb,15);
  p.mButtons.mRapidInput=TMarioGamePad::A;
  if(!(e.update(&p,original,rgb,15)&CreationEditor::UPDATE_CANCELLED))return 5;
  return custom==0x7fff?0:6;
 }
 p={};p.mButtons.mInput=p.mButtons.mFrameInput=TMarioGamePad::CSTICK_DOWN;
 e.update(&p,original,rgb,15);
 p.mButtons.mInput=p.mButtons.mFrameInput=TMarioGamePad::CSTICK_RIGHT;
 e.update(&p,original,rgb,15);
 return custom==0x7fff&&rgb[14][0]==38&&rgb[13][0]==33?0:7;
}
API int persistModes() {
 static CreationExtras extras;memset(&extras,0,sizeof(extras));
 SusamuneWallkickStyleCfg cfg={};cfg.magic=SUSAMUNE_WALLKICK_STYLE_MAGIC;cfg.version=2;
 extras.mNativeTimerCustomMask=0x4001;
 extras.adoptWallkick(&cfg);if(extras.mNativeTimerCustomMask!=0x4001)return 1;
 ApplyNativeTimerModesKey(&cfg,"native_timer_custom_mask","0");
 extras.adoptWallkick(&cfg);if(extras.mNativeTimerCustomMask)return 2;
 ApplyNativeTimerModesKey(&cfg,"native_timer_custom_mask","16385");
 extras.adoptWallkick(&cfg);if(extras.mNativeTimerCustomMask!=0x4001)return 3;
 const char *bad[]={"32768","65535","-1","9999999999999999",""};
 for(unsigned i=0;i<5;i++){
  ApplyNativeTimerModesKey(&cfg,"native_timer_custom_mask",bad[i]);
  if(cfg.nativeTimerCustomMask[0]!=64||cfg.nativeTimerCustomMask[1]!=1)return 4;
 }
 SusamuneWallkickStyleCfg saved={};extras.stageWallkickInto(&saved);
 if(saved.nativeTimerModesMagic!=SUSAMUNE_NATIVE_TIMER_MODES_MAGIC||
    saved.nativeTimerCustomMask[0]!=64||saved.nativeTimerCustomMask[1]!=1)return 5;
 extras.mNativeTimerCustomMask=0;extras.adoptWallkick(&saved);
 if(extras.mNativeTimerCustomMask!=0x4001)return 6;
 static J2DPicture pictures[25];
 for(unsigned i=0;i<25;i++)extras.mHudPictures[i]=pictures+i;
 for(unsigned i=0;i<15;i++){
  const u8 *rgb=extras.nativeTimerRgb(pictures+(i==14?0:i+11));
  if((rgb!=0)!=(i==0||i==14))return 7;
 }
 warning=true;if(extras.nativeTimerRgb(pictures))return 8;warning=false;
 saved.nativeTimerCustomMask[0]=0x80;extras.adoptWallkick(&saved);
 return extras.mNativeTimerCustomMask==0x4001?0:9;
}
'''
        source = work / "fixture.cpp"
        source.write_text(code, encoding="ascii")
        library = work / "fixture.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-I", str(work), "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))
        cls.dll.parse.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]

    def test_native_ini_partial_fields_and_bounds(self):
        class Style(ctypes.Structure):
            _fields_ = [("x", ctypes.c_uint16), ("y", ctypes.c_uint16),
                        ("scale", ctypes.c_uint8), ("alpha", ctypes.c_uint8),
                        ("brightness", ctypes.c_uint8), ("present", ctypes.c_uint8)]
        style = Style()
        self.dll.parse(ctypes.byref(style), b"native_timer_offset_x", b"-640")
        self.dll.parse(ctypes.byref(style), b"native_timer_offset_y", b"+480")
        self.assertEqual((style.x, style.y, style.present), (0, 960, 3))
        original = bytes(style)
        for key, value in (("offset_x", "641"), ("offset_y", "-481"), ("offset_x", "-"),
                           ("scale", "201"), ("scale", "49"), ("brightness", "24"),
                           ("alpha", "256"), ("offset_x", "9999999999999999")):
            self.dll.parse(ctypes.byref(style), ("native_timer_"+key).encode(), value.encode())
            self.assertEqual(bytes(style), original)
        for key, value in (("scale", "200"), ("alpha", "0"), ("brightness", "200")):
            self.dll.parse(ctypes.byref(style), ("native_timer_"+key).encode(), value.encode())
        self.assertEqual((style.scale, style.alpha, style.brightness, style.present), (200, 0, 200, 31))

    def test_v6_record_ignores_old_padding_and_v7_checksum_covers_new_tail(self):
        self.assertEqual(self.dll.migration(), 0)

    def test_shared_editor_normal_and_fine_steps_full_range_and_discard(self):
        for case in range(4):
            with self.subTest(case=case):
                self.assertEqual(self.dll.editor(case), 0)

    def test_original_custom_all_single_reset_and_cancel_keep_rgb_and_layout(self):
        for case in range(4):
            with self.subTest(case=case):
                self.assertEqual(self.dll.modes(case), 0)

    def test_mode_persistence_legacy_migration_validation_and_pane_selection(self):
        self.assertEqual(self.dll.persistModes(), 0)


if __name__ == "__main__":
    unittest.main()
