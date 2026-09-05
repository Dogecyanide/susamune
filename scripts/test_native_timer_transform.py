"""Check timer matrix composition and conservative clip rounding in native C."""
import ctypes
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NativeTimerTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clang = ROOT / "toolchain/clang.exe"
        if sys.platform != "win32" or not clang.exists():
            raise unittest.SkipTest("Bundled Windows compiler required for native C fixture")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-timer-draw-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = work / "test.c"
        source.write_text('''#include "susamune/native_timer_transform.h"
int _fltused;
__declspec(dllexport) int floorScale(int x,int p) { return SusamuneTimerScaleFloor(x,p); }
__declspec(dllexport) int ceilScale(int x,int p) { return SusamuneTimerScaleCeil(x,p); }
__declspec(dllexport) void basis(float *m,int p) { SusamuneTimerScaleBasis(m,p); }
''', encoding="ascii")
        library = work / "timer.dll"
        subprocess.run([str(clang), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, capture_output=True, text=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(
            ctypes.c_void_p(cls.dll._handle)))
        for name in ("floorScale", "ceilScale"):
            getattr(cls.dll, name).argtypes = [ctypes.c_int, ctypes.c_int]
            getattr(cls.dll, name).restype = ctypes.c_int
        cls.dll.basis.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int]

    def test_clip_rounding_encloses_both_signed_edges(self):
        for percent in range(50, 201, 2):
            for value in range(-1280, 1281):
                self.assertEqual(self.dll.floorScale(value, percent),
                                 math.floor(value * percent / 100))
                self.assertEqual(self.dll.ceilScale(value, percent),
                                 math.ceil(value * percent / 100))

    def test_scale_composes_with_rotation_preserving_translation_and_depth(self):
        original = [0, -1, 0, 200, 1, 0, 0, 30, 0, 0, 1, 4]
        for percent in range(50, 201, 2):
            matrix = (ctypes.c_float * 12)(*original)
            self.dll.basis(matrix, percent)
            for i, value in enumerate(original):
                expected = value * percent / 100 if i % 4 < 2 else value
                self.assertAlmostEqual(matrix[i], expected, places=6)

    def test_default_is_identity_and_repeated_draws_start_from_snapshot(self):
        original = [1, 0, 0, 31, 0, 1, 0, 71, 0, 0, 1, 0]
        for _ in range(100):
            matrix = (ctypes.c_float * 12)(*original)
            self.dll.basis(matrix, 100)
            self.assertEqual(list(matrix), original)


if __name__ == "__main__":
    unittest.main()
