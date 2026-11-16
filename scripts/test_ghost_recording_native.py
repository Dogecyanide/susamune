"""Native saved-recording orchestration with explicit asynchronous service doubles."""
import ctypes as C
import os,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PREAMBLE=r"""
#include <cstring>
#include <cstdio>
#include "susamune/ghost_recording.hxx"
static GhostRecording::Backend installedBackend;
static bool preparing=true,idle=true,pinned=false,world=false,refuse=false,started=false;
static unsigned cachedRun;
static unsigned watchedNonce,watchedRun,watchedRegion,watchedFlags,lookups,erases;
struct Menu {void toast(const char*){}};Menu*gMenu;
"""
STUBS=r"""
namespace GhostRecording {
bool discardHeaderHash(Identity id,unsigned&hash){hash=42;return id.nonce==78&&id.run==cachedRun;}
bool install(Runtime&,unsigned,unsigned,const Backend&b){installedBackend=b;return true;}
}
namespace GhostMemory {bool ready(){return true;}}
namespace GhostTrace {
bool backendIdentity(unsigned&v){v=1234;return true;}
bool continuationPending(){return false;}
bool checkpointSourceOwned(unsigned,unsigned){return pinned;}
}
namespace Ghost {bool observerPreparing(){return preparing;}}
namespace GhostTraceFlat {bool active(){return false;}}
namespace GhostVisualProvider {bool active(){return false;}}
namespace GhostTraceStreamNative {bool idleWriter(unsigned){return idle;}}
namespace GhostWorldRuntime {
bool busy(){return world;}bool active(){return world;}
void status(unsigned*out){std::memset(out,0,128);}
void stop(){world=false;}
bool armFile(unsigned nonce,unsigned run,unsigned region){watchedNonce=nonce;watchedRun=run;watchedRegion=region;world=!refuse;return world;}
bool setSourceRunFlags(unsigned flags){watchedFlags=flags;return !refuse;}
bool startRecorded(){started=true;return !refuse;}
}
namespace GhostReplayReport {unsigned poll(){return 0;}}
namespace GhostTraceBranchIo {
bool configureNative(Client&c,unsigned nonce){c={};c.nonce=nonce;c.phase=IDLE;return true;}
bool lookup(Client&c,unsigned nonce,unsigned run,unsigned game){if(c.phase!=IDLE)return false;++lookups;c.fileNonce=nonce;c.run=run;c.game=game;c.phase=WAITING;return true;}
Phase poll(Client&c){return c.phase;}
const MsTraceLookup*result(const Client&c){return c.phase==READY?&c.value:nullptr;}
bool consume(Client&c){c.phase=IDLE;return true;}
bool erase(Client&c,unsigned nonce,unsigned run,unsigned hash){if(c.phase!=IDLE||hash!=42)return false;++erases;c.fileNonce=nonce;c.run=run;c.phase=WAITING;return true;}
bool cancel(Client&c){c.phase=IDLE;return true;}
}
#define API extern "C" __declspec(dllexport)
API void init(){
 using namespace GhostRecordingNative;
 installed=false;state={};preparing=idle=true;pinned=world=refuse=started=false;
 cachedRun=watchedNonce=watchedRun=watchedRegion=watchedFlags=lookups=erases=0;poll();
}
API int load(unsigned game,int observer,int secondary,int splitCount){
 unsigned char manifest[256]={};MsRecordingPut(manifest+16,78);MsRecordingPut(manifest+20,90);
 MsRecordingPut(manifest+28,0x21);MsRecordingPut(manifest+32,game);manifest[37]=2;manifest[190]=splitCount;
 return installedBackend.load(manifest,256,observer,secondary);
}
API void prepare(int two){GhostRecordingNative::prepareWatch(two);}
API void cancel(){GhostRecordingNative::cancelWatch();}
API void preparing_set(int value){preparing=value;}
API void writer_set(int value){idle=value;}
API void refuse_set(int value){refuse=value;}
API void pin_set(int value){pinned=value;}
API void world_set(int value){world=value;}
API void poll(){GhostRecordingNative::poll();}
API int ready(){return GhostRecordingNative::watchReady();}
API int waiting(){return GhostRecordingNative::watchWaiting();}
API int start(){return GhostRecordingNative::startWatch();}
API unsigned watched(unsigned field){return field==0?watchedNonce:field==1?watchedRun:field==2?watchedRegion:field==3?watchedFlags:started;}
API void cache_hash(unsigned run){cachedRun=run;}
API int discard(unsigned run){return installedBackend.discardRetained({78,run},true);}
API unsigned ops(int deletion){return deletion?erases:lookups;}
API void ack(){GhostRecordingNative::state.files.phase=GhostTraceBranchIo::READY;GhostRecordingNative::state.files.value.file.headerHash=42;}
"""
class NativeRecordingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-native-flow-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  source=(ROOT/'src/ghost_recording_native.cpp').read_text(encoding='utf-8')
  source=source.replace('#include "susamune/menu.hxx"','').replace('#include "Dolphin/printf.h"','').replace('#include "Dolphin/mem.h"','')
  source=source.replace('Native &state=*reinterpret_cast<Native*>(MS_TRACE_CONTROL_PPC+MS_TRACE_NATIVE_OFFSET);','Native state;')
  source=source.replace('unsigned game(){return *reinterpret_cast<volatile const unsigned*>(0x80000000u);}','unsigned game(){return 0x474d5350u;}')
  source=source.replace('auto &runtime=*reinterpret_cast<GhostRecording::Runtime*>(MS_TRACE_CONTROL_PPC+0x2400);','static GhostRecording::Runtime runtime;')
  (d/'fixture.cpp').write_text(PREAMBLE+source+STUBS,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-DMOONSHINE_GHOST_TRACE=1','-DIS_EMULATOR=0','-DTIMEWARP_QF_MEMORY=1','-DSUSAMUNE_VERSION_PAL=1','-I',str(ROOT/'include'),'-I',str(ROOT/'include/JSystem'),str(d/'fixture.cpp'),'-o',str(d/'fixture.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.init()
 def load(self):self.lib.prepare(0);self.assertEqual(self.lib.load(0x474d5350,1,0,0),1)
 def test_splitless_clip_uses_its_recorded_destination_and_identity(self):
  self.load();self.assertEqual(self.lib.start(),1)
  self.assertEqual([self.lib.watched(i) for i in range(5)],[78,90,3,0x21,1]);self.assertEqual(self.lib.ready(),0)
 def test_writer_must_close_before_playback_uses_shared_buffers(self):
  self.load();self.lib.writer_set(0);self.assertEqual(self.lib.waiting(),1);self.assertEqual(self.lib.start(),0)
  self.assertEqual(self.lib.watched(0),0);self.lib.writer_set(1);self.assertEqual(self.lib.start(),1)
 def test_cancelled_or_wrong_region_reply_never_arms(self):
  self.lib.preparing_set(0);self.assertEqual(self.lib.load(0x474d5350,1,0,1),0)
  self.lib.preparing_set(1);self.assertEqual(self.lib.load(0x474d534a,1,0,1),0);self.assertEqual(self.lib.ready(),0)
 def test_watch_two_and_racing_are_refused_until_supported(self):
  self.lib.prepare(1);self.assertEqual(self.lib.load(0x474d5350,1,0,1),0)
  self.lib.prepare(0)
  for observer,secondary in ((0,0),(1,1)):self.assertEqual(self.lib.load(0x474d5350,observer,secondary,1),0)
 def test_cancel_releases_pending_watch_and_failed_arm_is_recoverable(self):
  self.load();self.lib.refuse_set(1);self.assertEqual(self.lib.start(),0);self.lib.cancel();self.assertEqual(self.lib.ready(),0)
  self.lib.refuse_set(0);self.load();self.assertEqual(self.lib.start(),1);self.lib.cancel();self.lib.poll();self.load()
 def test_discard_waits_for_matching_lookup_then_delete_ack(self):
  self.assertEqual(self.lib.discard(90),0);self.assertEqual(self.lib.ops(0),1)
  self.lib.ack();self.assertEqual(self.lib.discard(91),0);self.assertEqual(self.lib.ops(1),0)
  self.assertEqual(self.lib.discard(90),0);self.assertEqual(self.lib.ops(1),1)
  self.lib.ack();self.assertEqual(self.lib.discard(90),1)
 def test_completed_draft_skips_only_the_redundant_lookup(self):
  self.lib.cache_hash(90);self.assertEqual(self.lib.discard(90),0)
  self.assertEqual(self.lib.ops(0),0);self.assertEqual(self.lib.ops(1),1)
  self.assertEqual(self.lib.discard(91),0)
  self.lib.ack();self.assertEqual(self.lib.discard(90),1)
 def test_checkpoint_pin_and_playback_prevent_source_deletion(self):
  self.lib.world_set(1);self.assertEqual(self.lib.discard(90),0);self.assertEqual(self.lib.ops(0),0)
  self.lib.world_set(0);self.lib.pin_set(1);self.assertEqual(self.lib.discard(90),1);self.assertEqual(self.lib.ops(1),0)
if __name__=='__main__':unittest.main()
