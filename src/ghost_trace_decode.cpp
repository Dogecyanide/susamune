#include "susamune/ghost_provenance.h"
#include "susamune/ghost_trace_observation.h"
#include "susamune/ghost_trace_decode.hxx"
#include "susamune/ghost_simulation_settings.h"

namespace GhostTraceDecode {
namespace {
unsigned word(const unsigned char *p) {
    return unsigned(p[0]) << 24 | unsigned(p[1]) << 16 | unsigned(p[2]) << 8 | p[3];
}
unsigned half(const unsigned char *p) { return unsigned(p[0]) << 8 | p[1]; }
int signedWord(unsigned value) { return value <= 0x7fffffffu ? int(value) : -1-int(~value); }
short signedHalf(const unsigned char *p) {
    const unsigned value=half(p);return static_cast<short>(value<=32767u?int(value):int(value)-65536);
}
signed char signedByte(unsigned char value) {
    return static_cast<signed char>(value<=127u?int(value):int(value)-256);
}
bool floating(const unsigned char *p,float &out) {
    const unsigned bits=word(p);
    if((bits&0x7f800000u)==0x7f800000u)return false;
    __builtin_memcpy(&out,&bits,4);return true;
}
void observedFloat(const unsigned char *p,float &out) {
    const unsigned bits=word(p);__builtin_memcpy(&out,&bits,4);
}
bool zero(const unsigned char *p,unsigned n) {
    for(unsigned i=0;i<n;++i)if(p[i])return false;
    return true;
}
bool gameId(unsigned game) {
    return game==0x474d534au || game==0x474d5345u || game==0x474d5350u;
}
bool fail(Decoder &d,Error e) { d.error=e;return false; }
bool needs(Decoder &d,unsigned capability) {
    return (d.capabilities&capability)==capability || fail(d,CAPABILITY);
}
bool address(unsigned p) { return !(p&3u)&&p>=0x80000000u&&p<0x81800000u; }
Scene scene(const unsigned char *p) {
    Scene out={p[0],p[1],static_cast<unsigned short>(half(p+2))};return out;
}
bool stick(const unsigned char *p,Stick &out) {
    out.angle=signedHalf(p+12);out.rawX=signedByte(p[14]);out.rawY=signedByte(p[15]);
    return floating(p,out.x)&&floating(p+4,out.y)&&floating(p+8,out.magnitude);
}
bool buttons(const unsigned char *p,Buttons &out) {
    out.held=word(p);out.pressed=word(p+4);out.released=word(p+8);
    out.analogA=p[12];out.analogB=p[13];out.triggerL=p[14];out.triggerR=p[15];
    out.repeat=word(p+24);out.heldFrames=word(p+28);
    for(unsigned i=0;i<4;++i)out.repeatState[i]=word(p+32+i*4);
    return floating(p+16,out.analogL)&&floating(p+20,out.analogR);
}
bool shared(const unsigned char *p,SharedPad &out) {
    return buttons(p,out.buttons)&&stick(p+48,out.stick)&&stick(p+64,out.substick);
}
bool mirrorRecord(Decoder &d,const unsigned char *p,unsigned n,unsigned kind) {
    if(!needs(d,1u<<19))return false;
    if(n<8||word(p)!=1||word(p+4)!=80)return fail(d,SCHEMA);
    if(kind==24) {
        if(n!=88)return fail(d,SCHEMA);
        __builtin_memcpy(d.previousMirrors,p+8,80);
    } else {
        if(d.version<2||n<12)return fail(d,SCHEMA);
        if(!d.mirrorSeen)return fail(d,BASELINE);
        const unsigned mask=word(p+8);unsigned at=12;
        if(mask&~0xfffffu)return fail(d,VALUE);
        for(unsigned i=0;i<20;++i)if(mask&(1u<<i)) {
            if(n-at<4)return fail(d,BOUNDARY);
            __builtin_memcpy(d.previousMirrors+i*4,p+at,4);at+=4;
        }
        if(at!=n)return fail(d,BOUNDARY);
    }
    SharedPad value;
    if(!shared(d.previousMirrors,value))return fail(d,VALUE);
    d.mirrorSeen=1;return true;
}
bool input(Decoder &d,Input &out) {
    const unsigned char *p=d.previousInput;
    out.cue=word(p);out.flags=word(p+4);out.valid=word(p+20);
    if(out.flags&kFrameInput) {
        if(!needs(d,1u<<18))return false;
        if(out.cue || (out.flags&~(kFrameInput|3u)) || (out.valid&~1u))return fail(d,VALUE);
    } else if(!(out.cue&1u)||out.flags||(out.valid&~3u))return fail(d,VALUE);
    if(p[19]||(! (out.valid&1u) && !zero(p+24,240))||
       (!(out.valid&2u)&&!zero(p+264,36)))return fail(d,VALUE);
    out.raw.buttons=static_cast<unsigned short>(half(p+8));
    out.raw.stickX=signedByte(p[10]);out.raw.stickY=signedByte(p[11]);
    out.raw.substickX=signedByte(p[12]);out.raw.substickY=signedByte(p[13]);
    out.raw.triggerL=p[14];out.raw.triggerR=p[15];out.raw.analogA=p[16];out.raw.analogB=p[17];
    out.raw.error=signedByte(p[18]);
    if(out.raw.buttons&~0x1f7fu)return fail(d,VALUE);
    if(out.valid&1u) {
        const unsigned char *pad=p+24;
        if(!buttons(pad+0x18,out.pad.buttons)||!stick(pad+0x48,out.pad.stick)||
           !stick(pad+0x58,out.pad.substick))return fail(d,VALUE);
        for(unsigned i=0;i<10;++i)
            if(!floating(pad+0xa8+i*4,out.pad.meaningAxes[i]))return fail(d,VALUE);
        out.pad.meaning=word(pad+0xd0);out.pad.pressedMeaning=word(pad+0xd4);
        out.pad.releasedMeaning=word(pad+0xd8);
        out.pad.analogHeld=static_cast<unsigned short>(half(pad+0xdc));
        out.pad.analogPressed=static_cast<unsigned short>(half(pad+0xde));
        out.pad.analogReleased=static_cast<unsigned short>(half(pad+0xe0));
        out.pad.flags=static_cast<unsigned short>(half(pad+0xe2));
        out.pad.stickTimer=signedHalf(pad+0xe4);
        out.pad.disabledFrames=signedWord(word(pad+0xe8));
    }
    if(out.valid&2u) {
        const unsigned char *w=p+264;
        out.work.stickX=signedHalf(w);out.work.stickY=signedHalf(w+2);
        out.work.held=word(w+4);out.work.pressed=word(w+8);
        out.work.analogR=w[12];out.work.analogL=w[13];
        observedFloat(w+16,out.work.x);observedFloat(w+20,out.work.y);
        observedFloat(w+24,out.work.magnitude);observedFloat(w+28,out.work.right);observedFloat(w+32,out.work.left);
    }
    out.sharedKnown=d.mirrorSeen;
    if(d.mirrorSeen&&!shared(d.previousMirrors,out.shared))return fail(d,VALUE);
    return true;
}
bool inputRecord(Decoder &d,const unsigned char *p,unsigned n,unsigned kind,Input &out) {
    if(!needs(d,1u<<10))return false;
    if(kind==14) {
        if(n!=kInputBytes)return fail(d,SCHEMA);
        __builtin_memcpy(d.previousInput,p,kInputBytes);
    } else {
        if(d.version<2||n<16||word(p)!=kInputBytes)return fail(d,SCHEMA);
        if(!d.inputSeen)return fail(d,BASELINE);
        const unsigned masks[]={word(p+4),word(p+8),word(p+12)};
        if(masks[2]>>11)return fail(d,VALUE);
        unsigned at=16;
        for(unsigned i=0;i<75;++i)if(masks[i/32]&(1u<<(i%32))) {
            if(n-at<4)return fail(d,BOUNDARY);
            __builtin_memcpy(d.previousInput+i*4,p+at,4);at+=4;
        }
        if(at!=n)return fail(d,BOUNDARY);
    }
    if(!input(d,out))return false;
    d.inputSeen=1;return true;
}
bool visual(Decoder &d,const unsigned char *p,unsigned n,Visual &out) {
    if(!needs(d,1u<<17))return false;
    if(n!=64||word(p)!=1)return fail(d,SCHEMA);
    out.flags=word(p+4);out.qf=signedWord(word(p+8));out.scene=word(p+12);
    if((out.flags&~3u)||out.scene>0xffffu||p[41]>1||p[42]||p[43]||
       (!(out.flags&1u)&&!zero(p+16,36))||(!(out.flags&2u)&&out.qf))return fail(d,VALUE);
    if(!floating(p+16,out.x)||!floating(p+20,out.y)||!floating(p+24,out.z))return fail(d,VALUE);
    out.yaw=signedHalf(p+28);out.animationId=static_cast<unsigned short>(half(p+30));
    out.animationPhase=static_cast<unsigned short>(half(p+32));out.heldNameKey=static_cast<unsigned short>(half(p+34));
    out.heldObjectId=word(p+36);out.yoshi=p[40];out.visible=p[41];
    if(out.animationId>=336||out.animationPhase>4095||out.yoshi>5||
       !SusamuneGhostVisualValid(p+44,1)||((p[44]&SUSAMUNE_GHOST_VISUAL_YOSHI)&&!out.yoshi))return fail(d,VALUE);
    __builtin_memcpy(&out.fludd,p+44,8);
    out.directorTick=word(p+52);out.attempt=word(p+56);out.generation=word(p+60);
    return true;
}
bool stage(Decoder &d,const unsigned char *p,unsigned n,StageStart &out) {
    if(!needs(d,1u<<16))return false;
    if(n<64)return fail(d,SCHEMA);
    const bool phase=(d.capabilities&(1u<<23))!=0;
    const unsigned schema=word(p);
    if((phase? !((schema==2&&n==964)||(schema==3&&n==968)) : (schema!=1||n!=960))||word(p+32)!=896)return fail(d,SCHEMA);
    out.observations=schema==3?word(p+964):0;
    if(out.observations&~15u)return fail(d,VALUE);
    out.npcPollutionPhase=phase?word(p+960):0xffffffffu;
    if(phase&&out.npcPollutionPhase>=30)return fail(d,VALUE);
    out.flags=word(p+4);out.scene=word(p+8);out.previous=scene(p+12);out.current=scene(p+16);out.next=scene(p+20);
    out.rngSeed=word(p+24);out.generation=word(p+28);out.headBytes=word(p+36);out.tailBytes=word(p+40);
    out.heapBytes=word(p+44);out.game=word(p+48);out.discIdentity=word(p+52);
    out.tvFormat=word(p+56);out.cutscene=word(p+60);out.flagBytes=p+64;
    if((out.flags&~7u)||out.scene>0xffffu||!out.generation||out.game!=d.game||
       (out.heapBytes>0x1800000u)||out.headBytes>out.heapBytes||out.tailBytes>out.heapBytes-out.headBytes||
       (!(out.flags&2u)&&(out.headBytes||out.tailBytes||out.heapBytes))||
       (!(out.flags&1u)&&!zero(out.flagBytes,896)))return fail(d,VALUE);
    return true;
}
bool random(Decoder &d,const unsigned char *p,unsigned n,unsigned kind,Rng &out) {
    if(!needs(d,1u<<11))return false;
    if(kind==15) {
        if(n!=12)return fail(d,SCHEMA);
        out.caller=word(p);out.result=word(p+4);out.firstSeed=out.lastSeed=word(p+8);out.count=1;
        return address(out.caller)||fail(d,VALUE);
    }
    if(d.version<2||n<16)return fail(d,SCHEMA);
    out.firstSeed=word(p);out.lastSeed=word(p+4);out.count=word(p+8);out.callerCount=word(p+12);
    if(!out.count||out.count>512||!out.callerCount||out.callerCount>64||
       n!=16+out.callerCount*4+out.count)return fail(d,VALUE);
    out.callers=p+16;out.indices=p+16+out.callerCount*4;
    for(unsigned i=0;i<out.callerCount;++i)if(!address(word(out.callers+i*4)))return fail(d,VALUE);
    unsigned seed=out.firstSeed;
    for(unsigned i=0;i<out.count;++i) {
        if(out.indices[i]>=out.callerCount)return fail(d,VALUE);
        if(i)seed=seed*1103515245u+12345u;
    }
    return seed==out.lastSeed||fail(d,VALUE);
}
}
bool decodeVisual(Decoder &d,const void *p,unsigned bytes,Visual &out) {
    return p && visual(d,static_cast<const unsigned char*>(p),bytes,out);
}

bool begin(Decoder &d,unsigned version,unsigned game,unsigned capabilities,unsigned requiredCapabilities) {
    d={};d.version=version;d.game=game;d.capabilities=capabilities;
    if(version<1||version>3||!gameId(game))return fail(d,FORMAT);
    if((capabilities&0xff000000u)||(requiredCapabilities&~kKnownCapabilities)||
       (capabilities&requiredCapabilities)!=requiredCapabilities)return fail(d,CAPABILITY);
    return true;
}
bool pushChunk(Decoder &d,const void *p,unsigned bytes) {
    if(d.error)return false;
    if(!p||!bytes||bytes>0x80000u||d.offset!=d.bytes)return fail(d,ARGUMENT);
    d.chunk=static_cast<const unsigned char*>(p);d.bytes=bytes;d.offset=0;return true;
}
Result next(Decoder &d,Event &out) {
    if(d.error)return FAILED;
    while(d.offset<d.bytes) {
        if(d.bytes-d.offset<12){fail(d,BOUNDARY);return FAILED;}
        const unsigned char *p=d.chunk+d.offset;
        const unsigned kind=half(p),n=half(p+2),frame=word(p+4),tick=word(p+8),offset=d.offset;
        if(!kind||n>d.bytes-d.offset-12){fail(d,BOUNDARY);return FAILED;}
        if(frame<d.frame||tick<d.tick){fail(d,ORDER);return FAILED;}
        d.frame=frame;d.tick=tick;d.offset+=12+n;p+=12;
        const unsigned typed=(1u<<1)|(1u<<2)|(1u<<14)|(1u<<15)|(1u<<17)|(1u<<18)|(1u<<20)|(1u<<22)|(1u<<23)|(1u<<24)|(1u<<25)|(1u<<26)|(1u<<27)|(1u<<28);
        if(kind!=MS_TRACE_OBSERVATION&&(kind>28||!(typed&(1u<<kind))))continue;
        out={};out.kind=kind;out.frame=frame;out.tick=tick;out.offset=offset;
        bool valid=true;
        switch(kind) {
        case 1:
            out.type=SESSION;
            if(!needs(d,1u)){valid=false;break;}
            if(n!=64||!SusamuneGhostSimulationSettingsValid(p))valid=fail(d,SCHEMA);
            else out.settings=p;
            break;
        case 2: {
            out.type=FRAME;
            if(!needs(d,2u)){valid=false;break;}
            if(n!=32){valid=fail(d,SCHEMA);break;}
            Frame &f=out.frameData;f={word(p),word(p+4),word(p+8),word(p+12),word(p+16),word(p+20),word(p+24),word(p+28)};
            if(f.scene>0xffffu||f.movementTick!=tick||(f.flags&~15u)||
               (f.directorState>255u&&f.directorState!=0xffffffffu)){valid=fail(d,VALUE);break;}
            if(!d.frameSeen||f.scene!=d.scene)d.inputSeen=d.mirrorSeen=0;
            d.scene=f.scene;d.frameSeen=1;break;
        }
        case 14:case 20:out.type=INPUT;valid=inputRecord(d,p,n,kind,out.input);break;
        case 15:case 18:out.type=RNG;valid=random(d,p,n,kind,out.rng);break;
        case 17:
            out.type=IDENTITY;
            if(n!=16){valid=fail(d,SCHEMA);break;}
            out.identity={word(p),word(p+4),word(p+8),word(p+12)};
            if(out.identity.game!=d.game||out.identity.region!=(d.game==0x474d534au?1u:d.game==0x474d5345u?2u:3u))valid=fail(d,VALUE);
            break;
        case 22:out.type=STAGE_START;valid=stage(d,p,n,out.stage);break;
        case 23:out.type=VISUAL;valid=visual(d,p,n,out.visual);break;
        case 24:case 25:if(!mirrorRecord(d,p,n,kind))return FAILED;continue;
        case 26:
            out.type=WORLD_WITNESS;
            if(!needs(d,1u<<20))valid=false;
            else if(!GhostWorldWitness::decode(p,n,out.world))valid=fail(d,SCHEMA);
            break;
        case 27:
            out.type=CONTINUATION;
            if(!needs(d,MS_TRACE_HAS_CONTINUATION))valid=false;
            else if(!MsTraceContinuationDecode(&out.continuation,p,n))valid=fail(d,SCHEMA);
            else {d.inputSeen=d.mirrorSeen=d.frameSeen=0;d.runFlags|=out.continuation.runFlags;}
            break;
        case MS_TRACE_OBSERVATION:
            out.type=OBSERVATION;
            if(!MsTraceObservationValid(p,n))valid=fail(d,SCHEMA);
            else out.observation={word(p+4),n,p};
            break;
        case MS_TRACE_PROVENANCE:
            out.type=PROVENANCE;
            if(!needs(d,MS_TRACE_HAS_EXTENDED_STATE))valid=false;
            else if(n!=8||word(p)!=MS_TRACE_PROVENANCE_SCHEMA)valid=fail(d,SCHEMA);
            else {out.runFlags=word(p+4);if(!MsTraceProvenanceValid(out.runFlags)||(d.runFlags&~out.runFlags))valid=fail(d,VALUE);else d.runFlags=out.runFlags;}
            break;
        // Native byte observations and unknown optional kinds are never restore instructions.
        default:continue;
        }
        return valid?EVENT:FAILED;
    }
    return CHUNK_DONE;
}
bool sameRegion(const Decoder &d,unsigned game) { return gameId(game)&&game==d.game; }
bool hasPreStageEvidence(const Decoder &d,const StageStart &s,unsigned targetGame) {
    const unsigned required=(1u<<16)|(1u<<18)|(1u<<10)|(1u<<11)|3u;
    return !d.error&&sameRegion(d,targetGame)&&(d.capabilities&required)==required&&
        s.game==d.game&&(s.flags&7u)==7u;
}
bool rngCall(const Rng &r,unsigned index,unsigned &caller,unsigned &result,unsigned &seed) {
    if(index>=r.count)return false;
    if(!r.callerCount) {
        if(index||r.count!=1)return false;
        caller=r.caller;result=r.result;seed=r.firstSeed;return true;
    }
    if(!r.callers||!r.indices||r.callerCount>64||r.count>512||r.indices[index]>=r.callerCount)return false;
    caller=word(r.callers+r.indices[index]*4);seed=r.firstSeed;
    // Jump the affine LCG in at most nine steps, including random-access callers.
    unsigned multiplier=1103515245u,increment=12345u;
    while(index) {
        if(index&1u)seed=seed*multiplier+increment;
        increment*=multiplier+1u;multiplier*=multiplier;index>>=1;
    }
    result=(seed>>16)&32767u;return true;
}
}
