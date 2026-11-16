"""Run the menu's real input wrapper and tab routing with held/stale inputs."""
import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class MenuButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        source = r'''
#include "susamune/menu_button_edges.hxx"
using u16=unsigned short;using u32=unsigned;
void *operator new(__SIZE_TYPE__,void*p){return p;}
struct JUTGamePad {enum{A=256,B=512,X=1024,Y=2048,Z=16,START=4096,L=64,R=32,
 DPAD_LEFT=1,DPAD_RIGHT=2,DPAD_DOWN=4,DPAD_UP=8};struct Status{u16 mButton;};static Status mPadStatus[1];};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad:JUTGamePad {enum{CSTICK_UP=65536,CSTICK_DOWN=131072,CSTICK_LEFT=262144,CSTICK_RIGHT=524288};
 struct{u32 mInput,mFrameInput,mRapidInput,_8;}mButtons;};
struct MenuTab{bool grabsInput(){return false;}}tab;
struct NestedMenuTab{};
struct MenuSoundsDisplayTab:MenuTab{u16 mPreviousButtons;MenuSoundsDisplayTab(NestedMenuTab*){}};
struct{char soundDisplay[32],displayHub[32];}sMenuRuntime;
static MenuButtonEdges sMenuButtons;
enum{BIND_MENU_SEARCH,SETTING_MENU_SOUNDS};
static bool chord,available;
struct{bool recording(){return false;}unsigned get(int){return 64|2048;}bool wasPressedRaw(int){return chord;}}gBinds;
struct{bool getBool(int){return false;}}gSettings;
namespace MenuSounds{struct Transition{bool a,b,c,d,e,f;u16 g;};int choose(Transition){return 0;}void play(int){}}
static unsigned actions,searches,changes,lastAction;
struct Menu {
 bool mShown=true;int mNumTabs=1,mCurTab=0;MenuTab*mTabs[1]={&tab};
 bool searchActive(){return false;}bool searchAvailable(){return available;}
 u32 soundState(){return mCurTab;}void switchTab(int d){mCurTab+=d;++changes;}
 void openSearch(){++searches;}
 bool searchShortcut(TMarioGamePad*);void updateWithSounds(TMarioGamePad*);
 void update(TMarioGamePad*p){if(searchShortcut(p))return;lastAction=p->mButtons.mRapidInput;if(lastAction&512)++actions;}
};
''' + function((ROOT / 'src/menu_sounds.inc').read_text(), 'void Menu::updateWithSounds(') + '\n' + function(
            (ROOT / 'src/menu_search.inc').read_text(), 'bool Menu::searchShortcut(') + r'''
static Menu menu;
#define API extern "C" __declspec(dllexport)
API void reset(){sMenuButtons={};menu.mCurTab=0;actions=searches=changes=lastAction=0;}
API unsigned frame(unsigned held,unsigned repeat,unsigned release,unsigned canSearch,unsigned open){
 JUTGamePad::mPadStatus[0].mButton=held;available=canSearch;chord=open;
 TMarioGamePad p={};p.mButtons.mRapidInput=repeat;p.mButtons.mFrameInput=repeat;p.mButtons._8=release;
 menu.updateWithSounds(&p);
 return p.mButtons.mRapidInput==repeat&&p.mButtons.mFrameInput==repeat&&p.mButtons._8==release;
}
API unsigned value(unsigned i){return i==0?actions:i==1?changes:i==2?searches:lastAction;}
'''
        cpp = Path(cls.temp.name) / 'buttons.cpp'
        cpp.write_text(source)
        dll = cpp.with_suffix('.dll')
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-std=c++17', '-O2', '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
            '-I', str(ROOT / 'include'), str(cpp), '-o', str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)

    def setUp(self):
        self.lib.reset()

    def frame(self, held, repeat=0, release=0, search=False, chord=False):
        self.assertTrue(self.lib.frame(held, repeat, release, search, chord))

    def test_stale_or_repeating_back_is_one_action_per_physical_press(self):
        for _ in range(60): self.frame(512, 512)
        self.assertEqual(self.lib.value(0), 1)
        self.frame(0, 512, 512)
        self.frame(0, 512, 512)
        self.assertEqual(self.lib.value(0), 1)
        self.frame(512, 512)
        self.assertEqual(self.lib.value(0), 2)

    def test_shoulders_never_repeat_or_act_on_press_and_release(self):
        for button in (32, 64):
            with self.subTest(button=button):
                self.lib.reset()
                self.frame(button, button, search=False)
                for _ in range(60): self.frame(button, button, search=True)
                for _ in range(3): self.frame(0, button, button, search=True)
                self.assertEqual(self.lib.value(1), 1)

    def test_search_shoulder_defers_once_and_chord_cancels_it(self):
        self.frame(64, 64, search=True)
        for _ in range(60): self.frame(64, 64, search=True)
        self.assertEqual(self.lib.value(1), 0)
        for _ in range(3): self.frame(0, 64, 64, search=True)
        self.assertEqual(self.lib.value(1), 1)
        self.frame(64, 64, search=True)
        self.frame(64 | 2048, search=True, chord=True)
        self.frame(0, 64, 64, search=True)
        self.assertEqual(self.lib.value(1), 1)
        self.assertEqual(self.lib.value(2), 1)

    def test_directional_repeat_survives_and_tab_change_consumes_actions(self):
        self.frame(0, 65536)
        self.assertEqual(self.lib.value(3), 65536)
        self.frame(32 | 512, 32 | 512)
        self.assertEqual(self.lib.value(0), 0)
        self.frame(512, 512)
        self.assertEqual(self.lib.value(0), 0)


if __name__ == '__main__': unittest.main()
