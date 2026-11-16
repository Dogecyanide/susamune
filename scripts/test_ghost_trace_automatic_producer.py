"""Exercise an automatic retail stage setup with the actual PPC producer and ARM writer."""
import ctypes as C
from pathlib import Path
import struct
import unittest

import test_ghost_trace_producer as producer
import test_ghost_trace_warm_producer as warm

ROOT=Path(__file__).resolve().parents[1]
SETUP_STUBS=r"""
static unsigned testRevision=0,testPollutionPhase=8;
struct JKRSolidHeap {const void *mStart,*mEnd;unsigned _6C,_70,_68;};
struct TFlagManager {unsigned char flags[0x380];static TFlagManager *smInstance;};
static TFlagManager testFlags;
TFlagManager *TFlagManager::smInstance=&testFlags;
namespace GhostWorldRuntime {bool hooksActive(){return false;}}
namespace GhostTraceHooks {bool setActive(bool){return true;}}
namespace GhostSimulation {void capture(Snapshot&settings){std::memset(&settings,0x2a,sizeof(settings));}}
static unsigned VIGetTvFormat(){return 0;}
"""
SETUP_EXPORTS=r"""
API int armAuto(unsigned scene,unsigned run){return GhostTrace::armAutomaticStage(scene,run);}
API int pendingAuto(){return GhostTrace::automaticStartPending();}
API void actualSetup(unsigned scene,unsigned generation){GhostTrace::stageSetup(scene>>8,scene&255,generation);}
API int autoFailure(unsigned run){return GhostTrace::failure(run);}
API int retained(unsigned run){return GhostTrace::retainedFile(run);}
API int autoDiscarded(unsigned run){return GhostTrace::discarded(run);}
API int explicitStart(unsigned scene,unsigned run){return GhostTrace::armOrdinaryStage(scene,run);}
"""


class AutomaticProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous=(producer.PRE,producer.GLOBALS,producer.POST,producer.producer_source,warm.ROOT)
        source=(ROOT/'src/ghost_trace.cpp').read_text(encoding='utf-8')
        stage_setup=producer.function(source,'void stageSetup(')
        for address,name in (
            ('SUSAMUNE_ADDR_LIBC_RAND_SEED','testSeed'),('0x80000000u','testGame'),
            ('0x80000004u','testRevision'),('SUSAMUNE_ADDR_NPC_POLLUTION_PHASE','testPollutionPhase'),
        ):
            stage_setup=stage_setup.replace(f'*reinterpret_cast<volatile const unsigned*>({address})',name)
        for field in ('mStart','mEnd'):
            stage_setup=stage_setup.replace(
                f'reinterpret_cast<unsigned>(heap->{field})',
                f'static_cast<unsigned>(reinterpret_cast<__UINTPTR_TYPE__>(heap->{field}))',
            )
        producer.PRE=producer.PRE.replace(
            'unsigned char mAreaID,mEpisodeID;}mCurrentScene;}gpApplication={{2,0}};',
            'unsigned char mAreaID,mEpisodeID,pad[2];}mCurrentScene,mPrevScene,mNextScene;'
            'void *mCurrentHeap;unsigned mCutSceneID;}gpApplication={{2,0}};'+SETUP_STUBS,
        )
        # The stand-ins above add to GhostSimulation after its Snapshot declaration.
        stub='namespace GhostSimulation {void capture(Snapshot&settings){std::memset(&settings,0x2a,sizeof(settings));}}'
        producer.PRE=producer.PRE.replace(stub,'').replace(
            'struct Snapshot{unsigned char bytes[64];};}', 'struct Snapshot{unsigned char bytes[64];};}'+stub,
        )
        producer.GLOBALS+='static bool readable(const void*p,unsigned){return p==TFlagManager::smInstance;}\n'
        producer.POST+=SETUP_EXPORTS
        original=producer.producer_source
        producer.producer_source=lambda:original().replace(
            'bool armAutomaticStage(',stage_setup+'bool armAutomaticStage(',1,
        )
        warm.ROOT=ROOT
        try:
            warm.WarmProducerTests.setUpClass.__func__(cls)
        finally:
            producer.PRE,producer.GLOBALS,producer.POST,producer.producer_source,warm.ROOT=previous

    pump=warm.WarmProducerTests.pump
    file=producer.NativeProducerTests.file
    data=producer.NativeProducerTests.data
    records=producer.NativeProducerTests.records

    def setUp(self):
        self.arm.identity(0x474d534a,0x12345678)
        self.arm.reset()
        self.assertEqual(self.producer.resetAt(0x12345678),1)
        self.pump(12)
        self.run_id=self.producer.reserved()
        self.assertNotEqual(self.run_id,0)
        self.assertEqual((self.arm.preparePhase(),self.arm.prepareRun()),(6,self.run_id))

    def fake_reply(self,sequence,phase,error=0,chunk=0,nonce=0x12345678):
        response=C.create_string_buffer(C.string_at(self.arm.response(),64))
        struct.pack_into('<5I',response,8,nonce,sequence,phase,error,chunk)
        self.producer.receipts(response,self.arm.fence(),self.arm.branchResponse())

    def arm_and_enter(self):
        self.assertEqual(self.producer.armAuto(0x203,self.run_id),1)
        self.assertEqual(self.producer.pendingAuto(),1)
        self.assertEqual(self.producer.recording(),0)
        self.producer.actualSetup(0x203,42)
        self.assertEqual(self.producer.recording(),1)

    def test_matching_stage_setup_survives_stale_ack_and_is_saved(self):
        self.fake_reply(0,4,chunk=9)
        self.arm_and_enter()
        self.assertEqual(self.producer.retained(self.run_id),0)
        self.assertEqual(self.producer.finish(),0)
        self.assertEqual(self.producer.bulk(1,3100),1)
        self.producer.background()
        self.assertEqual(self.producer.sealed(0),1)
        size=self.producer.queued(0)
        self.assertGreater(size,0x20000)
        self.assertEqual(C.string_at(self.producer.chunk(0),32),bytes(32))
        self.assertEqual(self.producer.queued(0),size)
        self.assertEqual(self.producer.pendingAuto(),1)
        self.pump(2)
        self.assertEqual(self.producer.pendingAuto(),0)
        self.assertEqual(self.producer.recording(),1)
        self.assertEqual(self.producer.finish(),1)
        self.pump(20)
        rows=self.records(self.file(self.run_id))
        self.assertEqual([r[0] for r in rows[:3]],[1,22,2])
        self.assertEqual(struct.unpack_from('<3I',rows[1][3]),(3,5,0x203))
        self.assertEqual(struct.unpack_from('<I',rows[1][3],28),(42,))

    def test_refused_start_cannot_claim_a_previous_saved_writer(self):
        self.arm_and_enter()
        sequence=self.producer.requestSequence()
        self.fake_reply(sequence,4,error=8,chunk=9)
        self.producer.step()
        self.assertEqual(self.producer.pendingAuto(),0)
        self.assertEqual(self.producer.recording(),0)
        self.assertEqual(self.producer.autoFailure(self.run_id),8)
        self.assertEqual(self.producer.retained(self.run_id),0)
        self.assertEqual(self.producer.autoDiscarded(self.run_id),1)
        self.assertEqual(self.producer.queued(0),0)
        self.producer.stop()
        self.producer.step()
        self.assertEqual(self.producer.requestSequence(),sequence)
        self.assertEqual(self.producer.commandValue(),0)

    def test_cancel_waits_for_matching_ack_then_retires_empty_start(self):
        self.arm_and_enter()
        sequence=self.producer.requestSequence()
        self.producer.stop()
        self.producer.step()
        self.assertEqual(self.producer.requestSequence(),sequence)
        self.assertEqual(self.producer.pendingAuto(),1)
        self.assertEqual(C.string_at(self.producer.chunk(0),32),bytes(32))
        self.pump(20)
        self.assertEqual(self.producer.pendingAuto(),0)
        self.assertEqual(self.producer.autoDiscarded(self.run_id),1)
        self.assertIsNone(self.file(self.run_id,'part'))
        self.assertIsNone(self.file(self.run_id))

    def test_wrong_boot_reply_cannot_publish_speculative_stage_records(self):
        self.arm_and_enter()
        sequence=self.producer.requestSequence()
        self.fake_reply(sequence,2,nonce=0x12345679)
        self.producer.step()
        self.assertEqual(self.producer.pendingAuto(),1)
        self.assertEqual(self.producer.recording(),0)
        self.assertEqual(self.producer.autoFailure(self.run_id),3)
        self.assertEqual(self.producer.requestSequence(),sequence)
        self.assertEqual(C.string_at(self.producer.chunk(0),32),bytes(32))
        self.pump(20)
        self.assertEqual(self.producer.autoDiscarded(self.run_id),1)
        self.assertIsNone(self.file(self.run_id))

    def test_automatic_requires_exact_warm_file_and_explicit_remains_strict(self):
        self.assertEqual(self.producer.armAuto(0x203,self.run_id+1),0)
        self.assertEqual(self.producer.requestSequence(),0)
        self.assertEqual(self.producer.explicitStart(0x203,self.run_id),1)
        self.assertEqual(self.producer.pendingAuto(),0)
        self.producer.actualSetup(0x203,42)
        self.assertEqual(self.producer.recording(),0)
        self.assertEqual(self.producer.autoFailure(self.run_id),3)
        self.assertEqual(self.producer.queued(0),0)


if __name__=='__main__':
    unittest.main()
