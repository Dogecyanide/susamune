"""Actual branch LOOKUP + physical reader + bounded logical adapter."""
import ctypes as C,os,re,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];STAGE=ROOT;P=ROOT
sys.path.insert(0,str(ROOT/'scripts'))
import test_ghost_trace_stream as physical
import test_ghost_trace_storage as writer
import test_ghost_trace_reader as files
import test_ghost_trace_decode as records
BOOT=0x12345678;NONCE=0xabcdef01;GAME=0x474d534a;CAP=0x3fffff
EXTRA_ARM=r'''
__declspec(dllexport) void* branchPointer(unsigned which){return which?(void*)LOOKUP_RESULT:(void*)&branchMailbox;}
__declspec(dllexport) void installNamed(const char*name,const void*p,unsigned n){char path[128];_sprintf(path,"/Moonshine data/ghosts/recordings/%s",name);int i=lookup(path);if(i<0)i=testCount++;strcpy(testFiles[i].path,path);testFiles[i].bytes=p;testFiles[i].size=n;testFiles[i].live=1;testFiles[i].writable=0;}
'''
EXTRA_PPC=r'''
#include "susamune/ghost_trace_logical.hxx"
static GhostTraceBranchIo::Client maps;
static GhostTraceLogical::Stream logical;
static GhostTraceLogical::Workspace work __attribute__((aligned(32)));
static GhostArena::View rawView;static GhostTraceStream::Cursor rawCursor;
static void mapFlush(void*,const void*,unsigned){}static void mapInvalidate(void*,void*,unsigned){}
API int logicalSetup(void*mailbox,void*lookup){maps={};logical={};GhostTraceBranchIo::Hooks h={nullptr,(volatile MsTraceBranchMailbox*)mailbox,(volatile MsTraceLookup*)lookup,mapFlush,mapInvalidate};return GhostTraceBranchIo::configure(maps,h,BOOT_PLACEHOLDER);}
API int logicalStart(unsigned nonce,unsigned run,unsigned capacity,unsigned raw){
 (void)raw;GhostTraceLogical::Plan plan={work.segments,capacity,capacity>32?work.hash:nullptr,capacity>32?8192u:0u,0};
 return GhostTraceLogical::open(logical,plan,maps,stream,transport,0,{nonce,run,1},0x474d534a,0);
}
API int logicalPump(unsigned n){return GhostTraceLogical::poll(logical,n);}
API int logicalNext(){return GhostTraceLogical::nextEvent(logical,event,ticket);}
API int logicalRelease(unsigned t){return GhostTraceLogical::releaseEvent(logical,t?t:ticket);}
API int logicalChunk(){return GhostTraceLogical::nextChunk(logical,rawView,rawCursor,ticket);}
API const void*rawPointer(){return rawView.data;}API unsigned rawBytes(){return rawView.bytes;}
API int rawRelease(unsigned t){return GhostTraceLogical::releaseChunk(logical,t?t:ticket);}
API int logicalClose(){return GhostTraceLogical::close(logical);}API int logicalCancel(){return GhostTraceLogical::cancel(logical);}
API unsigned logicalGet(unsigned key){auto s=GhostTraceLogical::status(logical);switch(key){case 0:return s.phase;case 1:return s.error;case 2:return s.detail;case 3:return s.segments;case 4:return s.segment;case 5:return s.pending;case 6:return s.borrowed;case 7:return event.continuation.rngSeed;case 8:return event.continuation.actions;case 9:return maps.sequence;case 10:return logical.plan.count;case 11:return event.continuation.qf;case 12:return event.continuation.attempt;case 13:return event.continuation.generation;case 14:return event.visual.generation;case 15:return event.visual.attempt;case 16:return event.visual.qf;case 17:return event.input.pad.buttons.held;case 18:return event.input.pad.buttons.pressed;}return 0;}
API int planAlias(){GhostTraceLogical::Plan plan={(GhostTraceLogical::Segment*)hostBanks[0],1,nullptr,0,0};return GhostTraceLogical::open(logical,plan,maps,stream,transport,0,{0xabcdef01,1,1},0x474d534a,0);}
'''
def capture(run,chunks,caps=CAP):
 data=bytearray(files.capture(chunks,game=GAME));struct.pack_into('>II',data,16,NONCE,run);struct.pack_into('>I',data,28,caps);struct.pack_into('>I',data,60,files.fnv(data[:60]))
 at=64
 while at<len(data)-32:
  struct.pack_into('>I',data,at,run);count=struct.unpack_from('>I',data,at+8)[0];at+=32+count
 struct.pack_into('>I',data,len(data)-28,run);struct.pack_into('>I',data,len(data)-16,caps);return bytes(data)
def frame(n,value=0):return files.record(n,n,records.frame(tick=n),2)
def boundary(parent,chunk,raw,at=1,seed=777,actions=1):return files.record(at,at,struct.pack('>12I',1,0x23,actions,NONCE,parent,chunk,files.fnv(raw),seed,120,44,0,1),27)
def branch(child,parent,source,cut=1,frame=1):
 offset=64
 for i in range(cut):
  start=offset;size,hash=struct.unpack_from('>II',source,offset+8);offset+=32+size
 b=[NONCE,child,GAME,struct.unpack_from('>I',source,28)[0],NONCE,parent,1,frame,frame,cut,size,hash,1,offset,start,size,hash,struct.unpack_from('>I',source,60)[0],0,0,0x464f524b,1,1,0]
 data=bytearray(128);struct.pack_into('>4I',data,0,0x4d534742,1,128,1);struct.pack_into('>24I',data,16,*b);struct.pack_into('>I',data,124,files.fnv(data[:124]));return bytes(data)
class LogicalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-logical-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  old_compile=physical.compile_run;old_writer=writer.writer_source
  def compile_backend(command):
   path=d/'backend.c'
   if path.exists():path.write_text(path.read_text().replace('#define FIXTURE_FILES 20','#define FIXTURE_FILES 128')+EXTRA_ARM)
   return old_compile(command[:1]+['-I',str(P/'include'),'-I',str(ROOT/'include/susamune')]+command[1:])
  def staged_writer(*args):return old_writer(P).replace('#define LOOKUP_RESULT ((struct MsTraceLookup*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_BRANCH_LOOKUP_OFFSET))','static struct MsTraceLookup lookupResult;\n#define LOOKUP_RESULT (&lookupResult)')
  physical.compile_run=compile_backend;writer.writer_source=staged_writer
  try:physical.build_backend(d)
  finally:physical.compile_run=old_compile;writer.writer_source=old_writer
  native=(ROOT/'src/ghost_trace_stream_native.cpp').read_text();native=re.sub(r'^#include .*$', '',native,flags=re.M)
  native=native.replace('reinterpret_cast<volatile MsTraceReadMailbox*>(MS_TRACE_READ_MAILBOX_PPC(channel))','hostMailboxes[channel]').replace('reinterpret_cast<volatile MsTraceReadGrant*>(MS_TRACE_STREAM_GRANT_PPC(channel))','hostGrants[channel]').replace('reinterpret_cast<A::Address>(span.data)','hostAlias(span.data)').replace('reinterpret_cast<volatile const MsTraceMailbox*>(MS_TRACE_CONTROL_PPC)','hostWriter').replace('reinterpret_cast<const MoonshineGhostMemoryProof*>(MOONSHINE_GHOST_PROOF_PPC_BASE)','hostProof')
  native=re.sub(r'reinterpret_cast<void\*>\((MS_TRACE_BUFFER[01]_PPC|MS_TRACE_UPPER_PPC\+MS_TRACE_STREAM_PACKED_OFFSET|MS_TRACE_STREAM_IO_PPC\([01]\))\)',r'hostPointer(\1)',native)
  (d/'driver.cpp').write_text((physical.DRIVER.replace('NATIVE_SOURCE',native)+EXTRA_PPC).replace('BOOT_PLACEHOLDER',str(BOOT)+'u'))
  command=['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),'-I',str(ROOT),str(d/'driver.cpp'),str(P/'src/ghost_trace_stream.cpp'),str(ROOT/'src/ghost_trace_reader.cpp'),str(ROOT/'src/ghost_arena.cpp'),str(ROOT/'src/ghost_trace_io.cpp'),str(P/'src/ghost_trace_decode.cpp'),str(ROOT/'src/ghost_world_witness.cpp'),str(P/'src/ghost_trace_branch_io.cpp'),str(P/'src/ghost_trace_logical.cpp'),'-o',str(d/'driver.dll')]
  old_compile(command)
  cls.arm=C.CDLL(str(d/'backend.dll'));cls.ppc=C.CDLL(str(d/'driver.dll'))
  for lib in (cls.arm,cls.ppc):cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
  for name in ('mailboxBytes','received','nativePointer','branchPointer'):getattr(cls.arm,name).argtypes=[C.c_uint];getattr(cls.arm,name).restype=C.c_void_p
  cls.arm.installNamed.argtypes=[C.c_char_p,C.c_void_p,C.c_uint];cls.ppc.setup.argtypes=[C.c_void_p]*9;cls.ppc.logicalSetup.argtypes=[C.c_void_p]*2;cls.ppc.rawPointer.restype=C.c_void_p
 def setUp(self):
  self.owners=[];self.arm.readReset();self.arm.nativeInit();self.assertTrue(self.ppc.setup(self.arm.mailboxBytes(0),self.arm.mailboxBytes(1),*(self.arm.nativePointer(i) for i in range(4)),self.arm.received(0x13408000),self.arm.nativePointer(5),self.arm.nativePointer(4)));self.assertTrue(self.ppc.logicalSetup(self.arm.branchPointer(0),self.arm.branchPointer(1)))
 def add(self,run,data):return self.named(f'trace_{NONCE:08X}_{run:08X}.msgt',data)
 def named(self,name,data):
  owner=C.create_string_buffer(data);self.owners.append(owner);self.arm.installNamed(name.encode(),owner,len(data));return owner
 def map(self,child,data,suffix='msgb'):return self.named(f'ref_{NONCE:08X}_{child:08X}_464F524B_00000001_00000001.{suffix}',data)
 def tick(self,n=1):
  for _ in range(n):self.arm.readStep(1);self.ppc.logicalPump(4)
 def start(self,run,capacity=1):self.assertTrue(self.ppc.logicalStart(NONCE,run,capacity,0))
 def drain(self,raw=False):
  events=[]
  for _ in range(3000):
   result=self.ppc.logicalChunk() if raw else self.ppc.logicalNext()
   if result in (1,2):
    if raw:events.append(C.string_at(self.ppc.rawPointer(),self.ppc.rawBytes()));self.assertTrue(self.ppc.rawRelease(0))
    else:events.append((result,self.ppc.get(16),self.ppc.get(13),self.ppc.get(14),self.ppc.logicalGet(7)));self.assertTrue(self.ppc.logicalRelease(0))
   elif result==3:return events
   elif result==4:raise RuntimeError(f'{self.ppc.logicalGet(1)}/{self.ppc.logicalGet(2)}')
   else:self.tick()
  self.fail('logical stream did not settle')
 def graph(self):
  prefix=frame(1,111);root=capture(1,[prefix,frame(20,999)]);tail=capture(2,[boundary(1,1,prefix)+frame(2,222)])
  self.add(1,root);self.add(2,tail);self.map(2,branch(2,1,root));return root,tail,prefix
 def test_ordinary_file_uses_one_segment_workspace(self):
  self.add(1,capture(1,[frame(1),frame(2)]));self.start(1);events=self.drain();self.assertEqual([e[2] for e in events],[1,2]);self.assertEqual(self.ppc.logicalGet(3),1)
 def test_checked_fork_omits_old_future_and_exposes_rng_barrier(self):
  self.graph();self.start(2,2);events=self.drain();self.assertEqual([(e[0],e[1],e[2]) for e in events],[(1,2,1),(2,27,1),(1,2,2)]);self.assertEqual(events[1][4],777)
 def test_raw_mode_keeps_every_byte_in_selected_chunks(self):
  root,tail,prefix=self.graph();self.start(2,2);chunks=self.drain(True);self.assertEqual(chunks,[prefix,boundary(1,1,prefix)+frame(2,222)])
 def test_capacity_and_cycle_fail_before_events(self):
  self.graph();self.start(2,1)
  with self.assertRaisesRegex(RuntimeError,'3/'):self.drain()
  self.setUp();a=frame(1);one=capture(1,[a]);two=capture(2,[a]);self.add(1,one);self.add(2,two);self.map(1,branch(1,2,two));self.map(2,branch(2,1,one));self.start(1,4)
  with self.assertRaisesRegex(RuntimeError,'4/'):self.drain()
 def test_bad_cut_or_missing_continuation_refuses(self):
  root,tail,prefix=self.graph();bad=bytearray(branch(2,1,root));struct.pack_into('>I',bad,60,1);struct.pack_into('>I',bad,80,1);struct.pack_into('>I',bad,124,files.fnv(bad[:124]));self.map(2,bytes(bad));self.start(2,2)
  with self.assertRaises(RuntimeError):self.drain()
  self.setUp();root,tail,prefix=self.graph();self.add(2,capture(2,[frame(2)]));self.start(2,2)
  with self.assertRaisesRegex(RuntimeError,'7/'):self.drain()
 def test_pending_map_is_not_mistaken_for_ordinary(self):
  data=capture(1,[frame(1)]);self.add(1,data);self.map(1,b'partial','mbpt');self.start(1)
  with self.assertRaises(RuntimeError):self.drain()
 def test_corrupt_used_prefix_fails_but_discarded_future_is_not_read(self):
  root,tail,prefix=self.graph();bad=bytearray(root);bad[100]^=1;self.add(1,bytes(bad));self.start(2,2)
  with self.assertRaises(RuntimeError):self.drain()
  self.setUp();root,tail,prefix=self.graph();bad=bytearray(root);bad[64+32+len(prefix)+32+12]^=1;self.add(1,bytes(bad));self.start(2,2);self.assertEqual(len(self.drain()),3)
 def test_cancellation_waits_for_lookup_ack(self):
  self.add(1,capture(1,[frame(1)]));self.start(1);self.ppc.logicalPump(1);self.assertFalse(self.ppc.logicalCancel());self.assertTrue(self.ppc.logicalGet(5))
  for _ in range(20):self.ppc.logicalPump(1)
  self.assertTrue(self.ppc.logicalGet(5));self.tick(4);self.assertFalse(self.ppc.logicalGet(5))
 def test_continuation_allows_explicit_zero_generation_and_fresh_pad(self):
  old=records.input_body(boundary=True,buttons=0x100);new=records.input_body(boundary=True,buttons=0x200)
  prefix=frame(1)+files.record(1,1,old,14);root=capture(1,[prefix]);visual=bytearray(records.visual(qf=124));struct.pack_into('>II',visual,56,44,0)
  tail=capture(2,[boundary(1,1,prefix)+frame(2)+files.record(2,2,bytes(visual),23)+files.record(2,2,new,14)])
  self.add(1,root);self.add(2,tail);self.map(2,branch(2,1,root));self.start(2,2);observed=[]
  for _ in range(3000):
   result=self.ppc.logicalNext()
   if result in (1,2):
    kind=self.ppc.get(16)
    if kind==27:observed.append(('boundary',self.ppc.logicalGet(11),self.ppc.logicalGet(12),self.ppc.logicalGet(13)))
    if kind==23:observed.append(('visual',self.ppc.logicalGet(16),self.ppc.logicalGet(15),self.ppc.logicalGet(14)))
    if kind==14:observed.append(('pad',self.ppc.logicalGet(17),self.ppc.logicalGet(18)))
    self.ppc.logicalRelease(0)
   elif result==3:break
   elif result==4:self.fail(f'{self.ppc.logicalGet(1)}/{self.ppc.logicalGet(2)}')
   else:self.tick()
  self.assertEqual(observed,[('pad',0x100,0x100),('boundary',120,44,0),('visual',124,44,0),('pad',0x200,0x200)])
 def test_hash_index_resolves_more_than_thirty_two_segments(self):
  raw=frame(1);source=capture(1,[raw]);self.add(1,source)
  for run in range(2,41):
   nextRaw=boundary(run-1,1,raw,at=run-1)+frame(run);nextFile=capture(run,[nextRaw])
   self.add(run,nextFile);self.map(run,branch(run,run-1,source,frame=run-1));raw=nextRaw;source=nextFile
  self.start(40,64);events=self.drain();self.assertEqual(len(events),79);self.assertEqual(self.ppc.logicalGet(3),40)
  self.assertEqual([e[2] for e in events if e[1]==2],list(range(1,41)))
 def test_alias_plan_refuses_without_mutating_arena(self):self.assertFalse(self.ppc.planAlias());self.assertEqual(self.ppc.get(9),0x10c000)
if __name__=='__main__':unittest.main()
