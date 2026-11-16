"""The UI share adapter preserves the selected file and waits for final cleanup."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
from test_ghost_recording import manifest,trace
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
#include "susamune/ghost_trace_share.hxx"
#include "susamune/ghost_trace_flat.hxx"
static GhostTraceFlat::Task task;
static bool running,accepted=true,closed=true,published;
static unsigned calls,cancels,nonce,run,region,destination;
namespace GhostTrace {bool backendIdentity(unsigned&v){v=999;return true;}}
namespace GhostTraceFlat {
bool active(){return running;}Task*nativeTask(){return &task;}
bool configureNativeAndBegin(GhostTraceIo::File source,GhostTraceIo::File target,unsigned game,unsigned flags,unsigned){
 ++calls;nonce=target.nonce;run=target.run;region=target.region;destination=flags;
 if(source.nonce!=1234||source.run!=0x80000001u||game!=0x474d534au)return false;
 if(!accepted)return false;running=true;published=false;return true;
}
Phase poll(Task&,unsigned){return running?COPY_DATA:DONE;}
Status status(const Task&){return {running?COPY_DATA:DONE,0,0,96,1,0,0,running,published};}
bool close(Task&){return !running&&closed;}
bool cancel(Task&){++cancels;return false;}
}
#define API extern "C" __declspec(dllexport)
API void reset(){running=false;closed=true;published=false;GhostTraceShare::poll();accepted=true;calls=cancels=0;}
API int begin(const void*p,unsigned bytes){return GhostTraceShare::begin(p,bytes);}
API int poll(){return GhostTraceShare::poll();}API int busy(){return GhostTraceShare::busy();}
API void finish(int success,int ack){running=false;published=success;closed=ack;}
API void refuse(){accepted=false;}API void cancel(){GhostTraceShare::cancel();}
API unsigned get(unsigned id){return id==0?calls:id==1?nonce:id==2?run:id==3?region:id==4?destination:cancels;}
"""
class ShareTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='trace-share-');cls.addClassCleanup(cls.temp.cleanup);base=Path(cls.temp.name);(base/'fixture.cpp').write_text(FIXTURE,encoding='utf-8')
  cmd=['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-DMOONSHINE_GHOST_TRACE=1','-DIS_EMULATOR=0','-I',str(ROOT/'include'),str(base/'fixture.cpp'),str(ROOT/'src/ghost_trace_share.cpp'),'-o',str(base/'share.dll')]
  r=subprocess.run(cmd,capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']));assert r.returncode==0,r.stderr
  cls.lib=C.CDLL(str(base/'share.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.begin.argtypes=[C.c_void_p,C.c_uint];cls.lib.get.restype=C.c_uint
 def setUp(self):self.lib.reset();self.data=manifest(trace())
 def test_validated_selection_becomes_public_self_contained_export(self):
  self.assertTrue(self.lib.begin(self.data,256));self.assertEqual(self.lib.get(1),999);self.assertEqual(self.lib.get(2)&0xc0000000,0x40000000);self.assertEqual(self.lib.get(3),1);self.assertEqual(self.lib.get(4),3)
  self.assertFalse(self.lib.begin(self.data,256));self.assertEqual(self.lib.get(0),1);self.assertEqual(self.lib.poll(),1)
  self.lib.finish(1,1);self.assertEqual(self.lib.poll(),2);self.assertFalse(self.lib.busy());self.assertEqual(self.lib.poll(),0)
 def test_corrupt_or_truncated_descriptor_never_reaches_exporter(self):
  bad=bytearray(self.data);bad[20]^=1
  self.assertFalse(self.lib.begin(bytes(bad),256));self.assertFalse(self.lib.begin(self.data,255));self.assertEqual(self.lib.get(0),0)
 def test_publication_waits_for_cleanup_before_ui_success(self):
  self.assertTrue(self.lib.begin(self.data,256));self.lib.finish(1,0);self.assertEqual(self.lib.poll(),1);self.assertTrue(self.lib.busy())
  self.lib.finish(1,1);self.assertEqual(self.lib.poll(),2)
 def test_cancel_and_failure_wait_for_backend_receipts(self):
  self.assertTrue(self.lib.begin(self.data,256));self.lib.cancel();self.assertEqual(self.lib.get(5),1);self.assertTrue(self.lib.busy())
  self.lib.finish(0,1);self.assertEqual(self.lib.poll(),3);self.assertFalse(self.lib.busy())
 def test_refused_backend_does_not_keep_ui_busy(self):
  self.lib.refuse();self.assertFalse(self.lib.begin(self.data,256));self.assertFalse(self.lib.busy())
if __name__=='__main__':unittest.main()
