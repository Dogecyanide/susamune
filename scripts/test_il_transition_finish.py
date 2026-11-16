"""Exercise transition ownership and the native card-save boundary."""
import ctypes as C, os, subprocess, tempfile, unittest
from pathlib import Path
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class TransitionFinishTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix="moonshine-transition-");cls.addClassCleanup(cls.temp.cleanup)
  src=(ROOT/"src/iling.cpp").read_text()
  code=r"""
#include "susamune/stage_transition.hxx"
using s32=int;using u16=unsigned short;
bool sRunning,sAttemptReady,sAwaitingStageSetup,sTransitionPending;int sSelectedEntry,sFinishKind;
enum {FINISH_SHINE,FINISH_TRANSITION};struct Entry{unsigned char result;};Entry kEntries[]={{2},{6}};
bool validEntry(int i){return i>=0&&i<2;}
struct Timer{bool pending;u16 target;int reads,consumed;
 bool transitionEntryQf(s32*q,u16*t){++reads;if(!pending)return false;*q=99;*t=target;return true;}
 bool consumeTransition(s32*q,u16*t){++consumed;pending=false;*q=100;*t=target;return true;}
}gQFTTimer;
int sOverlayCount;bool sHavePlazaStoryFlags;
bool isPlazaEntry(int i){return i==1;}
int progression,cleanup,serialized,saveCalls;
void clearAttempt(){progression=7;++cleanup;sRunning=false;sSelectedEntry=-1;sOverlayCount=0;sHavePlazaStoryFlags=false;}
struct JSUMemoryOutputStream{};
struct TFlagManager{void save(JSUMemoryOutputStream&){serialized=progression;++saveCalls;}};
"""
  for name in ('consumeSelectedTransition','temporaryProgressionActive','susamuneILCardSave'):code+=function(src,name)
  code+=r"""
#define API extern "C" __declspec(dllexport)
API unsigned decode(unsigned v){return StageTransition::area(v);}
API unsigned attempt(unsigned bits,unsigned target,int selected,unsigned kind){
 sRunning=bits&1;sAttemptReady=bits&2;sAwaitingStageSetup=bits&4;sTransitionPending=bits&8;
 sFinishKind=kind;sSelectedEntry=selected;gQFTTimer={bool(bits&16),u16(target),0,0};s32 q=-1;
 bool result=consumeSelectedTransition(q);
 return unsigned(result)|(gQFTTimer.pending?2u:0u)|(unsigned(gQFTTimer.consumed)<<2)|(q==100?8u:0u);
}
API unsigned save(unsigned temp){
 progression=99;cleanup=serialized=saveCalls=0;sRunning=true;sSelectedEntry=temp==1?1:-1;sOverlayCount=temp==2;sHavePlazaStoryFlags=temp==3;
 TFlagManager f;JSUMemoryOutputStream out;susamuneILCardSave(&f,&out);
 return serialized|(cleanup<<8)|(saveCalls<<16)|(unsigned(sRunning)<<24);
}
"""
  path=Path(cls.temp.name)/'test.cpp';path.write_text(code)
  run=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2','-I',str(ROOT/'include'),str(path),'-o',str(path.with_suffix('.dll'))],capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  if run.returncode:raise RuntimeError(run.stderr)
  cls.lib=C.CDLL(str(path.with_suffix('.dll')));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.attempt.argtypes=[C.c_uint,C.c_uint,C.c_int,C.c_uint]
 def test_all_retail_destination_encodings(self):
  for area in range(255):
   self.assertEqual(self.lib.decode(area),area)
   for episode in (0,3,7,255):self.assertEqual(self.lib.decode(((area+1)<<8)|episode),area)
 def test_raw_and_explicit_matching_endpoints(self):
  for dest,entry in ((2,0),(0x300,0),(0x303,0),(6,1),(0x707,1)):self.assertEqual(self.lib.attempt(19,dest,entry,1),13)
 def test_unrelated_endpoint_remains_available(self):self.assertEqual(self.lib.attempt(19,0x500,0,1),2)
 def test_inactive_unready_loading_or_finished_cannot_consume(self):
  for bits in (18,17,23,27):self.assertEqual(self.lib.attempt(bits,2,0,1),2)
 def test_unselected_and_shine_attempts_do_not_steal_transition(self):
  for selected,kind in ((-1,1),(2,1),(0,0)):self.assertEqual(self.lib.attempt(19,2,selected,kind),2)
 def test_missing_capture_cannot_finish(self):self.assertEqual(self.lib.attempt(3,2,0,1),0)
 def test_card_save_restores_temporary_progress_before_serializing(self):
  for temp in (1,2,3):self.assertEqual(self.lib.save(temp),7|(1<<8)|(1<<16))
 def test_ordinary_card_save_is_unchanged(self):self.assertEqual(self.lib.save(0),99|(1<<16)|(1<<24))
if __name__=='__main__':unittest.main()
