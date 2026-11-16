"""Read the production metadata sampler against known movement/floor/nozzle states."""
import pathlib, re, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class MetadataValuesTests(unittest.TestCase):
    def test_values_and_discontinuities(self):
        source=(ROOT/'src/metadata_values.cpp').read_text()
        source=re.sub(r'^#include .*\n','',source,flags=re.M)
        source=source.replace('extern "C" f32 metadataSquareRoot(f32) asm("sqrtf__3stdFf");','float metadataSquareRoot(float f){return std::sqrt(f);}')
        mario=(ROOT/'include/SMS/Player/Mario.hxx').read_text()
        enums=mario[mario.index('enum State : u32'):];enums=enums[:enums.index('};')+2]
        extra=(ROOT/'include/susamune/metadata_values.hxx').read_text().split('namespace MetadataValues {',1)[1]
        shim=r"""
#include <cmath>
#include <cstdio>
#include <cassert>
#include <cstring>
#include "susamune/collision_geometry.h"
typedef unsigned u32;typedef unsigned short u16;typedef float f32;
namespace PackedText {const char *at(const char*p,int n){while(n--)while(*p++){}return p;}}
struct Vec{float x,y,z;};
struct TBGCheckData {u16 mFlags,mType;Vec mNormal;};
template<class T>struct Param{T v;T get()const{return v;}};
struct Nozzle {struct {Param<int> mAmountMax,mTriggerTime;} mEmitParams;};
struct TNozzleTrigger:Nozzle {enum {INACTIVE,ACTIVE,DEAD};int mSprayState,mSprayQuarterFramesLeft;};
struct TWaterGun {Nozzle mNozzleDeform;TNozzleTrigger mNozzleHover;int mCurrentWater;};
struct TMario { ENUMS Vec mSpeed,mTranslation;u32 mState;float mFloorBelow;
 TBGCheckData*mFloorTriangle;TWaterGun*mFludd;struct{bool mHasFludd;}mAttributes;};
namespace MetadataValues { EXTRA
""".replace('ENUMS',enums).replace('EXTRA',extra)
        main=r"""
int main(){
 using namespace MetadataValues;
 TMario m={};reset();char out[80];
 m.mSpeed={3,80,4};auto v=read(&m,4);assert(fabs(v.direction-36.8699f)<.001f&&v.gain==0);
 m.mSpeed={6,2,8};v=read(&m,8);assert(fabs(v.gain-5)<.001f);
 assert(read(&m,8).gain==5);assert(read(&m,16).gain==0);
 m.mSpeed={-1,0,0};assert(fabs(read(&m,20).direction-270)<.001f);
 m.mSpeed={0,0,0};v=read(&m,24);format(out,sizeof(out),0,v);assert(!strcmp(out,"--"));
 v=read(&m,4);assert(v.gain==0);reset();assert(read(&m,8).gain==0);
 TBGCheckData floor={0,2,{.6f,.8f,0}};m.mFloorTriangle=&floor;m.mFloorBelow=100;m.mTranslation.y=125;
 v=read(&m,12);assert(v.height==25&&fabs(v.slope-36.8699f)<.001f);format(out,sizeof(out),5,v);assert(!strcmp(out,"Slippery 0002"));
 floor.mFlags=0x10;v=read(&m,16);format(out,sizeof(out),2,v);assert(!strcmp(out,"--"));
 m.mState=TMario::STATE_WALLJUMP;v=read(&m,20);format(out,sizeof(out),3,v);assert(!strcmp(out,"Wallkick"));
 m.mState=0xdeadbeef;v=read(&m,24);format(out,sizeof(out),3,v);assert(strstr(out,"DEADBEEF"));
 TWaterGun gun={};m.mFludd=&gun;m.mAttributes.mHasFludd=true;
 gun.mCurrentWater=150;gun.mNozzleDeform.mEmitParams.mAmountMax.v=300;gun.mNozzleHover.mEmitParams.mTriggerTime.v=300;
 v=read(&m,28);assert(v.water==50&&v.hover==300);
 gun.mNozzleHover.mSprayState=TNozzleTrigger::ACTIVE;gun.mNozzleHover.mSprayQuarterFramesLeft=137;
 assert(read(&m,32).hover==137);gun.mNozzleHover.mSprayState=TNozzleTrigger::DEAD;assert(read(&m,36).hover==0);
 gun.mNozzleHover.mSprayState=0;gun.mCurrentWater=0;assert(read(&m,40).hover==0);
 m.mAttributes.mHasFludd=false;v=read(&m,44);format(out,sizeof(out),6,v);assert(!strcmp(out,"--"));
}
"""
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            folder=pathlib.Path(folder);cpp=folder/'sample.cpp';exe=folder/'sample.exe'
            cpp.write_text(shim+source+main)
            subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-static','-I',str(ROOT/'include'),str(cpp),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
