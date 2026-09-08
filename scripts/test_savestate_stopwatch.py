"""Run the production mission-stopwatch rebase across save and restore delays."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/savestate.cpp"


class SavestateStopwatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        source = r'''
typedef long long OSTime;
struct OSStopwatch {
    char *mName; OSTime mTotal; int mHits; OSTime mMin, mMax, mLast; bool mActive;
};
struct Director { OSStopwatch mStopwatch; } director;
static Director *gpMarDirector;
static OSTime now;
static unsigned int clockReads, stores, badStore;
OSTime OSGetTime() { ++clockReads; return now; }
void DCStoreRange(void *address, unsigned int size) {
    ++stores;
    if (address != &director.mStopwatch || size != sizeof(OSStopwatch)) ++badStore;
}
'''
        source += function_source(SOURCE, "void rebaseMissionStopwatch(")
        source += r'''
#define API extern "C" __declspec(dllexport)
API void setup(OSTime clock, OSTime last, OSTime total, unsigned int active,
               unsigned int present) {
    now = clock; clockReads = stores = badStore = 0;
    gpMarDirector = present ? &director : 0;
    director.mStopwatch.mLast = last;
    director.mStopwatch.mTotal = total;
    director.mStopwatch.mHits = 7;
    director.mStopwatch.mMin = 23;
    director.mStopwatch.mMax = 456;
    director.mStopwatch.mActive = active != 0;
}
API void clockAt(OSTime clock) { now = clock; }
API void rebase(OSTime previous) { rebaseMissionStopwatch(previous); }
API OSTime elapsed() {
    const OSStopwatch &watch = director.mStopwatch;
    return watch.mTotal + (watch.mActive ? now - watch.mLast : 0);
}
API OSTime last() { return director.mStopwatch.mLast; }
API unsigned int unchangedFields(unsigned int active, OSTime total) {
    const OSStopwatch &watch = director.mStopwatch;
    return watch.mTotal == total && watch.mHits == 7 && watch.mMin == 23 &&
           watch.mMax == 456 && watch.mActive == (active != 0);
}
API unsigned int get(unsigned int key) {
    return key == 0 ? stores : key == 1 ? badStore : clockReads;
}
'''
        shim = Path(cls.folder.name) / "stopwatch.cpp"
        shim.write_text(source, encoding="ascii")
        library = shim.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(shim), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.setup.argtypes = [C.c_longlong, C.c_longlong, C.c_longlong, C.c_uint, C.c_uint]
        cls.lib.setup.restype = None
        for name in ("clockAt", "rebase"):
            getattr(cls.lib, name).argtypes = [C.c_longlong]
            getattr(cls.lib, name).restype = None
        for name in ("elapsed", "last"):
            getattr(cls.lib, name).argtypes = []
            getattr(cls.lib, name).restype = C.c_longlong
        cls.lib.unchangedFields.argtypes = [C.c_uint, C.c_longlong]
        cls.lib.unchangedFields.restype = C.c_uint
        cls.lib.get.argtypes = [C.c_uint]
        cls.lib.get.restype = C.c_uint

    def test_save_delay_preserves_elapsed_and_countdown_then_resumes(self):
        # Use 64-bit tick values; seconds fit poorly as a truncation regression.
        start, saved_at, blocked, total = 1 << 40, (1 << 40) + 1250, 1 << 34, 317
        self.lib.setup(saved_at, start, total, 1, 1)
        saved_elapsed = self.lib.elapsed()
        self.lib.clockAt(saved_at + blocked)
        self.lib.rebase(saved_at)
        self.assertEqual(self.lib.elapsed(), saved_elapsed)
        self.assertEqual(10000 - self.lib.elapsed(), 10000 - saved_elapsed)
        self.assertEqual(self.lib.last(), start + blocked)
        self.assertEqual(self.lib.unchangedFields(1, total), 1)
        self.assertEqual([self.lib.get(i) for i in (0, 1)], [1, 0])
        self.lib.clockAt(saved_at + blocked + 77)
        self.assertEqual(self.lib.elapsed(), saved_elapsed + 77)

    def test_load_rewinds_to_saved_elapsed_including_restore_work(self):
        start, saved_at, total = 1 << 41, (1 << 41) + 375, 91
        self.lib.setup(saved_at, start, total, 1, 1)
        saved_elapsed = self.lib.elapsed()
        load_completed = saved_at + (1 << 35) + 823
        # The heap restore reinstates the saved watch before rebasing its origin.
        self.lib.setup(load_completed, start, total, 1, 1)
        self.assertGreater(self.lib.elapsed(), saved_elapsed)
        self.lib.rebase(saved_at)
        self.assertEqual(self.lib.elapsed(), saved_elapsed)
        self.assertEqual(self.lib.last(), start + load_completed - saved_at)
        self.assertEqual(self.lib.unchangedFields(1, total), 1)

    def test_stopped_watch_keeps_accumulated_time_and_activity_flag(self):
        self.lib.setup(10000, 120, 478, 0, 1)
        self.lib.rebase(500)
        self.assertEqual(self.lib.elapsed(), 478)
        self.assertEqual(self.lib.unchangedFields(0, 478), 1)

    def test_missing_director_is_harmless_and_touches_no_clock_or_cache(self):
        self.lib.setup(10000, 120, 478, 1, 0)
        self.lib.rebase(500)
        self.assertEqual(self.lib.last(), 120)
        self.assertEqual([self.lib.get(i) for i in (0, 1, 2)], [0, 0, 0])

    def test_both_save_outcomes_rebase_after_compression_before_interrupts(self):
        save = function_source(SOURCE, "bool SavestateManager::saveState()")
        failure = function_source(SOURCE, "if (!fits)")
        success = save[save.index(failure) + len(failure):]
        call = "rebaseMissionStopwatch(h->save_time);"
        self.assertEqual(save.count(call), 2)
        self.assertLess(save.index("StateCodec::compress("), save.index(failure))
        for branch in (failure, success):
            self.assertEqual(branch.count(call), 1)
            self.assertLess(branch.index(call), branch.index("unmuteAudioDma(dma);"))
            self.assertLess(branch.index(call), branch.index("OSRestoreInterrupts(ints);"))
        self.assertLess(success.index("StateSlotPoolCommit("), success.index(call))

    def test_restore_rebases_saved_time_after_decode_and_before_interrupts(self):
        load = function_source(SOURCE, "bool SavestateManager::loadSlot(")
        call = "rebaseMissionStopwatch(h->save_time);"
        self.assertEqual(load.count(call), 1)
        started = "const OSTime restoreStarted = OSGetTime();"
        failed_call = "rebaseMissionStopwatch(restoreStarted);"
        failed = function_source(SOURCE, "if (restored != StateCodec::SUCCESS)")
        self.assertEqual(load.count(failed_call), 1)
        self.assertLess(load.index(started), load.index("StateCodec::decompress("))
        self.assertLess(load.index("StateCodec::decompress("), load.index(failed))
        self.assertIn(failed_call, failed)
        self.assertNotIn(call, failed, "Rejected states must not rewind a live watch")
        self.assertLess(failed.index(failed_call), failed.index("unmuteAudioDma(dma);"))
        self.assertLess(failed.index(failed_call), failed.index("OSRestoreInterrupts(ints);"))
        self.assertLess(load.index("StateCodec::decompress("), load.index(call))
        self.assertLess(load.index("GXInvalidateTexAll();"), load.index(call))
        success = load[load.index(call):]
        self.assertLess(success.index(call), success.index("OSRestoreInterrupts(ints);"))


if __name__ == "__main__":
    unittest.main()
