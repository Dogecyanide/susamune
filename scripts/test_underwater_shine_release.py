"""Exercise the production shine-release helper and audit its retail call sites."""

import ctypes
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

from audit_practice_hooks import Dol
from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]
REGIONS = {
    "jp": (0x801204B8, 0x800FC568, 0x808D97E8),
    "us": (0x80241378, 0x802A8AFC, 0x808D9FB8),
    "pal": (0x80239104, 0x802A0BA4, 0x808D9EE0),
}


class ShineReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "shine.cpp"
        source.write_text(r'''
using u32 = unsigned;
using u16 = unsigned short;
static bool diving;
bool retailDivingMap() { return diving; }
struct TMario {
    enum { STATE_IDLE = 0x0C400201 };
    u32 mState, previous, argument, calls, requested, force;
    u16 mSubState, mSubStateTimer;
    void changePlayerStatus(u32 state, u32 arg, bool forced) {
        ++calls; requested = state; force = forced; previous = mState;
        mState = state; argument = arg; mSubState = mSubStateTimer = 0;
    }
};
''' + function_source(ROOT / "src/features.cpp", "void releaseShineMario(") + r'''
extern "C" __declspec(dllexport) unsigned run(unsigned underwater, unsigned field) {
    TMario mario = {0x1302, 0x891, 0xABCD, 0, 0, 0, 1, 99};
    diving = underwater;
    releaseShineMario(&mario);
    switch (field) {
    case 0: return mario.mState;
    case 1: return mario.previous;
    case 2: return mario.argument;
    case 3: return mario.calls;
    case 4: return mario.requested;
    case 5: return mario.force;
    case 6: return mario.mSubState;
    default: return mario.mSubStateTimer;
    }
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc", "-std=c++17", "-O2",
            "-fno-exceptions", "-fno-rtti", "-ffreestanding", "-shared",
            "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", str(source),
            "-o", str(library),
        ], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.dll._handle)
        cls.dll.run.argtypes = [ctypes.c_uint, ctypes.c_uint]
        cls.dll.run.restype = ctypes.c_uint

    def test_land_preserves_old_cave_state_writes(self):
        self.assertEqual([self.dll.run(0, i) for i in range(8)],
                         [0x0C400201, 0x891, 0xABCD, 0, 0, 0, 0, 0])

    def test_underwater_uses_native_forced_status_transition(self):
        self.assertEqual([self.dll.run(1, i) for i in range(8)],
                         [0x891, 0x1302, 0, 1, 0x891, 1, 0, 0])


class RetailShineAuditTests(unittest.TestCase):
    def test_regional_return_path_and_diving_predicate(self):
        for region, (win, diving, global_load) in REGIONS.items():
            with self.subTest(region=region):
                path = ROOT / f"build/timewarp-sd-retail/{region}-0/main.dol"
                if not path.exists():
                    self.skipTest("User-supplied retail DOLs are not present")
                dol = Dol(path)
                # r31 is the callee-saved Mario pointer; LR is restored after
                # the release site, so a nested C call keeps the retail return.
                self.assertEqual(dol.words(win, 5), (
                    0x7C0802A6, 0x90010004, 0x9421FFE8, 0x93E10014, 0x7C7F1B78))
                self.assertEqual(dol.words(win + 0xAC, 2), (0xB01F0084, 0x4800001C))
                self.assertEqual(dol.words(win + 0xCC, 6), (
                    0x8001001C, 0x38600000, 0x83E10014, 0x38210018, 0x7C0803A6, 0x4E800020))
                self.assertEqual(dol.words(diving, 13), (
                    global_load, 0x38600000, 0x8804007C, 0x28000039,
                    0x40820008, 0x38600001, 0x2800002C, 0x40820008,
                    0x38600001, 0x28000010, 0x4C820020, 0x38600001, 0x4E800020))


if __name__ == "__main__":
    unittest.main()
