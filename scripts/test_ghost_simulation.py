"""Exercise the production settings snapshot and pre-movement camera latch."""
import os,pathlib,re,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class GhostSimulationTests(unittest.TestCase):
    def test_snapshot_and_camera_ownership(self):
        compiler=shutil.which('g++') or ('C:/msys64/mingw64/bin/g++.exe' if pathlib.Path('C:/msys64/mingw64/bin/g++.exe').is_file() else None)
        if not compiler:self.skipTest('host C++ compiler unavailable')
        source=(ROOT/'src/ghost_simulation.cpp').read_text()
        source=re.sub(r'^#include .*\n','',source,flags=re.M)
        header=(ROOT/'include/susamune/ghost_simulation.hxx').read_text()
        header=re.sub(r'^#include .*\n|^#pragma once\n','',header,flags=re.M)
        validator=(ROOT/'include/susamune/ghost_simulation_settings.h').read_text()
        setting_list=(ROOT/'include/susamune/settings_list.h').read_text()
        shim=r'''
#include <cassert>
#include <cstring>
#include <cstdint>
#include <new>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif
using u8=unsigned char;using u32=unsigned;using f32=float;
SETTINGS
#define SETTING_ENUM(id,key) id,
enum SettingId { SUSAMUNE_SETTING_LIST(SETTING_ENUM) SETTING_COUNT };
#undef SETTING_ENUM
enum {SETTINGS_SAVE_PENDING=1};static int refuseOnce=-1;
struct Settings {u8 values[SETTING_COUNT];u8 get(SettingId id)const{return values[id];}
 int saveState()const{return 0;}bool setTransient(SettingId id,u8 value){if(refuseOnce==id){refuseOnce=-1;return false;}values[id]=value;return true;}
} gSettings;
static u8 patterns[3]={1,3,4};static bool suppressText,fastForward,freeCamera;static float cadence=60;
static u32 stickMode=1;
#define SUSAMUNE_MEM1_ADDR(j,u,p) reinterpret_cast<__UINTPTR_TYPE__>(&stickMode)
namespace StageLoader {bool fastTextSuppressed(){return suppressText;}}
namespace PracticeSession {bool freeCamera(){return ::freeCamera;}}
namespace PatternSelector {void copyPatterns(u8 out[3]){memcpy(out,patterns,3);}void setPatternsTransient(const u8 in[3]){memcpy(patterns,in,3);}}
bool actionsFastForwardActive(){return fastForward;}
float SMSGetVSyncTimesPerSec(){return cadence;}
struct TFlagManager {static TFlagManager*smInstance;bool removed;bool getBool(unsigned key){assert(key==0x1038b);return removed;}};
TFlagManager*TFlagManager::smInstance;
struct TMario {char pad[0x118];struct{bool mIsPerforming;}mAttributes;char more[0x14e - 0x119];unsigned short _14E;};
struct CPolarSubCamera {char pad[0x50];int mode;char more[0x258-0x54];short mAngleYaw;};
struct TMarDirector {bool _260;};
static TMario*gpMarioOriginal;static CPolarSubCamera*gpCamera;static TMarDirector*gpMarDirector,*activeDirector;
namespace RetailInput {TMarDirector*stageDirector(){return activeDirector;}}
'''.replace('\nSETTINGS\n','\n'+setting_list+'\n')
        main=r'''
static unsigned word(const unsigned char*p){return unsigned(p[0])<<24|unsigned(p[1])<<16|unsigned(p[2])<<8|p[3];}
int main(){
 using namespace GhostSimulation;
 Snapshot a,b;memset(&a,0xff,sizeof(a));capture(a);
 assert(SusamuneGhostSimulationSettingsValid(a.bytes));
 assert(a.bytes[SIRENA_PINEAPPLE_REMOVED]==255&&a.bytes[PATTERN_0]==1&&a.bytes[PATTERN_1]==3&&a.bytes[PATTERN_2]==4);
 assert(word(a.bytes+CADENCE_F32_BE)==0x42700000&&word(a.bytes+STICK_MODE_U32_BE)==1);
 gSettings.values[SETTING_FAST_TEXT]=1;capture(a);assert(a.bytes[EFFECTIVE_FAST_TEXT]==1);
 suppressText=true;capture(b);assert(b.bytes[FAST_TEXT]==1&&b.bytes[EFFECTIVE_FAST_TEXT]==0&&memcmp(&a,&b,sizeof(a)));
 a=b;gSettings.values[SETTING_GHOST_OPACITY]=3;capture(b);assert(!memcmp(&a,&b,sizeof(a)));
 TFlagManager flags={true};TFlagManager::smInstance=&flags;capture(a);assert(a.bytes[SIRENA_PINEAPPLE_REMOVED]==1&&flags.removed);
 gSettings.values[SETTING_GAMEPLAY_SPEED]=33;gSettings.values[SETTING_GELATO_BLUE_BIRD_PATTERN]=4;fastForward=true;freeCamera=true;patterns[2]=2;
 unsigned char before[SETTING_COUNT];memcpy(before,gSettings.values,sizeof(before));capture(a);
 assert(a.bytes[GAMEPLAY_SPEED]==33&&a.bytes[GELATO_BLUE_BIRD_PATTERN]==4&&a.bytes[PATTERN_2]==2&&a.bytes[FAST_FORWARD_ACTIVE]&&a.bytes[FREE_CAMERA_ACTIVE]);
 assert(!memcmp(before,gSettings.values,sizeof(before))&&stickMode==1&&cadence==60&&flags.removed&&patterns[2]==2);
 assert(a.bytes[47]==0);for(unsigned i=56;i<64;++i)assert(a.bytes[i]==0);
 assert(SusamuneGhostSimulationSettingsValid(a.bytes));
 for(unsigned i=0;i<64;++i){b=a;b.bytes[i]=255;if(i!=46 && (i<48 || i>=52))assert(!SusamuneGhostSimulationSettingsValid(b.bytes));}
 b=a;b.bytes[FAST_TEXT]=0;b.bytes[EFFECTIVE_FAST_TEXT]=1;assert(!SusamuneGhostSimulationSettingsValid(b.bytes));
 b=a;b.bytes[48]=0x7f;b.bytes[49]=0x80;assert(!SusamuneGhostSimulationSettingsValid(b.bytes));
 assert(!SusamuneGhostSimulationSettingsValid(nullptr));
 Snapshot requested=a;requested.bytes[PATTERN_0]=2;requested.bytes[PATTERN_1]=1;requested.bytes[PATTERN_2]=4;
 unsigned char originalPatterns[3];memcpy(originalPatterns,patterns,3);
 SettingsLease lease={};assert(sizeof(lease)==44);assert(beginSettings(lease,requested.bytes));
 assert(patterns[0]==2&&patterns[1]==1&&patterns[2]==4);assert(!beginSettings(lease,requested.bytes));
 restoreSettings(lease);assert(!lease.active&&!memcmp(originalPatterns,patterns,3));assert(!memcmp(before,gSettings.values,sizeof(before)));
 refuseOnce=SETTING_FLUDD_SECRETS;assert(!beginSettings(lease,requested.bytes));
 assert(!lease.active&&!memcmp(originalPatterns,patterns,3)&&!memcmp(before,gSettings.values,sizeof(before)));
 requested.bytes[PATTERN_0]=5;assert(!beginSettings(lease,requested.bytes));assert(!memcmp(originalPatterns,patterns,3));
 void*ram;
#ifdef _WIN32
 ram=VirtualAlloc(reinterpret_cast<void*>(0x81000000),0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
#else
 ram=mmap(reinterpret_cast<void*>(0x81000000),0x10000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
#endif
 assert(ram==reinterpret_cast<void*>(0x81000000));
 gpMarioOriginal=new(ram)TMario{};gpCamera=new(static_cast<char*>(ram)+0x2000)CPolarSubCamera{};
 TMarDirector director={true},otherDirector={true};gpMarDirector=activeDirector=&director;gpCamera->mode=73;gpCamera->mAngleYaw=-12345;
 CameraObservation c;beginFrame();readCamera(c);assert(!c.valid&&!c.tickCount&&!c.varied);
 observeMovement(gpMarioOriginal,4);readCamera(c);assert(!c.valid&&!c.tickCount);
 observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.valid&&c.tickCount==1&&c.yaw==-12345&&c.mode==73&&!c.varied);
 observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.tickCount==2&&!c.varied);
 gpCamera->mAngleYaw=22222;readCamera(c);assert(c.yaw==-12345);
 observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.valid&&c.tickCount==3&&c.yaw==22222&&c.varied);
 gpCamera->mode=-1;observeMovement(gpMarioOriginal,1);readCamera(c);assert(!c.valid&&c.tickCount==4);
 gpCamera->mode=5;observeMovement(gpMarioOriginal,1);readCamera(c);assert(!c.valid&&c.tickCount==5);
 beginFrame();gpMarioOriginal->_14E=2;observeMovement(gpMarioOriginal,1);readCamera(c);assert(!c.valid&&!c.tickCount);
 gpMarioOriginal->_14E=1;observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.valid&&c.tickCount==1);
 gpMarioOriginal->mAttributes.mIsPerforming=true;observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.tickCount==1);
 activeDirector=&otherDirector;readCamera(c);assert(!c.valid);observeMovement(gpMarioOriginal,1);readCamera(c);assert(c.tickCount==1);
 activeDirector=&director;gpMarioOriginal->mAttributes.mIsPerforming=false;gpCamera=nullptr;beginFrame();observeMovement(gpMarioOriginal,1);readCamera(c);assert(!c.valid&&c.tickCount==1);
 beginFrame();gpMarioOriginal=nullptr;observeMovement(nullptr,1);readCamera(c);assert(!c.valid&&!c.tickCount);
#ifdef _WIN32
 VirtualFree(ram,0,MEM_RELEASE);
#else
 munmap(ram,0x10000);
#endif
}
'''
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='ghost-simulation-') as folder:
            d=pathlib.Path(folder);(d/'test.cpp').write_text(shim+validator+header+source+main)
            env=dict(os.environ,PATH=str(pathlib.Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
            subprocess.run([compiler,'-std=c++17','-O2',str(d/'test.cpp'),'-o',str(d/'test.exe')],check=True,env=env)
            subprocess.run([str(d/'test.exe')],check=True,env=env)
if __name__=='__main__':unittest.main()
