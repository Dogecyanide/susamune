"""Checked scalar input borrowing against native-layout host buffers."""
import ctypes as C
import struct,unittest
import test_ghost_trace_decode as trace
from test_ghost_trace_reader import record

FIXTURE=trace.FIXTURE+r'''
#include <cstdio>
#include "src/ghost_world_input.cpp"
namespace I=GhostWorldInput;
static I::Borrow borrow;
static I::Plan plan;
static unsigned char padMemory[304] __attribute__((aligned(32)));
static unsigned char workMemory[100] __attribute__((aligned(32)));
static unsigned char sharedMemory[144] __attribute__((aligned(32)));
static unsigned char physicalMemory[12];
static unsigned generation=7,token=44,entered,left,locked,guardMode;
static I::Targets targetSet;
static I::GuardResult acquire(void*,const I::Owner &owner,const I::Targets &targets){
 ++entered;
 if(guardMode==1)return I::BUSY;
 if(guardMode==2||owner.generation!=generation||owner.token!=token||targets.pad!=reinterpret_cast<TMarioGamePad*>(padMemory+32)||
    (targets.work&&targets.work!=reinterpret_cast<TMarioControllerWork*>(workMemory+32))||targets.sharedButtons!=sharedMemory+32||
    targets.sharedStick!=sharedMemory+80||targets.sharedSubstick!=sharedMemory+96)return I::STALE;
 ++locked;return I::OWNED;
}
static void release(void*){++left;--locked;}
API void inputMode(unsigned flags,int timer,int disabled){
 unsigned short f=flags;short t=timer;memcpy(padMemory+32+0xe2,&f,2);memcpy(padMemory+32+0xe4,&t,2);memcpy(padMemory+32+0xe8,&disabled,4);
}
API void inputReset(){
 memset(padMemory,0xa5,sizeof(padMemory));memset(workMemory,0xb6,sizeof(workMemory));memset(sharedMemory,0xc7,sizeof(sharedMemory));memset(physicalMemory,0x5a,sizeof(physicalMemory));
 borrow={};plan={};generation=7;token=44;entered=left=locked=guardMode=0;
 targetSet={reinterpret_cast<TMarioGamePad*>(padMemory+32),reinterpret_cast<TMarioControllerWork*>(workMemory+32),sharedMemory+32,sharedMemory+80,sharedMemory+96};
 inputMode(0x20,-5,0);
}
API int inputPlan(unsigned policy){D::SharedPad reconstructed=event.input.shared;return I::prepare(plan,event.input,static_cast<I::MirrorPolicy>(policy),policy==2?&reconstructed:nullptr);}
API int inputStrict(unsigned policy,int proven){return I::prepare(plan,event.input,static_cast<I::MirrorPolicy>(policy),nullptr,I::RESTORE_INITIALIZED_WORK,proven!=0);}
API unsigned inputEvidence(){return I::evidenceGaps(plan);}
API int inputBegin(unsigned ownerGeneration,unsigned ownerToken,int hasWork){
 targetSet.work=hasWork?reinterpret_cast<TMarioControllerWork*>(workMemory+32):nullptr;
 return I::begin(borrow,targetSet,{ownerGeneration,ownerToken},{nullptr,acquire,release});
}
API int inputApply(unsigned flags){return I::apply(borrow,plan,{(flags&1)!=0,(flags&2)!=0,(flags&4)!=0,(flags&8)!=0});}
API int inputHistory(unsigned controls,unsigned flags,int timer,int disabled,int practice){
 I::Controls c={(controls&1)!=0,(controls&2)!=0,false,false};c.haveHistory=true;c.practiceHistory=practice!=0;
 c.history={static_cast<unsigned short>(flags),static_cast<short>(timer),disabled};return I::apply(borrow,plan,c);
}
API void inputSetupExpected(unsigned flags,int timer,int disabled){event.input.pad.flags=flags;event.input.pad.stickTimer=timer;event.input.pad.disabledFrames=disabled;}
API int inputRestore(){return I::restore(borrow);}
API void inputGuard(unsigned mode){guardMode=mode;}
API void inputOwner(unsigned gen,unsigned tok){generation=gen;token=tok;}
API int inputActive(){return borrow.active;}
API unsigned inputCalls(unsigned field){return field==0?entered:field==1?left:locked;}
API int inputCaptured(){return I::capturedMirrors(plan);}
API void* inputBuffer(unsigned which){return which==0?padMemory:which==1?workMemory:which==2?sharedMemory:physicalMemory;}
API unsigned inputBytes(unsigned which){return which==0?sizeof(I::Borrow):sizeof(I::Plan);}
API int inputAliased(){I::Targets aliases=targetSet;aliases.work=reinterpret_cast<TMarioControllerWork*>(padMemory+48);return I::begin(borrow,aliases,{7,44},{nullptr,acquire,release});}
API int inputStaleAddress(){I::Targets stale=targetSet;stale.pad=reinterpret_cast<TMarioGamePad*>(0x1000);return I::begin(borrow,stale,{6,44},{nullptr,acquire,release});}
API unsigned inputObserved(unsigned field){return field==0?borrow.observed.flags:field==1?borrow.observed.stickTimer:borrow.observed.disabledFrames;}
API void inputPoison(unsigned field,int prepared){
 D::Input &i=prepared?plan.input:event.input;unsigned nan=0x7fc00000;
 switch(field){
 case 0:memcpy(&i.pad.stick.x,&nan,4);break;
 case 1:i.pad.buttons.analogL=2;break;
 case 2:i.pad.stick.x=4.1f;break;
 case 3:i.pad.stick.magnitude=1.1f;break;
 case 4:i.pad.meaningAxes[2]=-1;break;
 case 5:i.pad.meaningAxes[9]=5;break;
 case 6:i.raw.buttons=0xffff;break;
 case 7:i.pad.buttons.pressed=i.pad.buttons.released=0x100;break;
 case 8:i.pad.buttons.repeatState[1]=0x100;i.pad.buttons.repeatState[2]=20;i.pad.buttons.repeatState[3]=0;break;
 case 9:i.pad.meaning=0xffffffff;break;
 case 10:i.pad.analogHeld=2;break;
 case 11:i.work.right=1.1f;break;
 case 12:i.work.magnitude=65;break;
 case 13:i.sharedKnown=2;break;
 case 14:i.sharedKnown=0;break;
 case 15:i.pad.flags^=0x80;break;
 case 16:memcpy(&i.work.right,&nan,4);break;
 case 17:i.valid=1;break;
 }
}
API const char* inputDiagnosis(){
 static char text[1200];const D::Input &i=event.input;
 snprintf(text,sizeof(text),"valid=%u raw=%x/%d buttons=%x/%x/%x repeat=%x/%x/%x/%u/%u analog=%g/%g stick=%g/%g/%g sub=%g/%g/%g meaning=%x/%x/%x analogbits=%x/%x/%x axes=%g,%g,%g,%g,%g,%g,%g,%g,%g,%g work=%x/%x;%g/%g/%g/%g/%g",i.valid,i.raw.buttons,i.raw.error,i.pad.buttons.held,i.pad.buttons.pressed,i.pad.buttons.released,i.pad.buttons.repeat,i.pad.buttons.repeatState[0],i.pad.buttons.repeatState[1],i.pad.buttons.repeatState[2],i.pad.buttons.repeatState[3],i.pad.buttons.analogL,i.pad.buttons.analogR,i.pad.stick.x,i.pad.stick.y,i.pad.stick.magnitude,i.pad.substick.x,i.pad.substick.y,i.pad.substick.magnitude,i.pad.meaning,i.pad.pressedMeaning,i.pad.releasedMeaning,i.pad.analogHeld,i.pad.analogPressed,i.pad.analogReleased,i.pad.meaningAxes[0],i.pad.meaningAxes[1],i.pad.meaningAxes[2],i.pad.meaningAxes[3],i.pad.meaningAxes[4],i.pad.meaningAxes[5],i.pad.meaningAxes[6],i.pad.meaningAxes[7],i.pad.meaningAxes[8],i.pad.meaningAxes[9],i.work.held,i.work.pressed,i.work.x,i.work.y,i.work.magnitude,i.work.left,i.work.right);
 return text;
}
API int inputValidateChunk(){
 if(!D::pushChunk(decoder,reader.output,reader.chunkBytes))return 0;
 D::Result result;
 while((result=D::next(decoder,event))==D::EVENT)if(event.type==D::INPUT){
  I::Plan candidate;
  if(I::prepare(candidate,event.input,event.input.sharedKnown?I::CAPTURED_SHARED:I::PRESERVE_SHARED)!=I::OK)return -1;
 }
 return result==D::CHUNK_DONE;
}
'''

class InputTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous=trace.FIXTURE;trace.FIXTURE=FIXTURE
  try:trace.DecodeTests.setUpClass.__func__(cls)
  finally:trace.FIXTURE=previous
  cls.lib.inputBuffer.restype=C.c_void_p
  cls.lib.inputDiagnosis.restype=C.c_char_p
 def setUp(self):self.lib.inputReset()
 def sample(self,boundary=True,shared=True,flags=0,buttons=0x100):
  p=bytearray(trace.input_body(boundary,buttons,1 if boundary else 3))
  if boundary:struct.pack_into('>I',p,4,0x80000000|flags)
  self.assertEqual(self.lib.decoderBegin(3,trace.GAME,trace.CAPS,0),1)
  data=b''
  if shared:
   m=trace.mirrors(trace.input_body(True,0x1000))
   data+=record(1,0,trace.mirror_literal(m),24)
  data+=record(1,0,p,14)
  self.buffer=C.create_string_buffer(data);self.assertEqual(self.lib.decoderPush(self.buffer,len(data)),1)
  self.assertEqual(self.lib.decoderNext(),0);self.assertEqual(self.lib.value(1),14)
 def memory(self):return [C.string_at(self.lib.inputBuffer(i),n) for i,n in enumerate((304,100,144,12))]
 def plan(self,policy=0):self.assertEqual(self.lib.inputPlan(policy),0)
 def borrow(self,work=1):self.assertEqual(self.lib.inputBegin(7,44,work),0)
 def apply_boundary(self,flags=0):
  self.sample(flags=flags);self.plan();self.borrow();self.assertEqual(self.lib.inputApply(flags),0)
 def guards(self):
  for data,fill in zip(self.memory()[:3],(0xa5,0xb6,0xc7)):
   self.assertEqual(data[:32],bytes([fill])*32);self.assertEqual(data[-32:],bytes([fill])*32)
  self.assertEqual(self.lib.inputCalls(2),0)
 def test_only_audited_scalars_are_written_and_exact_edges_preserved(self):
  before=self.memory();self.apply_boundary();after=self.memory()
  pad=after[0][32:272]
  self.assertEqual(struct.unpack_from('<II',pad,0x18),(0x100,0x100))
  self.assertEqual(struct.unpack_from('<I',pad,0xd4)[0],0x61)
  self.assertEqual(struct.unpack_from('<f',pad,0x48)[0],-.5)
  self.assertEqual(struct.unpack_from('<I',after[2],32)[0],0x1000)
  self.assertEqual(struct.unpack_from('<I',after[2],36)[0],0x1000)
  for i in range(240):
   if not (0x18<=i<0x68 or 0xa8<=i<0xe2):self.assertEqual(after[0][32+i],before[0][32+i],f'offset{i:x}')
  self.assertEqual(after[1],before[1]);self.assertEqual(after[3],before[3]);self.assertEqual(self.lib.inputCaptured(),1)
  self.assertEqual(self.lib.inputRestore(),0);self.assertEqual(self.memory(),before);self.guards()
 def test_movement_work_uses_audited_trigger_order_and_preserves_padding(self):
  original=self.memory();self.apply_boundary();self.sample(False);self.assertEqual(self.lib.inputStrict(0,1),0)
  self.assertEqual(self.lib.inputApply(0),0);work=self.memory()[1][32:68]
  self.assertEqual(struct.unpack_from('<hhII',work),(-123,456,0x200,0x100))
  self.assertAlmostEqual(struct.unpack_from('<f',work,0x1c)[0],.1)
  self.assertAlmostEqual(struct.unpack_from('<f',work,0x20)[0],.2)
  self.assertEqual(work[14:16],b'\xb6\xb6')
  self.assertEqual(self.lib.inputRestore(),0);self.assertEqual(self.memory(),original);self.guards()
 def test_paused_frame_recreates_native_pre_read_history(self):
  self.sample(flags=1);self.lib.inputSetupExpected(2,10,30);self.plan();self.lib.inputMode(0x42,9,29);self.borrow()
  self.assertEqual(self.lib.inputHistory(1,2,10,30,0),0)
  self.assertEqual((self.lib.inputObserved(0),self.lib.inputObserved(1),self.lib.inputObserved(2)),(2,10,30));self.guards()
 def test_exact_native_menu_mode_is_not_overwritten_by_pause_history(self):
  self.sample(flags=3);self.lib.inputSetupExpected(0x42,0,0);self.plan();self.lib.inputMode(0x42,0,0);self.borrow()
  self.assertEqual(self.lib.inputHistory(3,2,0,0,1),0)
  self.assertEqual((self.lib.inputObserved(0),self.lib.inputObserved(1),self.lib.inputObserved(2)),(0x42,0,0))
  self.assertEqual(struct.unpack_from('<H',self.memory()[0],32+0xe2)[0],0x42);self.guards()
 def test_exact_frozen_mode_keeps_all_native_counters(self):
  self.sample(flags=1);self.lib.inputSetupExpected(0x42,7,30);self.plan();self.lib.inputMode(0x42,7,30);self.borrow()
  self.assertEqual(self.lib.inputHistory(1,2,6,29,1),0)
  self.assertEqual((self.lib.inputObserved(0),self.lib.inputObserved(1),self.lib.inputObserved(2)),(0x42,7,30));self.guards()
 def test_menu_history_does_not_hide_unexplained_mode_bits(self):
  self.sample(flags=3);self.lib.inputSetupExpected(0x42,0,0);self.plan();self.lib.inputMode(0x82,0,0);self.borrow()
  self.assertEqual(self.lib.inputHistory(3,2,0,0,1),9)
  self.assertEqual(self.lib.inputObserved(0),2);self.guards()
 def test_practice_injection_replays_only_matching_pre_read_latch(self):
  self.sample();self.lib.inputSetupExpected(2,0,0);self.plan();self.lib.inputMode(0x42,0,0);self.borrow()
  before=self.memory();self.assertEqual(self.lib.inputHistory(0,2,0,0,0),9);self.assertEqual(self.memory(),before)
  self.assertEqual(self.lib.inputHistory(0,2,0,0,1),0);self.guards()
 def test_history_cannot_hide_game_mode_changes_or_repair_move_samples(self):
  self.sample();self.lib.inputSetupExpected(0x42,0,0);self.plan();self.lib.inputMode(0x40,0,0);self.borrow()
  before=self.memory();self.assertEqual(self.lib.inputHistory(0,0x42,0,0,1),9);self.assertEqual(self.memory(),before)
  self.lib.inputReset();self.apply_boundary();self.sample(False);self.lib.inputSetupExpected(0x20,-5,0);self.plan();self.lib.inputMode(0x60,-5,0)
  before=self.memory();self.assertEqual(self.lib.inputHistory(0,0x20,-5,0,1),9);self.assertEqual(self.memory(),before)
 def test_native_mode_flags_counters_are_compared_and_never_restored(self):
  self.sample();self.plan();self.borrow();self.lib.inputMode(0x80,30,10)
  before=self.memory();self.assertEqual(self.lib.inputApply(0),9);self.assertEqual(self.memory(),before)
  self.assertEqual(self.lib.inputObserved(0),0x80)
  self.lib.inputMode(0x20,-5,0);self.assertEqual(self.lib.inputApply(0),0)
  self.lib.inputMode(0x80,30,10);self.assertEqual(self.lib.inputRestore(),0)
  pad=self.memory()[0][32:272]
  self.assertEqual(struct.unpack_from('<Hh',pad,0xe2),(0x80,30));self.assertEqual(struct.unpack_from('<i',pad,0xe8)[0],10)
  self.guards()
 def test_setup_only_talk_flag_difference_keeps_native_mode_bytes(self):
  self.sample();self.lib.inputSetupExpected(0x40,0,0);self.plan();self.lib.inputMode(0x48,0,0);self.borrow()
  self.assertEqual(self.lib.inputApply(0),9)
  self.assertEqual(self.lib.inputApply(4),0)
  self.assertEqual(struct.unpack_from('<Hhi',self.memory()[0],32+0xe2)[0],0x48)
  self.assertEqual(self.lib.inputRestore(),0)
  self.guards()
 def test_pre_setup_flag_reset_covers_other_native_menu_modes(self):
  for flags in (0x40,0x41,0x42,0x48,0x80,0xffff):
   with self.subTest(flags=flags):
    self.lib.inputReset();self.sample();self.lib.inputSetupExpected(0x40,0,0);self.plan();self.lib.inputMode(flags,0,0);self.borrow()
    self.assertEqual(self.lib.inputApply(4),0)
    self.assertEqual(struct.unpack_from('<H',self.memory()[0],32+0xe2)[0],flags)
    self.guards()
 def test_setup_flag_reset_cannot_hide_counter_differences_or_apply_to_moves(self):
  for timer,disabled in ((1,0),(0,1),(60,5)):
   self.lib.inputReset();self.sample();self.lib.inputSetupExpected(0x40,0,0);self.plan();self.lib.inputMode(0x41,timer,disabled);self.borrow()
   before=self.memory();self.assertEqual(self.lib.inputApply(4),9);self.assertEqual(self.memory(),before)
  self.lib.inputReset();self.apply_boundary();self.sample(False);self.plan();self.assertEqual(self.lib.inputApply(4),11)
 def test_suppressed_pre_setup_input_keeps_native_flags_until_retail_reset(self):
  self.sample(flags=2);self.lib.inputSetupExpected(0x50,0,0);self.plan();self.lib.inputMode(0x40,0,0);self.borrow()
  self.assertEqual(self.lib.inputApply(2),9)
  self.assertEqual(self.lib.inputApply(6),0)
  self.assertEqual(struct.unpack_from('<H',self.memory()[0],32+0xe2)[0],0x40)
  self.lib.inputMode(0,0,0);self.sample(False);self.lib.inputSetupExpected(0,0,0);self.plan()
  self.assertEqual(self.lib.inputApply(2),0)
  self.lib.inputMode(0x40,0,0);self.sample(False);self.lib.inputSetupExpected(0x50,0,0);self.plan()
  self.assertEqual(self.lib.inputApply(2),9)
 def test_frozen_setup_cannot_claim_that_retail_will_reset_flags(self):
  self.sample(flags=1);self.lib.inputSetupExpected(0x50,0,0);self.plan();self.lib.inputMode(0x40,0,0);self.borrow()
  before=self.memory();self.assertEqual(self.lib.inputApply(5),9);self.assertEqual(self.memory(),before)
 def test_initial_stage_initializes_only_canonical_counters(self):
  self.sample();self.lib.inputSetupExpected(0x40,0,0);self.plan();self.lib.inputMode(0x41,60,5);self.borrow()
  self.assertEqual(self.lib.inputApply(12),0)
  pad=self.memory()[0][32:272]
  self.assertEqual(struct.unpack_from('<Hh',pad,0xe2),(0x41,0));self.assertEqual(struct.unpack_from('<i',pad,0xe8)[0],0)
  self.lib.inputMode(0x1,59,4);self.assertEqual(self.lib.inputRestore(),0)
  pad=self.memory()[0][32:272]
  self.assertEqual(struct.unpack_from('<Hh',pad,0xe2),(0x1,59));self.assertEqual(struct.unpack_from('<i',pad,0xe8)[0],4)
  self.guards()
 def test_noncanonical_initial_counter_is_not_overwritten(self):
  self.sample();self.lib.inputSetupExpected(0x40,30,0);self.plan();self.lib.inputMode(0x41,60,0);self.borrow()
  before=self.memory();self.assertEqual(self.lib.inputApply(12),9);self.assertEqual(self.memory(),before)
 def test_missing_mirrors_need_explicit_policy_and_preserve_live_is_not_rewritten(self):
  self.sample(shared=False);self.assertEqual(self.lib.inputPlan(0),2)
  self.plan(1);self.borrow();before=self.memory();self.assertEqual(self.lib.inputApply(0),0)
  self.assertEqual(self.memory()[2],before[2]);self.assertEqual(self.lib.inputCaptured(),0)
  C.memset(self.lib.inputBuffer(2)+32,0x33,80)
  self.assertEqual(self.lib.inputRestore(),0);self.assertEqual(self.memory()[2][32:112],bytes([0x33])*80)
  self.lib.inputReset();self.sample(shared=False);self.plan(3);self.borrow();self.assertEqual(self.lib.inputApply(0),0)
  self.assertEqual(struct.unpack_from('<I',self.memory()[2],32)[0],0x100);self.assertEqual(self.lib.inputCaptured(),0)
 def test_reconstructed_mirrors_are_explicit_and_distinct_from_captured(self):
  self.sample();self.plan(2);self.borrow();self.assertEqual(self.lib.inputApply(0),0)
  self.assertEqual(struct.unpack_from('<I',self.memory()[2],32)[0],0x1000);self.assertEqual(self.lib.inputCaptured(),0)
 def test_freeze_suppression_receipt_and_boundary_move_order(self):
  for flags in (1,2,3):
   self.lib.inputReset();self.sample(flags=flags);self.plan();self.borrow();before=self.memory()
   self.assertEqual(self.lib.inputApply(0),10);self.assertEqual(self.memory(),before)
   self.assertEqual(self.lib.inputApply(flags),0);self.assertEqual(self.lib.inputApply(flags),11)
   self.sample(False);self.plan()
   self.assertEqual(self.lib.inputApply(flags),11 if flags&1 else 0)
  self.lib.inputReset();self.sample(False);self.plan();self.borrow();self.assertEqual(self.lib.inputApply(0),11)
 def test_busy_lease_keeps_backup_and_stale_lease_never_touches_old_targets(self):
  self.apply_boundary();before=self.memory();self.lib.inputGuard(1)
  self.assertEqual(self.lib.inputRestore(),7);self.assertEqual(self.lib.inputActive(),1);self.assertEqual(self.memory(),before)
  self.lib.inputGuard(0);self.assertEqual(self.lib.inputRestore(),0);self.guards()
  self.lib.inputReset();self.apply_boundary();before=self.memory();self.lib.inputOwner(8,44)
  self.assertEqual(self.lib.inputRestore(),8);self.assertEqual(self.lib.inputActive(),0);self.assertEqual(self.memory(),before)
  self.lib.inputReset();self.assertEqual(self.lib.inputStaleAddress(),8);self.assertEqual(self.lib.inputActive(),0)
 def test_rejected_owner_alias_and_missing_work_are_no_write_failures(self):
  before=self.memory();self.assertEqual(self.lib.inputBegin(6,44,1),8);self.assertEqual(self.memory(),before)
  self.lib.inputReset();self.assertEqual(self.lib.inputBegin(7,0,1),4)
  self.assertEqual(self.lib.inputAliased(),3)
  self.sample();self.plan();self.borrow(0);self.assertEqual(self.lib.inputApply(0),0)
  self.sample(False);self.assertEqual(self.lib.inputStrict(0,1),0);before=self.memory();self.assertEqual(self.lib.inputApply(0),3);self.assertEqual(self.memory(),before)
 def test_generation_changed_before_apply_drops_borrow_without_native_reads(self):
  self.sample();self.plan();self.borrow();before=self.memory();self.lib.inputOwner(7,45)
  self.assertEqual(self.lib.inputApply(0),8);self.assertEqual(self.memory(),before);self.assertEqual(self.lib.inputActive(),0)
 def test_invalid_scalars_and_repeat_divisor_rejected_before_writes(self):
  for field in range(14):
   with self.subTest(field=field):
    self.lib.inputReset();self.sample(False if field in (11,12) else True);self.lib.inputPoison(field,0)
    before=self.memory();self.assertEqual(self.lib.inputStrict(0,1),1);self.assertEqual(self.memory(),before)
  self.lib.inputReset();self.sample();self.plan();self.borrow();self.lib.inputPoison(0,1)
  before=self.memory();self.assertEqual(self.lib.inputApply(0),1);self.assertEqual(self.memory(),before)
 def test_borrow_cannot_overwrite_an_active_backup(self):
  self.sample();self.plan();self.borrow();self.assertEqual(self.lib.inputBegin(7,44,1),5)
  self.assertEqual(self.lib.inputApply(0),0);self.assertEqual(self.lib.inputRestore(),0);self.assertEqual(self.lib.inputRestore(),6)
 def test_work_preservation_is_default_and_strict_restore_needs_proof(self):
  self.apply_boundary();self.sample(False);self.lib.inputPoison(11,0);self.plan()
  before=self.memory()[1];self.assertEqual(self.lib.inputEvidence(),2);self.assertEqual(self.lib.inputApply(0),0)
  self.assertEqual(self.memory()[1],before)
  self.assertEqual(self.lib.inputStrict(0,1),1)
  self.sample(False);self.assertEqual(self.lib.inputStrict(0,0),12);self.assertEqual(self.lib.inputStrict(0,1),0)
  self.assertEqual(self.lib.inputEvidence(),0)
 def test_missing_or_uninitialized_derived_work_can_be_preserved_safely(self):
  for field in (16,17):
   self.lib.inputReset();self.apply_boundary();self.sample(False);self.lib.inputPoison(field,0);self.plan()
   before=self.memory()[1];self.assertEqual(self.lib.inputApply(0),0);self.assertEqual(self.memory()[1],before)
   self.assertEqual(self.lib.inputEvidence(),2);self.assertEqual(self.lib.inputStrict(0,1),1)
 def test_real_legacy_capture_scalars_fit_audited_input_ranges(self):
  files=sorted((trace.ROOT/'build/pr48-sd-trace/wii-r9-captures').glob('*.msgt'))
  recent=trace.ROOT/'build/pr48-sd-trace/runtime-r12-capture.msgt'
  if recent.exists():files.append(recent)
  if not files:self.skipTest('Private capture fixtures unavailable')
  for path in files:
   with self.subTest(file=path.name),path.open('rb') as stream:
    self.assertEqual(self.lib.start(path.stat().st_size),1);started=False
    while self.lib.state()==0:
     self.assertEqual(self.lib.next(),1);stream.seek(self.lib.offset());data=stream.read(self.lib.size())
     C.memmove(self.lib.target(),data,len(data));self.assertEqual(self.lib.accept(len(data)),1)
     if self.lib.state()==1:
      if not started:self.assertEqual(self.lib.readerDecoderBegin(),1);started=True
      self.assertEqual(self.lib.inputValidateChunk(),1,f'{path.name}: frame{self.lib.value(2)} tick{self.lib.value(3)} {self.lib.inputDiagnosis().decode()}')
      self.assertEqual(self.lib.release(),1)
    self.assertEqual(self.lib.state(),2)
  print(f'Validated {len(files)} capture scalar streams; host Borrow={self.lib.inputBytes(0)}, Plan={self.lib.inputBytes(1)}')
if __name__=='__main__':unittest.main()
