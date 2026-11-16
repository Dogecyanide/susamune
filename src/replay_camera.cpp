#include "susamune/replay_camera.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/practice_session.hxx"
#include "SMS/System/PerformList.hxx"
#include "SMS/System/MarDirector.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_camera.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_trace.h"
#include "susamune/settings.hxx"
#include "susamune/addresses.hxx"
#include "susamune/features.hxx"
#include "susamune/menu.hxx"
#include "JUtility/JUTGamePad.hxx"
#include "Dolphin/math.h"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
extern "C" f32 retailSquareRoot(f32) asm("sqrtf__3stdFf");
extern "C" void susamuneReplaySimulationList(TPerformList *,u32,JDrama::TGraphics *);
extern "C" s32 susamunePracticeChangeState(TMarDirector *);
extern "C" s32 susamuneReplayChangeState(TMarDirector *);
namespace ReplayCamera {
namespace {
struct State {GhostCamera::View camera;float yaw,pitch,motion[5];unsigned tick,generation;bool enabled,release,ticked,simulating;JDrama::TGraphics *graphics;unsigned char graphicsView[0x7c];};
static_assert(sizeof(State)<=0x100,"replay camera stays inside its control lease");
State &s=*reinterpret_cast<State*>(MS_TRACE_CONTROL_PPC+0x3f00);
bool initialized;
bool hookSimulation(bool install){
    const unsigned base=SUSAMUNE_MEM1_ADDR(0x800ecdbcu,0x80299838u,0x802916d0u);
    const unsigned offsets[]={0x308,0x324,0x38c,0x3ac},original[]={0x81830000,0x818c0020,0x7d8803a6,0x4e800021};
    for(unsigned offset:offsets){
        const unsigned site=base+offset,branch=branchWord(site,reinterpret_cast<unsigned>(&susamuneReplaySimulationList))|1u;
        for(unsigned i=0;i<4;++i){
            const unsigned expected=install?original[i]:(i?0x60000000u:branch);
            if(*reinterpret_cast<const unsigned*>(site+i*4)!=expected)return false;
        }
    }
    const unsigned changeSite=base+0x4d4;
    const unsigned changeNative=branchWord(changeSite,reinterpret_cast<unsigned>(&susamunePracticeChangeState))|1u;
    const unsigned changeHook=branchWord(changeSite,reinterpret_cast<unsigned>(&susamuneReplayChangeState))|1u;
    if(*reinterpret_cast<const unsigned*>(changeSite)!=(install?changeNative:changeHook))return false;
    for(unsigned offset:offsets){
        const unsigned site=base+offset,branch=branchWord(site,reinterpret_cast<unsigned>(&susamuneReplaySimulationList))|1u;
        for(unsigned i=0;i<4;++i)writeGameCode(site+i*4,install?(i?0x60000000u:branch):original[i]);
    }
    writeGameCode(changeSite,install?changeHook:changeNative);
    return true;
}
float clamp(float n,float a,float b){return n<a?a:n>b?b:n;}
float scale(SettingId id){const float v[]={.25f,.5f,1,2,4};const unsigned i=gSettings.get(id);return v[i<5?i:2];}
void axes(s8 x,s8 y,float &a,float &b){
    const float length=retailSquareRoot(float(x)*x+float(y)*y);a=b=0;
    if(length<=12)return;const float t=clamp((length-12)/68,0,1),gain=t*t*(3-2*t)/length;a=x*gain;b=y*gain;
}
}
bool active(){return initialized&&s.enabled&&GhostWorldRuntime::active()&&s.generation==GhostStageContext::generation();}
void stop(){if(initialized&&s.enabled){GhostCamera::restore();hookSimulation(false);s.enabled=false;s.graphics=nullptr;}}
bool toggle(){
    if(!GhostWorldRuntime::active())return PracticeSession::requestFreeCameraToggle();
    if(active()){stop();if(gMenu)gMenu->toast("Replay camera off");return true;}
    GhostCamera::View camera;
    if(!GhostCamera::captureView(&camera)){if(gMenu)gMenu->toast("Replay camera needs a loaded scene");return false;}
    if(!hookSimulation(true)){if(gMenu)gMenu->toast("Replay camera unavailable");return false;}
    s={};s.camera=camera;s.generation=GhostStageContext::generation();s.enabled=s.release=true;initialized=true;
    float m[3][3];GhostCamera::matrix(camera,m);s.yaw=atan2f(-m[2][0],-m[2][2]);
    s.pitch=atan2f(-m[2][1],retailSquareRoot(m[2][0]*m[2][0]+m[2][2]*m[2][2]));
    if(gMenu)gMenu->toast("Camera: sticks move/look, L/R height");return true;
}
void update(){
    if(initialized)s.graphics=nullptr;
    if(!active())return;
    const PADStatus &pad=JUTGamePad::mPadStatus[0];const unsigned now=OSGetTick();
    const float dt=s.ticked?clamp(float(now-s.tick)/float(OS_TIMER_CLOCK),0,.1f):1.0f/30;
    s.tick=now;s.ticked=true;
    if(pad.mCurError||(gMenu&&gMenu->shown()))return;
    if(s.release){if(pad.mButton)return;s.release=false;}
    float input[5];axes(static_cast<s8>(pad.mStickX),static_cast<s8>(pad.mStickY),input[0],input[1]);
    axes(static_cast<s8>(pad.mSubStickX),static_cast<s8>(pad.mSubStickY),input[2],input[3]);
    input[4]=(int(pad.mTriggerRight)-int(pad.mTriggerLeft))/255.0f;
    const unsigned smoothing=gSettings.get(SETTING_FREE_CAMERA_SMOOTHING);
    const float gain=smoothing?clamp(dt/(smoothing*.1f),0,1):1;
    for(unsigned i=0;i<5;++i){s.motion[i]+=(input[i]-s.motion[i])*gain;input[i]=s.motion[i];}
    const float frames=dt*30,turn=.035f*scale(SETTING_FREE_CAMERA_SENSITIVITY)*frames;
    s.yaw-=input[2]*turn;if(s.yaw>3.14159265f)s.yaw-=6.2831853f;if(s.yaw< -3.14159265f)s.yaw+=6.2831853f;
    s.pitch=clamp(s.pitch+input[3]*turn,-1.45f,1.45f);
    const float forwardX=sinf(s.yaw),forwardZ=cosf(s.yaw),speed=scale(SETTING_FREE_CAMERA_SPEED)*(pad.mButton&JUTGamePad::X?75:20)*frames;
    const float advance=input[1]*speed,strafe=input[0]*speed*(gSettings.get(SETTING_FREE_CAMERA_STRAFE_REVERSE)?-1:1);
    s.camera.position[0]=clamp(s.camera.position[0]+forwardX*advance-forwardZ*strafe,-1000000,1000000);
    s.camera.position[1]=clamp(s.camera.position[1]+input[4]*speed,-1000000,1000000);
    s.camera.position[2]=clamp(s.camera.position[2]+forwardZ*advance+forwardX*strafe,-1000000,1000000);
    const float sy=sinf(s.yaw*.5f),cy=cosf(s.yaw*.5f),sp=sinf(s.pitch*.5f),cp=cosf(s.pitch*.5f);
    s.camera.rotation[0]=-sp*sy;s.camera.rotation[1]=cp*cy;s.camera.rotation[2]=-sp*cy;s.camera.rotation[3]=cp*sy;
}
bool view(GhostCamera::View &out){if(!active()||s.simulating)return false;out=s.camera;return true;}
void simulation(bool value){if(initialized)s.simulating=value;}
void saveGraphics(JDrama::TGraphics *graphics){
    if(!active()||!graphics)return;
    s.graphics=graphics;memcpy(s.graphicsView,reinterpret_cast<unsigned char*>(graphics)+0x74,sizeof(s.graphicsView));
}
void restoreGraphics(JDrama::TGraphics *graphics){
    if(!active())return;
    GhostCamera::restore();
    if(s.graphics==graphics){
        memcpy(reinterpret_cast<unsigned char*>(graphics)+0x74,s.graphicsView,sizeof(s.graphicsView));s.graphics=nullptr;
    }
}
void beforeStateChange(){if(active())restoreGraphics(s.graphics);}
}
#else
namespace ReplayCamera {
bool active(){return false;}bool toggle(){return PracticeSession::requestFreeCameraToggle();}
void stop(){}void update(){}bool view(GhostCamera::View &){return false;}
void simulation(bool){}
void saveGraphics(JDrama::TGraphics *){}void restoreGraphics(JDrama::TGraphics *){}
void beforeStateChange(){}
}
#endif

// Actor clipping runs during CalcAnim and changes simulation-visible flags.
extern "C" void susamuneReplaySimulationList(TPerformList *list,u32 cue,JDrama::TGraphics *graphics){
    ReplayCamera::restoreGraphics(graphics);
    ReplayCamera::simulation(true);
    list->TPerformList::perform(cue,graphics);
    ReplayCamera::simulation(false);
}

// Chain the existing pause/step hook so cutscene setup sees the simulated view.
extern "C" s32 susamuneReplayChangeState(TMarDirector *director){
    ReplayCamera::beforeStateChange();
    return susamunePracticeChangeState(director);
}
