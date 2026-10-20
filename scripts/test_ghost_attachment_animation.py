"""Execute attachment animation selection and shared-Yoshi restoration."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class AttachmentAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-attachment-animation-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        source = (ROOT / "src/ghost_model.cpp").read_text()
        code = r'''
using u8=unsigned char;using s8=signed char;using u16=unsigned short;using s16=short;
using u32=unsigned;using s32=int;using f32=float;
extern "C" int _fltused=0;
extern "C" void* memset(void*p,int c,unsigned long long n){auto*b=(u8*)p;while(n--)*b++=(u8)c;return p;}
extern "C" int memcmp(const void*a,const void*b,unsigned long long n){auto*x=(const u8*)a;auto*y=(const u8*)b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
extern "C" int strcmp(const char*a,const char*b){while(*a&&*a==*b){++a;++b;}return *a-*b;}
struct J3DTransformInfo {f32 sx,sy,sz;s16 rx,ry,rz;f32 tx,ty,tz;};
static_assert(sizeof(J3DTransformInfo)==32);
struct J3DNode{};
struct J3DJoint {u8 prefix[8];int(*mCallback)(J3DNode*,int);u8 pad[12];J3DTransformInfo transform;u8 tail[28];u32 calc,oldCalc;};
static_assert(__builtin_offsetof(J3DJoint,transform)==0x1c);
static_assert(__builtin_offsetof(J3DJoint,calc)==0x58);
struct Names{int getIndex(const char*)const{return 1;}} names;
struct J3DModelData {u16 count;J3DJoint**mJoints;Names*mJointNames;u16 getJointNum()const{return count;}};
int calculated, cleanDuringCalc;float recordedFrame;unsigned selected;
struct J3DModel {J3DModelData*data;void calc(){++calculated;cleanDuringCalc=1;for(unsigned i=0;i<data->count;++i){auto*j=data->mJoints[i];if(j->mCallback||j->calc||j->oldCalc||j->transform.tx!=recordedFrame+i)cleanDuringCalc=0;}}};
struct MActor {void*mAnmData;};struct Yoshi{MActor*mActor;};struct Mario{Yoshi*mYoshi;};Mario*gpMarioOriginal;
struct AttachmentModel{J3DModelData*data;J3DModel*model;};
struct TWaterGun {enum{Spray=0,Rocket=1,Turbo=5};};
const unsigned SUSAMUNE_GHOST_FLUDD_SPRAYING=16,SUSAMUNE_GHOST_VISUAL_YOSHI=128,kYoshiMaxJointCount=38;
namespace Ghost{struct VisualState{u16 animationId,animationPhase;u32 visualQf;struct{u8 mode,payload[7];}fludd;};}
s16 sYoshiHeadPitch;
int yoshiHeadCallback(J3DNode*,int){return 1;}
bool yoshiUpperJoint(J3DJoint*,J3DJoint*,u16&){return false;}
void ghostFluddTransform(const void*animation,f32 frame,u16 i,J3DTransformInfo*out){recordedFrame=frame;selected=*(const u8*)((const u8*)animation+8);memset(out,0,sizeof(*out));out->tx=frame+i;out->rx=3;}
'''
        literal = source.index("const char kTurboPropName[]")
        code += source[literal:source.index(";", literal) + 1] + "\n"
        for name in ("pumpFrame", "nozzleAnimationIndex", "animateFludd",
                     "yoshiAnimationIndex", "blendYoshiTransform", "animateYoshi"):
            code += function(source, name)
        code += r'''
u8 anmData[64],table[32],keysData[32][40];const u8*keys[32];const char*namesTable[32];
MActor actor;Yoshi yoshi;Mario mario;J3DJoint joint[2];J3DJoint*jointPtr[2];
J3DModelData data;J3DModel model;AttachmentModel attachment;Ghost::VisualState state;
int callback(J3DNode*,int){return 1;}
void setup(){
 memset(joint,0x35,sizeof(joint));memset(anmData,0,sizeof(anmData));memset(table,0,sizeof(table));
 for(unsigned i=0;i<32;++i){memset(keysData[i],0,40);*(s16*)(keysData[i]+2)=32;*(u16*)(keysData[i]+0x22)=2;keysData[i][8]=(u8)i;keys[i]=keysData[i];namesTable[i]="other";}
 namesTable[0]="wg_pump";namesTable[1]="wg_house";
 *(const char***)(table+8)=namesTable;*(const u8***)(table+12)=keys;
 *(u32*)table=26;*(u8**)(anmData+0x2c)=table;actor.mAnmData=anmData;
 yoshi.mActor=&actor;mario.mYoshi=&yoshi;gpMarioOriginal=&mario;
 for(unsigned i=0;i<2;++i){joint[i].mCallback=callback;jointPtr[i]=&joint[i];}
 data={2,jointPtr,&names};model.data=&data;attachment={&data,&model};
 state={0xc1,2048,40,{0}};calculated=cleanDuringCalc=0;
}
extern "C" __declspec(dllexport) int yoshiCase(int invalid){
 setup();J3DJoint before[2];for(int i=0;i<2;++i)before[i]=joint[i];
 if(invalid==1)*(u32*)table=33;
 if(invalid==2)*(u16*)(keysData[15]+0x22)=3;
 if(invalid==3)jointPtr[1]=nullptr;
 bool result=animateYoshi(attachment,state);
 return (result?1:0)|(calculated?2:0)|(cleanDuringCalc?4:0)|(!memcmp(before,joint,sizeof(joint))?8:0);
}
extern "C" __declspec(dllexport) float yoshiRecorded(int blend){
 setup();state.animationId=0xb8;state.animationPhase=3000;
 u8*p=(u8*)&state.fludd;p[0]=128;p[1]=15;p[2]=0;p[3]=120;p[4]=(u8)blend;
 if(!animateYoshi(attachment,state))return -1;
 return recordedFrame;
}
extern "C" __declspec(dllexport) unsigned yoshiSelected(){return selected;}
extern "C" __declspec(dllexport) unsigned nozzle(int n,int firing){return nozzleAnimationIndex((u8)n,firing);}
extern "C" __declspec(dllexport) unsigned yoshiIndex(unsigned id,int firing){Ghost::VisualState s={(u16)id,0,0,{(u8)(firing?16:0)}};return yoshiAnimationIndex(s);}
extern "C" __declspec(dllexport) unsigned fluddCase(unsigned nozzle,int firing,int body,unsigned qf){setup();*(u32*)table=8;state.fludd.mode=(u8)(nozzle|8|(firing?16:0));state.visualQf=qf;animateFludd(&data,&actor,body,state);return selected|((unsigned)(u16)joint[1].transform.rx<<8);}
'''
        # The two adjacent retail table pointers are 32-bit. Shift the name
        # pointer in this host-only surrogate; production offsets stay exact.
        code = code.replace("table + 8", "table + 24").replace("(table+8)", "(table+24)")
        cpp, dll = directory / "test.cpp", directory / "test.dll"
        cpp.write_text(code)
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2", str(cpp), "-o", str(dll)],
                       check=True, capture_output=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.fluddCase.restype = C.c_uint
        cls.lib.yoshiRecorded.restype = C.c_float

    def test_yoshi_calculates_private_model_and_restores_all_shared_joint_state(self):
        self.assertEqual(self.lib.yoshiCase(0), 15)

    def test_invalid_animation_and_joint_tables_leave_shared_state_untouched(self):
        for failure in (1, 2, 3):
            self.assertEqual(self.lib.yoshiCase(failure), 8)

    def test_recorded_yoshi_uses_own_frame_and_blend_instead_of_rider_phase(self):
        self.assertEqual(self.lib.yoshiRecorded(0), 7.5)
        self.assertEqual(self.lib.yoshiSelected(), 15)
        self.assertEqual(self.lib.yoshiRecorded(127), 7.5)
        self.assertEqual(self.lib.yoshiSelected(), 24)

    def test_spray_uses_its_own_table_and_secondary_nozzles_keep_trigger_keys(self):
        self.assertEqual([self.lib.nozzle(0, n) for n in (0, 1)], [6, 5])
        for nozzle in (1, 2, 4, 5):
            self.assertEqual([self.lib.nozzle(nozzle, n) for n in (0, 1)], [3, 2])

    def test_rider_running_jump_and_flutter_choose_yoshi_motion(self):
        for rider, yoshi in ((0xc1, 15), (0xbd, 10), (0xbc, 9), (0xc6, 22)):
            self.assertEqual(self.lib.yoshiIndex(rider, 0), yoshi)
        self.assertEqual(self.lib.yoshiIndex(0xb8, 0), 12)
        self.assertEqual(self.lib.yoshiIndex(0xb8, 1), 13)

    def test_turbo_propeller_uses_recorded_time_and_retains_idle_pose(self):
        self.assertEqual(self.lib.fluddCase(5, 1, 0, 4), 2 | ((3 + 8192) << 8))
        self.assertEqual(self.lib.fluddCase(5, 1, 0, 4), 2 | ((3 + 8192) << 8))
        self.assertEqual(self.lib.fluddCase(5, 0, 0, 4), 3 | (3 << 8))
        self.assertEqual(self.lib.fluddCase(1, 1, 0, 4), 2 | (3 << 8))

    def test_secondary_nozzle_firing_keeps_backpack_handle_retracted(self):
        self.assertEqual(self.lib.fluddCase(0, 1, 1, 4) & 255, 0)
        for nozzle in (1, 4, 5):
            self.assertEqual(self.lib.fluddCase(nozzle, 1, 1, 4) & 255, 1)


if __name__ == "__main__":
    unittest.main()
