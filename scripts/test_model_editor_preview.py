"""Check the production colour-editor orbit scope and raw-stick ownership."""
import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class ModelPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-model-preview-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = re.sub(r"^#(?:include|pragma)[^\n]*", "",
                        (ROOT / "src/model_editor_preview.cpp").read_text(), flags=re.M)
        code = r'''
typedef unsigned char u8;typedef signed char s8;typedef short s16;typedef float f32;typedef unsigned long u32;
extern "C" {int _fltused=0;}
extern "C" void*memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void*memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
struct TVec3f {f32 x,y,z;void set(f32 a,f32 b,f32 c){x=a;y=b;z=c;}};typedef TVec3f Vec;
struct CPolarSubCamera {TVec3f mTranslation,mTargetPos,mUpVector;f32 mProjectionFovy,mProjectionAspect,mProjectionNear,mProjectionFar;
 u8 gap0[0x124-52];TVec3f mWorldTranslation;u8 gap1[0x148-0x130];TVec3f cacheTarget;u8 gap2[0x16c-0x154];
 f32 projection[4][4];u8 gap3[0x1ec-0x1ac];f32 mTRSMatrix[3][4];u8 gap4[0x256-0x21c];s16 mAnglePitch,mAngleYaw;u8 gap5[2];};
static_assert(sizeof(CPolarSubCamera)==0x25c,"fixture camera range");
struct TMarDirector {bool _260;};TMarDirector *gpMarDirector;CPolarSubCamera *gpCamera;
struct Mario {TVec3f mTranslation;struct{s16 x,y,z;}mAngle;} *gpMarioOriginal;
struct PADStatus {u8 mStickX,mStickY,mCurError;};struct JUTGamePad {static PADStatus mPadStatus[1];};PADStatus JUTGamePad::mPadStatus[1];
namespace JUtility{struct TColor{TColor(int,int,int,int){}};}
static int hintX,hintY,hintW,hintH,textX,textY,textH;
struct Menu{bool visible;bool shown(){return visible;}
 static int textWidth(const char*,int){return 182;}
 void fillBox(int x,int y,int w,int h,JUtility::TColor){hintX=x;hintY=y;hintW=w;hintH=h;}
 void drawText(const char*,int x,int y,int,int h,JUtility::TColor){textX=x;textY=y;textH=h;}}*gMenu;
namespace JDrama{class TGraphics;}
void retailPerform(CPolarSubCamera*,u32,JDrama::TGraphics*);
#define SUSAMUNE_MEM1_ADDR(j,u,p) (&retailPerform)
namespace RetailInput{TMarDirector*stageDirector(){return gpMarDirector;}}
float sinf(float x){while(x>3.14159265f)x-=6.2831853f;while(x< -3.14159265f)x+=6.2831853f;float y=x*x;return x*(1-y/6+y*y/120-y*y*y/5040+y*y*y*y/362880);}
float cosf(float x){return sinf(x+1.570796325f);}
void C_MTXPerspective(float(*m)[4],float f,float a,float n,float z){for(int i=0;i<16;i++)m[0][i]=f+a+n+z+i;}
void C_MTXLookAt(float(*m)[4],const Vec*p,const Vec*u,const Vec*t){for(int i=0;i<12;i++)m[0][i]=p->x+p->y+p->z+u->y+t->x+i;}
namespace ModelEditorPreview{void restore();}
'''
        code += source
        code += r'''
static unsigned hudBegins,hudEnds,hudDraws;
static bool cinemaHidden;
class J2DGrafContext {};
struct J2DScreen{void draw(int,int,const J2DGrafContext*){++hudDraws;}};
struct Pane{void add(int,int){}};
struct PaneShift{Pane *pane;int y;};
PaneShift shiftPinnaTimerPanel(J2DScreen*){++hudBegins;return {nullptr,0};}
namespace PracticeSession{bool hideHud(){return cinemaHidden;}}
namespace NativeTimerLayout{bool beginDraw(J2DScreen*){++hudBegins;return true;}void endDraw(){++hudEnds;}}
namespace NativeTimerColor{bool beginDraw(J2DScreen*){++hudBegins;return true;}void endDraw(){++hudEnds;}}
namespace NativeHudPrecision{bool beginDraw(J2DScreen*){++hudBegins;return true;}void endDraw(){++hudEnds;}}
struct Extras{bool beginHudDraw(J2DScreen*){++hudBegins;return true;}void endHudDraw(){++hudEnds;}}gCreationExtras;
'''
        code += function((ROOT / "src/practice_visuals.cpp").read_text(), "void drawHudScreen(")
        code += r'''
using namespace ModelEditorPreview;
static unsigned originalCalls,retailCalls,practiceRestores,originalCue,retailCue;
namespace ModelEditorPreview{void restorePracticeCamera(){++practiceRestores;}}
extern "C" void susamunePracticeCameraPerform(CPolarSubCamera*,u32 cue,JDrama::TGraphics*){
 ++originalCalls;originalCue=cue;if(cue&3)restoreAll();
}
void retailPerform(CPolarSubCamera*,u32 cue,JDrama::TGraphics*){++retailCalls;retailCue=cue;}
static bool equal(const void*a,const void*b,unsigned n){const u8*x=(const u8*)a,*y=(const u8*)b;while(n--)if(*x++!=*y++)return false;return true;}
extern "C" __declspec(dllexport) int run(unsigned test){
 end();CPolarSubCamera camera;memset(&camera,0x29,sizeof(camera));camera.mProjectionAspect=4.0f/3;camera.mProjectionNear=10;camera.mProjectionFar=20000;
 CPolarSubCamera old=camera;Mario mario={{100,20,-400},{0,0,0}},oldMario=mario;TMarDirector director={true};Menu menu={true};
 gpMarioOriginal=&mario;gpCamera=&camera;gpMarDirector=&director;gMenu=&menu;JUTGamePad::mPadStatus[0]={0,0,0};
 begin(test==1);if(!wanted())return 1;
 drawHint(&menu);if(textX!=320-182/2||textY!=237||textY<hintY||textY+textH>hintY+hintH)return 11;
 if(test==2){
  float yaw=sYaw,pitch=sPitch;JUTGamePad::mPadStatus[0]={10,250,0};update();if(yaw!=sYaw||pitch!=sPitch)return 2;
  JUTGamePad::mPadStatus[0]={80,80,0};for(int i=0;i<1000;i++)update();
  if(sYaw< -3.141593f||sYaw>3.141593f||sPitch!=0.70f)return 3;
  JUTGamePad::mPadStatus[0]={176,176,0};for(int i=0;i<1000;i++)update();if(sPitch!= -0.10f)return 4;
  yaw=sYaw;pitch=sPitch;JUTGamePad::mPadStatus[0]={80,80,255};update();if(yaw!=sYaw||pitch!=sPitch)return 5;
 }
 apply(&camera);if(!sApplied||equal(&camera,&old,sizeof(camera))||!equal(&mario,&oldMario,sizeof(mario)))return 6;
 const f32 dx=camera.mTranslation.x-mario.mTranslation.x,dy=camera.mTranslation.y-mario.mTranslation.y,dz=camera.mTranslation.z-mario.mTranslation.z;
 const f32 distance=dx*dx+dy*dy+dz*dz;if(distance<459.0f*459.0f||distance>461.0f*461.0f)return 12;
 if(test<2&&((camera.mTranslation.z>mario.mTranslation.z)!=(test==0)))return 7;
 CPolarSubCamera applied=camera;apply(&camera);if(!equal(&camera,&applied,sizeof(camera)))return 8;
 if(test==3){menu.visible=false;if(wanted())return 9;}
 end();restore();if(wanted()||!equal(&camera,&old,sizeof(camera))||!equal(&mario,&oldMario,sizeof(mario)))return 10;
 return 0;
}
extern "C" __declspec(dllexport) int routing(unsigned test){
 end();CPolarSubCamera camera;memset(&camera,0,sizeof(camera));camera.mProjectionAspect=4.0f/3;
 CPolarSubCamera old=camera;Mario mario={{100,20,-400},{0,0,0}};TMarDirector director={true};Menu menu={true};
 gpMarioOriginal=&mario;gpCamera=&camera;gpMarDirector=&director;gMenu=&menu;
 originalCalls=retailCalls=practiceRestores=0;
 if(test==0){perform(&camera,0x15,nullptr);return originalCalls!=1||originalCue!=0x15||retailCalls||sApplied;}
 begin(false);
 if(test==4){
  hudBegins=hudEnds=hudDraws=0;cinemaHidden=false;J2DScreen screen;
  drawHudScreen(&screen,0,0,nullptr);if(hudBegins||hudEnds||hudDraws)return 5;
  end();drawHudScreen(&screen,0,0,nullptr);if(hudBegins!=5||hudEnds!=4||hudDraws!=1)return 6;
  cinemaHidden=true;drawHudScreen(&screen,0,0,nullptr);if(hudDraws!=1)return 7;
  cinemaHidden=false;return 0;
 }
 if(test==3){CPolarSubCamera other=camera;perform(&other,0x14,nullptr);return originalCalls!=1||retailCalls||sApplied;}
 perform(&camera,test==1?0x15:0x14,nullptr);
 if(!sApplied||retailCalls!=1||retailCue!=0x14||originalCalls!=(test==1))return 2;
 if(test==1&&(originalCue!=1||practiceRestores!=1))return 3;
 if(test==1)perform(&camera,1,nullptr);else restoreAll();
 if(sApplied||!equal(&camera,&old,sizeof(camera))||practiceRestores!=(test==1?2:1))return 4;
 end();return 0;
}
'''
        cpp = work / "preview.cpp"
        cpp.write_text(code, encoding="ascii")
        library = work / "preview.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
            str(cpp), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_front_back_camera_scope_and_close_restore_without_mario_changes(self):
        for scenario in (0, 1, 3):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.dll.run(scenario), 0)

    def test_stick_deadzone_wrapping_elevation_limits_and_disconnected_pad(self):
        self.assertEqual(self.dll.run(2), 0)

    def test_dispatch_preserves_freecam_and_restores_before_movement(self):
        for scenario in range(4):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.dll.routing(scenario), 0)

    def test_native_hud_is_skipped_only_during_preview_without_borrowing_panes(self):
        self.assertEqual(self.dll.routing(4), 0)


if __name__ == "__main__":
    unittest.main()
