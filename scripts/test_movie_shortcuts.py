"""Run the production movie routing and state-admission guards on the host."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class MovieShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        movie = function_source(ROOT / "src/main.cpp", "    if (!stageDirector) {")
        main = (ROOT / "src/main.cpp").read_text()
        def declaration(name):
            start = main.index(name)
            return main[start:main.index(";", start) + 1]
        cinematic = "\n".join(declaration(name) for name in (
            "const bool tasCinematic", "bool menuOwnsRetailPad", "const bool wheelToggleBeforeDirect"))
        menu_update = function_source(ROOT / "src/main.cpp", "    if (gMenu && (!tasCinematic")
        guard = function_source(ROOT / "src/savestate.cpp", "bool inLoadTransition()")
        source = Path(cls.folder.name) / "movie.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
struct TMarDirector { enum {STATE_GAME_STARTING=2,STATE_NORMAL=4,STATE_PAUSE_MENU=5};u8 _260,mCurState; } stage,other;
static TMarDirector *gpMarDirector,*activeStage;
namespace RetailInput {TMarDirector *stageDirector(){return activeStage;}}
static u32 raw,seen,buttons,queries,events,steps,pauses,stops,consumed;
static bool recording,tasRecording,tasReplaying;static unsigned menuUpdates;
enum {BIND_PRACTICE_STEP=1,BIND_PRACTICE_PAUSE=2,BIND_PRACTICE_STOP=3,BIND_MENU_TOGGLE=4,BIND_WARP_WHEEL=5,SETTING_DISABLE_WARPS=6};
struct Binds {
 bool recording(){return ::recording;}
 bool wasPressedPracticeRaw(unsigned id){queries|=1u<<id;return buttons&(1u<<id);}
 bool wasPressedRaw(unsigned id){return wasPressed(id);}
 bool wasPressed(unsigned id){queries|=1u<<id;return buttons&(1u<<id);}
} gBinds;
namespace PracticeSession {
 bool recording(){return tasRecording;}bool replaying(){return tasReplaying;}
 void requestStep(){++steps;}
 void requestPauseToggle(){++pauses;}
 void requestStop(){++stops;}
 void beforeDirect(bool modal){events=events*10+(modal?9:1);}
 void afterDirect(s32 result,bool advanced){events=events*10+4;consumed=advanced;}
}
void featuresApply(){events=events*10+2;}
namespace Ghost {void beforeDirect(){} void update(){events=events*10+5;}}
struct {bool getBool(unsigned){return false;}} gSettings;
struct Menu {void update(void*){++menuUpdates;}} menu,*gMenu=&menu;
struct {void *mGamePads[1];} gpApplication;
struct Director {s32 direct(){seen=raw;events=events*10+3;return 6;}} movie;
''' + guard + r'''
extern "C" __declspec(dllexport) unsigned route(unsigned input,unsigned bindings,unsigned modes){
 raw=input;seen=queries=events=steps=pauses=stops=consumed=0;buttons=bindings;recording=modes&1;
 auto *stageDirector=(modes&2)?&stage:nullptr;auto *director=&movie;
''' + movie + r'''
 return 99;
}
extern "C" __declspec(dllexport) unsigned value(unsigned index){
 switch(index){case 0:return seen;case 1:return events;case 2:return consumed;case 3:return queries;
 case 4:return steps;case 5:return pauses;case 6:return stops;default:return 0;}
}
extern "C" __declspec(dllexport) unsigned stageControls(unsigned state,unsigned initialized,unsigned mode,unsigned binds){
 stage.mCurState=state;stage._260=initialized;auto *stageDirector=&stage;
 tasRecording=mode&1;tasReplaying=mode&2;buttons=binds;menuUpdates=0;
 const bool menuOpenBeforeDirect=mode&4,stepOverridesShortcut=false,creationEditing=false,stateDiskBusy=false;
 const bool sessionResultBeforeDirect=false,practiceStepConsumed=false,sessionOwnsInput=false,allowExistingMenuToClose=false;
''' + cinematic + "\n" + menu_update + r'''
 return tasCinematic|(menuOwnsRetailPad<<1)|(wheelToggleBeforeDirect<<2)|(menuUpdates<<3);
}
extern "C" __declspec(dllexport) unsigned blocked(unsigned mode,unsigned initialized,unsigned state){
 stage._260=initialized;stage.mCurState=state;gpMarDirector=&stage;activeStage=&stage;
 if(mode==1){gpMarDirector=reinterpret_cast<TMarDirector*>(1);activeStage=nullptr;}
 if(mode==2)activeStage=&other;
 if(mode==3)gpMarDirector=nullptr;
 return inLoadTransition();
}
''', encoding="ascii")
        library=source.with_suffix(".dll")
        subprocess.run([str(compiler),"--target=x86_64-pc-windows-msvc","-shared",
                        "-nostdlib","-fuse-ld=lld","-Wl,/noentry","-O2",
                        "-I",str(ROOT/"include"),str(source),"-o",str(library)],check=True)
        cls.lib=C.CDLL(str(library))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_movie_menu_wheel_and_checkpoint_chords_remain_retail_inputs(self):
        for chord in (0x1800,0x10,0x40,0x300,0):
            self.assertEqual(self.lib.route(chord,0xFFF0,0),6)
            self.assertEqual([self.lib.value(i) for i in (0,1,2)], [chord,12345,1])
            self.assertEqual(self.lib.value(3)&~0xE,0)
            self.assertEqual([self.lib.value(i) for i in (4,5,6)],[0,0,0])

    def test_buffered_pause_and_step_never_drop_the_movie_input_clock(self):
        for mask,counts in ((2,(1,0,0)),(4,(0,1,0)),(6,(1,0,0)),(8,(0,0,1))):
            self.lib.route(0x100,mask,0)
            self.assertEqual([self.lib.value(i) for i in (0,1,2)],[0x100,12345,1])
            self.assertEqual(tuple(self.lib.value(i) for i in (4,5,6)),counts)

    def test_combo_recorder_owns_actions_without_changing_retail_movie_input(self):
        self.lib.route(0x100,14,1)
        self.assertEqual([self.lib.value(i) for i in (0,1,2,3)],[0x100,12345,1,0])

    def test_stage_does_not_take_movie_early_return(self):
        self.assertEqual(self.lib.route(0x100,14,2),99)
        self.assertEqual(self.lib.value(1),0)

    def test_active_tas_intro_chords_do_not_create_phantom_overlays(self):
        for state in (0,1,2,3,7,9,10,11,12):
            for mode in (1,2):
                self.assertEqual(self.lib.stageControls(state,1,mode,0x30),1)
                self.assertEqual(self.lib.stageControls(state,0,mode,0x30),1)

    def test_existing_intro_menu_remains_accessible_and_normal_menus_are_unchanged(self):
        self.assertEqual(self.lib.stageControls(1,1,5,0x10),11)
        self.assertEqual(self.lib.stageControls(1,1,0,0x10),10)
        for state in (4,5):
            self.assertEqual(self.lib.stageControls(state,1,1,0x10),10)

    def test_new_warp_wheel_only_claims_a_fully_loaded_normal_stage(self):
        self.assertEqual(self.lib.stageControls(4,1,1,0x20),12)
        self.assertEqual(self.lib.stageControls(4,0,1,0x20),8)
        for state in (0,1,2,3,5,7,9,10,11,12):
            self.assertFalse(self.lib.stageControls(state,1,0,0x20)&4)

    def test_stale_director_is_rejected_before_any_field_dereference(self):
        for mode in (1,2,3):
            self.assertTrue(self.lib.blocked(mode,1,4))

    def test_state_admission_keeps_existing_real_stage_rules(self):
        for state in range(13):
            self.assertEqual(self.lib.blocked(0,1,state),int(state<2))
            self.assertTrue(self.lib.blocked(0,0,state))

    def test_movie_branch_precedes_overlay_prediction_and_tas_dispatch(self):
        body=function_source(ROOT/"src/main.cpp", 'extern "C" s32 onUpdate(')
        start=body.index("if (!stageDirector)")
        self.assertLess(start,body.index("const bool creationEditing"))
        self.assertLess(start,body.index("menuOwnsRetailPad"))
        self.assertLess(start,body.index("TasProject::dispatchShortcut"))


if __name__ == "__main__":
    unittest.main()
