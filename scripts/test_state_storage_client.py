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
static u8 testExtra[SUSAMUNE_STATE_POOL_EXTRA_SIZE];static bool expanded;
static StatePoolMemory statePoolMemory() {StatePoolMemory m={{testPool,testExtra},{SUSAMUNE_STATE_POOL_SIZE,
 expanded?SUSAMUNE_STATE_POOL_EXTRA_SIZE:0}};return m;}
struct CacheCall {const void *address;u32 size;};
static CacheCall flushed[32],invalidated[32]; static u32 flushCount,invalidateCount;
static void DCFlushRange(void *p,u32 n) {if(flushCount<32)flushed[flushCount++]={p,n};}
static void DCInvalidateRange(void *p,u32 n) {if(invalidateCount<32)invalidated[invalidateCount++]={p,n};}
static u64 OSGetTime() {return 0x123456789ABCULL;}
namespace StateStorage {
struct Result {u32 command,status,id;SusamuneStateArchiveHeader header;const void *metadata;};
bool busy();
}
'''
EXPORTS = r'''
extern "C" {
__declspec(dllexport) void reset(u32 pending) {
 memset(&testMailbox,0,sizeof(testMailbox));
 testMailbox.response.magic=SUSAMUNE_STATE_STORAGE_MAGIC;
 testMailbox.response.version=SUSAMUNE_STATE_STORAGE_VERSION;
 testMailbox.response.available=1;testMailbox.response.configId=123;
 testMailbox.request.seq=pending;flushCount=invalidateCount=0;expanded=false;
 StateStorage::init();
}
__declspec(dllexport) u32 beginImport(u32 size,u32 offset) {return StateStorage::startImport(7,999,size,offset);}
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
__declspec(dllexport) void expand(void) {expanded=true;}
__declspec(dllexport) u32 extraInvalidated(u32 size) {
 for(u32 i=0;i<invalidateCount;++i)if(invalidated[i].address==testExtra && invalidated[i].size==size)return 1;return 0;}
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
        for size,offset in ((0,0),(0xFA0001,0),(100,0xFA0000)):
            self.assertEqual(self.lib.beginExport(size,offset),0)
        self.assertEqual(self.lib.beginExport(100,32),1)
        self.assertEqual(self.lib.headerValid(),1)

    def test_old_launcher_refuses_extra_bank_and_new_launcher_splits_cache_ranges(self):
        self.assertEqual(self.lib.beginImport(0x400100,0xFA0000-16),0)
        self.lib.expand()
        self.assertEqual(self.lib.beginImport(0x400100,0xFA0000-16),1)
        self.lib.clearCacheLog();self.lib.acknowledge(3,0,0);self.lib.tick()
        self.assertEqual(self.lib.poolTailInvalidated(0xFA0000-16,16),1)
        self.assertEqual(self.lib.extraInvalidated(240),1)


if __name__ == '__main__': unittest.main()
