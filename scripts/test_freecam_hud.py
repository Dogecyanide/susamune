"""Exercise cinematic HUD visibility through production pause-screen guards."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class FreecamHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        functions = "\n".join(function_source(ROOT / "src/gameplay_polish.cpp", name)
                              for name in ("bool pauseOpen(", "void restoreConsoleDraw(",
                                           "void hideConsoleDraw(", "void restoreScreens(",
                                           "void hideScreens(", "void beforeDirect(",
                                           "void afterDirect("))
        after_draw = function_source(ROOT / "src/main.cpp", "void afterDraw(")
        start = after_draw.index("if (PracticeSession::hideHud())")
        opening = after_draw.index("{", start)
        depth, end = 1, opening + 1
        while depth:
            depth += (after_draw[end] == "{") - (after_draw[end] == "}")
            end += 1
        route = after_draw[start:end]
        assert after_draw.index("gMenu->draw(&ortho)") < start
        source = Path(cls.folder.name) / "hud.cpp"
        source.write_text(r'''
struct J2DScreen { bool mIsVisible; };
typedef J2DScreen J2DSetScreen;
struct TPauseMenu2 { enum { MENU_OPEN=1 }; int mState; J2DSetScreen *mScreen; };
typedef unsigned short u16;
struct TGCConsole2 { J2DScreen *mMainScreen; u16 mPerformFlags; };
typedef TGCConsole2 Console;
struct TMarDirector { enum { STATE_PAUSE_MENU=5 }; int mCurState;
    TPauseMenu2 *mPauseMenu; Console *mGCConsole; };
struct JUTGamePad { enum { Z=16 }; struct Pad { unsigned mButton; };
    static Pad mPadStatus[1]; };
JUTGamePad::Pad JUTGamePad::mPadStatus[1];
static J2DScreen hud,pause;
static TPauseMenu2 pauseMenu;
static Console console;
static TMarDirector director,*gpMarDirector;
static J2DScreen *sHiddenHud;
static J2DSetScreen *sHiddenPause;
static bool sHudWasVisible,sPauseWasVisible,sCleanPause,sZHeld,sCinemaHidden,cinema;
static TGCConsole2 *sHiddenConsole;
static u16 sConsolePerformFlags;
namespace PracticeSession { bool hideHud() { return cinema; } }
static unsigned drawBits;
static bool sessionModal,wheelShown,wheelPrompt;
static void *gMenu;
namespace StageLoader {
bool modal(){return sessionModal;}void draw(void*){drawBits|=2;}
}
namespace WarpWheel {
bool shown(){return wheelShown;}bool promptPending(){return wheelPrompt;}
void draw(){drawBits|=4;}
}
''' + functions + r'''
extern "C" __declspec(dllexport) void reset(unsigned visible,unsigned paused) {
    hud.mIsVisible=visible&1;pause.mIsVisible=visible&2;
    pauseMenu.mState=1;pauseMenu.mScreen=&pause;console.mMainScreen=&hud;
    director.mCurState=paused?5:4;director.mPauseMenu=&pauseMenu;
    director.mGCConsole=&console;gpMarDirector=&director;
    sHiddenHud=sHiddenPause=0;sCleanPause=sZHeld=sCinemaHidden=cinema=false;
    sHiddenConsole=0;console.mPerformFlags=0;
    JUTGamePad::mPadStatus[0].mButton=0;
}
extern "C" __declspec(dllexport) unsigned tick(unsigned hide,unsigned z,unsigned end) {
    cinema=hide!=0;JUTGamePad::mPadStatus[0].mButton=z?16:0;
    if(end)afterDirect();else beforeDirect();
    return hud.mIsVisible|(pause.mIsVisible<<1);
}
extern "C" __declspec(dllexport) unsigned cues(unsigned flags,unsigned hide,unsigned end) {
    if(!end)console.mPerformFlags=flags;
    tick(hide,0,end);
    return console.mPerformFlags;
}
extern "C" __declspec(dllexport) unsigned changedOwner() {
    Console replacement={&hud,0x420};
    console.mPerformFlags=0x200;
    tick(1,0,0);
    director.mGCConsole=&replacement;
    tick(1,0,1);
    unsigned result=replacement.mPerformFlags;
    director.mGCConsole=&console;
    return result;
}
void routeDraw(){drawBits=1;
''' + route + r'''
drawBits|=8;
}
extern "C" __declspec(dllexport) unsigned draw(unsigned hide,unsigned modal,
                                              unsigned wheel,unsigned prompt) {
    cinema=hide!=0;sessionModal=modal!=0;wheelShown=wheel!=0;wheelPrompt=prompt!=0;
    routeDraw();return drawBits;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_cinematic_capture_restores_exact_visibility_before_state_save(self):
        for visible in range(4):
            for paused in range(2):
                self.lib.reset(visible, paused)
                self.assertEqual(self.lib.tick(1, 0, 0), 0)
                self.assertEqual(self.lib.tick(1, 0, 1), visible)
                self.assertEqual(self.lib.tick(0, 0, 0), visible)

    def test_existing_Z_hide_survives_cinematic_toggle(self):
        self.lib.reset(3, 1)
        self.assertEqual(self.lib.tick(0, 1, 0), 0)
        self.assertEqual(self.lib.tick(0, 0, 1), 0)
        self.assertEqual(self.lib.tick(1, 0, 0), 0)
        self.lib.tick(1, 0, 1)
        self.assertEqual(self.lib.tick(0, 0, 0), 0)
        self.assertEqual(self.lib.tick(0, 1, 0), 3)

    def test_detached_console_drawing_is_filtered_and_exact_mask_restored(self):
        for flags in (0, 1, 2, 8, 0x200, 0x3000, 0xFFFF):
            for paused in range(2):
                self.lib.reset(3, paused)
                during = self.lib.cues(flags, 1, 0)
                self.assertEqual(during, flags | 8)
                self.assertEqual(0xFFFF & ~during, (0xFFFF & ~flags) & ~8)
                self.assertEqual(self.lib.cues(0, 1, 1), flags)
                self.assertEqual(self.lib.cues(flags, 0, 0), flags)

    def test_restoration_never_writes_a_replaced_console(self):
        self.lib.reset(3, 0)
        self.assertEqual(self.lib.changedOwner(), 0x420)

    def test_hidden_hud_keeps_interactive_prompts_and_wheel_drawn(self):
        for modal in range(2):
            for wheel in range(2):
                for prompt in range(2):
                    expected = 1 | (2 if modal else 0) | (4 if wheel or prompt else 0)
                    self.assertEqual(self.lib.draw(1, modal, wheel, prompt), expected)
        self.assertEqual(self.lib.draw(0, 0, 0, 0), 9)


if __name__ == "__main__":
    unittest.main()
