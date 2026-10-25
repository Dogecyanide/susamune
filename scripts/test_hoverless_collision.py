"""Exercise the production Hoverless journal and collision edge clipper."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HoverlessCollisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-hoverless-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        fixture = (ROOT / "scripts/ghost_kernel_fixture.h").read_text()
        fixture = fixture[:fixture.index("#ifndef TEST_TRANSFER_EXTERNAL")]
        fixture = fixture.replace("#define FIXTURE_FILES 60000", "#define FIXTURE_FILES 8")
        fixture = fixture.replace("#define FIXTURE_WRITES 80", "#define FIXTURE_WRITES 8")
        fixture = fixture.replace("#define FIXTURE_FILE_BYTES 1400000", "#define FIXTURE_FILE_BYTES 1024")
        code = fixture + r'''
#include "susamune/hoverless.h"
#include "susamune/collision_projection.h"
enum { FR_INVALID_PARAMETER=20, FR_INVALID_OBJECT=21 };
int _fltused=0;
static struct SusamuneHoverlessCfg box;
#undef SUSAMUNE_HOVERLESS_PHYS_PTR
#define SUSAMUNE_HOVERLESS_PHYS_PTR (&box)
static bool PbGenerationIsNewer(u32 a,u32 b) { return (s32)(a-b)>0; }
'''
        code += (ROOT / "launcher/kernel/SusamuneHoverless.inc").read_text()
        code += r'''
__declspec(dllexport) void reset(void) {
 memset(testFiles,0,sizeof(testFiles));testCount=writeCount=writeBytes=0;
 failWriteAfter=0xffffffffu; InitHoverless("jp");
}
__declspec(dllexport) int save(int value,unsigned profile) {
 box.values[10]=value;box.activeProfile=profile;++box.saveSeq;
 if(HoverlessPending())ServiceHoverless();
 return box.status;
}
__declspec(dllexport) void reboot(void) { InitHoverless("jp"); }
__declspec(dllexport) int value(void) { return box.values[10]; }
__declspec(dllexport) int profile(void) { return box.activeProfile; }
__declspec(dllexport) int writable(void) { return HoverlessReady; }
__declspec(dllexport) unsigned generation(void) { return HoverlessGeneration; }
__declspec(dllexport) void failWrite(void) { failWriteAfter=writeBytes+50; }
__declspec(dllexport) int oldIntact(void) {
 const int i=lookup(HoverlessPaths[HoverlessActive]);
 return i>=0 && SusamuneHoverlessValid((const struct SusamuneHoverlessFile*)testFiles[i].bytes,GAME_ID);
}
__declspec(dllexport) void future(void) {
 const int i=lookup(HoverlessPaths[HoverlessActive]);
 struct SusamuneHoverlessFile *f=(struct SusamuneHoverlessFile*)testFiles[i].bytes;
 ++f->rule; f->checksum=SusamuneHoverlessChecksum(f);
}
__declspec(dllexport) int clip(float *a,float *b,float nearPlane,float farPlane) {
 return SusamuneCollisionClip(a,b,nearPlane,farPlane);
}
'''
        (folder / "fixture.c").write_text(code)
        result = subprocess.run([str(ROOT / "toolchain/clang.exe"),
            "--target=x86_64-pc-windows-msvc", "-shared", "-O1", "-fno-builtin",
            "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
            "-I", str(ROOT / "include"), str(folder / "fixture.c"),
            "-o", str(folder / "fixture.dll")], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.dll = C.CDLL(str(folder / "fixture.dll"))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.dll._handle))
        cls.dll.clip.argtypes = [C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_float, C.c_float]

    def setUp(self):
        self.dll.reset()

    def test_new_profile_roundtrip_and_alternating_generation(self):
        self.assertEqual(self.dll.value(), -1)
        self.assertEqual(self.dll.profile(), 255)
        self.assertEqual(self.dll.save(1234, 4), 0)
        self.assertEqual(self.dll.save(1200, 4), 0)
        self.dll.reboot()
        self.assertEqual((self.dll.value(), self.dll.profile(), self.dll.generation()), (1200, 4, 2))

    def test_short_write_preserves_last_valid_copy(self):
        self.assertEqual(self.dll.save(1234, 4), 0)
        self.dll.failWrite()
        self.assertNotEqual(self.dll.save(1200, 4), 0)
        self.assertTrue(self.dll.oldIntact())
        self.dll.reboot()
        self.assertEqual(self.dll.value(), 1234)
        self.assertFalse(self.dll.writable())

    def test_future_rule_is_not_overwritten(self):
        self.assertEqual(self.dll.save(1234, 4), 0)
        self.dll.future()
        self.dll.reboot()
        self.assertFalse(self.dll.writable())

    def test_invalid_profile_and_time_refused(self):
        self.assertNotEqual(self.dll.save(1234, 5), 0)
        self.assertNotEqual(self.dll.save(-2, 4), 0)

    def edge(self, a, b):
        a, b = (C.c_float * 3)(*a), (C.c_float * 3)(*b)
        return self.dll.clip(a, b, 1, 100), list(a), list(b)

    def test_near_crossing_and_behind_camera(self):
        ok, a, b = self.edge([0, 0, -2], [0, 0, 10])
        self.assertTrue(ok)
        self.assertAlmostEqual(a[2], 1)
        self.assertEqual(self.edge([0, 0, -2], [0, 0, -1])[0], 0)

    def test_viewport_and_far_clipping(self):
        ok, a, b = self.edge([-100, 0, 10], [100, 0, 10])
        self.assertTrue(ok)
        self.assertAlmostEqual(a[0], -10, places=4)
        self.assertAlmostEqual(b[0], 10, places=4)
        self.assertEqual(self.edge([0, 0, 101], [0, 0, 102])[0], 0)


if __name__ == "__main__":
    unittest.main()
