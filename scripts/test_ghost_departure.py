"""Asynchronous recording preparation must finish before stage setup, without blocking the fade."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
#include "susamune/ghost_departure.hxx"
static int answer,prepared,polled,canceled,missed;static unsigned lastScene;static bool lastSelected;
namespace Ghost {void prepareStreamDeparture(bool keepIncomplete){prepared+=keepIncomplete?100:1;}}
namespace GhostRecording {
Gate beforeDeparture(unsigned scene,bool selected){++polled;lastScene=scene;lastSelected=selected;return static_cast<Gate>(answer);}
void cancelArmed(){++canceled;}void unrecordedDeparture(){++missed;}
}
#define API extern "C" __declspec(dllexport)
API void reset(){GhostDeparture::cancel();answer=prepared=polled=canceled=missed=0;}
API int begin(unsigned scene,int selected){return GhostDeparture::begin(scene,selected!=0);}
API void response(int value){answer=value;}
API void tick(){GhostDeparture::poll();}
API int waiting(){return GhostDeparture::waiting();}
API int finish(){return GhostDeparture::finish();}
API void cancel(){GhostDeparture::cancel();}
API unsigned value(int n){return n==0?prepared:n==1?polled:n==2?canceled:n==3?missed:n==4?lastScene:lastSelected;}
'''
class DepartureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='msgt-departure-');cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name)
  (d/'fixture.cpp').write_text(FIXTURE)
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++11','-O2','-DMOONSHINE_GHOST_TRACE=1','-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),str(d/'fixture.cpp'),str(ROOT/'src/ghost_departure.cpp'),'-o',str(d/'fixture.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.reset()
 def test_pending_close_and_open_can_overlap_fade_but_not_stage_setup(self):
  self.lib.response(1);self.assertEqual(self.lib.begin(0x603,1),1)
  for _ in range(30):self.lib.tick();self.assertEqual(self.lib.waiting(),1)
  self.assertEqual(self.lib.value(0),1);self.assertEqual(self.lib.finish(),0);self.assertEqual(self.lib.waiting(),1)
  self.lib.response(0);self.lib.tick();self.assertEqual(self.lib.waiting(),0);self.assertEqual(self.lib.finish(),0)
  count=self.lib.value(1);self.lib.tick();self.assertEqual(self.lib.value(1),count)
 def test_cancel_does_not_commit_a_stale_request_to_a_later_departure(self):
  self.lib.response(1);self.lib.begin(0x603,1);self.lib.cancel();self.assertEqual(self.lib.waiting(),0)
  self.assertEqual(self.lib.value(2),1);self.lib.response(0);self.assertEqual(self.lib.begin(0x200,0),0)
  self.assertEqual(self.lib.value(4),0x200);self.assertEqual(self.lib.value(5),0);self.assertEqual(self.lib.finish(),0)
 def test_late_failure_records_unavailable_once_without_deadlocking_handoff(self):
  self.lib.response(1);self.lib.begin(0x603,1);self.lib.response(2);self.lib.tick()
  self.assertEqual(self.lib.waiting(),0);self.assertEqual(self.lib.finish(),1)
  self.assertEqual(self.lib.value(2),1);self.assertEqual(self.lib.value(3),1)
  self.assertEqual(self.lib.finish(),0);self.assertEqual(self.lib.value(3),1)
 def test_pending_destination_is_immutable_until_canceled(self):
  self.lib.response(1);self.lib.begin(0x603,1);self.assertEqual(self.lib.begin(0x200,0),2)
  self.lib.tick();self.assertEqual(self.lib.value(4),0x603);self.assertEqual(self.lib.value(0),1)
 def test_native_return_one_also_waits_when_an_explicit_tail_is_pending(self):
  source=(ROOT/'src/warp_wheel.cpp').read_text()
  line=next(line.strip() for line in source.splitlines() if 'appState!=0' in line and 'GhostDeparture::waiting()' in line)
  expression=line.removeprefix('if(').removesuffix(')return 0;')
  expression=expression.replace('TApplication::CONTEXT_DIRECT_MAIN_LOOP','1').replace('GhostDeparture::waiting()','pending').replace('&&',' and ').replace('||',' or ')
  cases=[('fade in progress',0,True,True,False),('explicit fade completed',1,True,True,True),
         ('ordinary frame return',1,False,True,False),('new scene return',5,False,True,True),
         ('recording ready',1,True,False,False)]
  for label,appState,sTailPending,pending,expected in cases:
   held=eval(expression,{},dict(appState=appState,sTailPending=sTailPending,pending=pending))
   self.assertEqual(held,expected,label)

if __name__=='__main__':unittest.main()
