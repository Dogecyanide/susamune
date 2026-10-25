"""Exercise the production speed editor's modal input and settings commits."""
import ctypes
from _ctypes import FreeLibrary
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
A, B, START = 0x100, 0x200, 0x1000
LEFT, RIGHT, DOWN, UP = 1, 2, 4, 8


class SpeedEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="speed-editor-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        folder = Path(cls.folder.name)
        stubs = folder / "include"
        (stubs / "susamune").mkdir(parents=True)
        (stubs / "JSystem/JUtility").mkdir(parents=True)
        (stubs / "susamune/menu.hxx").write_text('''
#pragma once
#include "Dolphin/types.h"
namespace JUtility { struct TColor { TColor(int,int,int,int) {} }; }
class Menu {
public:
    unsigned errors;
    void toast(const char *) { ++errors; }
    void fillBox(int,int,int,int,JUtility::TColor) {}
    void drawText(const char *,int,int,int,int,JUtility::TColor) {}
};
''')
        (stubs / "susamune/settings.hxx").write_text('''
#pragma once
#include "Dolphin/types.h"
enum { SETTING_GAMEPLAY_SPEED, SETTING_SLOWDOWN_PRESET };
struct Settings {
    u8 values[2];
    unsigned writes;
    u8 get(int id) const { return values[id]; }
    void set(int id,u8 v) { values[id]=v; ++writes; }
};
extern Settings gSettings;
''')
        (stubs / "JSystem/JUtility/JUTGamePad.hxx").write_text('''
#pragma once
#include "Dolphin/types.h"
class JUTGamePad {
public:
    enum { DPAD_LEFT=1, DPAD_RIGHT=2, DPAD_DOWN=4, DPAD_UP=8,
           Z=0x10, R=0x20, L=0x40, A=0x100, B=0x200, X=0x400,
           Y=0x800, START=0x1000 };
    struct Status { u16 mButton; };
    static Status mPadStatus[4];
};
''')
        wrapper = folder / "wrapper.cpp"
        wrapper.write_text('''
#include "susamune/menu.hxx"
#include "susamune/settings.hxx"
#include "JSystem/JUtility/JUTGamePad.hxx"
#include "susamune/gameplay_speed_editor.hxx"
#include "Dolphin/printf.h"
extern "C" int snprintf(char*,size_t,const char*,...){return 0;}
Settings gSettings;
JUTGamePad::Status JUTGamePad::mPadStatus[4];
Menu menu;
static int owners[2];
static unsigned number, numberResult;
extern "C" __declspec(dllexport) void begin(unsigned value,unsigned held) {
    GameplaySpeedEditor::cancel(&owners[0]);
    gSettings.values[0]=value;gSettings.values[1]=50;gSettings.writes=0;menu.errors=0;
    JUTGamePad::mPadStatus[0].mButton=held;
    GameplaySpeedEditor::begin(&owners[0]);
}
extern "C" __declspec(dllexport) void sample(unsigned held) {
    JUTGamePad::mPadStatus[0].mButton=held;
    GameplaySpeedEditor::update(&menu);
}
extern "C" __declspec(dllexport) void preset(unsigned speed, unsigned value) {
    GameplaySpeedEditor::cancel(&owners[0]);
    gSettings.values[0]=speed;gSettings.values[1]=value;gSettings.writes=0;menu.errors=0;
    JUTGamePad::mPadStatus[0].mButton=0;
    GameplaySpeedEditor::begin(&owners[0],true);
}
extern "C" __declspec(dllexport) unsigned state(unsigned index) {
    if(index==0) return gSettings.values[0];
    if(index==1) return gSettings.writes;
    if(index==2) return menu.errors;
    if(index==5) return gSettings.values[1];
    return GameplaySpeedEditor::active(&owners[index==3?0:1]);
}
extern "C" __declspec(dllexport) void numberBegin(unsigned value,unsigned low,unsigned high,unsigned held){
 JUTGamePad::mPadStatus[0].mButton=held;number=value;numberResult=0;
 NumberEditor::begin(&owners[0],"Number",value,low,high,"");
}
extern "C" __declspec(dllexport) int numberSample(unsigned held){
 JUTGamePad::mPadStatus[0].mButton=held;return NumberEditor::update(&menu,&number);
}
extern "C" __declspec(dllexport) unsigned numberValue(){return number;}
extern "C" __declspec(dllexport) void cancel(unsigned owner) {
    GameplaySpeedEditor::cancel(&owners[owner]);
}
''')
        from test_native_timer_creation import function
        menu_source = (ROOT / "src/menu.cpp").read_text()
        methods = "\n".join(function(menu_source, name) for name in (
            "beginTextEditor", "updateTextEditor", "parseFinishes"))
        with wrapper.open("a") as out:
            out.write(r'''
#include "susamune/raw_prompt_input.hxx"
extern "C" size_t strlen(const char *s){size_t n=0;while(s[n])++n;return n;}
namespace ILing {void formatTime(s32,char*,unsigned){}}
namespace StageTargets {void set(int,s32){}}
class StreakFixture { public:
 enum Editor {EDIT_NONE,EDIT_FINISHES,EDIT_TARGET};
 u16 mGoal; s32 mTargetQf; int mStreakEntry;char mText[32];u8 mTextLength,mTextCursor,mTextPage;
 bool mTextUpper;RawPromptInput mTextInput;Editor mEditor;
 static u16 keyboardMask(){return 0;}static bool parseTarget(const char*,s32*){return false;}
 void updateTimeKeyboard(u16){}
''' + methods + r'''
} streak;
extern "C" __declspec(dllexport) void streakBegin(unsigned count,unsigned held){
 streak.mGoal=count;JUTGamePad::mPadStatus[0].mButton=held;streak.beginTextEditor(StreakFixture::EDIT_FINISHES);
}
extern "C" __declspec(dllexport) unsigned streakSample(unsigned held){
 JUTGamePad::mPadStatus[0].mButton=held;streak.updateTextEditor(&menu);return streak.mGoal;
}
extern "C" __declspec(dllexport) unsigned streakActive(){return streak.mEditor!=StreakFixture::EDIT_NONE;}
''')
        library = folder / "editor.dll"
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            "-I", str(stubs), "-I", str(ROOT / "include"),
            str(ROOT / "src/gameplay_speed_editor.cpp"), str(wrapper), "-o", str(library),
        ], check=True, env={**os.environ, "TMP": str(folder), "TEMP": str(folder)})
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)

    def tap(self, button):
        self.dll.sample(button)
        self.dll.sample(0)

    def test_opening_button_must_be_released(self):
        self.dll.begin(50, A)
        self.dll.sample(A)
        self.assertEqual(self.dll.state(1), 0)
        self.assertEqual(self.dll.state(3), 1)
        self.dll.sample(0)
        self.tap(START)
        self.assertEqual(self.dll.state(0), 50)
        self.assertEqual(self.dll.state(3), 0)

    def test_numeric_edit_and_cancel_do_not_preview_settings(self):
        self.dll.begin(0, 0)
        self.tap(DOWN)  # 000
        self.tap(RIGHT)
        for _ in range(5):
            self.tap(UP)  # 050
        self.assertEqual(self.dll.state(1), 0)
        self.tap(A)
        self.assertEqual(self.dll.state(0), 50)
        self.assertEqual(self.dll.state(1), 1)
        self.dll.begin(50, 0)
        self.tap(RIGHT)
        self.tap(UP)
        self.tap(B)
        self.assertEqual(self.dll.state(0), 50)
        self.assertEqual(self.dll.state(1), 0)

    def test_range_limits_and_encoded_normal_speed(self):
        self.dll.begin(0, 0)
        self.tap(DOWN)  # 000 is invalid
        self.tap(A)
        self.assertEqual(self.dll.state(2), 1)
        self.assertEqual(self.dll.state(1), 0)
        self.assertEqual(self.dll.state(3), 1)
        self.tap(LEFT)
        self.tap(UP)  # 001
        self.tap(A)
        self.assertEqual(self.dll.state(0), 1)
        self.dll.begin(0, 0)
        self.tap(LEFT)
        self.tap(UP)  # 101 is invalid
        self.tap(A)
        self.assertEqual(self.dll.state(1), 0)
        self.assertEqual(self.dll.state(2), 1)
        self.tap(DOWN)  # 100 is encoded as zero
        self.tap(START)
        self.assertEqual(self.dll.state(0), 0)
        self.assertEqual(self.dll.state(1), 1)

    def test_modal_owner_and_focus_cancel(self):
        self.dll.begin(25, 0)
        self.assertEqual(self.dll.state(4), 0)
        self.dll.cancel(1)
        self.assertEqual(self.dll.state(3), 1)
        self.dll.cancel(0)
        self.assertEqual(self.dll.state(3), 0)
        self.tap(A)
        self.assertEqual(self.dll.state(1), 0)

    def test_preset_edit_leaves_active_speed_alone(self):
        for active_speed in (0, 25):
            self.dll.preset(active_speed, 50)
            self.tap(RIGHT)
            self.tap(UP)  # 060
            self.assertEqual(self.dll.state(1), 0)
            self.tap(A)
            self.assertEqual(self.dll.state(5), 60)
            self.assertEqual(self.dll.state(0), active_speed)
            self.assertEqual(self.dll.state(1), 1)

    def test_shared_numeric_entry_preserves_exact_scale_and_999_finish_goal(self):
        for value, low, high in ((37, 25, 150), (199, 50, 200), (999, 1, 999)):
            self.dll.numberBegin(value, low, high, A)
            self.assertEqual(self.dll.numberSample(A), 0)
            self.assertEqual(self.dll.numberSample(0), 0)
            self.assertEqual(self.dll.numberSample(A), 1)
            self.assertEqual(self.dll.numberValue(), value)
        self.dll.numberBegin(24, 25, 150, 0)
        self.assertEqual(self.dll.numberSample(A), 0)
        self.dll.numberSample(0)
        self.assertEqual(self.dll.numberSample(B), -1)
        self.assertEqual(self.dll.numberValue(), 24)

    def test_streak_finishes_menu_uses_numeric_owner_and_preserves_cancel(self):
        self.dll.streakBegin(5, A)
        self.assertEqual(self.dll.streakSample(A), 5)
        self.dll.streakSample(0)
        self.dll.streakSample(RIGHT)
        self.dll.streakSample(0)
        self.dll.streakSample(UP)
        self.dll.streakSample(0)
        self.assertEqual(self.dll.streakSample(START), 15)
        self.assertFalse(self.dll.streakActive())
        self.dll.streakBegin(999, 0)
        self.assertEqual(self.dll.streakSample(A), 999)
        self.assertFalse(self.dll.streakActive())
        self.dll.streakBegin(5, 0)
        self.dll.streakSample(UP)
        self.dll.streakSample(0)
        self.assertEqual(self.dll.streakSample(B), 5)
        self.assertFalse(self.dll.streakActive())


if __name__ == "__main__":
    unittest.main()
