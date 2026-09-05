"""Compile production tape capability and observer handoff gates for host checks."""

from pathlib import Path
import ctypes
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def function_source(path, signature):
    source = path.read_text(encoding="utf-8")
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class PracticeTapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("bundled Windows host compiler unavailable")
        cls.folder = tempfile.TemporaryDirectory()
        cls.libraries = []
        capability = function_source(ROOT / "src/practice_session.cpp", "bool tapeStorageReady()")
        observer = function_source(ROOT / "src/ghost.cpp", "void afterDirect(s32 appState)")
        shim = r'''
#include "susamune/ghost_storage.h"
#include "susamune/practice_input.h"
static_assert(SUSAMUNE_CONSOLE_PRACTICE_TAPE_PPC_BASE == 0x91880100u, "console tape base");
static_assert(SUSAMUNE_CONSOLE_PRACTICE_TAPE_PHYS_BASE == 0x11880100u, "ARM alias");
static_assert(SUSAMUNE_DOLPHIN_PRACTICE_TAPE_PPC_BASE == 0x71100100u, "Dolphin tape base");
static_assert(SUSAMUNE_PRACTICE_TAPE_SIZE == 65536u, "tape capacity");
static_assert(SUSAMUNE_PRACTICE_TAPE_OFFSET >= SUSAMUNE_GHOST_STORAGE_HEADER_SIZE, "live doorbells");
static_assert(SUSAMUNE_PRACTICE_TAPE_OFFSET + SUSAMUNE_PRACTICE_TAPE_SIZE <= SUSAMUNE_GHOST_SECONDARY_HEAP_OFFSET, "model heap");
struct Frame { SusamunePracticeInput input; unsigned fingerprint; };
static_assert(sizeof(Frame) * 4096u == SUSAMUNE_PRACTICE_TAPE_SIZE, "sample capacity");
static SusamuneGhostStorageMailbox testMailbox;
static unsigned cacheOffset, cacheSize;
#undef SUSAMUNE_GHOST_STORAGE_PPC_PTR
#define SUSAMUNE_GHOST_STORAGE_PPC_PTR (&testMailbox)
void DCInvalidateRange(void *address, unsigned size) {
    cacheOffset = (unsigned)((char *)address - (char *)&testMailbox);
    cacheSize = size;
}
typedef int s32;
struct TApplication { enum { CONTEXT_DIRECT_MAIN_LOOP = 1 }; };
struct TMarDirector { enum { STATE_NORMAL = 4 }; unsigned mCurState; };
static TMarDirector director;
static TMarDirector *gpMarDirector;
static bool running, sObserverMarioBaselineFinalized, sObserverMarioOwned;
static unsigned released;
bool observerRunning() { return running; }
void releaseObserverMario(bool) { ++released; }
'''
        wrapper = r'''
extern "C" __declspec(dllexport) int ready(unsigned magic, unsigned version, unsigned flags) {
    testMailbox.response.responseMagic = magic;
    testMailbox.response.protocolVersion = (unsigned short)version;
    testMailbox.response.flags = (unsigned short)flags;
    cacheOffset = cacheSize = 0;
    return tapeStorageReady();
}
extern "C" __declspec(dllexport) unsigned cache(unsigned which) {
    return which ? cacheSize : cacheOffset;
}
extern "C" __declspec(dllexport) unsigned tapeBase() {
    return SUSAMUNE_PRACTICE_TAPE_PPC_BASE;
}
extern "C" __declspec(dllexport) unsigned observerRelease(int state, unsigned ownership, unsigned stage) {
    running = (ownership & 1u) != 0;
    sObserverMarioBaselineFinalized = (ownership & 2u) != 0;
    sObserverMarioOwned = (ownership & 4u) != 0;
    director.mCurState = stage;
    gpMarDirector = stage == 0xff ? 0 : &director;
    released = 0;
    afterDirect(state);
    return released;
}
'''
        for emulator in (0, 1):
            source = Path(cls.folder.name) / f"gates_{emulator}.cpp"
            library = source.with_suffix(".dll")
            source.write_text(shim + capability + observer + wrapper)
            subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc",
                            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
                            f"-DIS_EMULATOR={emulator}", "-I", str(ROOT / "include"),
                            str(source), "-o", str(library)], check=True)
            cls.libraries.append(ctypes.CDLL(str(library)))

    @classmethod
    def tearDownClass(cls):
        handles = [library._handle for library in cls.libraries]
        cls.libraries.clear()
        for handle in handles:
            ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(handle))
        cls.folder.cleanup()

    def test_console_requires_exact_protocol_but_not_mounted_storage(self):
        console = self.libraries[0]
        for flags in (0, 1, 2):
            self.assertTrue(console.ready(0x53475354, 4, flags))
            self.assertEqual((console.cache(0), console.cache(1)), (32, 32))
        for magic, version in ((0, 4), (0x53475354, 3), (0x53475354, 5)):
            self.assertFalse(console.ready(magic, version, 1))

    def test_dolphin_uses_its_own_window_without_arm_mailbox_access(self):
        dolphin = self.libraries[1]
        self.assertTrue(dolphin.ready(0, 0, 0))
        self.assertEqual((dolphin.cache(0), dolphin.cache(1)), (0, 0))
        self.assertEqual(dolphin.tapeBase(), 0x71100100)
        self.assertEqual(self.libraries[0].tapeBase() & 0xffffffff, 0x91880100)

    def test_observer_keeps_both_ordinary_director_return_values(self):
        library = self.libraries[0]
        for state in (0, 1):
            self.assertEqual(library.observerRelease(state, 7, 4), 0)
        for state, stage in ((2, 4), (5, 4), (1, 9), (1, 0xff)):
            self.assertEqual(library.observerRelease(state, 7, stage), 1)
        for ownership in (0, 1, 3, 5, 6):
            self.assertEqual(library.observerRelease(5, ownership, 4), 0)


if __name__ == "__main__":
    unittest.main()
