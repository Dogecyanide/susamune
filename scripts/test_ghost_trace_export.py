"""Actual logical reader, encoded-copy exporter, source pins and transactional ARM writer."""
import ctypes as C,io,os,re,struct,subprocess,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT
sys.path.insert(0,str(ROOT/'scripts'))
import test_ghost_trace_stream as native
import test_ghost_trace_storage as storage
import test_ghost_trace_reader as files
import test_ghost_trace_decode as records
from ghost_trace_publication_fixture import writer_source
BOOT=0x12345678;NONCE=0xabcddcba;OUT=0x12345678;RUN=77;GAME=0x474d534a;CAP=0x3fffff
ARM=r'''
__declspec(dllexport) void* exportPointer(unsigned i){switch(i){case 0:return &branchMailbox;case 1:return LOOKUP_RESULT;case 2:return EXPORT_BOX;case 3:return EXPORT_DATA;}return 0;}
__declspec(dllexport) void exportReset(){memset(exportMemory,0xa5,sizeof(exportMemory));}
__declspec(dllexport) int exportGuards(){for(unsigned i=0;i<32;++i)if(exportMemory[i]!=0xa5||exportMemory[MS_TRACE_EXPORT_BUFFER_BYTES+32+i]!=0xa5)return 0;return 1;}
__declspec(dllexport) void named(const char*name,const void*p,unsigned n){int i=lookup(name);if(i<0)i=testCount++;strcpy(testFiles[i].path,name);testFiles[i].bytes=p;testFiles[i].size=n;testFiles[i].live=1;testFiles[i].writable=0;}
__declspec(dllexport) const void* namedBytes(const char*name,unsigned*n){int i=lookup(name);if(i<0){*n=0;return 0;}*n=testFiles[i].size;return testFiles[i].bytes;}
__declspec(dllexport) void damage(const char*name,unsigned offset){int i=lookup(name);if(i>=0&&offset<testFiles[i].size)((unsigned char*)testFiles[i].bytes)[offset]^=1;}
__declspec(dllexport) unsigned exportPhase(){return EXPORT_WRITER->response.phase;}
__declspec(dllexport) unsigned exportStatus(){return EXPORT_WRITER->response.status;}
__declspec(dllexport) void rawExport(unsigned operation,unsigned nonce,unsigned run,const void*data,unsigned bytes,unsigned flags){
 struct TraceExportWriter*w=EXPORT_WRITER;struct MsTraceExportRequest*q=&testExportBox.request;struct MsTraceExportTransfer*b=&testExportBox.transfer;
 unsigned sequence=q->sequence+1;*q=(struct MsTraceExportRequest){MS_TRACE_EXPORT_MAGIC,MS_TRACE_EXPORT_VERSION,WRITER->response.nonce,sequence,operation,nonce,run,GAME_ID};
 memset(b,0,sizeof(*b));b->flags=flags;
 if(operation==MS_TRACE_EXPORT_APPEND||operation==MS_TRACE_EXPORT_COMMIT){
  if(bytes>MS_TRACE_EXPORT_MAX_WRITE)return;
  memcpy(EXPORT_DATA,data,bytes);b->physical=MS_TRACE_EXPORT_BUFFER_PHYS;b->capacity=MS_TRACE_EXPORT_BUFFER_BYTES;b->bytes=bytes;b->lease=1;
  b->checksum=MsTraceHash(2166136261u,EXPORT_DATA,bytes);b->totalBytes=w->response.bytes;
  b->fileAdler=operation==MS_TRACE_EXPORT_COMMIT?MsTraceAdlerReplaceHeader(w->adler,w->header,EXPORT_DATA,w->response.bytes):MsTraceAdler(w->adler,EXPORT_DATA,bytes);
 }
 exportService();
}
'''
PPC=r'''
#include "susamune/ghost_trace_flat.hxx"
static GhostTraceBranchIo::Client maps;
static GhostTraceLogical::Stream logical;
static GhostTraceLogical::Workspace workspace __attribute__((aligned(32)));
static GhostTraceExportIo::Client output;
static GhostTraceFlat::Task job;
static void*outBytes;
static void noopFlush(void*,const void*,unsigned){}static void noopInvalidate(void*,void*,unsigned){}
static bool exportPhysical(void*,GhostArena::Span s,unsigned&out){if(s.data!=outBytes||s.bytes!=MS_TRACE_EXPORT_BUFFER_BYTES)return false;out=MS_TRACE_EXPORT_BUFFER_PHYS;return true;}
API int flatSetup(void*branch,void*lookup,void*box,void*buffer){
 maps={};logical={};output={};job={};outBytes=buffer;
 GhostTraceBranchIo::Hooks m={nullptr,(volatile MsTraceBranchMailbox*)branch,(volatile MsTraceLookup*)lookup,noopFlush,noopInvalidate};
 GhostTraceExportIo::Hooks e={nullptr,(volatile MsTraceExportMailbox*)box,{buffer,MS_TRACE_EXPORT_BUFFER_BYTES},noopFlush,noopInvalidate,exportPhysical};
 return GhostTraceBranchIo::configure(maps,m,BOOT_PLACEHOLDER)&&GhostTraceExportIo::configure(output,e,BOOT_PLACEHOLDER);
}
API int flatStart(unsigned sourceNonce,unsigned sourceRun,unsigned targetNonce,unsigned targetRun,unsigned destination){
 GhostTraceLogical::Plan plan={workspace.segments,32,nullptr,0,0};
 return GhostTraceFlat::begin(job,logical,plan,maps,stream,transport,output,0,1,{sourceNonce,sourceRun,1},{targetNonce,targetRun,1},0x474d534a,destination);
}
API void flatName(unsigned area,unsigned episode,unsigned parent,unsigned variant,unsigned qf){
 auto*p=job.exportName;MsTracePut(p,MS_TRACE_EXPORT_NAME_MAGIC);MsTracePut(p+4,area);MsTracePut(p+8,episode);
 MsTracePut(p+12,parent);MsTracePut(p+16,variant);MsTracePut(p+20,qf);MsTracePut(p+24,0);MsTracePut(p+28,MsTraceHash(2166136261u,p,28));
}
API unsigned flatPump(unsigned budget){return GhostTraceFlat::poll(job,budget);}
API unsigned flatGet(unsigned key){auto s=GhostTraceFlat::status(job);switch(key){case 0:return s.phase;case 1:return s.error;case 2:return s.detail;case 3:return s.bytes;case 4:return s.chunks;case 5:return s.runFlags;case 6:return s.pending;case 7:return s.published;case 8:return s.cleanupError;case 9:return job.copyAt;case 10:return job.cursor.fileOffset;case 11:return job.cursor.fileEnd;case 12:return output.operation;case 13:return output.sequence;case 14:return GhostArena::available(output.arena);case 15:return sizeof(job);case 16:return output.adler;}return 0;}
API int outputClose(){return GhostTraceExportIo::close(output);}
API unsigned outputPin(){auto*e=GhostArena::find(output.arena,output.lease,GhostArena::WORKSPACE);return e?e->pending:0;}
API void badExportAck(){auto*c=&output;auto*r=const_cast<MsTraceExportResponse*>(&c->hooks.mailbox->response);*r={MS_TRACE_EXPORT_MAGIC,MS_TRACE_EXPORT_VERSION,c->bootNonce,c->sequence,0,MS_TRACE_EXPORT_OPEN,c->bytes+c->pendingBytes+1,c->pendingAdler};}
API int flatCancel(){return GhostTraceFlat::cancel(job);}
API unsigned adlerReplace(unsigned adler,const void*a,const void*b,unsigned n){return MsTraceAdlerReplaceHeader(adler,a,b,n);}
'''
def capture(run,chunks,compress=None):
 data=bytearray(files.capture(chunks,game=GAME,compressed=compress));struct.pack_into('>II',data,16,NONCE,run);struct.pack_into('>I',data,28,CAP);struct.pack_into('>I',data,60,files.fnv(data[:60]));at=64;spans=[]
 while at<len(data)-32:
  start=at;struct.pack_into('>I',data,at,run);count,hash=struct.unpack_from('>II',data,at+8);codec=struct.unpack_from('>I',data,at+24)[0];at+=32
  if codec:
   raw=0
   while raw<count:
    n,stored=struct.unpack_from('>II',data,at);raw+=n;at+=8+(stored&0x7fffffff)
  else:at+=count
  spans.append((start,at,count,hash))
 struct.pack_into('>I',data,len(data)-28,run);struct.pack_into('>I',data,len(data)-16,CAP);return bytes(data),spans
def frame(n):return files.record(n,n,records.frame(tick=n),2)
def boundary(parent,raw):return files.record(1,1,struct.pack('>12I',1,0x23,1,NONCE,parent,1,files.fnv(raw),777,120,44,0,1),27)
def map_record(child,parent,source,span):
 start,end,count,hash=span;b=[NONCE,child,GAME,CAP,NONCE,parent,1,1,1,1,count,hash,1,end,start,count,hash,struct.unpack_from('>I',source,60)[0],0,0,0x464f524b,1,1,0]
 out=bytearray(128);struct.pack_into('>4I',out,0,0x4d534742,1,128,1);struct.pack_into('>24I',out,16,*b);struct.pack_into('>I',out,124,files.fnv(out[:124]));return bytes(out)
class FlatTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-flat-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  oldcompile=native.compile_run;oldwriter=storage.writer_source;native.compile_run=lambda command:None;storage.writer_source=lambda *args:writer_source(P)
  try:native.build_backend(d);native.build_driver(d)
  finally:native.compile_run=oldcompile;storage.writer_source=oldwriter
  p=d/'backend.c';p.write_text(p.read_text()+ARM)
  oldcompile(['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-fno-builtin','-static','-DMOONSHINE_GHOST_TRACE=1','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),str(p),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(d/'backend.dll')])
  p=d/'driver.cpp';p.write_text(p.read_text()+PPC.replace('BOOT_PLACEHOLDER',str(BOOT)+'u'))
  sources=[P/'src/ghost_trace_stream.cpp',ROOT/'src/ghost_trace_reader.cpp',ROOT/'src/ghost_arena.cpp',ROOT/'src/ghost_trace_io.cpp',ROOT/'src/ghost_trace_decode.cpp',ROOT/'src/ghost_world_witness.cpp',P/'src/ghost_trace_branch_io.cpp',P/'src/ghost_trace_logical.cpp',P/'src/ghost_trace_export_io.cpp',P/'src/ghost_trace_flat.cpp']
  oldcompile(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),'-I',str(ROOT),str(p),*map(str,sources),'-o',str(d/'driver.dll')])
  cls.arm=C.CDLL(str(d/'backend.dll'));cls.ppc=C.CDLL(str(d/'driver.dll'))
  for lib in (cls.arm,cls.ppc):cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
  for name in ('nativePointer','mailboxBytes','exportPointer'):getattr(cls.arm,name).argtypes=[C.c_uint];getattr(cls.arm,name).restype=C.c_void_p
  cls.arm.received.argtypes=[C.c_uint];cls.arm.received.restype=C.c_void_p;cls.arm.named.argtypes=[C.c_char_p,C.c_void_p,C.c_uint];cls.arm.namedBytes.argtypes=[C.c_char_p,C.POINTER(C.c_uint)];cls.arm.namedBytes.restype=C.c_void_p;cls.arm.damage.argtypes=[C.c_char_p,C.c_uint];cls.arm.rawExport.argtypes=[C.c_uint,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
  cls.ppc.setup.argtypes=[C.c_void_p]*9;cls.ppc.flatSetup.argtypes=[C.c_void_p]*4;cls.ppc.flatStart.argtypes=[C.c_uint]*5;cls.ppc.pack.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint];cls.ppc.adlerReplace.argtypes=[C.c_uint,C.c_void_p,C.c_void_p,C.c_uint];cls.ppc.adlerReplace.restype=C.c_uint
 def setUp(self):
  self.keep=[];self.arm.readReset();self.arm.nativeInit();self.arm.exportReset();self.assertTrue(self.ppc.setup(self.arm.mailboxBytes(0),self.arm.mailboxBytes(1),*(self.arm.nativePointer(i) for i in range(4)),self.arm.received(0x13408000),self.arm.nativePointer(5),self.arm.nativePointer(4)));self.assertTrue(self.ppc.flatSetup(*(self.arm.exportPointer(i) for i in range(4))))
 def tearDown(self):
  if self.ppc.flatGet(0)==0:self.ppc.outputClose()
  if not self.ppc.flatGet(6):
   self.assertEqual(self.ppc.get(9),0x10c000);self.assertEqual(self.ppc.flatGet(14),0x5000)
  self.assertEqual(self.arm.exportGuards(),1)
 def name(self,run,nonce=NONCE,suffix='msgt',public=False):return f'/Moonshine data/'+('ghosts/share/jp/p0/' if public else 'ghosts/recordings/')+f'trace_{nonce:08X}_{run:08X}.{suffix}'
 def add(self,name,data):
  owner=C.create_string_buffer(data);self.keep.append(owner);self.arm.named(name.encode(),owner,len(data));return owner
 def get(self,name):
  count=C.c_uint();p=self.arm.namedBytes(name.encode(),C.byref(count));return C.string_at(p,count.value) if p else None
 def pack(self,data):
  out=C.create_string_buffer(len(data)+len(data)//255+32);n=self.ppc.pack(data,len(data),out,len(out));self.assertGreater(n,0);return out.raw[:n]
 def tick(self,n=1):
  for _ in range(n):self.arm.readStep(1);self.ppc.flatPump(4)
 def finish(self):
  for _ in range(10000):
   if not self.ppc.flatGet(6):return
   self.tick()
  self.fail(f'export stuck {self.ppc.flatGet(0)}/{self.ppc.flatGet(1)}/{self.ppc.flatGet(2)}/{self.ppc.flatGet(12)}')
 def graph(self,compressed=True):
  prefix=frame(1)+files.record(1,1,b'a'*60000,99);root,rs=capture(1,[prefix,frame(20)],self.pack if compressed else None);tail,ts=capture(2,[boundary(1,prefix)+frame(2)],self.pack if compressed else None)
  self.add(self.name(1),root);self.add(self.name(2),tail);self.add(f'/Moonshine data/ghosts/recordings/ref_{NONCE:08X}_00000002_464F524B_00000001_00000001.msgb',map_record(2,1,root,rs[0]));return root,tail,rs,ts
 def start(self,public=0):self.assertTrue(self.ppc.flatStart(NONCE,2,OUT,RUN,public))
 def test_compressed_blocks_are_copied_exactly_and_file_is_self_contained(self):
  root,tail,rs,ts=self.graph();self.start(1);self.finish();self.assertEqual(self.ppc.flatGet(7),1)
  out=self.get(self.name(RUN,OUT,public=True));self.assertIsNotNone(out);self.assertEqual(struct.unpack_from('>I',out,36)[0]&0x23,0x23);self.assertEqual(struct.unpack_from('>I',out,40)[0],0x50525631)
  expected=bytearray();sequence=0
  for data,spans in ((root,rs[:1]),(tail,ts)):
   for start,end,*_ in spans:
    chunk=bytearray(data[start:end]);sequence+=1;struct.pack_into('>II',chunk,0,RUN,sequence);expected+=chunk
  self.assertEqual(out[64:-32],bytes(expected));self.assertEqual(struct.unpack_from('>I',out,len(out)-24)[0],2);self.assertEqual(self.arm.exportGuards(),1)
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload
  stream=io.BytesIO(out);stream.seek(64);raw=[]
  for _ in range(2):header=struct.unpack('>8I',stream.read(32));raw.append(chunk_payload(stream,header,3))
  self.assertEqual(struct.unpack_from('>H',raw[1])[0],27);self.assertEqual(self.ppc.get(9),0x10c000);self.assertEqual(self.ppc.flatGet(14),0x5000)
 def test_tagged_child_is_exported_only_after_logical_flattening(self):
  from ghost_trace_branch_admission_fixture import tag_header
  _,tail,_,_=self.graph();tagged=tag_header(tail,NONCE,1);self.add(self.name(2),tagged)
  self.start(1);self.finish();self.assertEqual(self.ppc.flatGet(7),1)
  out=self.get(self.name(RUN,OUT,public=True));self.assertIsNotNone(out)
  self.assertEqual(out[44:60],bytes(16));self.assertEqual(self.get(self.name(2)),tagged)
 def raw_export(self,operation,nonce,run,data=b'',flags=0):
  owner=C.create_string_buffer(bytes(data));self.keep.append(owner);self.arm.rawExport(operation,nonce,run,owner,len(data),flags)
 def test_portable_export_refuses_raw_branched_child_even_with_valid_local_dependencies(self):
  from ghost_trace_branch_admission_fixture import branch_graph,map_path
  for dependencies in (False,True):
   self.setUp();child,parent,edge=branch_graph(nonce=NONCE,child_run=2,parent_run=1)
   self.add(self.name(2),child)
   if dependencies:
    self.add(self.name(1),parent);self.add(map_path(NONCE,2),edge)
   self.raw_export(1,NONCE,2,flags=1);self.assertEqual(self.arm.exportPhase(),1)
   self.raw_export(2,NONCE,2,child[:64]);self.assertEqual(self.arm.exportPhase(),4)
   self.assertIsNone(self.get(self.name(2,NONCE,public=True)))
   self.assertEqual(self.get(self.name(2)),child)
   self.raw_export(4,NONCE,2);self.assertIsNone(self.get(self.name(2,NONCE,'part',public=True)))
 def test_portable_export_rejects_unknown_and_partial_parent_headers(self):
  from ghost_trace_branch_admission_fixture import capture,fnv
  ordinary=capture(OUT,RUN,frame(1),CAP,GAME)
  for offset,value in ((44,0x12345678),(48,NONCE),(52,1),(56,1)):
   self.setUp();bad=bytearray(ordinary[:64]);struct.pack_into('>I',bad,offset,value);struct.pack_into('>I',bad,60,fnv(bad[:60]))
   self.raw_export(1,OUT,RUN,flags=1);self.raw_export(2,OUT,RUN,bad)
   self.assertEqual(self.arm.exportPhase(),4);self.assertIsNone(self.get(self.name(RUN,OUT,public=True)))
   self.raw_export(4,OUT,RUN)
 def test_commit_cannot_introduce_a_dependency_into_an_ordinary_export(self):
  from ghost_trace_branch_admission_fixture import capture,tag_header
  ordinary=capture(OUT,RUN,frame(1),CAP,GAME)
  self.raw_export(1,OUT,RUN,flags=1);self.raw_export(2,OUT,RUN,ordinary[:64]);self.raw_export(2,OUT,RUN,ordinary[64:])
  self.assertEqual(self.arm.exportPhase(),1)
  dependent=tag_header(ordinary,NONCE,1)
  self.raw_export(3,OUT,RUN,dependent[:64]);self.assertEqual(self.arm.exportPhase(),4)
  self.assertIsNone(self.get(self.name(RUN,OUT,public=True)));self.raw_export(4,OUT,RUN)
 def test_named_export_uses_date_logical_level_time_and_file_checksum(self):
  self.graph();self.start(3);self.ppc.flatName(0x21,0,3,3,5200);self.finish();self.assertEqual(self.ppc.flatGet(7),1)
  # The public checksum is the finalized file checksum, not an unverified label.
  data=self.get(self.name(RUN,OUT,'part',public=True));self.assertIsNone(data)
  checksum=struct.unpack_from('=I',C.string_at(self.arm.exportPointer(2),128),92)[0]
  name=f'/Moonshine data/ghosts/share/jp/p0/2026_09_06_RH4_43376[{checksum:08X}].msgt'
  data=self.get(name);self.assertIsNotNone(data);self.assertEqual(zlib.adler32(data),checksum)
 def test_invalid_named_export_metadata_never_publishes(self):
  self.graph();self.start(3);self.ppc.flatName(0xff,0,255,0xffffffff,100);self.finish();self.assertEqual(self.ppc.flatGet(7),0)
 def test_export_summary_keeps_tas_evidence_from_the_recorded_stream(self):
  provenance=lambda f,flags:files.record(f,f,struct.pack('>II',1,flags),28)
  raw=frame(1)+provenance(1,0)+frame(2)+provenance(2,0x21)
  source,_=capture(2,[raw]);self.add(self.name(2),source)
  self.start();self.finish();self.assertEqual(self.ppc.flatGet(7),1)
  out=self.get(self.name(RUN,OUT));self.assertEqual(struct.unpack_from('>II',out,36),(0x21,0x50525631))
  self.assertEqual(out[96:-32],raw)
 def test_uncompressed_source_is_valid_version_three_export(self):
  self.graph(False);self.start();self.finish();out=self.get(self.name(RUN,OUT));self.assertEqual(struct.unpack_from('>I',out,4)[0],3);self.assertEqual(self.ppc.flatGet(7),1)
 def test_existing_destination_is_never_overwritten(self):
  self.graph();self.add(self.name(RUN,OUT),b'existing');self.start();self.finish();self.assertEqual(self.get(self.name(RUN,OUT)),b'existing');self.assertEqual(self.ppc.flatGet(7),0)
 def test_source_change_after_validation_refuses_publication(self):
  root,tail,rs,ts=self.graph();self.start()
  for _ in range(1000):
   self.tick()
   if self.ppc.flatGet(0)==10:break
  self.assertEqual(self.ppc.flatGet(0),10);self.arm.damage(self.name(1).encode(),rs[0][0]+40);self.finish();self.assertEqual(self.ppc.flatGet(7),0);self.assertIsNone(self.get(self.name(RUN,OUT)))
 def test_cancel_during_readback_does_not_publish(self):
  self.graph();self.start()
  for _ in range(2000):
   self.tick()
   if self.arm.exportPhase()==2:break
  self.assertEqual(self.arm.exportPhase(),2);self.ppc.flatCancel();self.finish();self.assertEqual(self.ppc.flatGet(7),0);self.assertIsNone(self.get(self.name(RUN,OUT)));self.assertIsNone(self.get(self.name(RUN,OUT,'part')))
 def test_readback_corruption_never_publishes(self):
  self.graph();self.start()
  for _ in range(2000):
   self.tick()
   if self.arm.exportPhase()==2:break
  self.arm.damage(self.name(RUN,OUT,'part').encode(),100);self.finish();self.assertEqual(self.ppc.flatGet(7),0);self.assertIsNone(self.get(self.name(RUN,OUT)))
 def test_export_source_pin_survives_until_cancel_ack(self):
  self.graph();self.start()
  for _ in range(1000):
   self.tick()
   if self.ppc.flatGet(0)==3:break
  pin=f'/Moonshine data/ghosts/recordings/ref_{NONCE:08X}_00000002_45585054_{RUN:08X}_{OUT:08X}.msgb'
  self.assertIsNotNone(self.get(pin));self.ppc.flatCancel();self.finish();self.assertIsNone(self.get(pin));self.assertIsNotNone(self.get(self.name(2)))
 def test_invalid_export_ack_keeps_output_lease(self):
  self.graph();self.start()
  for _ in range(1000):
   self.tick()
   if self.ppc.flatGet(12)==2:break
  sequence=self.ppc.outputPin();self.assertTrue(sequence);self.ppc.badExportAck();self.ppc.flatPump(4);self.assertEqual(self.ppc.outputPin(),sequence)
  self.finish();self.assertEqual(self.ppc.flatGet(7),1)
 def test_multi_window_raw_chunk_roundtrip(self):
  prefix=frame(1)+b''.join(files.record(1,1,bytes([i])*60000,99) for i in range(8))
  root,rs=capture(1,[prefix,frame(20)]);tail,ts=capture(2,[boundary(1,prefix)+frame(2)])
  self.add(self.name(1),root);self.add(self.name(2),tail);self.add(f'/Moonshine data/ghosts/recordings/ref_{NONCE:08X}_00000002_464F524B_00000001_00000001.msgb',map_record(2,1,root,rs[0]))
  self.start();self.finish();out=self.get(self.name(RUN,OUT));self.assertIsNotNone(out);self.assertEqual(self.ppc.flatGet(7),1);self.assertGreater(len(out),0x70000)
 def test_header_replacement_adler_matches_complete_rehash(self):
  for n in (96,1000,65536,131123):
   old=bytes((i*17)&255 for i in range(64));new=bytes((i*9+3)&255 for i in range(64));tail=bytes((i*11)&255 for i in range(n-64))
   self.assertEqual(self.ppc.adlerReplace(zlib.adler32(old+tail),old,new,n),zlib.adler32(new+tail))
if __name__=='__main__':unittest.main()
