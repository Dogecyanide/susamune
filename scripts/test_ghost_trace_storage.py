"""Exercise the actual SD trace writer with bounded buffers and failing FatFS calls."""
import ctypes as C
from pathlib import Path
import re, subprocess, tempfile, unittest, struct, importlib.util, os
ROOT=Path(__file__).resolve().parents[1]
ADAPTER=r'''
#include "susamune/ghost_trace.h"
#include "susamune/loading_trace.h"
#include "susamune/ghost_trace_compression.h"
#include "susamune/ghost_trace_stream_storage.h"
#include "susamune/ghost_trace_prepare.h"
#include "susamune/ghost_trace_checkpoint.h"
#include "susamune/ghost_state_reference.h"
#ifndef TRACE_READER_INTEGRATION
static void GhostTraceReadStorageInit(unsigned nonce){(void)nonce;}
static unsigned readerActive;
static int GhostTraceReadStoragePending(void){return 0;}
static int GhostTraceReadStorageActive(void){return readerActive;}
static int GhostTraceReadStorageOwns(unsigned nonce,unsigned run){(void)nonce;(void)run;return readerActive!=0;}
static int GhostTraceReadStorageService(int writer){(void)writer;return 0;}
#endif
typedef int FRESULT;
static struct MsTraceMailbox traceMailbox;
static struct MsTracePrepareMailbox prepareMailbox;
static struct MsTraceFenceInfo traceFence;
static struct MsTraceBranchMailbox branchMailbox;
static struct MoonshineGhostMemoryProof testProof;
static unsigned char traceBuffers[2][MS_TRACE_BUFFER_BYTES+64];
static unsigned char traceWork[MS_TRACE_PACK_WORK_BYTES+64] __attribute__((aligned(32)));
#undef MS_TRACE_PACK_WORK_PHYS
#define MS_TRACE_PACK_WORK_PHYS ((__UINTPTR_TYPE__)(traceWork+32))
static int f_truncate(FIL*f){struct TestFile*v=&testFiles[f->index];if(!v->writable||f->position>v->size)return FR_DENIED;v->size=f->position;return FR_OK;}
static unsigned testAdmit=1,clockTick,closeFailure,renameFailure,testStatePending,testClusterBytes=32768;
static int f_close(FIL *f){return closeFailure?FR_DISK_ERR:fixture_close(f);}
static int f_rename_char(const char*a,const char*b){return renameFailure?FR_DISK_ERR:fixture_rename(a,b);}
#define HW_TIMER 0
static u32 read32(u32 address){(void)address;return ++clockTick;}
static u32 DILastReadTick=0xff000000u;static int DI_IRQ,pendingDisc;
static unsigned TimerDiffTicks(unsigned since){return clockTick-since;}
static void _ahbMemFlush(unsigned mode){(void)mode;}
static int DiscCheckAsync(void){return !DI_IRQ;}
static void DIUpdateRegisters(void){if(pendingDisc){pendingDisc=0;DI_IRQ=1;DILastReadTick=clockTick;}}

'''
EXPORTS=r'''
__declspec(dllexport) void reset(void){
 testCount=writeCount=writeBytes=clockTick=closeFailure=renameFailure=0;
 failWriteAfter=0xffffffffu;testAdmit=1;directoryResult=0;testStatePending=0;testClusterBytes=32768;
 memset(testFiles,0,sizeof(testFiles));memset(traceBuffers,0xa5,sizeof(traceBuffers));memset(traceWork,0xa5,sizeof(traceWork));
 testProof.word[MGM_NONCE]=0x12345678u;GhostTraceStorageInit();
}
__declspec(dllexport) void submit(unsigned op,unsigned run,unsigned boundary,unsigned nonce){
 if(op==1)memset(traceMailbox.chunks,0,sizeof(traceMailbox.chunks));
 struct MsTraceRequest *r=&traceMailbox.request;r->magic=MS_TRACE_MAGIC;r->version=MS_TRACE_VERSION;
 r->nonce=nonce;r->sequence++;r->operation=op;r->run=run;r->scene=boundary;r->capabilities=0x4ff;
}
__declspec(dllexport) void chunk(unsigned index,unsigned run,unsigned seq,const void *p,unsigned n,unsigned bad){
 struct MsTraceChunk *c=&traceMailbox.chunks[index];memset(c,0,sizeof(*c));
 c->run=run;c->sequence=seq;c->bytes=n;c->firstFrame=1;c->lastFrame=8;
 if(n<=MS_TRACE_BUFFER_BYTES)memcpy(traceBuffers[index]+32,p,n);
 c->checksum=MsTraceHash(2166136261u,traceBuffers[index]+32,n<=MS_TRACE_BUFFER_BYTES?n:0)^bad;
}
__declspec(dllexport) unsigned run(unsigned max){
 for(unsigned i=0;i<max;++i){if(!GhostTraceStoragePending())return i;
 unsigned before=writeBytes;GhostTraceStorageService();if(writeBytes-before>0x4028)return 0xfffffffeu;}
 return GhostTraceStoragePending()?0xffffffffu:max;
}
__declspec(dllexport) const void *response(void){return &traceMailbox.response;}
__declspec(dllexport) const void *file(unsigned complete,unsigned *n){
 char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.%s",traceMailbox.response.nonce,traceMailbox.request.run,complete?"msgt":"part");
 int i=lookup(p);if(i<0){*n=0;return NULL;}*n=testFiles[i].size;return testFiles[i].bytes;
}
__declspec(dllexport) void failures(unsigned after,unsigned close,unsigned rename){failWriteAfter=after;closeFailure=close;renameFailure=rename;}
__declspec(dllexport) void identity(unsigned game,unsigned nonce){GAME_ID=game;testProof.word[MGM_NONCE]=nonce;GhostTraceStorageInit();}
__declspec(dllexport) void capabilities(unsigned flags){traceMailbox.request.capabilities=flags;}
__declspec(dllexport) void admit(unsigned v){testAdmit=v;}
__declspec(dllexport) unsigned guards(void){for(unsigned b=0;b<2;++b)for(unsigned n=0;n<32;++n)if(traceBuffers[b][n]!=0xa5||traceBuffers[b][MS_TRACE_BUFFER_BYTES+32+n]!=0xa5)return 0;for(unsigned n=0;n<32;++n)if(traceWork[n]!=0xa5||traceWork[MS_TRACE_PACK_WORK_BYTES+32+n]!=0xa5)return 0;return 1;}
'''

def writer_source(root=ROOT):
 source=(root/'launcher/kernel/GhostTraceStorage.c').read_text(encoding='utf-8')
 source=source.replace('#include "GhostTraceAsyncStorage.inc"',(root/'launcher/kernel/GhostTraceAsyncStorage.inc').read_text(encoding='utf-8-sig'))
 source=source.replace('#include "GhostTraceRetireStorage.inc"',(root/'launcher/kernel/GhostTraceRetireStorage.inc').read_text(encoding='utf-8-sig'))
 source=source.replace('#include "GhostTracePrepareStorage.inc"',(root/'launcher/kernel/GhostTracePrepareStorage.inc').read_text(encoding='utf-8-sig'))
 source=source.replace('#include "GhostTraceBranchStorage.inc"',(root/'launcher/kernel/GhostTraceBranchStorage.inc').read_text(encoding='utf-8'))
 if (root/'launcher/kernel/GhostTraceExportStorage.inc').exists():source=source.replace('#include "GhostTraceExportStorage.inc"',(root/'launcher/kernel/GhostTraceExportStorage.inc').read_text())
 if (root/'launcher/kernel/GhostTraceRecoveryStorage.inc').exists():source=source.replace('#include "GhostTraceRecoveryStorage.inc"',(root/'launcher/kernel/GhostTraceRecoveryStorage.inc').read_text())
 source=re.sub(r'^#include .*$', '',source,flags=re.M).replace('writeBytes(', 'traceWriteBytes(')
 source=source.replace('#define WRITER ((struct TraceWriter*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_ARM_OFFSET))','static struct TraceWriter testWriter;\n#define WRITER (&testWriter)')
 source=source.replace('#define MAILBOX ((volatile struct MsTraceMailbox*)MS_TRACE_CONTROL_PHYS)','#define MAILBOX (&traceMailbox)')
 source=source.replace('#define PREPBOX ((volatile struct MsTracePrepareMailbox*)MS_TRACE_PREPARE_PHYS)','#define PREPBOX (&prepareMailbox)')
 source=source.replace('#define FENCE_MAILBOX ((volatile struct MsTraceFenceInfo*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_FENCE_INFO_OFFSET))','#define FENCE_MAILBOX (&traceFence)')
 source=source.replace('#define BRANCHBOX ((volatile struct MsTraceBranchMailbox*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_BRANCH_MAILBOX_OFFSET))','#define BRANCHBOX (&branchMailbox)')
 source=source.replace('#define LOOKUP_RESULT ((struct MsTraceLookup*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_BRANCH_LOOKUP_OFFSET))','static struct MsTraceLookup lookupResult;\n#define LOOKUP_RESULT (&lookupResult)')
 source=re.sub(r'static int admitted\(void\) \{.*?\n\}', 'static int admitted(void){return testAdmit;}',source,flags=re.S)
 source=re.sub(r'static unsigned retireClusterBytes\(const FIL\*f\) \{.*?\n\}', 'static unsigned retireClusterBytes(const FIL*f){(void)f;return testClusterBytes;}',source,flags=re.S)
 source=source.replace('SusamuneStateStoragePending()', 'testStatePending')
 source=source.replace('(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE','&testProof')
 source=source.replace('(const unsigned char*)((index?MS_TRACE_BUFFER1_PPC:MS_TRACE_BUFFER0_PPC)&0x7fffffffu)','traceBuffers[index]+32')
 if (root/'launcher/kernel/GhostTraceExportStorage.inc').exists():
  source=source.replace('#define EXPORT_WRITER ((struct TraceExportWriter*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_ARM_OFFSET))','static struct TraceExportWriter testExportWriter;\n#define EXPORT_WRITER (&testExportWriter)')
  source=source.replace('#define EXPORT_BOX ((volatile struct MsTraceExportMailbox*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_MAILBOX_OFFSET))','static struct MsTraceExportMailbox testExportBox;\n#define EXPORT_BOX (&testExportBox)')
  source=source.replace('#define EXPORT_DATA ((unsigned char*)MS_TRACE_EXPORT_BUFFER_PHYS)','static unsigned char exportMemory[MS_TRACE_EXPORT_BUFFER_BYTES+64] __attribute__((aligned(32)));\n#define EXPORT_DATA (exportMemory+32)')
  source='#include "susamune/ghost_trace_export.h"\nvoid*memmove(void*,const void*,__SIZE_TYPE__);\n'+source
 return source

class TraceWriterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='trace-writer-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text(encoding='utf-8')
  fixture=fixture.replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 20').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 4').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 32000000')
  fixture=fixture.replace('f_close(','fixture_close(').replace('f_rename_char(','fixture_rename(')
  source=writer_source(ROOT)
  (d/'test.c').write_text('#define MOONSHINE_GHOST_TRACE 1\n'+fixture+ADAPTER+source+EXPORTS,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  p=subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-fno-builtin','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-static','-I',str(ROOT/'include'),'-DMOONSHINE_GHOST_TRACE=1',str(d/'test.c'),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=env)
  if p.returncode:raise RuntimeError(p.stdout+p.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.submit.argtypes=[C.c_uint]*4;cls.lib.chunk.argtypes=[C.c_uint]*3+[C.c_void_p,C.c_uint,C.c_uint]
  cls.lib.response.restype=C.POINTER(C.c_uint);cls.lib.run.argtypes=[C.c_uint];cls.lib.run.restype=C.c_uint
  cls.lib.file.argtypes=[C.c_uint,C.POINTER(C.c_uint)];cls.lib.file.restype=C.c_void_p
 @property
 def r(self):return list(self.lib.response()[:8])
 def setUp(self):self.lib.reset()
 def submit(self,op,run=1,boundary=0,nonce=0x12345678):self.lib.submit(op,run,boundary,nonce)
 def execute(self,n=200):return self.lib.run(n)
 def data(self,complete=0):
  n=C.c_uint();p=self.lib.file(complete,C.byref(n));return C.string_at(p,n.value) if p else None
 def chunk(self,index,seq,data,run=1,bad=0):self.lib.chunk(index,run,seq,data,len(data),bad)
 def start(self):self.submit(1);self.execute();self.assertEqual(self.r[4],2)
 def test_two_buffers_ack_order_and_exact_file(self):
  self.start();a=bytes(range(256))*2048;b=b'last payload'*3
  self.chunk(0,1,a);self.chunk(1,2,b);self.submit(2,boundary=2)
  self.execute(1);self.assertEqual(self.r[6],0)
  self.execute();self.assertEqual((self.r[4],self.r[6]),(4,2));self.assertIsNone(self.data())
  raw=self.data(1);import io,sys;sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload
  stream=io.BytesIO(raw);stream.seek(64);h=struct.unpack('>8I',stream.read(32));self.assertEqual(chunk_payload(stream,h,3),a);h=struct.unpack('>8I',stream.read(32));self.assertEqual(chunk_payload(stream,h,3),b);self.assertEqual(len(raw),stream.tell()+32)
  self.assertEqual(raw[-32:-28],b'DONE');self.assertEqual(self.lib.guards(),1)
 def test_keep_waits_for_promised_final_chunk(self):
  self.start();self.submit(2,boundary=1);self.execute(3);self.assertNotEqual(self.r[4],4)
  self.chunk(0,1,b'late');self.execute();self.assertEqual(self.r[4],4)
 def test_discard_during_partial_write_removes_only_attempt(self):
  self.start();self.chunk(0,1,b'x'*100000);self.execute(1);self.submit(3);self.execute()
  self.assertEqual(self.r[4],5);self.assertIsNone(self.data());self.assertIsNone(self.data(1))
 def test_duplicate_start_cannot_delete_existing_file(self):
  self.start();self.chunk(0,1,b'data');self.execute();original=self.data()
  self.submit(1);self.execute();self.assertEqual(self.r[4],6)
  self.submit(1);self.execute();self.assertEqual(self.r[4],6)
  self.submit(3);self.execute();self.assertEqual(self.data(),original)
 def test_short_write_and_discard_recovery(self):
  self.start();self.lib.failures(80,0,0);self.chunk(0,1,b'x'*80);self.execute();self.assertEqual(self.r[4],6)
  self.submit(2,boundary=1);self.execute();self.assertEqual(self.r[4],6)
  self.lib.failures(0xffffffff,0,0);self.submit(3);self.execute();self.assertEqual(self.r[4],5)
  self.submit(1,run=2);self.execute();self.assertEqual(self.r[4],2)
 def test_corrupt_or_wrong_epoch_chunk_never_publishes(self):
  for run,bad in ((9,0),(1,1)):
   self.lib.reset();self.start();self.chunk(0,1,b'payload',run=run,bad=bad);self.submit(2,boundary=1);self.execute()
   self.assertEqual(self.r[4],6);self.assertIsNone(self.data(1));self.assertEqual(self.lib.guards(),1)
 def test_close_and_rename_failures_keep_partial_only(self):
  for close,rename in ((1,0),(0,1)):
   self.lib.reset();self.start();self.lib.failures(0xffffffff,close,rename);self.submit(2);self.execute()
   self.assertEqual(self.r[4],6);self.assertIsNone(self.data(1));self.assertIsNotNone(self.data())
 def test_nonce_and_memory_admission(self):
  self.submit(1,nonce=9);self.execute();self.assertEqual(self.r[4],6);self.assertIsNone(self.data())
  self.lib.reset();self.lib.admit(0);self.submit(1);self.execute();self.assertEqual(self.r[4],0)
 def test_generated_file_passes_independent_stream_reader(self):
  spec=importlib.util.spec_from_file_location('trace_reader',ROOT/'tools/ghost_trace/inspect_trace.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
  self.start();record=struct.pack('>HHII',2,32,1,0)+bytes(32)+struct.pack('>HHII',14,300,8,4)+struct.pack('>I',1)+bytes(296)
  self.chunk(0,1,record);self.submit(2,boundary=1);self.execute()
  capture=Path(self.temp.name)/'actual.msgt';capture.write_bytes(self.data(1));result=reader.inspect(capture)
  self.assertTrue(result['complete']);self.assertEqual(result['movement_updates'],4);self.assertEqual(result['records'],{'frame':1,'controller':1})
  altered=bytearray(capture.read_bytes());altered[100]^=1;capture.write_bytes(altered)
  with self.assertRaises(ValueError):reader.inspect(capture)
  capture.write_bytes(self.data(1)[:-1])
  with self.assertRaisesRegex(ValueError,'Truncated|Invalid completion footer'):reader.inspect(capture)
 def test_compressed_and_raw_blocks_with_independent_decoder(self):
  import io,random,sys,lz4.block
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import chunk_payload
  self.start();data=bytes(16384)+random.Random(83).randbytes(16384)+b'abcde'*3000
  self.chunk(0,1,data);self.submit(2,boundary=1);self.execute();raw=self.data(1)
  stream=io.BytesIO(raw);stream.seek(64);header=struct.unpack('>8I',stream.read(32));self.assertEqual(chunk_payload(stream,header,3),data)
  stream.seek(96);decoded=bytearray();compressed=plain=0
  while len(decoded)<len(data):
   count,stored=struct.unpack('>2I',stream.read(8));payload=stream.read(stored&0x7fffffff)
   if stored&0x80000000:decoded.extend(lz4.block.decompress(payload,uncompressed_size=count));compressed+=1
   else:decoded.extend(payload);plain+=1
  self.assertEqual(bytes(decoded),data);self.assertGreater(compressed,0);self.assertGreater(plain,0);self.assertEqual(self.lib.guards(),1)
 def test_decoder_rejects_malformed_lz4(self):
  import sys
  sys.path.insert(0,str(ROOT/'tools/ghost_trace'));from inspect_trace import decode_lz4
  for data,count in ((b'',10),(b'\x00\x00\x00',10),(b'\xf0',10),(b'\x10a\x02\x00',5),(b'\x10a',0x4001)):
   with self.subTest(data=data,count=count),self.assertRaises(ValueError):decode_lz4(data,count)
 def test_sd_work_is_inside_existing_disc_idle_guard(self):
  source=(ROOT/'launcher/kernel/main.c').read_text(encoding='utf-8')
  start=source.index('if(StorageReadPending())',source.index('while('))
  end=source.index('else if(SusamuneGhostPending())',start)
  self.assertIn('else if(GhostTraceStoragePending())',source[start:end])
if __name__=='__main__':unittest.main()
