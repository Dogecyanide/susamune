"""Exercise frozen retail pad history across real releases between steps."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class HeldInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            "void capturePad(", "void restorePad(", "void retainPausedReleases("))
        source = Path(cls.folder.name) / "held.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
extern "C" void *memcpy(void *dst,const void *src,size_t n) {
    for(size_t i=0;i<n;++i)((u8*)dst)[i]=((const u8*)src)[i];return dst;
}
struct Button {u32 mInput,mFrameInput,released;u8 rest[36];};
struct Stick {u8 rest[16];};
struct JUTGamePad {static Button mPadButton[1];static Stick mPadMStick[1],mPadSStick[1];};
Button JUTGamePad::mPadButton[1];Stick JUTGamePad::mPadMStick[1],JUTGamePad::mPadSStick[1];
struct TMarioGamePad {Button mButtons;Stick main,sub;u32 _A4;u8 prefix[40];
    u32 mMeaning,mFrameMeaning,_D8;u8 suffix[20];};
static_assert(sizeof(Button)==48,"retail buttons");
static_assert(sizeof(TMarioGamePad)==156,"retail captured ranges");
struct PadHistory {u8 shared[80],controls[80],meaning[0x4c];};
static PadHistory sBeforeRead;
static TMarioGamePad pad;
''' + functions + r'''
// These are retail's button/meaning edge equations for normal A/B input.
void read(u32 buttons) {
    Button &shared=JUTGamePad::mPadButton[0];
    shared.mFrameInput=buttons&~shared.mInput;
    shared.released=shared.mInput&~buttons;shared.mInput=buttons;
    pad.mButtons=shared;
    u32 meaning=((buttons&0x100)?0x80:0)|((buttons&0x200)?0x100:0);
    pad.mFrameMeaning=meaning&~pad.mMeaning;
    pad._D8=pad.mMeaning&~meaning;pad.mMeaning=meaning;
}
extern "C" __declspec(dllexport) void reset(u32 initial) {
    pad={};JUTGamePad::mPadButton[0]={};read(initial);
    pad.mFrameMeaning=pad._D8=0;capturePad(sBeforeRead,&pad);
}
extern "C" __declspec(dllexport) u32 frame(u32 buttons,u32 step,u32 oldHold) {
    capturePad(sBeforeRead,&pad);read(buttons);
    if(!step) {
        if(oldHold)restorePad(sBeforeRead,&pad);
        else retainPausedReleases(&pad);
        restorePad(sBeforeRead,&pad);
    }
    return pad.mFrameMeaning;
}
extern "C" __declspec(dllexport) u32 meanings() {return pad.mMeaning;}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_reproduces_old_release_then_repress_losing_jump(self):
        self.lib.reset(0x100)
        self.lib.frame(0, 0, 1)
        self.lib.frame(0x100, 0, 1)
        self.assertEqual(self.lib.frame(0x100, 1, 1), 0)

    def test_release_between_steps_rearms_jump_without_an_empty_step(self):
        for wait in (1, 2, 30, 300):
            self.lib.reset(0x100)
            self.lib.frame(0, 0, 0)
            for _ in range(wait):
                self.assertEqual(self.lib.frame(0x100, 0, 0), 0)
            self.assertEqual(self.lib.frame(0x100, 1, 0), 0x80)

    def test_continuous_hold_is_not_repeated_as_a_new_jump_each_step(self):
        self.lib.reset(0)
        self.assertEqual(self.lib.frame(0x100, 1, 0), 0x80)
        for _ in range(20):
            self.lib.frame(0x100, 0, 0)
            self.assertEqual(self.lib.frame(0x100, 1, 0), 0)

    def test_tap_released_before_step_is_not_a_sticky_queued_input(self):
        self.lib.reset(0)
        self.lib.frame(0x100, 0, 0)
        self.lib.frame(0, 0, 0)
        self.assertEqual(self.lib.frame(0, 1, 0), 0)
        self.assertEqual(self.lib.meanings(), 0)

    def test_releasing_one_button_does_not_rearm_another_held_button(self):
        self.lib.reset(0x300)
        self.lib.frame(0x200, 0, 0)
        self.lib.frame(0x300, 0, 0)
        self.assertEqual(self.lib.frame(0x300, 1, 0), 0x80)
        self.assertEqual(self.lib.meanings(), 0x180)

    def test_live_playback_does_not_rewrite_frozen_history(self):
        self.lib.reset(0)
        self.assertEqual(self.lib.frame(0x100, 1, 0), 0x80)
        self.assertEqual(self.lib.frame(0, 1, 0), 0)
        self.assertEqual(self.lib.frame(0x100, 1, 0), 0x80)


if __name__ == "__main__":
    unittest.main()
