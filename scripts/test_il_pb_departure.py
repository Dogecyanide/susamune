"""Early Shine contact must keep its IL alive until result publication."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class PBDepartureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='early-pb-');cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name)
  il=(ROOT/'src/iling.cpp').read_text();wheel=(ROOT/'src/warp_wheel.cpp').read_text()
  code=r"""
using s32=int;using u32=unsigned;using u8=unsigned char;
struct TMario{enum{STATE_SHINE_C=0x1302};unsigned mState;struct Target{unsigned mObjectID;}*mGrabTarget;};
static TMario::Target shine={0x20000013};static TMario mario;static TMario*gpMarioOriginal=&mario;
static bool live,running,awaiting,ready,stopped;static unsigned finish;
#define sRunning running
#define sAwaitingStageSetup awaiting
#define sAttemptReady ready
#define sFinishKind finish
enum{FINISH_SHINE=0};bool stageObjectsLive(){return live;}
struct Timer{bool currentQf(int*q,bool*s){*q=200;*s=stopped;return true;}}gQFTTimer;
namespace ILing {
"""+function(il,'resultPendingForDeparture')+r"""
int count(){return 200;}int launches;bool start(int,int){++launches;return true;}
}
enum{SETTING_DISABLE_WARPS};struct Settings{bool disabled;bool getBool(int){return disabled;}}gSettings;
namespace StageLoader{bool pending;bool departureResultPending(){return pending;}}
namespace LevelWarp {struct Dest{enum{POST_CORONA=128};u8 area,episode,gameInt3;};void warpToGuarded(Dest,int,bool){}}
struct TGameSequence{enum{AREA_DOLPIC=1};};
enum HeldSessionDeparture{HELD_SESSION_DEPARTURE_NONE,HELD_SESSION_DEPARTURE_WARP,HELD_SESSION_DEPARTURE_IL,HELD_SESSION_DEPARTURE_EXIT_AREA,HELD_SESSION_DEPARTURE_TITLE};
enum PromptAction{PROMPT_NONE,PROMPT_WARP,PROMPT_IL,PROMPT_EXIT_AREA,PROMPT_TITLE};
HeldSessionDeparture sHeldSessionDeparture;LevelWarp::Dest sHeldSessionDest;int sHeldSessionDetail,sArmedILIndex;bool sPendingTitleExit;
static int cancellations,prompts,lastEntry;static bool protectedPB;
struct Menu{void toast(const char*){}};Menu*gMenu;
void cancelExplicitPractice(){++cancellations;running=false;}
bool beginPrompt(PromptAction,LevelWarp::Dest,int entry){++prompts;lastEntry=entry;return protectedPB;}
bool requestILStart(int entry){lastEntry=entry;return ILing::start(entry,0);}
void armExitAreaWarp(LevelWarp::Dest){}
"""+function(wheel,'requestExplicitILStart')
  resolved=function(wheel,'resolveDeferredRestart');resolved=resolved[:resolved.index('    const DeferredRestart deferred')]+"}\n"
  code+=resolved+r"""
#define API extern "C" __declspec(dllexport)
API void reset(){live=running=ready=true;awaiting=stopped=false;finish=0;mario={0,&shine};gpMarioOriginal=&mario;StageLoader::pending=false;gSettings.disabled=false;sHeldSessionDeparture=HELD_SESSION_DEPARTURE_NONE;cancellations=prompts=ILing::launches=0;protectedPB=false;}
API void state(unsigned flags){running=flags&1;ready=flags&2;awaiting=flags&4;live=flags&8;stopped=flags&16;mario.mState=(flags&32)?TMario::STATE_SHINE_C:0;gpMarioOriginal=(flags&64)?nullptr:&mario;finish=(flags&128)?1:0;}
API int pending(){return ILing::resultPendingForDeparture();}
API int request(int entry){return requestExplicitILStart(entry);}
API void resolve(){resolveDeferredRestart();}
API void published(int pb){running=false;protectedPB=pb!=0;}
API unsigned value(unsigned k){return k==0?cancellations:k==1?ILing::launches:k==2?prompts:lastEntry;}
"""
  (d/'test.cpp').write_text(code)
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2',str(d/'test.cpp'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=env)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.reset()
 def test_contact_before_timer_stop_defers_cancellation_and_preserves_selected_il(self):
  self.lib.state(1|2|8|32);self.assertEqual(self.lib.pending(),1);self.assertEqual(self.lib.request(50),1)
  for _ in range(5):self.lib.resolve()
  self.assertEqual(self.lib.value(0),0);self.assertEqual(self.lib.value(1),0)
  self.lib.published(1);self.lib.resolve()
  self.assertEqual(self.lib.value(0),1);self.assertEqual(self.lib.value(1),0);self.assertEqual(self.lib.value(2),1);self.assertEqual(self.lib.value(3),50)
 def test_non_pb_result_releases_exactly_one_departure(self):
  self.lib.state(1|2|8|16);self.lib.request(72);self.lib.published(0);self.lib.resolve()
  self.assertEqual(self.lib.value(1),1);self.assertEqual(self.lib.value(3),72)
 def test_regular_beach_reset_or_inactive_attempt_does_not_wait(self):
  for flags in (1|2|8,2|8|32,1|2|4|8|32,1|2|32,1|2|8|32|64,1|2|8|32|128):
   self.lib.reset();self.lib.state(flags);self.assertEqual(self.lib.pending(),0)
 def test_new_selection_replaces_pending_target_without_canceling_old_result(self):
  self.lib.state(1|2|8|32);self.lib.request(50);self.lib.request(72);self.assertEqual(self.lib.value(0),0)
  self.lib.published(1);self.lib.resolve();self.assertEqual(self.lib.value(3),72)
if __name__=='__main__':unittest.main()
