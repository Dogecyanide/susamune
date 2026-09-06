"""Exercise the retail transition gate used to catch the first playable tick."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class BufferedPauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            "bool actionableStage(", "bool activatePendingPause(",
            'extern "C" s32 susamunePracticeChangeState('))
        source = Path(cls.folder.name) / "buffer.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
struct TMarioGamePad {
    u8 prefix[0xe2];u16 flags;u32 padding;s32 _E8;
    struct { bool mDisable; } mState;
};
static_assert(__builtin_offsetof(TMarioGamePad,_E8)==0xe8,"retail pad gate offset");
struct TMarDirector {
    enum { STATE_NORMAL=4,STATE_STAGE_EXIT_2=12 };
    u32 mCurState,mGameState,mDemoState;
};
static TMarioGamePad pad;
static TMarDirector director;
static TMarDirector *gpMarDirector=&director;
struct TApplication { enum { CONTEXT_DIRECT_MAIN_LOOP=1 }; TMarioGamePad *mGamePads[1]; };
static TApplication gpApplication={{&pad}};
static TMarioGamePad *sReadPad;
static bool sHaveRead;
static u16 sBeforeRead;
void capturePad(u16 &out,TMarioGamePad *p) { out=p->flags; }
struct Mario { u32 mState; } mario;
static Mario *gpMarioOriginal=&mario;
static bool sPausePending,sPaused,sModal,sStepQueued,sFreeze,sBorrowedPause,transition;
static unsigned invalidations,retailCalls;
static s32 retailResult;
static u32 retailNext;
namespace Ghost {
static bool watching,frozen;
bool observerActive() { return watching; }
void frameControl(bool hold,bool) { frozen=hold; }
}
bool normalStage() { return director.mCurState==4; }
bool observerTransition() { return transition; }
void invalidate() { ++invalidations; }
void message(const char *) {}
s32 retailChange(TMarDirector *d) { ++retailCalls;d->mCurState=retailNext;return retailResult; }
static const size_t kChangeState=reinterpret_cast<size_t>(&retailChange);
''' + functions + r'''
extern "C" __declspec(dllexport) void reset(unsigned flags,int counter,unsigned state,
    unsigned game,unsigned marioState,unsigned demo,unsigned modes) {
    pad.flags=(u16)flags;pad._E8=counter;pad.mState.mDisable=modes&1;
    director.mCurState=state;director.mGameState=game;director.mDemoState=demo;
    mario.mState=marioState;sModal=modes&2;transition=modes&4;Ghost::watching=modes&8;
    sPausePending=true;sPaused=sFreeze=sBorrowedPause=Ghost::frozen=false;sStepQueued=true;
    invalidations=retailCalls=0;sHaveRead=false;sReadPad=0;sBeforeRead=0;
}
extern "C" __declspec(dllexport) unsigned ready(unsigned secondary) {
    return actionableStage(secondary!=0);
}
extern "C" __declspec(dllexport) unsigned activate(unsigned secondary) {
    return activatePendingPause(secondary!=0);
}
extern "C" __declspec(dllexport) int change(unsigned next,int result) {
    retailNext=next;retailResult=result;return susamunePracticeChangeState(&director);
}
extern "C" __declspec(dllexport) unsigned status() {
    return sPaused|(sPausePending<<1)|(sStepQueued<<2)|(sFreeze<<3)|
        (sBorrowedPause<<4)|(Ghost::frozen<<5)|(director.mCurState<<8)|
        (retailCalls<<16)|(invalidations<<24);
}
extern "C" __declspec(dllexport) unsigned savedPad() {
    return sHaveRead && sReadPad==&pad ? sBeforeRead : 0;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.status.restype = C.c_uint

    def reset(self, flags=2, counter=0, state=4, game=0, mario=0, demo=0, modes=0):
        self.lib.reset(flags, counter, state, game, mario, demo, modes)

    def test_raw_retail_gates_allow_neutral_input_but_reject_disabled_control(self):
        self.reset()
        self.assertEqual(self.lib.ready(0), 1)
        for blocked in (1, 8, 0x10, 0x80):
            self.reset(flags=2 | blocked)
            self.assertEqual(self.lib.ready(0), 0)
        for extra in (0x4, 0x20, 0x40, 0x100):
            self.reset(flags=2 | extra)
            self.assertEqual(self.lib.ready(0), 1)
        for args in ({"flags": 0}, {"mario": 0x1000}, {"demo": 1},
                     {"modes": 1}, {"modes": 4}, {"state": 2}):
            self.reset(**args)
            self.assertEqual(self.lib.ready(0), 0)

    def test_counter_anticipates_only_secondary_tick_decoding(self):
        for counter in (-1, 0, 1, 2):
            self.reset(counter=counter)
            self.assertEqual(self.lib.ready(0), counter <= 0)
            self.assertEqual(self.lib.ready(1), counter <= 1)

    def test_intro_finishing_mid_direct_holds_before_next_tick(self):
        self.reset(state=2)
        self.assertEqual(self.lib.activate(0), 0)
        self.assertEqual(self.lib.change(4, 1), 1)
        status = self.lib.status()
        self.assertEqual(status & 63, 57)  # paused, frozen, borrowed, ghosts held
        self.assertEqual((status >> 8) & 255, 12)
        self.assertEqual((status >> 16) & 255, 1)
        self.assertEqual(status >> 24, 1)
        self.assertEqual(self.lib.savedPad(), 2)
        self.lib.change(9, 4)
        self.assertEqual(self.lib.status(), status)  # no retail exit from borrowed 12

    def test_draw_boundary_does_not_anticipate_a_missing_pad_decode(self):
        self.reset(state=2, counter=1, game=0x4000)
        self.lib.change(4, 1)
        self.assertEqual(self.lib.status() & 63, 6)
        self.reset(state=2, counter=1, game=0)
        self.lib.change(4, 1)
        self.assertEqual(self.lib.status() & 63, 57)

    def test_menu_and_real_app_departure_leave_armed_request_pending(self):
        self.reset(state=2, modes=2)
        self.lib.change(4, 1)
        self.assertEqual(self.lib.status() & 63, 6)
        self.reset(state=2)
        self.lib.change(4, 4)
        self.assertEqual(self.lib.status() & 63, 6)


if __name__ == "__main__":
    unittest.main()
