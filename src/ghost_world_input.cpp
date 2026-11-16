#include "susamune/ghost_world_input.hxx"
#if defined(__powerpc__)
#include "SMS/Player/MarioGamePad.hxx"
static_assert(sizeof(TMarioGamePad)==0xf0&&sizeof(TMarioControllerWork)==0x24,"native controller sizes");
static_assert(sizeof(JUTGamePad::CButton)==48&&sizeof(JUTGamePad::CStick)==16,"native JUT scalar sizes");
static_assert(__builtin_offsetof(TMarioGamePad,mButtons)==0x18&&
    __builtin_offsetof(TMarioGamePad,mControlStick)==0x48&&__builtin_offsetof(TMarioGamePad,mCStick)==0x58&&
    __builtin_offsetof(TMarioGamePad,_A8)==0xa8&&__builtin_offsetof(TMarioGamePad,_CC)==0xcc&&
    __builtin_offsetof(TMarioGamePad,mMeaning)==0xd0&&__builtin_offsetof(TMarioGamePad,mFrameMeaning)==0xd4&&
    __builtin_offsetof(TMarioGamePad,_D8)==0xd8&&__builtin_offsetof(TMarioGamePad,_DC)==0xdc&&
    __builtin_offsetof(TMarioGamePad,_DE)==0xde&&__builtin_offsetof(TMarioGamePad,_E0)==0xe0&&
    __builtin_offsetof(TMarioGamePad,mState)==0xe2&&__builtin_offsetof(TMarioGamePad,_E4)==0xe4&&
    __builtin_offsetof(TMarioGamePad,_E8)==0xe8,"native pad scalar offsets");
static_assert(__builtin_offsetof(TMarioControllerWork,mInput)==4&&
    __builtin_offsetof(TMarioControllerWork,mFrameInput)==8&&__builtin_offsetof(TMarioControllerWork,mAnalogRU8)==12&&
    __builtin_offsetof(TMarioControllerWork,mAnalogLU8)==13&&__builtin_offsetof(TMarioControllerWork,mStickH)==16&&
    __builtin_offsetof(TMarioControllerWork,mStickV)==20&&__builtin_offsetof(TMarioControllerWork,mStickDist)==24&&
    __builtin_offsetof(TMarioControllerWork,mAnalogL)==28&&__builtin_offsetof(TMarioControllerWork,mAnalogR)==32,
    "native work offsets; decomp names right at1c and left at20");
#endif

namespace GhostWorldInput {
namespace {
const unsigned kButtons=0x0f0f1f7fu,kMeanings=0x003fffffu;
static_assert(__builtin_offsetof(Trace::Buttons,analogL)==16&&__builtin_offsetof(Trace::Buttons,repeat)==24&&
    __builtin_offsetof(Trace::Buttons,repeatState)==32&&__builtin_offsetof(Trace::Stick,angle)==12&&
    __builtin_offsetof(Trace::Stick,rawX)==14&&__builtin_offsetof(Trace::Stick,rawY)==15,"canonical JUT scalar layout");
static_assert(__builtin_offsetof(Trace::ProcessedPad,meaning)-__builtin_offsetof(Trace::ProcessedPad,meaningAxes)==40&&
    __builtin_offsetof(Trace::ProcessedPad,flags)-__builtin_offsetof(Trace::ProcessedPad,meaningAxes)==58,
    "canonical compensation/meaning/analog span excludes mode flags");
static_assert(__builtin_offsetof(Trace::ControllerWork,x)==16&&__builtin_offsetof(Trace::ControllerWork,left)==28&&
    __builtin_offsetof(Trace::ControllerWork,right)==32,"canonical work trigger order");
bool range(float value,float low,float high) {
    unsigned bits;__builtin_memcpy(&bits,&value,4);
    return (bits&0x7f800000u)!=0x7f800000u&&value>=low&&value<=high;
}
bool buttons(const Trace::Buttons &b) {
    return !((b.held|b.pressed|b.released|b.repeat|b.repeatState[0]|b.repeatState[1])&~kButtons)&&
        !(b.pressed&b.released)&&range(b.analogL,0,1.71f)&&range(b.analogR,0,1.71f)&&
        (!b.repeatState[1]||!b.repeatState[2]||b.repeatState[3]);
}
bool stick(const Trace::Stick &s) {
    // Non-clamped SDK mode can retain raw axes divided by the42-unit C-stick radius.
    return range(s.x,-4,4)&&range(s.y,-4,4)&&range(s.magnitude,0,1);
}
bool shared(const Trace::SharedPad &s) { return buttons(s.buttons)&&stick(s.stick)&&stick(s.substick); }
bool input(const Trace::Input &i,bool restoreWork) {
    const bool boundary=(i.flags&Trace::kFrameInput)!=0;
    if((boundary?(i.cue||(i.flags&~(Trace::kFrameInput|3u))||i.valid!=1):(!(i.cue&1u)||i.flags||!(i.valid&1u)||(i.valid&~3u)||(restoreWork&&i.valid!=3)))||
       (i.raw.buttons&~0x1f7fu)||i.raw.error||i.raw.reserved||i.sharedKnown>1)return false;
    const Trace::ProcessedPad &p=i.pad;
    if(!buttons(p.buttons)||!stick(p.stick)||!stick(p.substick)||
       ((p.meaning|p.pressedMeaning|p.releasedMeaning)&~kMeanings)||
       ((p.analogHeld|p.analogPressed|p.analogReleased)&~1u))return false;
    for(unsigned n=0;n<10;++n)
        if(!range(p.meaningAxes[n],n==2||n==3?0.0f:-4.0f,n==2||n==3?255.0f:4.0f))return false;
    if(!boundary&&restoreWork) {
        const Trace::ControllerWork &w=i.work;
        if(((w.held|w.pressed)&~0x4330u)||!range(w.x,-32768,32768)||!range(w.y,-32768,32768)||
           !range(w.magnitude,0,64)||!range(w.left,0,1)||!range(w.right,0,1))return false;
    }
    return !i.sharedKnown||shared(i.shared);
}
Error validPlan(const Plan &p) {
    if(p.work<PRESERVE_NATIVE_WORK||p.work>RESTORE_INITIALIZED_WORK||
       !input(p.input,p.work==RESTORE_INITIALIZED_WORK)||p.mirrors<CAPTURED_SHARED||p.mirrors>EXPERIMENTAL_PAD_MIRROR)return INVALID_INPUT;
    if(p.work==RESTORE_INITIALIZED_WORK&&!p.workProven)return WORK_PROOF_REQUIRED;
    if((p.mirrors==CAPTURED_SHARED||p.mirrors==RECONSTRUCTED_SHARED)&&!p.input.sharedKnown)return MISSING_SHARED;
    return OK;
}
using Address=__UINTPTR_TYPE__;
bool span(const void *p,unsigned bytes) {
    const Address a=reinterpret_cast<Address>(p);
    if(!a||(a&3u)||a+bytes<a)return false;
#if defined(__powerpc__)
    if(a<0x80003100u||a+bytes>0x81800000u)return false;
#endif
    return true;
}
bool overlaps(const void *a,unsigned an,const void *b,unsigned bn) {
    const Address x=reinterpret_cast<Address>(a),y=reinterpret_cast<Address>(b);
    return x<y+bn&&y<x+an;
}
bool targets(const Borrow &b,const Plan *plan=nullptr) {
    const void *p[]={b.targets.pad,b.targets.work,b.targets.sharedButtons,b.targets.sharedStick,b.targets.sharedSubstick};
    const unsigned bytes[]={240,36,48,16,16};
    for(unsigned i=0;i<5;++i) {
        if(i==1&&!p[i])continue;
        if(!span(p[i],bytes[i])||overlaps(p[i],bytes[i],&b,sizeof(b))||
           (plan&&overlaps(p[i],bytes[i],plan,sizeof(*plan))))return false;
        for(unsigned j=0;j<i;++j)if(p[j]&&overlaps(p[i],bytes[i],p[j],bytes[j]))return false;
    }
    return true;
}
template<class T>T load(const void *p,unsigned offset) {
    T value;__builtin_memcpy(&value,static_cast<const unsigned char*>(p)+offset,sizeof(value));return value;
}
template<class T>void store(void *p,unsigned offset,const T &value) {
    __builtin_memcpy(static_cast<unsigned char*>(p)+offset,&value,sizeof(value));
}
ModeState mode(const Targets &t) {
    return {load<unsigned short>(t.pad,0xe2),load<short>(t.pad,0xe4),load<int>(t.pad,0xe8)};
}
void readPad(const Targets &t,Trace::ProcessedPad &out) {
    const auto *p=reinterpret_cast<const unsigned char*>(t.pad);
    __builtin_memcpy(&out.buttons,p+0x18,48);__builtin_memcpy(&out.stick,p+0x48,16);
    __builtin_memcpy(&out.substick,p+0x58,16);__builtin_memcpy(reinterpret_cast<unsigned char*>(&out)+__builtin_offsetof(Trace::ProcessedPad,meaningAxes),p+0xa8,58);
    const ModeState m=mode(t);out.flags=m.flags;out.stickTimer=m.stickTimer;out.disabledFrames=m.disabledFrames;
}
void writePad(const Targets &t,const Trace::ProcessedPad &in) {
    auto *p=reinterpret_cast<unsigned char*>(t.pad);
    __builtin_memcpy(p+0x18,&in.buttons,48);__builtin_memcpy(p+0x48,&in.stick,16);
    __builtin_memcpy(p+0x58,&in.substick,16);__builtin_memcpy(p+0xa8,reinterpret_cast<const unsigned char*>(&in)+__builtin_offsetof(Trace::ProcessedPad,meaningAxes),58);
}
void readShared(const Targets &t,Trace::SharedPad &out) {
    __builtin_memcpy(&out.buttons,t.sharedButtons,48);__builtin_memcpy(&out.stick,t.sharedStick,16);
    __builtin_memcpy(&out.substick,t.sharedSubstick,16);
}
void writeShared(const Targets &t,const Trace::SharedPad &in) {
    __builtin_memcpy(t.sharedButtons,&in.buttons,48);__builtin_memcpy(t.sharedStick,&in.stick,16);
    __builtin_memcpy(t.sharedSubstick,&in.substick,16);
}
void readWork(const Targets &t,Trace::ControllerWork &out) {
    const auto *p=reinterpret_cast<const unsigned char*>(t.work);
    __builtin_memcpy(&out,p,14);__builtin_memcpy(reinterpret_cast<unsigned char*>(&out)+16,p+16,12);
    out.right=load<float>(p,28);out.left=load<float>(p,32);
}
void writeWork(const Targets &t,const Trace::ControllerWork &in) {
    auto *p=reinterpret_cast<unsigned char*>(t.work);
    __builtin_memcpy(p,&in,14);__builtin_memcpy(p+16,reinterpret_cast<const unsigned char*>(&in)+16,12);
    store(p,28,in.right);store(p,32,in.left);
}
Error enter(Borrow &b) {
    const GuardResult result=b.guard.enter(b.guard.context,b.owner,b.targets);
    if(result==OWNED)return OK;
    if(result==BUSY)return b.error=BUSY_OWNER;
    b.active=false;b.targets={};return b.error=STALE_OWNER;
}
}
Error prepare(Plan &out,const Trace::Input &source,MirrorPolicy policy,const Trace::SharedPad *reconstructed,
              WorkPolicy work,bool initializationAndOrderProven) {
    Plan candidate={source,policy,work,initializationAndOrderProven};
    if(policy==RECONSTRUCTED_SHARED) {
        if(!reconstructed)return MISSING_SHARED;
        candidate.input.shared=*reconstructed;candidate.input.sharedKnown=1;
    }
    const Error error=validPlan(candidate);
    if(error==OK)out=candidate;
    return error;
}
Error begin(Borrow &b,const Targets &native,Owner owner,Guard guard) {
    if(b.active)return b.error=ALREADY_BORROWED;
    if(!owner.generation||!owner.token||!guard.enter||!guard.leave)return b.error=OWNER_REQUIRED;
    const Targets copy=native;
    b={};b.targets=copy;b.owner=owner;b.guard=guard;
    if(!targets(b))return b.error=INVALID_TARGET;
    const Error acquired=enter(b);if(acquired!=OK)return acquired;
    readPad(b.targets,b.backup.pad);readShared(b.targets,b.backup.shared);
    if(b.targets.work)readWork(b.targets,b.backup.work);
    b.active=true;b.guard.leave(b.guard.context);return b.error=OK;
}
Error apply(Borrow &b,const Plan &plan,Controls controls) {
    if(!b.active)return b.error=NOT_BORROWED;
    if(overlaps(&b,sizeof(b),&plan,sizeof(plan)))return b.error=INVALID_TARGET;
    const Error valid=validPlan(plan);if(valid!=OK)return b.error=valid;
    if(!targets(b,&plan))return b.error=INVALID_TARGET;
    const bool boundary=(plan.input.flags&Trace::kFrameInput)!=0;
    const unsigned actual=(controls.frozen?1u:0u)|(controls.suppressed?2u:0u);
    if((boundary?b.boundaryApplied:!b.boundaryApplied)||(!boundary&&((b.controls&1u)||controls.setupResetsMode)))return b.error=INPUT_PHASE;
    if(actual!=(boundary?(plan.input.flags&3u):b.controls))return b.error=CONTROL_MISMATCH;
    if(!boundary&&plan.work==RESTORE_INITIALIZED_WORK&&!b.targets.work)return b.error=INVALID_TARGET;
    const Error acquired=enter(b);if(acquired!=OK)return acquired;
    b.expected={plan.input.pad.flags,plan.input.pad.stickTimer,plan.input.pad.disabledFrames};
    // Pad suppression does not prevent the native setup2 flags reset.
    const bool setupReset=boundary&&controls.setupResetsMode&&!controls.frozen;
    // These are reset's canonical counters; menu/camera leftovers are not replay initial state.
    if(setupReset&&controls.initialStage&&!b.expected.stickTimer&&!b.expected.disabledFrames) {
        auto *pad=reinterpret_cast<unsigned char*>(b.targets.pad);
        store<short>(pad,0xe4,0);store<int>(pad,0xe8,0);
    }
    b.observed=mode(b.targets);
    const bool exactMode=b.observed.flags==b.expected.flags&&b.observed.stickTimer==b.expected.stickTimer&&
        b.observed.disabledFrames==b.expected.disabledFrames;
    if(boundary&&controls.haveHistory&&!exactMode) {
        const ModeState &prior=controls.history;
        const bool injected=controls.practiceHistory&&(b.observed.flags^b.expected.flags)==0x40u&&
            prior.flags==b.expected.flags&&prior.stickTimer==b.expected.stickTimer&&prior.disabledFrames==b.expected.disabledFrames;
        // Practice pause/injection restores the pre-read pad history, including these counters.
        if(controls.frozen||injected) {
            auto *pad=reinterpret_cast<unsigned char*>(b.targets.pad);
            store(pad,0xe2,prior.flags);store(pad,0xe4,prior.stickTimer);store(pad,0xe8,prior.disabledFrames);
            b.observed=mode(b.targets);
        }
    }
    // setup2 replaces the entire flags word before its first input consumer.
    if((b.observed.flags!=b.expected.flags&&!setupReset)||b.observed.stickTimer!=b.expected.stickTimer||
       b.observed.disabledFrames!=b.expected.disabledFrames) {
        b.guard.leave(b.guard.context);return b.error=MODE_MISMATCH;
    }
    writePad(b.targets,plan.input.pad);
    if(plan.mirrors!=PRESERVE_SHARED) {
        if(plan.mirrors==EXPERIMENTAL_PAD_MIRROR) {
            const Trace::SharedPad mirror={plan.input.pad.buttons,plan.input.pad.stick,plan.input.pad.substick};
            writeShared(b.targets,mirror);
        } else writeShared(b.targets,plan.input.shared);
        b.mirrorsWritten=true;
    }
    if(!boundary&&plan.work==RESTORE_INITIALIZED_WORK){writeWork(b.targets,plan.input.work);b.workWritten=true;}
    if(boundary){b.boundaryApplied=true;b.controls=actual;}
    ++b.applications;b.guard.leave(b.guard.context);return b.error=OK;
}
Error restore(Borrow &b) {
    if(!b.active)return b.error=NOT_BORROWED;
    if(!targets(b))return b.error=INVALID_TARGET;
    const Error acquired=enter(b);if(acquired!=OK)return acquired;
    if(b.applications)writePad(b.targets,b.backup.pad);
    if(b.mirrorsWritten)writeShared(b.targets,b.backup.shared);
    if(b.workWritten)writeWork(b.targets,b.backup.work);
    b.active=false;b.guard.leave(b.guard.context);return b.error=OK;
}
bool capturedMirrors(const Plan &p) { return p.mirrors==CAPTURED_SHARED&&p.input.sharedKnown==1; }
unsigned evidenceGaps(const Plan &p) {
    return (capturedMirrors(p)?0u:NON_CAPTURED_MIRRORS)|
        (!(p.input.flags&Trace::kFrameInput)&&p.work==PRESERVE_NATIVE_WORK?NATIVE_WORK_PRESERVED:0u);
}
}
