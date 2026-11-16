#include "susamune/ghost_world_runtime.hxx"
#include "susamune/ghost_trace.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_trace_hooks.hxx"
#include "susamune/ghost_render_feedback.hxx"
#include "susamune/features.hxx"
#include "susamune/addresses.hxx"
#include "Dolphin/mem.h"
static bool traceReadable(unsigned p,unsigned n){return !(p&3u)&&p>=0x80000000u&&p<=0x81800000u-n;}
extern "C" void ghostTraceHookEvent(unsigned type,const unsigned *args,unsigned caller) {
    if(!GhostTrace::recording()&&!GhostWorldRuntime::hooksActive())return;
    const unsigned seed=*reinterpret_cast<volatile const unsigned*>(SUSAMUNE_ADDR_LIBC_RAND_SEED);
    if(type==6){GhostWorldRuntime::random(caller,args[0],seed);GhostTrace::random(caller,args[0],seed);return;}
    if(!GhostTrace::recording())return;
    struct Sample {unsigned type,caller,args[8],valid,position[9],actorFlags,seed;} out={};
    out.type=type;out.caller=caller;out.seed=seed;
    const unsigned count=type==1?5:type==2?7:type==3?5:2;
    memcpy(out.args,args,count*4);
    if(type==1&&traceReadable(args[2],16)){
        const unsigned *actor=reinterpret_cast<const unsigned*>(args[2]);out.actorFlags=actor[3];
        for(unsigned i=0;i<3;++i)if(traceReadable(actor[i],12)){memcpy(out.position+i*3,reinterpret_cast<const void*>(actor[i]),12);out.valid|=1u<<i;}
    }else if((type==2||type==3)&&traceReadable(args[1],12)){memcpy(out.position,reinterpret_cast<const void*>(args[1]),12);out.valid=1;}
    GhostTrace::event(type==1?MS_TRACE_SOUND:MS_TRACE_PARTICLE,&out,sizeof(out));
}
#if defined(SUSAMUNE_VERSION_JP)
#define SITE_Sound 0x801815fcu
#define TAIL_Sound "0x80181600"
#define SITE_Particle 0x8006fbb0u
#define TAIL_Particle "0x8006fbb4"
#define SITE_ParticleDirect 0x8006fc18u
#define TAIL_ParticleDirect "0x8006fc1c"
#define SITE_Delete 0x8006fcb0u
#define TAIL_Delete "0x8006fcb4"
#define SITE_ForceDelete 0x8006fd14u
#define TAIL_ForceDelete "0x8006fd18"
#define SITE_Rng 0x80085ae4u
#define TAIL_Rng "0x80085ae8"
#elif defined(SUSAMUNE_VERSION_US)
#define SITE_Sound 0x800180d8u
#define TAIL_Sound "0x800180dc"
#define SITE_Particle 0x80325298u
#define TAIL_Particle "0x8032529c"
#define SITE_ParticleDirect 0x80325300u
#define TAIL_ParticleDirect "0x80325304"
#define SITE_Delete 0x80325398u
#define TAIL_Delete "0x8032539c"
#define SITE_ForceDelete 0x803253fcu
#define TAIL_ForceDelete "0x80325400"
#define SITE_Rng 0x8033b1c4u
#define TAIL_Rng "0x8033b1c8"
#elif defined(SUSAMUNE_VERSION_PAL)
#define SITE_Sound 0x80018134u
#define TAIL_Sound "0x80018138"
#define SITE_Particle 0x8031d428u
#define TAIL_Particle "0x8031d42c"
#define SITE_ParticleDirect 0x8031d490u
#define TAIL_ParticleDirect "0x8031d494"
#define SITE_Delete 0x8031d528u
#define TAIL_Delete "0x8031d52c"
#define SITE_ForceDelete 0x8031d58cu
#define TAIL_ForceDelete "0x8031d590"
#define SITE_Rng 0x80333344u
#define TAIL_Rng "0x80333348"
#endif
extern "C" void gTraceSound();
asm(
    ".pushsection .text.gTraceSound,\"ax\",@progbits\n"
    ".global gTraceSound\n"
    ".type gTraceSound,@function\n"
    "gTraceSound:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,1\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "mflr 0\n"
    ".set gTraceSoundTail," TAIL_Sound "\n"
    "lis 12,gTraceSoundTail@h\n"
    "ori 12,12,gTraceSoundTail@l\n"
    "mtctr 12\n"
    "bctr\n"
    ".size gTraceSound,.-gTraceSound\n"
    ".popsection\n"
);
extern "C" void gTraceParticle();
asm(
    ".pushsection .text.gTraceParticle,\"ax\",@progbits\n"
    ".global gTraceParticle\n"
    ".type gTraceParticle,@function\n"
    "gTraceParticle:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,2\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "mflr 0\n"
    ".set gTraceParticleTail," TAIL_Particle "\n"
    "lis 12,gTraceParticleTail@h\n"
    "ori 12,12,gTraceParticleTail@l\n"
    "mtctr 12\n"
    "bctr\n"
    ".size gTraceParticle,.-gTraceParticle\n"
    ".popsection\n"
);
extern "C" void gTraceParticleDirect();
asm(
    ".pushsection .text.gTraceParticleDirect,\"ax\",@progbits\n"
    ".global gTraceParticleDirect\n"
    ".type gTraceParticleDirect,@function\n"
    "gTraceParticleDirect:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,3\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "mflr 0\n"
    ".set gTraceParticleDirectTail," TAIL_ParticleDirect "\n"
    "lis 12,gTraceParticleDirectTail@h\n"
    "ori 12,12,gTraceParticleDirectTail@l\n"
    "mtctr 12\n"
    "bctr\n"
    ".size gTraceParticleDirect,.-gTraceParticleDirect\n"
    ".popsection\n"
);
extern "C" void gTraceDelete();
asm(
    ".pushsection .text.gTraceDelete,\"ax\",@progbits\n"
    ".global gTraceDelete\n"
    ".type gTraceDelete,@function\n"
    "gTraceDelete:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,4\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "mflr 0\n"
    ".set gTraceDeleteTail," TAIL_Delete "\n"
    "lis 12,gTraceDeleteTail@h\n"
    "ori 12,12,gTraceDeleteTail@l\n"
    "mtctr 12\n"
    "bctr\n"
    ".size gTraceDelete,.-gTraceDelete\n"
    ".popsection\n"
);
extern "C" void gTraceForceDelete();
asm(
    ".pushsection .text.gTraceForceDelete,\"ax\",@progbits\n"
    ".global gTraceForceDelete\n"
    ".type gTraceForceDelete,@function\n"
    "gTraceForceDelete:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,5\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "mflr 0\n"
    ".set gTraceForceDeleteTail," TAIL_ForceDelete "\n"
    "lis 12,gTraceForceDeleteTail@h\n"
    "ori 12,12,gTraceForceDeleteTail@l\n"
    "mtctr 12\n"
    "bctr\n"
    ".size gTraceForceDelete,.-gTraceForceDelete\n"
    ".popsection\n"
);
extern "C" void gTraceRng();
asm(
    ".pushsection .text.gTraceRng,\"ax\",@progbits\n"
    ".global gTraceRng\n"
    ".type gTraceRng,@function\n"
    "gTraceRng:\n"
    "stwu 1,-160(1)\n"
    "mflr 0\n"
    "stw 0,164(1)\n"
    "mfcr 0\n"
    "stw 0,112(1)\n"
    "stw 3,64(1)\n"
    "stw 4,68(1)\n"
    "stw 5,72(1)\n"
    "stw 6,76(1)\n"
    "stw 7,80(1)\n"
    "stw 8,84(1)\n"
    "stw 9,88(1)\n"
    "stw 10,92(1)\n"
    "stw 11,96(1)\n"
    "stw 12,100(1)\n"
    "li 3,6\n"
    "addi 4,1,64\n"
    "lwz 5,164(1)\n"
    "bl ghostTraceHookEvent\n"
    "lwz 3,64(1)\n"
    "lwz 4,68(1)\n"
    "lwz 5,72(1)\n"
    "lwz 6,76(1)\n"
    "lwz 7,80(1)\n"
    "lwz 8,84(1)\n"
    "lwz 9,88(1)\n"
    "lwz 10,92(1)\n"
    "lwz 11,96(1)\n"
    "lwz 12,100(1)\n"
    "lwz 0,112(1)\n"
    "mtcrf 255,0\n"
    "lwz 0,164(1)\n"
    "mtlr 0\n"
    "addi 1,1,160\n"
    "blr\n"
    ".size gTraceRng,.-gTraceRng\n"
    ".popsection\n"
);
namespace GhostTraceHooks {
namespace {
struct Hook {unsigned site,original;void(*shim)();};
const Hook hooks[]={
    {SITE_Sound,0x7c0802a6u,gTraceSound},
    {SITE_Particle,0x7c0802a6u,gTraceParticle},
    {SITE_ParticleDirect,0x7c0802a6u,gTraceParticleDirect},
    {SITE_Delete,0x7c0802a6u,gTraceDelete},
    {SITE_ForceDelete,0x7c0802a6u,gTraceForceDelete},
    {SITE_Rng,0x4e800020u,gTraceRng},
    {MS_FEEDBACK_CAMERA_SITE,0x5400063fu,gFeedbackCamera},
    {MS_FEEDBACK_SILHOUETTE_SITE,0x5400063fu,gFeedbackSilhouette},
    {MS_FEEDBACK_WATER_SITE,0x8001000cu,gFeedbackWater},
};
bool active,feedbackActive,waterActive;
bool feedback(const Hook &h){return h.site==MS_FEEDBACK_CAMERA_SITE||h.site==MS_FEEDBACK_SILHOUETTE_SITE;}
unsigned branch(const Hook &h){return 0x48000000u|((reinterpret_cast<unsigned>(h.shim)-h.site)&0x03fffffcu);}
bool valid(){for(const auto &h:hooks){const unsigned current=*reinterpret_cast<volatile const unsigned*>(h.site);if(current!=((h.site==MS_FEEDBACK_WATER_SITE?waterActive:feedback(h)?feedbackActive:active)?branch(h):h.original))return false;}return true;}
}
unsigned capabilities(){return valid()?MS_TRACE_HAS_SOUND_REQUESTS|MS_TRACE_HAS_PARTICLE_EVENTS|MS_TRACE_HAS_RNG_CALLS:0;}
bool setActive(bool enabled){
    const bool render=enabled&&(GhostTrace::recording()||GhostWorldRuntime::wantsRenderFeedback());
    const bool water=enabled&&(GhostTrace::recording()||GhostWorldRuntime::wantsWaterFeedback());
    if(enabled==active&&render==feedbackActive&&water==waterActive)return true;
    // Refuse another patch owner's entry; never replace a foreign instruction.
    if(!valid())return false;
    for(const auto &h:hooks)writeGameCode(h.site,(h.site==MS_FEEDBACK_WATER_SITE?water:feedback(h)?render:enabled)?branch(h):h.original);
    active=enabled;feedbackActive=render;waterActive=water;return true;
}
}
#endif
