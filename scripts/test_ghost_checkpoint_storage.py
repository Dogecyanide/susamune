"""Actual staged ARM fence/branch I/O and exact checkpoint pin ownership."""
import ctypes as C,os,re,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from test_ghost_trace_storage import ADAPTER,EXPORTS,TraceWriterTests,writer_source
EXTRA=r"""
__declspec(dllexport) const void*fence(void){return &traceFence;}
__declspec(dllexport) void syncFailure(unsigned fail){failSync=fail;}
__declspec(dllexport) unsigned ioBytes(void){return writeBytes;}
__declspec(dllexport) unsigned reads(void){return readBytes;}
__declspec(dllexport) int branch(const void*p,unsigned kind){return GhostTraceBranchStore(p,kind);}
__declspec(dllexport) int unpin(const void*p){return GhostTraceBranchRelease(p,2);}
__declspec(dllexport) int discardSource(unsigned nonce,unsigned run,unsigned hash,unsigned begin){return GhostTraceRetainedDiscard(nonce,run,hash,begin);}
__declspec(dllexport) unsigned exists(unsigned run){char p[128];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.msgt",0x12345678,run);return lookup(p)>=0;}
__declspec(dllexport) void branchRequest(unsigned seq,unsigned operation,unsigned nonce,unsigned run,unsigned kind,const void*p){
 if(p)memcpy(&branchMailbox.payload,p,96);
 branchMailbox.request=(struct MsTraceBranchRequest){MS_TRACE_BRANCH_MAGIC,1,0x12345678,seq,operation,kind,nonce,run};
}
__declspec(dllexport) const void*branchResponse(void){return &branchMailbox.response;}
"""
class CheckpointStorageTests(TraceWriterTests):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-checkpoint-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text().replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 50').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 20').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 2000000')
  fixture=fixture.replace('f_close(','fixture_close(').replace('f_rename_char(','fixture_rename(')
  source=writer_source(P)
  code='#define MOONSHINE_GHOST_TRACE 1\n'+fixture+ADAPTER+'\n#include "susamune/ghost_trace_checkpoint.h"\n'+source+EXPORTS.replace('failWriteAfter=0xffffffffu;','failSync=0;readBytes=0;failWriteAfter=0xffffffffu;')+EXTRA
  (d/'test.c').write_text(code);env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-fno-builtin','-static','-DMOONSHINE_GHOST_TRACE=1','-DMS_TRACE_BRANCH_RETENTION_READY=1','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),str(d/'test.c'),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=env)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.submit.argtypes=[C.c_uint]*4;cls.lib.chunk.argtypes=[C.c_uint]*3+[C.c_void_p,C.c_uint,C.c_uint]
  cls.lib.response.restype=C.POINTER(C.c_uint);cls.lib.run.argtypes=[C.c_uint];cls.lib.run.restype=C.c_uint
  cls.lib.file.argtypes=[C.c_uint,C.POINTER(C.c_uint)];cls.lib.file.restype=C.c_void_p
  cls.lib.fence.restype=C.POINTER(C.c_uint);cls.lib.branch.argtypes=[C.c_void_p,C.c_uint];cls.lib.unpin.argtypes=[C.c_void_p]
  cls.lib.branchRequest.argtypes=[C.c_uint]*5+[C.c_void_p];cls.lib.branchResponse.restype=C.POINTER(C.c_uint)
 def setUp(self):self.lib.identity(0x474d534a,0x12345678);self.lib.reset()
 def cursor(self):return list(self.lib.fence()[:8])
 def complete(self,data=b'a'*1000):
  self.start();self.chunk(0,1,data);self.submit(4,boundary=1);self.execute();f=self.cursor();self.submit(2,boundary=1);self.execute();self.assertEqual(self.r[4],4);return f
 def branch_data(self,f,kind=1,tail=2):
  # Own identity, source cursor, exact physical fence receipt, stable owner.
  cursor=[0x12345678,1,0x40000001,8,4,1,f[3] if kind==1 else 0,f[4] if kind==1 else 0]
  fence=f if kind==1 else [0,f[1],0,0,0,f[5],0,0]
  return struct.pack('<24I',0x12345678,tail,0x474d534a,0x4ff,*cursor,*fence,1,1,1,0)
 def delete(self,f):
  result=self.lib.discardSource(0x12345678,1,f[5],1)
  for _ in range(100):
   if result:return result
   result=self.lib.discardSource(0x12345678,1,f[5],0)
  self.fail('discard did not settle')
 def test_fence_ack_precedes_post_boundary_chunk(self):
  self.start();self.chunk(0,1,b'first'*100);self.chunk(1,2,b'future'*100);self.submit(4,boundary=1)
  for _ in range(100):
   self.lib.run(1)
   if self.r[3]==2:break
  self.assertEqual(self.r[3],2);self.assertEqual(self.r[6],1)
  f=self.cursor();self.assertEqual(f[0],2);self.assertEqual(f[3],500);self.assertEqual(f[1],self.r[7]);self.assertEqual(f[2],64)
  self.execute();self.assertEqual(self.r[6],2);self.assertEqual(self.cursor(),f)
 def test_failed_sync_never_announces_checkpoint(self):
  self.start();self.chunk(0,1,b'checkpoint');self.lib.syncFailure(1);self.submit(4,boundary=1);self.execute()
  self.assertEqual(self.r[4],6);self.assertEqual(self.cursor(),[0]*8)
 def test_branch_is_fixed_metadata_and_pins_its_source(self):
  f=self.complete();self.submit(1,run=2);self.execute();before=self.lib.ioBytes();reads=self.lib.reads()
  self.assertEqual(self.lib.branch(self.branch_data(f),1),1);self.assertEqual(self.lib.ioBytes()-before,128)
  self.assertLessEqual(self.lib.reads()-reads,256);self.assertEqual(self.delete(f),-1);self.assertEqual(self.lib.exists(1),1)
 def test_pin_release_requires_exact_generation(self):
  f=self.complete();pin=self.branch_data(f,2,1);self.assertEqual(self.lib.branch(pin,2),1);self.assertEqual(self.delete(f),-1)
  stale=bytearray(pin);struct.pack_into('<I',stale,88,2);self.assertEqual(self.lib.unpin(bytes(stale)),0);self.assertEqual(self.delete(f),-1)
  self.assertEqual(self.lib.unpin(pin),1);self.assertEqual(self.delete(f),1);self.assertEqual(self.lib.exists(1),0)
 def test_failed_publication_leaves_conservative_pin(self):
  f=self.complete();self.lib.failures(0xffffffff,0,1)
  self.assertEqual(self.lib.branch(self.branch_data(f,2,1),2),0);self.lib.failures(0xffffffff,0,0)
  self.assertEqual(self.delete(f),-1);self.assertEqual(self.lib.exists(1),1)
 def test_bad_source_cut_cannot_publish_map(self):
  f=self.complete();self.submit(1,run=2);self.execute();bad=bytearray(self.branch_data(f));struct.pack_into('<I',bad,16+7*4,999)
  before=self.lib.ioBytes();self.assertEqual(self.lib.branch(bytes(bad),1),0);self.assertEqual(self.lib.ioBytes(),before)
 def test_source_and_tail_must_match_running_region(self):
  f=self.complete();self.lib.identity(0x474d5345,0x12345678);self.submit(1,run=2);self.execute()
  self.assertEqual(self.lib.branch(self.branch_data(f),1),0);self.assertEqual(self.lib.exists(1),1)
 def test_branch_service_acks_exact_request(self):
  f=self.complete();pin=self.branch_data(f,2,1);self.lib.branchRequest(91,1,0x12345678,1,2,pin);self.execute()
  self.assertEqual(list(self.lib.branchResponse()[:5])[3:],[91,0]);self.assertEqual(self.delete(f),-1)
  self.lib.branchRequest(92,2,0x12345678,1,2,pin);self.execute();self.assertEqual(list(self.lib.branchResponse()[:5])[3:],[92,0]);self.assertEqual(self.delete(f),1)
del TraceWriterTests
if __name__=='__main__':unittest.main()
