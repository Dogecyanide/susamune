"""Execute state prefix pins and recovery against the actual ARM trace worker."""
import ctypes as C
import importlib.util
import io
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest

P = Path(__file__).resolve().parents[1]
ROOT = P
while not (ROOT / "scripts/ghost_kernel_fixture.h").exists():
    ROOT = ROOT.parent
spec = importlib.util.spec_from_file_location("state_pin_writer", P / "scripts/test_ghost_trace_storage.py")
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)
BOOT, NEXT_BOOT, GAME = 0x12345678, 0x87654321, 0x474d534a

class Overlay:
    def __truediv__(self, name):
        candidate = P / name
        return candidate if candidate.exists() else ROOT / name

EXTRA = r'''
__declspec(dllexport) const void* checkpointFence(void){return &traceFence;}
__declspec(dllexport) int prepareRef(const void*v,unsigned project,unsigned id,unsigned generation){
 return GhostTraceStateReferencePrepare(v,GAME_ID,project,id,generation);
}
__declspec(dllexport) int storeRef(void){return GhostTraceStateReferenceStore();}
__declspec(dllexport) int releaseRef(void){return GhostTraceStateReferenceRelease();}
__declspec(dllexport) int recoverRef(unsigned begin){return GhostTraceStateReferenceRecover(begin);}
__declspec(dllexport) int cancelRef(void){return GhostTraceStateReferenceCancel();}
__declspec(dllexport) int extraPin(const void*b){return GhostTraceBranchStore(b,MS_TRACE_BRANCH_CHECKPOINT);}
__declspec(dllexport) unsigned recoveryPhase(void){return WRITER->recovery.phase;}
__declspec(dllexport) unsigned recoveryOpen(void){return WRITER->recovery.open||WRITER->recovery.directoryOpen;}
__declspec(dllexport) unsigned recoveryReady(void){return WRITER->recovery.phase==RECOVERY_COMMIT;}
__declspec(dllexport) unsigned retained(void){return WRITER->retained;}
__declspec(dllexport) unsigned readsCount(void){return readBytes;}
__declspec(dllexport) unsigned writesCount(void){return writeBytes;}
__declspec(dllexport) unsigned dirsCount(void){return dirCalls;}
__declspec(dllexport) void syncFailure(unsigned value){failSync=value;}
__declspec(dllexport) void stamp(unsigned index,unsigned first,unsigned last){traceMailbox.chunks[index].firstFrame=first;traceMailbox.chunks[index].lastFrame=last;}
__declspec(dllexport) const void* named(const char*p,unsigned*n){int i=lookup(p);if(i<0){*n=0;return NULL;}*n=testFiles[i].size;return testFiles[i].bytes;}
__declspec(dllexport) int shorten(const char*p,unsigned n){int i=lookup(p);if(i<0||n>testFiles[i].size)return 0;testFiles[i].size=n;return 1;}
__declspec(dllexport) void corrupt(const char*p,unsigned at,unsigned value){int i=lookup(p);if(i>=0&&testFiles[i].writable&&at<testFiles[i].size)((unsigned char*)testFiles[i].bytes)[at]=value;}
__declspec(dllexport) int install(const char*name,const void*p,unsigned n){FIL f;UINT done;return f_open_char(&f,name,FA_WRITE|FA_CREATE_NEW)==FR_OK&&f_write(&f,p,n,&done)==FR_OK&&done==n&&f_close(&f)==FR_OK;}
'''

class StateReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pr59-state-pins-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        fixture = (ROOT / "scripts/ghost_kernel_fixture.h").read_text()
        fixture = fixture.replace("#define FIXTURE_FILES 60000", "#define FIXTURE_FILES 64")
        fixture = fixture.replace("#define FIXTURE_WRITES 80", "#define FIXTURE_WRITES 24")
        fixture = fixture.replace("#define FIXTURE_FILE_BYTES 1400000", "#define FIXTURE_FILE_BYTES 3000000")
        fixture = fixture.replace("f_close(", "fixture_close(").replace("f_rename_char(", "fixture_rename(")
        exports = writer.EXPORTS.replace("failWriteAfter=0xffffffffu;", "failSync=0;readBytes=readCalls=dirCalls=0;failWriteAfter=0xffffffffu;")
        (folder / "test.c").write_text("#define MOONSHINE_GHOST_TRACE 1\n" + fixture + writer.ADAPTER +
                                      writer.writer_source(Overlay()) + exports + EXTRA)
        env = dict(os.environ, PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"])
        command = ["C:/msys64/mingw64/bin/gcc.exe", "-shared", "-O2", "-std=gnu99", "-fno-builtin", "-static",
                   "-DMOONSHINE_GHOST_TRACE=1", "-I", str(P / "include"), "-I", str(ROOT / "include"),
                   "-I", str(ROOT / "include/susamune"), str(folder / "test.c"),
                   str(ROOT / "launcher/kernel/GhostTraceCompression.c"), "-o", str(folder / "test.dll")]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(folder / "test.dll"))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.submit.argtypes = [C.c_uint] * 4
        cls.lib.chunk.argtypes = [C.c_uint] * 3 + [C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.response.restype = C.POINTER(C.c_uint)
        cls.lib.checkpointFence.restype = C.POINTER(C.c_uint)
        cls.lib.named.argtypes = [C.c_char_p, C.POINTER(C.c_uint)]
        cls.lib.named.restype = C.c_void_p
        cls.lib.prepareRef.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_uint]
        cls.lib.extraPin.argtypes = [C.c_void_p]
        cls.lib.shorten.argtypes = [C.c_char_p, C.c_uint]
        cls.lib.corrupt.argtypes = [C.c_char_p, C.c_uint, C.c_uint]
        cls.lib.install.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]

    def setUp(self):
        self.lib.identity(GAME, BOOT)
        self.lib.reset()
        self.lib.submit(1, 1, 0, BOOT)
        self.lib.run(300)
        self.assertEqual(self.lib.response()[4], 2)

    def path(self, suffix="part", run=1):
        return f"/Moonshine data/ghosts/recordings/trace_{BOOT:08X}_{run:08X}.{suffix}".encode()

    def data(self, path):
        size = C.c_uint()
        pointer = self.lib.named(path, C.byref(size))
        return C.string_at(pointer, size.value) if pointer else None

    def chunk(self, sequence, data):
        self.lib.chunk((sequence - 1) & 1, 1, sequence, data, len(data), 0)
        self.lib.stamp((sequence - 1) & 1, sequence * 8 - 7, sequence * 8)

    def fence(self, sequence=1, payload=None):
        self.chunk(sequence, payload if payload is not None else b"prefix" * 200)
        self.lib.submit(4, 1, sequence, BOOT)
        self.lib.run(500)
        self.assertEqual(self.lib.response()[4], 2)
        fence = list(self.lib.checkpointFence()[:8])
        self.assertEqual(self.lib.response()[6], sequence)
        prefix = [BOOT, 1, sequence, sequence * 8, sequence * 4, sequence, fence[3], fence[4]]
        return struct.pack("<24I", 0x4d534743, 1, *prefix, GAME, 0x200, 0x4ff, 99, *fence, 0, 0)

    def prepare(self, reference, id=1, generation=77, project=0):
        self.assertEqual(self.lib.prepareRef(reference, project, id, generation), 1)

    def store(self, reference, id=1, generation=77, project=0):
        self.prepare(reference, id, generation, project)
        self.assertEqual(self.lib.storeRef(), 1)

    def discard(self):
        self.lib.submit(3, 1, 0, BOOT)
        self.lib.run(500)
        self.assertEqual(self.lib.response()[4], 5)

    def reboot(self, reference, id=1, generation=77):
        self.lib.identity(GAME, NEXT_BOOT)
        self.prepare(reference, id, generation)

    def recover(self):
        result = self.lib.recoverRef(1)
        for _ in range(2000):
            if result:
                return result
            before = self.lib.readsCount(), self.lib.writesCount(), self.lib.dirsCount()
            result = self.lib.recoverRef(0)
            self.assertLessEqual(self.lib.readsCount() - before[0], 128)
            self.assertLessEqual(self.lib.writesCount() - before[1], 32)
            self.assertLessEqual(self.lib.dirsCount() - before[2], 1)
        self.fail("recovery did not settle")

    def branch(self, reference, id=2, generation=78):
        words = struct.unpack("<24I", reference)
        return struct.pack("<24I", words[2], words[3], words[10], words[12], *words[2:10],
                           *words[14:22], 0x80000000, id, generation, 0)

    def test_export_pin_owns_active_draft_after_ram_ownership_is_gone(self):
        reference = self.fence()
        self.store(reference)
        self.assertEqual(self.lib.retained(), 1)
        before = self.data(self.path())
        self.discard()
        self.assertEqual(self.data(self.path()), before)
        self.reboot(reference)
        self.assertEqual(self.recover(), 1)
        self.assertIsNone(self.data(self.path()))
        self.assertEqual(self.data(self.path("msgt"))[:-32], before)

    def test_missing_durable_fence_or_wrong_identity_cannot_pin(self):
        reference = bytearray(self.fence())
        reference[56:88] = bytes(32)
        self.assertEqual(self.lib.prepareRef(bytes(reference), 0, 1, 77), 0)
        reference = bytearray(self.fence(2))
        struct.pack_into("<I", reference, 76, 0x12345678)
        self.prepare(bytes(reference))
        self.assertEqual(self.lib.storeRef(), 0)
        self.assertEqual(self.lib.retained(), 0)

    def test_exact_owner_generation_including_crc_zero(self):
        reference = self.fence()
        self.store(reference, generation=0)
        self.prepare(reference, generation=1)
        self.assertEqual(self.lib.releaseRef(), 0)
        self.prepare(reference, generation=0)
        self.assertEqual(self.lib.releaseRef(), 1)
        self.assertEqual(self.lib.releaseRef(), 0)

    def test_failed_pin_publication_keeps_a_conservative_reference(self):
        reference = self.fence()
        self.prepare(reference)
        self.lib.failures(0xffffffff, 0, 1)
        self.assertEqual(self.lib.storeRef(), 0)
        self.lib.failures(0xffffffff, 0, 0)
        self.assertEqual(self.lib.retained(), 1)
        self.discard()
        self.assertIsNotNone(self.data(self.path()))
        self.reboot(reference)
        self.assertEqual(self.recover(), 1)

    def test_recovery_keeps_other_states_complete_future_prefixes(self):
        first = self.fence(1, random.Random(2).randbytes(200000))
        self.store(first)
        second = self.fence(2, b"second" * 10000)
        self.store(second, id=2, generation=78)
        complete = self.data(self.path())
        self.chunk(3, b"unfinished" * 50000)
        self.lib.run(1)
        self.discard()
        self.assertGreater(len(self.data(self.path())), len(complete))
        self.reboot(first)
        reads = self.lib.readsCount()
        self.assertEqual(self.recover(), 1)
        self.assertLess(self.lib.readsCount() - reads, 4096)
        final = self.data(self.path("msgt"))
        self.assertEqual(final[:-32], complete)
        self.assertEqual(struct.unpack_from(">I", final, len(final) - 24)[0], 2)

    def test_missing_later_owned_bytes_refuses_without_truncation(self):
        first = self.fence(1)
        self.store(first)
        second = self.fence(2, b"later" * 10000)
        self.store(second, id=2, generation=78)
        self.discard()
        self.assertEqual(self.lib.shorten(self.path(), len(self.data(self.path())) - 1), 1)
        before = self.data(self.path())
        self.reboot(first)
        writes = self.lib.writesCount()
        self.assertEqual(self.recover(), -1)
        self.assertEqual(self.lib.writesCount(), writes)
        self.assertEqual(self.data(self.path()), before)
        self.assertIsNone(self.data(self.path("msgt")))

    def test_existing_done_footer_is_preserved_exactly(self):
        reference = self.fence()
        self.store(reference)
        self.lib.failures(0xffffffff, 0, 1)
        self.lib.submit(2, 1, 1, BOOT)
        self.lib.run(500)
        self.lib.failures(0xffffffff, 0, 0)
        before = self.data(self.path())
        self.assertEqual(before[-32:-28], b"DONE")
        self.reboot(reference)
        writes = self.lib.writesCount()
        self.assertEqual(self.recover(), 1)
        self.assertEqual(self.lib.writesCount(), writes)
        self.assertEqual(self.data(self.path("msgt")), before)

    def test_new_reference_after_scan_forces_another_scan(self):
        reference = self.fence()
        self.store(reference)
        self.discard()
        self.reboot(reference)
        self.assertEqual(self.lib.recoverRef(1), 0)
        for _ in range(200):
            if self.lib.recoveryReady():
                break
            self.assertEqual(self.lib.recoverRef(0), 0)
        self.assertEqual(self.lib.recoveryReady(), 1)
        self.assertEqual(self.lib.extraPin(self.branch(reference)), 1)
        self.assertEqual(self.lib.recoverRef(0), 0)
        self.assertEqual(self.lib.recoveryReady(), 0)
        for _ in range(200):
            result = self.lib.recoverRef(0)
            if result:
                break
        self.assertEqual(result, 1)

    def test_bad_reference_record_blocks_mutation(self):
        reference = self.fence()
        self.store(reference)
        self.discard()
        self.assertEqual(self.lib.install(b"/Moonshine data/ghosts/recordings/uncertain.mbpt", b"x" * 128, 128), 1)
        before = self.data(self.path())
        self.reboot(reference)
        self.assertEqual(self.recover(), -1)
        self.assertEqual(self.data(self.path()), before)
        self.assertIsNone(self.data(self.path("msgt")))

    def test_close_failure_retains_worker_ownership_until_exact_close(self):
        reference = self.fence()
        self.store(reference)
        self.discard()
        self.reboot(reference)
        self.assertEqual(self.lib.recoverRef(1), 0)
        self.lib.failures(0xffffffff, 1, 0)
        self.assertEqual(self.lib.cancelRef(), 0)
        self.assertEqual(self.lib.recoveryOpen(), 1)
        self.lib.run(5)
        self.assertEqual(self.lib.recoveryOpen(), 1)
        self.lib.failures(0xffffffff, 0, 0)
        self.lib.run(5)
        self.assertEqual(self.lib.recoveryOpen(), 0)
        self.assertIsNotNone(self.data(self.path()))
        self.assertIsNone(self.data(self.path("msgt")))

if __name__ == "__main__":
    unittest.main()
