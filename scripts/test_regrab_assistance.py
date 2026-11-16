"""Regrab assistance follows actual state-changing action admission."""
import ctypes as C
import os,subprocess,tempfile,unittest
from pathlib import Path
from test_practice_tape import function_source
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
using u32=unsigned;
static bool stage,held,accept;static unsigned assist,invalidated,calls;
struct Actor {bool receiveMessage(void*,unsigned){++calls;return accept;}};
struct TMario {Actor*mHeldObject;Actor*mGrabTarget;unsigned mState;};
static TMario mario;static TMario*gpMarioAddress;
static Actor fruit;static Actor*gLastHeldObject;
static bool stageActive(){return stage;}
struct Timer {void markPracticeAssisted(){++assist;}}gQFTTimer;
namespace ILing {void invalidateForAssist(){++invalidated;}}
struct Binds {bool isHeld(unsigned){return held;}}gBinds;
enum {BIND_REGRAB_OBJECT=1,kMarioStatusTake=0x383,kHitMessageTake=4};
"""
POST=r"""
#define API extern "C" __declspec(dllexport)
API void reset(unsigned options){
 stage=options&1;held=options&2;accept=options&4;gpMarioAddress=options&8?&mario:nullptr;
 mario={options&16?&fruit:nullptr,nullptr,0x123};gLastHeldObject=options&32?&fruit:nullptr;assist=invalidated=calls=0;
}
API void run(){regrabLastHeldObject();}
API unsigned get(unsigned n){return n==0?assist:n==1?invalidated:n==2?calls:n==3?mario.mState:n==4?mario.mHeldObject==&fruit:gLastHeldObject==&fruit;}
"""
class RegrabAssistanceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='regrab-assist-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  (d/'test.cpp').write_text(FIXTURE+function_source(ROOT/'src/actions.cpp','void regrabLastHeldObject()')+POST,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-O2',str(d/'test.cpp'),'-o',str(d/'test.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_regrab_marks_assistance_and_invalidates_il(self):
  self.lib.reset(1|2|4|8|32);self.lib.run();self.assertEqual([self.lib.get(n) for n in range(5)],[1,1,1,0x383,1])
 def test_failed_take_still_marks_the_attempted_state_change(self):
  self.lib.reset(1|2|8|32);self.lib.run();self.assertEqual([self.lib.get(n) for n in range(5)],[1,1,1,0x383,0])
 def test_ordinary_held_object_tracking_is_not_assisted(self):
  self.lib.reset(1|2|4|8|16);self.lib.run();self.assertEqual([self.lib.get(n) for n in (0,1,2,5)],[0,0,0,1])
 def test_missing_stage_player_bind_or_object_does_not_mark(self):
  valid=1|2|4|8|32
  for missing in (1,2,8,32):
   self.lib.reset(valid&~missing);self.lib.run();self.assertEqual([self.lib.get(n) for n in range(3)],[0,0,0])
if __name__=='__main__':unittest.main()
