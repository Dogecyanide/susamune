"""Run production ghost particle advancement against measured retail QF units."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class GhostWaterMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-water-motion-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        source = (ROOT / "src/ghost_water.cpp").read_text()
        code = r'''
using u8=unsigned char;using s8=signed char;using u32=unsigned;using s32=int;using f32=float;
extern "C" int _fltused=0;
extern "C" void* memset(void*p,int c,unsigned long long n){auto*b=(u8*)p;while(n--)*b++=(u8)c;return p;}
struct TVec3f{f32 x,y,z;void set(f32 a,f32 b,f32 c){x=a;y=b;z=c;}};
struct Sample{u8 mode; signed char offset[3];u8 aim[3],power;};
namespace Ghost {struct VisualState{f32 x,y,z;short yaw;Sample fludd;u32 visualQf,recordingToken;};}
const unsigned kDrops=64;
'''
        code += source[source.index("struct Drop {"):source.index("struct Storage {")]
        code += r'''
template<class T>struct Param{T value;T get()const{return value;}};
struct TNozzleBase{struct{Param<int>mType;Param<f32>mSize,mNum,mEmitPow,mDirTremble,mPowTremble;}mEmitParams;};
struct Gun{TNozzleBase*mNozzleList[6];TNozzleBase mNozzleDeformBomb,mNozzleYoshiDeformBomb;};struct Mario{Gun*mFludd;};Mario*gpMarioOriginal;
struct TBGCheckData{};struct Map{f32 checkGround(f32,f32,f32,const TBGCheckData**p){*p=nullptr;return -40000;}};Map*gpMap;
const int SUSAMUNE_GHOST_FLUDD_SPRAYING=16,SUSAMUNE_GHOST_FLUDD_BURST=32,SUSAMUNE_GHOST_VISUAL_YOSHI=128;
f32 sinf(f32 x){return x;}f32 cosf(f32){return 1;}
f32 ghostSquareRoot(f32 x){f32 r=x>1?x:1;for(int i=0;i<16;i++)r=(r+x/r)*.5f;return r;}
void direction(const Sample&,TVec3f&v){v.set(0,0,1);}
f32 parameter(u8,unsigned offset,f32){return offset==0x54?-.4f:255;}
unsigned points;
namespace GhostModel {bool emissionPoint(unsigned,unsigned,unsigned n,TVec3f&p){points|=1u<<(n%2);p.set(n%2?10:-10,100,0);return true;}}
'''
        code += function(source, "advance")
        code += r'''
unsigned historyCalls;
namespace Ghost {bool observerVisualAt(unsigned,u32 qf,VisualState*out){
 ++historyCalls;*out={};out->x=qf;out->visualQf=qf;out->recordingToken=1;
 out->fludd.mode=16|8;out->fludd.power=40;return true;}}
'''
        code += function(source, "rebuildWatchWater")
        code += r'''
Water water; Ghost::VisualState state;Gun gun;Mario mario;
extern "C" __declspec(dllexport) void setup(int spray){
 memset(&water,0,sizeof(water));memset(&state,0,sizeof(state));points=0;
 gpMarioOriginal=nullptr;
 water.ready=true;water.qf=100;water.token=1;water.previous.set(0,0,0);
 state.visualQf=104;state.recordingToken=1;
 if(spray){state.x=32;state.fludd.mode=16|8|4;state.fludd.power=40;}
 else{water.drops[0].velocity.set(10,20,30);water.drops[0].life=255;}
}
extern "C" __declspec(dllexport) unsigned burst(){
 setup(1);gun.mNozzleDeformBomb.mEmitParams={};
 gun.mNozzleDeformBomb.mEmitParams.mNum.value=20;
 gun.mNozzleDeformBomb.mEmitParams.mDirTremble.value=1;
 gun.mNozzleDeformBomb.mEmitParams.mSize.value=80;
 mario.mFludd=&gun;gpMarioOriginal=&mario;state.fludd.mode=0x38;
 advance(water,state,0);return water.next;
}
extern "C" __declspec(dllexport) unsigned yoshiBurst(int firing){
 setup(1);gun={};
 gun.mNozzleDeformBomb.mEmitParams.mNum.value=7;
 gun.mNozzleYoshiDeformBomb.mEmitParams.mNum.value=20;
 gun.mNozzleYoshiDeformBomb.mEmitParams.mEmitPow.value=70;
 gun.mNozzleYoshiDeformBomb.mEmitParams.mDirTremble.value=1;
 gun.mNozzleYoshiDeformBomb.mEmitParams.mSize.value=90;
 mario.mFludd=&gun;gpMarioOriginal=&mario;state.fludd.mode=firing?0xb0:0x80;
 state.fludd.power=0;
 advance(water,state,0);return water.next;
}
extern "C" __declspec(dllexport) void run(){advance(water,state,0);}
extern "C" __declspec(dllexport) float field(int i,int n){return ((float*)&water.drops[i])[n];}
extern "C" __declspec(dllexport) unsigned pointMask(){return points;}
extern "C" __declspec(dllexport) void rewind(){state.visualQf=20;state.fludd.mode=0;advance(water,state,0);}
extern "C" __declspec(dllexport) unsigned rebuild(unsigned qf){
 historyCalls=0;points=0;gpMarioOriginal=nullptr;state={};state.x=qf;
 state.visualQf=qf;state.recordingToken=1;state.fludd.mode=16|8;state.fludd.power=40;
 rebuildWatchWater(water,state,0);return historyCalls;}
extern "C" __declspec(dllexport) unsigned emissions(){return water.next;}
'''
        cpp, dll = directory / "test.cpp", directory / "test.dll"
        cpp.write_text(code)
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2", str(cpp), "-o", str(dll)],
                       check=True, capture_output=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.field.restype = C.c_float

    def test_burst_uses_sub_nozzle_spread_and_count(self):
        self.assertEqual(self.lib.burst(), 20)
        self.assertGreater(abs(self.lib.field(0, 3) - 1), 3)

    def test_yoshi_burst_uses_its_own_sub_nozzle_without_gameplay_emission(self):
        self.assertEqual(self.lib.yoshiBurst(1), 20)
        self.assertGreater(abs(self.lib.field(0, 3) - 1), 3)
        self.assertGreater(self.lib.field(0, 5), 0)
        self.assertEqual(self.lib.yoshiBurst(0), 0)

    def test_four_qfs_match_four_retail_moves(self):
        self.lib.setup(0)
        self.lib.run()
        # Runtime: each Step advances four water moves, -0.4 gravity per move.
        expected = [40, 76, 120, 10, 18.4, 30, 251]
        for index, value in enumerate(expected):
            self.assertAlmostEqual(self.lib.field(0, index), value, places=4)

    def test_second_render_pass_and_pause_do_not_advance_twice(self):
        self.lib.setup(0)
        self.lib.run()
        before = [self.lib.field(0, i) for i in range(7)]
        for _ in range(3):
            self.lib.run()
        self.assertEqual([self.lib.field(0, i) for i in range(7)], before)

    def test_hover_uses_both_muzzles_and_retains_inherited_velocity(self):
        self.lib.setup(1)
        self.lib.run()
        self.assertEqual(self.lib.pointMask(), 3)
        self.assertEqual(self.lib.field(0, 0), -10)
        # Mario moves 32 units in four QFs: retail inherits 1/8 of velocity.
        seed = (104 * 1664525) & 0xFFFFFFFF
        self.assertAlmostEqual(self.lib.field(0, 3), 1 + ((seed & 255) - 127) * .016, places=5)
        self.assertEqual(self.lib.field(0, 6), 255)
        self.assertEqual(self.lib.field(3, 6), 252)

    def test_rewind_discards_old_visual_particles(self):
        self.lib.setup(0)
        self.lib.run()
        self.lib.rewind()
        self.assertEqual(self.lib.field(0, 6), 0)

    def test_watch_seek_rebuild_is_bounded_and_uses_recorded_origins(self):
        self.assertEqual(self.lib.rebuild(500), 70)
        self.assertEqual(self.lib.emissions(), 280)
        self.assertEqual(self.lib.pointMask(), 0)
        before = [self.lib.field(0, i) for i in range(7)]
        self.lib.rebuild(600)
        self.lib.rebuild(500)
        self.assertEqual([self.lib.field(0, i) for i in range(7)], before)
        self.assertEqual(self.lib.rebuild(20), 5)
        self.assertEqual(self.lib.emissions(), 20)


if __name__ == "__main__":
    unittest.main()
