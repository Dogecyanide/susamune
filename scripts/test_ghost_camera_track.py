"""Run the production camera codec, cadence, interpolation and bank bounds."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class View(C.Structure):
    _fields_ = [('position', C.c_float * 3), ('rotation', C.c_float * 4),
                ('fovy', C.c_float)]


def view(x=0, quaternion=(0, 0, 0, 1), fov=45):
    return View((C.c_float * 3)(x, 2.125, -3.125),
                (C.c_float * 4)(*quaternion), fov)


class CameraTrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled compiler required')
        parent = ROOT / 'build/pr11-camera-check'
        parent.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.addClassCleanup(cls.temp.cleanup)
        cpp = Path(cls.temp.name) / 'camera.cpp'
        cpp.write_text(r'''
#include "susamune/ghost_camera.hxx"
#include "Dolphin/mem.h"
extern "C" int _fltused=0;
extern "C" void *memset(void*p,u32 n,size_t size){u8*b=(u8*)p;while(size--)*b++=(u8)n;return p;}
extern "C" float retailSquareRoot(float) asm("sqrtf__3stdFf");
extern "C" float retailSquareRoot(float n){if(!n)return 0;float x=n>1?n:1;for(int i=0;i<32;++i)x=(x+n/x)*0.5f;return x;}
extern "C" float fabsf(float n){return n<0?-n:n;}
GhostCamera::View current;
namespace GhostCamera {bool captureView(View*out){*out=current;return true;}}
#include "src/ghost_camera_track.cpp"
u8 bank[0x695e0+32];
#define API extern "C" __declspec(dllexport)
API void reset(){memset(bank,0xa5,sizeof(bank));GhostCamera::reset(bank);}
API int encode(const GhostCamera::View*v,unsigned q,unsigned f,void*out){return GhostCamera::encode(*v,q,(u8)f,(SusamuneGhostCameraSample*)out);}
API void decode(const void*p,GhostCamera::View*out){GhostCamera::decode(*(const SusamuneGhostCameraSample*)p,out);}
API void capture(const GhostCamera::View*v,unsigned q,unsigned segment){current=*v;GhostCamera::capture(bank,q,(u8)segment);}
API int evaluate(unsigned q,unsigned segment,GhostCamera::View*out){return GhostCamera::evaluate(bank,q,(u8)segment,out);}
API void trim(unsigned q,unsigned segment){GhostCamera::trim(bank,q,(u16)segment);}
API unsigned count(){return ((SusamuneGhostCameraHeader*)GhostCamera::prefix(bank))->count;}
API unsigned flags(){return ((SusamuneGhostCameraHeader*)GhostCamera::prefix(bank))->flags;}
API unsigned size(){return GhostCamera::prefixSize(bank);}
API int guards(){for(unsigned i=0;i<SUSAMUNE_GHOST_CAMERA_BANK_OFFSET;++i)if(bank[i]!=0xa5)return 0;
 for(unsigned i=SUSAMUNE_GHOST_CAMERA_BANK_OFFSET+SUSAMUNE_GHOST_CAMERA_MAX_SIZE;i<sizeof(bank);++i)if(bank[i]!=0xa5)return 0;return 1;}
API void negate(unsigned index){auto*k=(SusamuneGhostCameraSample*)((SusamuneGhostCameraHeader*)GhostCamera::prefix(bank)+1);for(unsigned i=13;i<21;i+=2){short n=(short)((k[index].bytes[i]<<8)|k[index].bytes[i+1]);n=-n;k[index].bytes[i]=(u16)n>>8;k[index].bytes[i+1]=(u8)n;}}
API void matrix(const GhostCamera::View*v,float*out){GhostCamera::matrix(*v,(float(*)[3])out);}
API int valid(const void*p){return SusamuneGhostCameraSampleValid((const u8*)p,0,72000,0,0,0,1);}
''')
        dll = cpp.with_suffix('.dll')
        result = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc',
            '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-fno-builtin',
            '-O2', '-ffast-math', '-I', str(ROOT / 'include'), '-I', str(ROOT), str(cpp), '-o', str(dll)],
            capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.encode.argtypes = [C.POINTER(View), C.c_uint, C.c_uint, C.c_void_p]
        cls.lib.decode.argtypes = [C.c_void_p, C.POINTER(View)]
        cls.lib.capture.argtypes = [C.POINTER(View), C.c_uint, C.c_uint]
        cls.lib.evaluate.argtypes = [C.c_uint, C.c_uint, C.POINTER(View)]
        cls.lib.matrix.argtypes = [C.POINTER(View), C.c_void_p]

    def setUp(self):
        self.lib.reset()

    def sample(self, v, qf=0, flags=0x40):
        out = C.create_string_buffer(24)
        self.assertEqual(self.lib.encode(C.byref(v), qf, flags, out), 1)
        return out

    def test_codec_quantization_and_invalid_views(self):
        v = view(-100.13, (0.2, 0.3, 0.4, 0.842614977), 46.123)
        sample = self.sample(v)
        self.assertEqual(self.lib.valid(sample), 1)
        actual = View()
        self.lib.decode(sample, C.byref(actual))
        for a, b in zip(v.position, actual.position):
            self.assertLessEqual(abs(a-b), 0.12501)
        self.assertLess(abs(v.fovy-actual.fovy), 1/512)
        for a, b in zip(v.rotation, actual.rotation):
            self.assertLess(abs(a-b), 0.0001)
        for bad in (view(float('nan')), view(3000000), view(fov=0),
                    view(quaternion=(0, 0, 0, 0))):
            self.assertEqual(self.lib.encode(C.byref(bad), 0, 0x40, sample), 0)

    def test_periodic_samples_interpolate_and_quaternion_sign_is_equivalent(self):
        for qf in range(31):
            self.lib.capture(C.byref(view(qf)), qf, 0)
        self.assertEqual(self.lib.count(), 3)
        self.lib.negate(1)
        out = View()
        self.assertEqual(self.lib.evaluate(7, 0, C.byref(out)), 1)
        self.assertAlmostEqual(out.position[0], 7, places=4)
        self.assertAlmostEqual(abs(out.rotation[3]), 1, places=4)
        matrix = (C.c_float * 9)()
        self.lib.matrix(C.byref(out), matrix)
        self.assertEqual(list(matrix), [1, 0, 0, 0, 1, 0, 0, 0, 1])

    def test_cuts_and_scene_boundaries_never_blend(self):
        self.lib.capture(C.byref(view(0)), 0, 0)
        self.lib.capture(C.byref(view(2000)), 10, 0)
        self.lib.capture(C.byref(view(3000)), 20, 1)
        out = View()
        self.assertEqual(self.lib.evaluate(9, 0, C.byref(out)), 1)
        self.assertEqual(out.position[0], 0)
        self.assertEqual(self.lib.evaluate(10, 0, C.byref(out)), 1)
        self.assertEqual(out.position[0], 2000)
        self.assertEqual(self.lib.evaluate(19, 1, C.byref(out)), 1)
        self.assertEqual(out.position[0], 3000)
        self.assertEqual(self.lib.evaluate(25, 2, C.byref(out)), 0)
        self.lib.trim(10, 1)
        self.assertEqual(self.lib.count(), 2)

    def test_ten_minutes_fit_and_pathological_cut_overflow_is_bounded(self):
        for qf in range(0, 71929, 4):
            self.lib.capture(C.byref(view(qf/100)), qf, 0)
        self.assertLessEqual(self.lib.count(), 4797)
        self.assertEqual(self.lib.flags(), 0)
        self.assertEqual(self.lib.guards(), 1)
        self.lib.reset()
        for qf in range(5314):
            self.lib.capture(C.byref(view(1000*(qf%2))), qf, 0)
        self.assertEqual(self.lib.count(), 5312)
        self.assertEqual(self.lib.size(), 127520)
        self.assertEqual(self.lib.flags(), 1)
        self.assertEqual(self.lib.guards(), 1)
        self.assertEqual(self.lib.evaluate(5313, 0, C.byref(View())), 0)


if __name__ == '__main__':
    unittest.main()
