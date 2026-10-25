"""Accepted burst capture must not be inferred from the controller or lost later."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class EmissionCaptureTests(unittest.TestCase):
    def test_accepted_burst_retention_and_nonemitting_rejection(self):
        source = (ROOT / 'src/ghost_fludd.cpp').read_text()
        code = r'''
using u8=unsigned char;using s32=int;using u32=unsigned;using f32=float;
#include "susamune/ghost_fludd.h"
extern "C" int _fltused=0;
struct Vec {float x,y,z;};
template<class T>struct Param{T value;const T&get()const{return value;}};
struct TWaterEmitInfo{Param<Vec>mPos,mDir;Param<float>mPow;};
struct TNozzleTrigger{enum{INACTIVE,ACTIVE,DEAD};unsigned mSprayState;};
struct TNozzleBase{int getGunAngle()const{return 256;}};
struct TWaterGun{enum{Spray=0,Yoshi=3,Hover=4};TWaterEmitInfo*mEmitInfo;
 u8 mCurrentNozzle;TNozzleTrigger mNozzleDeformBomb,mNozzleYoshiDeformBomb;
 TNozzleBase*mNozzleList[6];};
struct J3DFrameCtrl{float mCurFrame,mNumFrames;};
struct J3DJoint{};
struct ModelData{J3DJoint*mJoints[22];int getJointNum()const{return 22;}};
struct Model{ModelData*mModelData;};
struct Bck{float getMotionBlendRatio()const{return 0;}};
struct MActor{enum{BCK};Bck*mBckInfo;Model*mModel;J3DFrameCtrl frame;
 int getCurAnmIdx(int)const{return 15;}const J3DFrameCtrl*getFrameCtrl(int)const{return &frame;}};
struct TYoshi{enum{MOUNTED=1};int mState;MActor*mActor;u8 padding[128];};
struct TMario{TWaterGun*mFludd;TYoshi*mYoshi;};
TMario*gpMarioOriginal;TMario*sEmitter;
Vec sPosition,sDirection;float sPower;bool sEmitted,sBurst,sHoverEmitted;u8 sNozzle;
bool stage=true;namespace RetailInput {bool stageDirector(){return stage;}}
bool finite(float value){return value>=-1000000&&value<=1000000;}
'''
        code += function(source, 'observe')
        code += function(source, 'captureYoshi')
        code += r'''
extern "C" __declspec(dllexport) unsigned run(unsigned scenario){
 TWaterEmitInfo a={{{1,2,3}},{{0,0,1}},{70}},other={};
 TWaterGun gun={&a,0,{TNozzleTrigger::ACTIVE},{TNozzleTrigger::ACTIVE},{}};TMario mario={&gun,nullptr};
 gpMarioOriginal=&mario;sEmitter=nullptr;sEmitted=sBurst=sHoverEmitted=false;sNozzle=255;stage=true;
 if(scenario==0)observe(a,0);
 if(scenario==1)observe(other,1);
 if(scenario==2){stage=false;observe(a,1);}
 if(scenario==4){gun.mCurrentNozzle=4;observe(a,0);}
 if(scenario==5){gun.mCurrentNozzle=4;observe(a,1);}
 if(scenario==3){observe(a,1);gun.mNozzleDeformBomb.mSprayState=TNozzleTrigger::INACTIVE;
   gun.mCurrentNozzle=4;a.mPow.value=30;observe(a,1);}
 if(scenario>=6){
   gun.mCurrentNozzle=3;
   if(scenario==7)gun.mNozzleYoshiDeformBomb.mSprayState=TNozzleTrigger::INACTIVE;
   if(scenario==8){gun.mCurrentNozzle=0;gun.mNozzleDeformBomb.mSprayState=TNozzleTrigger::INACTIVE;}
   if(scenario==11)gun.mNozzleYoshiDeformBomb.mSprayState=TNozzleTrigger::DEAD;
   observe(a,scenario==9?0:1);
   if(scenario==10){gun.mNozzleYoshiDeformBomb.mSprayState=TNozzleTrigger::INACTIVE;a.mPow.value=30;observe(a,1);}
 }
 return (sHoverEmitted?0x80000000u:0)|(sEmitted?1:0)|(sBurst?2:0)|((unsigned)sNozzle<<8)|((unsigned)sPower<<16);
}
extern "C" __declspec(dllexport) unsigned yoshiCapture(unsigned scenario){
 run(scenario);ModelData data={};Model model={&data};Bck bck;
 MActor actor={&bck,&model,{7.5f,16}};TYoshi yoshi={TYoshi::MOUNTED,&actor,{}};
 TWaterGun gun={};TMario mario={&gun,&yoshi};
 // Preserve the accepted observation while replacing the stack-bound actor.
 gpMarioOriginal=&mario;if(sEmitter)sEmitter=&mario;
 SusamuneGhostFluddSample sample={};
 captureYoshi(sample,&mario);
 return sample.mode|(SusamuneGhostVisualValid((const u8*)&sample,1)?0x100:0);
}
'''
        with tempfile.TemporaryDirectory(prefix='moonshine-emission-') as folder:
            cpp, dll = Path(folder) / 'test.cpp', Path(folder) / 'test.dll'
            cpp.write_text(code)
            result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'),
                '--target=x86_64-pc-windows-msvc', '-O2', '-shared', '-nostdlib',
                '-fuse-ld=lld', '-Wl,/noentry', '-I', str(ROOT / 'include'), str(cpp), '-o', str(dll)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lib = C.CDLL(str(dll))
            try:
                for case in (0, 1, 2):
                    self.assertEqual(lib.run(case) & 0xffff, 0xff00)
                lib.run.restype = C.c_uint
                self.assertEqual(lib.run(3), 0x80000000 | 3 | (70 << 16))
                self.assertFalse(lib.run(4) & 0x80000000)
                self.assertTrue(lib.run(5) & 0x80000000)
                for case in (6, 10):
                    self.assertEqual(lib.run(case), 3 | (3 << 8) | (70 << 16))
                    self.assertEqual(lib.yoshiCapture(case), 0x1b0)
                for case in (7, 8, 11):
                    self.assertFalse(lib.run(case) & 2)
                    self.assertEqual(lib.yoshiCapture(case), 0x190)
                self.assertEqual(lib.yoshiCapture(9), 0x180)
            finally:
                _ctypes.FreeLibrary(lib._handle)


if __name__ == '__main__':
    unittest.main()
