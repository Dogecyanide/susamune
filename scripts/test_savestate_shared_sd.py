"""Real shared SD manager lifecycle; async transport and game admission are bounded fakes."""
import ctypes as C
from pathlib import Path
import random
import tempfile
import unittest
import zlib

from mod_transport import encode_quick
from test_practice_tape import function_source
from test_state_codec import Guarded, Result
from test_state_store import StoreCodec, StorePool, Identity
from test_timewarp_staged_transaction import StageHarness

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/savestate.cpp'

FIXTURE = r'''
#include "susamune/state_storage.h"
#include "susamune/state_pool_memory.h"
#include "susamune/state_import.hxx"
typedef unsigned int u32; typedef unsigned char u8; typedef long long OSTime;
namespace PracticeSession {struct SavestateData{u32 flags,stateKey[2],originKey[2],frames;};}
struct Header {u32 magic;u8 area_id,episode_id,pad[2];};
struct StoredState {Header header;u8 sidecars[128];PracticeSession::SavestateData practice;
 u32 archiveProfile,generation,rawSize,packedSize,adler32,parentEpisode,metadataTag;};
struct SavestateManager {
 enum{kSlotCount=3};bool mLoadPending;u32 mLoadWaitFrames;
 struct TransferResult{u32 command,status,id,slot,generation;SusamuneStateArchiveHeader header;};
 static bool diskBusy();void updateDisk();bool cancelSD();
 bool beginSDLoad(u32,u32,u32,bool,u32,const SusamuneTasRequest*);
 bool beginSDExport(u32,u32,const char*,const SusamuneTasRequest*);
};
static SavestateManager manager;
static StateStore::Store *testStore;
#define sSharedStore (*testStore)
static StateSlotPool sPool;
static StatePoolMemory sPoolMemory;
static StoredState sSlots[3],sCandidate,returned,originalMetadata;
static u32 sPackedChecksums[3],sNextGeneration,sDurableSlots,sActiveSlot,sLoadSlot;
static u32 sDiskSlot,sDiskGeneration,sDiskPoolUsed,sDiskScene,sDiskRootPin;
static u32 sPendingSlot,sPendingGeneration,sStreamId,sStreamOffset,sStreamSize,sStreamSeen,sStreamCrc,sStreamChecksums[8];
static bool sSharedReady,sBusy,sAwaitingLoadApproval,sDiskActive,sDiskRestore,sDiskLoadReady;
static bool sDiskChunkImport,sDiskNextWindow,sDiskCancelRequested,sDiskStream,sDiskRecovered,sStreamCommit;
static bool sExplicitTransfer,sTransferReady;
static SavestateManager::TransferResult sTransferResult;
static StateImport::Cursor sDiskImport;
static SusamuneTasRequest sDiskProject;
static SusamuneStateArchiveHeader sStreamHeader,fileHeader;
static SusamuneStateCatalogEntry sSelectedSD;
static u32 sProjectStartKey[2],sProjectRole,sProjectFrames;
static OSTime sDiskStarted;
static const char*sDiskStatus;
static void*work;static u8*windowBytes;static u8*stageBytes;
static const u8*archiveBytes;static u32 archiveSize,scene,terminalStatus,notices,cleared,rebased,errors;
static bool candidateAllowed,muted,interrupts,sealedCommitRefused;
static const u32 kSnapshotMagic=0x53555341,kSnapshotVersion=17;
static int snprintf(char*d,__SIZE_TYPE__ n,const char*,...){if(n)*d=0;return 0;}
extern "C" char*strncpy(char*d,const char*s,__SIZE_TYPE__ n){char*r=d;while(n--)*d++=*s?*s++:0;return r;}
namespace TransferLease{bool sharedMap(){return true;}}
namespace PracticeSession {
 static bool projectSavestateMatches(const SavestateData&p,const u32*k,u32 role,u32 frames){
  return p.flags==7&&p.originKey[0]==k[0]&&p.originKey[1]==k[1]&&p.frames==frames&&role==1;}
 static void onSavestateCleared(u32,u32){++cleared;}static void cancelLoadHold(){}
}
namespace StateArchiveProfile {static bool valid(u32 n){return n==71;}static bool reidentify(u32&n,u32){return valid(n);}}
struct Menu{void toast(const char*){++notices;}}menu;static Menu*gMenu=&menu;
static void*codecWorkspace(){return work;}
static u32 poolCapacity(){return TWBankCapacity(sSharedStore.memory->pool);}
static u32 archiveSceneKey(){return scene;}
static u32 archiveGameId(){return 0x474d5350;}
static u32 archiveBuildId(){return 712;}
static bool admitArchiveStage(bool=false){return true;}
static OSTime OSGetTime(){return 27;}
static void GXDrawDone(){}
static bool OSDisableInterrupts(){interrupts=true;return true;}
static void OSRestoreInterrupts(bool){interrupts=false;}
static bool muteAudioDma(){muted=true;return true;}
static void unmuteAudioDma(bool){muted=false;}
static void rebaseMissionStopwatch(OSTime){++rebased;}
static const char*archiveStatusText(u32 n){terminalStatus=n;return "refused";}
static void poolReadSpans(u32,u32,StateCodec::ReadSpan*){++errors;}
static u32 metadataTag(const StoredState&);
static bool sharedStoreValid();
static bool observedSeal(u32,StateCodec::Result,u32);
static bool validStore(){return sharedStoreValid();}
static bool archiveCandidateMatches(const SusamuneStateArchiveHeader&h){
 return candidateAllowed&&sCandidate.header.magic==kSnapshotMagic&&sCandidate.metadataTag==metadataTag(sCandidate)&&
  sCandidate.packedSize==h.packedSize&&sCandidate.rawSize==h.rawSize&&
  SusamuneStateCrc(&sCandidate,sizeof(sCandidate))==h.metadataCrc;}
static bool archiveProjectCandidateMatches(const SusamuneStateArchiveHeader&h){return archiveCandidateMatches(h);}
namespace StateStorage {
 struct ResultToken{u32 generation;};
 struct Result{u32 command,status,id;SusamuneStateArchiveHeader header;const void*metadata;char name[32];
  SusamuneStateWindowReceipt window;SusamuneTasManifest project;ResultToken token;};
 static Result result;static bool owned,pending,ready,borrowed,retained,cancelled;
 static u32 generation,requests,consumed,retainedConsumes,releases,requestOffset,requestSize,requestCommand,delayStarts;
 static u32 lastCommand,lastStatus;static SusamuneStateExportPlan exportPlan;
 static bool busy(){return owned||pending||ready||borrowed;}
 static void*stagingBase(){return stageBytes;}static u32 stagingSize(){return 0x33e000;}
 static void*tailWindowBase(){return windowBytes;}static u32 tailWindowSize(){return 0x4e000;}
 static void update(){}static void discardCancelledResult(){}
 static bool startImportWindow(u32 id,u32 crc,u32 packed,u32 offset,u32 size,const SusamuneTasRequest*){
  if(delayStarts){--delayStarts;return false;}
  if(pending||ready||borrowed||(owned&&!retained)){++errors;return false;}
  if(id!=77||crc!=fileHeader.headerCrc||packed!=archiveSize||size>tailWindowSize()||offset+size>packed)return false;
  owned=pending=true;retained=cancelled=false;requestOffset=offset;requestSize=size;requestCommand=SUSAMUNE_STATE_CMD_READ_WINDOW;
  ++requests;return true;
 }
 static bool startImport(u32,u32,u32,u32,const SusamuneTasRequest*){++errors;return false;}
 static bool startWindow(u32,u32,u32,u32,u32,const SusamuneTasRequest*){++errors;return false;}
 static bool startExport(const SusamuneStateArchiveHeader&,const void*,u32,const SusamuneTasRequest*){++errors;return false;}
 typedef bool(*Builder)(void*,SusamuneStateExportPlan&,u32);
 static bool startPlannedExport(const SusamuneStateArchiveHeader&h,const void*m,Builder builder,void*ctx,const SusamuneTasRequest*){
  if(busy())return false;owned=true;
  if(!builder(ctx,exportPlan,SusamuneStateCrc(m,sizeof(StoredState)))){owned=false;return false;}
  fileHeader=h;requestCommand=SUSAMUNE_STATE_CMD_EXPORT;pending=true;++requests;return true;
 }
 static bool takeResult(Result&out){if(!ready)return false;out=result;ready=pending=false;borrowed=true;return true;}
 static bool consumeResult(const Result&r,bool keep=false){
  if(!owned||!borrowed||r.token.generation!=result.token.generation){++errors;return false;}
  borrowed=false;++consumed;lastCommand=r.command;lastStatus=r.status;
  memset(windowBytes,0xd7,tailWindowSize());memset(&returned,0xd7,sizeof(returned));
  if(keep){retained=true;++retainedConsumes;}
  else {if(sSharedStore.pending||sSharedStore.pin)++errors;owned=false;++releases;}
  return true;
 }
 static bool releaseOwner(){
  if(!owned||pending||borrowed||ready||sSharedStore.pending||sSharedStore.pin){++errors;return false;}
  owned=retained=false;++releases;return true;
 }
 static bool cancel(){if(!pending)return false;cancelled=true;return true;}
}
static StateStorage::ResultToken sDiskBorrow;
bool SavestateManager::diskBusy(){return sDiskActive||sDiskLoadReady||StateStorage::busy();}
'''

EXPORTS = r'''
static bool observedSeal(u32 slot,StateCodec::Result result,u32 kind){
 bool ok=sealSharedCandidate(slot,result,kind);
 sealedCommitRefused=!ok&&sSharedStore.sealed&&StateStore::valid(sSharedStore);return ok;
}
extern "C" {
__declspec(dllexport) void setup(StateStore::Store*s,void*w,void*window,void*staging){
 testStore=s;work=w;windowBytes=(u8*)window;stageBytes=(u8*)staging;
 sPool={};sPoolMemory={};for(u32 i=0;i<3;++i){sSlots[i]={};sPackedChecksums[i]=0;}
 sCandidate={};sNextGeneration=sDurableSlots=sActiveSlot=sLoadSlot=0;sSharedReady=true;
 sBusy=sAwaitingLoadApproval=sDiskActive=sDiskRestore=sDiskLoadReady=sDiskChunkImport=sDiskNextWindow=false;
 sDiskCancelRequested=sDiskStream=sDiskRecovered=sStreamCommit=sExplicitTransfer=sTransferReady=false;
 sDiskImport={};sDiskProject={};sDiskBorrow={};sDiskRootPin=0;manager={};scene=0x04020005;
 terminalStatus=notices=cleared=rebased=errors=0;candidateAllowed=true;muted=interrupts=sealedCommitRefused=false;
 StateStorage::owned=StateStorage::pending=StateStorage::ready=StateStorage::borrowed=StateStorage::retained=StateStorage::cancelled=false;
 StateStorage::generation=StateStorage::requests=StateStorage::consumed=StateStorage::retainedConsumes=StateStorage::releases=0;
 StateStorage::delayStarts=StateStorage::lastCommand=StateStorage::lastStatus=0;
}
__declspec(dllexport) int seed(u32 slot,const void*p,u32 n){
 sCandidate={};sCandidate.header={kSnapshotMagic,4,2,{0,0}};sCandidate.archiveProfile=71;
 sCandidate.generation=sNextGeneration+1;sCandidate.rawSize=n;sCandidate.parentEpisode=5;sCandidate.sidecars[0]=41+slot;
 StateCodec::ReadSpan source={p,n};StateCodec::Result result;
 bool ok=compressSharedCandidate(&source,1,slot,0,result);if(ok)++sNextGeneration;return ok;
}
__declspec(dllexport) void identity(u32 slot,StateStore::Identity*out){*out=sharedIdentity(slot);}
__declspec(dllexport) void archive(const void*p,u32 n,u32 raw,u32 adler){
 archiveBytes=(const u8*)p;archiveSize=n;returned={};returned.header={kSnapshotMagic,4,2,{0,0}};
 returned.archiveProfile=71;returned.generation=191;returned.rawSize=raw;returned.packedSize=n;returned.adler32=adler;
 returned.parentEpisode=5;returned.sidecars[0]=99;returned.practice={7,{3,4},{1,2},16};returned.metadataTag=metadataTag(returned);
 originalMetadata=returned;fileHeader={};fileHeader.magic=SUSAMUNE_STATE_ARCHIVE_MAGIC;fileHeader.version=1;
 fileHeader.headerSize=sizeof(fileHeader);fileHeader.metadataSize=sizeof(returned);fileHeader.packedSize=n;fileHeader.rawSize=raw;
 fileHeader.gameId=archiveGameId();fileHeader.buildCrc=archiveBuildId();fileHeader.snapshotVersion=kSnapshotVersion;
 fileHeader.metadataCrc=SusamuneStateCrc(&returned,sizeof(returned));fileHeader.payloadCrc=SusamuneStateCrc(p,n);
 fileHeader.sceneKey=scene;fileHeader.headerCrc=SusamuneStateHeaderCrc(&fileHeader);terminalStatus=0;
}
__declspec(dllexport) int begin(u32 slot,u32 project){
 SusamuneTasRequest p={};p.projectId=9;p.componentId=77;p.role=1;
 bool accepted=manager.beginSDLoad(77,fileHeader.headerCrc,archiveSize,false,slot,project?&p:0);
 sProjectStartKey[0]=1;sProjectStartKey[1]=2;sProjectRole=1;sProjectFrames=16;return accepted;
}
__declspec(dllexport) int beginExport(u32 slot){return manager.beginSDExport(slot,sSlots[slot].generation,"probe",0);}
__declspec(dllexport) int complete(u32 fault){
 using namespace StateStorage;if(!owned||!pending||ready||borrowed)return 0;
 returned=originalMetadata;
 result={};result.token.generation=++generation;result.command=requestCommand;result.id=77;result.header=fileHeader;
 result.metadata=&returned;result.status=cancelled?SUSAMUNE_STATE_CANCELLED:SUSAMUNE_STATE_OK;
 if(requestCommand==SUSAMUNE_STATE_CMD_READ_WINDOW){
  memcpy(windowBytes,archiveBytes+requestOffset,requestSize);result.window.offset=requestOffset;result.window.size=requestSize;
  result.window.checksum=SusamuneStateCrc(windowBytes,requestSize);
 }
 switch(fault){case 1:result.window.checksum^=1;break;case 2:++result.header.rawSize;break;
 case 3:++returned.sidecars[0];break;case 4:++sSlots[sDiskSlot].generation;break;case 5:++scene;break;
 case 6:result.command=SUSAMUNE_STATE_CMD_IMPORT;break;case 7:++result.id;break;
 case 8:++result.window.offset;break;case 9:result.metadata=0;break;
 case 10:result.status=SUSAMUNE_STATE_CANCELLED;break;case 11:--result.window.size;break;
 case 12:windowBytes[17]^=1;result.window.checksum=SusamuneStateCrc(windowBytes,requestSize);break;}
 ready=true;return 1;
}
__declspec(dllexport) void repairFault(u32 fault){if(fault==4)--sSlots[sDiskSlot].generation;if(fault==5)--scene;returned=originalMetadata;}
__declspec(dllexport) void tick(){manager.updateDisk();}
__declspec(dllexport) int cancel(){return manager.cancelSD();}
__declspec(dllexport) void delay(u32 n){StateStorage::delayStarts=n;}
__declspec(dllexport) u32 get(u32 n){using namespace StateStorage;switch(n){
 case 0:return sDiskActive;case 1:return pending;case 2:return ready;case 3:return borrowed;case 4:return owned;
 case 5:return retained;case 6:return requests;case 7:return consumed;case 8:return retainedConsumes;case 9:return releases;
 case 10:return errors;case 11:return sSharedStore.pending;case 12:return sDiskNextWindow;case 13:return sDiskRootPin;
 case 14:return sSharedStore.pin;case 15:return sDurableSlots;case 16:return sNextGeneration;
 case 17:return sTransferReady;case 18:return sTransferResult.command;case 19:return sTransferResult.status;
 case 20:return lastCommand;case 21:return terminalStatus;case 22:return notices;case 23:return cleared;
 case 24:return sSharedStore.roots[sDiskSlot].generation;case 25:return sCandidate.sidecars[0];
 case 26:return muted||interrupts;case 27:return !owned;case 28:return sDiskImport.offset;case 29:return exportPlan.count;
 case 30:return sealedCommitRefused;}
 return 0;
}
__declspec(dllexport) u32 metadata(u32 slot,u32 n){
 if(n==4){StoredState expected=originalMetadata;expected.generation=sSlots[slot].generation;
  expected.metadataTag=metadataTag(expected);return !memcmp(&expected,&sSlots[slot],sizeof(expected));}
 return n==0?sSlots[slot].metadataTag==metadataTag(sSlots[slot]):
  n==1?sSlots[slot].sidecars[0]:n==2?sSlots[slot].archiveProfile:sSlots[slot].parentEpisode;}
}
'''


class SharedSdManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='shared-sd-manager-')
        folder = Path(cls.temp.name)
        (folder / 'allocator').mkdir()
        functions = []
        for name in (
            'u32 metadataTag(', 'StateStore::Identity sharedIdentity(', 'bool sharedStoreValid(',
            'bool abortSharedCandidate(', 'bool sealSharedCandidate(', 'bool compressSharedCandidate(',
            'u32 nextGeneration(', 'bool finishSharedExport(', 'bool buildSharedExport(',
            'u32 appendSharedImport(', 'bool SavestateManager::beginSDLoad(',
            'bool SavestateManager::beginSDExport(', 'bool SavestateManager::cancelSD(',
            'void SavestateManager::updateDisk('):
            source = function_source(SOURCE, name)
            if name == 'u32 appendSharedImport(':
                source = source.replace('sealSharedCandidate(', 'observedSeal(')
            functions.append(source)
        cls.codec = StoreCodec(folder, '#include "' + (ROOT / 'src/state_import.cpp').as_posix() +
            '"\n' + FIXTURE + '\n'.join(functions) + EXPORTS)
        cls.codec.work = Guarded(0x4e000)
        cls.harness = StageHarness(folder / 'allocator')
        p, u = C.c_void_p, C.c_uint
        for name, args in {'setup': [p, p, p, p], 'seed': [u, p, u],
                'identity': [u, C.POINTER(Identity)], 'archive': [p, u, u, u],
                'begin': [u, u], 'beginExport': [u], 'complete': [u], 'repairFault': [u],
                'tick': [], 'cancel': [], 'delay': [u], 'get': [u], 'metadata': [u, u]}.items():
            getattr(cls.codec.lib, name).argtypes = args

    @classmethod
    def tearDownClass(cls):
        cls.codec.close()
        cls.harness.close()
        cls.temp.cleanup()

    def setup_store(self, sizes=None, staging=0x2f0000):
        self.store = StorePool(self.harness, self.codec, sizes, staging)
        self.window = Guarded(0x4e000)
        self.codec.lib.setup(self.store.storage.ptr, self.codec.work.ptr, self.window.ptr,
                             self.store.pool.stage_memory.staging)
        self.raws = [random.Random(i + 1).randbytes(0x22017) for i in range(3)]
        for slot, raw in enumerate(self.raws):
            src = C.create_string_buffer(raw)
            self.assertTrue(self.codec.lib.seed(slot, src, len(raw)))
            self.sync(slot, raw)
        self.before = [bytes(i) for i in self.store.identities]

    def sync(self, slot, raw):
        info = Identity()
        self.codec.lib.identity(slot, C.byref(info))
        self.store.identities[slot] = info
        sequence, spans = self.store.borrowed(slot)
        encoded = b''.join(C.string_at(span.data, span.size) for span in spans)
        self.assertTrue(self.store.call('su', sequence))
        self.store.roots[slot] = raw, encoded
        self.store.decode(slot, True)
        self.assertTrue(self.codec.lib.metadata(slot, 0))

    def set_archive(self, kind, raw=None):
        self.incoming = raw if raw is not None else random.Random(731).randbytes(0xb0123)
        packed = encode_quick(self.incoming) if kind == 0 else zlib.compress(self.incoming)
        self.archive = C.create_string_buffer(packed)
        self.codec.lib.archive(self.archive, len(packed), len(self.incoming), zlib.adler32(self.incoming))

    def get(self, n):
        return self.codec.lib.get(n)

    def preserved(self):
        for slot, raw in enumerate(self.raws):
            self.sync(slot, raw)
            self.assertEqual(bytes(self.store.identities[slot]), self.before[slot])
        self.assertTrue(self.window.guards())
        self.assertEqual(self.get(10), 0)

    def finish(self):
        for _ in range(100):
            if not self.get(0):
                break
            self.assertEqual(self.get(27), 0, 'ghost reuse before terminal consumption')
            if self.get(1) and not self.get(2):
                self.assertTrue(self.codec.lib.complete(0))
            self.codec.lib.tick()
        self.assertFalse(self.get(0))
        self.assertEqual((self.get(4), self.get(11), self.get(14), self.get(26)), (0, 0, 0, 0))
        self.assertEqual(self.get(10), 0)

    def first_window(self, slot=1, project=0):
        self.assertTrue(self.codec.lib.begin(slot, project))
        self.assertEqual(self.get(11), 0)
        self.assertTrue(self.codec.lib.complete(0))
        self.codec.lib.tick()
        self.assertTrue(self.get(12))
        self.assertTrue(self.get(11))
        self.assertTrue(self.get(5))
        self.assertEqual(self.get(3), 0)
        self.preserved()

    def test_quick_and_deflate_replace_each_slot_only_after_all_windows(self):
        for kind in (0, 1):
            for slot in range(3):
                with self.subTest(kind=kind, slot=slot):
                    self.setup_store()
                    self.set_archive(kind)
                    self.first_window(slot, 1)
                    self.codec.lib.delay(2)
                    for _ in range(2):
                        self.codec.lib.tick()
                        self.assertTrue(self.get(12))
                        self.assertEqual(self.get(27), 0)
                    self.finish()
                    for current in range(3):
                        self.sync(current, self.incoming if current == slot else self.raws[current])
                    self.assertEqual(self.store.identities[slot].kind, kind)
                    self.assertEqual(self.store.identities[slot].generation, 4)
                    self.assertEqual(self.get(15), 1 << slot)
                    self.assertEqual((self.get(17), self.get(18), self.get(19)), (1, 2, 0))
                    self.assertEqual(self.get(20), 2)
                    self.assertEqual(self.get(8), self.get(6) - 1)
                    self.assertEqual(self.get(9), 1)
                    self.assertEqual(self.codec.lib.metadata(slot, 1), 99)
                    self.assertEqual(self.codec.lib.metadata(slot, 2), 71)
                    self.assertEqual(self.codec.lib.metadata(slot, 3), 5)
                    self.assertTrue(self.codec.lib.metadata(slot, 4))

    def test_cancel_before_first_or_between_windows_releases_only_after_abort(self):
        for between in (False, True):
            with self.subTest(between=between):
                self.setup_store()
                self.set_archive(0)
                if between:
                    self.first_window()
                else:
                    self.assertTrue(self.codec.lib.begin(1, 0))
                self.assertTrue(self.codec.lib.cancel())
                self.finish()
                self.assertEqual(self.get(21), 6)
                self.assertEqual(self.get(9), 1)
                self.preserved()

    def test_second_window_identity_crc_metadata_and_stale_owner_faults_preserve_roots(self):
        for fault in range(1, 13):
            with self.subTest(fault=fault):
                self.setup_store()
                self.set_archive(0)
                self.first_window(project=1)
                self.codec.lib.tick()
                self.assertTrue(self.codec.lib.complete(fault))
                self.codec.lib.tick()
                self.finish()
                self.codec.lib.repairFault(fault)
                self.assertIn(self.get(19), (3, 6))
                self.assertEqual(self.get(18), 2)
                self.preserved()

    def test_full_pool_candidate_refusal_preserves_all_three_roots(self):
        self.setup_store(sizes=[0x50000, 0x30000, 0x30000, 0x30000], staging=0x20000)
        self.set_archive(0, random.Random(884).randbytes(0x180000))
        self.assertTrue(self.codec.lib.begin(2, 1))
        self.finish()
        self.assertEqual(self.get(19), 4)
        self.preserved()

    def test_sealed_candidate_final_capacity_refusal_is_full_and_preserves_roots(self):
        self.setup_store(sizes=[0x50000, 0x30000, 0x30000, 0x30000])
        self.set_archive(0, random.Random(901).randbytes(0x100000))
        self.first_window(2, 1)
        self.finish()
        self.assertTrue(self.get(30), 'final commit must refuse an otherwise valid sealed candidate')
        self.assertEqual((self.get(17), self.get(18), self.get(19)), (1, 2, 4))
        self.assertEqual(self.get(8), self.get(6) - 1)
        self.assertEqual(self.get(9), 1)
        self.preserved()

    def test_retained_payload_corruption_is_bad_file_even_after_candidate_seals(self):
        self.setup_store()
        self.set_archive(0)
        self.first_window(2, 1)
        pool = self.store.pool
        chunk = pool.directory.chunks[pool.directory.slots[0].ids[0] - 1]
        bank, offset = 0, chunk.offset
        while offset >= pool.memory.sizes[bank]:
            offset -= pool.memory.sizes[bank]
            bank += 1
        changed = C.c_ubyte.from_address(pool.memory.banks[bank] + offset + 16)
        changed.value ^= 1
        try:
            self.finish()
            self.assertTrue(self.get(30), 'candidate seal must succeed despite unrelated old payload corruption')
            self.assertEqual((self.get(17), self.get(18), self.get(19)), (1, 2, 3))
            self.assertEqual(self.get(9), 1)
        finally:
            changed.value ^= 1
        self.preserved()

    def test_export_plan_pins_root_until_async_completion_then_consumes(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.setup_store()
                self.assertTrue(self.codec.lib.beginExport(1))
                self.assertTrue(self.get(13))
                self.assertEqual(self.get(13), self.get(14))
                self.assertGreater(self.get(29), 0)
                self.assertFalse(self.store.begin(0))
                self.assertEqual(self.get(27), 0)
                if cancelled:
                    self.assertTrue(self.codec.lib.cancel())
                self.finish()
                self.assertEqual(self.get(20), 1)
                self.assertEqual(self.get(21), 6 if cancelled else 0)
                self.assertEqual(self.get(9), 1)
                self.preserved()


if __name__ == '__main__':
    unittest.main()
