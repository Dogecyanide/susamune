"""Exercise camera-hook installation and the composed render owners."""

import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_nested_menu_focus import function


ROOT = Path(__file__).resolve().parents[1]


class CameraHookChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if sys.platform != "win32" or not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-camera-chain-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        practice = (ROOT / "src/practice_session.cpp").read_text()
        preview = (ROOT / "src/model_editor_preview.cpp").read_text()
        ghost = (ROOT / "src/ghost_camera.cpp").read_text()
        install = function(ghost, "void init()")
        install = install.replace("reinterpret_cast<u32>", "reinterpret_cast<HookAddress>")
        install = install.replace("u32 *table = reinterpret_cast<u32 *>(kCameraVtable);",
                                  "HookAddress *table = hookTable;")
        code = r'''
using u32=unsigned int;using HookAddress=__UINTPTR_TYPE__;
struct CPolarSubCamera {int view;};
namespace JDrama {struct TGraphics {};}
using Perform=void(*)(CPolarSubCamera*,u32,JDrama::TGraphics*);
static CPolarSubCamera camera,other,*gpCamera=&camera,*sCamera=&camera;
static bool sFreeCamera,sCameraApplied,previewWanted,previewApplied,recordedAvailable;
static bool ghostApplied;
static int practiceSaved,previewSaved,ghostSaved,captured,lastView;
static unsigned retailCalls,retailCue,practiceApplies,previewApplies,ghostApplies;
static unsigned captures,recordedQueries,flushes,setups;
static HookAddress hookTable[32];
enum {SETTING_GHOST_CAMERA};
struct Settings {int choice;int get(int){return choice;}} gSettings;
static void retailPerform(CPolarSubCamera*c,u32 cue,JDrama::TGraphics*) {
 ++retailCalls;retailCue=cue;if(cue&3)c->view=0;lastView=c->view;
}
static Perform kCameraPerform=&retailPerform;
void DCFlushRange(void*,unsigned){++flushes;}
void applyCamera(){if(!sCameraApplied){practiceSaved=camera.view;camera.view=1;sCameraApplied=true;++practiceApplies;}}
namespace ModelEditorPreview {
bool wanted(){return previewWanted;}
void apply(CPolarSubCamera*c){if(!previewApplied){previewSaved=c->view;c->view=2;previewApplied=true;++previewApplies;}}
void restoreAll(){
 if(previewApplied){camera.view=previewSaved;previewApplied=false;}
 if(sCameraApplied){camera.view=practiceSaved;sCameraApplied=false;}
}
void perform(CPolarSubCamera*,u32,JDrama::TGraphics*);
}
namespace GhostCamera {
struct View {int view;};
bool ready(){return true;}
void restore(){if(ghostApplied){camera.view=ghostSaved;ghostApplied=false;}}
void apply(CPolarSubCamera*c,const View&v){restore();ghostSaved=c->view;c->view=v.view;ghostApplied=true;++ghostApplies;}
void readRendered(CPolarSubCamera*c){captured=c->view;++captures;}
void onStageSetup(){++setups;}
}
namespace Ghost {
bool recordedCameraView(GhostCamera::View*v){++recordedQueries;v->view=3;return recordedAvailable;}
}
#define SUSAMUNE_MEM1_ADDR(j,u,p) (&retailPerform)
'''
        code += function(practice, 'extern "C" void susamunePracticeCameraPerform(')
        code += "\nnamespace ModelEditorPreview {\n"
        code += function(preview, "void perform(") + "\n}\n"
        code += "namespace GhostCamera {\n"
        code += function(ghost, 'extern "C" void susamuneGhostCameraPerform(')
        code += "\n" + install + "\n}\n"
        code += r'''
#define API extern "C" __declspec(dllexport)
API void reset(unsigned flags){
 camera.view=other.view=0;gpCamera=sCamera=&camera;
 sFreeCamera=flags&1;previewWanted=flags&2;recordedAvailable=flags&4;
 gSettings.choice=(flags&8)?1:0;sCameraApplied=previewApplied=ghostApplied=false;
 retailCalls=retailCue=practiceApplies=previewApplies=ghostApplies=0;
 captures=recordedQueries=flushes=setups=0;captured=lastView=-1;
 for(auto &entry:hookTable)entry=0;
 hookTable[8]=reinterpret_cast<HookAddress>(&ModelEditorPreview::perform);
 GhostCamera::init();
}
API unsigned installed(){return hookTable[8]==reinterpret_cast<HookAddress>(&GhostCamera::susamuneGhostCameraPerform);}
API void reinstall(){GhostCamera::init();}
API unsigned flushCount(){return flushes;}
API void dispatch(unsigned cue,unsigned foreign){reinterpret_cast<Perform>(hookTable[8])(foreign?&other:&camera,cue,nullptr);}
API unsigned counts(){return retailCalls|practiceApplies<<4|previewApplies<<8|ghostApplies<<12|captures<<16|recordedQueries<<20;}
API int rendered(){return captured;}
API int retailView(){return lastView;}
API int currentView(){return camera.view;}
API unsigned lastCue(){return retailCue;}
API unsigned rejectUnknown(){
 hookTable[8]=reinterpret_cast<HookAddress>(&retailPerform);flushes=0;
 GhostCamera::init();return hookTable[8]==reinterpret_cast<HookAddress>(&retailPerform)&&flushes==0;
}
'''
        cpp = work / "chain.cpp"
        cpp.write_text(code, encoding="ascii")
        library = work / "chain.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld",
                        "-Xlinker", "/noentry", str(cpp), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_install_accepts_practice_installed_wrapper_once(self):
        practice = (ROOT / "src/practice_session.cpp").read_text()
        self.assertIn("table[i] = reinterpret_cast<u32>(&ModelEditorPreview::perform);",
                      function(practice, "void init()"))
        self.dll.reset(0)
        self.assertTrue(self.dll.installed())
        self.assertEqual(self.dll.flushCount(), 1)
        self.dll.reinstall()
        self.assertTrue(self.dll.installed())
        self.assertEqual(self.dll.flushCount(), 1)
        self.assertTrue(self.dll.rejectUnknown())

    def test_regular_and_free_camera_draw_capture_actual_render_owner(self):
        for flags, view, expected in ((0, 0, 0x10001), (1, 1, 0x10011)):
            self.dll.reset(flags)
            self.dll.dispatch(0x14, 0)
            self.assertEqual(self.dll.counts(), expected)
            self.assertEqual(self.dll.rendered(), view)
            self.assertEqual(self.dll.retailView(), view)

    def test_recorded_watch_keeps_draw_precedence_and_restores_before_movement(self):
        self.dll.reset(1 | 4 | 8)
        self.dll.dispatch(0x14, 0)
        self.assertEqual(self.dll.counts(), 0x111001)
        self.assertEqual(self.dll.rendered(), 3)
        self.dll.dispatch(1, 0)
        self.assertEqual(self.dll.currentView(), 0)
        self.assertEqual(self.dll.retailView(), 0)
        self.assertEqual(self.dll.counts(), 0x111002)

    def test_colour_preview_takes_priority_over_free_and_recorded_cameras(self):
        for flags in (1 | 2, 1 | 2 | 4 | 8):
            for cue in (0x14, 0x15):
                self.dll.reset(flags)
                self.dll.dispatch(cue, 0)
                self.assertEqual(self.dll.counts(), 0x10101 + bool(cue & 1))
                self.assertEqual(self.dll.rendered(), 2)
                self.assertEqual(self.dll.retailView(), 2)
                self.assertEqual(self.dll.lastCue(), 0x14)
                self.dll.dispatch(1, 0)
                self.assertEqual(self.dll.currentView(), 0)
                self.assertEqual(self.dll.retailView(), 0)

    def test_other_cameras_and_movement_do_not_capture_or_apply_draw_owners(self):
        self.dll.reset(1 | 2 | 4 | 8)
        self.dll.dispatch(0x14, 1)
        self.assertEqual(self.dll.counts(), 1)
        self.assertEqual(self.dll.retailView(), 0)
        self.dll.dispatch(1, 0)
        self.assertEqual(self.dll.counts(), 2)


if __name__ == "__main__":
    unittest.main()
