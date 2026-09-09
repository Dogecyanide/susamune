"""Drive the production PPC client through stale receipts and cancellation."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREAMBLE = r'''
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef unsigned long long size_t;
#include "susamune/state_storage.h"
#include "susamune/state_pool_memory.h"
extern "C" void *memcpy(void *d,const void *s,size_t n) {u8 *a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void *d,int c,size_t n) {u8*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
static SusamuneStateStorageMailbox testMailbox;
static u8 testPool[SUSAMUNE_STATE_POOL_SIZE], testStaging[SUSAMUNE_STATE_STAGING_SIZE];
static u8 testExtra[SUSAMUNE_STATE_POOL_EXTRA_SIZE];static bool expanded,relocated;
static StatePoolMemory statePoolMemory() {StatePoolMemory m={{testPool,testExtra},{relocated?SUSAMUNE_STATE_POOL_SIZE:SUSAMUNE_STATE_POOL_LEGACY_SIZE,
 expanded?SUSAMUNE_STATE_POOL_EXTRA_SIZE:0}};return m;}
struct CacheCall {const void *address;u32 size;};
static CacheCall flushed[32],invalidated[32]; static u32 flushCount,invalidateCount;
static u8 physical[192],expected[128];static bool watch,requestSawFlushed;
static void DCFlushRange(void *p,u32 n) {
 if(flushCount<32)flushed[flushCount++]={p,n};
 if(!watch)return;
 StatePoolMemory memory=statePoolMemory();
 for(u32 i=0;i<sizeof(physical);++i){StatePoolMemorySpan span;
  StatePoolMemorySpanAt(&memory,SUSAMUNE_STATE_POOL_SIZE-96+i,1,&span);
  __UINTPTR_TYPE__ a=(__UINTPTR_TYPE__)span.data,b=(__UINTPTR_TYPE__)p;
  if(a>=b && a-b<n)physical[i]=*span.data;}
 if(p==&testMailbox.request){requestSawFlushed=true;
  for(u32 i=0;i<sizeof(physical);++i)
   if(physical[i]!=(i>=32 && i<160?expected[i-32]:0xA5))requestSawFlushed=false;}
}
static void DCInvalidateRange(void *p,u32 n) {if(invalidateCount<32)invalidated[invalidateCount++]={p,n};}
static u64 OSGetTime() {return 0x123456789ABCULL;}
namespace StateStorage {
struct Result {u32 command,status,id;SusamuneStateArchiveHeader header;const void *metadata;char name[32];SusamuneStateWindowReceipt window;};
bool busy();
}
'''
EXPORTS = r'''
extern "C" {
__declspec(dllexport) void reset(u32 pending) {
 watch=requestSawFlushed=false;
 memset(&testMailbox,0,sizeof(testMailbox));
 testMailbox.response.magic=SUSAMUNE_STATE_STORAGE_MAGIC;
 testMailbox.response.version=SUSAMUNE_STATE_STORAGE_VERSION;
 testMailbox.response.available=1;testMailbox.response.configId=123;
 testMailbox.request.seq=pending;flushCount=invalidateCount=0;expanded=false;relocated=true;
 StateStorage::init();
}
__declspec(dllexport) u32 beginImport(u32 size,u32 offset) {return StateStorage::startImport(7,999,size,offset);}
__declspec(dllexport) u32 beginWindow(u32 packed,u32 offset,u32 size,u32 crc) {return StateStorage::startWindow(7,crc,packed,offset,size);}
__declspec(dllexport) u32 prepareWindow(u32 packed) {
 auto &h=testMailbox.header;memset(&h,0,sizeof(h));h.magic=SUSAMUNE_STATE_ARCHIVE_MAGIC;h.version=1;
 h.headerSize=sizeof(h);h.metadataSize=8;h.packedSize=packed;h.rawSize=packed*2;h.gameId=0x474D5345;
 h.buildCrc=12;h.snapshotVersion=15;h.configId=123;h.metadataCrc=SusamuneStateCrc(testMailbox.metadata,8);
 h.headerCrc=SusamuneStateHeaderCrc(&h);return h.headerCrc;
}
__declspec(dllexport) u32 poolSize(void) {return SUSAMUNE_STATE_POOL_SIZE;}
__declspec(dllexport) u32 stagingSize(void) {return SUSAMUNE_STATE_STAGING_SIZE;}
__declspec(dllexport) u32 version(void) {return SUSAMUNE_STATE_STORAGE_VERSION;}
__declspec(dllexport) u32 setVersion(u32 version) {
 testMailbox.response.version=version;StateStorage::init();return StateStorage::available();}
__declspec(dllexport) u32 legacyLayout(void) {
 relocated=false;StateStorage::init();return StateStorage::available();}
__declspec(dllexport) void revokeCapabilities(void) {relocated=expanded=false;}
__declspec(dllexport) u32 beginRename(u32 id,u32 crc,const char *name) {return StateStorage::rename(id,crc,name);}
__declspec(dllexport) u32 beginDelete(u32 id,u32 crc) {return StateStorage::remove(id,crc);}
__declspec(dllexport) const void *mailbox(void) {return &testMailbox;}
__declspec(dllexport) u32 beginExport(u32 size,u32 offset) {
 SusamuneStateArchiveHeader h={};h.metadataSize=8;h.packedSize=size;h.rawSize=size*2;
 h.gameId=0x474D5345;h.buildCrc=1234;h.snapshotVersion=15;
 const u32 meta[2]={1,2}; return StateStorage::startExport(h,meta,offset);
}
__declspec(dllexport) void acknowledge(u32 status,u32 change,u32 oldSeq) {
 auto &r=testMailbox.request;auto &receipt=testMailbox.receipt;
 receipt.session=r.session;receipt.command=r.command;receipt.id=r.id;
 receipt.seq=r.seq;testMailbox.response.ackSeq=r.seq;testMailbox.response.status=status;
 if(change==1)receipt.session^=1;if(change==2)receipt.command^=1;if(change==3)receipt.id^=1;
 if(change==4)receipt.seq^=1;
 if(oldSeq)testMailbox.response.ackSeq=oldSeq;
}
__declspec(dllexport) u32 result(void) {StateStorage::Result r;return StateStorage::takeResult(r)?r.status:999;}
__declspec(dllexport) void windowReceipt(u32 corrupt) {
 acknowledge(0,0,0);auto &r=testMailbox.receipt;auto &h=testMailbox.header;auto &w=testMailbox.window;
 r.headerCrc=h.headerCrc;r.packedSize=h.packedSize;r.metadataSize=h.metadataSize;
 r.reserved=SusamuneStateCrc(testMailbox.resultName,32);testMailbox.response.resultId=testMailbox.request.id;
 w.offset=testMailbox.request.poolOffset;w.size=testMailbox.request.reserved;w.checksum=42;
 testMailbox.response.transferred=w.size;
 if(corrupt==1)w.offset++;if(corrupt==2)w.size--;if(corrupt==3)w.reserved[4]=1;
 if(corrupt==4)testMailbox.response.transferred--;if(corrupt==5)testMailbox.metadata[0]^=1;
 if(corrupt==6)testMailbox.response.resultId++;if(corrupt==7)r.headerCrc++;
}
__declspec(dllexport) void tick(void) {StateStorage::update();}
__declspec(dllexport) u32 busy(void) {return StateStorage::busy();}
__declspec(dllexport) u32 cancel(void) {return StateStorage::cancel();}
__declspec(dllexport) u32 seq(void) {return testMailbox.request.seq;}
__declspec(dllexport) u32 command(void) {return testMailbox.request.command;}
__declspec(dllexport) void clearCacheLog(void) {flushCount=invalidateCount=0;}
__declspec(dllexport) u32 stagingInvalidations(void) {
 u32 count=0;for(u32 i=0;i<invalidateCount;++i) if(invalidated[i].address==testStaging)++count;return count;
}
__declspec(dllexport) u32 poolTailInvalidated(u32 offset,u32 size) {
 for(u32 i=0;i<invalidateCount;++i) if(invalidated[i].address==testPool+offset && invalidated[i].size==size)return 1;
 return 0;
}
__declspec(dllexport) u32 headerValid(void) {return SusamuneStateHeaderValid(&testMailbox.header);}
__declspec(dllexport) void expand(void) {expanded=true;StateStorage::init();}
__declspec(dllexport) u32 prepareCompaction(void) {
 expanded=true;StateStorage::init();StatePoolMemory memory=statePoolMemory();
 StateSlotPool pool={};pool.slots[0]={0,SUSAMUNE_STATE_POOL_SIZE-64};
 pool.slots[1]={SUSAMUNE_STATE_POOL_SIZE-64,96};
 pool.slots[2]={SUSAMUNE_STATE_POOL_SIZE+32,128};pool.used=SUSAMUNE_STATE_POOL_SIZE+160;
 for(u32 i=0;i<128;++i)expected[i]=(u8)(i*17+3);
 StatePoolMemoryCopyIn(&memory,pool.slots[2].offset,expected,128);
 memset(physical,0xA5,sizeof(physical));watch=true;
 if(!StateSlotPoolClearBanked(&pool,&memory,1))return 0;
 return pool.slots[2].offset==SUSAMUNE_STATE_POOL_SIZE-64;
}
__declspec(dllexport) u32 exportFlushedCompaction(void) {return requestSawFlushed;}
__declspec(dllexport) u32 exactPoolFlushes(void) {
 u32 count=0;for(u32 i=0;i<flushCount;++i){const CacheCall&f=flushed[i];
  if((f.address==testPool+SUSAMUNE_STATE_POOL_SIZE-64 && f.size==64) ||
     (f.address==testExtra && f.size==64))++count;}
 return count;
}
__declspec(dllexport) u32 extraInvalidated(u32 size) {
 for(u32 i=0;i<invalidateCount;++i)if(invalidated[i].address==testExtra && invalidated[i].size==size)return 1;return 0;}
__declspec(dllexport) u32 prepareMutation(void) {
 auto &h=testMailbox.header;memset(&h,0,sizeof(h));h.magic=SUSAMUNE_STATE_ARCHIVE_MAGIC;h.version=1;
 h.headerSize=sizeof(h);h.metadataSize=8;h.packedSize=100;h.rawSize=200;h.gameId=0x474D5345;
 h.buildCrc=12;h.snapshotVersion=15;h.configId=777;memcpy(h.name,"Original",9);
 h.headerCrc=SusamuneStateHeaderCrc(&h);
 return h.headerCrc;
}
__declspec(dllexport) void mutationReceipt(u32 corruption) {
 auto &h=testMailbox.header;
 acknowledge(0,0,0);auto &r=testMailbox.receipt;r.headerCrc=h.headerCrc;r.packedSize=h.packedSize;r.metadataSize=h.metadataSize;
 testMailbox.response.resultId=testMailbox.request.id;
 memcpy(testMailbox.resultName,"Renamed state",14);r.reserved=SusamuneStateCrc(testMailbox.resultName,32);
 if(corruption==1)testMailbox.resultName[0]^=1;if(corruption==2)testMailbox.response.resultId^=1;
 if(corruption==3)r.headerCrc^=1;if(corruption==4)h.headerCrc^=1;
}
__declspec(dllexport) u32 renamedResult(void) {
 StateStorage::Result r;if(!StateStorage::takeResult(r)||r.status||r.metadata||!SusamuneStateHeaderValid(&r.header))return 0;
 return r.name[0]=='R' && r.name[8]=='s' && r.header.name[0]=='O';
}
}
'''


class StateStorageClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists(): raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-state-client-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = (ROOT / 'src/state_storage.cpp').read_text()
        source = re.sub(r'^#(?:include|pragma) .*$', '', source, flags=re.M)
        start = source.index('#if IS_EMULATOR')
        end = source.index('#endif', start)+len('#endif')
        source = source[:start] + '''const size_t kMailbox=reinterpret_cast<size_t>(&testMailbox);
const size_t kStaging=reinterpret_cast<size_t>(testStaging);''' + source[end:]
        (path / 'test.cpp').write_text(PREAMBLE + source + EXPORTS)
        proc = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O1', '-DIS_EMULATOR=0',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT/'include'), str(path/'test.cpp'), '-o', str(path/'test.dll')], capture_output=True, text=True)
        if proc.returncode: raise RuntimeError(proc.stdout+proc.stderr)
        cls.lib = C.CDLL(str(path/'test.dll'))
        cls.lib.beginRename.argtypes = [C.c_uint, C.c_uint, C.c_char_p]
        cls.lib.mailbox.restype = C.c_void_p
        cls.pool_size,cls.staging_size=cls.lib.poolSize(),cls.lib.stagingSize()
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self): self.lib.reset(0)

    def test_all_four_receipt_identity_fields_must_match(self):
        self.assertEqual(self.lib.beginImport(100,0),1)
        for field in (1,2,3,4):
            self.lib.acknowledge(3,field,0);self.lib.tick()
            self.assertEqual(self.lib.busy(),1)
            self.assertEqual(self.lib.result(),999)
        self.lib.acknowledge(3,0,0);self.lib.tick()
        self.assertEqual(self.lib.busy(),0)
        self.assertEqual(self.lib.result(),3)

    def test_cancel_keeps_import_cache_ownership_until_own_receipt(self):
        self.assertEqual(self.lib.beginImport(0x400123,0x200000),1)
        old=self.lib.seq();self.lib.clearCacheLog()
        self.assertEqual(self.lib.cancel(),1)
        self.assertEqual(self.lib.command(),4)
        self.assertEqual(self.lib.stagingInvalidations(),0)
        self.lib.acknowledge(6,0,old);self.lib.tick()
        self.assertEqual(self.lib.busy(),1)
        self.assertEqual(self.lib.stagingInvalidations(),0)
        self.lib.acknowledge(6,0,0);self.lib.tick()
        self.assertEqual(self.lib.busy(),0)
        self.assertEqual(self.lib.stagingInvalidations(),1)
        self.assertEqual(self.lib.poolTailInvalidated(0x200000,0x123),1)
        self.assertEqual(self.lib.result(),6)

    def test_long_wait_never_unlocks_or_overwrites_request(self):
        self.assertEqual(self.lib.beginImport(100,0),1)
        seq=self.lib.seq()
        for _ in range(2000):self.lib.tick()
        self.assertEqual(self.lib.busy(),1)
        self.assertEqual(self.lib.beginExport(100,0),0)
        self.assertEqual(self.lib.seq(),seq)

    def test_reinjection_retires_prior_client_before_new_requests(self):
        self.lib.reset(400)
        self.assertEqual(self.lib.busy(),1)
        self.assertEqual(self.lib.seq(),401)
        self.assertEqual(self.lib.command(),4)
        self.assertEqual(self.lib.beginImport(100,0),0)
        self.lib.acknowledge(6,0,0);self.lib.tick()
        self.assertEqual(self.lib.result(),6)
        self.assertEqual(self.lib.beginImport(100,0),1)

    def test_export_fills_valid_crc_header_but_refuses_bad_ranges(self):
        for size,offset in ((0,0),(self.pool_size+1,0),(100,self.pool_size)):
            self.assertEqual(self.lib.beginExport(size,offset),0)
        self.assertEqual(self.lib.beginExport(100,32),1)
        self.assertEqual(self.lib.headerValid(),1)

    def test_old_launcher_refuses_extra_bank_and_new_launcher_splits_cache_ranges(self):
        self.assertEqual(self.lib.beginImport(self.staging_size+256,self.pool_size-16),0)
        self.lib.expand()
        self.assertEqual(self.lib.beginImport(self.staging_size+256,self.pool_size-16),1)
        self.lib.clearCacheLog();self.lib.acknowledge(3,0,0);self.lib.tick()
        self.assertEqual(self.lib.poolTailInvalidated(self.pool_size-16,16),1)
        self.assertEqual(self.lib.extraInvalidated(240),1)

    def test_previous_protocol_with_old_bank_boundary_exposes_no_service(self):
        self.assertGreater(self.lib.version(),3)
        for version in (2,3,4):
            with self.subTest(version=version):
                self.lib.reset(0)
                self.assertEqual(self.lib.setVersion(version),0)
                self.assertEqual(self.lib.beginImport(100,0),0)
                self.assertEqual(self.lib.beginExport(100,0),0)
                self.assertEqual(self.lib.beginRename(7,999,b'Name'),0)
                self.assertEqual(self.lib.beginDelete(7,999),0)
                self.assertEqual(self.lib.seq(),0)

    def test_current_protocol_requires_matching_full_primary_capability(self):
        self.assertEqual(self.lib.legacyLayout(),0)
        self.assertEqual(self.lib.beginImport(100,0),0)
        self.assertEqual(self.lib.beginExport(100,0),0)
        self.assertEqual(self.lib.seq(),0)

    def test_pending_import_keeps_its_latched_bank_map_if_capability_bytes_change(self):
        self.lib.expand()
        self.assertEqual(self.lib.beginImport(self.staging_size+256,self.pool_size-16),1)
        self.lib.revokeCapabilities()
        self.lib.clearCacheLog();self.lib.acknowledge(3,0,0);self.lib.tick()
        self.assertEqual(self.lib.poolTailInvalidated(self.pool_size-16,16),1)
        self.assertEqual(self.lib.extraInvalidated(240),1)
        self.assertEqual(self.lib.busy(),0)

    def test_export_flushes_dirty_compacted_slot_before_publishing_request(self):
        self.assertEqual(self.lib.prepareCompaction(),1)
        self.lib.clearCacheLog()
        self.assertEqual(self.lib.exportFlushedCompaction(),0)
        self.assertEqual(self.lib.beginExport(128,self.pool_size-64),1)
        self.assertEqual(self.lib.exactPoolFlushes(),2)
        self.assertEqual(self.lib.exportFlushedCompaction(),1,
                         'ARM must see both compacted pieces before the export request')

    def test_name_bounds_and_mutations_hold_ownership_through_receipt(self):
        for name in (None, b'', b'a'*32, b'a\nb', b'\xFF'):
            self.assertEqual(self.lib.beginRename(7,999,name),0)
        self.assertEqual(self.lib.beginRename(0,999,b'Name'),0)
        self.assertEqual(self.lib.beginDelete(100000000,999),0)
        for command in (5,6):
            with self.subTest(command=command):
                self.lib.reset(0)
                accepted = self.lib.beginRename(7,999,b'a'*31) if command==5 else self.lib.beginDelete(7,999)
                self.assertEqual(accepted,1)
                self.assertEqual(self.lib.command(),command)
                self.assertEqual(self.lib.cancel(),0)
                self.assertEqual(self.lib.beginImport(100,0),0)
                self.lib.acknowledge(7,3,0);self.lib.tick()
                self.assertEqual(self.lib.busy(),1)
                self.lib.acknowledge(7,0,0);self.lib.tick()
                self.assertEqual(self.lib.result(),7)
                self.assertEqual(self.lib.busy(),0)

    def test_effective_name_is_separate_from_immutable_header_and_has_receipt_crc(self):
        for corrupt in range(5):
            with self.subTest(corrupt=corrupt):
                self.lib.reset(0)
                crc=self.lib.prepareMutation()
                self.assertEqual(self.lib.beginRename(7,crc,b'Renamed state'),1)
                self.lib.mutationReceipt(corrupt);self.lib.tick()
                if corrupt:self.assertEqual(self.lib.result(),3)
                else:self.assertEqual(self.lib.renamedResult(),1)

    def test_window_bounds_and_verified_receipt_before_releasing_staging(self):
        for packed,offset,size in ((0,0,1),(100,100,1),(100,0,101),(100,0,0),
                                   (0x500000,0,self.staging_size+1),(100,0xffffffff,10)):
            self.assertEqual(self.lib.beginWindow(packed,offset,size,123),0)
        for corrupt in range(8):
            with self.subTest(corrupt=corrupt):
                self.lib.reset(0)
                crc=self.lib.prepareWindow(0x500123)
                self.assertEqual(self.lib.beginWindow(0x500123,0x400000,0x100123,crc),1)
                self.lib.clearCacheLog()
                self.lib.windowReceipt(corrupt);self.lib.tick()
                self.assertEqual(self.lib.result(),3 if corrupt else 0)
                self.assertEqual(self.lib.stagingInvalidations(),1)
                self.assertEqual(self.lib.busy(),0)

    def test_canceled_window_rejects_late_read_receipt_and_keeps_ownership(self):
        crc=self.lib.prepareWindow(0x500000)
        self.assertEqual(self.lib.beginWindow(0x500000,0x400000,0x100000,crc),1)
        old=self.lib.seq();self.lib.clearCacheLog()
        self.assertEqual(self.lib.cancel(),1)
        self.lib.acknowledge(0,0,old);self.lib.tick()
        self.assertEqual(self.lib.stagingInvalidations(),0)
        self.assertEqual(self.lib.busy(),1)
        self.lib.acknowledge(6,0,0);self.lib.tick()
        self.assertEqual(self.lib.result(),6)
        self.assertEqual(self.lib.stagingInvalidations(),1)


if __name__ == '__main__': unittest.main()
