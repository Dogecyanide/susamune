"""Deferred ordinary retirement keeps one exact old FIL outside the live writer."""
import ctypes as C
from pathlib import Path
import struct
import random
import unittest
from unittest.mock import patch
import test_ghost_trace_storage as writer
import test_ghost_trace_prepare as warm

NONCE=warm.NONCE
A=warm.RUN
B=A+1
EXTRA=r'''
__declspec(dllexport) unsigned completedSource(unsigned run){char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.msgt",WRITER->response.nonce,run);return lookup(p)>=0;}
__declspec(dllexport) unsigned retired(unsigned field){struct TraceRetire*r=&WRITER->retiring;switch(field){case 0:return r->phase;case 1:return r->preserve;case 2:return r->run;case 3:return r->file.index;case 4:return r->bytes;case 5:return r->generation;case 6:return retirementUnlinks;default:return WRITER->retained;}}
__declspec(dllexport) void retiredMutate(unsigned offset,unsigned value){struct TestFile*f=&testFiles[WRITER->retiring.file.index];((u8*)f->bytes)[offset]=(u8)value;}
__declspec(dllexport) void retiredSize(unsigned bytes){testFiles[WRITER->retiring.file.index].size=bytes;}
__declspec(dllexport) void preserveRetired(){retirePreserve(WRITER->retiring.nonce,WRITER->retiring.run);}
__declspec(dllexport) void statePending(unsigned value){testStatePending=value;}
__declspec(dllexport) void clusterBytes(unsigned value){testClusterBytes=value;}
__declspec(dllexport) void unknownReferences(void){WRITER->references.valid=0;}
__declspec(dllexport) void newReferenceGeneration(void){++WRITER->referenceGeneration;}
__declspec(dllexport) int lateReference(const void*p){return GhostTraceBranchStore((const struct MsTraceBranch*)p,MS_TRACE_BRANCH_CHECKPOINT);}
__declspec(dllexport) void queueReference(const void*p){memcpy(&branchMailbox.payload,p,96);branchMailbox.request=(struct MsTraceBranchRequest){MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,WRITER->response.nonce,99,MS_TRACE_BRANCH_STORE,MS_TRACE_BRANCH_CHECKPOINT,((const struct MsTraceBranch*)p)->nonce,((const struct MsTraceBranch*)p)->run};}
__declspec(dllexport) int statePrepare(const void*p,unsigned generation){return GhostTraceStateReferencePrepare((const struct MsTraceStateReference*)p,GAME_ID,7,8,generation);}
__declspec(dllexport) int stateStore(void){return GhostTraceStateReferenceStore();}
__declspec(dllexport) void stateReset(void){GhostTraceStateReferenceReset();}
__declspec(dllexport) int stateRecover(unsigned begin){return GhostTraceStateReferenceRecover(begin);}
'''


class RetirementTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous=(writer.EXPORTS,writer.ADAPTER)
  writer.EXPORTS+=EXTRA
  writer.ADAPTER+=r'''
static unsigned retirementUnlinks;
static int retirementUnlink(const char*p){++retirementUnlinks;return f_unlink_char(p);}
#define f_unlink_char retirementUnlink
'''
  original_read=Path.read_text
  def strict_read(path,*args,**kwargs):
   text=original_read(path,*args,**kwargs)
   if path.name=='ghost_kernel_fixture.h':
    text=text.replace('typedef struct { int index; u32 position; } FIL;','typedef struct { int index; u32 position,flags; } FIL;')
    text=text.replace('f->index=i; f->position=0; return FR_OK;','f->index=i; f->position=0; f->flags=flags; return FR_OK;')
    text=text.replace('static int f_read(FIL *f,void *dst,UINT size,UINT *got) {','static int f_read(FIL *f,void *dst,UINT size,UINT *got) {\n if(!(f->flags&FA_READ)){*got=0;return FR_DENIED;}')
   return text
  try:
   with patch.object(Path,'read_text',strict_read):warm.WarmWriterTests.setUpClass.__func__(cls)
  finally:writer.EXPORTS,writer.ADAPTER=previous
  cls.lib.lateReference.argtypes=cls.lib.queueReference.argtypes=[C.c_void_p]
  cls.lib.statePrepare.argtypes=[C.c_void_p,C.c_uint]
  cls.lib.retired.restype=C.c_uint
 setUp=warm.WarmWriterTests.setUp
 response=warm.WarmWriterTests.response
 execute=warm.WarmWriterTests.execute
 request=warm.WarmWriterTests.request
 allow=warm.WarmWriterTests.allow
 prepare=warm.WarmWriterTests.prepare
 start=warm.WarmWriterTests.start
 file=warm.WarmWriterTests.file
 def begin(self,fenced=False,bytes=1000):
  self.start()
  self.lib.chunk(0,A,1,b'x'*bytes,bytes,0);self.execute()
  if fenced:
   self.lib.submit(4,A,1,NONCE);self.execute()
  self.lib.warmBackground(40)
  self.assertEqual(self.lib.response()[4],2)
 def discard(self,op=6):
  self.lib.submit(op,A,0,NONCE);self.execute()
 def pin(self):
  fence=list(self.lib.warmFence()[:8])
  prefix=[NONCE,A,0x40000001,8,4,1,fence[3],fence[4]]
  branch=struct.pack('<24I',NONCE,A,0x474d534a,0x4ff,*prefix,*fence,0x80000007,8,9,0)
  state=struct.pack('<24I',0x4d534743,1,*prefix,0x474d534a,0x603,0x4ff,0x40000001,*fence,0,0)
  return branch,state
 def test_logical_retire_moves_fil_with_no_close_unlink_or_open(self):
  self.begin();self.prepare(run=B);old=self.file()
  before=(self.lib.warmCloseCalls(),self.lib.retired(6),self.lib.warmState(4))
  self.discard()
  self.assertEqual(self.lib.response()[4],5)
  self.assertEqual(self.lib.retired(0),1)
  self.assertEqual((self.lib.warmCloseCalls(),self.lib.retired(6),self.lib.warmState(4)),before)
  self.assertEqual(self.file(),old)
  opens=self.lib.warmState(4);self.start(run=B)
  self.assertEqual(self.lib.response()[4],2);self.assertEqual(self.lib.warmState(4),opens)
  self.assertEqual(self.lib.retired(2),A)
  self.allow(8)
  self.assertEqual(self.lib.retired(0),0);self.assertIsNone(self.file())
  self.assertIsNotNone(self.file(run=B))
 def test_fence_then_abandoned_candidate_uses_actual_header_scene_not_chunk_count(self):
  self.begin(fenced=True);header=self.file()[:64]
  self.assertEqual(struct.unpack_from('>I',header,24)[0],0x603)
  self.discard();self.assertEqual(self.lib.retired(0),1)
  self.allow(8);self.assertIsNone(self.file());self.assertEqual(self.lib.retired(0),0)
 def test_legacy_discard_still_physically_closes_and_deletes_before_ack(self):
  self.begin();before=self.lib.retired(6);self.discard(op=3)
  self.assertEqual(self.lib.response()[4],5);self.assertEqual(self.lib.retired(0),0)
  self.assertEqual(self.lib.retired(6),before+1);self.assertIsNone(self.file())
 def test_partial_current_chunk_needs_no_old_producer_buffer_after_detach(self):
  self.start();self.lib.warmBackground(40)
  self.lib.chunk(0,A,1,b'z'*0x20000,0x20000,0);self.lib.run(1)
  self.assertEqual(self.lib.response()[6],0)
  self.discard();self.assertEqual(self.lib.response()[4],5)
  self.assertEqual(self.lib.retired(0),1)
  self.assertEqual(self.lib.response()[6],0)
  self.allow(8);self.assertIsNone(self.file())
 def test_large_and_high_cluster_count_sources_fall_back_synchronously(self):
  for large in (False,True):
   self.setUp();self.start()
   data=random.Random(17).randbytes(0x80000 if large else 20000)
   for sequence in range(1,3 if large else 2):
    self.lib.chunk((sequence-1)&1,A,sequence,data,len(data),0);self.execute()
   self.lib.warmBackground(40)
   self.lib.clusterBytes(32768 if large else 512)
   self.discard();self.assertEqual(self.lib.retired(0),0);self.assertIsNone(self.file())
 def test_full_retirement_slot_fallback_preserves_a_new_matching_state_source(self):
  self.begin();self.discard();self.start(run=B)
  data=b'new checkpoint source'*100
  self.lib.chunk(0,B,1,data,len(data),0);self.execute();self.lib.submit(4,B,1,NONCE);self.execute()
  f=list(self.lib.warmFence()[:8]);prefix=[NONCE,B,0x40000002,8,4,1,f[3],f[4]]
  state=struct.pack('<24I',0x4d534743,1,*prefix,0x474d534a,0x603,0x4ff,0x40000002,*f,0,0)
  self.assertEqual(self.lib.statePrepare(state,9),1);old=self.file(run=B)
  self.lib.submit(6,B,0,NONCE);self.execute()
  self.assertEqual(self.lib.retired(2),A);self.assertEqual(self.file(run=B),old)

 def test_close_failure_keeps_old_handle_and_does_not_fail_new_writer(self):
  self.begin();self.prepare(run=B);self.discard();self.start(run=B)
  self.lib.failures(0xffffffff,1,0);self.allow(3)
  self.assertEqual(self.lib.retired(0),5);self.assertEqual(self.lib.response()[4],2)
  self.assertEqual(self.lib.response()[5],0);self.assertIsNotNone(self.file())
  old_index=self.lib.retired(3);self.lib.failures(0xffffffff,0,0)
  self.allow(20);self.assertEqual(self.lib.retired(3),old_index);self.assertEqual(self.lib.retired(0),5)
 def test_bad_header_unexpected_size_and_done_tail_are_preserved(self):
  for mutation in ('header','size','done'):
   self.setUp();self.begin();self.discard()
   if mutation=='header':self.lib.retiredMutate(0,0)
   elif mutation=='size':self.lib.retiredSize(self.lib.retired(4)+1)
   else:
    size=self.lib.retired(4)
    for i,v in enumerate(b'DONE'):self.lib.retiredMutate(size-32+i,v)
   old=self.file();self.allow(8)
   self.assertEqual(self.file(),old);self.assertEqual(self.lib.retired(0),0)
 def test_pending_branch_before_retire_closes_but_preserves_valid_parent(self):
  self.begin(fenced=True);branch,state=self.pin();old=self.file()
  self.lib.queueReference(branch);self.discard()
  self.assertEqual(self.lib.retired(0),0);self.assertEqual(self.file(),old)
  self.execute();self.assertEqual(self.lib.statePrepare(state,9),1)
  result=self.lib.stateRecover(1)
  for _ in range(80):
   if result:break
   result=self.lib.stateRecover(0)
  self.assertEqual(result,1)
 def test_state_prepare_before_store_prevents_fallback_unlink(self):
  self.begin(fenced=True);_,state=self.pin();old=self.file()
  self.assertEqual(self.lib.statePrepare(state,9),1)
  self.discard();self.assertEqual(self.lib.retired(0),0);self.assertEqual(self.file(),old)
  self.assertEqual(self.lib.stateStore(),1)
 def test_unknown_reference_summary_and_queued_state_job_preserve_fallback_source(self):
  for condition in ('unknown','statejob','reader'):
   self.setUp();self.begin();old=self.file()
   if condition=='unknown':self.lib.unknownReferences()
   elif condition=='statejob':self.lib.statePending(1)
   else:self.lib.warmReaders(1)
   self.discard();self.assertEqual(self.lib.retired(0),0)
   self.assertEqual(self.file(),old)
 def test_late_successful_or_uncertain_checkpoint_publication_preserves_retiree(self):
  for failed in (False,True):
   self.setUp();self.begin(fenced=True);branch,state=self.pin();self.discard();old=self.file()
   if failed:self.lib.failures(0,0,0)
   result=self.lib.lateReference(branch)
   self.assertEqual(result,0 if failed else 1)
   self.assertEqual(self.lib.retired(1),1)
   self.lib.failures(0xffffffff,0,0);self.allow(8)
   self.assertEqual(self.file(),old);self.assertEqual(self.lib.retired(0),0)
 def test_fresh_generation_proof_and_queued_pins_are_rechecked_before_unlink(self):
  for condition in ('generation','branch','statejob','reader'):
   self.setUp();self.begin(fenced=True);branch,_=self.pin();self.discard();self.allow(3)
   self.assertEqual(self.lib.retired(0),4);old=self.file()
   if condition=='generation':self.lib.newReferenceGeneration()
   elif condition=='branch':self.lib.queueReference(branch)
   elif condition=='statejob':self.lib.statePending(1)
   else:self.lib.warmReaders(1)
   self.lib.warmBackground(1)
   self.assertEqual(self.file(),old,condition)
 def test_matching_explicit_state_recovery_preserves_and_closes_without_permit(self):
  self.begin(fenced=True);_,state=self.pin();self.discard()
  self.lib.warmPermit(0,0);self.assertEqual(self.lib.statePrepare(state,9),1)
  result=self.lib.stateRecover(1)
  for _ in range(80):
   if result:break
   result=self.lib.stateRecover(0)
  self.assertEqual(result,1);self.assertEqual(self.lib.retired(0),0)
  self.assertTrue(self.file() is not None or self.lib.completedSource(A))
 def test_matching_explicit_recovery_close_failure_retains_owner_and_refuses(self):
  self.begin(fenced=True);_,state=self.pin();self.discard();old=self.file()
  self.lib.warmPermit(0,0);self.assertEqual(self.lib.statePrepare(state,9),1)
  self.lib.failures(0xffffffff,1,0)
  self.assertEqual(self.lib.stateRecover(1),-1)
  self.assertEqual(self.lib.retired(0),5);self.assertEqual(self.file(),old)
 def test_nonmatching_state_recovery_does_not_wait_for_or_close_retiree_or_current_writer(self):
  other=A+9
  self.start(run=other);self.lib.chunk(0,other,1,b'other source'*100,1200,0);self.execute()
  self.lib.submit(4,other,1,NONCE);self.execute()
  f=list(self.lib.warmFence()[:8]);prefix=[NONCE,other,0x40000001,8,4,1,f[3],f[4]]
  state=struct.pack('<24I',0x4d534743,1,*prefix,0x474d534a,0x603,0x4ff,0x40000001,*f,0,0)
  self.lib.submit(2,other,1,NONCE);self.execute()
  self.begin();self.discard();self.start(run=B);current=self.file(run=B)
  phase,index=self.lib.retired(0),self.lib.retired(3)
  self.lib.warmPermit(0,0);self.assertEqual(self.lib.statePrepare(state,9),1)
  self.assertEqual(self.lib.stateRecover(1),1)
  self.assertEqual((self.lib.retired(0),self.lib.retired(3)),(phase,index))
  self.assertEqual(self.lib.response()[4],2);self.assertEqual(self.file(run=B),current)
 def test_size_fallback_with_a_valid_state_reference_preserves_parent(self):
  self.start();data=random.Random(37).randbytes(20000)
  self.lib.chunk(0,A,1,data,len(data),0);self.execute();self.lib.submit(4,A,1,NONCE);self.execute()
  self.lib.warmBackground(40);_,state=self.pin()
  self.assertEqual(self.lib.statePrepare(state,9),1);self.assertEqual(self.lib.stateStore(),1)
  old=self.file();self.lib.clusterBytes(512);self.discard()
  self.assertEqual(self.lib.retired(0),0);self.assertEqual(self.file(),old)

 def test_manual_same_identity_start_is_refused_while_old_owner_is_retiring(self):
  self.begin();self.discard();old=self.file();self.start()
  self.assertEqual(self.lib.response()[4],6);self.assertEqual(self.file(),old)
 def test_no_background_close_when_offline_permit_revoked_or_reader_active(self):
  for reader in (False,True):
   self.setUp();self.begin();self.discard();before=self.lib.warmCloseCalls()
   self.lib.warmPermit(0,0)
   if reader:self.lib.warmReaders(1)
   self.lib.warmBackground(30)
   self.assertEqual(self.lib.warmCloseCalls(),before);self.assertEqual(self.lib.retired(0),1)
 def test_pending_flag_survives_ready_warm_phase_and_clears_after_cleanup(self):
  self.begin();self.prepare(run=B);self.discard()
  self.assertEqual(self.response()[4],6);self.assertEqual(self.response()[5],0x100)
  self.allow(8);self.assertEqual(self.response()[5],0)


if __name__=='__main__':unittest.main()
