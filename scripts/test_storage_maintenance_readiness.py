"""Run the real held-director readiness query without changing game state."""
import ctypes as C
from pathlib import Path
import subprocess,tempfile,unittest
from test_practice_tape import function_source
ROOT=Path(__file__).resolve().parents[1]
class MaintenanceReadinessTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
  code=r'''
typedef unsigned char u8;
struct TPauseMenu2{enum{MENU_OPEN=1,MENU_SAVING=2};unsigned mState;};
struct TMarDirector{enum{STATE_NORMAL=4,STATE_PAUSE_MENU=5,STATE_SAVE_CARD=11,STATE_STAGE_EXIT_2=12};unsigned _260;u8 mCurState;TPauseMenu2*mPauseMenu;};
struct TSMSFader{enum{FADE_OFF=0};unsigned mFadeStatus;};
static TPauseMenu2 pauseMenu;static TMarDirector director,other,*gpMarDirector;static TSMSFader fader;
static struct{TMarDirector*mDirector;TSMSFader*mFader;}gpApplication;
enum{CARD_ERROR_BUSY=-1,DEFERRED_RESTART_NONE=0,HELD_SESSION_DEPARTURE_NONE=0};
struct Card{int status;int getLastStatus(){return status;}};static Card card,*gpCardManager;
static bool sArmed,sTailPending,sPendingTitleExit,sHoldNaturalDeparture;static unsigned sDeferredRestart,sHeldSessionDeparture;
'''
  for name in ('bool readyForOnlineRace()', 'bool readyForStorageMaintenance('):code+=function_source(ROOT/'src/warp_wheel.cpp',name)
  code+=r'''
#define API extern "C" __declspec(dllexport)
API void reset(unsigned actual){pauseMenu.mState=1;director._260=1;director.mCurState=(u8)actual;director.mPauseMenu=&pauseMenu;gpMarDirector=&director;gpApplication.mDirector=&director;gpApplication.mFader=&fader;fader.mFadeStatus=0;card.status=0;gpCardManager=&card;sArmed=sTailPending=sPendingTitleExit=sHoldNaturalDeparture=false;sDeferredRestart=sHeldSessionDeparture=0;}
API void damage(unsigned id){switch(id){case 0:sArmed=true;break;case 1:sTailPending=true;break;case 2:sPendingTitleExit=true;break;case 3:sHoldNaturalDeparture=true;break;case 4:sDeferredRestart=1;break;case 5:sHeldSessionDeparture=1;break;case 6:card.status=-1;break;case 7:director._260=0;break;case 8:gpApplication.mDirector=&other;break;case 9:gpApplication.mFader=0;break;case 10:fader.mFadeStatus=1;break;case 11:gpMarDirector=0;break;case 12:director.mPauseMenu=0;break;case 13:pauseMenu.mState=3;break;case 14:pauseMenu.mState=2;break;case 15:gpCardManager=0;break;}}
API unsigned maintenance(unsigned held){return readyForStorageMaintenance((u8)held);}
API unsigned online(){return readyForOnlineRace();}
API unsigned state(){return director.mCurState;}
'''
  folder=Path(cls.temp.name);src=folder/'readiness.cpp';dll=folder/'readiness.dll';src.write_text(code)
  r=subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-O2','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry',str(src),'-o',str(dll)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  cls.lib=C.CDLL(str(dll));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  for name in ('reset','damage','maintenance'):getattr(cls.lib,name).argtypes=[C.c_uint]
  for name in ('state','online','maintenance'):getattr(cls.lib,name).restype=C.c_uint
 def test_borrowed_normal_query_preserves_actual_state_and_online_gate(self):
  self.lib.reset(12);self.assertEqual(self.lib.online(),0);self.assertEqual(self.lib.maintenance(4),1);self.assertEqual(self.lib.state(),12);self.assertEqual(self.lib.online(),0)
 def test_loaded_normal_pause_and_idle_save_are_eligible(self):
  for actual,held in ((4,4),(5,5),(11,11),(12,4),(12,5),(12,11)):
   with self.subTest(actual=actual,held=held):self.lib.reset(actual);self.assertEqual(self.lib.maintenance(held),1);self.assertEqual(self.lib.state(),actual)
 def test_intro_exit_and_unknown_states_refuse(self):
  for state in (0,1,2,3,6,7,8,9,10,12,255):
   with self.subTest(state=state):self.lib.reset(state);self.assertEqual(self.lib.maintenance(state),0)
 def test_actual_state_must_match_or_be_the_borrowed_state(self):
  for actual,held in ((9,4),(5,4),(4,5),(11,4),(1,4)):
   self.lib.reset(actual);self.assertEqual(self.lib.maintenance(held),0);self.assertEqual(self.lib.state(),actual)
 def test_pending_departure_card_setup_and_fader_guards_remain(self):
  for guard in range(12):
   with self.subTest(guard=guard):self.lib.reset(12);self.lib.damage(guard);self.assertEqual(self.lib.maintenance(4),0);self.assertEqual(self.lib.state(),12)
 def test_pause_menu_must_be_stable(self):
  for guard in (12,13):self.lib.reset(12);self.lib.damage(guard);self.assertEqual(self.lib.maintenance(5),0)
  self.lib.reset(12);self.lib.damage(14);self.assertEqual(self.lib.maintenance(5),1)
 def test_absent_card_worker_keeps_retail_no_card_behavior(self):
  self.lib.reset(12);self.lib.damage(15);self.assertEqual(self.lib.maintenance(4),1)
if __name__=='__main__':unittest.main()
