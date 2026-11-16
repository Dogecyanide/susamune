#ifndef SUSAMUNE_GHOST_TRACE_OBSERVATION_H
#define SUSAMUNE_GHOST_TRACE_OBSERVATION_H
#define MS_TRACE_OBSERVATION_SCHEMA 1u
enum MsTraceObservationKind { MS_OBSERVE_CONTEXT=1, MS_OBSERVE_CONTROL, MS_OBSERVE_CRANE, MS_OBSERVE_SPIN, MS_OBSERVE_ANIMATION };
enum MsTraceHoldReason { MS_HOLD_DIRECT=1, MS_HOLD_GAME_MODE=2, MS_HOLD_MENU=4, MS_HOLD_DISK=8, MS_HOLD_STAGELOADER=16, MS_HOLD_WHEEL=32, MS_HOLD_PRACTICE=64, MS_HOLD_WATCH=128, MS_HOLD_ONLINE=256, MS_HOLD_INPUT=512, MS_HOLD_REPLAY=1024 };
static inline unsigned MsObservationWord(const unsigned char*p) { return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3]; }
/* Observations are evidence, never native restore destinations or callable pointers. */
static inline int MsTraceObservationValid(const unsigned char*p,unsigned bytes) {
    unsigned type;
    if(!p||bytes<8||MsObservationWord(p)!=MS_TRACE_OBSERVATION_SCHEMA)return 0;
    type=MsObservationWord(p+4);
    switch(type) {
    case MS_OBSERVE_CONTEXT:
        return bytes==44&&MsObservationWord(p+8)<=4&&MsObservationWord(p+12)<=65536u&&
            !(MsObservationWord(p+16)&~255u)&&!(MsObservationWord(p+24)&~15u)&&
            MsObservationWord(p+28)<=255&&!(MsObservationWord(p+32)&~127u)&&MsObservationWord(p+40)<=65535u;
    case MS_OBSERVE_CONTROL:
        return bytes==16&&!(MsObservationWord(p+8)&~2047u)&&
            (MsObservationWord(p+12)<=255||MsObservationWord(p+12)==0xffffffffu);
    case MS_OBSERVE_CRANE:
        return bytes==104&&MsObservationWord(p+8)<5&&MsObservationWord(p+16)<=32767&&
            !(MsObservationWord(p+20)&~3u);
    case MS_OBSERVE_SPIN:
        return bytes==28&&MsObservationWord(p+8)&&MsObservationWord(p+12)>=1&&
            MsObservationWord(p+12)<=9&&MsObservationWord(p+16)<=1&&MsObservationWord(p+24)==1&&
            (MsObservationWord(p+16)?(MsObservationWord(p+20)==2||MsObservationWord(p+20)==3):MsObservationWord(p+20)==4);
    case MS_OBSERVE_ANIMATION:
        return bytes==28&&MsObservationWord(p+8)<=1&&MsObservationWord(p+12)<=65535u&&
            (!(MsObservationWord(p+8))||((MsObservationWord(p+16)&0x7f800000u)!=0x7f800000u&&
             (MsObservationWord(p+20)&0x7f800000u)!=0x7f800000u&&MsObservationWord(p+24)<=32767u));
    default:return type!=0;
    }
}
#endif
