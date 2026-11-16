"""Exercise atomic continuation ownership and fast practice fallback in the actual PPC producer."""
import ctypes as C
import struct
import unittest
import test_ghost_trace_producer as producer
import test_ghost_trace_warm_producer as warm

POST=r"""
API int fastLoad(unsigned slot,unsigned generation){return GhostRecording::prepareFastCheckpointLoad(snapshots[slot],slot,generation);}
API int fastSkip(unsigned slot,unsigned generation){return GhostRecording::authorizeFastCheckpointLoad(snapshots[slot],slot,generation);}
API int fastLoadReady(unsigned slot,unsigned generation){return GhostRecording::checkpointLoadReady(snapshots[slot],slot,generation);}
API int loadRecorded(){return GhostRecording::checkpointLoadRecorded();}
API int branchOwnerHeld(){return GhostTraceBranchOwner::state.owner!=nullptr;}
API unsigned initialParent(unsigned n){return n==0?GhostTrace::s.parentNonce:n==1?GhostTrace::s.parentRun:GhostTrace::s.parentChunk;}
API int untracked(){return GhostTrace::fastContinuationUntracked();}
API int checkpointWithoutTrace(){GhostTrace::CheckpointSnapshot v;return GhostRecording::captureCheckpoint(v)&&!v.magic;}
API int saveStoppingBusyRecording(unsigned slot, unsigned generation) {
    GhostRecording::CheckpointSave transaction;
    auto &snapshot = snapshots[slot];
    return transaction.capture(snapshot, true) && !snapshot.magic &&
           GhostTrace::checkpointValid(snapshot) && transaction.commit(slot, generation);
}
API int publicationPending(){return GhostTrace::continuationPublicationPending();}
API unsigned finishedForPublication(){return GhostTrace::s.publishFinish;}
API int managedSelection(){char name[48];return GhostRecording::copySelection(name,sizeof(name),nullptr);}
API unsigned selectedToken(){char name[48];unsigned token=0;GhostRecording::copySelection(name,sizeof(name),&token);return token;}
API int exportForSave(void*out){unsigned owner,token;return GhostRecording::exportManifest(out,0,"Default",&owner,&token);}
API int saveStarted(unsigned token){return GhostRecording::publicationStarted(token,77);}
API void saveCompleted(){GhostRecording::publicationResult(77,true);}
API int ownsManagedSession(){return GhostRecording::ownsSession();}
API void failedFence(){auto&pins=GhostTrace::checkpoints->pins;auto&p=pins.pins[pins.slots[0].pin];p.phase=GhostCheckpoints::FAILED;p.error=MS_TRACE_IO;}
"""

class FastProducerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous=producer.POST;previous_arm=producer.ARM;producer.POST+=POST
  producer.ARM+=r"""
__declspec(dllexport) unsigned fastDiagnostic(unsigned n){unsigned values[]={WRITER->prepare.phase,WRITER->prepare.link.phase,WRITER->retiring.phase,WRITER->branchResponse.status,GhostTraceStoragePending(),GhostTraceBackgroundPending(),WRITER->prepare.permitSequence,WRITER->prepare.permitReady,WRITER->request.operation};return n<9?values[n]:0;}
"""
  try:warm.WarmProducerTests.setUpClass.__func__(cls)
  finally:producer.POST=previous;producer.ARM=previous_arm
  for name in ('fastLoad','fastSkip','fastLoadReady','saveStoppingBusyRecording'):getattr(cls.producer,name).argtypes=[C.c_uint,C.c_uint]
  cls.producer.initialParent.restype=cls.producer.selectedToken.restype=C.c_uint
  cls.producer.exportForSave.argtypes=[C.c_void_p]
 setUp=warm.WarmProducerTests.setUp
 pump=warm.WarmProducerTests.pump
 response=warm.WarmProducerTests.response
 data=warm.WarmProducerTests.data
 file=warm.WarmProducerTests.file
 def setUp(self):
  warm.WarmProducerTests.setUp(self);self.pump(12)
  self.assertEqual(self.producer.record(10,40,100),1);self.assertEqual(self.producer.save(0,11),1);self.pump(12)
  self.assertEqual(self.producer.ready(0),1);self.old=self.producer.run()
  self.payload=bytes(C.string_at(self.producer.buffer(0),256))
 def words(self,p):return struct.unpack('<8I',C.string_at(p,32))
 def begin(self):
  self.assertEqual(self.producer.fastLoad(0,11),0)
  self.primary=self.words(self.producer.request());self.side=self.words(self.producer.branch()+96)
  self.assertEqual(self.primary[4],8);self.assertEqual(self.side[4:8],(5,self.primary[3],1,self.old))
  self.child=self.primary[5];self.assertNotEqual(self.child,self.old)
  self.assertEqual(self.producer.run(),self.old);self.assertEqual(self.producer.branchOwnerHeld(),1)
  self.assertEqual(bytes(C.string_at(self.producer.buffer(0),256)),self.payload)
 def receipt(self,status=0x100,owner=None,primary_error=0,phase=2,ack=None,atomic=None,old=None):
  if owner is None:owner=self.child
  if ack is None:ack=self.primary[3]
  if atomic is None:atomic=self.primary[3]
  if old is None:old=self.old
  r=(C.c_uint*16)(0x4d535452,4,0x12345678,ack,phase,primary_error,0,64,*([0]*8))
  b=(C.c_uint*8)(0x4d534742,1,0x12345678,self.side[3],status,owner,atomic,old)
  self.producer.receipts(r,self.arm.fence(),b);self.producer.step()
 def accepted(self):
  self.begin();self.receipt();self.assertEqual(self.producer.fastLoad(0,11),1)
  self.assertEqual(self.producer.run(),self.child);self.assertEqual(self.producer.recording(),0)
 def test_atomic_owner_ack_is_required_before_bank_reuse(self):
  self.begin();self.receipt(atomic=self.primary[3]+1)
  self.assertEqual(self.producer.run(),self.old)
  self.assertEqual(bytes(C.string_at(self.producer.buffer(0),256)),self.payload)
  self.assertEqual(self.producer.fastLoad(0,11),0)
  self.receipt();self.assertEqual(self.producer.fastLoad(0,11),1)
  self.assertEqual(self.producer.run(),self.child)
 def test_commit_records_continuation_while_publication_stays_owned(self):
  self.accepted();self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.loadRecorded(),1)
  self.assertEqual(self.producer.publicationPending(),1);self.assertEqual(self.producer.branchOwnerHeld(),1)
  self.assertEqual(self.producer.record(11,44,300),1)
  data=C.string_at(self.producer.buffer(0),60)
  self.assertEqual(struct.unpack_from('>HHII',data),(27,48,10,40))
  self.assertEqual(struct.unpack_from('>4I',data,24),(0x12345678,self.old,1,struct.unpack('<24I',C.string_at(self.producer.snapshot(0),96))[9]))
  self.assertEqual([self.producer.initialParent(i) for i in range(3)],[0x12345678,self.old,1])
 def test_ownership_ack_during_ram_copy_can_attach_before_simulation(self):
  self.begin();self.assertEqual(self.producer.fastSkip(0,11),1)
  self.assertEqual(self.producer.fastLoadReady(0,11),1);self.assertEqual(self.producer.run(),self.old)
  self.receipt();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.loadRecorded(),1);self.assertEqual(self.producer.record(11,44,300),1)
 def test_skipped_restore_never_starts_capture_late(self):
  self.begin();self.assertEqual(self.producer.fastSkip(0,11),1)
  self.assertEqual(self.producer.fastLoadReady(0,11),1);self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.loadRecorded(),0);self.assertEqual(self.producer.run(),self.old)
  self.receipt();self.assertEqual(self.producer.run(),self.child)
  self.assertEqual(self.producer.recording(),0);self.assertEqual(self.producer.untracked(),1)
  self.assertEqual(self.words(self.producer.request())[4:6],(5,self.child))
  self.assertEqual(self.producer.record(11,44,999),0);self.assertEqual(self.producer.branchOwnerHeld(),1)
 def test_refusal_releases_only_still_owned_old_run(self):
  self.begin();self.receipt(status=8,owner=0,primary_error=8)
  self.assertEqual(self.producer.run(),self.old)
  self.assertEqual(self.words(self.producer.request())[4:6],(5,self.old))
  self.assertEqual(self.producer.fastSkip(0,11),1);self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.loadRecorded(),0)
 def test_storage_failure_during_ram_restore_is_practice_success(self):
  self.accepted();self.receipt(status=2)
  self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.loadRecorded(),0)
  self.assertEqual(self.producer.recording(),0)
 def test_finish_stops_at_original_boundary_until_map_is_durable(self):
  self.accepted();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.record(11,44,300),1);self.assertEqual(self.producer.finishManaged(),1)
  self.producer.next_frame();self.assertEqual(self.producer.finishedForPublication(),1)
  self.assertEqual(self.producer.endingValue(),0);self.assertEqual(self.producer.record(12,48,999),0)
  self.receipt(status=0);self.assertEqual(self.producer.branchOwnerHeld(),0)
  self.producer.next_frame();self.assertEqual(self.producer.endingValue(),2)
  self.assertEqual((self.producer.frame(),self.producer.tick()),(11,44))
 def test_busy_restore_preserves_an_already_finished_attempt(self):
  self.accepted();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.record(11,44,300),1);self.assertEqual(self.producer.finishManaged(),1)
  self.producer.next_frame();self.assertEqual(self.producer.finishedForPublication(),1)
  self.assertEqual(self.producer.fastSkip(0,11),1);self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.loadRecorded(),0);self.assertEqual(self.producer.endingValue(),0)
  self.receipt(status=0);self.producer.next_frame()
  self.assertEqual(self.producer.endingValue(),2)
 def test_finished_attempt_survives_warp_and_reset_before_durable_map(self):
  self.accepted();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.record(11,44,300),1);self.assertEqual(self.producer.finishManaged(),1)
  self.producer.next_frame();self.assertEqual(self.producer.finishedForPublication(),1)
  self.assertEqual(self.producer.start(),0);self.producer.stop()
  self.assertEqual(self.producer.endingValue(),0);self.assertEqual(self.producer.branchOwnerHeld(),1)
  self.assertEqual(self.producer.record(12,48,999),0)
  self.receipt(status=0);self.producer.next_frame()
  self.assertEqual(self.producer.endingValue(),2)
  self.assertEqual((self.producer.frame(),self.producer.tick()),(11,44))
 def test_ram_save_while_metadata_is_pending_skips_only_recording(self):
  self.accepted();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.checkpointWithoutTrace(),1)
  self.assertEqual(self.producer.untracked(),1);self.assertEqual(self.producer.branchOwnerHeld(),1)
  self.assertEqual(self.producer.ready(0),1)
 def test_manual_second_save_stops_busy_recording_and_keeps_earlier_checkpoints(self):
  self.accepted()
  self.assertEqual(self.producer.commit(),1)
  self.receipt(status=0)
  self.assertEqual(self.producer.publicationPending(),0)
  self.assertEqual(self.producer.record(11,44,300),1)
  self.assertEqual(self.producer.save(1,12),1)
  self.assertEqual(self.producer.record(12,48,301),1)
  # The first checkpoint's sealed bank is still awaiting an ARM receipt.
  self.assertEqual(self.producer.save(2,13),0)
  self.assertEqual(self.producer.recording(),1)
  self.assertEqual(self.producer.pinrefs(),2)
  self.assertEqual(self.producer.saveStoppingBusyRecording(2,13),1)
  self.assertEqual(self.producer.recording(),0)
  self.assertEqual(self.producer.pinrefs(),2)
  self.assertEqual(self.producer.ready(0),1)
  self.assertEqual(self.producer.ready(1),0)
  self.assertEqual(self.producer.owned(self.child),1)
 def test_matching_ram_pin_with_io_failure_is_busy_not_invalid(self):
  self.producer.failedFence();self.assertEqual(self.producer.ready(0),-1)
  self.assertEqual(self.producer.fastLoad(0,11),0)
  self.assertEqual(self.producer.fastSkip(0,11),1);self.assertEqual(self.producer.fastLoadReady(0,11),1)
  self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.loadRecorded(),0)
 def test_warp_during_metadata_publication_does_not_wait_for_sd(self):
  self.accepted();self.assertEqual(self.producer.commit(),1)
  self.assertEqual(self.producer.record(11,44,300),1)
  self.assertEqual(self.producer.start(),0)
  self.assertEqual(self.producer.recording(),0);self.assertEqual(self.producer.untracked(),1)
  self.assertEqual(self.producer.branchOwnerHeld(),1);self.assertEqual(self.producer.ready(0),1)
 def test_invalid_sidecar_is_not_treated_as_recorder_busy(self):
  value=C.cast(self.producer.snapshot(0),C.POINTER(C.c_uint));value[1]=999
  self.assertEqual(self.producer.fastLoad(0,11),-1);self.assertEqual(self.producer.fastSkip(0,11),0)
  self.assertEqual(self.producer.run(),self.old);self.assertEqual(self.producer.recording(),1)

class FastIntegratedTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):FastProducerTests.setUpClass.__func__(cls)
 setUp=FastProducerTests.setUp
 pump=warm.WarmProducerTests.pump
 response=warm.WarmProducerTests.response
 data=warm.WarmProducerTests.data
 file=warm.WarmProducerTests.file
 def atomic(self):
  old=self.producer.run();self.background_enabled=False
  self.assertEqual(self.producer.fastLoad(0,11),0)
  self.assertEqual(struct.unpack('<8I',C.string_at(self.producer.request(),32))[4],8)
  self.pump(1);self.assertEqual(self.producer.fastLoad(0,11),1)
  child=self.producer.run();self.assertNotEqual(child,old)
  self.assertEqual(self.producer.commit(),1);self.assertEqual(self.producer.loadRecorded(),1)
  return old,child
 def complete(self):
  self.background_enabled=True;history=[]
  for _ in range(100):
   self.producer.next_frame();self.pump()
   state=[self.arm.fastDiagnostic(i) for i in range(9)]
   if not history or history[-1]!=state:history.append(state)
   if self.response()[4]==4:return
  self.fail(f'child completion remained blocked: response={self.response()} PPCphase={self.producer.phase()} pub={self.producer.publicationPending()} command={self.producer.commandValue()} ending={self.producer.endingValue()} finished={self.producer.finishedForPublication()} history={history}')
 def test_actual_atomic_same_parent_finishes_graph_then_child(self):
  parent,child=self.atomic();self.assertEqual(self.producer.record(11,44,300),1)
  self.assertEqual(self.producer.finishManaged(),1);self.producer.next_frame();self.pump(5)
  self.assertEqual(self.producer.publicationPending(),1);self.assertNotEqual(self.response()[4],4)
  self.complete();self.assertTrue(self.file(parent));data=self.file(child);self.assertTrue(data)
  header=struct.unpack('>16I',data[:64]);self.assertEqual(header[9:15],(0x23,0x50525631,0x42524348,0x12345678,parent,1))
  self.assertTrue(self.data(f'ref_12345678_{child:08X}_464F524B_00000001_00000001.msgb'))
  self.assertEqual(self.producer.branchOwnerHeld(),0);self.assertEqual(self.producer.ready(0),1)
 def test_finished_child_warps_then_remains_saveable_after_durable_map(self):
  parent,child=self.atomic();self.assertEqual(self.producer.record(11,44,300),1)
  self.assertEqual(self.producer.finishManaged(),1);self.producer.next_frame()
  self.assertEqual(self.producer.start(),0);self.producer.stop();self.assertEqual(self.producer.record(12,48,999),0)
  self.complete();self.assertEqual(self.producer.ownsManagedSession(),1);self.assertEqual(self.producer.managedSelection(),1)
  manifest=C.create_string_buffer(256);self.assertEqual(self.producer.exportForSave(manifest),1)
  token=self.producer.selectedToken();self.assertTrue(token);self.assertEqual(self.producer.saveStarted(token),1);self.producer.saveCompleted()
  self.assertTrue(self.file(parent));self.assertTrue(self.file(child));self.assertEqual(self.arm.guards(),1)
 def test_actual_atomic_older_parent_retires_unrelated_current(self):
  parent=self.producer.run();self.producer.abandon();self.pump(30)
  self.assertEqual(self.producer.start(),1);self.pump(4);self.producer.enter();self.pump(16)
  old=self.producer.run();self.assertNotEqual(old,parent);self.assertEqual(self.producer.record(12,48,500),1)
  abandoned,child=self.atomic();self.assertEqual(abandoned,old)
  self.assertEqual(self.producer.record(11,44,300),1);self.assertEqual(self.producer.finishManaged(),1)
  self.complete();self.assertIsNone(self.file(old,'part'));self.assertTrue(self.file(parent));self.assertTrue(self.file(child))

if __name__=='__main__':unittest.main()
