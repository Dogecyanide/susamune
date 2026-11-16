#include "susamune/metadata_values.hxx"
#include "susamune/collision_geometry.h"
#include "susamune/packed_text.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/Player/Watergun.hxx"
#include "SMS/Map/BGCheck.hxx"
#include "Dolphin/printf.h"
#include "Dolphin/math.h"

extern "C" f32 metadataSquareRoot(f32) asm("sqrtf__3stdFf");

namespace MetadataValues {
namespace {
const TMario *sMario;
u32 sFrame;
float sSpeed, sGain;
bool sValid;
const char *action(u32 state) {
    switch(state) {
    case TMario::STATE_IDLE:return "Idle";
    case TMario::STATE_RUNNING:return "Run";
    case TMario::STATE_STOP:return "Brake";
    case TMario::STATE_JUMP:return "Jump";
    case TMario::STATE_D_JUMP:return "Double jump";
    case TMario::STATE_TRIPLE_J:return "Triple jump";
    case TMario::STATE_BACK_FLIP:return "Backflip";
    case TMario::STATE_SIDE_FLIP:return "Sideflip";
    case TMario::STATE_JUMPSPIN:case TMario::STATE_JUMPSPINR:case TMario::STATE_JUMPSPINL:return "Spin jump";
    case TMario::STATE_SPIN:return "Spin";
    case TMario::STATE_FALL:return "Fall";
    case TMario::STATE_DIVE:return "Dive";
    case TMario::STATE_DIVEJUMP:return "Rollout";
    case TMario::STATE_DIVESLIDE:return "Dive slide";
    case TMario::STATE_GOOPSLIDE:return "Goop slide";
    case 0x00840452:case 0x00840453:return "Buttslide";
    case TMario::STATE_WALLJUMP:return "Wallkick";
    case TMario::STATE_WALLSLIDE:return "Wall slide";
    case TMario::STATE_HOVER:return "Hover";
    case TMario::STATE_SWIM:return "Swim";
    case TMario::STATE_SPRAY:return "Spray";
    case TMario::STATE_CLIMB:case TMario::STATE_CLIMBUP:return "Climb";
    case TMario::STATE_ROOFHANG:return "Ceiling hang";
    case TMario::STATE_HANG:return "Ledge hang";
    case TMario::STATE_SLAMSTART:case TMario::STATE_SLAM:return "Ground pound";
    case TMario::STATE_TALKING:return "Talk";
    case TMario::STATE_SHINE_C:return "Shine grab";
    case TMario::STATE_JMP_LAND:case TMario::STATE_HVY_LAND:case TMario::STATE_D_LAND:case TMario::STATE_T_LAND:return "Land";
    default:return nullptr;
    }
}
}
void reset() { sValid=false;sMario=nullptr;sGain=0; }
Extra read(const TMario *m, u32 frame) {
    Extra v={};
    const float speed=metadataSquareRoot(m->mSpeed.x*m->mSpeed.x + m->mSpeed.z*m->mSpeed.z);
    v.moving=speed>0.001f;
    v.direction=v.moving ? atan2f(m->mSpeed.x,m->mSpeed.z)*57.2957795f : 0;
    if(v.direction<0)v.direction+=360;
    if(!sValid || sMario!=m || frame!=sFrame) {
        // A discontinuous QF clock denotes a hold, warp or state restore.
        sGain=sValid && sMario==m && frame-sFrame==4 ? speed-sSpeed : 0;
        sMario=m;sFrame=frame;sSpeed=speed;sValid=true;
    }
    v.gain=sGain;v.action=m->mState;
    const TBGCheckData *floor=m->mFloorTriangle;
    v.ground=floor && !(floor->mFlags&0x10) && m->mFloorBelow>-1000000.0f;
    if(v.ground) {
        v.floor=floor->mType;v.height=m->mTranslation.y-m->mFloorBelow;
        if(v.height<0)v.height=0;
        v.slope=atan2f(metadataSquareRoot(floor->mNormal.x*floor->mNormal.x+floor->mNormal.z*floor->mNormal.z),floor->mNormal.y)*57.2957795f;
    }
    const TWaterGun *gun=m->mFludd;
    v.fludd=gun && m->mAttributes.mHasFludd;
    if(v.fludd) {
        const int capacity=gun->mNozzleDeform.mEmitParams.mAmountMax.get();
        v.water=capacity>0 ? 100.0f*gun->mCurrentWater/capacity : 0;
        const auto &hover=gun->mNozzleHover;
        int remaining=gun->mCurrentWater<=0 ? 0 : hover.mSprayState==TNozzleTrigger::DEAD ? 0 : hover.mSprayState==TNozzleTrigger::ACTIVE ? hover.mSprayQuarterFramesLeft : hover.mEmitParams.mTriggerTime.get();
        if(remaining<0)remaining=0;
        // Display the nozzle's own remaining budget in QFs, independent of VI rate.
        v.hover=remaining;
    }
    return v;
}
const char *label(unsigned field,bool full) {
    static const char shortNames[]="Dir\0Gain\0Height\0Action\0Slope\0Floor\0Water\0Hover";
    static const char longNames[]="Movement direction\0Speed gain / frame\0Height above floor\0Current action\0Slope angle\0Floor type\0FLUDD water\0Hover remaining";
    return PackedText::at(full?longNames:shortNames,field);
}
void format(char *out,u32 cap,unsigned field,const Extra &v) {
    if((field==0&&!v.moving)||((field==2||field==4||field==5)&&!v.ground)||(field>=6&&!v.fludd)) {snprintf(out,cap,"--");return;}
    switch(field) {
    case 0:snprintf(out,cap,"%.1f deg",v.direction);break;
    case 1:snprintf(out,cap,"%.2f",v.gain);break;
    case 2:snprintf(out,cap,"%.2f",v.height);break;
    case 3:if(const char *name=action(v.action))snprintf(out,cap,"%s",name);else snprintf(out,cap,"0x%08lX",v.action);break;
    case 4:snprintf(out,cap,"%.1f deg",v.slope);break;
    case 5:{
        static const char names[]="Solid\0Slippery\0Very slippery\0Slide\0No-slip\0Wet\0Water\0Sand\0Warp\0Wall\0Ceiling\0Death";
        snprintf(out,cap,"%s %04X",PackedText::at(names,SusamuneCollisionColorFor(v.floor,0)),v.floor);break;
    }
    case 6:snprintf(out,cap,"%.1f pct",v.water);break;
    case 7:snprintf(out,cap,"%.0f QF",v.hover);break;
    default:out[0]=0;break;
    }
}
}
