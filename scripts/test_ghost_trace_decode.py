"""Exercise production typed reconstruction without allocating a whole recording."""
import ctypes as C
import importlib.util,os,struct,subprocess,tempfile,unittest
from pathlib import Path
import test_ghost_trace_reader as container
ROOT=container.ROOT
CAPS=0xfffff
GAME=0x474d534a

def frame(scene=0xd00,tick=0):
 return struct.pack('>8I',scene,5,100,1000,1,tick,4,6)

def input_body(boundary=False,buttons=0x100,valid=1):
 p=bytearray(300)
 struct.pack_into('>IIH',p,0,0 if boundary else 1,0x80000000 if boundary else 0,buttons)
 p[10:14]=bytes((0x80,0x7f,0xff,1))
 struct.pack_into('>I',p,20,valid)
 if valid&1:
  struct.pack_into('>III',p,24+0x18,buttons,buttons,0)
  struct.pack_into('>ff',p,24+0x28,.25,.5)
  struct.pack_into('>fffh',p,24+0x48,-.5,.75,1,32767)
  struct.pack_into('>II',p,24+0xd0,0x200,0x61)
  struct.pack_into('>Hh',p,24+0xe2,0x20,-5)
 if valid&2:
  struct.pack_into('>hhII',p,264,-123,456,0x200,0x100)
  struct.pack_into('>fffff',p,280,-.25,.75,.8,.1,.2)
 return bytes(p)

def delta(old,new):
 masks=[0]*3;data=bytearray()
 for i in range(75):
  if old[i*4:i*4+4]!=new[i*4:i*4+4]:masks[i//32]|=1<<(i%32);data+=new[i*4:i*4+4]
 return struct.pack('>4I',300,*masks)+data

def mirrors(input_sample):
 return input_sample[24+0x18:24+0x68]

def mirror_literal(data):return struct.pack('>2I',1,80)+data

def mirror_delta(old,new):
 mask=0;out=bytearray()
 for i in range(20):
  if old[i*4:i*4+4]!=new[i*4:i*4+4]:mask|=1<<i;out+=new[i*4:i*4+4]
 return struct.pack('>3I',1,80,mask)+out

def stage(flags=7,scene=0xd00,generation=3):
 words=[1,flags,scene,0x01000000,scene<<16,scene<<16,1234,generation,896,100,32,0x100000,GAME,0x30310000,0,0]
 if not flags&2:words[9:12]=[0]*3
 return struct.pack('>16I',*words)+bytes(896)

def visual(flags=3,qf=-1,scene=0xd00):
 p=bytearray(64);struct.pack_into('>IIiI',p,0,1,flags,qf,scene)
 if flags&1:
  struct.pack_into('>fffhHHHI',p,16,12.5,-9,22,-32768,123,4095,77,0x12345678)
  p[41]=1
 struct.pack_into('>3I',p,52,91,8,3)
 return bytes(p)

def rng_block(count=5):
 seeds=[0x12345678]
 for _ in range(count-1):seeds.append((seeds[-1]*1103515245+12345)&0xffffffff)
 return struct.pack('>6I',seeds[0],seeds[-1],count,2,0x80012340,0x80201000)+bytes(i%2 for i in range(count)),seeds

FIXTURE=container.FIXTURE+r'''
#include "src/ghost_world_witness.cpp"
#include "src/ghost_trace_decode.cpp"
namespace D=GhostTraceDecode;
static D::Decoder decoder;
static D::Event event;
static unsigned totals[16];
API int decoderBegin(unsigned version,unsigned game,unsigned caps,unsigned required){memset(totals,0,sizeof(totals));return D::begin(decoder,version,game,caps,required);}
API int readerDecoderBegin(){return decoderBegin(reader.version,reader.game,reader.capabilities,0);}
API int decoderPush(const void*p,unsigned n){return D::pushChunk(decoder,p,n);}
API int decoderNext(){return D::next(decoder,event);}
API unsigned decoderError(){return decoder.error;}
API unsigned decoderWorkspace(){return sizeof(decoder)+sizeof(event);}
API unsigned decoderOnly(){return sizeof(decoder);}
API unsigned eventOnly(){return sizeof(event);}
API int decodeReaderChunk(){
 if(!D::pushChunk(decoder,reader.output,reader.chunkBytes))return 0;
 D::Result result;
 while((result=D::next(decoder,event))==D::EVENT){
  ++totals[event.type];
  if(event.type==D::INPUT)++totals[(event.input.flags&D::kFrameInput)?7:8];
 }
 return result==D::CHUNK_DONE;
}
API unsigned total(unsigned i){return i<16?totals[i]:0;}
API unsigned value(unsigned key){
 switch(key){
 case 0:return event.type;case 1:return event.kind;case 2:return event.frame;case 3:return event.tick;case 4:return event.offset;
 case 5:return event.input.cue;case 6:return event.input.flags;case 7:return event.input.valid;
 case 8:return event.input.raw.buttons;case 9:return event.input.pad.buttons.held;
 case 10:return event.input.pad.meaning;case 11:return event.input.pad.enabledFrameMeaning;
 case 12:return event.visual.flags;case 13:return event.visual.qf;case 14:return event.visual.animationId;
 case 15:return event.visual.animationPhase;case 16:return event.visual.yaw;case 17:return event.visual.attempt;case 18:return event.visual.generation;
 case 35:return event.runFlags;case 33:return event.stage.npcPollutionPhase;case 34:return event.stage.observations;
 case 19:return event.stage.flags;case 20:return event.stage.generation;case 21:return event.stage.rngSeed;
 case 22:return event.rng.count;case 23:return event.rng.lastSeed;case 24:return event.frameData.scene;
 case 25:return event.input.work.held;case 26:return event.input.work.stickX;
 case 30:return event.input.sharedKnown;case 31:return event.input.shared.buttons.held;case 32:return event.input.shared.buttons.pressed;
 case 27:return event.input.pad.disabledFrames;case 28:return event.input.pad.stick.rawX;case 29:return event.input.pad.stickTimer;
 default:return 0;
 }
}
API void* raw(){return &event.input.raw;}
API float floatValue(unsigned key){return key==0?event.visual.x:key==1?event.input.pad.stick.x:key==3?event.input.pad.meaningAxes[9]:key==4?event.input.work.right:key==5?event.input.work.left:event.input.work.x;}
API int evidence(unsigned game){return D::hasPreStageEvidence(decoder,event.stage,game);}
API int call(unsigned index,unsigned*out){return D::rngCall(event.rng,index,out[0],out[1],out[2]);}
'''

class DecodeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-trace-decode-');cls.addClassCleanup(cls.temp.cleanup)
  d=Path(cls.temp.name);(d/'fixture.cpp').write_text(FIXTURE,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++11','-O2','-Wall','-Wextra','-shared','-static','-Wno-unused-function','-I',str(ROOT/'include'),'-I',str(ROOT),str(d/'fixture.cpp'),str(ROOT/'src/ghost_trace_reader.cpp'),'-o',str(d/'decode.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr[:5000])
  cls.lib=C.CDLL(str(d/'decode.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.decoderPush.argtypes=[C.c_void_p,C.c_uint]
  cls.lib.target.restype=cls.lib.chunk.restype=cls.lib.raw.restype=C.c_void_p
  cls.lib.value.restype=C.c_uint
  cls.lib.floatValue.restype=C.c_float
  cls.lib.call.argtypes=[C.c_uint,C.POINTER(C.c_uint)]
 def begin(self,version=3,game=GAME,caps=CAPS,required=0):
  self.assertEqual(self.lib.decoderBegin(version,game,caps,required),1)
 def push(self,data):
  self.data=C.create_string_buffer(data);self.assertEqual(self.lib.decoderPush(self.data,len(data)),1)
 def event(self,kind):
  self.assertEqual(self.lib.decoderNext(),0,f'decoder error {self.lib.decoderError()}')
  self.assertEqual(self.lib.value(1),kind)
 def bad(self,data,error=None,caps=CAPS,version=3):
  self.begin(caps=caps,version=version);self.push(data)
  while self.lib.decoderNext()==0:pass
  self.assertNotEqual(self.lib.decoderError(),0)
  if error is not None:self.assertEqual(self.lib.decoderError(),error)
  self.assertEqual(self.lib.decoderNext(),2)
 def test_new_observations_decode_without_changing_legacy_frame(self):
  context=struct.pack('>11I',1,1,4,20,0x8b,0x06030100,0,0,0x40,3,0x603)
  animation=struct.pack('>7I',1,5,1,12,0x41012345,0x3f000000,50)
  self.begin();self.push(container.record(1,0,frame(),2)+container.record(1,0,context,29)+container.record(1,0,animation,29))
  self.event(2);self.event(29);self.event(29);self.assertEqual(self.lib.decoderNext(),1)
 def test_mod_hold_frame_flag_and_old_flags_are_both_accepted(self):
  for flags in (6,7,14,15):
   sample=bytearray(frame());struct.pack_into('>I',sample,28,flags)
   self.begin();self.push(container.record(1,0,sample,2));self.event(2)
  sample=bytearray(frame());struct.pack_into('>I',sample,28,16)
  self.bad(container.record(1,0,sample,2))
 def test_spin_observation_tuple_and_future_optional_subtype(self):
  for caller in range(1,10):
   for result,direction in ((0,4),(1,2),(1,3)):
    data=struct.pack('>7I',1,4,1,caller,result,direction,1)
    self.begin();self.push(container.record(1,0,data,29));self.event(29)
  for result,direction in ((0,2),(1,4),(2,3)):
   self.bad(container.record(1,0,struct.pack('>7I',1,4,1,1,result,direction,1),29))
  self.begin();self.push(container.record(1,0,struct.pack('>2I',1,999),29));self.event(29)
 def test_future_optional_byte_payload_matches_inspector(self):
  body=struct.pack('>2I',1,999)+b'x'
  self.begin();self.push(container.record(1,0,body,29));self.event(29)
  import importlib.util
  spec=importlib.util.spec_from_file_location('new_inspector',ROOT/'tools/ghost_trace/inspect_trace.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  self.assertEqual(module.validate_observation(body),999)
 def test_movie_skip_choice_two_preserves_old_session_values(self):
  for choice in (0,1,2):
   body=bytearray(64);body[5]=choice;struct.pack_into('>fI',body,48,60.0,1)
   self.begin();self.push(container.record(1,0,body,1));self.event(1)
  body[5]=3;self.bad(container.record(1,0,body,1))
 def test_malformed_observation_fields_are_rejected(self):
  for data in (b'',struct.pack('>2I',2,1),struct.pack('>11I',1,1,5,0,0,0,0,0,0,0,0),struct.pack('>4I',1,2,2048,4),struct.pack('>7I',1,5,1,3,0x7fc00000,0,20)):
   self.bad(container.record(1,0,data,29))
 def test_chronological_input_delta_shared_between_frame_and_movement_and_chunks(self):
  a=input_body(True);b=input_body(False,0x200,3);c=input_body(True,0x400)
  self.begin();self.push(container.record(1,0,frame(),2)+container.record(1,0,a,14))
  self.event(2);self.event(14)
  self.assertEqual(self.lib.value(6),0x80000000);self.assertEqual(self.lib.value(11),0x61)
  self.assertEqual(C.string_at(self.lib.raw(),12),struct.pack('<HbbbbBBBBbB',0x100,-128,127,-1,1,0,0,0,0,0,0))
  self.assertEqual(self.lib.floatValue(1),-.5)
  self.assertEqual(self.lib.decoderNext(),1)
  self.push(container.record(1,1,delta(a,b),20)+container.record(2,1,frame(tick=1),2)+container.record(2,1,delta(b,c),20))
  self.event(20);self.assertEqual(self.lib.value(5),1);self.assertEqual(self.lib.value(9),0x200);self.assertEqual(self.lib.value(25),0x200)
  self.assertEqual(C.c_int(self.lib.value(26)).value,-123)
  self.event(2);self.event(20);self.assertEqual(self.lib.value(9),0x400)
  self.assertEqual(self.lib.decoderNext(),1)
 def test_scene_change_requires_new_literal_but_same_scene_stage_does_not(self):
  a=input_body(True)
  self.begin();self.push(container.record(1,0,frame(),2)+container.record(1,0,a,14)+container.record(1,0,stage(generation=4),22)+container.record(2,0,frame(),2)+container.record(2,0,delta(a,a),20))
  for k in (2,14,22,2,20):self.event(k)
  self.assertEqual(self.lib.decoderNext(),1)
  self.push(container.record(3,0,frame(0xe00),2)+container.record(3,0,delta(a,a),20));self.event(2)
  self.assertEqual(self.lib.decoderNext(),2);self.assertEqual(self.lib.decoderError(),7)
 def test_delta_baseline_mask_and_length_fail_closed(self):
  a=input_body();valid=container.record(1,1,a,14)
  self.bad(container.record(1,1,delta(a,a),20),7)
  for d in (struct.pack('>4I',300,0,0,1<<11),struct.pack('>4I',300,1,0,0),delta(a,a)+bytes(4),struct.pack('>4I',296,0,0,0)):
   self.bad(valid+container.record(1,2,d,20))
  self.bad(valid+container.record(1,2,delta(a,a),20),6,version=1)
 def test_input_semantics_and_pointer_bytes_never_exposed(self):
  good=bytearray(input_body(True));struct.pack_into('>I',good,24,0xffffffff)
  self.begin();self.push(container.record(1,0,good,14));self.event(14);self.assertEqual(self.lib.value(9),0x100)
  for at,word in ((0,1),(4,0x80000004),(20,3),(24+0x48,0x7fc00000)):
   bad=bytearray(input_body(True));struct.pack_into('>I',bad,at,word);self.bad(container.record(1,0,bad,14))
  bad=bytearray(input_body(False,valid=0));bad[264]=1;self.bad(container.record(1,1,bad,14))
  self.bad(container.record(1,0,input_body(True),14),3,caps=CAPS&~(1<<18))
 def test_visual_checked_normalized_and_missing_pose(self):
  self.begin();self.push(container.record(1,0,visual(),23));self.event(23)
  self.assertEqual(C.c_int(self.lib.value(13)).value,-1);self.assertEqual(self.lib.value(14),123)
  self.assertEqual(self.lib.value(15),4095);self.assertEqual(C.c_int(self.lib.value(16)).value,-32768)
  self.assertEqual(self.lib.floatValue(0),12.5)
  self.assertEqual(self.lib.decoderNext(),1);self.push(container.record(2,0,visual(flags=0,qf=0),23));self.event(23)
  self.assertEqual(self.lib.value(12),0)
  for at,value in ((0,2),(4,4),(16,0x7f800000),(28,336),(32,4096<<16),(40,0x00010001),(44,0x40000000)):
   bad=bytearray(visual());struct.pack_into('>I',bad,at,value);self.bad(container.record(1,0,bad,23))
  bad=bytearray(visual(flags=0,qf=0));bad[16]=1;self.bad(container.record(1,0,bad,23))
 def test_stage_evidence_same_region_without_build_gate(self):
  self.begin();self.push(container.record(0,0,stage(),22));self.event(22)
  self.assertEqual(self.lib.evidence(GAME),1);self.assertEqual(self.lib.evidence(0x474d5350),0)
  self.assertEqual(self.lib.value(21),1234)
  self.assertEqual(self.lib.decoderNext(),1);self.push(container.record(1,0,stage(flags=3),22));self.event(22)
  self.assertEqual(self.lib.evidence(GAME),0)
  for at,value in ((0,2),(4,8),(8,0x10000),(28,0),(32,895),(36,0xffffffff),(48,0x474d5350)):
   bad=bytearray(stage());struct.pack_into('>I',bad,at,value);self.bad(container.record(0,0,bad,22))
 def test_npc_phase_is_versioned_and_legacy_remains_explicitly_absent(self):
  self.begin();self.push(container.record(0,0,stage(),22));self.event(22);self.assertEqual(self.lib.value(33),0xffffffff)
  for phase in (0,9,29):
   data=bytearray(stage());struct.pack_into('>I',data,0,2);data+=struct.pack('>I',phase)
   self.begin(caps=CAPS|(1<<23));self.push(container.record(0,0,data,22));self.event(22);self.assertEqual(self.lib.value(33),phase)
 def test_npc_phase_capability_schema_and_bounds_are_checked(self):
  good=bytearray(stage());struct.pack_into('>I',good,0,2);good+=struct.pack('>I',9)
  self.bad(container.record(0,0,good,22),6)
  self.bad(container.record(0,0,stage(),22),6,caps=CAPS|(1<<23))
  for phase in (30,0x80000000,0xffffffff):
   bad=good[:-4]+struct.pack('>I',phase);self.bad(container.record(0,0,bad,22),8,caps=CAPS|(1<<23))
  for bad in (good[:-1],good+bytes(4)):
   self.bad(container.record(0,0,bad,22),6,caps=CAPS|(1<<23))
 def test_stage_consumer_observations_are_explicit_and_bounded(self):
  data=bytearray(stage());struct.pack_into('>I',data,0,3);data+=struct.pack('>2I',9,1)
  self.begin(caps=CAPS|(1<<23));self.push(container.record(0,0,data,22));self.event(22);self.assertEqual(self.lib.value(34),1)
  for body in (b'',bytes(4),bytes(60),data[:-1],data+bytes(4)):
   self.bad(container.record(0,0,body,22),6,caps=CAPS|(1<<23))
  for flags in (4,7,8,15):
   self.begin(caps=CAPS|(1<<23));self.push(container.record(0,0,data[:-4]+struct.pack('>I',flags),22));self.event(22);self.assertEqual(self.lib.value(34),flags)
  for flags in (16,0xffffffff):self.bad(container.record(0,0,data[:-4]+struct.pack('>I',flags),22),8,caps=CAPS|(1<<23))
 def test_provenance_is_monotonic_and_tas_requires_assisted(self):
  self.begin();self.push(b''.join(container.record(i,0,struct.pack('>2I',1,v),28) for i,v in enumerate((0,0x21,0x23))))
  for value in (0,0x21,0x23):self.event(28);self.assertEqual(self.lib.value(35),value)
  self.assertEqual(self.lib.decoderNext(),1)
  for bad in (32,2,4,0x40):self.bad(container.record(0,0,struct.pack('>2I',1,bad),28),8)
  self.bad(container.record(0,0,struct.pack('>2I',1,0x21),28)+container.record(1,0,struct.pack('>2I',1,0),28),8)
  self.bad(container.record(0,0,struct.pack('>2I',2,0),28),6)
 def test_rng_block_reconstruction_and_bounds(self):
  body,seeds=rng_block(512)
  self.begin();self.push(container.record(0,0,body,18));self.event(18)
  for i in (0,1,2,3,15,63,255,511):
   out=(C.c_uint*3)();self.assertEqual(self.lib.call(i,out),1)
   self.assertEqual(list(out),[0x80012340 if i%2==0 else 0x80201000,(seeds[i]>>16)&32767,seeds[i]])
  self.assertEqual(self.lib.call(512,(C.c_uint*3)()),0)
  for at,value in ((4,0),(8,513),(12,65),(16,0x1000)):
   bad=bytearray(body);struct.pack_into('>I',bad,at,value);self.bad(container.record(0,0,bad,18))
  bad=bytearray(body);bad[-1]=2;self.bad(container.record(0,0,bad,18))
  self.assertEqual(self.lib.decoderBegin(3,GAME,CAPS,0),1)
  self.push(container.record(1,0,struct.pack('>3I',0x80012340,0xdeadbeef,17),15));self.event(15)
  out=(C.c_uint*3)();self.assertEqual(self.lib.call(0,out),1);self.assertEqual(list(out),[0x80012340,0xdeadbeef,17])
 def test_optional_future_records_and_capabilities_and_container_versions(self):
  for version in (1,2,3):
   self.begin(version=version,caps=CAPS|(1<<23));self.push(container.record(1,0,b'optional schema',60000)+container.record(1,0,frame(),2));self.event(2)
   self.assertEqual(self.lib.decoderNext(),1)
  for version,game,caps,required in ((4,GAME,CAPS,0),(3,0,CAPS,0),(3,GAME,CAPS,1<<20),(3,GAME,0,2)):
   self.assertEqual(self.lib.decoderBegin(version,game,caps,required),0)
 def test_boundaries_order_and_unconsumed_chunk_ownership(self):
  a=container.record(2,2,frame(tick=2),2)
  self.bad(a+container.record(1,2,b'',99),5)
  self.bad(a+container.record(3,1,b'',99),5)
  self.bad(a+b'bad',4)
  self.begin();self.push(a);self.assertEqual(self.lib.decoderPush(self.data,len(a)),0)
 def test_host_inspector_matches_typed_capability_and_evidence_rules(self):
  spec=importlib.util.spec_from_file_location('ms_trace_inspector',ROOT/'tools/ghost_trace/inspect_trace.py')
  inspector=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspector)
  path=Path(self.temp.name)/'inspect.msgt'
  def inspect(payload,caps=CAPS):
   encoded=bytearray(container.capture([payload],game=GAME))
   struct.pack_into('>I',encoded,28,caps);struct.pack_into('>I',encoded,60,container.fnv(encoded[:60]))
   struct.pack_into('>I',encoded,len(encoded)-16,caps);path.write_bytes(encoded)
   return inspector.inspect(path)
  payload=container.record(0,0,stage(flags=3),22)+container.record(1,0,frame(),2)+container.record(1,0,visual(),23)+container.record(1,0,b'future optional',65000)
  summary=inspect(payload,CAPS|(1<<21))
  self.assertEqual(summary['late_stage_samples'],1);self.assertEqual(summary['pre_stage_samples'],0)
  self.assertEqual(summary['records']['optional_65000'],1);self.assertFalse(summary['full_world_replay_proven'])
  self.assertEqual(summary['visual_pose_frames'],1)
  with self.assertRaises(ValueError):inspect(payload,CAPS&~(1<<17))
  for at,value in ((16,0x7fc00000),(32,4096<<16),(44,0x40000000)):
   bad=bytearray(visual());struct.pack_into('>I',bad,at,value)
   with self.assertRaises(ValueError):inspect(container.record(1,0,bad,23))
  a=input_body(True);b=input_body(False,0x200,3)
  summary=inspect(container.record(1,0,frame(),2)+container.record(1,0,a,14)+container.record(1,1,delta(a,b),20))
  self.assertEqual((summary['frame_inputs'],summary['movement_inputs']),(1,1))
  self.assertEqual(summary['input_shared_missing'],2)
  summary=inspect(container.record(1,0,frame(),2)+container.record(1,0,mirror_literal(mirrors(a)),24)+container.record(1,0,a,14)+container.record(1,1,mirror_delta(mirrors(a),mirrors(b)),25)+container.record(1,1,delta(a,b),20))
  self.assertEqual(summary['input_shared_known'],2);self.assertEqual(summary['input_shared_missing'],0)
  with self.assertRaises(ValueError):inspector.apply_mirrors(struct.pack('>3I',1,80,1<<20),3,bytearray(80),25)
  with self.assertRaises(ValueError):inspect(container.record(1,0,delta(a,b),20))
  with self.assertRaises(ValueError):inspector.apply_blob(struct.pack('>4I',0x80300000,0,512,4)+bytes(4),3,{},3)
 def test_all_canonical_controller_scalars_use_decomp_offsets(self):
  body=bytearray(input_body(valid=3))
  struct.pack_into('>f',body,24+0xcc,.875);struct.pack_into('>i',body,24+0xe8,-17)
  body[24+0x56:24+0x58]=bytes((0x80,0xff))
  self.begin();self.push(container.record(1,1,body,14));self.event(14)
  self.assertAlmostEqual(self.lib.floatValue(3),.875);self.assertAlmostEqual(self.lib.floatValue(4),.1)
  self.assertAlmostEqual(self.lib.floatValue(5),.2)
  self.assertEqual(C.c_int(self.lib.value(27)).value,-17)
  self.assertEqual(C.c_int(self.lib.value(28)).value,-128)
  self.assertEqual(C.c_int(self.lib.value(29)).value,-5)
  struct.pack_into('>I',body,24+0xcc,0x7f800000);self.bad(container.record(1,1,body,14))
 def test_captured_shared_mirrors_attach_to_inputs_with_independent_delta_chain(self):
  a=input_body(True,0x100);b=input_body(False,0x200,3)
  m=mirrors(input_body(True,0x1000));n=mirrors(input_body(True,0x400))
  self.begin();self.push(container.record(1,0,frame(),2)+container.record(1,0,mirror_literal(m),24)+container.record(1,0,a,14))
  self.event(2);self.event(14);self.assertEqual(self.lib.value(30),1)
  self.assertEqual(self.lib.value(31),0x1000);self.assertEqual(self.lib.value(9),0x100)
  self.assertEqual(self.lib.decoderNext(),1)
  self.push(container.record(1,1,mirror_delta(m,n),25)+container.record(1,1,delta(a,b),20)+container.record(1,2,delta(b,b),20))
  self.event(20);self.assertEqual(self.lib.value(31),0x400);self.assertEqual(self.lib.value(9),0x200)
  self.event(20);self.assertEqual(self.lib.value(30),1);self.assertEqual(self.lib.value(31),0x400)
  self.assertEqual(self.lib.decoderNext(),1)
 def test_shared_mirror_baseline_resets_only_on_frame_scene_change(self):
  a=input_body(True);m=mirrors(a)
  self.begin();self.push(container.record(1,0,frame(),2)+container.record(1,0,mirror_literal(m),24)+container.record(1,0,a,14)+container.record(1,0,stage(generation=4),22)+container.record(2,0,frame(),2)+container.record(2,0,a,14))
  for k in (2,14,22,2,14):self.event(k)
  self.assertEqual(self.lib.value(30),1);self.assertEqual(self.lib.decoderNext(),1)
  self.push(container.record(3,0,frame(0xe00),2)+container.record(3,0,a,14));self.event(2);self.event(14)
  self.assertEqual(self.lib.value(30),0);self.assertEqual(self.lib.decoderNext(),1)
  self.push(container.record(3,0,mirror_delta(m,m),25));self.assertEqual(self.lib.decoderNext(),2);self.assertEqual(self.lib.decoderError(),7)
 def test_shared_mirror_schema_mask_bounds_and_missing_capability(self):
  m=mirrors(input_body(True));literal=container.record(1,0,mirror_literal(m),24)
  self.bad(container.record(1,0,mirror_delta(m,m),25),7)
  self.bad(literal,3,caps=CAPS&~(1<<19))
  self.bad(literal+container.record(1,0,mirror_delta(m,m),25),6,version=1)
  for body in (struct.pack('>3I',1,80,1<<20),struct.pack('>3I',1,80,1),mirror_delta(m,m)+bytes(4),struct.pack('>3I',2,80,0),struct.pack('>3I',1,84,0)):
   self.bad(literal+container.record(1,0,body,25))
  bad=bytearray(m);struct.pack_into('>I',bad,48,0x7fc00000)
  self.bad(container.record(1,0,mirror_literal(bad),24),8)
 def test_legacy_inputs_report_shared_mirrors_missing(self):
  self.begin(caps=0x7ffff);self.push(container.record(1,0,input_body(True),14));self.event(14)
  self.assertEqual(self.lib.value(30),0);self.assertEqual(self.lib.value(31),0)
 def test_native_work_remains_observational_even_when_uninitialized(self):
  body=bytearray(input_body(False,valid=3));struct.pack_into('>I',body,292,0x7fc01234)
  self.begin();self.push(container.record(1,1,body,14));self.event(14)
  import math
  self.assertTrue(math.isnan(self.lib.floatValue(4)))
 def test_real_capture_typed_reconstruction(self):
  files=sorted((ROOT/'build/pr48-sd-trace/wii-r9-captures').glob('*.msgt'))
  recent=ROOT/'build/pr48-sd-trace/runtime-r12-capture.msgt'
  if recent.exists():files.append(recent)
  if not files:self.skipTest('Private capture fixtures unavailable')
  for path in files:
   with self.subTest(capture=path.name),path.open('rb') as f:
    self.assertEqual(self.lib.start(path.stat().st_size),1);started=False
    while self.lib.state()==0:
     self.assertEqual(self.lib.next(),1)
     f.seek(self.lib.offset());data=f.read(self.lib.size());C.memmove(self.lib.target(),data,len(data))
     self.assertEqual(self.lib.accept(len(data)),1,f'container error {self.lib.error()}')
     if self.lib.state()==1:
      if not started:self.assertEqual(self.lib.readerDecoderBegin(),1);started=True
      self.assertEqual(self.lib.decodeReaderChunk(),1,f'{path.name}: typed error {self.lib.decoderError()}')
      self.assertEqual(self.lib.release(),1)
    self.assertEqual(self.lib.state(),2);self.assertEqual(self.lib.guards(),1)
    self.assertGreater(self.lib.total(0),0);self.assertGreater(self.lib.total(1),0)
    if path==recent:self.assertEqual(self.lib.total(3),151);self.assertEqual(self.lib.total(2),1)
    else:self.assertEqual(self.lib.total(3),0);self.assertEqual(self.lib.total(2),0)
  print(f'Checked {len(files)} captures; host decoder/event={self.lib.decoderOnly()}/{self.lib.eventOnly()} bytes')
if __name__=='__main__':unittest.main()
