"""Execute actual staged producer/manager functions against the actual ARM writer."""
import ctypes as C,io,json,os,re,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
STAGED=Path(__file__).resolve().parents[1];ROOT=STAGED
while not (ROOT/"scripts/ghost_kernel_fixture.h").exists():ROOT=ROOT.parent
class Overlay:
 def __truediv__(self,name):
  p=STAGED/name;return p if p.exists() else ROOT/name
P=Overlay()
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(STAGED/'scripts'))
from test_ghost_trace_storage import ADAPTER,EXPORTS,writer_source
ARM=r"""
__declspec(dllexport) void requests(const void*p,const void*b){memcpy(&traceMailbox.request,p,32);memcpy(&branchMailbox,b,128);}
__declspec(dllexport) void rawChunk(unsigned index,const void*h,const void*p){memcpy(&traceMailbox.chunks[index],h,32);unsigned n=traceMailbox.chunks[index].bytes;if(n<=MS_TRACE_BUFFER_BYTES)memcpy(traceBuffers[index]+32,p,n);}
__declspec(dllexport) const void*fence(void){return &traceFence;}
__declspec(dllexport) const void*branchResponse(void){return &branchMailbox.response;}
__declspec(dllexport) unsigned written(void){return writeBytes;}
__declspec(dllexport) const void*path(const char*path,unsigned*n){int i=lookup(path);if(i<0){*n=0;return NULL;}*n=testFiles[i].size;return testFiles[i].bytes;}
__declspec(dllexport) void syncFail(unsigned value){failSync=value;}
"""
PRE=r"""
#define MOONSHINE_GHOST_TRACE 1
#define TIMEWARP_LIVE_RACING 1
#define IS_EMULATOR 0
#include <cstring>
typedef int s32;
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_trace_observation.h"
#include "susamune/ghost_spin_observation.hxx"
#include "susamune/ghost_provenance.h"
#include "susamune/ghost_trace_compression.h"
#include "susamune/ghost_recording.hxx"
namespace TGameSequence {enum Area {AREA_NONE=0xA,AREA_TEST10=0xC,AREA_OPTION=0xF};}
namespace LevelWarp {unsigned char parentArea(unsigned char area){return area==7||area==14||area==40?6:255;}}
namespace GhostRecordingNative {void poll(){}}
namespace GhostTraceBranchOwner { State state; }
namespace StateSaveProbe { bool enabled(){return false;} }
namespace GhostMemory { bool ready(){return true;} bool admitted(){return true;} }
namespace GhostWorldRuntime { bool busy(){return false;} bool active(){return false;} bool armFile(unsigned,unsigned,unsigned){return false;} bool startAt(int){return false;} void stop(){} }
namespace LiveRaceSession {struct Session {struct Info {bool connected;const char*remoteName;}info;};}
static unsigned MSRRead32(const unsigned char*p){return MsObservationWord(p);}
struct FakeMenu {void toast(const char*){}};static FakeMenu*gMenu;
struct FakeApplication {struct Scene {unsigned char mAreaID,mEpisodeID;}mCurrentScene;}gpApplication={{2,0}};
namespace GhostSpinObservation {bool install(Queue&q,Mode m){q.mode=m;return true;}bool uninstall(Mode){return true;}}
namespace ILing {void captureTraceContext(unsigned*out){std::memset(out,0,24);}}
namespace ReplaySession {bool blocksResults(){return false;}}
namespace PracticeSession {bool assisted(){return false;}}
enum {SETTING_FMV_SKIPS=5};static struct FakeSettings {unsigned get(unsigned){return 1;}}gSettings;
namespace GhostTraceHooks { unsigned capabilities(){return 0;} }
namespace Ghost {bool observerActive(){return false;}bool observerPreparing(){return false;}bool observerStatsSuppressed(){return false;}}
namespace GhostSimulation {struct Snapshot{unsigned char bytes[64];};}
struct TMarioGamePad {char bytes[0xf0];};struct TMarioControllerWork {char bytes[36];};
static unsigned testGame=0x474d534a,testSeed=0x98765432,testNonce=0x12345678;
struct FakeTimer {bool currentQf(int*p){*p=120;return true;}unsigned attemptSerial(){return 44;}bool practiceAssisted(){return false;}}gQFTTimer;
namespace GhostStageContext {struct Sample{};bool sample(Sample*){return false;}unsigned generation(){return 0;}}
static bool OSDisableInterrupts(){return true;}static void OSRestoreInterrupts(bool){}
static void DCStoreRange(void*,unsigned){}static void DCInvalidateRange(void*,unsigned){}
namespace GhostTraceFlat {bool active(){return false;}}
namespace GhostTrace {
unsigned prepareNextRun(unsigned){return 0;}unsigned discardOperation(){return MS_TRACE_DISCARD;}unsigned retainOperation(){return MS_TRACE_KEEP;}bool fastPreparedRun(unsigned){return false;}void revokePreparation(){}
namespace {
struct ContactSample {unsigned words[22];};struct CameraSample {unsigned words[22];};
struct StageStart {unsigned words[16];unsigned char flags[0x380];unsigned npcPollutionPhase,observations;};
"""
GLOBALS=r"""
static State s;static MsTraceMailbox mailbox;static bool bootReady;
static CheckpointController*checkpoints;static MsTraceFenceInfo hostFence;static MsTraceBranchMailbox hostBranch;
static unsigned char actorBytes[MOONSHINE_GHOST_ARAM_BYTES];static unsigned char*actors=actorBytes;
static unsigned char dataBuffers[2][MS_TRACE_BUFFER_BYTES];
static unsigned char*buffer(unsigned index){return dataBuffers[index];}
static void checkpointPoll();static unsigned checkpointBoundary();static bool sourcePinned();static bool forkBlocksCapture();static bool issueCheckpointFence();static bool atomicContinuationPending();
static void provenance(bool);static void contextObservation();static void drainSpin();static void append(unsigned,const void*,unsigned);
static void flushRandom();static void beginAttempt(){s.attempt=99;s.introStage=0;}
"""
POST=r"""
static GhostRecording::Runtime managerRuntime;
static GhostTrace::CheckpointSnapshot snapshots[3];
static bool mockLoad(const void*,unsigned,bool,bool){return false;}static bool mockCheckpoint(GhostRecording::Checkpoint&,bool){return false;}static int mockDiscard(GhostRecording::Identity,bool){return 0;}
#define API extern "C" __declspec(dllexport)
API int reset(){
 using namespace GhostTrace;s={};mailbox={};hostFence={};hostBranch={};checkpoints=nullptr;bootReady=true;s.magic=MS_TRACE_MAGIC;
 mailbox.response={MS_TRACE_MAGIC,MS_TRACE_VERSION,testNonce,0,MS_TRACE_IDLE,0,0,0};
 hostBranch.response={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,testNonce,0,0,{0,0,0}};poll();
 memset(snapshots,0,sizeof(snapshots));GhostRecording::runtime=nullptr;
 GhostRecording::Backend b={mockLoad,mockCheckpoint,mockDiscard};return GhostRecording::install(managerRuntime,testNonce,15,b);
}
API int resetAt(unsigned nonce){testNonce=nonce;return reset();}
API int exportRaw(unsigned slot,void*out){auto value=snapshots[slot];if(!GhostTrace::checkpointExport(value))return 0;memcpy(out,&value,96);return 1;}
API int adopt(const void*p,unsigned slot,unsigned generation){if(slot>=3||!GhostRecording::importCheckpoint(*(const GhostTrace::CheckpointSnapshot*)p)||!GhostRecording::checkpointSaved(slot,generation))return 0;memcpy(snapshots+slot,p,96);return 1;}
API int externalLoad(const void*p,unsigned generation){
 const auto&v=*(const GhostTrace::CheckpointSnapshot*)p;
 if(!GhostRecording::checkpointLoadPending()&&!GhostRecording::importCheckpoint(v))return -1;
 return GhostRecording::prepareCheckpointLoad(v,3,generation);
}
API int start(){return GhostRecording::beforeDeparture(0x200,true);}
API void enter(){GhostTrace::s.waitingStage=false;GhostRecording::poll();}
API void step(){GhostTrace::service();GhostRecording::poll();}
API const void*request(){return &GhostTrace::mailbox.request;}
API const void*chunk(unsigned index){return &GhostTrace::mailbox.chunks[index];}
API const void*buffer(unsigned index){return GhostTrace::dataBuffers[index];}
API const void*branch(){return &GhostTrace::hostBranch;}
API void receipts(const void*r,const void*f,const void*b){memcpy(&GhostTrace::mailbox.response,r,64);memcpy(&GhostTrace::hostFence,f,32);memcpy(&GhostTrace::hostBranch.response,b,32);}
API int record(unsigned frame,unsigned tick,unsigned value){using namespace GhostTrace;if(!recording())return 0;s.frame=frame;s.tick=tick;unsigned char payload[32]={};MsTracePut(payload,value);append(MS_TRACE_FRAME,payload,32);return 1;}
API int save(unsigned slot,unsigned generation){return slot<3&&GhostRecording::captureCheckpoint(snapshots[slot])&&snapshots[slot].magic&&GhostRecording::checkpointSaved(slot,generation);}
API const void*snapshot(unsigned slot){return snapshots+slot;}
API int abandonSave(){GhostRecording::CheckpointSave transaction;GhostTrace::CheckpointSnapshot copy;return transaction.capture(copy);}
API int exportable(unsigned slot){auto copy=snapshots[slot];return GhostRecording::checkpointExport(copy);}
API int ready(unsigned slot){return GhostTrace::checkpointReady(snapshots[slot]);}
API int load(unsigned slot,unsigned generation){return GhostRecording::prepareCheckpointLoad(snapshots[slot],slot,generation);}
API int commit(){return GhostRecording::commitCheckpointLoad();}
API int untrackedLoad(unsigned commit){GhostRecording::CheckpointLoad load;return !commit||load.commit();}
API void audio(unsigned actions){GhostRecording::noteContinuationAudio(actions);}
API int hold(){return GhostRecording::checkpointLoadPending();}
API void cancel(){GhostRecording::cancelCheckpointLoad();}
API void clear(unsigned slot,unsigned generation){GhostRecording::checkpointCleared(slot,generation);}
API unsigned run(){return GhostTrace::s.run;}
API unsigned phase(){return GhostTrace::checkpoints->phase;}
API unsigned frame(){return GhostTrace::s.frame;}
API unsigned tick(){return GhostTrace::s.tick;}
API unsigned owned(unsigned run){return GhostTrace::checkpointSourceOwned(0x12345678,run);}
API unsigned pinrefs(){unsigned count=0;for(auto&p:managerRuntime.checkpoints.pins.pins)count+=p.references;return count;}
API void stop(){GhostTrace::reset();}
API int pendingSpin(unsigned caller,unsigned result,unsigned direction){using namespace GhostTrace;if(!recording()||s.spin.count>=16)return 0;auto&q=s.spin;q.mode=GhostSpinObservation::RECORD;q.events[q.count++]={++q.sequence,caller,result,direction,1};return 1;}
API unsigned pendingSpins(){return GhostTrace::s.spin.count;}
API unsigned stateBytes(){return sizeof(GhostTrace::State);}
API void sourceFlags(unsigned flags){GhostTrace::s.runFlags=flags;}
API int monitor(unsigned op){unsigned char packet[16]={};MsTracePut(packet,0x4d4d5131);MsTracePut(packet+8,op);LiveRaceSession::Session session={{true,"Memory monitor"}};return GhostTrace::receive(session,packet,sizeof(packet));}

API void abandon(){GhostRecording::cancelActive();}
API int finish(){return GhostTrace::finishOrdinary(GhostTrace::s.run);}
API int finishManaged(){GhostRecording::Info info={};info.ownerToken=44;info.endQf=info.resultQf=200;info.area=2;info.parent=255;memcpy(info.name,"Bianco 1",8);return GhostRecording::finish(info);}
API int queue_finish(){return GhostTrace::queueOrdinaryFinish(GhostTrace::s.run);}
API void next_frame(){GhostTrace::flushOrdinaryFinish();GhostTrace::service();}
API int recording(){return GhostTrace::recording();}
API void background(){GhostTrace::flushBackground();GhostTrace::service();}
API unsigned queued(unsigned index){return GhostTrace::s.used[index&1u];}
API unsigned sealed(unsigned index){return GhostTrace::s.sealed[index&1u];}
API unsigned activeBuffer(){return GhostTrace::s.active;}
API int bulk(unsigned first,unsigned count){for(unsigned i=0;i<count;++i)if(!record(first+i,(first+i)*4,first+i))return 0;return 1;}
API void poisonBaselines(){using namespace GhostTrace;s.inputSeen=s.cameraSeen=s.mirrorSeen=true;s.contactMask=~0u;s.actorSerial=777;for(auto&v:s.blobPointer)v=1;memset(actors,1,MOONSHINE_GHOST_ARAM_BYTES);}
API int freshBaselines(){using namespace GhostTrace;if(s.inputSeen||s.cameraSeen||s.mirrorSeen||s.contactMask||s.actorSerial)return 0;for(auto v:s.blobPointer)if(v)return 0;for(unsigned i=0;i<MOONSHINE_GHOST_ARAM_BYTES;++i)if(actors[i])return 0;return 1;}
API unsigned metadataRun(){auto*d=GhostRecordingLifecycle::active(managerRuntime.state);return d?d->identity.run:0;}
API unsigned runtimeBytes(){return sizeof(managerRuntime);}
"""
def function(source,prefix):
 start=source.index(prefix);brace=source.index('{',start);at=brace+1;depth=1
 while depth:
  depth+=(source[at]=='{')-(source[at]=='}');at+=1
 return source[start:at]+'\n'
def producer_source():
 source=(P/'src/ghost_trace.cpp').read_text();state=source[source.index('struct State {'):source.index('\nstruct Actor {')]
 internal=''.join(function(source,p) for p in ('void poll()','bool automaticReply()','bool automaticWritable()','void command(','void seal()','void stop(','unsigned captureCapabilities()'))
 internal+=function(source,'void append(').replace('void append(','void appendNative(',1)
 # Native unsigned arrays are big-endian on PPC; the host adapter preserves that wire representation.
 internal+=r'''void append(unsigned kind,const void*data,unsigned bytes){
 if((kind==MS_TRACE_OBSERVATION||kind==MS_TRACE_PROVENANCE)&&bytes<=104&&!(bytes&3u)){
  unsigned char target[104];for(unsigned at=0;at<bytes;at+=4){unsigned word;memcpy(&word,(const unsigned char*)data+at,4);MsTracePut(target+at,word);}appendNative(kind,target,bytes);
 }else appendNative(kind,data,bytes);
}
'''
 internal+=''.join(function(source,p) for p in ('void flushRandom() {','void flushBackground()','void service()','void provenance(bool force)','void contextObservation() {','void drainSpin() {'))
 public=''.join(function(source,p) for p in ('bool recording()','void reset()','__attribute__((noinline)) bool initializeCapture(','__attribute__((noinline)) bool startCapture(','__attribute__((noinline)) bool armStage(','__attribute__((noinline)) bool stageArmed()','bool backendIdentity(','bool armOrdinaryStage(','bool armAutomaticStage(','bool automaticStartPending()','unsigned ownedRun()','unsigned failure(','bool finishOrdinary(','bool queueOrdinaryFinish(','void flushOrdinaryFinish()','bool discarded(','bool retainedFile(','bool completion(','unsigned completedRunFlags(','bool receive('))
 public=public.replace('*reinterpret_cast<volatile const unsigned*>(0x80000000u)','testGame')
 code=PRE+state+GLOBALS+internal+'}\n'+public
 inc=(P/'src/ghost_trace_producer.inc').read_text().replace('volatile MsTraceFenceInfo &fenceMailbox=*reinterpret_cast<volatile MsTraceFenceInfo*>(MS_TRACE_CONTROL_PPC+MS_TRACE_FENCE_INFO_OFFSET);','volatile MsTraceFenceInfo &fenceMailbox=hostFence;').replace('volatile MsTraceBranchMailbox &branchMailbox=*reinterpret_cast<volatile MsTraceBranchMailbox*>(MS_TRACE_CONTROL_PPC+MS_TRACE_BRANCH_MAILBOX_OFFSET);','volatile MsTraceBranchMailbox &branchMailbox=hostBranch;')
 inc=inc.replace('s32 qf=0','int qf=0').replace('*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED)','testSeed')
 code+=inc+'}\n'+re.sub(r'^#include .*$', '',(P/'src/ghost_recording.cpp').read_text(),flags=re.M)+POST
 return code
class NativeProducerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-producer-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text().replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 50').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 20').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 2000000').replace('f_close(','fixture_close(').replace('f_rename_char(','fixture_rename(')
  (d/'arm.c').write_text('#define MOONSHINE_GHOST_TRACE 1\n'+fixture+ADAPTER+writer_source(P)+EXPORTS.replace('failWriteAfter=0xffffffffu;','failSync=0;failWriteAfter=0xffffffffu;')+ARM)
  (d/'producer.cpp').write_text(producer_source());env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  includes=['-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune')]
  for name,command in [('arm',['C:/msys64/mingw64/bin/gcc.exe','-std=gnu99','-DMOONSHINE_GHOST_TRACE=1',str(d/'arm.c'),str(ROOT/'launcher/kernel/GhostTraceCompression.c')]),('producer',['C:/msys64/mingw64/bin/g++.exe','-std=c++17',str(d/'producer.cpp'),str(ROOT/'src/ghost_trace_checkpoint.cpp')])]:
   r=subprocess.run(command+['-shared','-static','-O2','-fno-builtin']+includes+['-o',str(d/(name+'.dll'))],capture_output=True,text=True,env=env)
   if r.returncode:raise RuntimeError(r.stderr)
   lib=C.CDLL(str(d/(name+'.dll')));setattr(cls,name,lib);cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
  for name in ('request','chunk','buffer','branch','snapshot'):getattr(cls.producer,name).restype=C.c_void_p
  cls.producer.run.restype=cls.producer.metadataRun.restype=C.c_uint
  cls.producer.receipts.argtypes=[C.c_void_p]*3
  cls.producer.exportRaw.argtypes=[C.c_uint,C.c_void_p];cls.producer.adopt.argtypes=[C.c_void_p,C.c_uint,C.c_uint];cls.producer.externalLoad.argtypes=[C.c_void_p,C.c_uint]
  cls.producer.resetAt.argtypes=[C.c_uint]
  for name in ('response','fence','branchResponse','path'):getattr(cls.arm,name).restype=C.c_void_p
  cls.arm.requests.argtypes=[C.c_void_p]*2;cls.arm.rawChunk.argtypes=[C.c_uint,C.c_void_p,C.c_void_p];cls.arm.path.argtypes=[C.c_char_p,C.POINTER(C.c_uint)]
 def setUp(self):
  self.arm.identity(0x474d534a,0x12345678);self.arm.reset();self.assertEqual(self.producer.resetAt(0x12345678),1);self.assertEqual(self.producer.start(),1);self.pump(3);self.producer.enter();self.assertEqual(self.producer.recording(),1)
 def response(self):return struct.unpack('<8I',C.string_at(self.arm.response(),32))
 def pump(self,count=1):
  for _ in range(count):
   self.producer.step();self.arm.requests(self.producer.request(),self.producer.branch())
   for i in range(2):self.arm.rawChunk(i,self.producer.chunk(i),self.producer.buffer(i))
   self.arm.run(1);self.producer.receipts(self.arm.response(),self.arm.fence(),self.arm.branchResponse());self.producer.step()
 def settled(self,slot=0,gen=11):
  for _ in range(100):
   result=self.producer.load(slot,gen)
   if result:return result
   self.pump()
  self.fail('continuation did not settle')
 def data(self,name):
  count=C.c_uint();p=self.arm.path(('/Moonshine data/ghosts/recordings/'+name).encode(),C.byref(count));return C.string_at(p,count.value) if p else None
 def file(self,run,suffix='msgt'):return self.data(f'trace_12345678_{run:08X}.{suffix}')
 def checkpoint(self,slot=0,gen=11):
  self.assertEqual(self.producer.record(10,40,100),1);self.assertEqual(self.producer.save(slot,gen),1);self.assertEqual(self.producer.ready(slot),0)
 def records(self,data):
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload
  stream=io.BytesIO(data);stream.seek(64);result=[]
  while True:
   raw=stream.read(32);self.assertEqual(len(raw),32);header=struct.unpack('>8I',raw)
   if header[0]==0x444f4e45:
    self.assertEqual(stream.read(),b'');return result
   body=chunk_payload(stream,header,3);at=0
   while at<len(body):
    kind,size,frame,tick=struct.unpack_from('>HHII',body,at);start=at+12
    self.assertLessEqual(start+size,len(body));result.append((kind,frame,tick,body[start:start+size]));at=start+size
 def test_monitor_keep_drains_final_spin_and_emits_terminal_context_and_provenance(self):
  self.assertEqual(self.producer.record(10,40,100),1);run=self.producer.run()
  self.producer.sourceFlags(0x21);self.assertEqual(self.producer.pendingSpin(3,1,2),1)
  self.assertEqual(self.producer.monitor(4),1);self.assertEqual(self.producer.pendingSpins(),0)
  self.assertEqual(self.producer.recording(),0);self.pump(30);self.assertEqual(self.response()[4],4)
  records=self.records(self.file(run));literal=[(i,row) for i,row in enumerate(records) if row[0]==29 and struct.unpack_from('>I',row[3],4)[0]==4]
  self.assertEqual(len(literal),1);index,row=literal[0];self.assertEqual(row[1:3],(10,40))
  self.assertEqual(struct.unpack('>7I',row[3]),(1,4,1,3,1,2,1))
  contexts=[i for i,row in enumerate(records) if row[0]==29 and struct.unpack_from('>I',row[3],4)[0]==1]
  provenance=[(i,struct.unpack('>2I',row[3])) for i,row in enumerate(records) if row[0]==28]
  self.assertTrue(contexts);self.assertGreater(contexts[-1],index);self.assertGreater(provenance[-1][0],contexts[-1])
  self.assertEqual(provenance[-1][1],(1,0x21))
  flags=0
  for _,(_,value) in provenance:self.assertEqual(flags&~value,0);flags=value
 def test_monitor_discard_of_pinned_source_keeps_final_spin_without_losing_checkpoint(self):
  self.checkpoint();self.pump(12);run=self.producer.run()
  self.assertEqual(self.producer.record(11,44,101),1);self.assertEqual(self.producer.pendingSpin(9,0,4),1)
  self.assertEqual(self.producer.monitor(5),1);self.assertEqual(self.producer.pendingSpins(),0)
  self.pump(30);self.assertEqual(self.response()[4],4);self.assertEqual(self.producer.ready(0),1)
  spins=[row for row in self.records(self.file(run)) if row[0]==29 and struct.unpack_from('>I',row[3],4)[0]==4]
  self.assertEqual([(row[1],row[2],struct.unpack('>7I',row[3])) for row in spins],[(11,44,(1,4,1,9,0,4,1))])
 def test_checkpoint_prefix_includes_pending_spin_before_fence_receipt(self):
  self.assertEqual(self.producer.record(10,40,100),1);run=self.producer.run()
  self.assertEqual(self.producer.pendingSpin(1,1,3),1);self.assertEqual(self.producer.save(0,11),1)
  self.assertEqual(self.producer.pendingSpins(),0);snapshot=struct.unpack('<24I',C.string_at(self.producer.snapshot(0),96))
  self.assertEqual(snapshot[8],44+40);self.pump(12);self.assertEqual(self.producer.ready(0),1)
  data=self.file(run,'part');self.assertIsNotNone(data)
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload,checksum
  stream=io.BytesIO(data);stream.seek(64);header=struct.unpack('>8I',stream.read(32));body=chunk_payload(stream,header,3)
  self.assertEqual(len(body),snapshot[8]);self.assertEqual(checksum(body),snapshot[9])
  self.assertEqual(struct.unpack_from('>HHII',body,44),(29,28,10,40))
  self.assertEqual(struct.unpack_from('>7I',body,56),(1,4,1,1,1,3,1))
 def test_native_trace_state_still_fits_fixed_private_window(self):
  self.assertLessEqual(self.producer.stateBytes(),4096)
 def test_background_flush_starts_io_before_the_half_megabyte_bank_is_full(self):
  self.assertEqual(self.producer.bulk(1,3000),1);self.assertEqual(self.producer.queued(0),132000)
  self.producer.background();self.assertEqual(self.producer.sealed(0),1);self.assertEqual(self.producer.activeBuffer(),1)
  self.pump(16);self.assertEqual(self.response()[6],1);self.assertEqual(self.producer.queued(0),0)
  self.assertEqual(self.producer.recording(),1)
  self.assertEqual(self.producer.record(3001,12004,55),1)
  self.assertEqual(self.producer.save(0,11),1);self.pump(12);self.assertEqual(self.producer.ready(0),1)
 def test_slow_sd_keeps_the_full_other_bank_available_and_preserves_record_order(self):
  self.assertEqual(self.producer.bulk(1,3000),1);self.producer.background()
  self.assertEqual(self.producer.bulk(3001,10000),1);self.producer.background()
  self.assertEqual(self.producer.activeBuffer(),1);self.assertEqual(self.producer.sealed(1),0)
  self.assertEqual(self.producer.queued(1),440000);self.assertEqual(self.producer.recording(),1)
  run=self.producer.run();self.assertEqual(self.producer.finish(),1);self.pump(100)
  self.assertEqual(self.response()[4],4)
  records=self.records(self.file(run));frames=[row[1] for row in records if row[0]==2]
  self.assertEqual(frames,list(range(1,13001)));self.assertEqual(self.arm.guards(),1)
  terminal=[row for row in records if row[0]!=2]
  self.assertEqual([row[0] for row in terminal],[29,28])
  self.assertEqual([row[1:3] for row in terminal],[(13000,52000)]*2)
  self.assertEqual(struct.unpack_from('>2I',terminal[0][3]),(1,1))
  self.assertEqual(struct.unpack('>2I',terminal[1][3]),(1,0))
 def test_background_flush_waits_below_threshold_and_does_not_change_finish_ownership(self):
  self.assertEqual(self.producer.bulk(1,1000),1);self.producer.background();self.assertEqual(self.producer.sealed(0),0)
  self.assertEqual(self.producer.finish(),1);self.producer.background();self.pump(20)
  self.assertEqual(self.response()[4],4);self.assertEqual(self.response()[6],1)
 def test_abandoned_attempt_does_not_drain_unsent_data_or_remove_completed_run(self):
  self.assertEqual(self.producer.record(1,4,1),1);kept=self.producer.run()
  self.assertEqual(self.producer.finishManaged(),1);self.producer.next_frame();self.pump(20);saved=self.file(kept);self.assertTrue(saved)
  self.assertEqual(self.producer.start(),1);self.pump(3);self.producer.enter();discarded=self.producer.run();self.assertNotEqual(discarded,kept)
  self.assertEqual(self.producer.bulk(1,5000),1);self.producer.background();self.pump(1)
  self.assertEqual(self.response()[6],0);self.producer.abandon();self.pump(6)
  self.assertEqual(self.response()[4],5);self.assertEqual(self.response()[6],0)
  self.assertIsNone(self.file(discarded));self.assertIsNone(self.file(discarded,'part'))
  self.assertEqual(self.file(kept),saved)
 def test_abandonment_preserves_a_checkpoint_owned_source(self):
  self.checkpoint();kept=self.producer.run();self.pump(12)
  self.assertEqual(self.producer.bulk(11,1000),1);self.producer.abandon();self.pump(30)
  self.assertEqual(self.response()[4],4);self.assertTrue(self.file(kept));self.assertEqual(self.producer.ready(0),1)
 def test_ram_save_is_same_frame_and_does_not_wait_for_io(self):
  before=self.arm.written();self.checkpoint();self.assertEqual(self.arm.written(),before)
  values=struct.unpack('<24I',C.string_at(self.producer.snapshot(0),96));self.assertEqual(values[5:8],(10,40,1));self.assertEqual(self.producer.record(11,44,101),1)
  self.pump(10);self.assertEqual(self.producer.ready(0),1);self.assertEqual(values,struct.unpack('<24I',C.string_at(self.producer.snapshot(0),96)))
 def test_reset_retains_a_snapshotted_source(self):
  self.checkpoint();source=self.producer.run();self.producer.stop();self.pump(20)
  self.assertEqual(self.response()[4],4);self.assertIsNotNone(self.file(source));self.assertEqual(self.producer.owned(source),1)
 def test_actual_fork_preserves_prefix_and_resumes_global_clock(self):
  self.checkpoint();source=self.producer.run();self.pump(8);self.producer.record(20,80,200);self.producer.poisonBaselines()
  self.assertEqual(self.producer.load(0,11),0);self.assertEqual(self.producer.hold(),1);self.assertEqual(self.producer.commit(),0);self.assertEqual(self.settled(),1)
  tail=self.producer.run();self.assertNotEqual(tail,source);self.assertEqual(self.producer.freshBaselines(),1);self.assertEqual(self.producer.record(21,84,999),0)
  marker=self.data(f'ref_12345678_{tail:08X}_464F524B_00000001_00000001.msgb');self.assertEqual(len(marker),128);self.assertIsNotNone(self.file(source))
  self.producer.audio(5);self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.hold(),0);self.assertEqual((self.producer.frame(),self.producer.tick()),(10,40));self.assertEqual(self.producer.metadataRun(),tail)
  self.assertEqual(self.producer.record(11,44,300),1);self.assertEqual(self.producer.finish(),1);self.pump(20);self.assertIsNotNone(self.file(tail,'msgt'))
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload
  def frames(data):
   file=io.BytesIO(data);file.seek(64);result=[]
   while True:
    header=struct.unpack('>8I',file.read(32))
    if header[0]==0x444f4e45:break
    raw=chunk_payload(file,header,3);at=0;chunk=[]
    while at<len(raw):
     kind,size,frame,tick=struct.unpack_from('>HHII',raw,at)
     if kind==2:chunk.append((frame,tick,struct.unpack_from('>I',raw,at+12)[0]))
     at+=12+size
    result.append(chunk)
   return result
  sourceFrames=frames(self.file(source));tailFrames=frames(self.file(tail))
  self.assertEqual(sourceFrames,[[(10,40,100)],[(20,80,200)]]);self.assertEqual(tailFrames,[[(11,44,300)]])
  cutoff=struct.unpack_from('>I',marker,52)[0];self.assertEqual(cutoff,1)
  self.assertEqual(sourceFrames[:cutoff]+tailFrames,[[(10,40,100)],[(11,44,300)]])
  stream=io.BytesIO(self.file(tail));stream.seek(64);header=struct.unpack('>8I',stream.read(32));raw=chunk_payload(stream,header,3)
  self.assertEqual(struct.unpack_from('>HHII',raw), (27,48,10,40))
  self.assertEqual(struct.unpack_from('>12I',raw,12), (1,0x23,5,0x12345678,source,1,struct.unpack_from('<I',C.string_at(self.producer.snapshot(0),96),36)[0],0x98765432,120,44,0,1))

 def test_cancellation_keeps_pin_until_branch_receipt(self):
  self.checkpoint();source=self.producer.run();self.pump(8);self.producer.record(12,48,120);self.producer.load(0,11)
  for _ in range(100):
   if self.producer.phase()==4:break
   self.pump()
  self.assertEqual(self.producer.phase(),4);self.producer.clear(0,11);self.producer.cancel();self.assertEqual(self.producer.hold(),0);self.assertEqual(self.producer.owned(source),1)
  self.pump(30);self.assertEqual(self.producer.owned(source),0);self.assertIsNotNone(self.file(source))
 def test_two_slots_can_share_one_pending_boundary(self):
  self.checkpoint();request=C.string_at(self.producer.request(),32);self.assertEqual(self.producer.save(1,12),1);self.assertEqual(C.string_at(self.producer.request(),32),request);self.assertEqual(self.producer.pinrefs(),2)
  self.producer.clear(0,11);self.pump(8);self.assertEqual(self.producer.ready(1),1);self.assertEqual(self.producer.pinrefs(),1)
 def test_finish_keeps_the_remaining_draw_side_observations(self):
  self.assertEqual(self.producer.record(10,40,100),1)
  self.assertEqual(self.producer.queue_finish(),1);self.assertEqual(self.producer.queue_finish(),0)
  self.assertEqual(self.producer.recording(),1)
  self.assertEqual(self.producer.record(10,40,101),1);self.pump(2)
  self.assertEqual(self.response()[4],2)
  self.producer.next_frame();self.assertEqual(self.producer.recording(),0)
  self.assertEqual(self.producer.record(11,44,102),0);self.pump(20)
  self.assertEqual(self.response()[4],4)
 def test_failed_writer_releases_without_deleting_checkpoint_prefix(self):
  self.checkpoint();self.pump(12);source=self.producer.run();prefix=self.file(source,'part')
  self.assertTrue(prefix);self.assertEqual(self.producer.ready(0),1)
  self.assertEqual(self.producer.record(20,80,200),1);self.arm.failures(0,0,0)
  self.assertEqual(self.producer.finish(),1);self.pump(20)
  self.assertEqual(self.response()[4],5);self.assertEqual(self.producer.owned(source),1)
  self.assertEqual(self.file(source,'part'),prefix)
  self.arm.failures(0xffffffff,0,0)
  self.assertEqual(self.producer.start(),1);self.pump(4);self.producer.enter()
  self.assertEqual(self.producer.recording(),1);self.assertNotEqual(self.producer.run(),source)
  self.assertEqual(self.producer.ready(0),1)
 def test_failed_sync_never_allows_load(self):
  self.checkpoint();self.arm.syncFail(1);self.pump(10);self.assertEqual(self.producer.ready(0),-1);self.assertEqual(self.producer.load(0,11),-1);self.assertEqual(self.producer.pinrefs(),1)
 def test_wrong_slot_generation_does_not_leak_a_load_pin(self):
  self.checkpoint();self.pump(8);before=self.producer.pinrefs();self.assertEqual(self.producer.load(0,99),-1);self.assertEqual(self.producer.pinrefs(),before)
 def test_map_publication_failure_keeps_source_and_refuses_commit(self):
  self.checkpoint();source=self.producer.run();self.pump(8);self.producer.record(12,48,120);self.producer.load(0,11)
  for _ in range(100):
   if self.producer.phase()==4:break
   self.pump()
  self.arm.failures(0xffffffff,0,1);self.pump(20);self.assertEqual(self.producer.load(0,11),-1);self.assertEqual(self.producer.commit(),0);self.assertIsNotNone(self.file(source))
 def test_queued_fences_cannot_be_overtaken_by_post_boundary_chunks(self):
  self.checkpoint();self.pump();self.assertEqual(self.response()[6],1);self.assertEqual(self.response()[3],1)
  self.assertEqual(self.producer.record(11,44,101),1);self.assertEqual(self.producer.save(1,12),1)
  self.pump(12);self.assertEqual(self.producer.ready(0),1);self.assertEqual(self.producer.ready(1),1)
  first=struct.unpack('<24I',C.string_at(self.producer.snapshot(0),96));second=struct.unpack('<24I',C.string_at(self.producer.snapshot(1),96))
  self.assertEqual((first[7],second[7]),(1,2));self.assertEqual(self.response()[6],2)
 def test_failed_ram_save_keeps_only_pending_io_ownership(self):
  self.assertEqual(self.producer.record(10,40,100),1);source=self.producer.run();self.assertEqual(self.producer.abandonSave(),1)
  self.assertEqual(self.producer.pinrefs(),0);self.assertEqual(self.producer.owned(source),1);self.pump(8);self.assertEqual(self.producer.owned(source),0)
  self.assertEqual(self.producer.save(1,12),1);self.pump(8);self.assertEqual(self.producer.ready(1),1)
 def test_export_refuses_unpinned_persistent_checkpoint(self):
  self.checkpoint();self.assertEqual(self.producer.exportable(0),0);self.pump(8);self.assertEqual(self.producer.exportable(0),0)
 def test_cancel_before_finalizing_preserves_current_recording(self):
  self.checkpoint();source=self.producer.run();self.assertEqual(self.producer.load(0,11),0);self.producer.cancel()
  self.assertEqual(self.producer.metadataRun(),source);self.assertEqual(self.producer.record(11,44,101),1)
  self.pump(12);self.assertEqual(self.producer.recording(),1);self.assertEqual(self.producer.ready(0),1)
 def test_control_runtime_fits_reserved_lease(self):self.assertLessEqual(self.producer.runtimeBytes(),3072)
 def test_untracked_successful_restore_stops_recording_without_inventing_prefix(self):
  self.assertEqual(self.producer.record(10,40,100),1);self.assertEqual(self.producer.untrackedLoad(1),1)
  self.assertEqual(self.producer.recording(),0);self.pump(20);self.assertEqual(self.response()[4],5)
 def test_failed_untracked_restore_preserves_recording(self):
  self.assertEqual(self.producer.untrackedLoad(0),1);self.assertEqual(self.producer.recording(),1)
 def durable_export(self):
  self.checkpoint();self.pump(8);copy=C.create_string_buffer(96)
  self.assertEqual(self.producer.exportRaw(0,copy),1)
  self.assertEqual(self.producer.finish(),1);self.pump(20)
  return copy
 def test_durable_archive_can_resume_after_fresh_boot_and_reused_run_number(self):
  copy=self.durable_export();old=struct.unpack('<24I',copy.raw)
  self.arm.identity(0x474d534a,0x87654321);self.assertEqual(self.producer.resetAt(0x87654321),1)
  self.assertEqual(self.producer.adopt(copy,0,51),1)
  self.assertEqual(self.producer.load(0,51),0)
  for _ in range(120):
   self.pump()
   result=self.producer.load(0,51)
   if result:break
  self.assertEqual(result,1);self.assertEqual(self.producer.run(),old[3])
  self.assertEqual(self.producer.commit(),1);self.assertEqual((self.producer.frame(),self.producer.tick()),(10,40))
  name=f'ref_87654321_{old[3]:08X}_464F524B_00000001_00000001.msgb'
  self.assertIsNotNone(self.data(name))
 def test_direct_archive_load_holds_prefix_until_native_commit(self):
  copy=self.durable_export()
  self.arm.identity(0x474d534a,0x87654321);self.assertEqual(self.producer.resetAt(0x87654321),1)
  self.assertEqual(self.producer.externalLoad(copy,71),0)
  for _ in range(120):
   self.pump()
   result=self.producer.externalLoad(copy,71)
   if result:break
  self.assertEqual(result,1);self.assertEqual(self.producer.hold(),1);self.assertEqual(self.producer.pinrefs(),1)
  self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.pinrefs(),0)
if __name__=='__main__':unittest.main()
