"""Run the production coordinator with each real worker and a bounded peer."""
import ctypes as C
from pathlib import Path
import re
import struct
import unittest

import test_ghost_kernel_paging as ghost
import test_state_storage_kernel as state
from test_timewarp_transfer_lease import Control, Line

ROOT = Path(__file__).resolve().parents[1]
ABI = 0x10002


def declarations(path):
    return re.sub(r'^#(?:include|ifndef|define|endif).*$', '', path.read_text(), flags=re.M)


def fixture(text):
    return '#define TEST_TRANSFER_EXTERNAL\n' + text + '\n#include "susamune/transfer_layout.h"\n' + \
        declarations(ROOT/'launcher/kernel/SusamuneTransfer.h') + r'''
static TWLeaseControl testTransfer __attribute__((aligned(32)));
#define TRANSFER_WIRE (&testTransfer)
'''


def bridge(real):
    peer = 'SusamuneStateStorage' if real == 'ghost' else 'SusamuneGhost'
    arity = 'u32 seq,u32 session,u32 command' if real == 'ghost' else 'u32 seq,u32 command'
    ignore = '(void)seq;(void)command;' + ('(void)session;' if real == 'ghost' else '')
    mock = r'''
static u32 peerBusy,peerFailed,peerCalls;
static u32 diBlocked,diReservations;
bool DIReserveScratchTail(void){++diReservations;return !diBlocked;}
void PEERInit(void){peerBusy=0;}
bool PEERQuiescent(void){return !peerBusy&&!peerFailed;}
bool PEERRetireFailed(void){return peerFailed;}
bool PEERRetire(void){if(peerBusy)--peerBusy;return PEERQuiescent();}
void PEERService(void){++peerCalls;}
bool PEERRequestReady(ARITY){IGNORE return false;}
bool PEERReceiptReady(ARITY){IGNORE return false;}
'''.replace('PEER', peer).replace('ARITY', arity).replace('IGNORE', ignore)
    source = re.sub(r'^#include .*$', '', (ROOT/'launcher/kernel/SusamuneTransfer.c').read_text(), flags=re.M)
    source = source.replace('u8 *SusamuneTransferGhostBase(void)', 'u8 *LogicalGhostBase(void)')
    source = source.replace('u8 *SusamuneTransferStageBase(void)', 'u8 *LogicalStageBase(void)')
    source = source.replace('u8 *SusamuneTransferPoolPiece(u32 offset, u32 *size)', 'u8 *LogicalPoolPiece(u32 offset, u32 *size)')
    if real == 'ghost':
        memory = r'''
static u8 sharedStage[SUSAMUNE_TRANSFER_STAGE_SIZE+64];
u8 *SusamuneTransferStageBase(void){return sharedStage+32;}
u8 *SusamuneTransferGhostBase(void){return SharedMap?sharedStage+32:testPayload;}
u8 *SusamuneTransferPoolPiece(u32 offset,u32 *size){return LogicalPoolPiece(offset,size);}
'''
        reset = 'IoFileOpen=ImportDirOpen=false;'
        tail = ''
    else:
        memory = r'''
static u8 fifthPool[SUSAMUNE_TRANSFER_POOL_FIFTH_SIZE] __attribute__((aligned(32)));
u8 *SusamuneTransferStageBase(void){return STATE_STAGING;}
u8 *SusamuneTransferGhostBase(void){return SharedMap?STATE_STAGING:testPayload;}
u8 *SusamuneTransferPoolPiece(u32 offset,u32 *size){
 u32 p=(u32)(__UINTPTR_TYPE__)LogicalPoolPiece(offset,size);
 if(!*size)return 0;
 if(p>=SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE&&p<SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE+SUSAMUNE_STATE_POOL_SIZE)
  return STATE_POOL+p-SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE;
 if(p>=SUSAMUNE_STATE_POOL_EXTRA_PHYS_BASE&&p<SUSAMUNE_STATE_POOL_EXTRA_PHYS_BASE+SUSAMUNE_STATE_POOL_EXTRA_SIZE)
  return STATE_POOL_EXTRA+p-SUSAMUNE_STATE_POOL_EXTRA_PHYS_BASE;
 if(p>=SUSAMUNE_TRANSFER_POOL_THIRD_PHYS_BASE&&p<NIN_MEM2_DI_SCRATCH_PHYS_BASE)
  return STATE_STAGING+SUSAMUNE_TRANSFER_STAGE_SIZE+p-SUSAMUNE_TRANSFER_POOL_THIRD_PHYS_BASE;
 if(p>=SUSAMUNE_TRANSFER_POOL_FIFTH_PHYS_BASE&&p<NIN_MEM2_LOADER_DISC_PHYS_BASE)
  return fifthPool+p-SUSAMUNE_TRANSFER_POOL_FIFTH_PHYS_BASE;
 return testPayload+p-SUSAMUNE_TRANSFER_POOL_FOURTH_PHYS_BASE;
}
'''
        reset = 'FileOpen=DirOpen=false;'
        tail = r'''
__declspec(dllexport) u32 thirdWord(void){return *(u32*)(STATE_STAGING+SUSAMUNE_TRANSFER_STAGE_SIZE);}
__declspec(dllexport) u32 fourthWord(void){return *(u32*)testPayload;}
__declspec(dllexport) const void *poolPointer(u32 offset){u32 size=1;return SusamuneTransferPoolPiece(offset,&size);}
'''
    return '#include "susamune/transfer_publication.h"\n' + mock + source + memory + r'''
static TWLeasePublisher peerPublisher;
__declspec(dllexport) void coldBoot(void){
 Mode=0;SharedMap=Dispatching=false;ActivationMask=0;
 memset(&Arm,0,sizeof(Arm));memset(&Control,0,sizeof(Control));
 memset(&Publisher,0,sizeof(Publisher));memset(&peerPublisher,0,sizeof(peerPublisher));
 peerBusy=peerFailed=peerCalls=diBlocked=diReservations=0;Retiring=CloseFailed=false;Phase=0;
 RESET_HANDLES
 reset();SusamuneTransferInit();
}
__declspec(dllexport) const void *wire(void){return &testTransfer;}
__declspec(dllexport) u32 publish(const TWLeaseLine *line){return TWLeasePublicationWrite(&peerPublisher,
 &testTransfer.request,&testTransfer.requestPublication,line,&PublicationIo);}
__declspec(dllexport) u32 pump(u32 count){
 u32 passes=0;while(count--&&SusamuneTransferPending()){SusamuneTransferService();++passes;}return passes;
}
__declspec(dllexport) u32 active(void){return SusamuneTransferActive();}
__declspec(dllexport) u32 stageBytes(void){return SusamuneTransferStageSize();}
__declspec(dllexport) u32 poolBytes(void){return SusamuneTransferPoolSize();}
__declspec(dllexport) u32 stageAddress(void){return (u32)(__UINTPTR_TYPE__)LogicalStageBase();}
__declspec(dllexport) u32 ghostAddress(void){return (u32)(__UINTPTR_TYPE__)LogicalGhostBase();}
__declspec(dllexport) u32 piece(u32 offset,u32 *size){return (u32)(__UINTPTR_TYPE__)LogicalPoolPiece(offset,size);}
__declspec(dllexport) void busyPeer(u32 value){peerBusy=value;}
__declspec(dllexport) void blockDi(u32 value){diBlocked=value;}
__declspec(dllexport) u32 reservations(void){return diReservations;}
__declspec(dllexport) void failedPeer(u32 value){peerFailed=value;}
__declspec(dllexport) u32 peerServices(void){return peerCalls;}
__declspec(dllexport) u32 workerPending(void){return REALPending();}
__declspec(dllexport) void workerService(void){REALService();}
__declspec(dllexport) void beginRetire(void){SusamuneTransferBeginRetire();}
__declspec(dllexport) u32 retireStep(void){return SusamuneTransferRetireStep();}
__declspec(dllexport) u32 retireFailed(void){return SusamuneTransferRetireFailed();}
__declspec(dllexport) u32 resumeLegacy(void){return SusamuneTransferResumeLegacy();}
__declspec(dllexport) u32 workerPhase(void){return Phase;}
'''.replace('RESET_HANDLES', reset).replace('REAL', 'SusamuneGhost' if real == 'ghost' else 'SusamuneStateStorage') + tail


class CoordinatorChecks:
    fixture_transform = staticmethod(fixture)

    def setup_coordinator(self):
        self.lib.wire.restype = C.c_void_p
        self.lib.publish.argtypes = [C.POINTER(Line)]
        self.lib.piece.argtypes = [C.c_uint, C.POINTER(C.c_uint)]
        self.lib.piece.restype = C.c_uint
        self.lib.coldBoot()
        self.buffers = []
        self.ticket = 0

    def wire(self):
        return Control.from_buffer_copy(C.string_at(self.lib.wire(), C.sizeof(Control)))

    def activate(self):
        line = self.wire().response
        self.assertEqual((line.phase, line.command), (1, ABI))
        line.phase = 2
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.assertEqual(self.lib.pump(100), 3)
        self.assertTrue(self.lib.active())
        self.assertEqual(self.wire().response.phase, 3)

    def remote(self, owner, seq, command, session=0, phase=5):
        self.ticket += 1
        line = Line(0x534c5331, self.wire().response.epoch, self.ticket, owner, phase, seq, session, command)
        self.assertTrue(self.lib.publish(C.byref(line)))

    def test_explicit_abi_and_complete_activation_are_required(self):
        self.assertFalse(self.lib.active())
        self.assertEqual((self.lib.stageBytes(), self.lib.poolBytes(), self.lib.ghostAddress()),
                         (0x400000, 0x11f0000, 0x11cff000))
        line = self.wire().response
        line.phase = 2; line.command = ABI + 1
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.assertEqual(self.lib.pump(10), 0)
        self.lib.busyPeer(2)
        line.command = ABI
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.lib.pump(1)
        self.assertFalse(self.lib.active())
        self.assertEqual(self.lib.stageBytes(), 0x400000)
        self.lib.pump(10)
        self.assertTrue(self.lib.active())
        self.assertEqual((self.lib.stageBytes(), self.lib.poolBytes(), self.lib.ghostAddress()),
                         (0x13e000, 0x1660000, 0x11300000))

    def test_five_banks_exclude_live_di_prefix_and_reset_returns_to_legacy(self):
        self.activate()
        offset = 0
        for base, capacity in ((0x11f00000,0xff0000), (0x1193f000,0x200000),
                               (0x1143e000,0x2c2000), (0x11cff000,0x13e000),
                               (0x11710000,0x70000)):
            size = C.c_uint(0xffffffff)
            self.assertEqual(self.lib.piece(offset, C.byref(size)), base)
            self.assertEqual(size.value, capacity)
            offset += capacity
        size = C.c_uint(1)
        self.assertEqual(self.lib.piece(offset, C.byref(size)), 0)
        self.assertEqual(size.value, 0)
        epoch = self.wire().response.epoch
        self.lib.beginRetire(); self.lib.beginRetire()
        self.assertFalse(self.lib.resumeLegacy())
        for _ in range(4):
            if self.lib.retireStep(): break
        self.assertTrue(self.lib.resumeLegacy())
        self.assertFalse(self.lib.active())
        self.assertEqual(self.wire().response.epoch, epoch+1)
        self.assertEqual(self.wire().response.phase, 1)
        self.assertEqual((self.lib.stageBytes(), self.lib.poolBytes()), (0x400000,0x11f0000))

        # A request still present in the parked PPC's old cache cannot activate.
        old = Line(0x534c5331, epoch, 0, 0, 2, 0, 0, ABI)
        self.assertTrue(self.lib.publish(C.byref(old)))
        self.assertEqual(self.lib.pump(10), 0)
        self.assertFalse(self.lib.active())
        self.activate()

    def test_di_fence_failure_keeps_all_reclaimed_ranges_unpublished(self):
        self.lib.blockDi(1)
        line = self.wire().response
        line.phase = 2
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.lib.pump(5)
        self.assertFalse(self.lib.active())
        self.assertEqual(self.wire().response.phase, 1)
        self.assertEqual((self.lib.stageBytes(), self.lib.poolBytes()), (0x400000, 0x11f0000))
        self.assertGreater(self.lib.reservations(), 0)
        self.lib.blockDi(0)
        self.lib.pump(1)
        self.assertTrue(self.lib.active())
        self.assertEqual(self.wire().response.phase, 3)

    def test_close_failure_cannot_activate_or_resume(self):
        self.activate()
        self.lib.failedPeer(1)
        self.lib.beginRetire()
        self.assertTrue(self.lib.retireFailed())
        self.assertFalse(self.lib.retireStep())
        self.assertFalse(self.lib.resumeLegacy())
        self.assertEqual(self.wire().response.phase, 8)


class GhostCoordinatorTests(CoordinatorChecks, unittest.TestCase):
    bridge_source = bridge('ghost')
    setUpClass = classmethod(ghost.GhostKernelPagingTests.setUpClass.__func__)

    def setUp(self):
        self.lib = self.dll
        self.setup_coordinator()

    def test_actual_worker_pending_and_service_obey_owner_ticket(self):
        self.activate()
        self.dll.submit(4,0,0,b'',0,0)
        self.assertFalse(self.lib.workerPending())
        self.lib.workerService()
        self.assertEqual(self.lib.workerPhase(), 0)
        self.remote(2,1,4,session=9)
        self.assertEqual(self.lib.pump(4), 0)
        self.assertFalse(self.lib.workerPending())
        self.remote(1,1,4)
        self.assertGreater(self.lib.pump(100), 0)
        self.assertEqual(self.wire().response.phase, 7)
        self.assertEqual(self.wire().response.owner, 1)
        self.assertEqual(self.lib.peerServices(), 0)
        self.assertEqual(self.lib.pump(10), 0)

    def test_done_requires_both_workers_quiet_after_real_receipt(self):
        self.activate()
        self.dll.submit(4,0,0,b'',0,0)
        self.remote(1,1,4)
        self.lib.pump(1)
        self.lib.busyPeer(1)
        self.lib.pump(100)
        self.assertNotEqual(self.wire().response.phase, 7)
        self.assertEqual(self.lib.workerPhase(), 0)
        self.lib.busyPeer(0)
        self.lib.pump(1)
        self.assertEqual(self.wire().response.phase, 7)

    def test_withdrawn_publication_cannot_dispatch_a_matching_doorbell(self):
        self.activate()
        self.dll.submit(4,0,0,b'',0,0)
        self.remote(1,1,4)
        wire = Control.from_address(self.lib.wire())
        generation = wire.requestPublication.generation
        wire.requestPublication.generation = 0
        self.assertEqual(self.lib.pump(10), 0)
        self.assertFalse(self.lib.workerPending())
        self.lib.workerService()
        self.assertEqual(self.lib.workerPhase(), 0)
        wire.requestPublication.generation = generation
        self.assertGreater(self.lib.pump(100), 0)
        self.assertEqual(self.wire().response.phase, 7)


class StateCoordinatorTests(CoordinatorChecks, unittest.TestCase):
    bridge_source = bridge('state')
    setUpClass = classmethod(state.StateStorageKernelTests.setUpClass.__func__)
    buffer = state.StateStorageKernelTests.buffer

    def setUp(self):
        self.setup_coordinator()

    def test_real_export_uses_reclaimed_banks_and_completes_after_receipt(self):
        self.activate()
        for offset in (0x11f0000,0x14b2000,0x15f0000):
            data, meta = b'new bank payload'*2000, b'metadata'
            self.lib.prepare(self.buffer(data),len(data),offset,self.buffer(meta),len(meta))
            self.lib.submit(1,0,offset,len(data),0,11)
            seq = C.c_uint.from_address(self.lib.mailbox()).value
            self.lib.workerService()
            self.assertEqual(self.lib.workerPhase(),0)
            self.remote(2,seq,1,11)
            self.assertGreater(self.lib.pump(100),0)
            self.assertEqual(self.wire().response.phase,7)
            self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,0)
            result = C.c_uint.from_address(self.lib.mailbox()+48).value
            length = C.c_uint()
            p=self.lib.file(f'/Moonshine data/states/state_{result:08d}.mss'.encode(),C.byref(length))
            self.assertEqual(C.string_at(p,length.value)[96+len(meta):],data)

    def test_cancellation_and_retirement_keep_the_accepted_operation_owned(self):
        self.activate()
        data,meta=b'pending export'*3000,b'meta'
        self.lib.prepare(self.buffer(data),len(data),32,self.buffer(meta),len(meta))
        self.lib.submit(1,0,32,len(data),0,11)
        self.remote(2,1,1,11)
        self.lib.pump(2)
        line=self.wire().request;line.phase=6
        self.assertTrue(self.lib.publish(C.byref(line)))
        self.lib.pump(100)
        self.assertEqual(self.wire().response.phase,7)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,6)
        self.lib.submit(1,0,32,len(data),0,11)
        self.remote(2,2,1,11)
        self.lib.pump(2)
        self.lib.beginRetire()
        for _ in range(100):
            if self.lib.retireStep():break
        else:self.fail('Retirement failed to finish export')
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,0)
        self.assertTrue(self.lib.resumeLegacy())
        self.assertEqual(self.wire().response.phase,1)

    def test_import_splits_at_shared_stage_and_each_reclaimed_bank_boundary(self):
        self.activate()
        self.lib.poolPointer.restype = C.c_void_p
        stage = self.lib.stageBytes()
        data = (bytes(range(251))*((stage+4567)//251+1))[:stage+4567]
        meta = b'metadata remains in its own mailbox'
        self.lib.prepare(self.buffer(data),len(data),32,self.buffer(meta),len(meta))
        self.lib.submit(state.EXPORT,0,32,len(data),0,11)
        self.remote(2,1,state.EXPORT,11)
        self.lib.pump(5000)
        length = C.c_uint()
        file = self.lib.file(b'/Moonshine data/states/state_00000001.mss',C.byref(length))
        archive = C.string_at(file,length.value)
        header = state.Header.from_buffer_copy(archive)
        self.assertEqual(archive[96+len(meta):],data)

        for seq, boundary in enumerate((0x14b2000, 0x15f0000), 2):
            offset = boundary-123
            before = self.lib.poolPointer(offset)
            after = self.lib.poolPointer(boundary)
            C.memset(self.lib.staging(),0xA5,stage)
            C.memset(before-16,0x91,123+16)
            C.memset(after,0xE7,4567-123+16)
            self.lib.submit(state.IMPORT,1,offset,len(data),header.headerCrc,11)
            self.remote(2,seq,state.IMPORT,11)
            self.lib.pump(5000)
            self.assertEqual(self.wire().response.phase,7)
            self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,state.OK)
            self.assertEqual(C.string_at(self.lib.staging(),stage),data[:stage])
            self.assertEqual(C.string_at(before,123),data[stage:stage+123])
            self.assertEqual(C.string_at(after,4567-123),data[stage+123:])
            self.assertEqual(C.string_at(before-16,16),b'\x91'*16)
            self.assertEqual(C.string_at(after+4567-123,16),b'\xE7'*16)
            self.assertTrue(self.lib.guards())

    def test_cancel_before_dispatch_preserves_window_and_never_opens_file(self):
        self.activate()
        before = C.string_at(self.lib.staging(),64)
        self.lib.submit(state.WINDOW,1,0,12345,0,11)
        self.lib.windowSize(64)
        self.remote(2,1,state.WINDOW,11,phase=6)
        self.lib.pump(100)
        self.assertEqual(self.wire().response.phase,7)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+44).value,state.CANCELLED)
        self.assertEqual((self.lib.reads(),self.lib.writes()),(0,0))
        self.assertEqual(C.string_at(self.lib.staging(),64),before)


if __name__ == '__main__':
    unittest.main()
