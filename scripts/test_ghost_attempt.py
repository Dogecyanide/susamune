"""MSGT attempt metadata without any resident pose or input banks."""
import ctypes as C
import os,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PRE=r"""
#include <cstring>
#include <cstdio>
#include "susamune/ghost_attempt.hxx"
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_clock.h"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/mem2_map.h"
#include "susamune/susamune_cfg.h"
struct TMarDirector {unsigned _260=1;};static TMarDirector director;
static GhostRecording::Identity identity={1234,1};static unsigned token=77,protectedValue,finishCount,profile;
static bool capturing=true,blocked,sourceOn=true;static unsigned area=3,episode=2;static int parentVariant=2;
static GhostRecording::Info finished;
struct Timer {int qf=0;unsigned serial=1;bool stopped=false,assisted=false;
 bool currentQf(s32*out,bool*stop=nullptr)const{*out=qf;if(stop)*stop=stopped;return true;}
 unsigned attemptSerial()const{return serial;}bool practiceAssisted()const{return assisted;}
};static Timer gQFTTimer;
struct TFlagManager {static TFlagManager *smInstance;int getFlag(unsigned){return parentVariant;}};
static TFlagManager flags;TFlagManager*TFlagManager::smInstance=&flags;
namespace RetailInput {TMarDirector*stageDirector(){return &director;}}
namespace GhostStageContext {bool sample(Sample*out){*out={0,0,0,1,(u8)area,(u8)episode};return true;}}
namespace GhostTrace {bool recording(){return sourceOn;}}
namespace ReplaySession {bool blocksResults(){return blocked;}}
namespace ILing {int pbProfile(){return profile;}int activeEntry(){return 16;}const char*label(int){return "Ricco Harbor 3";}}
namespace LevelWarp {u8 parentArea(u8 value){return value==7?6:255;}}
namespace GhostRecording {
 bool activeIdentity(Identity&out,unsigned&owner){out=identity;owner=token;return ::capturing;}
 bool capturing(){return ::capturing;}
 bool finish(const Info&i){finished=i;++finishCount;::capturing=false;return true;}
 void cancelActive(){::capturing=false;}
 void split(unsigned,const SusamuneGhostSplitSample&){}
 void protect(unsigned owner,unsigned pb){if(owner==token)protectedValue=pb;}
 bool protectedToken(unsigned value){return protectedValue&&value==protectedValue;}
}
"""
POST=r"""
#define API extern "C" __declspec(dllexport)
API void init(){identity={1234,1};token=77;protectedValue=finishCount=profile=0;capturing=sourceOn=true;blocked=false;area=3;episode=2;parentVariant=2;gQFTTimer={};finished={};GhostAttempt::init();}
API void frame(int qf,int stop,int freeze,int assisted){gQFTTimer.qf=qf;gQFTTimer.stopped=stop;gQFTTimer.assisted=assisted;GhostAttempt::frameControl(freeze,assisted);GhostAttempt::update();}
API void scene(unsigned a,unsigned e,int parent){area=a;episode=e;parentVariant=parent;}
API void source(unsigned run,unsigned owner){identity.run=run;token=owner;capturing=true;sourceOn=true;}
API void block(int value){blocked=value;}
API unsigned finishes(){return finishCount;}
API unsigned value(unsigned field){return field==0?finished.startQf:field==1?finished.endQf:field==2?finished.resultQf:field==3?finished.runFlags:field==4?finished.area:field==5?finished.episode:field==6?finished.ownerToken:finished.splitCount;}
API const char*name(){return finished.name;}
API int pb(int qf){return GhostAttempt::markPB(qf);}
API int save(void*out){return GhostAttempt::capture(*static_cast<Ghost::SavestateData*>(out));}
API int valid(void*in){return GhostAttempt::valid(*static_cast<Ghost::SavestateData*>(in));}
API void restore(void*in){++gQFTTimer.serial;GhostAttempt::resetAfterLoad();GhostAttempt::restore(*static_cast<Ghost::SavestateData*>(in));}
API void depart(){GhostAttempt::depart();}
API unsigned bytes(){return sizeof(GhostAttempt::State);}
"""
class GhostAttemptTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-attempt-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  source=(ROOT/'src/ghost_attempt.cpp').read_text(encoding='utf-8');source=re.sub(r'^#include .*$', '',source,flags=re.M)
  source=source.replace('State &s=*reinterpret_cast<State*>(SUSAMUNE_GHOST_TRACKS_PPC_BASE);','State s;')
  (d/'fixture.cpp').write_text(PRE+source+POST,encoding='utf-8');env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-DMOONSHINE_GHOST_TRACE=1','-I',str(ROOT/'include'),'-I',str(ROOT/'include/JSystem'),str(d/'fixture.cpp'),'-o',str(d/'fixture.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.name.restype=C.c_char_p;cls.lib.value.restype=C.c_uint
  for n in ('save','valid','restore'):getattr(cls.lib,n).argtypes=[C.c_void_p]
 def setUp(self):self.lib.init()
 def frame(self,qf,stop=0,freeze=0,assisted=0):self.lib.frame(qf,stop,freeze,assisted)
 def test_normal_result_and_pb_have_stable_source_owner(self):
  self.frame(0);self.frame(4);self.frame(120,1)
  self.assertEqual([self.lib.value(i) for i in range(7)],[0,120,120,0,3,2,77])
  self.assertEqual(self.lib.pb(119),0);self.assertEqual(self.lib.pb(120),1)
  self.assertEqual(self.lib.name(),b'Ricco Harbor 3 - 0:01.001')
 def test_full_route_retains_initial_scene_across_internal_levels(self):
  self.lib.scene(6,3,3);self.frame(0);self.frame(40)
  self.lib.scene(7,0,3);self.frame(80);self.lib.scene(14,0,3);self.frame(160,1)
  self.assertEqual((self.lib.value(4),self.lib.value(5),self.lib.value(2)),(6,3,160))
 def test_no_legacy_ten_minute_duration_limit(self):
  self.frame(0);self.frame(120*660,1);self.assertEqual(self.lib.value(2),79200);self.assertEqual(self.lib.finishes(),1)
 def test_assisted_pause_omits_hold_time_and_cannot_protect_pb(self):
  self.frame(0);self.frame(4);self.frame(104,freeze=1,assisted=1);self.frame(108,1,assisted=1)
  self.assertEqual(self.lib.value(2),8);self.assertEqual(self.lib.value(3)&0x21,0x21);self.assertEqual(self.lib.pb(8),0)
 def test_snapshot_continuation_keeps_origin_and_marks_tas(self):
  self.lib.scene(6,3,3);self.frame(0);self.frame(120)
  saved=C.create_string_buffer(512);self.assertEqual(self.lib.save(saved),1);self.assertEqual(self.lib.valid(saved),1)
  self.lib.restore(saved);self.lib.source(2,88);self.lib.scene(7,0,3);self.frame(124);self.frame(180,1)
  self.assertEqual((self.lib.value(4),self.lib.value(5),self.lib.value(6)),(6,3,88))
  self.assertEqual(self.lib.value(3)&0x23,0x23);self.assertEqual(self.lib.pb(180),0)
 def test_partial_departure_and_replay_isolation(self):
  self.frame(0);self.frame(40);self.lib.depart();self.assertEqual(self.lib.value(2),0xffffffff);self.assertEqual(self.lib.value(3)&8,8)
  self.lib.init();self.lib.block(1);self.frame(40,1);self.assertEqual(self.lib.finishes(),0)
 def test_snapshot_reserved_bytes_and_magic_are_checked(self):
  self.frame(0);self.frame(40);saved=C.create_string_buffer(512);self.assertEqual(self.lib.save(saved),1)
  saved[511]=b'\x01';self.assertEqual(self.lib.valid(saved),0);saved[511]=b'\0';saved[0]=b'\0';self.assertEqual(self.lib.valid(saved),0)
 def test_clean_new_run_does_not_inherit_previous_assistance(self):
  self.frame(0);self.frame(40,1,assisted=1);self.assertEqual(self.lib.value(3)&0x21,0x21)
  self.lib.source(2,88);self.frame(0);self.frame(120,1)
  self.assertEqual(self.lib.value(3),0);self.assertEqual(self.lib.pb(120),1)
 def test_metadata_fits_existing_control_window(self):self.assertLessEqual(self.lib.bytes(),640)
if __name__=='__main__':unittest.main()
