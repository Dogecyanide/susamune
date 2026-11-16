"""Run retained-prefix handoff and atomic continuation against the real ARM writer."""
import ctypes as C,struct,unittest
from pathlib import Path
from unittest.mock import patch
import test_ghost_trace_retirement as retirement
import test_ghost_trace_prepare as warm
from test_ghost_trace_reader import fnv
NONCE=warm.NONCE;A=warm.RUN;B=A+1;D=A+2;E=A+3;CAPS=warm.CAPS|0x200000
EXTRA=r"""
__declspec(dllexport) void atomic(const void*payload,unsigned oldRun,unsigned preserve,unsigned child,unsigned mismatch){
 struct MsTraceRequest*q=&traceMailbox.request;unsigned primary=q->sequence+1;
 branchMailbox.request=(struct MsTraceBranchRequest){MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,WRITER->response.nonce,
   branchMailbox.request.sequence+1,MS_TRACE_BRANCH_ASYNC_CONTINUE,primary+mismatch,preserve,oldRun};
 memcpy(&branchMailbox.payload,payload,96);
 *q=(struct MsTraceRequest){MS_TRACE_MAGIC,MS_TRACE_VERSION,WRITER->response.nonce,primary,MS_TRACE_CONTINUE,child,0x603,0x2004ff};
}
__declspec(dllexport) const void*asyncResponse(void){return &branchMailbox.response;}
__declspec(dllexport) unsigned asyncField(unsigned n){struct TraceLink*l=&WRITER->prepare.link;switch(n){case 0:return WRITER->prepare.phase;case 1:return l->phase;case 2:return l->file.index;case 3:return WRITER->active;case 4:return WRITER->references.valid;case 5:return WRITER->references.failed;case 6:return WRITER->request.run;case 7:return WRITER->file.position;case 8:return retireNonce(&WRITER->retiring);case 10:return WRITER->file.index;default:return WRITER->retiring.phase;}}
__declspec(dllexport) const void*named(unsigned run,unsigned complete,unsigned*n){char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/trace_%08X_%08X.%s",WRITER->response.nonce,run,complete?"msgt":"part");int i=lookup(p);if(i<0){*n=0;return 0;}*n=testFiles[i].size;return testFiles[i].bytes;}
__declspec(dllexport) unsigned mapExists(unsigned run){char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/ref_%08X_%08X_464F524B_00000001_00000001.msgb",WRITER->response.nonce,run);return lookup(p)>=0;}
__declspec(dllexport) unsigned primarySequence(void){return traceMailbox.request.sequence;}
__declspec(dllexport) void corruptFence(void){traceFence.headerHash^=1;}
__declspec(dllexport) void unknownCache(void){WRITER->references.valid=0;}
__declspec(dllexport) unsigned cacheHasParent(unsigned nonce,unsigned run){return !referenceCacheUnreferenced(nonce,run);}
__declspec(dllexport) int childAdmitted(unsigned run){unsigned char h[64];unsigned n;const void*p=named(run,1,&n);if(!p||n<64)return 0;memcpy(h,p,64);return GhostTraceChildDependencyValid(h,WRITER->response.nonce,run,GAME_ID);}
__declspec(dllexport) int dropSource(unsigned run,unsigned hash){return GhostTraceRetainedDiscard(WRITER->response.nonce,run,hash,1);}
__declspec(dllexport) void overwritePayloads(void){memset(traceBuffers,0xee,sizeof(traceBuffers));}
"""
class AsyncWriterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  original=retirement.EXTRA;retirement.EXTRA+=EXTRA;read=Path.read_text
  def smaller(path,*a,**kw):
   text=read(path,*a,**kw)
   if path.name=='ghost_kernel_fixture.h':text=text.replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 16').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 2000000')
   return text
  try:
   with patch.object(Path,'read_text',smaller):retirement.RetirementTests.setUpClass.__func__(cls)
  finally:retirement.EXTRA=original
  cls.lib.atomic.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint];cls.lib.asyncResponse.restype=C.POINTER(C.c_uint);cls.lib.asyncField.restype=C.c_uint
  cls.lib.named.argtypes=[C.c_uint,C.c_uint,C.POINTER(C.c_uint)];cls.lib.named.restype=C.c_void_p
 setUp=warm.WarmWriterTests.setUp
 execute=warm.WarmWriterTests.execute
 allow=warm.WarmWriterTests.allow
 response=warm.WarmWriterTests.response
 def main(self,op,run=A,boundary=0x603):
  self.lib.submit(op,run,boundary,NONCE);self.lib.capabilities(CAPS);self.execute()
 def start(self,run=A):self.main(1,run)
 def prepare(self,run):
  self.lib.warmRequest(2,run,CAPS,0);self.execute();self.allow(12);self.assertEqual(self.response()[4],6)
 def file(self,run=A,complete=0):
  n=C.c_uint();p=self.lib.named(run,complete,C.byref(n));return C.string_at(p,n.value) if p else None
 def parent(self,run=A):
  self.start(run);data=b'checked parent prefix'*80;self.lib.chunk(0,run,1,data,len(data),0);self.execute();self.main(4,run,1)
  self.lib.warmBackground(60);f=list(self.lib.warmFence()[:8]);prefix=[NONCE,run,0x40000001,8,4,1,f[3],f[4]]
  return data,prefix,f
 def branch(self,child,prefix,fence):return struct.pack('<24I',NONCE,child,0x474d534a,CAPS,*prefix,*fence,0x464f524b,1,1,0)
 def atom(self,child,prefix,fence,old=A,preserve=1,mismatch=0):
  self.lib.atomic(self.branch(child,prefix,fence),old,preserve,child,mismatch);self.execute()
 def bresponse(self):return list(self.lib.asyncResponse()[:8])
 def background(self,limit=80):
  for _ in range(limit):
   self.allow(1)
   if self.bresponse()[4]!=0x100:return
  self.fail('Async map did not reach terminal status')
 def test_retain_parks_fenced_file_without_close_rename_or_delete(self):
  data,prefix,f=self.parent();self.prepare(B);before=self.lib.warmCloseCalls();unlinks=self.lib.retired(6);self.main(7,A)
  self.assertEqual(self.lib.response()[4:6],[5,0]);self.assertEqual(self.lib.warmCloseCalls(),before)
  self.assertEqual(self.lib.asyncField(9),6);self.start(B);self.allow(12)
  source=self.file(A,1);self.assertIsNotNone(source);self.assertEqual(source[-32:-28],b'DONE');self.assertEqual(self.lib.retired(6),unlinks)
 def test_retain_drops_only_unacknowledged_partial_tail_and_never_reads_old_payload(self):
  data,prefix,f=self.parent();self.lib.chunk(1,A,2,b'partial'*24000,168000,0);self.lib.run(1);self.assertEqual(self.lib.response()[6],1)
  self.main(7,A);self.lib.overwritePayloads();self.allow(12);source=self.file(A,1)
  self.assertEqual(struct.unpack_from('>I',source,len(source)-24)[0],1)
  self.assertEqual(struct.unpack_from('>I',source,len(source)-4)[0],1)
  self.assertEqual(struct.unpack_from('>I',source,len(source)-20)[0],f[1]);self.assertEqual(len(source),f[1]+32)
 def test_retain_refuses_missing_or_changed_fence_and_keeps_old_owner(self):
  self.start();self.main(7);self.assertEqual(self.lib.response()[5],8);self.assertEqual(self.lib.asyncField(3),1)
  self.setUp();data,prefix,f=self.parent();self.lib.corruptFence();old=self.file();self.main(7)
  self.assertEqual(self.lib.response()[5],8);self.assertEqual(self.file(),old);self.assertEqual(self.lib.asyncField(3),1)
 def test_atomic_same_parent_is_pending_until_exact_durable_map(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  self.assertEqual(self.lib.response()[4:6],[2,0]);self.assertEqual(self.bresponse()[4:], [0x100,B,self.lib.primarySequence(),A])
  h=self.file(B)[:64];self.assertEqual(struct.unpack_from('>4I',h,44),(0x42524348,NONCE,A,1));self.assertEqual(struct.unpack_from('>I',h,60)[0],fnv(h[:60]))
  self.assertEqual(self.lib.run(1),0,'Known old bank must not starve background work')
  self.background();self.assertEqual(self.bresponse()[4],0);self.assertTrue(self.lib.mapExists(B));self.assertIsNotNone(self.file(A,1))
 def test_other_parent_uses_unreferenced_retirement_with_exact_side_exception(self):
  data,prefix,f=self.parent();self.main(2,A,1);self.start(B);self.lib.chunk(0,B,1,b'old unpinned',12,0);self.execute();self.lib.warmBackground(60);self.prepare(D)
  self.atom(D,prefix,f,old=B,preserve=0);self.assertEqual(self.lib.response()[4:6],[2,0]);self.background()
  self.assertEqual(self.bresponse()[4],0);self.assertIsNotNone(self.file(A,1));self.assertIsNone(self.file(B));self.assertIsNotNone(self.file(D))
 def test_atomic_refusal_does_not_drop_source_buffers_or_warm_ownership(self):
  data,prefix,f=self.parent();old=self.file();self.atom(B,prefix,f)
  self.assertEqual(self.lib.response()[5],8);self.assertEqual(self.bresponse()[5],0);self.assertEqual(self.lib.asyncField(6),A);self.assertEqual(self.file(),old)
  self.prepare(B);self.atom(B,prefix,f,mismatch=1);self.assertEqual(self.lib.response()[5],3);self.assertEqual(self.lib.asyncField(6),A);self.assertEqual(self.lib.warmState(1),1)
 def test_wrong_new_bank_is_still_a_protocol_error(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  self.lib.chunk(0,D,1,b'wrong owner',11,0);self.execute();self.assertEqual(self.lib.response()[4:6],[6,3]);self.assertIsNotNone(self.file(A))
 def test_parent_hold_and_partial_temp_do_not_poison_negative_summary(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  for _ in range(30):
   self.allow(1)
   if self.lib.asyncField(1)==4:break
  self.assertEqual(self.lib.asyncField(1),4);self.assertEqual(self.lib.asyncField(5),0)
  header=struct.unpack_from('>I',self.file(A,1),60)[0];self.assertEqual(self.lib.dropSource(A,header),-1)
  self.lib.warmPermit(0,0);self.lib.warmBackground(30);self.assertEqual(self.lib.asyncField(5),0)
  self.background();self.assertEqual(self.bresponse()[4],0);self.assertEqual(self.lib.asyncField(4),1);self.assertEqual(self.lib.cacheHasParent(NONCE,A),1)
 def test_release_child_does_not_cancel_parent_map_publication(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f);self.main(5,B);self.background()
  self.assertEqual(self.bresponse()[4],0);self.assertTrue(self.lib.mapExists(B));self.assertIsNotNone(self.file(A,1))
 def test_map_close_failure_retains_handle_but_not_permanent_async_lock(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  for _ in range(50):
   self.allow(1)
   if self.lib.asyncField(1)==6:break
  self.assertEqual(self.lib.asyncField(1),6);self.lib.failures(0xffffffff,1,0);self.allow(1)
  self.assertEqual(self.bresponse()[4],2);self.assertEqual(self.lib.asyncField(0),7);self.assertEqual(self.lib.warmState(1),2);index=self.lib.asyncField(2)
  self.lib.failures(0xffffffff,0,0);self.main(5,B);self.start(D)
  self.assertEqual(self.lib.response()[4:6],[2,0]);self.assertEqual(self.lib.asyncField(2),index);self.assertEqual(self.lib.warmState(1),2);self.assertFalse(self.lib.mapExists(B))
 def test_failed_map_close_cancel_retries_exact_alias_before_replacement(self):
  data,prefix,f=self.parent();self.prepare(B);owner=self.response()[7];self.atom(B,prefix,f)
  for _ in range(50):
   self.lib.warmPermit(1,0);self.lib.warmBackground(1)
   if self.lib.asyncField(1)==6:break
  self.assertEqual(self.lib.asyncField(1),6);self.lib.failures(0xffffffff,1,0)
  self.lib.warmPermit(1,0);self.lib.warmBackground(1);index=self.lib.asyncField(2);child=self.file(B)
  self.assertEqual(self.lib.warmState(1),2);self.assertNotEqual(index,self.lib.asyncField(10))
  self.lib.warmRequest(2,D,CAPS,0);self.execute()
  self.assertEqual(self.response()[4:8],[7,2,B,owner]);self.assertEqual(self.lib.asyncField(2),index)
  closes=self.lib.warmCloseCalls();unlinks=self.lib.retired(6)
  self.lib.warmRequest(3,B,0,owner);self.execute();self.allow(1)
  self.assertGreater(self.lib.warmCloseCalls(),closes);self.assertEqual(self.lib.warmState(1),2)
  self.assertEqual(self.lib.asyncField(2),index);self.assertEqual(self.file(B),child);self.assertIsNotNone(self.file(A,1))
  self.assertEqual(self.lib.retired(6),unlinks);self.lib.failures(0xffffffff,0,0)
  self.lib.warmRequest(3,B,0,owner);self.execute();self.allow(1)
  self.assertEqual(self.lib.warmState(1),0);self.assertEqual(self.lib.retired(6),unlinks)
  self.prepare(D);self.assertNotEqual(self.lib.asyncField(2),index);self.assertEqual(self.file(B),child)
 def test_retained_close_failure_keeps_boot_owner_and_fails_dependency(self):
  data,prefix,f=self.parent();self.prepare(B);unlinks=self.lib.retired(6);self.atom(B,prefix,f)
  for _ in range(20):
   self.lib.warmPermit(1,0);self.lib.warmBackground(1)
   if self.lib.asyncField(9)==9:break
  self.assertEqual(self.lib.asyncField(9),9);self.lib.failures(0xffffffff,1,0);self.allow(1)
  self.assertEqual(self.lib.asyncField(9),12);self.assertEqual(self.lib.asyncField(8),NONCE);self.background()
  self.assertNotEqual(self.bresponse()[4],0);self.assertIsNotNone(self.file(A));self.assertEqual(self.lib.retired(6),unlinks)

 def test_post_adoption_header_failure_reports_child_owner_and_preserves_parent(self):
  data,prefix,f=self.parent();self.prepare(B);self.lib.failures(0,0,0);self.atom(B,prefix,f)
  self.assertEqual(self.lib.response()[4:6],[6,2]);self.assertEqual(self.bresponse()[5:],[B,self.lib.primarySequence(),A])
  self.assertEqual(self.lib.asyncField(6),B);self.assertIsNotNone(self.file(A));self.assertEqual(self.lib.asyncField(9),6)
  self.lib.failures(0xffffffff,0,0);self.main(5,B);self.allow(12);self.assertIsNotNone(self.file(A,1))
 def test_rejected_warm_header_restores_old_append_cursor(self):
  data,prefix,f=self.parent();oldHeader=self.file(A)[:64];self.prepare(B);self.lib.warmMutate(0,0);before=len(self.file(A));self.atom(B,prefix,f)
  self.assertEqual(self.bresponse()[5],0);self.assertEqual(self.lib.asyncField(6),A);self.assertEqual(self.lib.asyncField(7),before)
  payload=b'after a refused handoff';self.lib.chunk(1,A,2,payload,len(payload),0);self.execute()
  self.assertEqual(self.file(A)[:64],oldHeader);self.assertEqual(self.lib.response()[6],2)
  self.main(2,A,2);self.assertIsNotNone(self.file(A,1));self.assertEqual(self.file(A,1)[:64],oldHeader)
 def test_stale_marker_survives_finished_map_and_ends_after_first_new_bank(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f);self.background();self.assertEqual(self.lib.run(1),0)
  self.lib.chunk(0,B,1,b'new child',9,0);self.execute();self.assertEqual(self.lib.response()[6],1)
  self.lib.chunk(1,A,2,b'late old owner',14,0);self.execute();self.assertEqual(self.lib.response()[4:6],[6,3])
 def test_failed_map_rename_never_admits_orphan_even_with_valid_temp(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  for _ in range(70):
   self.lib.warmPermit(1,0);self.lib.warmBackground(1)
   if self.lib.asyncField(1)==10:break
  self.assertEqual(self.lib.asyncField(1),10);self.lib.failures(0xffffffff,0,1);self.lib.warmPermit(1,0);self.lib.warmBackground(1)
  self.assertEqual(self.bresponse()[4],2);self.assertFalse(self.lib.mapExists(B));self.lib.failures(0xffffffff,0,0)
  self.lib.chunk(0,B,1,b'unpublished child',17,0);self.execute();self.main(2,B,1)
  self.assertIsNotNone(self.file(B,1));self.assertEqual(self.lib.childAdmitted(B),0);self.assertIsNotNone(self.file(A,1))
 def test_parent_finalization_failure_terminates_map_without_fabricating_done(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f);self.lib.failures(0,0,0)
  for _ in range(20):
   self.lib.warmPermit(1,0);self.lib.warmBackground(1)
   if self.bresponse()[4]!=0x100:break
  self.assertEqual(self.bresponse()[4],2);self.assertEqual(self.lib.asyncField(9),11);self.assertIsNotNone(self.file(A));self.assertIsNone(self.file(A,1));self.assertFalse(self.lib.mapExists(B))
 def test_metadata_only_permit_finishes_exact_parent_map_without_warming(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  self.lib.warmRequest(2,D,CAPS,0);self.execute();self.assertEqual(self.response()[5]&255,5)
  for _ in range(50):
   self.lib.warmPermit(2,0);self.lib.warmBackground(1)
   if self.bresponse()[4]!=0x100:break
  self.assertEqual(self.bresponse()[4],0);self.assertIsNotNone(self.file(A,1));self.assertTrue(self.lib.mapExists(B));self.assertIsNone(self.file(D))
  self.lib.warmRequest(2,D,CAPS,0);self.execute();self.assertEqual(self.response()[4],1)
  for _ in range(20):self.lib.warmPermit(2,0);self.lib.warmBackground(1)
  self.assertEqual(self.response()[4],1);self.assertIsNone(self.file(D));self.allow(12);self.assertEqual(self.response()[4],6)
 def test_metadata_only_permit_cannot_delete_unreferenced_retirement(self):
  self.start();self.lib.chunk(0,A,1,b'unpinned tail',13,0);self.execute();self.lib.warmBackground(60);self.prepare(B);self.main(6,A)
  self.assertEqual(self.lib.asyncField(9),1);unlinks=self.lib.retired(6)
  for _ in range(20):self.lib.warmPermit(2,0);self.lib.warmBackground(1)
  self.assertEqual(self.lib.asyncField(9),1);self.assertEqual(self.lib.retired(6),unlinks);self.assertIsNotNone(self.file(A))
  self.allow(12);self.assertIsNone(self.file(A));self.assertEqual(self.lib.retired(6),unlinks+1)
 def test_metadata_permit_keeps_unknown_flags_headroom_and_reader_guards(self):
  for flags,queued,reader in [(4,0,0),(2,0x40001,0),(2,0,1),(0,0,0)]:
   with self.subTest(flags=flags,queued=queued,reader=reader):
    self.setUp();data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f);before=self.file(A);self.lib.warmReaders(reader)
    for _ in range(20):self.lib.warmPermit(flags,queued);self.lib.warmBackground(1)
    self.assertEqual(self.bresponse()[4],0x100);self.assertEqual(self.lib.asyncField(9),6);self.assertEqual(self.file(A),before)
    self.lib.warmReaders(0)
    for _ in range(50):
     self.lib.warmPermit(2,0);self.lib.warmBackground(1)
     if self.bresponse()[4]!=0x100:break
    self.assertEqual(self.bresponse()[4],0)
 def test_new_durable_checkpoint_during_map_keeps_generation_protection(self):
  data,prefix,f=self.parent();self.prepare(B);self.atom(B,prefix,f)
  for _ in range(70):
   self.lib.warmPermit(1,0);self.lib.warmBackground(1)
   if self.lib.asyncField(1)==4:break
  checkpoint=struct.pack('<24I',NONCE,A,0x474d534a,CAPS,*prefix,*f,0x80000007,8,9,0)
  self.assertEqual(self.lib.lateReference(checkpoint),1);self.background();self.allow(100)
  self.assertEqual(self.bresponse()[4],0);self.assertEqual(self.lib.asyncField(5),0);self.assertEqual(self.lib.cacheHasParent(NONCE,A),1)

if __name__=='__main__':unittest.main()
