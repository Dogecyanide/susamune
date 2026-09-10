"""Exercise the production audio reconciliation around retained JAudio state."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/savestate.cpp"


class SavestatePauseAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = r'''
typedef unsigned char u8;
struct TMarDirector {enum{STATE_NORMAL=4,STATE_PAUSE_MENU=5};u8 mCurState,mDemoState;};
static TMarDirector director,*gpMarDirector;
static unsigned ons,offs,lastArg;
static unsigned volumes[9];
struct Sound {
 void pauseOn(bool sound){++ons;lastArg=sound;for(unsigned i=0;i<9;++i)if(i!=4)volumes[i]=0;}
 void pauseOff(u8 sound){++offs;lastArg=sound;for(unsigned i=0;i<9;++i)if(i!=4)volumes[i]=1;}
};
static Sound sound,*gpMSound;
''' + function_source(SOURCE, "void reconcilePauseAudio(") + r'''
#define API extern "C" __declspec(dllexport)
API void run(unsigned oldState,unsigned state,unsigned demo,unsigned present){
 director.mCurState=(u8)state;director.mDemoState=(u8)demo;
 gpMarDirector=present&1?&director:0;gpMSound=present&2?&sound:0;
 ons=offs=lastArg=0;
 for(unsigned i=0;i<9;++i)volumes[i]=(oldState==5&&i!=4)?0:1;
 reconcilePauseAudio((u8)oldState);
}
API unsigned result(unsigned key){return key==0?ons:key==1?offs:key==2?lastArg:volumes[key-3]!=0;}
'''
        path = Path(cls.temp.name) / "audio.cpp"
        path.write_text(source, encoding="ascii")
        library = path.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(path), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_gameplay_load_from_retail_pause_restores_effects_without_pause_chime(self):
        self.lib.run(5, 4, 0, 3)
        self.assertEqual([self.lib.result(i) for i in range(3)], [0, 1, 2])
        self.assertEqual([self.lib.result(i) for i in range(3, 12)], [1] * 9)

    def test_saved_retail_pause_stays_silent_and_normal_unpause_can_resume(self):
        self.lib.run(4, 5, 0, 3)
        self.assertEqual([self.lib.result(i) for i in range(3)], [1, 0, 0])
        self.assertEqual([self.lib.result(i) for i in range(3, 12)], [0, 0, 0, 0, 1, 0, 0, 0, 0])
        self.lib.run(5, 5, 0, 3)
        self.assertEqual([self.lib.result(i) for i in range(3)], [0, 0, 0])

    def test_unrelated_gameplay_demo_and_borrowed_holds_do_not_change_audio(self):
        for old, new, demo in [(4, 4, 0), (12, 4, 0), (4, 12, 0),
                               (5, 4, 1), (5, 2, 0), (5, 3, 0),
                               (5, 7, 0), (5, 9, 0), (5, 10, 0)]:
            with self.subTest(old=old, new=new, demo=demo):
                self.lib.run(old, new, demo, 3)
                self.assertEqual([self.lib.result(i) for i in range(2)], [0, 0])
        for present in range(3):
            self.lib.run(5, 4, 0, present)
            self.assertEqual([self.lib.result(i) for i in range(2)], [0, 0])

    def test_only_successful_restore_reconciles_after_audio_interrupts_resume(self):
        load = function_source(SOURCE, "bool SavestateManager::loadSlot(u32 slot,")
        capture = load.index("const u8 previousDirectorState")
        self.assertLess(capture, load.index("gpMSound->stopAllSound();"))
        call = load.index("reconcilePauseAudio(previousDirectorState);")
        self.assertGreater(call, load.rindex("OSRestoreInterrupts(ints);"))
        self.assertGreater(call, load.index("if (restored != StateCodec::SUCCESS)"))
        self.assertEqual(load.count("reconcilePauseAudio("), 1)
        save = function_source(SOURCE, "bool SavestateManager::saveSlotExplicit(")
        self.assertNotIn("reconcilePauseAudio", save)


if __name__ == "__main__":
    unittest.main()
