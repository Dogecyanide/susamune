"""Run the production archive worker against bounded RAM and memory-backed FatFS."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
POOL, STAGING = 0xFA0000, 0x400000
EXPANDED = POOL + 0x200000
EXPORT, IMPORT, CATALOG, CANCEL = 1, 2, 3, 4
OK, IO, BAD, FULL, CANCELLED, STALE, CONFIG = 0, 2, 3, 4, 6, 7, 8


class Header(C.Structure):
    _fields_ = [(n, C.c_uint) for n in (
        'magic', 'version', 'headerSize', 'metadataSize', 'packedSize', 'rawSize',
        'gameId', 'buildCrc', 'snapshotVersion', 'configId', 'metadataCrc', 'payloadCrc',
        'headerCrc', 'sceneKey', 'reserved0', 'reserved1')] + [('name', C.c_char * 32)]


ADAPTER = r'''
#include "susamune/state_storage.h"
typedef int FRESULT;
static struct SusamuneStateStorageMailbox stateMailbox;
static u8 statePool[SUSAMUNE_STATE_POOL_SIZE + 64], stateStaging[SUSAMUNE_STATE_STAGING_SIZE + 64];
static u8 stateExtra[SUSAMUNE_STATE_POOL_EXTRA_SIZE + 64];
#define STATE_MAILBOX (&stateMailbox)
#define STATE_POOL (statePool + 32)
#define STATE_POOL_EXTRA (stateExtra + 32)
#define STATE_STAGING (stateStaging + 32)
static int f_mkdir_char(const char *p) { (void)p; return FR_EXIST; }
static bool failRename;
static int f_rename_char(const char *from,const char *to) {
 if(failRename) return FR_DISK_ERR;
 int index=lookup(from); if(index<0) return FR_NO_FILE;
 if(lookup(to)>=0) return FR_EXIST;
 copystr(testFiles[index].path,to); return FR_OK;
}
'''

EXPORTS = r'''
__declspec(dllexport) void reset(void) {
 testCount=writeCount=readBytes=readCalls=dirCalls=maxRead=writeBytes=0;
 failWriteAfter=0xFFFFFFFFu; failSync=failRename=false; directoryResult=FR_OK;
 memset(testFiles,0,sizeof(testFiles)); memset(statePool,0x5A,sizeof(statePool));
 memset(stateStaging,0xA5,sizeof(stateStaging)); memset(stateExtra,0xC3,sizeof(stateExtra)); SusamuneStateStorageInit();
}
__declspec(dllexport) void submit(u32 command,u32 id,u32 offset,u32 size,u32 crc,u32 session) {
 struct SusamuneStateRequest *r=&stateMailbox.request;
 ++r->seq; r->command=command; r->id=id; r->session=session;
 r->poolOffset=offset; r->packedSize=size; r->expectedHeaderCrc=crc; r->reserved=0;
}
__declspec(dllexport) int run(u32 limit) {
 for(u32 i=0;i<limit;++i) {
  u32 reads=readBytes,writes=writeBytes,dirs=dirCalls;
  if(!SusamuneStateStoragePending()) return (int)i;
  SusamuneStateStorageService();
  if(readBytes-reads>SUSAMUNE_STATE_CHUNK_SIZE || writeBytes-writes>SUSAMUNE_STATE_CHUNK_SIZE || dirCalls-dirs>16) return -2;
 }
 return SusamuneStateStoragePending()?-1:0;
}
__declspec(dllexport) void prepare(const void *data,u32 size,u32 offset,const void *meta,u32 metaSize) {
 struct SusamuneStateArchiveHeader *h=&stateMailbox.header;
 memset(h,0,sizeof(*h)); h->magic=SUSAMUNE_STATE_ARCHIVE_MAGIC; h->version=1;
 h->headerSize=sizeof(*h); h->metadataSize=metaSize; h->packedSize=size;
 h->rawSize=size*2; h->gameId=GAME_ID; h->buildCrc=123; h->snapshotVersion=15;
 h->configId=ConfigId; h->metadataCrc=SusamuneStateCrc(meta,metaSize);
 h->sceneKey=0x10203; memcpy(h->name,"Bianco 3",9);
 h->headerCrc=SusamuneStateHeaderCrc(h);
 memcpy(stateMailbox.metadata,meta,metaSize);
 u32 written=0;while(written<size){u32 piece=size-written;u8*target=PoolPiece(offset+written,&piece);
 memcpy(target,(const u8*)data+written,piece);written+=piece;}
}
__declspec(dllexport) int add(const char *path,const u8 *bytes,u32 size) {
 int i=lookup(path); if(i<0) i=(int)testCount++;
 if(i>=FIXTURE_FILES) return -1;
 copystr(testFiles[i].path,path); testFiles[i].bytes=bytes;
 testFiles[i].size=size; testFiles[i].live=1; testFiles[i].writable=0; return i;
}
__declspec(dllexport) const void *file(const char *p,u32 *size) {
 int i=lookup(p); if(i<0) {*size=0; return 0;} *size=testFiles[i].size; return testFiles[i].bytes;
}
__declspec(dllexport) const void *mailbox(void) {return &stateMailbox;}
__declspec(dllexport) const void *pool(void) {return STATE_POOL;}
__declspec(dllexport) const void *staging(void) {return STATE_STAGING;}
__declspec(dllexport) const void *extra(void) {return STATE_POOL_EXTRA;}
__declspec(dllexport) void failures(u32 after,u32 sync,u32 rename) {
 failWriteAfter=after; failSync=sync; failRename=rename;
}
__declspec(dllexport) u32 guards(void) {
 for(u32 i=0;i<32;++i) if(statePool[i]!=0x5A || statePool[32+SUSAMUNE_STATE_POOL_SIZE+i]!=0x5A ||
   stateStaging[i]!=0xA5 || stateStaging[32+SUSAMUNE_STATE_STAGING_SIZE+i]!=0xA5 ||
   stateExtra[i]!=0xC3 || stateExtra[32+SUSAMUNE_STATE_POOL_EXTRA_SIZE+i]!=0xC3) return 0;
 return 1;
}
'''


class StateStorageKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-state-files-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        fixture = (ROOT / 'scripts/ghost_kernel_fixture.h').read_text()
        fixture = fixture.replace('#define FIXTURE_FILES 60000', '#define FIXTURE_FILES 100')
        fixture = fixture.replace('#define FIXTURE_WRITES 80', '#define FIXTURE_WRITES 8')
        fixture = fixture.replace('#define FIXTURE_FILE_BYTES 1400000', '#define FIXTURE_FILE_BYTES 6000000')
        source = (ROOT / 'launcher/kernel/SusamuneStateStorage.c').read_text()
        source = re.sub(r'^#include .*$', '', source, flags=re.M)
        start = source.index('static u32 BootConfigId(void)')
        end = source.index('\nstatic void Paths(', start)
        source = source[:start] + 'static u32 BootConfigId(void) {return 6789u;}\n' + source[end:]
        (path / 'test.c').write_text(fixture + ADAPTER + source + EXPORTS)
        proc = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O1',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT / 'include'), str(path / 'test.c'), '-o', str(path / 'test.dll')],
            text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.submit.argtypes = [C.c_uint] * 6
        cls.lib.prepare.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.add.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]
        cls.lib.file.argtypes = [C.c_char_p, C.POINTER(C.c_uint)]
        for name in ('mailbox', 'pool', 'staging', 'extra', 'file'):
            getattr(cls.lib, name).restype = C.c_void_p

    def setUp(self):
        self.lib.reset()
        self.buffers = []

    def buffer(self, data):
        out = C.create_string_buffer(data)
        self.buffers.append(out)
        return out

    def command(self, command, id=0, offset=0, size=0, crc=0, session=11):
        self.lib.submit(command, id, offset, size, crc, session)

    def finish(self):
        self.assertGreaterEqual(self.lib.run(5000), 0)
        self.assertEqual(self.lib.guards(), 1)
        return C.c_uint.from_address(self.lib.mailbox() + 44).value

    def file(self, id=1, suffix='mss'):
        size = C.c_uint()
        pointer = self.lib.file(f'/moonshine_states/state_{id:08d}.{suffix}'.encode(), C.byref(size))
        return C.string_at(pointer, size.value) if pointer else None

    def add(self, id, data, suffix='mss'):
        self.lib.add(f'/moonshine_states/state_{id:08d}.{suffix}'.encode(), self.buffer(data), len(data))

    def export(self, data=b'opaque compressed payload' * 900, meta=b'owned game and profile metadata', offset=32):
        self.lib.prepare(self.buffer(data), len(data), offset, self.buffer(meta), len(meta))
        self.command(EXPORT, offset=offset, size=len(data))
        self.assertEqual(self.finish(), OK)
        return self.file(), data, meta

    def test_atomic_export_crc_and_roundtrip_across_two_bounded_segments(self):
        data = (bytes(range(256)) * ((STAGING + 12345) // 256 + 1))[:STAGING + 12345]
        archive, data, meta = self.export(data)
        h = Header.from_buffer_copy(archive)
        self.assertEqual(h.payloadCrc, zlib.crc32(data))
        self.assertEqual(h.metadataCrc, zlib.crc32(meta))
        check = bytearray(archive[:96]); check[48:52] = b'\0' * 4
        self.assertEqual(h.headerCrc, zlib.crc32(check))
        self.assertEqual(archive[96:], meta + data)
        self.assertIsNone(self.file(suffix='tmp'))
        self.lib.reset(); self.buffers = []; self.add(1, archive)
        self.command(IMPORT, 1, 0x200001, h.packedSize, h.headerCrc)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(C.string_at(self.lib.staging(), STAGING), data[:STAGING])
        self.assertEqual(C.string_at(self.lib.pool() + 0x200001, len(data) - STAGING), data[STAGING:])
        self.assertEqual(C.string_at(self.lib.pool(), 0x200001), b'Z' * 0x200001)

    def test_short_write_sync_and_rename_failure_preserve_existing_archive(self):
        archive, data, meta = self.export()
        for after, sync, rename in ((100, 0, 0), (0xFFFFFFFF, 1, 0), (0xFFFFFFFF, 0, 1)):
            with self.subTest(after=after, sync=sync, rename=rename):
                self.lib.reset(); self.buffers = []; self.add(1, archive)
                self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(meta), len(meta))
                self.lib.failures(after, sync, rename)
                self.command(EXPORT, offset=32, size=len(data))
                self.assertNotEqual(self.finish(), OK)
                self.assertEqual(self.file(1), archive)
                self.assertIsNone(self.file(2))
                self.assertIsNotNone(self.file(2, 'tmp'))

    def test_corrupt_truncated_extended_wrong_config_and_stale_files_refuse(self):
        archive, _, _ = self.export()
        h = Header.from_buffer_copy(archive)
        damaged = bytearray(archive); damaged[-1] ^= 0x80
        metadata = bytearray(archive); metadata[96] ^= 1
        wrong = bytearray(archive); changed = Header.from_buffer(wrong); changed.configId ^= 1
        changed.headerCrc = 0; changed.headerCrc = zlib.crc32(wrong[:96])
        for contents, crc, expected in ((archive[:-1], h.headerCrc, BAD), (archive+b'x', h.headerCrc, BAD),
                (damaged, h.headerCrc, BAD), (metadata, h.headerCrc, BAD),
                (archive, h.headerCrc ^ 1, STALE), (wrong, changed.headerCrc, CONFIG)):
            with self.subTest(expected=expected, size=len(contents)):
                self.lib.reset(); self.buffers = []; self.add(1, bytes(contents))
                self.command(IMPORT, 1, 0x200000, h.packedSize, crc)
                self.assertEqual(self.finish(), expected)
                self.assertEqual(C.string_at(self.lib.pool(), 0x200000), b'Z' * 0x200000)

    def test_capacity_rejects_before_any_staging_write(self):
        for offset, size in ((EXPANDED + 32, 10), (EXPANDED, STAGING + 1), (0, EXPANDED + 1), (0, 0)):
            self.command(IMPORT, 1, offset, size, 123)
            self.assertEqual(self.finish(), FULL)
            self.assertEqual(C.string_at(self.lib.staging(), 64), b'\xA5' * 64)

    def test_cancel_ack_retires_previous_writer_before_new_receipt(self):
        archive, _, _ = self.export(b'compressed bytes' * 30000)
        h = Header.from_buffer_copy(archive)
        self.lib.reset(); self.buffers=[]; self.add(1, archive)
        self.command(IMPORT, 1, 0, h.packedSize, h.headerCrc, 11)
        self.assertEqual(self.lib.run(6), -1)
        old_seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.command(CANCEL, session=22)
        new_seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.assertEqual(self.lib.run(1), -1)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+40).value, old_seq)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+64).value, 11)
        self.assertEqual(self.finish(), CANCELLED)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+40).value, new_seq)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+64).value, 22)
        before=C.string_at(self.lib.staging(), h.packedSize)
        self.assertGreaterEqual(self.lib.run(20), 0)
        self.assertEqual(C.string_at(self.lib.staging(), h.packedSize), before)

    def test_catalog_pages_sorted_ids_ignore_partial_and_bad_headers(self):
        archive, _, _ = self.export()
        self.lib.reset(); self.buffers=[]
        for id in (25, 7, 9, 4, 2, 22, 24, 6, 8, 3, 1, 5): self.add(id, archive)
        self.add(10, archive, 'tmp'); self.add(11, b'bad')
        self.command(CATALOG)
        self.assertEqual(self.finish(), OK)
        c = self.lib.mailbox()+192
        self.assertEqual([C.c_uint.from_address(c+i*4).value for i in range(4)], [8,0,8,1])
        self.assertEqual([C.c_uint.from_address(c+32+i*64).value for i in range(8)], list(range(1,9)))
        self.command(CATALOG, 8)
        self.assertEqual(self.finish(), OK)
        self.assertEqual([C.c_uint.from_address(c+i*4).value for i in range(4)], [4,8,25,0])
        self.assertEqual([C.c_uint.from_address(c+32+i*64).value for i in range(4)], [9,22,24,25])

    def test_export_and_import_split_exactly_at_noncontiguous_bank_boundary(self):
        archive, data, meta = self.export(b'bank-crossing-state' * 12000, offset=POOL-123)
        self.assertEqual(archive[96:], meta+data)
        data = (b'archive-tail-crosses-the-bank' * 200000)[:STAGING+45678]
        self.lib.reset(); self.buffers=[]
        archive,data,_ = self.export(data)
        h=Header.from_buffer_copy(archive)
        self.lib.reset();self.buffers=[];self.add(1,archive)
        self.command(IMPORT,1,POOL-123,h.packedSize,h.headerCrc)
        self.assertEqual(self.finish(),OK)
        self.assertEqual(C.string_at(self.lib.pool(),POOL-123),b'Z'*(POOL-123))
        self.assertEqual(C.string_at(self.lib.pool()+POOL-123,123),data[STAGING:STAGING+123])
        self.assertEqual(C.string_at(self.lib.extra(),len(data)-STAGING-123),data[STAGING+123:])

    def test_tail_memory_ownership_keeps_maximum_ghost_file(self):
        text = (ROOT / 'include/susamune/mem2_map.h').read_text()
        self.assertIn('0x0013E000u', text)
        self.assertGreaterEqual(0x13E000, 1297992)
        self.assertEqual(0x91CFF000 + 0x13E000, 0x91E3D000)
        self.assertEqual(0x91E3D000 + 8192, 0x91E3F000)
        self.assertEqual(0x713C0000 + 0x13E000 + 8192, 0x71500000)


if __name__ == '__main__':
    unittest.main()
