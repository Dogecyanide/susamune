"""Wii test-page capture and replay ownership, using the actual controller."""
import ctypes as C
from pathlib import Path
import os, re, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
PREFIX=r"""
#include <cstring>
#include <cstdio>
#define MOONSHINE_GHOST_TRACE 1
static unsigned gameVersion=1;
#define SUSAMUNE_GAME_VERSION gameVersion
static unsigned char memory[256] __attribute__((aligned(32)));
#define MS_TRACE_CONTROL_PPC ((__UINTPTR_TYPE__)memory-0x3100)
static unsigned warpCalls,finishCalls,openCalls,watchCalls,stopCalls,nonce=77,run,recordScene,errorCode,reportCode,lastWatchRun;
static int entry=57,warpEntry=-1,lastWatchEntry=-1;
static unsigned admissionError;
static bool armed,recording,saved,discarded,busy,watching,warpOk=true;
struct Menu {void toast(const char*){}};static Menu menu;Menu*gMenu=&menu;
namespace ILing {int activeEntry(){return entry;}unsigned ghostBrowseFilter(int){return 0x0407;}const char*shortLabel(int){return "Sirena 4 Full";}}
namespace WarpWheel {bool requestExplicitILStart(int e){++warpCalls;warpEntry=e;return warpOk;}}
namespace GhostTrace {
unsigned completedRunFlags(unsigned){return 0;}
struct Completion {unsigned nonce,run,game,bytes,chunks,frames,capabilities,headerHash,footerHash;};
bool backendIdentity(unsigned &n){n=nonce;return true;}
bool armOrdinaryStage(unsigned scene,unsigned r){++openCalls;recordScene=scene;run=r;return true;}
bool finishOrdinary(unsigned r){++finishCalls;return recording&&r==run;}
bool stageArmed(){return armed;}bool recording(){return ::recording;}
unsigned failure(unsigned){return errorCode;}bool discarded(unsigned){return ::discarded;}
bool completion(unsigned r,Completion&out){if(!saved)return false;out={nonce,r,0x474d534a,1000,1,10,0,0,0};return true;}
void reset(){::discarded=true;}
}
namespace GhostReplayReport {unsigned poll(){return 0;}}
namespace GhostWorldRuntime {
bool setSourceRunFlags(unsigned){return true;}
bool armFile(unsigned n,unsigned r,unsigned region){++watchCalls;lastWatchRun=r;return n&&region==SUSAMUNE_GAME_VERSION&&!admissionError;}
unsigned startError(){return admissionError;}
bool startAt(int e){lastWatchEntry=e;watching=true;return true;}
void stop(){++stopCalls;watching=busy=false;}
bool busy(){return ::busy||watching;}
void status(unsigned*out){std::memset(out,0,128);out[3]=reportCode;out[4]=123;}
}
unsigned OSGetTick(){return 1234;}
"""
SUFFIX=r"""
extern "C" {
__declspec(dllexport) void region(unsigned v){gameVersion=v;}
__declspec(dllexport) void resetTest(){GhostReplayTest::initialized=false;std::memset(memory,0,sizeof(memory));warpCalls=finishCalls=openCalls=watchCalls=stopCalls=run=recordScene=errorCode=reportCode=lastWatchRun=0;entry=57;warpEntry=lastWatchEntry=-1;armed=recording=saved=discarded=busy=watching=false;warpOk=true;admissionError=0;}
__declspec(dllexport) int action(unsigned n){return GhostReplayTest::action(n);}
__declspec(dllexport) void tick(){GhostReplayTest::update();}
__declspec(dllexport) void finish(){GhostReplayTest::finished();}
__declspec(dllexport) void set(unsigned key,int value){switch(key){case 0:entry=value;break;case 1:armed=value;break;case 2:recording=value;break;case 3:saved=value;break;case 4:discarded=value;break;case 5:busy=value;break;case 6:reportCode=value;break;case 7:warpOk=value;break;case 8:admissionError=value;break;}}
__declspec(dllexport) const char* message(){return GhostReplayTest::status();}
__declspec(dllexport) unsigned get(unsigned key){switch(key){case 0:return warpCalls;case 1:return finishCalls;case 2:return openCalls;case 3:return watchCalls;case 4:return stopCalls;case 5:return recordScene;case 6:return lastWatchRun;case 7:return lastWatchEntry;}return 0;}
}
"""
class ReplayTestController(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-replay-controls-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  source=re.sub(r'^#include .*$', '',(ROOT/'src/ghost_replay_test.cpp').read_text(),flags=re.M)
  (folder/'probe.cpp').write_text(PREFIX+source+SUFFIX)
  env=os.environ.copy();env['PATH']='C:/msys64/mingw64/bin;'+env.get('PATH','')
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static',str(folder/'probe.cpp'),'-o',str(folder/'probe.dll')],capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(str(r.returncode)+"\n"+r.stdout[-1000:]+r.stderr[-4000:])
  cls.lib=C.CDLL(str(folder/'probe.dll'));cls.lib.message.restype=C.c_char_p;cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.resetTest()
 def start(self):
  self.assertTrue(self.lib.action(0));self.lib.tick();self.assertEqual(self.lib.get(0),0)
  self.lib.set(1,1);self.lib.tick();self.lib.set(2,1);self.assertEqual(self.lib.get(0),1);self.assertEqual(self.lib.get(5),0x0603)
 def save(self):
  self.lib.finish();self.assertEqual(self.lib.get(1),0);self.lib.tick();self.assertEqual(self.lib.get(1),1)
  self.lib.set(3,1);self.lib.tick()
 def test_requires_selected_il(self):
  self.lib.set(0,-1);self.assertFalse(self.lib.action(0));self.assertEqual(self.lib.get(2),0)
 def test_loading_zones_do_not_finalize_a_full_il(self):
  self.start()
  for _ in range(80):self.lib.tick()
  self.assertEqual(self.lib.get(1),0);self.assertEqual(self.lib.get(0),1)
 def test_result_waits_for_complete_frame_and_published_file(self):
  self.start();self.lib.finish();self.assertEqual(self.lib.get(1),0);self.lib.tick()
  self.assertFalse(self.lib.action(2));self.assertEqual(self.lib.get(3),0)
  self.lib.set(3,1);self.lib.tick();self.assertTrue(self.lib.action(2));self.assertEqual(self.lib.get(6),1234);self.assertEqual(self.lib.get(7),57)
 def test_manual_stop_also_preserves_last_frame(self):
  self.start();self.assertFalse(self.lib.action(1));self.assertEqual(self.lib.get(1),0);self.lib.tick();self.assertEqual(self.lib.get(1),1)
 def test_discard_preserves_last_completed_capture(self):
  self.start();self.save();self.lib.set(1,0);self.lib.set(3,0);self.assertTrue(self.lib.action(0));self.lib.set(4,1);self.lib.tick()
  self.assertTrue(self.lib.action(2));self.assertEqual(self.lib.get(6),1234)
 def test_playback_error_stops_once(self):
  self.assertTrue(self.lib.action(3));self.lib.set(6,116);self.lib.tick();self.lib.tick();self.assertEqual(self.lib.get(4),1)
 def test_replay_ownership_blocks_recording(self):
  self.lib.set(5,1);self.assertFalse(self.lib.action(0));self.assertEqual(self.lib.get(2),0)
 def test_memory_card_refusal_is_not_reported_as_recording(self):
  self.lib.set(8,6);self.assertFalse(self.lib.action(3));self.assertIn(b'GameCube memory card',self.lib.message());self.assertEqual(self.lib.get(4),0)
 def test_other_start_refusals_report_the_actual_check(self):
  self.lib.set(8,8);self.assertFalse(self.lib.action(3));self.assertIn(b'check 8',self.lib.message())
 def test_returned_pal_samples_route_to_the_correct_ils(self):
  self.lib.region(3)
  try:
   self.assertEqual(self.lib.action(3),1);self.assertEqual(self.lib.get(6),0x31eb5436);self.assertEqual(self.lib.get(7),3);self.lib.action(6)
   self.assertEqual(self.lib.action(4),1);self.assertEqual(self.lib.get(6),0x3f630001);self.assertEqual(self.lib.get(7),52);self.lib.action(6)
   self.assertEqual(self.lib.action(5),1);self.assertEqual(self.lib.get(6),0x3f630002);self.assertEqual(self.lib.get(7),85)
  finally:self.lib.region(1)
if __name__=='__main__':unittest.main()
