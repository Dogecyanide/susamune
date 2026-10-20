"""Native retail-boundary stubs for the production Watch UI/model path."""
from test_native_timer_creation import function


def render_fixture(source, model, scrub):
    code = r'''
class Menu {
public:
 bool open;int toasts;
 bool shown()const{return open;}
 void hide(){open=false;}
 void toast(const char*){++toasts;}
} menu;
Menu *gMenu=&menu;
struct JUTGamePad {enum {A=1,B=2,X=4,Y=8,L=16,R=32,Z=64,
 DPAD_LEFT=128,DPAD_RIGHT=256,DPAD_DOWN=512,DPAD_UP=1024};};
struct TMarioGamePad {enum {CSTICK_LEFT=1,CSTICK_RIGHT=2,CSTICK_DOWN=4,CSTICK_UP=8};};
u8 sSelected;bool sSelectionFailed;
struct Pad {u32 mFrameMeaning;};
struct Application {Pad*mGamePads[1];}gpApplication;
struct TMovieDirector {int mFlags,mState;Pad*mGamePad;};
namespace RetailInput {
 TMovieDirector*movieDirector(){return nullptr;}
 TMarDirector*stageDirector(){return gpMarDirector;}
}
namespace GhostFludd {void beginFrame(){}}
bool sObserverMarioBaselineFinalized;
void releaseObserverMario(bool){}
bool sStageRoutePending,sLiveRouteValid,sBoundaryPending;
void*gpMarioOriginal;
int sAttemptSerial,sClockPhase;
enum {CLOCK_UNAVAILABLE,CLOCK_WAIT_STAGE,CLOCK_PROVISIONAL,CLOCK_ACTIVE,CLOCK_FINISHED};
bool actionsFastForwardActive(){return false;}
void updateProvisionalPlayback(s32){}
void updatePlayback(s32){}
u32 sPlaybackToken;
const SusamuneGhostInputSample*playbackObservation(const Track&,u16,s32){return nullptr;}
int renderedCameraQf;
namespace GhostCamera {
 struct View {f32 position[3],rotation[4],fovy;};
 u32 prefixSize(const void*){return 128;}
 bool evaluate(const void*,u32 qf,u8,View*){renderedCameraQf=qf;return true;}
}
namespace Ghost {
 bool observerPreparing(){return false;}
 bool observerStatsSuppressed(){return observerRunning();}
}
namespace LiveGhost {bool visualState(Ghost::VisualState*){return false;}}
'''
    code += function(scrub, 'jumpSplit')
    code += '\nnamespace GhostScrub {\n'
    for name in ('begin', 'end', 'update'):
        code += function(scrub, name)
    code += '\n}\nnamespace Ghost {\n'
    for name in ('beforeDirect', 'visualFludd', 'visualState', 'secondaryVisualState',
                 'renderVisualState', 'prepareVisual', 'recordedCameraAvailable',
                 'recordedCameraView', 'observerGhostCount'):
        code += function(source, name)
    code += r'''
}
typedef f32 Mtx[3][4];
struct J3DMtxCalc {};
struct J3DAnmTransform {f32 frame;};
J3DAnmTransform animation;
J3DMtxCalc calc;
struct JointNames {int getIndex(const char*){return -1;}};
struct ModelData {JointNames*mJointNames;void**mJoints;int getJointNum(){return 0;}};
struct J3DModel {
 Mtx base;f32 submittedX,calculatedFrame;int entries;
 Mtx*getBaseTRMtx(){return &base;}
 void calc(){calculatedFrame=animation.frame;}
 void viewCalc(){}
 void entry(){submittedX=base[0][3];++entries;}
};
struct ModelSlot {ModelData*data;J3DModel*model;J3DMtxCalc*mtxCalc,*upperCalc;
 J3DMtxCalc*root;J3DAnmTransform*animation;};
enum {SETTING_GHOST_DISPLAY,SETTING_GHOST_APPEARANCE,MODEL_SLOT_COUNT=2};
struct Settings {bool getBool(int){return true;}int get(int){return 2;}}gSettings;
const f32 kAngleToRadians=0.0000958738f;
ModelSlot sSlots[2];ModelData modelData[2];J3DModel models[2];
J3DAnmTransform*marioAnimation(u16,bool,bool=false){return &animation;}
J3DAnmTransform**animationSlot(ModelSlot&s){return &s.animation;}
J3DMtxCalc**rootMtxCalcSlot(ModelSlot&s){return &s.root;}
s16 animationFrameMax(J3DAnmTransform*){return 100;}
f32*animationFrame(J3DAnmTransform*a){return &a->frame;}
f32 pumpFrame(const Ghost::VisualState&,s16){return 0;}
void MTXRotRad(Mtx m,char,f32){memset(m,0,sizeof(Mtx));m[0][0]=m[1][1]=m[2][2]=1;}
void MTXCopy(const Mtx a,Mtx b){memcpy(b,a,sizeof(Mtx));}
bool configureOpacity(ModelSlot&,bool){return true;}
void clearLiveModel(ModelSlot&){}
bool modelPacketsReady(const ModelSlot&){return true;}
void*lightSetFor(const Ghost::VisualState&){return nullptr;}
void ghostLightExit(void*){}
struct AttachmentRequest {};
struct AttachmentModel {J3DModel*model;};
AttachmentRequest desiredAttachment(const Ghost::VisualState&){return {};}
void desiredFludd(const Ghost::VisualState&,AttachmentRequest*){}
void rebuildAttachments(AttachmentRequest*){}
AttachmentModel*prepareAttachment(int,const AttachmentRequest&,const Ghost::VisualState&){return nullptr;}
void entryAttachment(AttachmentModel&){}
struct TCircleShadowRequest {TVec3f mTranslation;f32 mOffsetY,mOffsetY2;int mNeedsProjection;};
struct ShadowManager {void request(const TCircleShadowRequest&,int){}}*gpBindShadowManager;
struct Color {u8 a;}sGhostColor;
u8 ghostAlpha(){return 128;}
const int kAttachments=6;
const u32 kCueCalcView=4,kCueEntry=0x200;
bool sRegistered=true,sHaveVisualState[2],sPrepared[2],sSubmitted[2];
Ghost::VisualState sVisualStates[2];
AttachmentModel*sPreparedAttachments[6];
namespace JDrama {
 struct TGraphics {};
 struct TViewObj {TViewObj(const char*){}virtual void perform(u32,TGraphics*){}};
}
'''
    code += function(model, 'runnerSlot')
    code += function(model, 'prepareRunner')
    code += model[model.index('class GhostView :'):model.index('alignas(32) u8 sViewStorage')]
    code += r'''
#define API extern "C" __declspec(dllexport)
API int openTimeline(){menu.open=true;menu.toasts=0;return GhostScrub::begin();}
API int selected(){return sSelectionFailed?-1:sSelected;}
API int press(int action){
 const u16 buttons[]={0,JUTGamePad::R,JUTGamePad::L,JUTGamePad::X,JUTGamePad::Y,
 JUTGamePad::A,JUTGamePad::B,JUTGamePad::DPAD_RIGHT,JUTGamePad::Z};
 return GhostScrub::update(&menu,0,buttons[action]);
}
API int menuShown(){return menu.shown();}
API void showMenu(int v){menu.open=v;}
API int toastCount(){return menu.toasts;}
API void render(int raw,int frozen){
 director.unk5C=raw;sFrameFrozen=frozen;
 director.mCurState=frozen?TMarDirector::STATE_STAGE_EXIT_2:TMarDirector::STATE_NORMAL;
 Ghost::beforeDirect();
 for(int i=0;i<2;++i){
  sSlots[i].model=&models[i];sSlots[i].data=&modelData[i];sSlots[i].mtxCalc=&calc;
  sPrepared[i]=sSubmitted[i]=false;
 }
 GhostCamera::View camera;Ghost::recordedCameraView(&camera);
 GhostView view;view.perform(kCueCalcView,nullptr);view.perform(kCueEntry,nullptr);
 director.mCurState=TMarDirector::STATE_NORMAL;
}
API float renderedX(int runner){return runnerSlot(runner).model->submittedX;}
API int submitted(int runner){return sSubmitted[runner];}
API int renderedQf(int runner){return sVisualStates[runner].visualQf;}
API int cameraQf(){return renderedCameraQf;}
'''
    return code
