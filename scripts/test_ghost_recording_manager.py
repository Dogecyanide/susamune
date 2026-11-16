"""Execute the staged native manager with asynchronous producer/backend doubles."""
import ctypes as C
import os
from pathlib import Path
import subprocess,tempfile,unittest
from test_nested_menu_focus import function
ROOT=Path(__file__).resolve().parents[1];P=ROOT
FIXTURE=r'''
#define MOONSHINE_GHOST_TRACE 1
#include "susamune/ghost_recording.hxx"
namespace GhostRecordingNative {void poll(){}}
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost.hxx"
#include <cstring>
static GhostRecording::Runtime runtime;
static unsigned sourceRun,phase,starts,finishes,headerHash=23,footerHash=45,fileBytes=4096;
static unsigned prepareSupport,preparePhase,preparedRun;
static bool waiting,resetPending,fail,installed,automaticPending;
static unsigned worldOwner,pinnedRun,discardCalls;
static int discardResult;
namespace LevelWarp {u8 parentArea(u8 area){return area==7||area==14||area==40?6:255;}}
namespace GhostWorldRuntime {bool busy(){return worldOwner!=0;}bool active(){return worldOwner==1;}}
namespace Ghost {bool observerPreparing(){return false;}bool observerStatsSuppressed(){return false;}}
namespace GhostTraceFlat {bool active(){return false;}}
namespace GhostTrace {
unsigned prepareNextRun(unsigned run){if(!prepareSupport)return 0;if(!run)return 1;preparedRun=run;return preparePhase;}
void revokePreparation(){}
unsigned completedRunFlags(unsigned){return 0;}
bool installCheckpoints(CheckpointController&c){c={};GhostCheckpoints::init(c.pins);return true;}
CheckpointCapture captureCheckpoint(CheckpointSnapshot&){return CheckpointCapture::Unavailable;}
void abandonCheckpoint(){}
bool checkpointSaved(unsigned,unsigned){return true;}
void checkpointCleared(unsigned,unsigned){}
int checkpointReady(const CheckpointSnapshot&){return -1;}
bool checkpointSourceOwned(unsigned,unsigned run){return run==pinnedRun;}
bool importCheckpoint(const CheckpointSnapshot&v){return checkpointValid(v);}
bool checkpointExport(CheckpointSnapshot&){return false;}
bool beginContinuation(const CheckpointSnapshot&,unsigned,unsigned,unsigned){return false;}
int continuationStatus(){return -1;}bool continuationPending(){return false;}unsigned continuationRun(){return 0;}
bool commitContinuation(){return false;}void cancelContinuation(){}
bool checkpointLoadValid(const CheckpointSnapshot&v,unsigned,unsigned){return checkpointValid(v)&&!v.magic;}
int beginFastContinuation(const CheckpointSnapshot&,unsigned,unsigned,unsigned){return 0;}
void stopFastContinuation(){reset();}bool fastContinuationUntracked(){return false;}bool continuationPublicationPending(){return false;}bool continuationBackgroundPending(){return false;}
bool backendIdentity(unsigned&nonce){nonce=1234;return true;}
bool armOrdinaryStage(unsigned,unsigned run){if(phase==1||phase==2||phase==3)return false;sourceRun=run;phase=1;waiting=true;++starts;return true;}
bool armAutomaticStage(unsigned scene,unsigned run){
    if(preparePhase!=2||preparedRun!=run||!armOrdinaryStage(scene,run))return false;
    automaticPending=true;phase=2;waiting=false;return true;
}
bool automaticStartPending(){return automaticPending;}
bool stageArmed(){return phase==2&&waiting;}
bool recording(){return phase==2&&!waiting;}
unsigned ownedRun(){return sourceRun;}
unsigned failure(unsigned){return fail?1:0;}
bool queueOrdinaryFinish(unsigned run){if(run!=sourceRun||!recording())return false;phase=3;++finishes;return true;}
void reset(){resetPending=true;}
bool discarded(unsigned run){return run==sourceRun&&phase==5;}
bool retainedFile(unsigned run){return run==sourceRun&&phase==4;}
bool completion(unsigned run,Completion&out){if(run!=sourceRun||phase!=4)return false;out={1234,run,0x474d534a,fileBytes,1,2,0xfffff,headerHash,footerHash};return true;}
}
static bool load(const void*,unsigned,bool,bool){return true;}
static bool checkpoint(GhostRecording::Checkpoint&,bool){return false;}
static int discard(GhostRecording::Identity,bool){++discardCalls;return discardResult;}
#define API extern "C" __declspec(dllexport)
API void init(){
 if(!installed){GhostRecording::Backend b={load,checkpoint,discard};installed=GhostRecording::install(runtime,1234,15,b);}
 GhostRecordingLifecycle::init(runtime.state,1234,15);runtime.scene=runtime.waitFrames=runtime.discardIssued=runtime.saveToken=runtime.saveProfile=runtime.saveOwner=0;runtime.session=runtime.warmDisabled=runtime.automatic=false;runtime.previousAutomatic=0;prepareSupport=preparedRun=0;preparePhase=1;
 discardResult=0;pinnedRun=discardCalls=worldOwner=0;sourceRun=phase=starts=finishes=0;waiting=resetPending=fail=automaticPending=false;
}
API void warming(unsigned support,unsigned value){prepareSupport=support;preparePhase=value;}
API unsigned reservedRun(){return runtime.state.reservedRun;}
API unsigned serialValue(){return runtime.state.serial;}
API unsigned preparedValue(){return preparedRun;}
API void manualSource(unsigned run){sourceRun=run;}
API unsigned allocatorBoundary(){GhostRecordingLifecycle::State state;GhostRecordingLifecycle::init(state,1234,15);state.nextRun=0x7fffffffu;unsigned reserved=GhostRecordingLifecycle::reserveRun(state);auto*d=GhostRecordingLifecycle::arm(state);return reserved==0xffffffffu&&d&&d->identity.run==reserved&&!state.reservedRun&&!GhostRecordingLifecycle::reserveRun(state);}
API void world(unsigned owner){worldOwner=owner;}
API int gate(unsigned scene,int selected){return GhostRecording::beforeDeparture(scene,selected!=0);}
API void automatic_setup(unsigned scene){GhostRecording::automaticStageSetup(scene);}
API void automatic_departure(unsigned scene){GhostRecording::automaticDeparture(scene);}
API unsigned automatic_scene(){return runtime.scene;}
API void automatic_ack(){automaticPending=false;}
API unsigned run(){return sourceRun;}
API unsigned start_count(){return starts;}
API unsigned finish_count(){return finishes;}
API void open_ack(){phase=2;waiting=true;}
API void stage_start(){phase=2;waiting=false;}
API void finish_ack(){phase=4;}
API void discard_ack(){phase=5;resetPending=automaticPending=false;}
API void poll(){GhostRecording::poll();}
API void cancel(){GhostRecording::cancelArmed();}
API int cancel_pending(){return resetPending;}
API int capturing(){return GhostRecording::capturing();}
API int finish_as(unsigned owner){GhostRecording::Info i={};i.ownerToken=owner;i.startQf=100;i.endQf=104;i.resultQf=104;i.area=2;i.parent=255;memcpy(i.name,"Bianco 1",8);return GhostRecording::finish(i);}
API int finish(){return finish_as(10);}
API void protect(){GhostRecording::protect(10,77);}
API void protect_value(unsigned owner,unsigned pb){GhostRecording::protect(owner,pb);}
API int select(unsigned token){return GhostRecording::selectForSave(token);}
API unsigned selection(){char n[48];unsigned token=0;return GhostRecording::copySelection(n,sizeof(n),&token)?token:0;}
API int queue(unsigned token,unsigned profile){return GhostRecording::queueSave(token,profile);}
API int queued(){return GhostRecording::queuedSave();}
API unsigned take(unsigned profile){unsigned token=0;return GhostRecording::takeQueuedSave(profile,token)?token:0;}
API int exporting(void*out){unsigned owner=0,token=0;return GhostRecording::exportManifest(out,0,"Profile 1",&owner,&token)&&owner==10;}
API int started(unsigned token,unsigned seq){return GhostRecording::publicationStarted(token,seq);}
API void acknowledged(unsigned seq,int ok){GhostRecording::publicationResult(seq,ok!=0);}
API int phase_for(unsigned token){auto*d=GhostRecordingLifecycle::find(runtime.state,token);return d?d->phase:99;}
API void failure(){fail=true;}
API void unrecorded(){GhostRecording::unrecordedDeparture();}
API int active_slot(){return runtime.state.active;}
API void pin_source(){pinnedRun=sourceRun;}
API unsigned deletes(){return discardCalls;}
API unsigned discard_hash(unsigned nonce,unsigned run){unsigned hash=0;return GhostRecording::discardHeaderHash({nonce,run},hash)?hash:0;}
API void delete_result(int result){discardResult=result;}
API void protect_all(){for(auto&d:runtime.state.drafts)if(d.phase==GhostRecordingLifecycle::READY)d.pbToken=d.token+100;}
API int discard_selection(unsigned token){return GhostRecording::discard(token);}
API int null_manifest(){return GhostRecording::loadManifest(nullptr,256,false,false);}
API int restored(){GhostRecording::Checkpoint c={};return GhostRecording::checkpoint(c,true);}
'''
# Exercise the menu/PB queries against the file owner, with deliberately stale resident metadata.
_ghost=(ROOT/'src/ghost.cpp').read_text()
FIXTURE+=r'''
namespace Ghost {
struct Track {bool valid,pb,saved;unsigned pbToken;};
static Track sRecord,sPlayback;
void formatTrackName(const Track&,char*out,unsigned){memcpy(out,"Legacy",7);}
}
'''
for signature in ('bool copyUnsavedPBName(', 'bool hasUnsavedPB()', 'bool hasUnsavedPBToken(', 'bool unprotectUnsavedPB('):
 FIXTURE+='\nnamespace Ghost {\n'+function(_ghost,signature)+'\n}\n'
FIXTURE+=r'''
API void stale_track(unsigned token){Ghost::sRecord={true,true,false,token};Ghost::sPlayback={};}
API unsigned pb_ui(){char name[48];u32 token=0;return Ghost::copyUnsavedPBName(name,sizeof(name),&token)?token:0;}
API int has_pb_ui(){return Ghost::hasUnsavedPB();}
API int has_pb_token(unsigned token){return Ghost::hasUnsavedPBToken(token);}
API int unprotect_ui(unsigned token){return Ghost::unprotectUnsavedPB(token);}
'''
class NativeManagerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-native-manager-');cls.addClassCleanup(cls.temp.cleanup);out=Path(cls.temp.name)
  (out/'fixture.cpp').write_text(FIXTURE,encoding='utf-8');env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++11','-O2','-DMOONSHINE_GHOST_TRACE=1','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/JSystem'),'-I',str(ROOT/'include/susamune'),str(out/'fixture.cpp'),str(P/'src/ghost_recording.cpp'),str(ROOT/'src/ghost_trace_checkpoint.cpp'),'-o',str(out/'manager.dll')],env=env,capture_output=True,text=True,encoding='utf-8')
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(out/'manager.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.selection.restype=cls.lib.run.restype=cls.lib.take.restype=C.c_uint;cls.lib.exporting.argtypes=[C.c_void_p]
 def setUp(self):self.lib.init()
 def capture(self):
  self.assertEqual(self.lib.gate(0x200,1),1);self.lib.open_ack();self.assertEqual(self.lib.gate(0x200,1),0)
  self.lib.stage_start();self.lib.poll();self.assertEqual(self.lib.capturing(),1)
 def test_warm_reservation_has_no_draft_or_pb_token_and_arm_consumes_exact_identity(self):
  self.lib.warming(1,1);self.lib.poll()
  reserved=self.lib.reservedRun()&0xffffffff;self.assertEqual(reserved,0x80000001)
  self.assertEqual(self.lib.active_slot(),3);self.assertEqual(self.lib.serialValue(),1)
  self.assertEqual(self.lib.selection(),0)
  self.assertEqual(self.lib.gate(0x200,1),1)
  self.assertEqual(self.lib.run()&0xffffffff,reserved)
  self.assertEqual(self.lib.serialValue(),2)
 def test_failed_preparation_burns_reserved_identity_and_cold_start_still_works(self):
  self.lib.warming(1,1);self.lib.poll();old=self.lib.reservedRun()&0xffffffff
  self.lib.warming(1,3);self.lib.poll();self.assertEqual(self.lib.reservedRun(),0)
  self.assertEqual(self.lib.gate(0x200,1),1);self.assertNotEqual(self.lib.run()&0xffffffff,old)
 def test_manual_consumption_cannot_reuse_reserved_identity(self):
  self.lib.warming(1,1);self.lib.poll();old=self.lib.reservedRun()&0xffffffff
  self.lib.manualSource(old);self.lib.poll();self.assertNotEqual(self.lib.reservedRun()&0xffffffff,old)
 def test_last_reserved_identity_can_be_armed_when_counter_is_exhausted(self):
  self.assertEqual(self.lib.allocatorBoundary(),1)

 def test_automatic_only_starts_exact_warm_playable_scene_and_promotes_after_ack(self):
  self.lib.warming(1,1);self.lib.poll();reserved=self.lib.reservedRun()
  self.lib.automatic_setup(0x603)
  self.assertEqual(self.lib.start_count(),0);self.assertEqual(self.lib.serialValue(),1)
  self.assertEqual(self.lib.reservedRun(),reserved);self.assertEqual(self.lib.active_slot(),3)
  self.lib.warming(1,2);self.lib.poll()
  for scene in (0x0f00,0x0a00,0x06ff,0x3d00):
   self.lib.automatic_setup(scene)
  self.assertEqual(self.lib.start_count(),0)
  self.lib.automatic_setup(0x603);self.assertEqual(self.lib.run(),reserved&0xffffffff)
  self.assertEqual(self.lib.start_count(),1)
  self.lib.poll();self.assertEqual(self.lib.capturing(),0)
  self.lib.automatic_ack();self.lib.poll();self.assertEqual(self.lib.capturing(),1)
 def test_automatic_preserves_natural_course_hops_and_retires_on_retry(self):
  self.lib.warming(1,2);self.lib.poll();self.lib.automatic_setup(0x603)
  self.lib.automatic_ack();self.lib.poll()
  for scene in (0x702,0xe00,0x2800,0x603):
   self.lib.automatic_departure(scene);self.lib.automatic_setup(scene)
   self.assertEqual(self.lib.automatic_scene(),scene)
   self.assertEqual(self.lib.start_count(),1);self.assertEqual(self.lib.cancel_pending(),0)
  self.lib.automatic_departure(0x603);self.assertEqual(self.lib.cancel_pending(),1)
  self.assertEqual(self.lib.gate(0x603,0),0)
  self.lib.automatic_setup(0x603);self.assertEqual(self.lib.start_count(),1)
  self.lib.discard_ack();self.lib.automatic_setup(0x603)
  self.assertEqual(self.lib.start_count(),2)
 def test_automatic_keeps_previous_finished_and_protected_choice(self):
  self.capture();self.lib.finish();self.lib.protect();self.lib.finish_ack();self.lib.poll()
  self.assertEqual(self.lib.selection(),77)
  self.lib.warming(1,2);self.lib.poll();self.lib.automatic_setup(0x603)
  self.assertEqual(self.lib.selection(),77);self.assertEqual(self.lib.pb_ui(),77)
  self.lib.automatic_ack();self.lib.poll()
  self.assertEqual(self.lib.selection(),77)
  self.lib.automatic_departure(0x400);self.lib.discard_ack();self.lib.poll()
  self.assertEqual(self.lib.selection(),77);self.assertEqual(self.lib.select(77),1)
  self.assertEqual(self.lib.selection(),77)
 def test_explicit_armed_and_watch_stages_never_get_replaced_by_automatic(self):
  self.lib.warming(1,2);self.lib.poll()
  self.lib.world(1);self.lib.automatic_setup(0x603);self.assertEqual(self.lib.start_count(),0)
  self.lib.world(0);self.assertEqual(self.lib.gate(0x603,1),1);self.lib.open_ack()
  self.lib.automatic_setup(0x603);self.assertEqual(self.lib.start_count(),1)
  self.lib.automatic_departure(0xffffffff);self.assertEqual(self.lib.cancel_pending(),0)
 def test_cached_discard_identity_requires_completed_exact_source(self):
  self.capture();run=self.lib.run();self.assertEqual(self.lib.discard_hash(1234,run),0)
  self.lib.finish();self.lib.finish_ack();self.lib.poll();token=self.lib.selection()
  self.assertEqual(self.lib.discard_hash(1234,run),0)
  self.assertEqual(self.lib.discard_selection(token),1)
  self.assertEqual(self.lib.discard_hash(1234,run),23)
  self.assertEqual(self.lib.discard_hash(1235,run),0)
  self.assertEqual(self.lib.discard_hash(1234,run+1),0)
  self.lib.delete_result(1);self.lib.poll();self.assertEqual(self.lib.discard_hash(1234,run),0)
 def test_pb_menu_uses_file_owner_instead_of_stale_resident_track(self):
  self.capture();self.lib.finish();self.lib.protect();self.lib.stale_track(88)
  self.assertEqual(self.lib.pb_ui(),77);self.assertEqual(self.lib.has_pb_ui(),1)
  self.assertEqual(self.lib.has_pb_token(77),1);self.assertEqual(self.lib.has_pb_token(88),0)
  self.assertEqual(self.lib.unprotect_ui(88),0);self.assertEqual(self.lib.pb_ui(),77)
  self.assertEqual(self.lib.unprotect_ui(77),1);self.assertEqual(self.lib.has_pb_ui(),0)
 def test_published_pb_is_not_reintroduced_by_old_track_metadata(self):
  self.capture();self.lib.finish();self.lib.protect();self.lib.stale_track(77)
  self.lib.finish_ack();self.lib.poll();self.assertEqual(self.lib.started(77,9),1)
  self.lib.acknowledged(9,1);self.assertEqual(self.lib.pb_ui(),0);self.assertEqual(self.lib.has_pb_ui(),0)
 def test_playback_departure_does_not_start_or_steal_a_recording(self):
  self.lib.world(1);self.assertEqual(self.lib.gate(0x200,1),0);self.assertEqual(self.lib.start_count(),0)
  self.lib.world(2);self.assertEqual(self.lib.gate(0x200,1),1);self.assertEqual(self.lib.start_count(),0)
  self.lib.world(0);self.assertEqual(self.lib.gate(0x200,1),1);self.assertEqual(self.lib.start_count(),1)
 def test_pre_setup_open_wait_is_nonblocking_and_single_request(self):
  self.assertEqual(self.lib.gate(0x200,1),1)
  for _ in range(20):self.assertEqual(self.lib.gate(0x200,1),1)
  self.assertEqual(self.lib.start_count(),1);self.assertEqual(self.lib.capturing(),0)
  self.lib.open_ack();self.assertEqual(self.lib.gate(0x200,1),0);self.assertEqual(self.lib.capturing(),0)
  self.lib.stage_start();self.lib.poll();self.assertEqual(self.lib.capturing(),1)
 def test_cancel_waits_for_exact_discard_ack(self):
  self.lib.gate(0x200,1);run=self.lib.run();self.lib.cancel();self.assertEqual(self.lib.cancel_pending(),1)
  self.lib.poll();self.assertEqual(self.lib.active_slot(),0)
  self.lib.discard_ack();self.lib.poll();self.assertEqual(self.lib.active_slot(),3)
 def test_finish_queue_publish_ack_preserves_new_capture(self):
  self.capture();self.assertEqual(self.lib.finish(),1);self.lib.protect();self.assertEqual(self.lib.selection(),77)
  self.assertEqual(self.lib.queue(77,0),1);self.assertEqual(self.lib.take(0),0)
  self.lib.finish_ack();self.lib.poll();self.assertEqual(self.lib.take(0),77)
  out=C.create_string_buffer(256);self.assertEqual(self.lib.exporting(out),1);self.assertEqual(out.raw[:4],b'MSGM')
  self.assertEqual(self.lib.started(77,6),1);self.assertEqual(self.lib.gate(0x200,1),1)
  self.lib.acknowledged(5,1);self.assertEqual(self.lib.phase_for(77),5)
  self.lib.acknowledged(6,1);self.assertEqual(self.lib.phase_for(0x40000001),6);self.assertEqual(self.lib.active_slot(),1)
 def test_profile_change_cancels_queued_intent_without_losing_draft(self):
  self.capture();self.lib.finish();token=self.lib.selection();self.assertEqual(self.lib.queue(token,0),1)
  self.lib.finish_ack();self.lib.poll();self.assertEqual(self.lib.take(1),0);self.assertEqual(self.lib.queued(),0);self.assertEqual(self.lib.selection(),token)
 def test_failure_and_missing_fork_remain_explicit(self):
  self.capture();self.lib.failure();self.lib.poll();self.assertEqual(self.lib.capturing(),0);self.assertEqual(self.lib.restored(),0)
 def test_unexpected_producer_reset_cannot_look_like_continued_recording(self):
  self.capture();self.lib.discard_ack();self.lib.poll();self.assertEqual(self.lib.capturing(),0);self.assertEqual(self.lib.active_slot(),3)
 def test_active_recording_is_not_silently_finalized_by_save(self):
  self.capture();self.assertEqual(self.lib.selection(),0);self.assertEqual(self.lib.queue(1,0),0);self.assertEqual(self.lib.finish_count(),0)
 def test_discard_keeps_the_source_owned_by_a_saved_checkpoint(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();self.lib.pin_source()
  token=self.lib.selection();self.assertEqual(self.lib.discard_selection(token),1);self.lib.poll()
  self.assertEqual(self.lib.phase_for(token),99);self.assertEqual(self.lib.deletes(),0)
 def test_discard_old_pinned_source_does_not_wait_on_the_new_writer(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();self.lib.pin_source();token=self.lib.selection()
  self.capture();self.assertEqual(self.lib.discard_selection(token),1);self.lib.poll()
  self.assertEqual(self.lib.phase_for(token),99);self.assertEqual(self.lib.deletes(),0)
  self.assertEqual(self.lib.capturing(),1);self.assertEqual(self.lib.active_slot(),1)
 def test_fourth_attempt_retires_oldest_unprotected_without_touching_latest(self):
  tokens=[]
  for _ in range(3):
   self.capture();self.assertEqual(self.lib.finish(),1);self.lib.finish_ack();self.lib.poll();tokens.append(self.lib.selection())
  self.assertEqual(self.lib.gate(0x200,1),1);self.assertEqual(self.lib.phase_for(tokens[0]),7)
  self.assertEqual(self.lib.gate(0x200,1),1);self.assertEqual(self.lib.phase_for(tokens[1]),4)
  self.lib.delete_result(1);self.lib.poll();self.assertEqual(self.lib.phase_for(tokens[0]),99)
  self.assertEqual(self.lib.gate(0x200,1),1);self.assertEqual(self.lib.start_count(),4)
  self.assertEqual(self.lib.phase_for(tokens[2]),4)
 def test_retirement_timeout_cancels_departure_without_dropping_other_drafts(self):
  tokens=[]
  for _ in range(3):
   self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();tokens.append(self.lib.selection())
  self.assertEqual(self.lib.gate(0x200,1),1)
  for _ in range(899):self.assertEqual(self.lib.gate(0x200,1),1)
  self.assertEqual(self.lib.gate(0x200,1),2)
  self.assertEqual(self.lib.phase_for(tokens[2]),4);self.assertEqual(self.lib.start_count(),3)
 def test_full_protected_pool_never_auto_discards_a_pb(self):
  for _ in range(3):self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll()
  self.lib.protect_all();self.assertEqual(self.lib.gate(0x200,1),2);self.assertEqual(self.lib.deletes(),0)
 def test_latest_never_falls_back_to_an_older_attempt_after_failure(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();old=self.lib.selection()
  self.capture();self.assertEqual(self.lib.selection(),0)
  self.lib.failure();self.lib.poll();self.assertEqual(self.lib.selection(),0)
  self.assertEqual(self.lib.select(old),1);self.assertEqual(self.lib.selection(),old)
 def test_latest_does_not_reoffer_an_old_file_after_publication(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();old=self.lib.selection()
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();latest=self.lib.selection()
  self.assertNotEqual(old,latest);self.assertEqual(self.lib.started(latest,33),1)
  self.lib.acknowledged(33,1);self.assertEqual(self.lib.selection(),0)
  self.assertEqual(self.lib.select(old),1);self.assertEqual(self.lib.selection(),old)
 def test_explicit_discard_does_not_make_an_old_attempt_latest(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();old=self.lib.selection()
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();latest=self.lib.selection()
  self.lib.delete_result(1);self.assertEqual(self.lib.discard_selection(latest),1);self.lib.poll()
  self.assertEqual(self.lib.selection(),0);self.assertEqual(self.lib.select(old),1)
 def test_unrecorded_departure_keeps_the_old_pb_but_not_as_latest(self):
  self.capture();self.lib.finish();self.lib.protect();self.lib.finish_ack();self.lib.poll()
  self.lib.unrecorded();self.assertEqual(self.lib.selection(),0);self.assertEqual(self.lib.pb_ui(),77)
  self.assertEqual(self.lib.select(77),1);self.assertEqual(self.lib.selection(),77)
 def test_each_pb_prompt_selects_its_exact_recording(self):
  self.capture();self.lib.finish_as(10);self.lib.protect_value(10,77);self.lib.finish_ack();self.lib.poll()
  self.capture();self.lib.finish_as(11);self.lib.protect_value(11,88);self.lib.finish_ack();self.lib.poll()
  self.assertEqual(self.lib.selection(),88)
  self.assertEqual(self.lib.select(77),1);self.assertEqual(self.lib.selection(),77)
  out=C.create_string_buffer(256);self.assertEqual(self.lib.exporting(out),1)
  self.assertEqual(self.lib.select(88),1);self.assertEqual(self.lib.selection(),88)
  self.assertEqual(self.lib.select(999),0);self.assertEqual(self.lib.selection(),88)
 def test_default_latest_does_not_return_an_older_protected_pb(self):
  self.capture();self.lib.finish_as(10);self.lib.protect_value(10,77);self.lib.finish_ack();self.lib.poll()
  self.capture();self.lib.finish_as(11);self.lib.finish_ack();self.lib.poll()
  latest=self.lib.selection();self.assertNotEqual(latest,77)
  self.lib.select(77);self.assertEqual(self.lib.selection(),77);self.lib.select(0);self.assertEqual(self.lib.selection(),latest)
 def test_selected_publication_ack_does_not_leave_a_stale_save_intent(self):
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();token=self.lib.selection()
  self.assertEqual(self.lib.select(token),1);self.assertEqual(self.lib.started(token,91),1)
  self.lib.acknowledged(91,1);self.assertEqual(self.lib.selection(),0)
  self.capture();self.lib.finish();self.lib.finish_ack();self.lib.poll();self.assertNotEqual(self.lib.selection(),0)
 def test_null_manifest_is_refused_before_reading_metadata(self):
  self.assertEqual(self.lib.null_manifest(),0)
if __name__=='__main__':unittest.main()
