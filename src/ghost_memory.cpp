#include "susamune/ghost_memory.hxx"
#if TIMEWARP_QF_MEMORY
#include "susamune/addresses.hxx"
#include "susamune/susamune_cfg.h"
#include "susamune/memory_telemetry_scan.h"
#include "susamune/retail_input.hxx"
#include "SMS/System/MarDirector.hxx"
#include "JSystem/JKernel/JKRAramHeap.hxx"
#include "JSystem/JKernel/JKRHeap.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
namespace GhostMemory {
namespace {
struct Runtime { unsigned magic,flags,error,block,manager,progress,phase,passes,bad,expected,observed,nonce,batUpper,batLower; };
static_assert(sizeof(Runtime)<=MOONSHINE_GHOST_MEMORY_RUNTIME_BYTES,"ghost memory runtime overflow");
Runtime &state=*reinterpret_cast<Runtime *>(SUSAMUNE_GHOST_RECORD_PPC_BASE+MOONSHINE_GHOST_MEMORY_RUNTIME_OFFSET);
unsigned word(unsigned p) { return *reinterpret_cast<volatile const unsigned *>(p); }
#if !IS_EMULATOR
bool mapped(unsigned base,unsigned bytes) {
    unsigned upper[8],lower[8],hid4,msr;
    __asm__ volatile("mfmsr %0" : "=r"(msr));
    if((msr&0x4010u)!=0x10u)return false;
#define BAT(index,spr) __asm__ volatile("mfspr %0," #spr : "=r"(upper[index]));
    BAT(0,536) BAT(1,538) BAT(2,540) BAT(3,542) BAT(4,568) BAT(5,570) BAT(6,572) BAT(7,574)
#undef BAT
#define BAT(index,spr) __asm__ volatile("mfspr %0," #spr : "=r"(lower[index]));
    BAT(0,537) BAT(1,539) BAT(2,541) BAT(3,543) BAT(4,569) BAT(5,571) BAT(6,573) BAT(7,575)
#undef BAT
    __asm__ volatile("mfspr %0,1011" : "=r"(hid4));
    bool found=false;
    for(unsigned i=0;i<((hid4&0x02000000u)?8u:4u);++i) {
        if(!(upper[i]&2u))continue;
        const unsigned mask=(((upper[i]>>2)&0x7ffu)<<17)|0x1ffffu;
        const unsigned first=upper[i]&0xfffe0000u;
        if(base>first+mask || base+bytes-1u<first)continue;
        if(!MoonshineGhostMemoryBat(upper[i],lower[i],base,bytes))return false;
        state.batUpper=upper[i];state.batLower=lower[i];found=true;
    }
    return found;
}
#endif
bool validBlock() {
#if IS_EMULATOR
    return true;
#else
    const unsigned manager=word(SUSAMUNE_MEM1_ADDR(0x804097c8u,0x8040e230u,0x80405908u));
    const unsigned list=SUSAMUNE_MEM1_ADDR(0x80400b8cu,0x80404290u,0x803fba30u);
    if(manager!=state.manager || !MemoryReadable(state.block,36) ||
        word(state.block+8)!=list || word(state.block+20)!=MOONSHINE_GHOST_ARAM_START ||
        word(state.block+24)!=MOONSHINE_GHOST_ARAM_BYTES ||
        *reinterpret_cast<volatile const unsigned char *>(state.block+32)!=0x4du)return false;
    unsigned node=word(list);
    for(unsigned i=0;node && i<128;++i) {
        if(!MemoryReadable(node,16)||word(node+4)!=list)return false;
        if(node==state.block+4 && word(node)==state.block)return true;
        node=word(node+12);
    }
    return false;
#endif
}
bool reserveAram() {
#if IS_EMULATOR
    state.flags|=2;return true;
#else
    const TMarDirector *director=RetailInput::stageDirector();
    if(!director||!director->_260)return false;
    const unsigned manager=word(SUSAMUNE_MEM1_ADDR(0x804097c8u,0x8040e230u,0x80405908u));
    const unsigned list=SUSAMUNE_MEM1_ADDR(0x80400b8cu,0x80404290u,0x803fba30u);
    const unsigned console=word(SUSAMUNE_MEM1_ADDR(0x8040a2d8u,0x8040e1a8u,0x80405870u));
    const unsigned guide=word(SUSAMUNE_MEM1_ADDR(0x8040a2e0u,0x8040e1b0u,0x80405878u));
    MemoryPoolSample sample={};
    const bool irq=OSDisableInterrupts();
    const bool valid=MemoryReadable(manager,0x7c)&&MemoryReadable(console,36)&&MemoryReadable(guide,36)&&console!=guide&&
        word(console+8)==list&&word(guide+8)==list&&word(console+24)&&word(guide+24)&&
        MemoryArchiveSample(manager,list,word,sample)&&
        sample.capacity-sample.tailExtent>=MOONSHINE_GHOST_ARAM_BYTES+0x8000u;
    const unsigned heap=valid?word(manager+0x78):0;
    const unsigned metadata=MemoryReadable(heap,0x44)?word(heap+0x30):0;
    const bool canAllocate=MemoryReadable(metadata,0x84) &&
        word(metadata)==SUSAMUNE_MEM1_ADDR(0x803a8548u,0x803dff38u,0x803d78f0u);
    OSRestoreInterrupts(irq);
    // Retail allocTail assumes its MEM1 block-descriptor allocation succeeds.
    if(!valid || !canAllocate || reinterpret_cast<JKRExpHeap *>(metadata)->JKRExpHeap::getFreeSize()<0x80u){state.error=4;return false;}
    // Use the native allocator; a free-looking address is not ownership.
    auto *block=reinterpret_cast<JKRAramHeap *>(heap)->alloc(MOONSHINE_GHOST_ARAM_BYTES,JKRAramHeap::TAIL);
    state.manager=manager;state.block=reinterpret_cast<unsigned>(block);
    if(MemoryReadable(state.block,36) && word(state.block+20)==MOONSHINE_GHOST_ARAM_START &&
       word(state.block+24)==MOONSHINE_GHOST_ARAM_BYTES)
        *reinterpret_cast<volatile unsigned char *>(state.block+32)=0x4d;
    if(!validBlock()){state.error=5;state.flags|=16;return false;}
    state.flags|=2;state.error=0;return true;
#endif
}
unsigned upperBase() {
#if IS_EMULATOR
    return MOONSHINE_GHOST_UPPER_DOLPHIN_BASE;
#else
    return MOONSHINE_GHOST_UPPER_PPC_BASE;
#endif
}
unsigned tailBase() {
#if IS_EMULATOR
    return MOONSHINE_GHOST_TAIL_DOLPHIN_BASE;
#else
    return 0x90000000u+MOONSHINE_GHOST_ARAM_START;
#endif
}
}
void init() {
    const Runtime previous=state;
    state={};state.magic=0x47514d31u;
#if IS_EMULATOR
    state.flags=1;state.nonce=1;
#else
    const auto *cfg=SUSAMUNE_CFG_PPC_PTR;DCInvalidateRange((void*)cfg,32);
    if(cfg->magic!=SUSAMUNE_CFG_MAGIC||cfg->version!=SUSAMUNE_CFG_VERSION||
       !(cfg->flags&MOONSHINE_GHOST_MEMORY_FLAG)){state.error=1;return;}
    MoonshineGhostMemoryProof proof;
    DCInvalidateRange((void*)MOONSHINE_GHOST_PROOF_PPC_BASE,sizeof(proof));
    memcpy(&proof,(const void*)MOONSHINE_GHOST_PROOF_PPC_BASE,sizeof(proof));
    if(!MoonshineGhostMemoryProofValid(&proof,SUSAMUNE_MEM1_ADDR(0x474d534au,0x474d5345u,0x474d5350u))){state.error=2;return;}
    if(!mapped(MOONSHINE_GHOST_UPPER_PPC_BASE,MOONSHINE_GHOST_UPPER_SIZE)||
       !mapped(0x90000000u+MOONSHINE_GHOST_ARAM_START,MOONSHINE_GHOST_ARAM_BYTES)){state.error=3;return;}
    state.flags=1;state.nonce=proof.word[MGM_NONCE];
    // A title/reset path can retain the native ARAM manager. Re-adopt only
    // this boot's tagged block that is still linked into that same manager.
    if(previous.magic==state.magic && previous.nonce==state.nonce && (previous.flags&2u)) {
        state.manager=previous.manager;state.block=previous.block;
        if(validBlock())state.flags|=2;
        else state.manager=state.block=0;
    }
#endif
}
bool admitted() { return state.magic==0x47514d31u && (state.flags&1u); }
bool ready() { return admitted() && (state.flags&3)==3 && !(state.flags&16); }
void *primary(unsigned bank) { return ready()&&bank<2?(void*)(upperBase()+MOONSHINE_GHOST_CORE_SIZE+bank*MOONSHINE_GHOST_PRIMARY_PART_SIZE):nullptr; }
void *tail(unsigned bank) { return ready()&&bank<2?(void*)(tailBase()+bank*MOONSHINE_GHOST_TAIL_PART_SIZE):nullptr; }
void update() {
    if(!(state.flags&1) || (state.flags&16))return;
    if(!(state.flags&2) && !reserveAram())return;
    if(!validBlock()){state.flags|=16;state.error=6;return;}
#if TIMEWARP_QF_MEMORY_PILOT
    const unsigned total=MOONSHINE_GHOST_UPPER_SIZE+MOONSHINE_GHOST_ARAM_BYTES;
    if(!state.phase)state.phase=1;
    const unsigned offset=state.progress;
    const unsigned base=offset<MOONSHINE_GHOST_UPPER_SIZE?upperBase()+offset:tailBase()+offset-MOONSHINE_GHOST_UPPER_SIZE;
    const unsigned length=total-offset<0x4000u?total-offset:0x4000u;
    auto *words=reinterpret_cast<volatile unsigned *>(base);
    if(state.phase==2)DCInvalidateRange((void*)base,length);
    for(unsigned i=0;i<length/4;++i){
        const unsigned pattern=0x51464d31u^((offset/4+i)*0x9e3779b1u)^state.nonce;
        if(state.phase==1)words[i]=pattern;
        else if(words[i]!=pattern){state.bad=base+i*4;state.expected=pattern;state.observed=words[i];state.error=7;state.flags|=16;return;}
    }
    if(state.phase==1)DCStoreRange((void*)base,length);
    state.progress+=length;
    if(state.progress==total){state.progress=0;if(state.phase==2){++state.passes;state.flags|=8;}state.phase=2;}
#endif
}
void status(unsigned *out) {
    out[0]=state.flags|(TIMEWARP_QF_MEMORY_PILOT?0u:4u);out[1]=state.error;out[2]=MOONSHINE_GHOST_UPPER_SIZE;out[3]=MOONSHINE_GHOST_ARAM_BYTES;
    out[4]=state.progress;out[5]=MOONSHINE_GHOST_UPPER_SIZE+MOONSHINE_GHOST_ARAM_BYTES;out[6]=state.passes;
    out[7]=state.bad;out[8]=state.expected;out[9]=state.observed;out[10]=state.phase;
}
}
#endif
