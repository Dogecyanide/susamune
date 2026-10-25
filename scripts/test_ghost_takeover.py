"""Exercise production takeover at the retail actor/session boundary."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]

class TakeoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ghost-takeover-', dir=ROOT/'build')
        cls.addClassCleanup(cls.temp.cleanup)
        code = r'''
using s16=short;using u16=unsigned short;using u32=unsigned;using f32=float;
struct TVec3f {float x,y,z;void set(float a,float b,float c){x=a;y=b;z=c;}};
using Vec=TVec3f;
struct TMario {
 enum{STATE_IDLE=1,STATE_FALL=2,ANIMATION_IDLE=3,ANIMATION_FALL=4,STATE_RUNNING=5,STATE_JUMP=6,STATE_D_JUMP=7,STATE_TRIPLE_J=8,STATE_WALLJUMP=9,STATE_SIDE_FLIP=10,STATE_BACK_FLIP=11};
 TVec3f mTranslation,mLastPosition,mLastPos,mLastGroundedPos,mSpeed,mPrevSpeed;
 struct {s16 y;}mAngle;s16 mModelAngleY,mAccelerationDirection;
 float mForwardSpeed,mFloorBelow;const int*mWallTriangle,*mRoofTriangle,*mFloorTriangle;
 int state,animation,dropped;
 struct {bool mIsVisible;} mAttributes,mPrevAttributes;
 void dropObject(){++dropped;}
 void changePlayerStatus(int s,int,bool){state=s;}
 void setAnimation(int a,float){animation=a;}
}mario,*gpMarioOriginal=&mario,*sObserverMario=&mario;
struct Camera {void addMoveCameraAndMario(const Vec&){}}camera,*gpCamera=&camera;
struct Map {int triangle;const int*getIllegalCheckData(){return &triangle;}
 float checkGround(float,float,float,const int**out){*out=&triangle;return 20;}
}map,*gpMap=&map;
struct TMarDirector {enum{STATE_NORMAL=4};int mCurState;}director,*gpMarDirector=&director;
bool running,two,loading,sObserverStageReady,sGhostVisible,sObserverMarioOwned,sObserverMarioBaselineFinalized;
bool observerRunning(){return running;}bool observerHasTwo(){return two;}bool observerLoading(){return loading;}
TVec3f sGhostPosition;s16 sGhostYaw;int ends,warps;u16 sGhostAnimationId;
struct Sample {int x,y,z;unsigned deltaQf;};struct Segment {unsigned firstSample,sampleCount;};
struct Playback {unsigned segmentCount;Segment segments[1];Sample samples[2];}sPlayback;
unsigned sPlaybackSegment,sPlaybackCursor,sGhostYoshi,sGhostHeldObjectId;
int sampleX(const Sample&s){return s.x;}int sampleY(const Sample&s){return s.y;}int sampleZ(const Sample&s){return s.z;}
float samplePosition(int n){return n;}float sinf(float){return 0;}float cosf(float){return 1;}

void endObserver(bool reload,const char*){++ends;warps+=reload;running=false;mario.mTranslation={0,0,0};mario.mAttributes.mIsVisible=mario.mPrevAttributes.mIsVisible=true;}
namespace PracticeSession {
 bool held,allowed,free,assisted;unsigned stripped;
 bool manualPaused(){return held;}bool requestPauseToggle(bool){if(!allowed)return false;held=assisted=true;return true;}
 bool freeCamera(){return free;}void requestFreeCameraToggle(){free=false;}
 void stripShortcutButtons(unsigned b){stripped=b;}
}
struct JUTGamePad {enum{START=4096,A=256};};
struct Binds {int suppressed;void suppressUntilRelease(){++suppressed;}}gBinds;
namespace GhostModel {void refreshPlayerAfterTakeover(){}}
'''+''.join(function((ROOT/'src/ghost.cpp').read_text(), name) for name in ('bool takeoverMomentum(', 'u32 takeoverStatus(', 'bool takeOverObserver()'))+r'''
#define API extern "C" __declspec(dllexport)
API void reset(){sPlayback={};sGhostAnimationId=0;sGhostYoshi=sGhostHeldObjectId=0;mario={};director.mCurState=4;gpMarDirector=&director;gpMap=&map;sObserverMario=&mario;
 running=sObserverStageReady=sGhostVisible=sObserverMarioOwned=sObserverMarioBaselineFinalized=true;
 two=loading=false;ends=warps=0;gBinds.suppressed=0;sGhostPosition={120,20,80};sGhostYaw=1234;
 PracticeSession::held=PracticeSession::assisted=false;PracticeSession::allowed=PracticeSession::free=true;
 mario.mSpeed={1,2,3};mario.mPrevSpeed={4,5,6};mario.mForwardSpeed=7;}
API void block(int n){switch(n){case 0:running=false;break;case 1:two=true;break;case 2:loading=true;break;
 case 3:sObserverStageReady=false;break;case 4:sGhostVisible=false;break;case 5:gpMap=nullptr;break;
 case 6:gpMarDirector=nullptr;break;case 7:director.mCurState=1;break;case 8:sObserverMarioOwned=false;break;
 case 9:sObserverMarioBaselineFinalized=false;break;case 10:sObserverMario=nullptr;break;case 11:PracticeSession::allowed=false;}}
API int take(){return takeOverObserver();}
API void airborne(){sGhostPosition.y=100;}
API void recorded(unsigned gap,unsigned jump){sGhostPosition.y=100;sGhostYaw=0;sGhostAnimationId=jump?0x4d:0;
 sPlayback.segmentCount=1;sPlayback.segments[0]={0,2};sPlayback.samples[0]={120,100,80,0};sPlayback.samples[1]={120,116,88,gap};}
API int momentumCheck(){return mario.mSpeed.x==0&&mario.mSpeed.y==16&&mario.mSpeed.z==8&&mario.mForwardSpeed==8&&mario.animation==0x4d&&mario.state==6;}
API int check(int n){switch(n){case 0:return ends==1&&!warps&&!running&&!mario.mAttributes.mIsVisible&&!mario.mPrevAttributes.mIsVisible;
 case 1:return mario.mTranslation.x==120&&mario.mTranslation.y==sGhostPosition.y&&mario.mTranslation.z==80;
 case 2:return mario.mAngle.y==1234&&mario.mModelAngleY==1234;
 case 3:return !mario.mSpeed.x&&!mario.mSpeed.y&&!mario.mSpeed.z&&!mario.mPrevSpeed.z&&!mario.mForwardSpeed;
 case 4:return PracticeSession::held&&PracticeSession::assisted&&!PracticeSession::free;
 case 5:return gBinds.suppressed==1&&PracticeSession::stripped==4352;
 case 6:return mario.state;case 7:return ends;default:return 0;}}
extern "C" {int _fltused=0;}
'''
        path=Path(cls.temp.name)/'test.cpp';path.write_text(code)
        result=subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc',
            '-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-O2',str(path),'-o',str(path.with_suffix('.dll'))],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(path.with_suffix('.dll')))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_rejected_takeover_preserves_watch(self):
        for n in range(12):
            self.lib.reset();self.lib.block(n)
            self.assertEqual(self.lib.take(),0,n)
            self.assertEqual(self.lib.check(7),0,n)

    def test_grounded_and_airborne_takeover_pause_without_reloading(self):
        for airborne in (False,True):
            self.lib.reset()
            if airborne:self.lib.airborne()
            self.assertEqual(self.lib.take(),1)
            for n in range(6):self.assertEqual(self.lib.check(n),1,(airborne,n))
            self.assertEqual(self.lib.check(6),2 if airborne else 1)
            self.assertEqual(self.lib.take(),0)
            self.assertEqual(self.lib.check(7),1)

    def test_recorded_motion_and_animation_restore_common_jump(self):
        self.lib.reset();self.lib.recorded(4,1)
        self.assertEqual(self.lib.take(),1)
        self.assertEqual(self.lib.momentumCheck(),1)
        self.lib.reset();self.lib.recorded(80,1)
        self.assertEqual(self.lib.take(),1)
        self.assertEqual(self.lib.check(3),1)
        self.assertEqual(self.lib.check(6),2)

if __name__=='__main__':unittest.main()
