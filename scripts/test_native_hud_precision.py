"""Exercise the production 3DP draw scope, timing input and retail ownership."""
import ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeHudPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-3dp-")
        cls.addClassCleanup(cls.temp.cleanup)
        timer = (ROOT / "src/qft_timer.cpp").read_text()
        structs = "\n".join(re.search(r"  struct " + name + r" \{.*?\n  \};", timer, re.S)[0]
                            for name in ("TimerState", "SavedTimerData"))
        production = (ROOT / "src/native_hud_precision.cpp").read_text()
        production = production[production.index("namespace NativeHudPrecision {"):]
        source = r'''
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;typedef int s32;
typedef float Mtx[3][4];
extern "C" { int _fltused; }
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int v,unsigned long long n){u8*a=(u8*)d;while(n--)*a++=(u8)v;return d;}
struct JUTRect {int mX1,mY1,mX2,mY2;};
struct JUTTexture {unsigned digit;};
enum {BindingBottom=1,BindingTop=2,BindingRight=4,BindingLeft=8};
struct J2DPane {void**vtable;u32 mTag,mTypeMagic;bool mIsVisible;JUTRect mRect,mClipRect;Mtx mScreenMtx;u8 _84[48];};
struct J2DPicture:J2DPane {u8 mTextureCount;JUTTexture*mTextures[4];u32 mBinding,mMirrorFlags;bool mRotate90;};
struct J2DScreen {J2DPicture*panes;J2DPane*search(u32 tag){for(unsigned i=0;i<11;++i)if(panes[i].mTag==tag)return panes+i;return nullptr;}};
struct TGCConsole2 {J2DScreen*mMainScreen;bool mIsTimerMoving;u8 pad[0xE0-sizeof(void*)-1];JUTTexture*numbers[10];};
static_assert(__builtin_offsetof(TGCConsole2,numbers)==0xE0,"fixture number table");
struct TMarDirector {bool _260;TGCConsole2*mGCConsole;};TMarDirector*gpMarDirector;
namespace RetailInput {bool matches=true;TMarDirector*stageDirector(){return matches?gpMarDirector:nullptr;}}
namespace PracticeSession {bool held;bool paused(){return held;}}
enum {SETTING_TIMER_SUNSHINE_VISIBILITY,SETTING_NATIVE_TIMER_DECIMAL_SEPARATOR};
struct Settings {u8 visibility,separator;u8 get(int id){return id==SETTING_TIMER_SUNSHINE_VISIBILITY?visibility:separator;}}gSettings;
struct Style {u8 scale;};struct Extras {Style style;const Style&nativeTimerStyle(){return style;}}gCreationExtras;
constexpr int kSectionHistoryCount=16;
''' + structs + r'''
static_assert(sizeof(SavedTimerData)==96,"production sidecar size");
static_assert(__builtin_offsetof(SavedTimerData,retailTimerOwned)==92,"production ownership offset");
static_assert(__builtin_offsetof(TimerState,stopReason)==2,"production stop reason offset");
struct Timer {struct SavestateData{u32 words[24];};s32 qf,transition;bool stopped,owned,ready;
 bool currentQf(s32*q,bool*s){*q=qf;*s=stopped;return ready;}
 void captureSavestate(SavestateData&out){SavedTimerData state={};state.timer.stopped=stopped;state.timer.stopReason=stopped;state.retailTimerOwned=owned;memcpy(&out,&state,sizeof(out));}
 bool transitionEntryQf(s32*q,u16*t){*q=transition;*t=1;return transition>=0;}
}gQFTTimer;
typedef Timer QFTTimer;
''' + production + r'''
static J2DPicture panes[11];static JUTTexture numbers[10],original[9];static void*table[11];
static J2DScreen screen;static TGCConsole2 console;static TMarDirector director;
static unsigned calls,drawDigit[2];static bool extraPass[2];static float drawX[2],drawY[2];
static int drawHeight[2];static unsigned drawBinding[2];
void matrix(J2DPane*p,int,int){p->mClipRect=p->mRect;}
void draw(J2DPicture*p,int,int,Mtx*){
 if(calls<2){drawDigit[calls]=p->mTextures[0]->digit;extraPass[calls]=NativeHudPrecision::extraDigit();drawX[calls]=(*(Mtx*)p->_84)[0][3];drawY[calls]=(*(Mtx*)p->_84)[1][3];drawHeight[calls]=p->mRect.mY2-p->mRect.mY1;drawBinding[calls]=p->mBinding;}++calls;
}
void reset(){
 NativeHudPrecision::endDraw();memset(panes,0,sizeof(panes));
 table[8]=(void*)draw;table[10]=(void*)matrix;
 screen.panes=panes;console.mMainScreen=&screen;console.mIsTimerMoving=false;
 director={true,&console};gpMarDirector=&director;RetailInput::matches=true;
 gQFTTimer={0,-1,false,false,true};gSettings.visibility=0;gSettings.separator=0;PracticeSession::held=false;gCreationExtras.style.scale=100;
 for(unsigned i=0;i<10;++i){numbers[i].digit=i;console.numbers[i]=numbers+i;}
 for(unsigned i=0;i<11;++i){panes[i].vtable=table;panes[i].mIsVisible=true;panes[i].mTypeMagic=i<2?'PAN1':'PIC1';
  panes[i].mTag=i==0?'\0t_0':i==1?'\0t_1':i<8?'t_n1'+i-2:'t_c1'+i-8;
  panes[i].mRect={(int)i*27,-(int)i*5,(int)i*27+36,36-(int)i*5};panes[i].mClipRect={1,2,3,4};
  panes[i].mTextureCount=1;panes[i].mBinding=15;if(i>=2)panes[i].mTextures[0]=original+i-2;
  Mtx&w=*(Mtx*)panes[i]._84;w[0][0]=w[1][1]=w[2][2]=1;w[0][3]=33;
 }calls=0;
}
extern "C" __declspec(dllexport) unsigned digits(int qf){u8 d[7];NativeHudPrecision::formatDigits(qf,d);unsigned n=0;for(unsigned i=0;i<7;++i)n=n*10+d[i];return n;}
extern "C" __declspec(dllexport) int scoped(int scale,int transform){
 reset();gQFTTimer.qf=4;gCreationExtras.style.scale=scale;
 NativeHudPrecision::capture(false);
 if(!NativeHudPrecision::beginDraw(&screen)||NativeHudPrecision::beginDraw(&screen))return 1;
 unsigned expected[]={0,0,0,0,0,3};
 for(unsigned i=0;i<6;++i)if(panes[i+2].mTextures[0]!=numbers+expected[i])return 2;
 for(unsigned i: {0u,1u,7u}){
  ((void(*)(J2DPane*,int,int))panes[i].vtable[10])(panes+i,0,0);
  if(panes[i].mClipRect.mX2!=panes[i].mRect.mX2+(27*scale+99)/100)return 3;
 }
 Mtx&w=*(Mtx*)panes[7]._84;Mtx&prior=*(Mtx*)panes[6]._84;
 const float unit=(float)scale/100;
 // Both native pictures are tilted 15 degrees; their positions belong to the parent.
 w[0][0]=.9659258f*unit;w[0][1]=.2588190f*unit;
 w[1][0]=-.2588190f*unit;w[1][1]=.9659258f*unit;
 float dx=27*unit,dy=-5*unit;
 if(transform){const float before=dx;dx=.8f*dx-.6f*dy;dy=.6f*before+.8f*dy;}
 const float px=transform?-192.5f:33,py=transform?287.25f:17;
 w[0][3]=px;w[1][3]=py;prior[0][3]=px-dx;prior[1][3]=py-dy;
 ((void(*)(J2DPicture*,int,int,Mtx*))panes[7].vtable[8])(panes+7,0,0,nullptr);
 const float errorX=drawX[1]-px-dx,errorY=drawY[1]-py-dy;
 if(calls!=2||drawDigit[0]!=3||drawDigit[1]!=3||drawX[0]!=px||drawY[0]!=py||
    errorX<-.001f||errorX>.001f||errorY<-.001f||errorY>.001f||w[0][3]!=px||w[1][3]!=py||
    extraPass[0]||!extraPass[1]||NativeHudPrecision::extraDigit())return 4;
 NativeHudPrecision::endDraw();NativeHudPrecision::endDraw();
 if(NativeHudPrecision::normalDigits()!=6)return 8;
 for(unsigned i=0;i<8;++i)if(panes[i].vtable!=table)return 5;
 for(unsigned i=0;i<6;++i)if(panes[i+2].mTextures[0]!=original+i)return 6;
 for(unsigned i:{0u,1u,7u})if(panes[i].mClipRect.mX2!=3)return 7;
 return 0;
}
extern "C" __declspec(dllexport) int admission(int test){
 reset();gQFTTimer.qf=20;gSettings.separator=1;
 if(test==0)gQFTTimer.owned=true;
 if(test==1)console.mIsTimerMoving=true;
 if(test==2)gSettings.visibility=2;
 if(test==3)gSettings.visibility=1;
 if(test==4)gQFTTimer.ready=false;
 NativeHudPrecision::capture(false);
 if(test==5)console.mIsTimerMoving=true;
 if(test==6)panes[1].mIsVisible=false;
 if(test==7)panes[7].mIsVisible=false;
 if(test==8)console.numbers[1]=nullptr;
 if(NativeHudPrecision::beginDraw(&screen))return 1;
 for(unsigned i=0;i<11;++i)if(panes[i].vtable!=table)return 2;
 for(unsigned i=0;i<6;++i)if(panes[i+2].mTextures[0]!=original+i)return 3;
 return 0;
}
extern "C" __declspec(dllexport) int loading(int test){
 reset();gQFTTimer.qf=20;NativeHudPrecision::capture(false);
 if(!NativeHudPrecision::sValid)return 1;
 director.mGCConsole=(TGCConsole2*)0x7a140;
 if(test==0)director._260=false;
 if(test==1)RetailInput::matches=false;
 if(test==2)gpMarDirector=nullptr;
 NativeHudPrecision::capture(false);
 if(NativeHudPrecision::sValid||NativeHudPrecision::beginDraw(&screen))return 2;
 director={true,&console};gpMarDirector=&director;RetailInput::matches=true;
 NativeHudPrecision::capture(false);
 if(!NativeHudPrecision::beginDraw(&screen))return 3;
 NativeHudPrecision::endDraw();return 0;
}
extern "C" __declspec(dllexport) int separator(int option,int scale,int rotated,int fault){
 reset();gSettings.separator=option;gQFTTimer.qf=4;gCreationExtras.style.scale=scale;
 J2DPicture&p=panes[9];p.mRect={131,-33,149,3};
 if(fault==1)p.mTag=0;
 if(fault==2)p.mTextureCount=0;
 if(fault==3)p.mMirrorFlags=1;
 if(fault==4)p.mRotate90=true;
 if(fault==5)gQFTTimer.owned=true;
 Mtx&w=*(Mtx*)p._84;const float unit=(float)scale/100;
 w[0][1]=(rotated?.7f:.17364818f)*unit;w[1][1]=(rotated?.71414284f:.98480775f)*unit;
 const float x=rotated?-171.5f:300,y=rotated?289.25f:70;
 w[0][3]=x;w[1][3]=y;
 NativeHudPrecision::capture(false);bool active=NativeHudPrecision::beginDraw(&screen);
 if(active!=(fault!=5))return 1;
 ((void(*)(J2DPicture*,int,int,Mtx*))p.vtable[8])(&p,0,0,nullptr);
 const bool dot=option==1&&!fault;
 const float dx=drawX[0]-x-(dot?w[0][1]*18:0),dy=drawY[0]-y-(dot?w[1][1]*18:0);
 if(calls!=1||drawHeight[0]!=(dot?18:36)||drawBinding[0]!=(dot?13:15)||dx<-.001f||dx>.001f||dy<-.001f||dy>.001f)return 2;
 if(p.mRect.mY1!=-33||p.mRect.mY2!=3||p.mBinding!=15||w[0][3]!=x||w[1][3]!=y||p.mTextures[0]!=original+7)return 3;
 if(panes[8].vtable!=table||panes[10].vtable!=table)return 4;
 NativeHudPrecision::endDraw();
 for(unsigned i=0;i<11;++i)if(panes[i].vtable!=table)return 5;
 return 0;
}
extern "C" __declspec(dllexport) unsigned clock(int test){
 reset();gQFTTimer.qf=20;
 if(test<2)PracticeSession::held=true;
 if(test==2||test==3)gQFTTimer.transition=8;
 if(test==3){gQFTTimer.stopped=true;gSettings.visibility=1;}
 NativeHudPrecision::capture(test==0);
 if(!NativeHudPrecision::beginDraw(&screen))return 0xffffffff;
 unsigned result=0;for(unsigned i=0;i<7;++i)result=result*10+NativeHudPrecision::sDigits[i];
 NativeHudPrecision::endDraw();return result;
}
'''
        # Avoid pulling a standard-library initializer_list into the bare fixture.
        source = source.replace('for(unsigned i: {0u,1u,7u})', 'for(unsigned j=0;j<3;++j)if(unsigned i=j<2?j:7;true)')
        source = source.replace('for(unsigned i:{0u,1u,7u})', 'for(unsigned j=0;j<3;++j)if(unsigned i=j<2?j:7;true)')
        cpp = Path(cls.temp.name) / "precision.cpp"
        cpp.write_text(source)
        dll = cpp.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-std=c++17", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        str(cpp), "-o", str(dll)], check=True)
        cls.dll = ctypes.CDLL(str(dll))
        cls.dll.digits.restype = ctypes.c_uint
        cls.dll.clock.restype = ctypes.c_uint
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_all_digits_use_truncated_qf_precision_with_minute_carries_and_cap(self):
        for qf in (-1, 0, 1, 2, 4, 119, 120, 7192, 7193, 71928, 719280, 719281, 2147483647):
            millis = min(max(qf, 0) * 1001 // 120, 5999999)
            expected = millis // 60000 * 100000 + millis // 1000 % 60 * 1000 + millis % 1000
            self.assertEqual(self.dll.digits(qf), expected, qf)

    def test_draw_borrows_digits_and_scissor_then_restores_every_owned_field(self):
        for scale in (50, 75, 100, 125, 200):
            for transform in (0, 1):
                self.assertEqual(self.dll.scoped(scale, transform), 0, (scale, transform))

    def test_native_running_and_finished_races_stay_2dp_and_failed_admission_is_inert(self):
        for case in range(9):
            self.assertEqual(self.dll.admission(case), 0, case)

    def test_pre_direct_phase_pause_step_transition_and_final_stop(self):
        for case, qf in enumerate((16, 20, 8, 20)):
            self.assertEqual(self.dll.clock(case), self.dll.digits(qf), case)

    def test_stage_load_and_director_change_never_dereference_stale_hud(self):
        for case in range(3):
            self.assertEqual(self.dll.loading(case), 0, case)

    def test_decimal_uses_lower_native_dot_and_restores_geometry_binding_and_transforms(self):
        for option in (0, 1):
            for scale in (50, 100, 200):
                for rotated in (0, 1):
                    for fault in range(6):
                        with self.subTest(option=option, scale=scale, rotated=rotated, fault=fault):
                            self.assertEqual(self.dll.separator(option, scale, rotated, fault), 0)


if __name__ == "__main__":
    unittest.main()
