"""Exercise the real phase producer/consumer and their cache-line ownership."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class LoadingTraceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='ms-loading-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  code=r"""
#define TIMEWARP_LIVE_RACING 1
#define MOONSHINE_LOADING_DIAGNOSTICS 1
#include "susamune/loading_trace.h"
#include <cstring>
MsLoadingMailbox boxMemory;unsigned lastPhase,ticks,stores,badOwnership,logged;bool readyValue;
namespace GhostTrace{bool backendIdentity(unsigned &n){n=17;return readyValue;}}
struct Scene{unsigned char mAreaID,mEpisodeID;};struct App{Scene mCurrentScene;}gpApplication;
unsigned OSGetTick(){return ticks;}
#define OS_TIMER_CLOCK 162000000u / 4
void DCInvalidateRange(void*,unsigned){}
void DCStoreRange(void*p,unsigned bytes){unsigned off=(char*)p-(char*)&boxMemory;++stores;if(bytes!=32||off==32||(off&&off<64))++badOwnership;}
struct Writer{struct{unsigned nonce;}response;}writer;
#define WRITER (&writer)
#define LOADBOX (&boxMemory)
int admitted(){return readyValue;}
void sync_before_read(void*,unsigned){}
void sync_after_write(void*p,unsigned n){if(p!=&boxMemory.readSequence||n!=32)++badOwnership;}
void ISOReadTiming(unsigned*out){memset(out,0,16);}
MsLoadingEntry received[16];
void MoonshineNetLogLoading(const MsLoadingEntry*entry,const unsigned*){if(logged<16)received[logged++]=*entry;}
"""
  producer=function((ROOT/'src/loading_trace.cpp').read_text(),'mark')
  producer=producer.replace('*reinterpret_cast<volatile MsLoadingMailbox*>(MS_TRACE_CONTROL_PPC+MS_LOADING_TRACE_OFFSET)','boxMemory')
  code+=producer+function((ROOT/'launcher/kernel/GhostTraceStorage.c').read_text(),'GhostTraceLoadingService')
  code+=r"""
#define API extern "C" __declspec(dllexport)
API void reset(){memset(&boxMemory,0,sizeof(boxMemory));boxMemory.magic=MS_LOADING_TRACE_MAGIC;boxMemory.version=MS_LOADING_TRACE_VERSION;boxMemory.nonce=writer.response.nonce=17;lastPhase=stores=badOwnership=logged=0;readyValue=true;ticks=40500000;gpApplication.mCurrentScene={6,3};}
API void produce(unsigned phase,unsigned value){mark(phase,value);}
API void consume(){GhostTraceLoadingService();}
API unsigned get(unsigned key){return key==0?boxMemory.writeSequence:key==1?boxMemory.readSequence:key==2?boxMemory.dropped:key==3?logged:key==4?badOwnership:stores;}
API unsigned sample(unsigned i,unsigned word){return ((unsigned*)&received[i])[word];}
API void damage(unsigned what){if(what==1)boxMemory.nonce=18;if(what==2)boxMemory.magic=0;if(what==3)boxMemory.version=9;if(what==4)readyValue=false;if(what==5)boxMemory.entries[0].sequence=9;if(what==6)boxMemory.writeSequence=99;}
"""
  (d/'test.cpp').write_text(code)
  p=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-I',str(ROOT/'include'),str(d/'test.cpp'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  if p.returncode:raise RuntimeError(p.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.reset()
 def test_phase_tick_scene_and_clock_are_transferred(self):
  self.lib.produce(1,0x604);self.lib.consume();self.assertEqual(self.lib.get(3),1)
  self.assertEqual([self.lib.sample(0,i) for i in range(8)],[1,1,40500000,0x603,0x604,0,40500000,0]);self.assertEqual(self.lib.get(4),0)
 def test_repeated_wait_is_coalesced_but_new_requests_are_distinct(self):
  self.lib.produce(3,0);self.lib.produce(3,0);self.lib.produce(1,0);self.lib.produce(1,0);self.assertEqual(self.lib.get(0),3)
 def test_full_queue_does_not_overwrite_unread_entries(self):
  for i in range(9):self.lib.produce(1,i)
  self.assertEqual(self.lib.get(0),8);self.assertEqual(self.lib.get(2),1);self.lib.consume();self.assertEqual(self.lib.get(3),8)
  self.assertEqual([self.lib.sample(i,4) for i in range(8)],list(range(8)));self.lib.produce(8,0);self.lib.consume()
  self.assertEqual(self.lib.get(3),9);self.assertEqual(self.lib.sample(8,5),1);self.assertEqual(self.lib.get(4),0)
 def test_wrong_owner_version_or_unavailable_memory_never_writes(self):
  for issue in (1,2,3,4):
   self.lib.reset();self.lib.damage(issue);self.lib.produce(1,0);self.assertEqual(self.lib.get(5),0)
 def test_unpublished_or_invalid_sequences_never_reach_logger(self):
  for issue in (5,6):
   self.lib.reset();self.lib.produce(1,0);self.lib.damage(issue);self.lib.consume();self.assertEqual(self.lib.get(1),0);self.assertEqual(self.lib.get(3),0)
 def test_unknown_phases_do_not_enter_queue(self):
  for phase in (0,9,255):self.lib.produce(phase,0)
  self.assertEqual(self.lib.get(0),0)
if __name__=='__main__':unittest.main()
