"""Bounded same-region world replay coordination; no native game mutation."""
import ctypes as C
import struct,unittest
import test_ghost_trace_decode as trace
from test_ghost_trace_reader import record

GAME=trace.GAME
CAPS=trace.CAPS

def settings():
 p=bytearray(64);struct.pack_into('>I',p,48,0x3f800000);return bytes(p)

def frame(ready=True,tick=0,state=1,scene=0xd00,flags=None):
 return struct.pack('>8I',scene,5,100,1000,1,tick,state,6 if ready else 0 if flags is None else flags)

def boundary(buttons=0x100,flags=0):
 p=bytearray(trace.input_body(True,buttons));struct.pack_into('>I',p,4,0x80000000|flags);return bytes(p)

def prefix():return record(0,0,trace.stage(),22)

def random_block(count,seed=0x12345678,callers=(0x80012340,0x80201000)):
 expected=[];indices=bytes(i%len(callers) for i in range(count));first=seed
 for index in indices:
  expected.append((callers[index],(seed>>16)&32767,seed))
  seed=(seed*1103515245+12345)&0xffffffff
 body=struct.pack('>4I',first,expected[-1][2],count,len(callers))
 return body+struct.pack('>'+str(len(callers))+'I',*callers)+indices,expected


def first_frame(inputs=True,rng=False,moves=0,flags=0,shared=True):
 out=prefix()+record(1,0,frame(),2)+record(1,0,trace.visual(),23)+record(1,0,settings(),1)
 if shared:out+=record(1,0,trace.mirror_literal(trace.mirrors(boundary(flags=flags))),24)
 if inputs:out+=record(1,0,boundary(flags=flags),14)
 if rng:out+=record(1,0,trace.rng_block(2)[0],18)
 for i in range(moves):out+=record(1,i+1,trace.input_body(False,valid=3),14)
 return out

FIXTURE=trace.FIXTURE+r'''
#include "src/ghost_world_replay.cpp"
namespace W=GhostWorldReplay;
static W::Replay replay;
static W::Movement moves[64];
alignas(32) static unsigned char randomMemory[16384*24+64];
static W::RandomCall *const randomCalls=reinterpret_cast<W::RandomCall*>(randomMemory+32);
static W::FrameView view;
static const W::Movement *movementView;
API int worldBegin(unsigned mode,unsigned game,unsigned caps,unsigned movesCap,unsigned randomCap){memset(randomMemory,0xa5,sizeof(randomMemory));return W::begin(replay,reader.version?reader.version:3,decoder.game,game,caps,static_cast<W::Mode>(mode),moves,movesCap,randomCalls,randomCap);}
API int worldFeed(){return W::feed(replay,event);}
API int worldFinish(){return W::finishSource(replay);}
API int worldSeal(unsigned frame,unsigned tick){return W::sealBoundary(replay,frame,tick);}
API int worldContinue(){return W::continueSource(replay,event.continuation);}
API int worldMovie(){return W::acceptSkippedMovie(replay);}
API int worldState(){return W::state(replay);}
API unsigned worldError(){return replay.error;}
API unsigned worldDetail(){return replay.detail;}
API unsigned worldMissing(){return replay.missingEvidence;}
API int worldInitial(){W::InitialView initial;return W::initialView(replay,initial);}
API int worldConfirm(unsigned coverage,int blocked){return W::confirmInitialization(replay,coverage,blocked);}
API int worldStart(unsigned scene,unsigned context,unsigned director,unsigned setup,int visual){
 Trace::Visual actual=replay.visual;
 if(visual==2)actual.x+=1;
 if(visual==3)actual.qf+=1;
 W::NativeFrame native={scene,context,director,(setup&1)!=0,(setup&2)!=0,visual?&actual:nullptr};
 return W::beginFrame(replay,native,view);
}
API void worldInheritedClock(){replay.inheritedClockPending=true;}
API int worldStartClock(int qf,int positionBias){
 Trace::Visual actual=replay.visual;
 actual.qf=qf;actual.x+=positionBias;
 W::NativeFrame native={replay.frame.scene,replay.frame.context,replay.frame.directorState,true,true,&actual};
 return W::beginFrame(replay,native,view);
}
API int worldClockMatches(unsigned expected,unsigned actual){return W::clockMatches(replay,expected,actual);}
API unsigned worldBoundary(unsigned field){return !view.boundary?0:field==0?view.boundary->raw.buttons:field==1?view.boundary->flags:field==2?view.sourceFrame:field==3?view.boundary->pad.enabledFrameMeaning:view.movements;}
API int worldApplied(int success){return W::inputApplied(replay,success);}
API int worldMove(unsigned cue,unsigned ordinal){return W::movement(replay,cue,ordinal,movementView);}
API unsigned worldMoveTick(){return movementView?movementView->tick:0;}
API int worldRandom(unsigned caller,unsigned result,unsigned seed){return W::verifyRandom(replay,caller,result,seed);}
static unsigned feedbackResult;
API int worldFeedback(unsigned caller,unsigned seed){feedbackResult=0xa5a5a5a5;return W::replayFeedback(replay,caller,seed,feedbackResult);}
API unsigned worldFeedbackValue(){return feedbackResult;}
API int worldFloatFeedback(unsigned caller,unsigned seed){feedbackResult=0xa5a5a5a5;return W::replayFloatFeedback(replay,caller,seed,feedbackResult);}
API int worldEnd(int observed,int matches){return W::endFrame(replay,observed,matches);}
API int worldRefuse(unsigned action){return W::refuseAction(replay,static_cast<W::PersistentAction>(action));}
API void worldCancel(){W::cancel(replay);}
API unsigned worldStats(unsigned field){W::Report r=W::report(replay);switch(field){case 0:return r.loadingFrames;case 1:return r.playedFrames;case 2:return r.movementCalls;case 3:return r.randomCalls;case 4:return r.complete;case 5:return r.experimental;default:return r.missingEvidence;}}
API unsigned worldQueued(){return replay.randomCount;}
API unsigned worldQueueBytes(){return replay.randomUsed;}
API unsigned worldSourceFrame(){return replay.sourceFrame;}
API int worldRandomGuard(){
 for(unsigned i=0;i<32;++i)if(randomMemory[i]!=0xa5)return 0;
 for(unsigned i=32+replay.randomCapacity*24;i<sizeof(randomMemory);++i)if(randomMemory[i]!=0xa5)return 0;
 return 1;
}
API int worldPeek(W::RandomCall *out){const W::RandomCall *q=W::head(replay);if(!q)return 0;*out=*q;return 1;}
API int worldBadRng(unsigned field){
 D::Event invalid=event;
 const unsigned char badIndex=64;
 switch(field){
 case 0:invalid.rng.lastSeed^=1;break;
 case 1:invalid.rng.callerCount=65;break;
 case 2:invalid.rng.indices=nullptr;break;
 case 3:invalid.rng.count=0;break;
 case 4:invalid.rng.count=1;invalid.rng.indices=&badIndex;invalid.rng.lastSeed=invalid.rng.firstSeed;break;
 }
 return W::feed(replay,invalid);
}
API void worldSetupTime(unsigned frame,unsigned tick){replay.sourceFrame=frame;replay.sourceTick=tick;}
API int worldRunExpected(const W::RandomCall *calls,unsigned count){
 W::NativeFrame native={replay.frame.scene,replay.frame.context,replay.frame.directorState,(replay.frame.flags&2)!=0,(replay.frame.flags&4)!=0,replay.haveVisual?&replay.visual:nullptr};
 if(W::beginFrame(replay,native,view)!=W::FRAME_STARTED||!W::inputApplied(replay,true))return 0;
 unsigned i=0;
 for(unsigned phase=0;phase<=replay.movementCount;++phase){
  while(i<count&&calls[i].frame==replay.sourceFrame&&calls[i].tick==replay.activeTick&&!calls[i].setup){
   const W::RandomCall &q=calls[i++];if(!W::verifyRandom(replay,q.caller,q.result,q.seed))return 0;
  }
  if(phase<replay.movementCount){if(!W::movement(replay,replay.movements[phase].input.cue,phase,movementView)||!W::inputApplied(replay,true))return 0;}
 }
 return i==count&&W::endFrame(replay,false,false);
}
API int worldConsumeSetup(){while(replay.randomCount&&W::head(replay)->setup){W::RandomCall q=*W::head(replay);if(!W::verifyRandom(replay,q.caller,q.result,q.seed))return 0;}return 1;}
API int worldRunRecordedFrame(){
 W::NativeFrame native={replay.frame.scene,replay.frame.context,replay.frame.directorState,(replay.frame.flags&2)!=0,(replay.frame.flags&4)!=0,replay.haveVisual?&replay.visual:nullptr};
 if(W::beginFrame(replay,native,view)!=W::FRAME_STARTED||!W::inputApplied(replay,true))return 0;
 for(unsigned phase=0;phase<=replay.movementCount;++phase){
  while(replay.randomCount){W::RandomCall q=*W::head(replay);if(q.setup||q.frame!=replay.sourceFrame||q.tick!=replay.activeTick)break;if(!W::verifyRandom(replay,q.caller,q.result,q.seed))return 0;}
  if(phase<replay.movementCount){if(!W::movement(replay,replay.movements[phase].input.cue,phase,movementView)||!W::inputApplied(replay,true))return 0;}
 }
 return W::endFrame(replay,false,false);
}
API unsigned worldBytes(unsigned field){return field==0?sizeof(replay):field==1?sizeof(W::Movement):sizeof(W::RandomCall);}
API int worldAliases(){return W::begin(replay,3,0x474d534a,0x474d534a,0x7ffff,W::EXPERIMENTAL,reinterpret_cast<W::Movement*>(&replay),1,randomCalls,8);}
'''.replace('Trace::Visual actual','GhostTraceDecode::Visual actual')

class ReplayTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous=trace.FIXTURE;trace.FIXTURE=FIXTURE
  try:trace.DecodeTests.setUpClass.__func__(cls)
  finally:trace.FIXTURE=previous
  cls.lib.worldBoundary.restype=C.c_uint
  cls.lib.worldPeek.argtypes=[C.c_void_p]
  cls.lib.worldRunExpected.argtypes=[C.c_void_p,C.c_uint]
 def setUp(self):
  self.reset()
 def reset(self,mode=0,game=GAME,caps=CAPS,moves=8,rng=4096,source_game=GAME):
  self.assertEqual(self.lib.decoderBegin(3,source_game,caps,0),1)
  self.pending=False;self.assertEqual(self.lib.worldBegin(mode,game,caps,moves,rng),1)
 def push(self,data):
  self.buffer=C.create_string_buffer(data);self.assertEqual(self.lib.decoderPush(self.buffer,len(data)),1)
  return self.drain()
 def drain(self):
  while True:
   if not self.pending:
    result=self.lib.decoderNext()
    self.assertNotEqual(result,2,f'typed error {self.lib.decoderError()}')
    if result==1:return 0
   result=self.lib.worldFeed();self.pending=result==1
   if result:return result
 def initialize(self,coverage=0,blocked=True):
  self.assertEqual(self.lib.worldInitial(),1);self.assertEqual(self.lib.worldConfirm(coverage,blocked),1)
 def start(self,state=1,visual=1,setup=3):
  return self.lib.worldStart(0xd00,5,state,setup,visual)
 def ready(self,data=None,mode=0,coverage=0):
  self.reset(mode=mode);self.assertEqual(self.push(first_frame() if data is None else data),0)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize(coverage)
 def call_block(self,count=2,bad=False):
  _,seeds=trace.rng_block(count)
  for i,seed in enumerate(seeds):
   ok=self.lib.worldRandom(0x80012340 if i%2==0 else 0x80201000,((seed>>16)&32767)+(1 if bad and i==0 else 0),seed)
   if bad:return ok
   self.assertEqual(ok,1,f'world RNG error {self.lib.worldError()}')
 def test_feedback_uses_literal_value_without_advancing_rng_seed(self):
  for bit in (0,1):
   self.ready(first_frame()+record(1,0,struct.pack('>3I',0x8002a1d8,bit,123),15));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
   self.assertEqual(self.lib.worldFeedback(0x8002a1d8,123),1);self.assertEqual(self.lib.worldFeedbackValue(),bit)
   self.assertEqual(self.lib.worldQueued(),0);self.assertEqual(self.lib.worldEnd(1,1),1)
 def test_feedback_rejects_wrong_consumer_seed_value_and_rng_blocks(self):
  for value,caller,seed in ((1,0x8002a1dc,123),(1,0x8002a1d8,124),(2,0x8002a1d8,123)):
   self.ready(first_frame()+record(1,0,struct.pack('>3I',0x8002a1d8,value,123),15));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
   self.assertEqual(self.lib.worldFeedback(caller,seed),0);self.assertEqual(self.lib.worldFeedbackValue()&0xffffffff,0xa5a5a5a5);self.assertEqual(self.lib.worldQueued(),1)
  self.ready(first_frame()+record(1,0,random_block(1,1,(0x8002a1d8,))[0],18));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldFeedback(0x8002a1d8,1),0)
 def test_float_feedback_preserves_exact_bounded_values(self):
  for value in (0,0x80000000,0x459c4100,0xc2c80000,0x49742400,0xc9742400):
   self.ready(first_frame()+record(1,0,struct.pack('>3I',0x801fabf4,value,123),15));self.assertEqual(self.start(),0);self.lib.worldApplied(1)
   self.assertEqual(self.lib.worldFloatFeedback(0x801fabf4,123),1);self.assertEqual(self.lib.worldFeedbackValue()&0xffffffff,value)
   self.assertEqual(self.lib.worldQueued(),0);self.assertEqual(self.lib.worldEnd(1,1),1)
 def test_float_feedback_rejects_nonfinite_out_of_range_or_wrong_request(self):
  for value,caller,seed in ((0x7f800000,0x801fabf4,123),(0xff800000,0x801fabf4,123),(0x7fc00000,0x801fabf4,123),(0x49742401,0x801fabf4,123),(0xc9742401,0x801fabf4,123),(0x459c4100,0x801fabf8,123),(0x459c4100,0x801fabf4,124)):
   self.ready(first_frame()+record(1,0,struct.pack('>3I',0x801fabf4,value,123),15));self.assertEqual(self.start(),0);self.lib.worldApplied(1)
   self.assertEqual(self.lib.worldFloatFeedback(caller,seed),0);self.assertEqual(self.lib.worldQueued(),1)
   self.assertEqual(self.lib.worldFeedbackValue()&0xffffffff,0xa5a5a5a5)
 def test_feedback_cannot_run_before_input_or_leave_extra_reads(self):
  data=first_frame()+record(1,0,struct.pack('>3I',0x8002a1d8,1,123),15)
  self.ready(data);self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldFeedback(0x8002a1d8,123),0)
  self.ready(data);self.assertEqual(self.start(),0);self.lib.worldApplied(1);self.assertEqual(self.lib.worldEnd(1,1),0)
 def test_declared_provenance_requires_each_frame_and_retains_tas(self):
  start=bytearray(trace.stage());struct.pack_into('>I',start,0,3);start+=struct.pack('>2I',0,2)
  body=first_frame()[len(prefix()):]
  self.reset(caps=CAPS|(1<<23));self.assertEqual(self.push(record(0,0,start,22)+body),0);self.assertEqual(self.lib.worldFinish(),0)
  self.reset(caps=CAPS|(1<<23));self.assertEqual(self.push(record(0,0,start,22)+body+record(1,0,struct.pack('>2I',1,0x21),28)),0)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1)
 def test_continuation_waits_for_final_prefix_frame_then_allows_next_frame(self):
  self.assertEqual(self.push(first_frame(moves=1)),0);self.initialize()
  self.assertEqual(self.lib.worldSeal(1,1),1)
  self.assertEqual(self.lib.worldStats(1),0)
  self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertEqual(self.lib.worldSeal(1,1),0)
  self.assertEqual(self.lib.worldStats(1),1)
  tail=record(2,1,frame(tick=1),2)+record(2,1,trace.visual(),23)+record(2,1,boundary(),14)
  self.assertEqual(self.push(tail),0);self.assertEqual(self.lib.worldFinish(),1)
  self.assertEqual(self.lib.worldRunRecordedFrame(),1);self.assertEqual(self.lib.worldStats(4),1)
 def test_continuation_rejects_wrong_cut_and_finished_source(self):
  for frame_no,tick in ((2,1),(1,0)):
   self.reset();self.assertEqual(self.push(first_frame(moves=1)),0);self.initialize()
   self.assertEqual(self.lib.worldSeal(frame_no,tick),2);self.assertEqual(self.lib.worldError(),6)
   self.assertEqual(self.lib.worldStats(1),0)
  self.ready();self.assertEqual(self.lib.worldSeal(1,0),2);self.assertEqual(self.lib.worldError(),6)
 def marker(self,generation=0):
  body=struct.pack('>12I',1,0x23,1,7,8,1,9,123,120,44,generation,1)
  self.buffer=C.create_string_buffer(record(1,0,body,27))
  self.assertEqual(self.lib.decoderPush(self.buffer,len(self.buffer.raw)-1),1)
  self.assertEqual(self.lib.decoderNext(),0)
 def test_continuation_generation_zero_is_only_accepted_after_barrier(self):
  self.reset(caps=CAPS|(1<<21));self.assertEqual(self.push(first_frame()),0);self.initialize()
  self.assertEqual(self.lib.worldSeal(1,0),1);self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.marker();self.assertEqual(self.lib.worldContinue(),1)
  visual=bytearray(trace.visual());struct.pack_into('>I',visual,60,0)
  tail=record(2,0,frame(),2)+record(2,0,visual,23)+record(2,0,boundary(),14)
  self.assertEqual(self.push(tail),0)
  self.reset(caps=CAPS|(1<<21));self.assertEqual(self.push(first_frame()),0);self.initialize()
  self.marker();self.assertEqual(self.lib.worldContinue(),0);self.assertEqual(self.lib.worldError(),6)
 def test_continuation_cannot_rebind_an_unrelated_stage_generation(self):
  self.reset(caps=CAPS|(1<<21));self.assertEqual(self.push(first_frame()),0);self.initialize()
  self.assertEqual(self.lib.worldSeal(1,0),1);self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.marker(generation=123456);self.assertEqual(self.lib.worldContinue(),0);self.assertEqual(self.lib.worldError(),2)
 def test_continuation_never_drops_pending_random_calls(self):
  self.assertEqual(self.push(first_frame(rng=True)),0);self.initialize()
  self.assertEqual(self.lib.worldSeal(1,0),1)
  self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldSeal(1,0),1)
  self.call_block();self.assertEqual(self.lib.worldEnd(0,0),1)
  self.assertEqual(self.lib.worldSeal(1,0),0);self.assertEqual(self.lib.worldStats(3),2)
 def test_new_stage_waits_for_departing_frame_and_new_initialization(self):
  next_stage=bytearray(trace.stage());struct.pack_into('>I',next_stage,8,0xe00)
  struct.pack_into('>2I',next_stage,16,0x0e000000,0x0e000000);struct.pack_into('>I',next_stage,28,999)
  visual=bytearray(trace.visual());struct.pack_into('>I',visual,12,0xe00);struct.pack_into('>I',visual,60,999)
  data=first_frame()+record(1,0,next_stage,22)+record(2,0,frame(scene=0xe00),2)+record(2,0,visual,23)+record(2,0,boundary(),14)
  self.assertEqual(self.push(data),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertEqual(self.drain(),0);self.assertEqual(self.lib.worldState(),1)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertEqual(self.lib.worldStats(1),2);self.assertEqual(self.lib.worldStats(4),1)
 def test_application_scene_can_change_during_unowned_loading_before_setup(self):
  stage=bytearray(trace.stage());struct.pack_into('>I',stage,8,0xe00);struct.pack_into('>2I',stage,16,0x0e000000,0x0e000000);struct.pack_into('>I',stage,28,999)
  empty=bytearray(64);struct.pack_into('>I',empty,0,1);struct.pack_into('>I',empty,12,0xe00)
  visible=bytearray(trace.visual());struct.pack_into('>I',visible,12,0xe00);struct.pack_into('>I',visible,60,999)
  data=first_frame()+record(2,0,frame(False,state=0xffffffff,scene=0xe00),2)+record(2,0,empty,23)+record(2,0,boundary(),14)
  data+=record(2,0,stage,22)+record(3,0,frame(scene=0xe00),2)+record(3,0,visible,23)+record(3,0,boundary(),14)
  self.assertEqual(self.push(data),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertEqual(self.drain(),0);self.assertEqual(self.lib.worldStats(0),1);self.assertEqual(self.lib.worldFinish(),1);self.initialize()
  self.assertEqual(self.lib.worldRunRecordedFrame(),1);self.assertEqual(self.lib.worldStats(4),1)
 def test_legacy_movie_gap_requires_recorded_skip_and_reports_timing_gap(self):
  for enabled in (False,True):
   self.reset();cfg=bytearray(settings());cfg[5]=int(enabled)
   initial=first_frame().replace(record(1,0,settings(),1),record(1,0,cfg,1))
   stage=bytearray(trace.stage());struct.pack_into('>I',stage,8,0xe00);struct.pack_into('>2I',stage,16,0x0e000000,0x0e000000);struct.pack_into('>I',stage,28,999)
   empty=bytearray(64);struct.pack_into('>I',empty,0,1);struct.pack_into('>I',empty,12,0xe00)
   visual=bytearray(trace.visual());struct.pack_into('>I',visual,12,0xe00);struct.pack_into('>I',visual,60,999)
   data=initial+record(2,0,frame(False,state=0xffffffff,scene=0xe00),2)+record(2,0,empty,23)+record(2,0,boundary(),14)
   data+=record(2,0,stage,22)+record(3,0,frame(scene=0xe00),2)+record(3,0,visual,23)+record(3,0,boundary(),14)+record(4,0,frame(scene=0xe00),2)
   self.assertEqual(self.push(data),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1);self.assertEqual(self.drain(),1)
   self.assertEqual(self.lib.worldMovie(),int(enabled))
   self.assertEqual(bool(self.lib.worldMissing()&2048),enabled)
 def test_skipped_movie_is_not_a_general_loading_bypass(self):
  self.assertEqual(self.lib.worldMovie(),0)
  self.ready();self.assertEqual(self.lib.worldMovie(),0)
 def test_a_ready_new_scene_still_requires_its_stage_start_record(self):
  self.assertEqual(self.push(first_frame()+record(2,0,frame(scene=0xe00),2)),1);self.initialize();self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertEqual(self.drain(),2);self.assertEqual(self.lib.worldError(),9)
 def test_stage_boundary_cannot_reuse_generation_or_jump_source_time(self):
  for frame_no,changed in ((1,False),(2,True)):
   self.reset();stage=bytearray(trace.stage())
   if changed:struct.pack_into('>I',stage,28,999)
   self.assertEqual(self.push(first_frame()+record(frame_no,0,stage,22)),2)
   self.assertEqual(self.lib.worldError(),9)
 def test_loading_duration_does_not_swallow_first_ready_skip_edge(self):
  out=prefix()+record(1,0,frame(False),2)+record(1,0,settings(),1)+record(1,0,boundary(0x100),14)+record(1,0,trace.rng_block(2)[0],18)
  out+=record(2,0,frame(False,flags=2),2)+record(2,0,boundary(0x200),14)
  out+=record(3,0,frame(),2)+record(3,0,trace.visual(),23)+record(3,0,boundary(0x1000),14)
  out+=record(3,0,trace.rng_block(2)[0],18)+record(3,1,trace.input_body(False,valid=3),14)
  out+=record(3,1,trace.rng_block(2)[0],18)+record(3,2,trace.input_body(False,valid=3),14)
  out+=record(4,2,frame(tick=2,state=2),2)+record(4,2,trace.visual(qf=0),23)+record(4,2,boundary(0x400,3),14)
  self.assertEqual(self.push(out),1);self.initialize()
  self.assertEqual(self.lib.worldStats(0),2)
  for _ in range(20):self.assertEqual(self.start(setup=0),2)
  self.call_block();self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldBoundary(0),0x1000);self.assertEqual(self.lib.worldBoundary(2),3)
  self.assertEqual(self.lib.worldBoundary(3),0x61);self.assertEqual(self.lib.worldBoundary(4),2)
  self.assertEqual(self.lib.worldApplied(1),1);self.call_block()
  self.assertEqual(self.lib.worldMove(1,0),1);self.assertEqual(self.lib.worldMoveTick(),1)
  self.assertEqual(self.lib.worldApplied(1),1);self.call_block()
  self.assertEqual(self.lib.worldMove(1,1),1);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(0,0),1);self.assertEqual(self.drain(),0)
  self.assertEqual(self.lib.worldFinish(),1);self.assertEqual(self.start(state=2),0)
  self.assertEqual(self.lib.worldBoundary(1),0x80000003)
  self.assertEqual(self.lib.worldApplied(1),1);self.assertEqual(self.lib.worldEnd(0,0),1)
  self.assertEqual(self.lib.worldState(),6);self.assertEqual(self.lib.worldStats(4),1)
  self.assertEqual([self.lib.worldStats(i) for i in range(4)],[2,2,2,6])
  self.assertNotEqual(self.lib.worldMissing(),0)
 def test_experimental_initialization_reports_missing_evidence(self):
  self.ready();self.assertEqual(self.lib.worldMissing(),255)
  self.assertEqual(self.start(visual=0),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(0,0),1);self.assertEqual(self.lib.worldMissing(),1023)
  self.assertEqual(self.lib.worldStats(5),1);self.assertEqual(self.lib.worldStats(4),1)
 def test_evidence_mode_requires_coverage_and_per_frame_witnesses(self):
  self.reset(mode=1);self.assertEqual(self.push(first_frame()),0);self.assertEqual(self.lib.worldFinish(),1)
  self.assertEqual(self.lib.worldConfirm(0,1),0);self.assertEqual(self.lib.worldError(),20)
  self.ready(mode=1,coverage=255);self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,1),1);self.assertEqual(self.lib.worldMissing(),0)
  self.assertEqual(self.lib.worldStats(5),0);self.assertEqual(self.lib.worldStats(4),1)
  self.ready(mode=1,coverage=255);self.assertEqual(self.start(visual=0),3);self.assertEqual(self.lib.worldError(),20)
  self.ready(mode=1,coverage=255);self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(0,0),0);self.assertEqual(self.lib.worldError(),20)
 def test_persistent_write_guard_is_required_and_actions_stop_before_execution(self):
  self.assertEqual(self.push(first_frame()),0);self.assertEqual(self.lib.worldConfirm(0,0),0)
  self.assertEqual(self.lib.worldError(),21)
  for action in (1,2,3,4):
   self.ready();self.assertEqual(self.lib.worldRefuse(action),0)
   self.assertEqual(self.lib.worldError(),22);self.assertEqual(self.lib.worldDetail(),action)
   self.assertEqual(self.start(),3);self.assertEqual(self.lib.worldStats(1),0)
 def test_same_region_capture_evidence_and_capabilities_are_mandatory(self):
  self.assertEqual(self.lib.worldBegin(0,0x474d5350,CAPS,8,4096),0);self.assertEqual(self.lib.worldError(),3)
  self.assertEqual(self.lib.worldBegin(0,GAME,CAPS&~(1<<18),8,4096),0);self.assertEqual(self.lib.worldError(),4)
  self.reset();self.assertEqual(self.push(record(0,0,trace.stage(flags=3),22)),2);self.assertEqual(self.lib.worldError(),5)
  self.reset();self.assertEqual(self.push(record(1,0,frame(),2)),2);self.assertEqual(self.lib.worldError(),5)
  self.reset(caps=CAPS|(1<<21));self.assertEqual(self.push(first_frame()),0)
 def clock_frame(self,flags=2,setup=False,caps=0x3fffff,mode=0):
  self.reset(caps=caps,mode=mode)
  v=bytearray(trace.visual(flags=flags,qf=0));struct.pack_into('>I',v,52,0)
  data=prefix()+record(1,0,frame(ready=setup,state=1 if setup else 0,flags=4),2)+record(1,0,v,23)+record(1,0,settings(),1)+record(1,0,trace.mirror_literal(trace.mirrors(boundary())),24)+record(1,0,boundary(),14)
  return self.push(data)
 def test_legacy_pre_setup_clock_migration_has_explicit_evidence(self):
  self.assertEqual(self.clock_frame(),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.start(state=0,visual=3,setup=2),0)
  self.assertEqual(self.lib.worldMissing()&(4096|32),4096|32)
 def test_legacy_clock_migration_is_refused_in_strict_mode(self):
  self.assertEqual(self.clock_frame(mode=1),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.start(state=0,visual=3,setup=2),3);self.assertEqual(self.lib.worldError(),20)
 def test_post_setup_clock_stays_exact(self):
  self.assertEqual(self.clock_frame(setup=True),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.start(state=1,visual=3),3);self.assertEqual(self.lib.worldError(),18);self.assertEqual(self.lib.worldDetail(),8)
  self.assertFalse(self.lib.worldMissing()&4096)
 def test_legacy_transition_can_carry_the_previous_stage_clock(self):
  self.reset(caps=0x3fffff);self.assertEqual(self.push(first_frame()),0);self.initialize(255)
  self.assertEqual(self.lib.worldSeal(1,0),1)
  self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  visual=bytearray(trace.visual(flags=2,qf=1812,scene=0xe00));struct.pack_into('>3I',visual,52,0,8,4)
  tail=record(1,0,trace.stage(scene=0xe00,generation=4),22)+record(2,0,frame(ready=False,state=0,scene=0xe00,flags=4),2)+record(2,0,visual,23)+record(2,0,boundary(),14)
  self.assertEqual(self.push(tail),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.lib.worldStart(0xe00,5,0,2,3),0);self.assertTrue(self.lib.worldMissing()&4096)
 def test_new_clock_capability_forbids_pre_setup_timer_claim(self):
  self.assertEqual(self.clock_frame(caps=0x7fffff),2);self.assertEqual(self.lib.worldError(),2)
  self.assertEqual(self.clock_frame(flags=0,caps=0x7fffff),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.start(state=0,visual=1,setup=2),0);self.assertFalse(self.lib.worldMissing()&4096)
 def test_unidentified_old_capture_does_not_get_clock_migration(self):
  self.assertEqual(self.clock_frame(caps=CAPS),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize(255)
  self.assertEqual(self.start(state=0,visual=3,setup=2),3);self.assertEqual(self.lib.worldError(),18)
 def inherited_clock_frames(self,mode=0):
  self.reset(mode=mode)
  def sample(index,qf,attempt):
   v=bytearray(trace.visual(qf=qf))
   struct.pack_into('>2I',v,52,(index-1)*4,attempt)
   out=record(index,0,frame(),2)+record(index,0,v,23)
   if index==1:
    out+=record(1,0,settings(),1)+record(1,0,trace.mirror_literal(trace.mirrors(boundary())),24)
   return out+record(index,0,boundary(),14)
  data=prefix()+sample(1,1908,5)+sample(2,1912,5)+sample(3,0,6)
  self.assertEqual(self.push(data),1,self.lib.worldError())
  self.initialize(255)
 def test_inherited_clock_seeds_once_and_clears_for_a_new_attempt(self):
  self.inherited_clock_frames()
  self.lib.worldInheritedClock()
  self.assertEqual(self.lib.worldStartClock(0,0),0)
  self.assertTrue(self.lib.worldMissing()&32)
  self.assertTrue(self.lib.worldClockMatches(1912,4))
  self.assertFalse(self.lib.worldClockMatches(1913,4))
  self.lib.worldApplied(1);self.assertTrue(self.lib.worldEnd(1,1))
  self.assertEqual(self.drain(),1)
  self.assertEqual(self.lib.worldStartClock(4,0),0)
  self.lib.worldApplied(1);self.assertTrue(self.lib.worldEnd(1,1))
  self.assertEqual(self.drain(),0);self.assertTrue(self.lib.worldFinish())
  self.assertEqual(self.lib.worldStartClock(0,0),0)
 def test_inherited_clock_does_not_accept_later_time_or_pose_mismatches(self):
  self.inherited_clock_frames()
  self.lib.worldInheritedClock()
  self.assertEqual(self.lib.worldStartClock(0,1),3)
  self.assertEqual(self.lib.worldDetail(),16)
  self.inherited_clock_frames()
  self.lib.worldInheritedClock()
  self.assertEqual(self.lib.worldStartClock(0,0),0)
  self.lib.worldApplied(1);self.assertTrue(self.lib.worldEnd(1,1))
  self.assertEqual(self.drain(),1)
  self.assertEqual(self.lib.worldStartClock(5,0),3)
  self.assertEqual(self.lib.worldDetail(),8)
 def test_unseeded_inherited_clock_rejects_mismatch(self):
  self.inherited_clock_frames()
  self.assertEqual(self.lib.worldStartClock(0,0),3)
  self.assertEqual(self.lib.worldDetail(),8)
 def test_native_ready_state_and_visual_mismatches_stop(self):
  for scene,context,director,visual,error in ((0xe00,5,1,1,13),(0xd00,6,1,1,13),(0xd00,5,4,1,13),(0xd00,5,1,2,18),(0xd00,5,1,3,18)):
   self.ready();self.assertEqual(self.lib.worldStart(scene,context,director,3,visual),3)
   self.assertEqual(self.lib.worldError(),error)
 def test_missing_boundary_and_processed_pad_data_are_not_reconstructed(self):
  self.assertEqual(self.push(first_frame(inputs=False)),0);self.assertEqual(self.lib.worldFinish(),0);self.assertEqual(self.lib.worldError(),8)
  self.reset();self.assertEqual(self.push(first_frame()+record(1,1,trace.input_body(False,valid=0),14)),2)
  self.assertEqual(self.lib.worldError(),8)
  self.reset();self.assertEqual(self.push(first_frame()+record(1,2,trace.input_body(False,valid=3),14)),2)
  self.assertEqual(self.lib.worldError(),11)
 def test_input_receipts_and_exact_quarter_ordinal_are_enforced(self):
  for cue,ordinal in ((1,1),(3,0)):
   self.ready(first_frame(moves=1));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
   self.assertEqual(self.lib.worldMove(cue,ordinal),0);self.assertEqual(self.lib.worldError(),11)
  self.ready(first_frame(moves=1));self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldMove(1,0),0);self.assertEqual(self.lib.worldError(),11)
  self.ready();self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(0),0);self.assertEqual(self.lib.worldError(),12)
  self.ready(first_frame(moves=1));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,1),0);self.assertEqual(self.lib.worldError(),11)
 def test_rng_has_independent_strict_consumption_and_order(self):
  self.ready(first_frame(rng=True,moves=1));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldMove(1,0),0);self.assertEqual(self.lib.worldError(),17)
  self.ready(first_frame(rng=True));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.call_block(bad=True),0);self.assertEqual(self.lib.worldError(),16)
  self.ready(first_frame(rng=True));self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,1),0);self.assertEqual(self.lib.worldError(),17)
  self.ready(first_frame(rng=True));self.assertEqual(self.start(),0)
  self.assertEqual(self.call_block(bad=True),0);self.assertEqual(self.lib.worldError(),15)
  self.ready();self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldRandom(0x80012340,0,0),0);self.assertEqual(self.lib.worldError(),14)
 def test_rings_wrap_and_capacity_is_a_hard_bound(self):
  self.reset(rng=2)
  data=prefix()+record(1,0,frame(False),2)+record(1,0,settings(),1)+record(1,0,boundary(),14)+record(1,0,trace.rng_block(2)[0],18)
  self.assertEqual(self.push(data),0);self.initialize();self.call_block()
  self.assertEqual(self.push(record(2,0,frame(),2)+record(2,0,trace.visual(),23)+record(2,0,boundary(),14)+record(2,0,trace.rng_block(2)[0],18)),0)
  self.assertEqual(self.lib.worldFinish(),1);self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1);self.call_block()
  self.assertEqual(self.lib.worldEnd(1,1),1)
  self.reset(rng=1);self.assertEqual(self.push(first_frame(rng=True)),2);self.assertEqual(self.lib.worldError(),7)
  self.reset(moves=1);self.assertEqual(self.push(first_frame(moves=2)),2);self.assertEqual(self.lib.worldError(),7)
  self.assertEqual(self.lib.worldAliases(),0);self.assertEqual(self.lib.worldError(),1)
 def test_scene_or_settings_changes_are_explicitly_unsupported(self):
  self.assertEqual(self.push(first_frame()+record(2,0,frame(scene=0xe00),2)),1);self.initialize()
  self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1);self.assertEqual(self.lib.worldEnd(1,1),1)
  self.assertEqual(self.drain(),2);self.assertEqual(self.lib.worldError(),9)
  self.reset();changed=bytearray(settings());changed[0]=1
  self.assertEqual(self.push(first_frame()+record(1,0,changed,1)),2);self.assertEqual(self.lib.worldError(),10)
 def test_cancel_and_world_desync_are_terminal(self):
  self.ready();self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,0),0);self.assertEqual(self.lib.worldError(),19)
  self.lib.worldCancel();self.assertEqual(self.lib.worldError(),19)
  self.ready();self.lib.worldCancel();self.assertEqual(self.lib.worldError(),23);self.assertEqual(self.start(),3)
 def test_initialization_rng_must_finish_before_first_ready_frame(self):
  data=prefix()+record(1,0,frame(False),2)+record(1,0,settings(),1)+record(1,0,boundary(),14)+record(1,0,trace.rng_block(2)[0],18)
  data+=record(2,0,frame(),2)+record(2,0,trace.visual(),23)+record(2,0,boundary(),14)
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize()
  self.assertEqual(self.start(),3);self.assertEqual(self.lib.worldError(),17)
 def test_no_settings_or_only_loading_is_not_an_initializable_finished_run(self):
  data=prefix()+record(1,0,frame(),2)+record(1,0,boundary(),14)
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldFinish(),0);self.assertEqual(self.lib.worldError(),20)
  self.reset();data=prefix()+record(1,0,frame(False),2)+record(1,0,settings(),1)+record(1,0,boundary(),14)
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldFinish(),0);self.assertEqual(self.lib.worldError(),24)
 def test_frozen_movement_and_preboundary_rng_are_unsupported(self):
  self.assertEqual(self.push(first_frame(moves=1,flags=1)),0);self.assertEqual(self.lib.worldFinish(),0);self.assertEqual(self.lib.worldError(),11)
  self.reset();data=prefix()+record(1,0,frame(),2)+record(1,0,trace.rng_block(2)[0],18)
  self.assertEqual(self.push(data),2);self.assertEqual(self.lib.worldError(),15)
 def test_raw_rng_results_and_source_chunk_boundaries_are_preserved(self):
  data=first_frame()+record(1,0,struct.pack('>3I',0x80012340,0xdeadbeef,17),15)
  self.assertEqual(self.push(data),0)
  self.assertEqual(self.push(record(1,1,trace.input_body(False,valid=3),14)),0)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldApplied(1),1);self.assertEqual(self.lib.worldRandom(0x80012340,0xdeadbeef,17),1)
  self.assertEqual(self.lib.worldMove(1,0),1);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,1),1);self.assertEqual(self.lib.worldStats(4),1)
 def test_legacy_missing_shared_mirrors_remain_explicit_evidence(self):
  self.ready(first_frame(shared=False));self.assertTrue(self.lib.worldMissing()&1024)
  self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1);self.assertEqual(self.lib.worldEnd(1,1),1)
  self.reset(mode=1);self.assertEqual(self.push(first_frame(shared=False)),2);self.assertEqual(self.lib.worldError(),20)
 def test_pre_resource_settings_before_stage_and_identical_repeat(self):
  data=record(0,0,settings(),1)+first_frame()
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldInitial(),1)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldApplied(1),1);self.assertEqual(self.lib.worldEnd(1,1),1)
  self.reset();changed=bytearray(settings());changed[0]=1
  self.assertEqual(self.push(record(0,0,settings(),1)+record(0,0,changed,1)+prefix()),2)
  self.assertEqual(self.lib.worldError(),10)
 def test_setup_completion_frame_preserves_first_moves(self):
  # Observed in the real armed secret capture: frame16 flags4/state0 has4 MOVEs.
  data=prefix()+record(1,0,frame(False,state=0,flags=4),2)+record(1,0,settings(),1)
  data+=record(1,0,boundary(),14)+record(1,0,trace.rng_block(2)[0],18)
  for i in range(4):data+=record(1,i+1,trace.input_body(False,valid=3),14)
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize()
  for _ in range(5):self.assertEqual(self.start(state=0,setup=0,visual=0),2)
  self.assertEqual(self.start(state=0,setup=2,visual=0),0)
  self.assertEqual(self.lib.worldApplied(1),1);self.call_block()
  for i in range(4):
   self.assertEqual(self.lib.worldMove(1,i),1);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldEnd(1,1),1)
  self.assertEqual(self.lib.worldStats(2),4);self.assertEqual(self.lib.worldStats(4),1)
  self.reset();self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldFinish(),1);self.initialize()
  self.assertEqual(self.start(state=0,setup=3,visual=0),3)

 def assert_random(self,calls,frame=1,tick=0,setup=0):
  for caller,result,seed in calls:
   observed=(C.c_uint*6)();self.assertEqual(self.lib.worldPeek(observed),1)
   self.assertEqual(tuple(observed),(caller,result,seed,frame,tick,setup))
   self.assertEqual(self.lib.worldRandom(caller,result,seed),1,f'RNG error {self.lib.worldError()}')
 def test_dense_first_frame_exceeds_old_call_limit_in_same_lease(self):
  self.reset(rng=16384);data=first_frame();expected=[];remaining=18921;seed=0x12345678
  while remaining:
   count=min(512,remaining);body,calls=random_block(count,seed)
   data+=record(1,0,body,18);expected+=calls;remaining-=count
   seed=(calls[-1][2]*1103515245+12345)&0xffffffff
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldQueued(),18921)
  self.assertLess(self.lib.worldQueueBytes(),24000);self.assertEqual(self.lib.worldRandomGuard(),1)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldApplied(1),1);self.assert_random(expected)
  self.assertEqual(self.lib.worldQueueBytes(),0);self.assertEqual(self.lib.worldQueued(),0)
  self.assertEqual(self.lib.worldEnd(1,1),1);self.assertEqual(self.lib.worldStats(3),18921)
 def test_packet_ring_wraps_and_outlives_borrowed_source_bytes(self):
  self.reset(rng=6);self.assertEqual(self.push(prefix()+record(0,0,settings(),1)),0);self.initialize()
  for iteration in range(96):
   count=1+iteration%23;callers=tuple(0x80001000+4*i for i in range(1+iteration%5))
   body,calls=random_block(count,0xf0000000+iteration,callers)
   self.assertEqual(self.push(record(0,0,body,18)),0)
   C.memset(self.buffer,0xd3,len(self.buffer))
   middle=count//2;self.assert_random(calls[:middle],frame=0,setup=1)
   tail,extra=random_block(7,0x87654321+iteration)
   self.assertEqual(self.push(record(0,0,tail,18)),0)
   C.memset(self.buffer,0xe4,len(self.buffer))
   self.assert_random(calls[middle:]+extra,frame=0,setup=1)
   self.assertEqual(self.lib.worldQueueBytes(),0);self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_raw_results_interleave_with_compact_packets_across_wrap(self):
  self.reset(rng=4);self.assertEqual(self.push(prefix()+record(0,0,settings(),1)),0);self.initialize()
  for iteration in range(24):
   body,calls=random_block(16,0x80000000+iteration)
   before=(0x80012340,0xffffffff-iteration,0x87650000+iteration)
   after=(0x80201000,0x80000000+iteration,0x76540000+iteration)
   data=record(0,0,struct.pack('>3I',*before),15)+record(0,0,body,18)+record(0,0,struct.pack('>3I',*after),15)
   self.assertEqual(self.push(data),0);C.memset(self.buffer,0xe5,len(self.buffer))
   self.assert_random([before]+calls+[after],frame=0,setup=1)
   self.assertEqual(self.lib.worldQueueBytes(),0);self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_unused_dictionary_entries_preserve_literal_capacity(self):
  self.reset(rng=1);body,calls=random_block(1,callers=tuple(0x80000000+i*4 for i in range(64)))
  self.assertEqual(self.push(first_frame()+record(1,0,body,18)),0)
  self.assertEqual(self.lib.worldQueueBytes(),24)
  self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.start(),0)
  self.assertEqual(self.lib.worldApplied(1),1);self.assert_random(calls)
  self.assertEqual(self.lib.worldEnd(1,1),1);self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_raw_queue_still_holds_16384_arbitrary_results(self):
  self.reset(rng=16384)
  data=first_frame()+b''.join(record(1,0,struct.pack('>3I',0x80001000+i*4,0xf0000000+i,0xffffffff-i),15) for i in range(16384))
  self.assertEqual(self.push(data),0);self.assertEqual(self.lib.worldQueued(),16384)
  self.assertEqual(self.lib.worldQueueBytes(),384*1024);self.assertEqual(self.lib.worldRandomGuard(),1)
  self.assertEqual(self.push(record(1,0,struct.pack('>3I',0x80000000,1,1),15)),2)
  self.assertEqual(self.lib.worldError(),7);self.assertEqual(self.lib.worldDetail(),16385)
  self.assertEqual(self.lib.worldQueued(),16384);self.assertEqual(self.lib.worldQueueBytes(),384*1024)
  self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_compact_queue_still_refuses_bounded_exhaustion_atomically(self):
  self.reset(rng=16384);self.assertEqual(self.push(first_frame()),0)
  body,_=random_block(512,callers=tuple(0x80000000+i*4 for i in range(64)))
  for _ in range(1024):
   before=(self.lib.worldQueued(),self.lib.worldQueueBytes())
   result=self.push(record(1,0,body,18))
   if result==2:break
   self.assertEqual(result,0)
  else:self.fail('Compact queue did not enforce its fixed allocation')
  self.assertEqual(self.lib.worldError(),7);self.assertGreater(before[0],16384)
  self.assertEqual((self.lib.worldQueued(),self.lib.worldQueueBytes()),before)
  self.assertLessEqual(before[1],384*1024);self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_packet_metadata_preserves_all_frame_and_tick_bits(self):
  self.reset(rng=3);self.assertEqual(self.push(prefix()+record(0,0,settings(),1)),0);self.initialize()
  for frame_no,tick in ((0x80000001,0x80000002),(0xffffffff,0xffffffff)):
   self.lib.worldSetupTime(frame_no,tick);body,calls=random_block(5)
   self.assertEqual(self.push(record(frame_no,tick,body,18)),0)
   self.assert_random(calls,frame=frame_no,tick=tick,setup=1)
  self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_compressed_call_value_seed_and_caller_are_independently_checked(self):
  for field in range(3):
   self.reset();body,calls=random_block(512,callers=tuple(0x80000000+i*4 for i in range(64)))
   self.assertEqual(self.push(first_frame()+record(1,0,body,18)),0)
   self.assertEqual(self.lib.worldFinish(),1);self.initialize();self.assertEqual(self.start(),0)
   self.assertEqual(self.lib.worldApplied(1),1);self.assert_random(calls[:257])
   invalid=list(calls[257]);invalid[field]^=1
   self.assertEqual(self.lib.worldRandom(*invalid),0);self.assertEqual(self.lib.worldError(),16)
   self.assertEqual(self.lib.worldQueued(),512-257)
 def test_packet_rng_cannot_cross_move_or_setup_order(self):
  body,calls=random_block(2)
  self.ready(first_frame()+record(1,1,trace.input_body(False,valid=3),14)+record(1,1,body,18))
  self.assertEqual(self.start(),0);self.assertEqual(self.lib.worldApplied(1),1)
  self.assertEqual(self.lib.worldRandom(*calls[0]),0);self.assertEqual(self.lib.worldError(),15)
  self.reset();self.assertEqual(self.push(first_frame()+record(1,0,body,18)),0);self.initialize()
  self.assertEqual(self.lib.worldRandom(*calls[0]),0);self.assertEqual(self.lib.worldError(),15)
 def test_packet_validation_precedes_publication(self):
  for field in range(5):
   self.reset();self.assertEqual(self.push(first_frame()),0)
   body,_=random_block(5);data=record(1,0,body,18);self.buffer=C.create_string_buffer(data)
   self.assertEqual(self.lib.decoderPush(self.buffer,len(data)),1);self.assertEqual(self.lib.decoderNext(),0)
   self.assertEqual(self.lib.worldBadRng(field),2)
   self.assertEqual(self.lib.worldError(),7 if field==3 else 2)
   self.assertEqual(self.lib.worldQueued(),0);self.assertEqual(self.lib.worldQueueBytes(),0)
   self.assertEqual(self.lib.worldRandomGuard(),1)
 def test_actual_wii_pianta6_first_frame_and_complete_capture(self):
  from pathlib import Path
  import sys
  root=Path(__file__).resolve().parents[1]
  path=root/'build/pr48-sd-trace/pr63-wii-captures/trace_C1A6804B_2C9DE32C.msgt'
  if not path.exists():self.skipTest('Private returned Wii Pianta6 capture unavailable')
  sys.path.insert(0,str(root/'tools/ghost_trace'));from inspect_trace import chunk_payload
  initialized=False;first_calls=[];first_checked=False;peak=0
  with path.open('rb') as f:
   header=struct.unpack('>16I',f.read(64));self.reset(game=header[3],source_game=header[3],caps=header[7],rng=16384)
   while True:
    words=struct.unpack('>8I',f.read(32))
    if words[0]==0x444f4e45:break
    data=chunk_payload(f,words,header[1]);offset=0
    while offset<len(data):
     kind,n,frame_no,tick=struct.unpack_from('>HHII',data,offset);offset+=12
     body=data[offset:offset+n];offset+=n
     if frame_no!=40 or kind not in (15,18):continue
     if kind==15:
      caller,result,seed=struct.unpack('>3I',body);first_calls.append((caller,result,seed,frame_no,tick,0))
     else:
      seed,last,count,table=struct.unpack_from('>4I',body);callers=struct.unpack_from('>'+str(table)+'I',body,16)
      for index in body[16+4*table:16+4*table+count]:
       first_calls.append((callers[index],(seed>>16)&32767,seed,frame_no,tick,0));seed=(seed*1103515245+12345)&0xffffffff
      self.assertEqual(first_calls[-1][2],last)
    result=self.push(data)
    while result==1:
     if not initialized:self.initialize();initialized=True
     self.assertEqual(self.lib.worldConsumeSetup(),1)
     peak=max(peak,self.lib.worldQueued())
     if self.lib.worldSourceFrame()==40:
      self.assertEqual(len(first_calls),18921);self.assertEqual(self.lib.worldQueueBytes(),20244)
      expected=(C.c_uint*(len(first_calls)*6))(*(v for row in first_calls for v in row))
      self.assertEqual(self.lib.worldRunExpected(expected,len(first_calls)),1,f'First frame error {self.lib.worldError()}')
      first_checked=True
     else:self.assertEqual(self.lib.worldRunRecordedFrame(),1,f'Frame error {self.lib.worldError()}')
     result=self.drain()
    self.assertEqual(result,0,f'Feed error {self.lib.worldError()}, detail {self.lib.worldDetail()}')
   self.assertEqual(self.lib.worldFinish(),1);self.assertEqual(self.lib.worldConsumeSetup(),1)
   if self.lib.worldState()==4:self.assertEqual(self.lib.worldRunRecordedFrame(),1)
  self.assertTrue(first_checked);self.assertEqual(peak,18921)
  self.assertEqual(self.lib.worldStats(1),2139);self.assertEqual(self.lib.worldStats(2),7836)
  self.assertEqual(self.lib.worldStats(3),2438668);self.assertEqual(self.lib.worldStats(4),1)
  self.assertEqual(self.lib.worldQueueBytes(),0);self.assertEqual(self.lib.worldRandomGuard(),1)
  # Only frame40 uses independently decoded RNG values; witnesses remain recorded observations.
  self.assertTrue(self.lib.worldMissing())
  print('Returned PAL Pianta6: 18,921 calls / 20,244 bytes at frame40; 2,438,668 calls consumed')

 def test_actual_pre_resource_capture_scheduling(self):
  from pathlib import Path
  import sys
  root=Path(__file__).resolve().parents[1];path=root/'build/pr48-sd-trace/runtime-r12-armed-capture.msgt'
  if not path.exists():self.skipTest('Private armed capture unavailable')
  sys.path.insert(0,str(root/'tools/ghost_trace'));from inspect_trace import chunk_payload
  initialized=False
  with path.open('rb') as f:
   header=struct.unpack('>16I',f.read(64));self.reset(caps=header[7],rng=16384)
   while True:
    words=struct.unpack('>8I',f.read(32))
    if words[0]==0x444f4e45:break
    data=chunk_payload(f,words,header[1]);result=self.push(data)
    while result==1:
     if not initialized:self.initialize();initialized=True
     self.assertEqual(self.lib.worldConsumeSetup(),1,f'RNG setup error {self.lib.worldError()}')
     self.assertEqual(self.lib.worldRunRecordedFrame(),1,f'Frame error {self.lib.worldError()}, detail {self.lib.worldDetail()}')
     result=self.drain()
    self.assertEqual(result,0,f'Feed error {self.lib.worldError()}, detail {self.lib.worldDetail()}')
   if not initialized:self.initialize()
   self.assertEqual(self.lib.worldFinish(),1)
   self.assertEqual(self.lib.worldConsumeSetup(),1)
   if self.lib.worldState()==4:self.assertEqual(self.lib.worldRunRecordedFrame(),1)
   self.assertEqual(self.lib.worldStats(4),1)
   self.assertGreater(self.lib.worldStats(2),0)
   # This checks event scheduling only, with expected observations supplied as witnesses.
   self.assertTrue(self.lib.worldMissing())

 def test_buffers_and_initial_views_are_bounded(self):
  self.assertLess(self.lib.worldBytes(0),2048)
  self.assertEqual(self.lib.worldBytes(1),296);self.assertEqual(self.lib.worldBytes(2),24)
  print(f'Host replay={self.lib.worldBytes(0)}; movement={self.lib.worldBytes(1)}; RNG={self.lib.worldBytes(2)} bytes')
if __name__=='__main__':unittest.main()
