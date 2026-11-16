"""Exercise the real spawn/nozzle boundaries and replay-camera clock expression."""
from pathlib import Path
import ctypes as C, os, re, subprocess, tempfile, unittest
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class DepartureBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-departure-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  il=(ROOT/'src/iling.cpp').read_text();warp=(ROOT/'src/warp_wheel.cpp').read_text();camera=(ROOT/'src/replay_camera.cpp').read_text()
  code=r"""
using u8=unsigned char;
struct TApplication{enum{CONTEXT_DIRECT_STAGE=5};};struct TGameSequence{enum{AREA_AIRPORT=0};};
struct Scene{u8 mAreaID,mEpisodeID;unsigned short mFlag;};
struct App{unsigned mContext;Scene mCurrentScene,mNextScene;}gpApplication;
namespace LevelWarp{struct Dest{u8 area,episode,gameInt3;};}
struct Director{unsigned _260,state;};Director director,*gpMarDirector=&director;
struct Flags{int value,writes;void setFlag(unsigned id,int v){if(id==0x40004){value=v;++writes;}}};
struct TFlagManager{static Flags*smInstance;};Flags flags;Flags*TFlagManager::smInstance=&flags;
struct Fludd{u8 mSecondNozzle;};Fludd fludd;struct Mario{Fludd*mFludd;}mario{&fludd},*gpMarioOriginal=&mario;
bool sRunning,sTemporaryRocketActive,sBowserNozzleShieldActive,sRocketEquipPending,sBowserNozzleShieldPending;
bool sAttemptReady,sAwaitingStageSetup,sTransitionPending,sRecordsEligible,sChildRetryContinuation,sNativeIgt,sSecretOnly;
int sSavedSecondNozzleFlag,sSavedBowserNozzleFlag,sSelectedEntry,sAssistReasons,sRejectionCause;
u8 sSavedSecondNozzle;enum{REJECT_PRACTICE};
bool stageObjectsLive(){return gpApplication.mContext==5&&director._260&&director.state>=2;}
bool isPlazaEntry(int){return false;}void restorePlazaSetupState(){}void restorePlazaStoryFlags(){}void restoreOverlayFlags(bool){}
namespace Records{void onILAttemptEnded(){}}namespace StageLoader{void onILAttemptEnded(){}}namespace SplitStats{void onILAttemptEnded(){}}
"""
  code+=function(il,'clearAttempt')+function(il,'onDeparture')+function(warp,'overrideSourceForDefaultSpawn')+function(camera,'clamp')
  expr=re.search(r'const float dt=([^;]+);',camera).group(1)
  code+=r"""
#define API extern "C" __declspec(dllexport)
API unsigned nozzle(unsigned kind,int original,unsigned ready,unsigned context,bool clearFirst){
 flags={4,0};director={ready,4};gpApplication.mContext=context;
 sTemporaryRocketActive=kind==1;sBowserNozzleShieldActive=kind==2;
 sSavedSecondNozzleFlag=sSavedBowserNozzleFlag=original;sSavedSecondNozzle=1;fludd.mSecondNozzle=3;
 sRocketEquipPending=sBowserNozzleShieldPending=true;sRunning=true;
 if(clearFirst){clearAttempt();flags.value=4;flags.writes=0;}
 onDeparture();return unsigned(flags.value)|(unsigned(flags.writes)<<8)|(unsigned(sTemporaryRocketActive)<<16)|(unsigned(sBowserNozzleShieldActive)<<17);
}
API unsigned spawn(unsigned destination,unsigned source){
 gpApplication.mCurrentScene={9,3,77};gpApplication.mNextScene={u8(destination),0,0};
 overrideSourceForDefaultSpawn({u8(source),0,0});const auto &p=gpApplication.mCurrentScene;
 return p.mAreaID|(unsigned(p.mEpisodeID)<<8)|(unsigned(p.mFlag)<<16);
}
#define OS_BUS_CLOCK bus
#define OS_TIMER_CLOCK OS_BUS_CLOCK / 4
API float step(unsigned bus,unsigned elapsed,bool ticked){
 struct {unsigned tick;bool ticked;}s={0,ticked};unsigned now=elapsed;
"""+'const float dt='+expr+';return dt;}\n'
  (folder/'test.cpp').write_text(code)
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static',str(folder/'test.cpp'),'-o',str(folder/'test.dll')],capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(folder/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.nozzle.argtypes=[C.c_uint,C.c_int,C.c_uint,C.c_uint,C.c_bool];cls.lib.spawn.argtypes=[C.c_uint,C.c_uint];cls.lib.step.argtypes=[C.c_uint,C.c_uint,C.c_bool];cls.lib.step.restype=C.c_float
 def test_plaza_can_request_airstrip_exit_spawn(self):self.assertEqual(self.lib.spawn(1,0),0)
 def test_airstrip_destination_keeps_live_source(self):self.assertEqual(self.lib.spawn(0,0),9|(3<<8)|(77<<16))
 def test_temporary_nozzle_survives_early_attempt_cleanup(self):self.assertEqual(self.lib.nozzle(1,0,1,5,True),1<<8)
 def test_bowser_restores_original_choice_after_retail_departure(self):
  for value in [0,4]:self.assertEqual(self.lib.nozzle(2,value,1,5,False),value|(1<<8))
 def test_unowned_or_unloaded_state_is_not_modified(self):
  self.assertEqual(self.lib.nozzle(0,0,1,5,False),4)
  self.assertEqual(self.lib.nozzle(2,0,0,5,False),4|(1<<17))
  self.assertEqual(self.lib.nozzle(2,0,1,6,False),4|(1<<17))
 def test_camera_tick_clock_has_correct_precedence(self):
  self.assertAlmostEqual(self.lib.step(162000000,1350000,True),1/30,places=6)
  self.assertAlmostEqual(self.lib.step(243000000,1012500,True),1/60,places=6)
  self.assertAlmostEqual(self.lib.step(162000000,162000000,True),.1,places=6)
  self.assertAlmostEqual(self.lib.step(162000000,0,False),1/30,places=6)
if __name__=='__main__':unittest.main()
