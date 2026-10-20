"""Execute the production collision hook's admission and GX handoff on the host."""
import ctypes as C
import _ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CollisionRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-collision-hook-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / "src/collision_render.cpp").read_text()
        source = re.sub(r"^#include.*\n", "", source, flags=re.M)
        source = re.sub(r'\s+asm\("[^"\n]+"\)', "", source)
        source = source.replace("reinterpret_cast<u32>", "reinterpret_cast<unsigned long long>")
        source = source.replace("u32 collisionEfbVtable", "unsigned long long collisionEfbVtable")
        prelude = r'''
using u8=unsigned char;using u32=unsigned int;using f32=float;using Mtx44=float[4][4];
enum{SETTING_COLLISION_VIEWER,GX_PERSPECTIVE=0,GX_ORTHOGRAPHIC=1};
namespace JDrama {struct TEfbCtrlTex{const char *mKeyName;};struct TGraphics{};}
bool hidden,modal,menuShown,wheelShown,drawn;
unsigned events,originalCalls,drawCalls,restoreCalls,projectionCalls;float saved[7],restored[7];
unsigned wireframeEnds;
unsigned wireframeInits;
struct Settings{unsigned mode;unsigned get(int){return mode;}}gSettings;
struct Menu{bool shown(){return menuShown;}}menu,*gMenu=&menu;
namespace PracticeSession {bool hideHud(){return hidden;}}
namespace StageLoader {bool modal(){return ::modal;}}
namespace WarpWheel {bool shown(){return wheelShown;}}
namespace GameWireframe {void init(){++wireframeInits;}void endWorld(){++wireframeEnds;}}
namespace CollisionViewer {
void init();void beginFrame(){};
bool drawWorld(){++drawCalls;events=events*10+1;return drawn;}
}
void DCFlushRange(void*,unsigned){}
extern "C" {
int _fltused=0;unsigned long long collisionEfbVtable[9];
void *memset(void *p,int v,unsigned long long n){auto b=(u8*)p;while(n--)*b++=v;return p;}
void collisionRetailEfbPerform(JDrama::TEfbCtrlTex*,u32,JDrama::TGraphics*){
 ++originalCalls;events=events*10+4;
}
void ReInitializeGX(){++restoreCalls;events=events*10+2;}
void GXGetProjectionv(float *p){for(int i=0;i<7;++i)p[i]=saved[i];}
}
void GXSetProjection(Mtx44 m,u8 type){
 ++projectionCalls;events=events*10+3;
 restored[0]=type;restored[1]=m[0][0];restored[2]=m[0][type==0?2:3];
 restored[3]=m[1][1];restored[4]=m[1][type==0?2:3];
 restored[5]=m[2][2];restored[6]=m[2][3];
}
'''
        exports = r'''
#define API extern "C" __declspec(dllexport)
API void run(unsigned choice){
 hidden=modal=menuShown=wheelShown=false;drawn=true;gSettings.mode=2;
 events=originalCalls=drawCalls=restoreCalls=projectionCalls=0;
 wireframeEnds=0;
 auto name=(char*)0x81000000;
 for(unsigned i=0;i<sizeof(kNormalScene);++i)name[i]=kNormalScene[i];
 JDrama::TEfbCtrlTex object={name};unsigned cue=8;
 for(int i=0;i<7;++i){saved[i]=i?i*0.125f:0;restored[i]=-1;}
 if(choice==1)gSettings.mode=0;
 if(choice==2)cue=0x80;
 if(choice==3)name[0]='x';
 if(choice==4)hidden=true;
 if(choice==5)modal=true;
 if(choice==6)menuShown=true;
 if(choice==7)wheelShown=true;
 if(choice==8)drawn=false;
 if(choice==9)saved[0]=1;
 if(choice==10)object.mKeyName=(const char*)0x7fffffff;
 if(choice==11)object.mKeyName=(const char*)0x817fffff;
 collisionScenePerform(&object,cue,nullptr);
}
API unsigned eventOrder(){return events;}
API unsigned wireframeEndCount(){return wireframeEnds;}
API unsigned install(unsigned kind){
 wireframeInits=0;for(auto &entry:collisionEfbVtable)entry=0;
 if(kind)collisionEfbVtable[4]=kind==1?(unsigned long long)&collisionRetailEfbPerform:(unsigned long long)&collisionScenePerform;
 CollisionViewer::init();return wireframeInits;
}
API unsigned counts(){return originalCalls+drawCalls*16+restoreCalls*256+projectionCalls*4096;}
API int projectionMatches(){for(int i=0;i<7;++i)if(saved[i]!=restored[i])return 0;return 1;}
'''
        folder = Path(cls.temp.name)
        (folder / "fixture.cpp").write_text(prelude + source + exports)
        subprocess.run([str(ROOT / "toolchain/clang++.exe"),
                        "--target=x86_64-pc-windows-msvc", "-shared", "-O1", "-fno-builtin",
                        "-nostdlib", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        str(folder / "fixture.cpp"), "-o", str(folder / "fixture.dll")],
                       check=True, capture_output=True, text=True)
        cls.dll = C.CDLL(str(folder / "fixture.dll"))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.dll._handle))
        kernel = C.WinDLL("kernel32", use_last_error=True)
        kernel.VirtualAlloc.restype = C.c_void_p
        kernel.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, C.c_uint]
        kernel.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, C.c_uint]
        arena = kernel.VirtualAlloc(0x81000000, 4096, 0x3000, 4)
        if arena != 0x81000000:
            raise RuntimeError("Could not reserve the private name fixture")
        cls.addClassCleanup(lambda: kernel.VirtualFree(arena, 0, 0x8000))

    def test_world_draw_restores_before_retail_once(self):
        self.dll.run(0)
        self.assertEqual(self.dll.eventOrder(), 1234)
        self.assertEqual(self.dll.counts(), 0x1111)
        self.assertTrue(self.dll.projectionMatches())

    def test_off_other_cues_names_and_overlays_leave_gx_alone(self):
        for choice in (1, 2, 3, 5, 6, 7, 10, 11):
            with self.subTest(choice=choice):
                self.dll.run(choice)
                self.assertEqual(self.dll.eventOrder(), 4)
                self.assertEqual(self.dll.counts(), 1)

    def test_free_camera_hide_hud_keeps_enabled_world_geometry(self):
        self.dll.run(4)
        self.assertEqual(self.dll.eventOrder(), 1234)
        self.assertTrue(self.dll.projectionMatches())

    def test_wireframe_scope_ends_at_normal_copy_even_when_overlay_suppressed(self):
        for choice in range(12):
            self.dll.run(choice)
            self.assertEqual(self.dll.wireframeEndCount(),0 if choice in (2,3,10,11) else 1)

    def test_wireframe_installation_requires_the_verified_copy_callback(self):
        self.assertEqual(self.dll.install(0),0)
        self.assertEqual(self.dll.install(1),1)
        self.assertEqual(self.dll.install(2),1)

    def test_rejected_geometry_does_not_reinitialize_gx(self):
        self.dll.run(8)
        self.assertEqual(self.dll.eventOrder(), 14)
        self.assertEqual(self.dll.counts(), 0x11)

    def test_orthographic_projection_handoff(self):
        self.dll.run(9)
        self.assertEqual(self.dll.eventOrder(), 1234)
        self.assertTrue(self.dll.projectionMatches())


if __name__ == "__main__":
    unittest.main()
