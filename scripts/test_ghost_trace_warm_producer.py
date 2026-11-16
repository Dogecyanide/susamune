"""Run the real central allocator, preparation client and ARM writer across fork cancellation."""
import ctypes as C
from pathlib import Path
import unittest
import test_ghost_trace_producer as producer

ROOT=Path(__file__).resolve().parents[1]
ARM_EXTRA=r'''
__declspec(dllexport) void prepareInputs(const void*q,const void*p){memcpy(&prepareMailbox.request,q,32);memcpy(&prepareMailbox.permit,p,32);}
__declspec(dllexport) const void*prepareResponse(void){return &prepareMailbox.response;}
__declspec(dllexport) unsigned preparePhase(){return WRITER->prepare.phase;}
__declspec(dllexport) unsigned prepareRun(){return WRITER->prepare.request.run;}
__declspec(dllexport) unsigned retiredPhase(){return WRITER->retiring.phase;}
__declspec(dllexport) void backgroundWarm(){if(GhostTraceBackgroundPending())GhostTraceBackgroundService();}
'''
POST_EXTRA=r'''
API const void*prepareRequest(){return &GhostTrace::hostPrepare.request;}
API const void*preparePermit(){return &GhostTrace::hostPrepare.permit;}
API void prepareReceipt(const void*p){memcpy(&GhostTrace::hostPrepare.response,p,32);}
API void grantPreparation(){auto&p=GhostTrace::hostPrepare.permit;p.magic=MS_TRACE_PREPARE_MAGIC;p.version=MS_TRACE_PREPARE_VERSION;p.bootNonce=testNonce;++p.sequence;p.flags=1;p.queued=0;p.reserved=0;}
API unsigned reserved(){return managerRuntime.state.reservedRun;}
API unsigned serial(){return managerRuntime.state.serial;}
API unsigned prepareOperation(){return GhostTrace::hostPrepare.request.operation;}
API unsigned prepareTarget(){return GhostTrace::hostPrepare.request.target;}
API unsigned requestSequence(){return GhostTrace::s.request;}
API unsigned commandValue(){return GhostTrace::s.command;}
API unsigned endingValue(){return GhostTrace::s.ending;}
'''


class WarmProducerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous=(producer.PRE,producer.GLOBALS,producer.POST,producer.ARM,producer.producer_source)
  source=(ROOT/'src/ghost_trace.cpp').read_text(encoding='utf-8')
  producer.PRE=producer.PRE.replace('#include "susamune/ghost_trace.hxx"','#include "susamune/ghost_trace.hxx"\n#include "susamune/ghost_trace_prepare.h"')
  producer.PRE=producer.PRE.replace('unsigned prepareNextRun(unsigned){return 0;}unsigned discardOperation(){return MS_TRACE_DISCARD;}unsigned retainOperation(){return MS_TRACE_KEEP;}bool fastPreparedRun(unsigned){return false;}void revokePreparation(){}','void revokePreparation(){}')
  helper='static MsTracePrepareMailbox hostPrepare;static volatile MsTracePrepareMailbox &prepareBox=hostPrepare;\nstatic unsigned osTicks=100;static unsigned OSGetTick(){return ++osTicks;}\nunsigned captureCapabilities();\n'
  helper+=producer.function(source,'bool prepareResponse(')+producer.function(source,'void prepareRequest(')
  producer.GLOBALS+=helper
  producer.POST=producer.POST.replace('using namespace GhostTrace;s={};','using namespace GhostTrace;hostPrepare={};s={};')+POST_EXTRA
  producer.ARM+=ARM_EXTRA
  original=producer.producer_source
  def with_client():
   code=original();return code.replace('bool recording(){',producer.function(source,'unsigned prepareNextRun(')+producer.function(source,'unsigned discardOperation(')+producer.function(source,'unsigned retainOperation(')+producer.function(source,'bool fastPreparedRun(')+'bool recording(){',1)
  producer.producer_source=with_client
  try:producer.NativeProducerTests.setUpClass.__func__(cls)
  finally:producer.PRE,producer.GLOBALS,producer.POST,producer.ARM,producer.producer_source=previous
  cls.arm.prepareInputs.argtypes=[C.c_void_p,C.c_void_p];cls.arm.prepareResponse.restype=C.c_void_p
  cls.producer.prepareReceipt.argtypes=[C.c_void_p]
  cls.producer.prepareRequest.restype=cls.producer.preparePermit.restype=C.c_void_p
  cls.producer.reserved.restype=cls.arm.prepareRun.restype=C.c_uint
 setUp=producer.NativeProducerTests.setUp
 data=producer.NativeProducerTests.data
 file=producer.NativeProducerTests.file
 response=producer.NativeProducerTests.response
 def pump(self,count=1):
  for _ in range(count):
   self.producer.step();self.producer.grantPreparation()
   self.arm.requests(self.producer.request(),self.producer.branch())
   self.arm.prepareInputs(self.producer.prepareRequest(),self.producer.preparePermit())
   for i in range(2):self.arm.rawChunk(i,self.producer.chunk(i),self.producer.buffer(i))
   self.arm.run(1)
   if getattr(self,"background_enabled",True):self.arm.backgroundWarm()
   self.producer.receipts(self.arm.response(),self.arm.fence(),self.arm.branchResponse())
   self.producer.prepareReceipt(self.arm.prepareResponse());self.producer.step()
 def test_retire_has_one_ack_then_warm_next_start_and_bank_reuse_are_independent(self):
  self.pump(12);self.assertEqual(self.arm.preparePhase(),6)
  old=self.producer.run();self.assertEqual(self.producer.record(1,4,42),1)
  self.background_enabled=False
  self.producer.abandon();self.assertEqual(self.producer.endingValue(),6)
  self.pump(4)
  self.assertEqual(self.response()[4],5);self.assertEqual(self.arm.retiredPhase(),1)
  self.assertEqual(self.producer.commandValue(),6)
  sequence=self.producer.requestSequence();self.pump(5)
  self.assertEqual(self.producer.requestSequence(),sequence)
  self.assertEqual(self.producer.start(),1);self.pump(4);self.producer.enter()
  new=self.producer.run();self.assertNotEqual(new,old)
  self.assertEqual(self.producer.recording(),1);self.assertEqual(self.producer.freshBaselines(),1)
  self.assertEqual(self.producer.record(1,4,100),1)
  self.background_enabled=True;self.pump(18)
  self.assertEqual(self.arm.retiredPhase(),0);self.assertIsNone(self.file(old,'part'))
  self.assertIsNotNone(self.file(new,'part'));self.assertEqual(self.producer.recording(),1)

 def checkpoint(self,slot=0,generation=11):
  self.assertEqual(self.producer.record(10,40,100),1)
  self.assertEqual(self.producer.save(slot,generation),1)

 def older_checkpoint_and_new_run(self):
  self.checkpoint();self.pump(12);parent=self.producer.run()
  self.producer.abandon();self.pump(30);self.assertIn(self.response()[4],(4,5))
  source=self.file(parent);self.assertTrue(source)
  self.assertEqual(self.producer.start(),1);self.pump(4);self.producer.enter();self.pump(12)
  current=self.producer.run();self.assertNotEqual(current,parent)
  self.assertEqual(self.producer.record(11,44,200),1)
  return parent,current,source

 def finish_load(self,slot=0,generation=11):
  for _ in range(80):
   result=self.producer.load(slot,generation)
   if result:
    self.assertEqual(result,1);return
   self.pump()
  self.fail('continuation did not settle')

 def test_same_parent_ram_load_keeps_its_durable_source(self):
  self.checkpoint();self.pump(12);parent=self.producer.run()
  self.assertEqual(self.producer.ready(0),1)
  self.assertEqual(self.producer.load(0,11),0)
  self.assertEqual(self.producer.endingValue(),2)
  self.finish_load();self.assertTrue(self.file(parent))
  self.assertEqual(self.producer.commit(),1)

 def test_loading_older_checkpoint_retires_unrelated_unpinned_tail(self):
  parent,tail,source=self.older_checkpoint_and_new_run()
  self.background_enabled=False
  self.assertEqual(self.producer.load(0,11),0)
  self.assertEqual(self.producer.endingValue(),6)
  self.finish_load();self.assertEqual(self.file(parent),source)
  self.assertEqual(self.arm.retiredPhase(),1)
  self.assertEqual(self.producer.commit(),1)
  self.background_enabled=True;self.pump(18)
  self.assertEqual(self.arm.retiredPhase(),0);self.assertIsNone(self.file(tail,'part'))
  self.assertEqual(self.file(parent),source)
  self.assertEqual(self.producer.record(11,44,300),1)

 def test_loading_older_checkpoint_keeps_another_durable_ram_pin(self):
  parent,current,source=self.older_checkpoint_and_new_run()
  self.checkpoint(1,22);self.pump(12)
  self.assertEqual(self.producer.ready(1),1)
  self.assertEqual(self.producer.load(0,11),0)
  self.assertEqual(self.producer.endingValue(),2)
  self.finish_load();self.assertTrue(self.file(current))
  self.assertEqual(self.file(parent),source);self.assertEqual(self.producer.ready(1),1)

 def test_loading_older_checkpoint_keeps_pending_current_fence(self):
  parent,current,source=self.older_checkpoint_and_new_run()
  self.checkpoint(1,22);self.assertEqual(self.producer.ready(1),0)
  self.assertEqual(self.producer.load(0,11),0)
  self.assertEqual(self.producer.endingValue(),2)
  self.finish_load();self.assertTrue(self.file(current))
  self.assertEqual(self.file(parent),source);self.assertEqual(self.producer.ready(1),1)

 def test_canceling_fork_before_child_start_retires_abandoned_warm_id_and_prepares_next(self):
  self.pump(12)
  self.assertEqual((self.arm.preparePhase(),self.arm.prepareRun(),self.producer.reserved()),(6,0x80000002,0x80000002))
  source=self.producer.run();serial=self.producer.serial()
  self.assertEqual(self.producer.record(10,40,100),1);self.assertEqual(self.producer.save(0,11),1)
  self.assertEqual(self.producer.load(0,11),0);self.assertEqual(self.producer.phase(),1)
  self.assertEqual(self.producer.reserved(),0)
  self.producer.cancel();self.assertEqual(self.producer.phase(),0)
  saw_cancel=False
  for _ in range(32):
   self.pump()
   if self.producer.prepareOperation()==3:saw_cancel=True;self.assertNotEqual(self.producer.prepareTarget(),0)
   if self.arm.preparePhase()==6 and self.arm.prepareRun()==0x80000003:break
  self.assertTrue(saw_cancel)
  self.assertEqual((self.arm.preparePhase(),self.arm.prepareRun(),self.producer.reserved()),(6,0x80000003,0x80000003))
  self.assertEqual(self.producer.run(),source);self.assertEqual(self.producer.recording(),1)
  self.assertEqual(self.producer.serial(),serial)
  self.assertEqual(len(self.file(0x80000002,'part')),64)
  self.assertIsNotNone(self.file(source,'part'))


if __name__=='__main__':unittest.main()
