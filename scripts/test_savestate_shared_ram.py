"""Execute the game's shared RAM preparation/identity and virgin-init gates."""
import ctypes as C
from pathlib import Path
import random
import tempfile
import unittest

from test_practice_tape import function_source
from test_state_codec import Guarded, Result, Span
from test_state_store import StoreCodec, StorePool, Identity
from test_timewarp_staged_transaction import StageHarness

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r'''
#include "susamune/state_pool_memory.h"
#include "susamune/state_work_lease.hxx"
typedef unsigned int u32; typedef unsigned char u8;
struct SavestateManager {
 enum {kSlotCount=3}; bool mLoadPending;
 static bool diskBusy(); bool initSharedStore(); bool sharedStoreReady()const;
 bool clearSlot(u32,u32);
};
struct Header {u32 magic;};
struct StoredState {Header header;u8 sidecars[512];u32 generation,rawSize,packedSize,adler32,parentEpisode,metadataTag;};
static StateStore::Store *store;
#define sSharedStore (*store)
static TWBankMemory sSharedBanks;
static TWStageMemory sSharedMemory;
static StatePoolMemory sPoolMemory;
static StateSlotPool sPool;
static StoredState sSlots[3],sCandidate;
static u32 sPackedChecksums[3],sNextGeneration,sDurableSlots,clearNotices;
static bool sSharedReady,sMetadataReady,sBusy,sAwaitingLoadApproval,diskBusy;
static struct {u32 generation;} sDiskBorrow;
static bool shared,storageQuiet,ghostQuiet,workAllowed,mapAllowed;
static unsigned epoch,held,directoryWrites;
static void *testWorkspace,*second,*nativeTable;
static unsigned nativeBytes;
static u8 *staging;
static SavestateManager manager;
static const u32 kSnapshotMagic=0x53555341;
#define SUSAMUNE_TRANSFER_IMPORT_WINDOW_OFFSET 0x2F0000u
namespace TransferLease {bool sharedMap(){return shared;}}
namespace StateStorage {
 bool quiet(){return storageQuiet;} void *stagingBase(){return staging;}
 void *tailWindowBase(){return second;} unsigned tailWindowSize(){return 0x4E000;}
}
namespace GhostStorage {bool quiet(){return ghostQuiet;}}
namespace StateWorkLease {
 Guard::Guard(bool needed):mHeld(needed&&workAllowed){if(mHeld)++held;}
 Guard::~Guard(){if(mHeld)--held;}
 unsigned epoch(){return held?::epoch:0;}
}
bool SavestateManager::diskBusy(){return ::diskBusy;}
bool statePoolSharedMemory(StatePoolMemory&){return mapAllowed;}
void *codecWorkspace(){return testWorkspace;}
bool sharedStoreValid();
bool validStore(){return sharedStoreValid();}
namespace PracticeSession {void onSavestateCleared(u32,u32){if(held)++clearNotices;}}
namespace StateStore {
static bool nativeInit(Store&s,const TWStageMemory&m,unsigned e){
 ++directoryWrites;return init(s,m,e,nativeTable,nativeBytes);}
}
'''

SUFFIX = r'''
extern "C" {
__declspec(dllexport) void setup(StateStore::Store*s,TWStageMemory*m,void*w,void*p,void*t,unsigned tn){
 store=s;testWorkspace=w;second=p;nativeTable=t;nativeBytes=tn;staging=m->staging;
 sSharedMemory=*m;sSharedBanks=*m->pool;
 for(unsigned i=0;i<4;++i){sPoolMemory.banks[i]=m->pool->banks[i];sPoolMemory.sizes[i]=m->pool->sizes[i];}
 sPool={};for(unsigned i=0;i<3;++i){sSlots[i]={};sPackedChecksums[i]=0;}sCandidate={};
 sNextGeneration=0;shared=sSharedReady=sMetadataReady=storageQuiet=ghostQuiet=workAllowed=mapAllowed=true;
 sBusy=sAwaitingLoadApproval=diskBusy=manager.mLoadPending=false;sDiskBorrow.generation=0;
 epoch=73;held=directoryWrites=0;
 clearNotices=sDurableSlots=0;
}
__declspec(dllexport) int save(unsigned slot,const void*p,unsigned n,unsigned mode,StateCodec::Result*out){
 if(!sharedStoreValid())return 0;
 sCandidate={};sCandidate.header.magic=kSnapshotMagic;sCandidate.rawSize=n;sCandidate.generation=sNextGeneration+1;
 sCandidate.sidecars[0]=41+slot;sCandidate.parentEpisode=5+slot;
 StateCodec::ReadSpan source={p,n};bool ok=mode<3?
  compressSharedCandidate(&source,1,slot,mode,*out):saveSharedCandidate(&source,1,n,slot,*out);
 if(ok)++sNextGeneration;return ok;
}
__declspec(dllexport) int retained(unsigned slot,unsigned compact){return repackSharedRetained(slot,compact!=0);}
__declspec(dllexport) void identity(unsigned slot,StateStore::Identity*out){*out=sharedIdentity(slot);}
__declspec(dllexport) unsigned meta(unsigned slot,unsigned which){
 const StoredState&s=sSlots[slot];return which==0?s.generation:which==1?s.metadataTag:
 which==2?metadataTag(s):which==3?s.sidecars[0]:which==4?s.parentEpisode:sNextGeneration;}
__declspec(dllexport) int binding(){return sharedStoreValid();}
__declspec(dllexport) void corruptMeta(unsigned slot){++sSlots[slot].rawSize;}
__declspec(dllexport) void initFault(unsigned n){
 sSharedReady=false;*store={};
 switch(n){case 1:shared=false;break;case 2:sMetadataReady=false;break;
 case 3:sNextGeneration=1;break;case 4:sPool.used=1;break;case 5:sBusy=true;break;
 case 6:diskBusy=true;break;case 7:manager.mLoadPending=true;break;
 case 8:sAwaitingLoadApproval=true;break;case 9:sDiskBorrow.generation=1;break;
 case 10:storageQuiet=false;break;case 11:ghostQuiet=false;break;case 12:store->magic=1;break;
 case 13:sPool.slots[1].offset=1;break;case 14:sPool.slots[1].size=1;break;
 case 15:sSlots[1].header.magic=1;break;case 16:sSlots[1].generation=1;break;
 case 17:sSlots[1].rawSize=1;break;case 18:sSlots[1].packedSize=1;break;
 case 19:sSlots[1].metadataTag=1;break;case 20:sPackedChecksums[1]=1;break;
 case 21:workAllowed=false;break;case 22:epoch=0;break;case 23:mapAllowed=false;break;
 case 24:sPoolMemory.banks[3]=sPoolMemory.banks[0];break;}
}
__declspec(dllexport) int init(){return manager.initSharedStore();}
__declspec(dllexport) unsigned get(unsigned n){return n==0?held:n==1?directoryWrites:sSharedReady;}
__declspec(dllexport) int clear(unsigned slot,unsigned generation,unsigned allowed){workAllowed=allowed!=0;return manager.clearSlot(slot,generation);}
__declspec(dllexport) unsigned cleared(){return clearNotices;}
}
'''


class SharedRamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='shared-ram-')
        folder = Path(cls.temp.name)
        (folder / 'allocator').mkdir()
        functions = '\n'.join(function_source(ROOT / 'src/savestate.cpp', name) for name in (
            'u32 metadataTag(', 'StateStore::Identity sharedIdentity(', 'bool sharedStoreValid(',
            'bool abortSharedCandidate(', 'bool sealSharedCandidate(', 'bool compressSharedCandidate(',
            'u32 repackedMetadataTag(', 'bool repackSharedRetained(', 'bool saveSharedCandidate(',
            'u32 nextGeneration(', 'bool SavestateManager::sharedStoreReady(',
            'bool SavestateManager::initSharedStore(', 'bool SavestateManager::clearSlot('))
        functions = functions.replace('StateStore::init(', 'StateStore::nativeInit(')
        cls.codec = StoreCodec(folder, PREFIX + functions + SUFFIX)
        cls.codec.work = Guarded(0x4E000)
        cls.harness = StageHarness(folder / 'allocator')
        p, u = C.c_void_p, C.c_uint
        for name, args in {
            'setup': [p, p, p, p, p, u], 'save': [u, p, u, u, C.POINTER(Result)],
            'retained': [u, u], 'identity': [u, C.POINTER(Identity)],
            'meta': [u, u], 'binding': [], 'corruptMeta': [u], 'initFault': [u], 'init': [], 'get': [u],
            'clear': [u, u, u], 'cleared': []
        }.items():
            getattr(cls.codec.lib, name).argtypes = args

    @classmethod
    def tearDownClass(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.codec.lib._handle)
        _ctypes.FreeLibrary(cls.harness.lib._handle)
        cls.temp.cleanup()

    def make_store(self, sizes=None, staging=0x2f0000):
        self.store = StorePool(self.harness, self.codec, sizes=sizes, staging=staging)
        self.second = Guarded(0x4E000)
        self.codec.lib.setup(self.store.storage.ptr, C.byref(self.store.pool.stage_memory),
            self.codec.work.ptr, self.second.ptr, self.store.table.ptr, self.store.table.size)
        return self.store

    def sync(self, slot, raw):
        identity = Identity()
        self.codec.lib.identity(slot, C.byref(identity))
        self.store.identities[slot] = identity
        sequence, spans = self.store.borrowed(slot)
        encoded = b''.join(C.string_at(s.data, s.size) for s in spans)
        self.assertTrue(self.store.call('su', sequence))
        self.store.roots[slot] = raw, encoded
        self.store.decode(slot, True)
        self.assertEqual(self.codec.lib.meta(slot, 1), self.codec.lib.meta(slot, 2))

    def save(self, slot, raw, mode=3):
        source, result = C.create_string_buffer(raw), Result()
        ok = self.codec.lib.save(slot, source, len(raw), mode, C.byref(result))
        if ok:
            self.sync(slot, raw)
        return ok, result

    def test_all_three_quick_slots_and_every_replacement_preserve_binding(self):
        self.make_store(sizes=[0x140000, 0x60000, 0x60000, 0x60000])
        raw = [random.Random(i).randbytes(0x41013) for i in range(3)]
        for slot in range(3):
            self.assertTrue(self.save(slot, raw[slot])[0])
            self.assertEqual(self.store.identities[slot].kind, 0)
        for slot in range(3):
            raw[slot] = raw[slot][:0x20000] + bytes([slot]) * (len(raw[slot]) - 0x20000)
            self.assertTrue(self.save(slot, raw[slot])[0])
            for n in range(3):
                self.sync(n, raw[n])
        self.assertTrue(self.codec.lib.binding())
        self.assertTrue(self.second.guards())

    def test_deflate_fallback_and_retained_repack_keep_external_generation(self):
        self.make_store()
        raw = bytes([31]) * 0x60123
        self.assertTrue(self.save(0, raw, 0)[0])
        old = self.store.identities[0]
        self.assertTrue(self.codec.lib.retained(0, 0))
        self.sync(0, raw)
        new = self.store.identities[0]
        self.assertEqual(new.kind, 1)
        self.assertEqual(new.generation, old.generation)
        self.assertLess(new.packed, old.packed)
        self.assertEqual(self.codec.lib.meta(0, 3), 41)
        self.assertEqual(self.codec.lib.meta(0, 4), 5)
        self.assertEqual(self.codec.lib.meta(0, 5), 1)
        self.assertTrue(self.save(1, raw, 1)[0])
        self.assertEqual(self.store.identities[1].kind, 1)
        self.assertEqual(self.store.identities[1].generation, 2)
        self.assertTrue(self.codec.lib.binding())
        self.assertTrue(self.second.guards())

    def test_full_pool_refusal_keeps_every_old_root_and_generation(self):
        self.make_store(sizes=[0x90000, 0x40000, 0x40000, 0x40000], staging=0x40000)
        raws = [random.Random(i).randbytes(0x30123) for i in range(3)]
        for slot, raw in enumerate(raws):
            self.assertTrue(self.save(slot, raw)[0])
        old = [bytes(i) for i in self.store.identities]
        candidate = random.Random(77).randbytes(0x200000)
        self.assertFalse(self.save(1, candidate)[0])
        for slot, raw in enumerate(raws):
            self.sync(slot, raw)
            self.assertEqual(bytes(self.store.identities[slot]), old[slot])
        self.assertEqual(self.codec.lib.meta(0, 5), 3)
        self.assertTrue(self.codec.lib.binding())

    def test_retained_repack_refuses_to_trade_shared_blocks_for_more_pool_bytes(self):
        self.make_store()
        raw = bytes([47]) * 0x60123
        self.assertTrue(self.save(0, raw, 0)[0])
        self.assertTrue(self.save(1, raw, 0)[0])
        old = [bytes(i) for i in self.store.identities]
        occupied = self.store.pool.directory.high_water
        self.assertFalse(self.codec.lib.retained(0, 0))
        for slot in (0, 1):
            self.sync(slot, raw)
            self.assertEqual(bytes(self.store.identities[slot]), old[slot])
        self.assertEqual(self.store.pool.directory.high_water, occupied)

    def test_mismatched_metadata_refuses_before_candidate_mutation(self):
        self.make_store()
        raw = b'unchanged' * 30000
        self.assertTrue(self.save(0, raw)[0])
        before = self.store.pool.states()
        self.codec.lib.corruptMeta(0)
        self.assertFalse(self.save(1, raw)[0])
        self.assertEqual(self.store.pool.states(), before)

    def test_shared_clear_requires_owner_and_exact_generation_then_saves_again(self):
        self.make_store()
        raw = b'original' * 30000
        self.assertTrue(self.save(1, raw)[0])
        before = self.store.pool.states()
        self.assertFalse(self.codec.lib.clear(1, 1, 0))
        self.assertFalse(self.codec.lib.clear(1, 9, 1))
        self.assertEqual(self.store.pool.states(), before)
        self.assertTrue(self.codec.lib.clear(1, 1, 1))
        empty = Identity()
        self.codec.lib.identity(1, C.byref(empty))
        self.assertEqual(empty.generation, 2)
        self.assertEqual(empty.packed, 0)
        self.assertEqual(self.codec.lib.cleared(), 1)
        self.assertTrue(self.codec.lib.binding())
        self.assertTrue(self.save(1, raw)[0])
        self.assertEqual(self.store.identities[1].generation, 3)

    def test_init_gates_refuse_without_touching_stale_directory(self):
        for fault in range(1, 25):
            with self.subTest(fault=fault):
                self.make_store(sizes=[0x90000, 0x40000, 0x40000, 0x40000])
                C.memset(self.store.pool.memory.banks[0], 0xA5, 0x8000)
                self.codec.lib.initFault(fault)
                before = C.string_at(self.store.pool.memory.banks[0], 0x8000)
                self.assertFalse(self.codec.lib.init())
                self.assertEqual(C.string_at(self.store.pool.memory.banks[0], 0x8000), before)
                self.assertEqual(self.codec.lib.get(0), 0)
                self.assertEqual(self.codec.lib.get(1), 0)

    def test_virgin_owned_init_discards_only_old_directory_and_is_idempotent(self):
        self.make_store(sizes=[0x90000, 0x40000, 0x40000, 0x40000])
        bank = self.store.pool.memory.banks[0]
        C.memset(bank, 0xA5, 0x8040)
        self.codec.lib.initFault(0)
        self.assertTrue(self.codec.lib.init())
        self.assertEqual(C.string_at(bank + 0x8000, 0x40), bytes([0xA5]) * 0x40)
        self.assertEqual(self.codec.lib.get(0), 0)
        self.assertEqual(self.codec.lib.get(1), 1)
        self.assertTrue(self.codec.lib.init())
        self.assertEqual(self.codec.lib.get(1), 1)
        self.assertTrue(self.save(0, b'fresh' * 9000)[0])


if __name__ == '__main__':
    unittest.main()
