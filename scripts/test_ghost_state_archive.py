"""Actual archive publication/import/delete with actual streamed-checkpoint pins."""
import ctypes as C
import importlib.util
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest

P = Path(__file__).resolve().parents[1]
ROOT = P
while not (ROOT / "scripts/ghost_kernel_fixture.h").exists():
    ROOT = ROOT.parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

writer = load("archive_pin_writer", P / "scripts/test_ghost_trace_storage.py")
archive = load("archive_pin_archive", P / "scripts/test_state_storage_kernel.py")
BOOT, GAME = 0x12345678, 0x474d534a

class Overlay:
    def __truediv__(self, name):
        path = P / name
        return path if path.exists() else ROOT / name

RENAME = r'''
static unsigned missingPinAtPublication;
static int f_rename_char(const char*from,const char*to) {
 if(failRename)return FR_DISK_ERR;
 int index=lookup(from);if(index<0)return FR_NO_FILE;
 if(lookup(to)>=0)return FR_EXIST;
 unsigned length=(unsigned)strlen(to);
 if(length>4&&!strcmp(to+length-4,".mss")) {
  const struct SusamuneStateArchiveHeader*h=(const void*)testFiles[index].bytes;
  if(h->reserved[0]==MS_STATE_TRACE_REFERENCE_MAGIC) {
   const struct MsTraceStateReference*v=(const void*)(testFiles[index].bytes+sizeof(*h)+h->reserved[1]);
   char pin[160];_sprintf(pin,"%s/ghosts/recordings/ref_%08X_%08X_%08X_%08X_%08X.msgb",
    SusamuneCfgStoragePrefix(),v->prefix.nonce,v->prefix.run,MS_TRACE_OWNER_STATE|TasContext.projectId,FileId,h->metadataCrc);
   if(lookup(pin)<0)++missingPinAtPublication;
  }
 }
 copystr(testFiles[index].path,to);return FR_OK;
}
'''
EXTRA = r'''
__declspec(dllexport) const void* makeCheckpoint(void) {
 static struct MsTraceStateReference v;
 testProof.word[MGM_NONCE]=0x12345678u;GhostTraceStorageInit();
 traceMailbox.request=(struct MsTraceRequest){MS_TRACE_MAGIC,MS_TRACE_VERSION,0x12345678,1,MS_TRACE_START,1,0x200,0x4ff};
 GhostTraceStorageService();
 memset(traceBuffers[0]+32,0x5a,400000);
 traceMailbox.chunks[0]=(struct MsTraceChunk){1,1,400000,MsTraceHash(2166136261u,traceBuffers[0]+32,400000),1,8,{0,0}};
 traceMailbox.request.sequence=2;traceMailbox.request.operation=MS_TRACE_FENCE;traceMailbox.request.scene=1;
 for(unsigned i=0;i<200&&GhostTraceStoragePending();++i)GhostTraceStorageService();
 memset(&v,0,sizeof(v));v.magic=MS_TRACE_CHECKPOINT_MAGIC;v.version=1;
 v.prefix=(struct MsTracePrefix){0x12345678,1,1,8,4,1,400000,traceFence.checksum};
 v.game=GAME_ID;v.scene=0x200;v.capabilities=0x4ff;v.fence=traceFence;
 return traceMailbox.response.ackRequest==2?&v:NULL;
}
__declspec(dllexport) void referenceHeader(unsigned offset){
 stateMailbox.header.reserved[0]=MS_STATE_TRACE_REFERENCE_MAGIC;stateMailbox.header.reserved[1]=offset;
 stateMailbox.header.snapshotVersion=19;stateMailbox.header.headerCrc=SusamuneStateHeaderCrc(&stateMailbox.header);
}
__declspec(dllexport) unsigned publicationReady(void){return Phase==RENAME_FILE;}
__declspec(dllexport) unsigned pinOrderErrors(void){return missingPinAtPublication;}
__declspec(dllexport) void traceDiscard(void){
 traceMailbox.request.sequence++;traceMailbox.request.operation=MS_TRACE_DISCARD;
 for(unsigned i=0;i<200&&GhostTraceStoragePending();++i)GhostTraceStorageService();
}
__declspec(dllexport) void traceReboot(void){testProof.word[MGM_NONCE]=0x87654321u;GhostTraceStorageInit();}
__declspec(dllexport) void poisonMetadata(void){memset(stateMailbox.metadata,0xee,sizeof(stateMailbox.metadata));}
__declspec(dllexport) unsigned refExists(unsigned id,unsigned generation){
 char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/ref_%08X_%08X_%08X_%08X_%08X.msgb",0x12345678,1,MS_TRACE_OWNER_STATE,id,generation);
 return lookup(p)>=0;
}
__declspec(dllexport) unsigned ioReads(void){return readBytes;}
__declspec(dllexport) int duplicateArchive(const char*name){
 const char*source="/Moonshine data/states/state_00000001.mss";int i=lookup(source);FIL f;UINT done;
 return i>=0&&f_open_char(&f,name,FA_WRITE|FA_CREATE_NEW)==FR_OK&&
  f_write(&f,testFiles[i].bytes,testFiles[i].size,&done)==FR_OK&&done==testFiles[i].size&&f_close(&f)==FR_OK;
}
__declspec(dllexport) int projectReference(unsigned project,unsigned id,unsigned generation){
 const struct MsTraceStateReference*v=(const void*)(stateMailbox.metadata+64);
 return GhostTraceStateReferencePrepare(v,GAME_ID,project,id,generation)&&GhostTraceStateReferenceStore();
}
__declspec(dllexport) unsigned projectPin(unsigned project,unsigned id,unsigned generation){
 char p[160];_sprintf(p,"/Moonshine data/ghosts/recordings/ref_%08X_%08X_%08X_%08X_%08X.msgb",0x12345678,1,MS_TRACE_OWNER_STATE|project,id,generation);
 return lookup(p)>=0;
}
__declspec(dllexport) int projectCleanup(const char*path,unsigned project,unsigned id){return StateGhostUnlink(path,project,id);}

'''
class StateArchivePinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pr59-archive-pins-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        fixture = (ROOT / "scripts/ghost_kernel_fixture.h").read_text()
        fixture = fixture.replace("#define FIXTURE_FILES 60000", "#define FIXTURE_FILES 64")
        fixture = fixture.replace("#define FIXTURE_WRITES 80", "#define FIXTURE_WRITES 24")
        fixture = fixture.replace("#define FIXTURE_FILE_BYTES 1400000", "#define FIXTURE_FILE_BYTES 3000000")
        for name in ("f_open_char", "f_unlink_char", "f_read", "f_close", "f_rename_char", "f_mkdir_char"):
            replacement = {"f_open_char":"fixture_open", "f_unlink_char":"fixture_unlink",
                           "f_read":"fixture_read", "f_close":"fixture_close", "f_rename_char":"fixture_rename", "f_mkdir_char":"fixture_mkdir"}[name]
            fixture = fixture.replace(name + "(", replacement + "(")
        fixture = fixture.replace("int live; int writable;", "int live; int writable; int directory;")
        fixture = fixture.replace("info->fsize=testFiles[i].size; return FR_OK;",
                                  "info->fsize=testFiles[i].size;info->fattrib=testFiles[i].directory?AM_DIR:0;return FR_OK;")
        fixture = fixture.replace("info->fsize=v->size; return FR_OK;",
                                  "info->fsize=v->size;info->fattrib=v->directory?AM_DIR:0;return FR_OK;")
        state_adapter = re.sub(r"static int f_rename_char\(.*?\n\}", "static int f_rename_char(const char*,const char*);", archive.ADAPTER, flags=re.S)
        trace_adapter = re.sub(r"static int f_rename_char\(.*?\n", "", writer.ADAPTER)
        trace_adapter = trace_adapter.replace(",renameFailure;", ";")
        source = (P / "launcher/kernel/SusamuneStateStorage.c").read_text()
        for name in ("SusamuneTasStorage.inc", "GhostStateArchive.inc"):
            source = source.replace('#include "' + name + '"', (P / "launcher/kernel" / name).read_text())
        source = re.sub(r"^#include .*$", "", source, flags=re.M)
        begin = source.index("static u32 BootConfigId(void)")
        end = source.index("\nstatic void Paths(", begin)
        source = source[:begin] + "static u32 BootConfigId(void){return 6789u;}\n" + source[end:]
        exports = archive.EXPORTS.replace("SusamuneStateStorageInit();\n}", "testProof.word[MGM_NONCE]=0x12345678;GhostTraceStorageInit();missingPinAtPublication=0;SusamuneStateStorageInit();\n}", 1)
        code = "#define MOONSHINE_GHOST_TRACE 1\n" + fixture + state_adapter + trace_adapter
        code += writer.writer_source(Overlay()) + source + RENAME + exports + EXTRA
        (folder / "test.c").write_text(code)
        command = ["C:/msys64/mingw64/bin/gcc.exe", "-shared", "-O2", "-std=gnu99", "-fno-builtin", "-static",
                   "-DMOONSHINE_GHOST_TRACE=1", "-I", str(P / "include"), "-I", str(ROOT / "include"),
                   "-I", str(ROOT / "include/susamune"), str(folder / "test.c"),
                   str(ROOT / "launcher/kernel/GhostTraceCompression.c"), "-o", str(folder / "test.dll")]
        result = subprocess.run(command, capture_output=True, text=True,
                                env=dict(os.environ, PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"]))
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(folder / "test.dll"))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.makeCheckpoint.restype = C.c_void_p
        cls.lib.mailbox.restype = C.c_void_p
        cls.lib.prepare.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.submit.argtypes = [C.c_uint] * 6
        cls.lib.file.argtypes = [C.c_char_p, C.POINTER(C.c_uint)]
        cls.lib.file.restype = C.c_void_p
        cls.lib.openFailure.argtypes = [C.c_char_p]
        cls.lib.requestName.argtypes = [C.c_char_p]
        cls.lib.duplicateArchive.argtypes = [C.c_char_p]
        cls.lib.projectCleanup.argtypes = [C.c_char_p, C.c_uint, C.c_uint]

    def setUp(self):
        self.lib.reset()
        pointer = self.lib.makeCheckpoint()
        self.assertTrue(pointer)
        self.reference = C.string_at(pointer, 96)
        self.payload = b"state-payload" * 150
        self.metadata = bytes(64) + self.reference + bytes(32)
        self.lib.prepare(self.payload, len(self.payload), 0, self.metadata, len(self.metadata))
        self.lib.referenceHeader(64)

    def response(self):
        return list((C.c_uint * 8).from_address(self.lib.mailbox() + 32))

    def header(self):
        return archive.Header.from_buffer_copy(C.string_at(self.lib.mailbox() + 96, 96))

    def data(self, path):
        size = C.c_uint()
        p = self.lib.file(path, C.byref(size))
        return C.string_at(p, size.value) if p else None

    def settle(self):
        self.assertGreaterEqual(self.lib.run(5000), 0)

    def publish(self):
        self.lib.submit(1, 0, 0, len(self.payload), 0, 1)
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertEqual(self.lib.pinOrderErrors(), 0)
        self.assertEqual(self.lib.refExists(1, self.header().metadataCrc), 1)
        return self.header()

    def test_pin_is_durable_before_archive_publication(self):
        h = self.publish()
        self.assertEqual(self.data(b"/Moonshine data/states/state_00000001.mss")[96:96 + len(self.metadata)], self.metadata)
        self.assertEqual(self.lib.refExists(1, h.metadataCrc), 1)

    def test_late_ppc_metadata_mutation_cannot_change_pinned_file_identity(self):
        original = self.header()
        self.lib.submit(1, 0, 0, len(self.payload), 0, 1)
        for _ in range(200):
            if self.lib.publicationReady():
                break
            self.lib.run(1)
        self.assertEqual(self.lib.publicationReady(), 1)
        self.lib.poisonMetadata()
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertEqual(self.lib.refExists(1, original.metadataCrc), 1)
        self.assertEqual(self.lib.pinOrderErrors(), 0)
        self.assertEqual(self.data(b"/Moonshine data/states/state_00000001.mss")[96:96 + len(self.metadata)], self.metadata)

    def test_pin_failure_does_not_publish_archive(self):
        h = self.header()
        path = f"/Moonshine data/ghosts/recordings/ref_{BOOT:08X}_00000001_80000000_00000001_{h.metadataCrc:08X}.mbpt".encode()
        self.lib.openFailure(path)
        self.lib.submit(1, 0, 0, len(self.payload), 0, 1)
        self.settle()
        self.assertNotEqual(self.response()[3], 0)
        self.assertIsNone(self.data(b"/Moonshine data/states/state_00000001.mss"))

    def test_delete_failure_retains_pin_and_success_releases_exact_pin(self):
        h = self.publish()
        self.lib.unlinkFailure(1)
        self.lib.submit(6, 1, 0, 0, h.headerCrc, 2)
        self.settle()
        self.assertNotEqual(self.response()[3], 0)
        self.assertEqual(self.lib.refExists(1, h.metadataCrc), 1)
        self.lib.unlinkFailure(0)
        self.lib.submit(6, 1, 0, 0, h.headerCrc, 3)
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertEqual(self.lib.refExists(1, h.metadataCrc), 0)
        self.assertIsNone(self.data(b"/Moonshine data/states/state_00000001.mss"))

    def test_rename_preserves_reference_identity(self):
        h = self.publish()
        self.lib.poisonMetadata()
        self.lib.requestName(b"Retained source")
        self.lib.submit(5, 1, 0, 0, h.headerCrc, 2)
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertEqual(self.lib.refExists(1, h.metadataCrc), 1)

    def test_import_recovers_discarded_source_after_reboot_without_prefix_copy(self):
        h = self.publish()
        self.lib.traceDiscard()
        self.assertIsNotNone(self.data(b"/Moonshine data/ghosts/recordings/trace_12345678_00000001.part"))
        self.lib.traceReboot()
        reads = self.lib.ioReads()
        self.lib.submit(2, 1, 0, len(self.payload), h.headerCrc, 2)
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertIsNotNone(self.data(b"/Moonshine data/ghosts/recordings/trace_12345678_00000001.msgt"))
        self.assertLess(self.lib.ioReads() - reads, 16384)

    def test_imported_name_adoption_pins_before_publishing_owned_id(self):
        h = self.publish()
        self.assertEqual(self.lib.duplicateArchive(b"/Moonshine data/states/imported.mss"), 1)
        self.lib.submit(3, 0, 0, 0, 0, 2)
        self.settle()
        self.assertEqual(self.response()[3], 0)
        self.assertEqual(self.lib.refExists(2, h.metadataCrc), 1)
        self.assertIsNotNone(self.data(b"/Moonshine data/states/state_00000002.mss"))
        self.assertIsNone(self.data(b"/Moonshine data/states/imported.mss"))
        self.assertEqual(self.lib.pinOrderErrors(), 0)

    def test_project_cleanup_releases_only_its_exact_reference_namespace(self):
        h = self.publish()
        path = b"/Moonshine data/tas/tas_00000007/state_00000005.mss"
        self.assertEqual(self.lib.duplicateArchive(path), 1)
        self.assertEqual(self.lib.projectReference(7, 5, h.metadataCrc), 1)
        self.assertEqual(self.lib.projectPin(7, 5, h.metadataCrc), 1)
        self.assertEqual(self.lib.projectCleanup(path, 7, 5), 0)
        self.assertEqual(self.lib.projectPin(7, 5, h.metadataCrc), 0)
        self.assertEqual(self.lib.refExists(1, h.metadataCrc), 1)
        self.assertIsNotNone(self.data(b"/Moonshine data/states/state_00000001.mss"))

if __name__ == "__main__":
    unittest.main()
