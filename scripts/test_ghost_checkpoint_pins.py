"""Execute pending RAM snapshot/fork ownership with stale and late receipts."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1];ROOT=P
while not (ROOT/"scripts/ghost_kernel_fixture.h").exists():ROOT=ROOT.parent
FIXTURE=r"""
#include "susamune/ghost_checkpoint_lifecycle.hxx"
using namespace GhostCheckpoints;
State state;Load load;
#define API extern "C" __declspec(dllexport)
API void init(){GhostCheckpoints::init(state);load={};}
API int capture(unsigned generation,unsigned request){MsTracePrefix p={1,2,generation,10,40,1,100,55};return GhostCheckpoints::capture(state,p,request);}
API int commit(unsigned slot,unsigned gen){return GhostCheckpoints::commit(state,slot,gen);}
API int ack(unsigned request,unsigned bytes,unsigned error){MsTraceFenceInfo f={request,1000,64,bytes,55,123,0,0};return acknowledge(state,1,2,request,f,error);}
API void abandon(){GhostCheckpoints::abandon(state);}
API int clear(unsigned slot,unsigned gen){return GhostCheckpoints::clear(state,slot,gen);}
API int adopt(unsigned generation,unsigned request,unsigned hash){MsTracePrefix p={1,2,generation,10,40,1,100,55};MsTraceFenceInfo f={request,1000,64,100,55,hash,0,0};return adoptDurable(state,p,f);}
API int retainPrefix(unsigned generation){MsTracePrefix p={1,2,generation,10,40,1,100,55};return retainPrefixLoad(state,p,load)!=0;}
API unsigned references(){unsigned n=0;for(unsigned i=0;i<kPins;++i)n+=state.pins[i].references;return n;}
API unsigned owned(){return sourceOwned(state,1,2);}
API unsigned pins(){unsigned n=0;for(unsigned i=0;i<kPins;++i)n+=state.pins[i].phase!=EMPTY;return n;}
API int retain(unsigned slot,unsigned gen){return retainLoad(state,slot,gen,load)!=0;}
API int release(){return releaseLoad(state,load);}
API int issue(unsigned request){return forkIssued(state,load,request);}
API int forkack(unsigned request){return forkAcknowledged(state,load,request);}
API unsigned token(){return load.token;}
API int release_old(unsigned token){Load stale=load;stale.token=token;return releaseLoad(state,stale);}
"""
class CheckpointPinTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-pins-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name);(d/'test.cpp').write_text(FIXTURE)
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++11','-O2','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),str(d/'test.cpp'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.init()
 def test_ram_commit_does_not_require_sync_ack(self):
  self.assertEqual(self.lib.capture(11,1),1);self.assertEqual(self.lib.commit(0,12),1);self.assertEqual(self.lib.retain(0,12),1)
  self.assertEqual(self.lib.issue(100),0);self.assertEqual(self.lib.ack(1,100,0),1);self.assertEqual(self.lib.issue(100),1)
 def test_abandoned_pending_capture_waits_for_exact_receipt(self):
  self.lib.capture(11,1);self.lib.abandon();self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.ack(2,100,0),0)
  self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.ack(1,100,0),1);self.assertEqual(self.lib.owned(),0)
 def test_replacing_slot_does_not_reclaim_pending_source(self):
  self.lib.capture(11,1);self.lib.commit(0,12);self.lib.capture(13,2);self.lib.commit(0,14)
  self.assertEqual(self.lib.pins(),2);self.assertEqual(self.lib.clear(0,12),0);self.lib.ack(1,100,0);self.assertEqual(self.lib.pins(),1)
  self.lib.clear(0,14);self.assertEqual(self.lib.pins(),1);self.lib.ack(2,100,0);self.assertEqual(self.lib.pins(),0)
 def test_canceled_fork_holds_load_pin_until_ack(self):
  self.lib.capture(11,1);self.lib.commit(0,12);self.lib.ack(1,100,0);self.assertEqual(self.lib.retain(0,12),1);self.assertEqual(self.lib.issue(101),1)
  self.lib.clear(0,12);self.assertEqual(self.lib.release(),0);self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.forkack(102),0)
  self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.forkack(101),1);self.assertEqual(self.lib.owned(),0);self.assertEqual(self.lib.release(),0)
 def test_bad_receipt_and_failed_sync_do_not_free_slot(self):
  self.lib.capture(11,1);self.lib.commit(0,12);self.assertEqual(self.lib.ack(1,99,0),0);self.assertEqual(self.lib.owned(),1)
  self.assertEqual(self.lib.ack(1,100,2),1);self.assertEqual(self.lib.retain(0,12),0);self.assertEqual(self.lib.owned(),1);self.lib.clear(0,12);self.assertEqual(self.lib.owned(),0)
 def test_old_load_token_cannot_release_new_load(self):
  self.lib.capture(11,1);self.lib.commit(0,12);self.lib.ack(1,100,0);self.lib.retain(0,12);old=self.lib.token();self.assertEqual(self.lib.release(),1)
  self.lib.retain(0,12);self.assertEqual(self.lib.release_old(old),0);self.lib.clear(0,12);self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.release(),1);self.assertEqual(self.lib.owned(),0)
 def test_durable_archive_import_can_replace_a_slot_without_sync(self):
  self.assertEqual(self.lib.adopt(11,1,123),1);self.assertEqual(self.lib.commit(0,12),1)
  self.assertEqual(self.lib.retain(0,12),1);self.assertEqual(self.lib.issue(100),1)
  self.assertEqual(self.lib.forkack(100),1);self.assertEqual(self.lib.release(),1)
  self.assertEqual(self.lib.adopt(13,2,124),1);self.assertEqual(self.lib.commit(0,14),1)
  self.assertEqual(self.lib.pins(),1);self.assertEqual(self.lib.clear(0,14),1);self.assertEqual(self.lib.pins(),0)
 def test_import_does_not_promote_a_pending_live_fence(self):
  self.lib.capture(11,1);self.lib.commit(0,12)
  self.assertEqual(self.lib.adopt(11,1,123),0);self.assertEqual(self.lib.references(),1)
  self.assertEqual(self.lib.ack(1,100,0),1);self.assertEqual(self.lib.adopt(11,1,123),1)
  self.assertEqual(self.lib.references(),2);self.lib.abandon();self.assertEqual(self.lib.references(),1)
 def test_direct_archive_load_keeps_pin_after_candidate_release(self):
  self.assertEqual(self.lib.adopt(11,1,123),1);self.assertEqual(self.lib.adopt(11,1,123),1)
  self.assertEqual(self.lib.references(),1);self.assertEqual(self.lib.retainPrefix(11),1)
  self.lib.abandon();self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.references(),1)
  self.assertEqual(self.lib.issue(77),1);self.assertEqual(self.lib.release(),0)
  self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.forkack(77),1);self.assertEqual(self.lib.owned(),0)
 def test_import_fence_identity_must_match_existing_pin(self):
  self.assertEqual(self.lib.adopt(11,1,123),1);self.lib.commit(0,12)
  self.assertEqual(self.lib.adopt(11,1,124),0);self.assertEqual(self.lib.references(),1)
  self.assertEqual(self.lib.adopt(13,0,123),0);self.assertEqual(self.lib.references(),1)
if __name__=='__main__':unittest.main()
