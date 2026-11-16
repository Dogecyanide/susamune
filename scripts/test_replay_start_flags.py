"""Initial replay flags change only at the checked, completed start departure."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class StartFlagTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-start-flags-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  code=r"""
#include "susamune/ghost_trace_initial_flags.hxx"
#include "susamune/ghost_trace_decode.hxx"
#include <cstring>
namespace Flags=GhostTraceInitialFlags;
bool enabled,readyValue,ownerValid,threadIdle;int gSetupThread;unsigned writes;
struct App {GhostTraceDecode::Scene mNextScene;}gpApplication;
struct Replay {GhostTraceDecode::StageStart stage;unsigned char flagBytes[896];};
struct State {bool active,started;unsigned error,startEntry;bool haveLiveFlags;void*flagOwner;Replay replay;}s;
bool ready(){return readyValue;}unsigned scenarioCount(unsigned){return 1;}
bool flagOwnerValid(void*){return ownerValid;}bool OSIsThreadTerminated(int*){return threadIdle;}
bool fail(unsigned error,unsigned=0){s.error=error;return false;}
void setFlag(void*,unsigned,int){++writes;}int getFlag(void*,unsigned){return 0;}
Flags::Access flagAccess(void*p){return {p,getFlag,setFlag};}
"""
  code+=function((ROOT/'src/ghost_world_runtime.cpp').read_text(),'prepareStartDeparture')
  code+=r"""
#define API extern "C" __declspec(dllexport)
API unsigned exercise(unsigned condition){
 s={};enabled=readyValue=ownerValid=threadIdle=true;s.active=s.haveLiveFlags=true;
 s.replay.stage.scene=0x101;s.replay.stage.current={1,1,0};gpApplication.mNextScene=s.replay.stage.current;writes=0;
 switch(condition){case 1:enabled=false;break;case 2:s.active=false;break;case 3:s.started=true;break;
 case 4:s.error=7;break;case 5:s.startEntry=1;break;case 6:readyValue=false;break;
 case 7:gpApplication.mNextScene.episode=2;break;case 8:ownerValid=false;break;
 case 9:threadIdle=false;break;case 10:s.haveLiveFlags=false;break;case 11:s.replay.flagBytes[0xdf]=8;break;}
 prepareStartDeparture();return writes|(s.error<<16);
}
"""
  path=d/'test.cpp';path.write_text(code)
  proc=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-I',str(ROOT/'include'),str(path),str(ROOT/'src/ghost_trace_initial_flags.cpp'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  if proc.returncode:raise RuntimeError(proc.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.lib.exercise.restype=C.c_uint;cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_valid_start_applies_checked_snapshot(self):
  value=self.lib.exercise(0);self.assertGreater(value&65535,0);self.assertEqual(value>>16,0)
 def test_live_game_pending_start_and_later_replay_departures_do_not_write(self):
  for case in (1,2,3,4,5,6):self.assertEqual(self.lib.exercise(case)&65535,0)
 def test_destination_mismatch_is_still_rejected(self):self.assertEqual(self.lib.exercise(7),406<<16)
 def test_unowned_busy_or_missing_backup_cannot_apply_flags(self):
  for case in (8,9,10):self.assertEqual(self.lib.exercise(case),418<<16)
 def test_invalid_snapshot_is_rejected_before_any_write(self):self.assertEqual(self.lib.exercise(11),417<<16)
if __name__=='__main__':unittest.main()
