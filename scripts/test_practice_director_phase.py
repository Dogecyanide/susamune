"""Keep frozen retail calls from changing the next active simulation tick count."""

import ctypes
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class PracticeDirectorPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="practice-phase-", dir=ROOT / "build")
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "phase.cpp"
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            "void beginFrozenDirector(bool frozen)", "void endFrozenDirector()"))
        source.write_text(r'''
using s32 = int;
struct TMarDirector { int mTickBudget; bool normal; } director, replacement;
TMarDirector *gpMarDirector, *sFrozenDirector;
s32 sFrozenTickBudget;
bool normalStage() { return gpMarDirector && gpMarDirector->normal; }
''' + functions + r'''
extern "C" __declspec(dllexport) void reset(int phase) {
    director={phase,true};replacement={91,true};gpMarDirector=&director;sFrozenDirector=nullptr;
}
extern "C" __declspec(dllexport) int frame(int dt,int frozen,int changed) {
    beginFrozenDirector(frozen!=0);
    gpMarDirector->mTickBudget+=dt;
    int ticks=0;
    do { gpMarDirector->mTickBudget-=5; ++ticks; } while(gpMarDirector->mTickBudget>=5);
    if(changed==1)gpMarDirector=&replacement;
    if(changed==2)gpMarDirector->normal=false;
    endFrozenDirector();
    return ticks;
}
extern "C" __declspec(dllexport) int phase(){return gpMarDirector->mTickBudget;}
extern "C" __declspec(dllexport) int oldPhase(){return director.mTickBudget;}
extern "C" __declspec(dllexport) int staleEnd(){endFrozenDirector();return gpMarDirector->mTickBudget;}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-std=c++17", "-O2", "-fno-exceptions", "-fno-rtti", "-ffreestanding",
            "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
            str(source), "-o", str(library),
        ], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)
        cls.dll.reset.argtypes = [ctypes.c_int]
        cls.dll.frame.argtypes = [ctypes.c_int] * 3
        cls.dll.frame.restype = ctypes.c_int

    def test_paused_wait_does_not_change_first_active_tick_count(self):
        for dt in (24, 12, 20):
            for phase in range(5):
                self.dll.reset(phase)
                baseline = self.dll.frame(dt, 0, 0)
                expected = self.dll.phase()
                self.dll.reset(phase)
                for _ in range(17):
                    self.dll.frame(dt, 1, 0)
                    self.assertEqual(self.dll.phase(), phase)
                self.assertEqual(self.dll.frame(dt, 0, 0), baseline)
                self.assertEqual(self.dll.phase(), expected)

    def test_active_calls_keep_fractional_cadence(self):
        self.dll.reset(0)
        self.assertEqual([self.dll.frame(24, 0, 0) for _ in range(5)], [4, 5, 5, 5, 5])
        self.assertEqual(self.dll.phase(), 0)
        self.assertEqual(self.dll.staleEnd(), 0)

    def test_changed_or_departing_director_is_not_rewound(self):
        self.dll.reset(0)
        self.dll.frame(24, 1, 1)
        self.assertEqual(self.dll.phase(), 91)
        self.assertEqual(self.dll.oldPhase(), 4)
        self.assertEqual(self.dll.staleEnd(), 91)
        self.dll.reset(0)
        self.dll.frame(24, 1, 2)
        self.assertEqual(self.dll.phase(), 4)
        self.assertEqual(self.dll.staleEnd(), 4)


if __name__ == "__main__":
    unittest.main()
