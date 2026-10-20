"""Exercise the production QFT decomposition over multi-stage attempt histories."""
import ctypes
import _ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class FinishBreakdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="qft-segments-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        (folder / "test.cpp").write_text(r'''
#include "susamune/qft_segments.h"
MoonshineQftSegments state;
#define API extern "C" __declspec(dllexport)
API void reset() {state.seen=false;state.invalidate();}
API void sample(unsigned serial,unsigned generation,unsigned scene,int qf,int local,unsigned load) {
 state.sample(serial,generation,(unsigned short)scene,qf,local,load);
}
API void edge(int qf) {state.transition(qf);}
API void invalidate() {state.invalidate();}
API int finish(int qf) {return state.finish(qf);}
API unsigned load(unsigned n) {return state.stages[n].loadMs;}
API int count() {return state.count;}
API int stage(unsigned n,int field) {return field==0?state.stages[n].begin:
 field==1?state.stages[n].end:state.stages[n].scene;}
''')
        runtime = (ROOT / "src/finish_breakdown.cpp").read_text()
        lifecycle = "\n".join(function(runtime, sig) for sig in (
            "void onStageSetup()", "void onDeparture()", "void finish(int entry", "void draw(Menu *menu)"))
        shim = r'''
typedef unsigned u32;typedef unsigned short u16;typedef unsigned char u8;typedef int s32;typedef long long OSTime;
#define OSSecondsToTicks(x) ((x)*1000)
#define OSTicksToMilliseconds(x) (x)
OSTime now,sBreakdownDeparture;OSTime OSGetTime(){return now;}
MoonshineQftSegments &sBreakdownSegments=state;
MoonshineQftSegments::Stage sBreakdownResult[8];
u32 sBreakdownSetup,sBreakdownLoadMs;u16 sBreakdownResultFrames;u8 sBreakdownResultCount,sBreakdownHalfSeconds;int sBreakdownEntry,drawn;bool sBreakdownLoading;
struct Menu {bool hidden;bool shown(){return hidden;}} menu;
namespace StageLoader {bool held;bool modal(){return held;}}
namespace WarpWheel {bool retailExit;bool shown(){return false;}bool retailExitPending(){return retailExit;}}
enum{SETTING_FINISH_BREAKDOWN,SETTING_DISABLE_WARPS};
struct Settings{bool disableWarps;bool getBool(int id){return id==SETTING_FINISH_BREAKDOWN||disableWarps;}} gSettings;
void drawPanel(Menu*,bool){++drawn;}
'''
        exports = r'''
API void resultStart(unsigned duration) {
 sBreakdownHalfSeconds=duration;state.seen=false;state.sample(5,1,3,0,4,0);
 state.sample(5,1,3,1000,1004,0);state.transition(1000);
 state.sample(5,2,42,1120,4,900);finish(1,3000);drawn=0;
}
API unsigned frames(){return sBreakdownResultFrames;}
API void render(int hidden,int modal){menu.hidden=hidden;StageLoader::held=modal;draw(&menu);}
API void depart(){onDeparture();}
API void setup(){onStageSetup();}
'''
        main = (ROOT / "src/main.cpp").read_text()
        direct_start = main.index("int state = director->direct();")
        direct_fragment = main[direct_start:main.index("// Exit Area is identified", direct_start)]
        setup_start = main.index("director->setupObjects();")
        setup_fragment = main[setup_start:main.index("SplitEvents::onStageSetup(director);", setup_start)]
        integration = r'''
namespace FinishBreakdown {
void onDeparture(){::onDeparture();}void onStageSetup(){::onStageSetup();}
}
struct TApplication {enum{CONTEXT_DIRECT_MAIN_LOOP=1};};
int rawAppState;
struct TMarDirector {
 int mCurState,mAreaID,mEpisodeID,_260;
 int direct(){return rawAppState;}
 void setupObjects(){now+=400;}
} integrationDirector,*gpMarDirector=&integrationDirector;
namespace LevelWarp {
bool held;int calls,cancellations;
int onDirected(int state){++calls;return held?0:state;}
void cancelPending(bool){++cancellations;}
}
void restoreRetailPad(int,int){}
namespace PracticeSession {void endFrozenDirector(){}void afterDirect(int,bool){}void seekAfterDirect(){}}
namespace Ghost {void afterDirect(int){}}
namespace WallkickDisplay {void afterDirect(bool){}}
namespace MovementDisplay {void afterDirect(bool){}}
namespace MovementTimingDisplay {void afterDirect(bool){}}
namespace GameplayPolish {void afterDirect(){}}
enum{SUSAMUNE_CRASH_EVENT_SETUP_RETURN};
namespace CrashReport {void note(int,u32,int){now+=1000;}}
namespace ILing {void onStageSetup(){now+=1000;}}
namespace Records {enum Area{OLD,NEW};Area classifyArea(int){return NEW;}}
namespace RecordsPersistence {void checkpoint(){now+=1000;}}
void featuresOnStageLoad(){now+=1000;}
void actionsOnStageLoad(){now+=1000;}
void visibleGoopOnStageSetup(){now+=1000;}
struct Timer {void onStageSetup(TMarDirector*){now+=1000;}}gQFTTimer;
API void integrationReset(){
 state.seen=false;state.sample(9,1,3,0,4,0);
 sBreakdownResultFrames=0;sBreakdownLoading=false;sBreakdownLoadMs=~0u;
 now=10000;LevelWarp::calls=LevelWarp::cancellations=0;
}
API int mainDirect(int returned,int held,int frozen,int disabled,int retailExit){
 rawAppState=returned;LevelWarp::held=held;gSettings.disableWarps=disabled;WarpWheel::retailExit=retailExit;
 TMarDirector *director=&integrationDirector;
 bool suppressPad=false,freeze=frozen,menuOwnsRetailPad=false,stateDiskBusy=false,marioActive=true;
 int retailPad=0,retailInput=0,heldDirectorState=4;
'''
        integration += direct_fragment + r'''
 return state;
}
API void advanceClock(unsigned elapsed){now+=elapsed;}
API unsigned mainSetup(){
 TMarDirector *director=&integrationDirector;
 bool recordsSceneKnown=true;Records::Area recordsArea=Records::OLD;
'''
        integration += setup_fragment + r'''
 return sBreakdownLoadMs;
}
API int loading(){return sBreakdownLoading;}
API unsigned clockValue(){return (unsigned)now;}
'''
        with (folder / "test.cpp").open("a") as out:
            out.write(shim + lifecycle + exports + integration)
        result = subprocess.run([str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-shared", "-O1", "-nostdlib",
            "-fuse-ld=lld", "-Xlinker", "/noentry", "-I", str(ROOT / "include"),
            str(folder / "test.cpp"), "-o", str(folder / "test.dll")],
            capture_output=True, text=True,
            env={**os.environ, "TEMP": str(folder), "TMP": str(folder)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.dll = ctypes.CDLL(str(folder / "test.dll"))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.dll._handle))

    def setUp(self):
        self.dll.reset()

    def sample(self, serial, generation, scene, qf, local=4, load=900):
        self.dll.sample(serial, generation, scene, qf, local, load)

    def totals(self):
        stages = [(self.dll.stage(i, 0), self.dll.stage(i, 1))
                  for i in range(self.dll.count())]
        durations = [end - start for start, end in stages]
        loads = [stages[i + 1][0] - stages[i][1] for i in range(len(stages) - 1)]
        return durations, loads

    def test_until_leave_never_expires_but_departure_clears_it(self):
        self.dll.resultStart(0)
        for _ in range(10000):
            self.dll.render(0, 0)
        self.assertEqual(self.dll.frames(), 65535)
        self.dll.depart()
        self.assertEqual(self.dll.frames(), 0)
        self.dll.resultStart(0)
        self.dll.setup()
        self.assertEqual(self.dll.frames(), 0)

    def test_timed_result_pauses_for_menu_and_survives_exit(self):
        self.dll.resultStart(1)
        self.assertEqual(self.dll.frames(), 15)
        for _ in range(100):
            self.dll.render(1, 0)
            self.dll.render(0, 1)
        self.assertEqual(self.dll.frames(), 15)
        self.dll.depart()
        self.dll.setup()
        self.assertEqual(self.dll.frames(), 15)
        for _ in range(15):
            self.dll.render(0, 0)
        self.assertEqual(self.dll.frames(), 0)

    def test_main_loop_returns_and_held_warp_retain_until_leave_result(self):
        self.dll.integrationReset()
        self.dll.resultStart(0)
        for returned, held, frozen, expected in ((0, 0, 0, 0), (1, 0, 0, 1),
                                                (5, 1, 0, 0), (5, 0, 1, 0)):
            with self.subTest(returned=returned, held=held, frozen=frozen):
                self.assertEqual(self.dll.mainDirect(returned, held, frozen, 0, 0), expected)
                self.assertEqual(self.dll.frames(), 65535)
                self.assertFalse(self.dll.loading())
        self.assertEqual(self.dll.mainDirect(5, 0, 0, 0, 0), 5)
        self.assertEqual(self.dll.frames(), 0)

    def test_main_only_accepted_handoff_starts_load_before_retail_setup_finishes(self):
        self.dll.integrationReset()
        for returned, held in ((0, 0), (1, 0), (5, 1)):
            self.dll.mainDirect(returned, held, 0, 0, 0)
            self.assertFalse(self.dll.loading())
            self.dll.advanceClock(500)
        self.dll.mainDirect(5, 0, 0, 0, 0)
        self.assertTrue(self.dll.loading())
        self.dll.advanceClock(600)
        # Retail setup costs 400 ms; every later mod callback costs 1000 ms.
        self.assertEqual(self.dll.mainSetup(), 1000)
        self.assertFalse(self.dll.loading())
        self.assertGreater(self.dll.clockValue(), 12500)

    def test_main_disabled_warps_still_recognizes_real_retail_departure(self):
        self.dll.integrationReset()
        self.dll.resultStart(0)
        self.dll.mainDirect(1, 0, 0, 1, 0)
        self.assertEqual(self.dll.frames(), 65535)
        self.dll.mainDirect(5, 0, 0, 1, 0)
        self.assertEqual(self.dll.frames(), 0)

    def test_two_stage_route_preserves_entry_load_secret_and_total(self):
        self.sample(1, 1, 2, 0)
        self.sample(1, 1, 2, 1524)
        self.dll.edge(1520)
        self.sample(1, 1, 2, 1620)
        self.sample(1, 2, 42, 1628)
        self.assertTrue(self.dll.finish(5268))
        self.assertEqual(self.totals(), ([1520, 3640], [108]))
        self.assertEqual(sum(map(sum, self.totals())), 5268)

    def test_first_ready_sampling_does_not_shorten_secret(self):
        for early_ticks in (4, 120, 400):
            self.dll.reset()
            self.sample(1, 1, 3, 0, 4)
            self.sample(1, 1, 3, 1528, 1532)
            self.dll.edge(1524)
            self.sample(1, 2, 42, 1632 + early_ticks, early_ticks, 900)
            self.assertTrue(self.dll.finish(5268))
            self.assertEqual(self.totals(), ([1524, 3632], [112]))
            self.assertEqual(self.dll.load(0), 900)
            self.assertEqual(sum(map(sum, self.totals())), 5268)

    def test_actual_load_does_not_change_qft_components(self):
        for actual_ms in (100, 900, 7000):
            self.dll.reset()
            self.sample(1, 1, 3, 0, 4)
            self.sample(1, 1, 3, 1524, 1528)
            self.dll.edge(1524)
            self.sample(1, 2, 42, 1636, 4, actual_ms)
            self.assertTrue(self.dll.finish(5268))
            self.assertEqual(self.totals(), ([1524, 3632], [112]))
            self.assertEqual(self.dll.load(0), actual_ms)

    def test_three_stage_route_and_repeated_areas_keep_all_loads(self):
        for generation, scene, begin, edge in ((1, 6, 0, 1000), (2, 7, 1120, 2020), (3, 14, 2100, 3100)):
            self.sample(2, generation, scene, begin)
            self.sample(2, generation, scene, edge)
            self.dll.edge(edge)
        self.sample(2, 4, 7, 3200)
        self.assertTrue(self.dll.finish(4000))
        self.assertEqual(self.totals(), ([1000, 900, 1000, 800], [120, 80, 100]))
        self.assertEqual(sum(map(sum, self.totals())), 4000)

    def test_new_attempt_discards_old_route_and_no_single_stage_breakdown(self):
        self.sample(1, 1, 2, 0)
        self.sample(1, 2, 42, 1000)
        self.sample(2, 3, 42, 0)
        self.assertEqual(self.dll.count(), 1)
        self.assertFalse(self.dll.finish(3000))

    def test_restore_blocks_history_until_fresh_attempt(self):
        self.sample(1, 1, 2, 0)
        self.dll.invalidate()
        self.sample(1, 2, 42, 2000)
        self.assertFalse(self.dll.finish(3000))
        self.sample(2, 3, 2, 0)
        self.sample(2, 4, 42, 2000)
        self.assertTrue(self.dll.finish(3000))

    def test_backward_clock_and_excessive_route_are_refused(self):
        self.sample(1, 1, 2, 100)
        self.sample(1, 2, 42, 99)
        self.assertFalse(self.dll.finish(3000))
        for i in range(9):
            self.sample(2, i, i, 100 * i)
        self.assertFalse(self.dll.finish(3000))

    def test_result_stays_frozen_and_missing_portal_uses_stage_end(self):
        self.sample(1, 1, 2, 0)
        self.sample(1, 1, 2, 600)
        self.sample(1, 2, 42, 720)
        self.assertTrue(self.dll.finish(1000))
        self.sample(1, 2, 42, 2000)
        self.assertFalse(self.dll.finish(2000))
        self.assertEqual(self.totals(), ([600, 280], [120]))


if __name__ == "__main__":
    unittest.main()
