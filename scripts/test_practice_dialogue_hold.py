"""Practice holds suppress only the live dialogue's two update cues."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/practice_session.cpp"


class PracticeDialogueHoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-dialogue-hold-")
        cls.addClassCleanup(cls.temp.cleanup)
        code = r'''
typedef unsigned int u32;
namespace JDrama {struct TViewObj {u32 flags;};struct TGraphics {u32 value;};}
struct TMarDirector {unsigned char before[0xb0];__UINTPTR_TYPE__ _11;};
static TMarDirector director;static TMarDirector *gpMarDirector=&director;
static JDrama::TViewObj owned={0x8120},unrelated={0x4321};
static JDrama::TGraphics graphics={0xabcd};
static bool sFreeze,ready,sPadHookReady,sTalkHookReady;
static u32 calls,lastCue,movement,animation,draw,wrongArguments;
static u32 table[12],flushes,flushSize;static void *flushAddress;
static bool stageReady(){return ready;}
static void original(JDrama::TViewObj*obj,u32 cue,JDrama::TGraphics*gfx){
 ++calls;lastCue=cue;movement+=(cue&1)!=0;animation+=(cue&2)!=0;draw+=(cue&8)!=0;
 wrongArguments|=(obj!=&owned&&obj!=&unrelated)||gfx!=&graphics;
}
static const __UINTPTR_TYPE__ kTalkPerform=reinterpret_cast<__UINTPTR_TYPE__>(&original);
static void DCFlushRange(void*address,u32 size){++flushes;flushSize=size;flushAddress=address;}
'''
        for name in ('bool installVtableEntry(', 'extern "C" void susamunePracticeTalkPerform(',
                     'bool available()'):
            code += function_source(SOURCE, name) + "\n"
        code += r'''
extern "C" {
__declspec(dllexport) void reset(){
 calls=lastCue=movement=animation=draw=wrongArguments=flushes=flushSize=0;flushAddress=0;
 director._11=reinterpret_cast<__UINTPTR_TYPE__>(&owned);
 owned.flags=0x8120;unrelated.flags=0x4321;
 for(u32 i=0;i<12;++i)table[i]=0x11220000+i;
}
__declspec(dllexport) void dispatch(u32 cue,u32 freeze,u32 valid,u32 same){
 sFreeze=freeze;ready=valid;
 susamunePracticeTalkPerform(same?&owned:&unrelated,cue,&graphics);
}
__declspec(dllexport) u32 install(u32 before){
 table[8]=before;
 return installVtableEntry(&table[8],0x802130a8u,reinterpret_cast<void*>(&susamunePracticeTalkPerform));
}
__declspec(dllexport) u32 reinstall(){
 return installVtableEntry(&table[8],0x802130a8u,reinterpret_cast<void*>(&susamunePracticeTalkPerform));
}
__declspec(dllexport) u32 tableWord(u32 i){return table[i];}
__declspec(dllexport) u32 hooks(u32 mask){sPadHookReady=mask&1;sTalkHookReady=mask&2;return available();}
__declspec(dllexport) u32 get(u32 key){switch(key){
 case 0:return calls;case 1:return lastCue;case 2:return movement;case 3:return animation;
 case 4:return draw;case 5:return wrongArguments;case 6:return owned.flags;case 7:return unrelated.flags;
 case 8:return flushes;case 9:return flushSize;case 10:return flushAddress==&table[8];
 case 11:return static_cast<u32>(reinterpret_cast<__UINTPTR_TYPE__>(&susamunePracticeTalkPerform));
 }return 0;}
}
'''
        source = Path(cls.temp.name)/"dialogue.cpp"
        source.write_text(code)
        library = source.with_suffix(".dll")
        subprocess.run([str(ROOT/"toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-O2", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                        str(source), "-o", str(library)], capture_output=True, text=True, check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.get.restype = C.c_uint
        cls.lib.tableWord.restype = C.c_uint
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self):
        self.lib.reset()

    def test_holding_dialogue_preserves_draw_without_movement_or_page_animation(self):
        for _ in range(120):
            self.lib.dispatch(0xb,1,1,1)
        self.assertEqual([self.lib.get(i) for i in range(6)],[120,8,0,0,120,0])
        self.assertEqual([self.lib.get(i) for i in (6,7)],[0x8120,0x4321])

    def test_step_releases_both_updates_then_hold_resumes(self):
        self.lib.dispatch(0xb,1,1,1)
        self.lib.dispatch(0xb,0,1,1)
        self.lib.dispatch(0xb,1,1,1)
        self.assertEqual([self.lib.get(i) for i in (0,2,3,4)],[3,1,1,3])

    def test_pause_activated_between_retail_ticks_is_seen_at_next_dispatch(self):
        self.lib.dispatch(1,0,1,1)
        self.lib.dispatch(3,1,1,1)
        self.lib.dispatch(8,1,1,1)
        self.assertEqual([self.lib.get(i) for i in (0,2,3,4)],[3,1,0,1])

    def test_ordinary_play_unrelated_objects_and_unready_stage_pass_through(self):
        for freeze,valid,same in ((0,1,1),(1,0,1),(1,1,0)):
            self.lib.reset();self.lib.dispatch(0xffffffff,freeze,valid,same)
            self.assertEqual([self.lib.get(i) for i in range(6)],[1,0xffffffff,1,1,1,0])

    def test_only_update_bits_are_removed_from_combined_and_draw_only_cues(self):
        for cue in (0,1,2,3,8,0xb,0x14,0x100,0xffffffff):
            self.lib.reset();self.lib.dispatch(cue,1,1,1)
            self.assertEqual(self.lib.get(1),cue&~3)
            self.assertEqual(self.lib.get(0),1)

    def test_vtable_installs_only_over_expected_retail_word_and_flushes_one_word(self):
        for original in (0,0x802130ac,0x11111111):
            self.lib.reset();self.assertEqual(self.lib.install(original),0)
            self.assertEqual(self.lib.tableWord(8),original)
            self.assertEqual(self.lib.get(8),0)
        self.lib.reset();self.assertEqual(self.lib.install(0x802130a8),1)
        self.assertEqual(self.lib.tableWord(8),self.lib.get(11))
        self.assertEqual([self.lib.get(i) for i in (8,9,10)],[1,4,1])
        self.assertEqual([self.lib.tableWord(i) for i in range(12) if i!=8],
                         [0x11220000+i for i in range(12) if i!=8])
        self.assertEqual(self.lib.reinstall(),0)
        self.assertEqual(self.lib.get(8),1)

    def test_unavailable_dialogue_hook_disables_practice_admission(self):
        self.assertEqual([self.lib.hooks(i) for i in range(4)],[0,0,0,1])
        init = function_source(SOURCE,"void init()")
        self.assertIn("sTalkHookReady = installVtableEntry(reinterpret_cast<u32 *>(kTalkVtable + 0x20u)",init)
        for name in ("bool requestPauseToggle(", "bool requestStep(", "bool requestRecordFrom("):
            self.assertIn("!available()",function_source(SOURCE,name))
        stage = function_source(SOURCE,"bool stageReady()")
        self.assertIn("RetailInput::stageDirector() == gpMarDirector",stage)
        self.assertIn("gpMarDirector->_260 != 0",stage)


if __name__ == "__main__":
    unittest.main()
