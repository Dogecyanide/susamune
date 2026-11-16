#ifndef MOONSHINE_GHOST_TRACE_CONTINUATION_H
#define MOONSHINE_GHOST_TRACE_CONTINUATION_H
#include "ghost_trace_checkpoint.h"
#define MS_TRACE_CONTINUATION_RUN_FLAGS 0x23u
#define MS_TRACE_CONTINUATION_BYTES 48u
#define MS_TRACE_CONTINUATION_QF_VALID 1u
#define MS_TRACE_AUDIO_STOP 1u
#define MS_TRACE_AUDIO_PAUSE_ON 2u
#define MS_TRACE_AUDIO_PAUSE_OFF 4u
struct MsTraceContinuation { unsigned runFlags,actions,parentNonce,parentRun,parentChunk,parentHash,rngSeed,qf,attempt,generation,contextFlags; };
static inline int MsTraceContinuationDecode(struct MsTraceContinuation*out,const unsigned char*p,unsigned n) {
    if(!out||!p||n!=MS_TRACE_CONTINUATION_BYTES||MsTraceGet(p)!=1||MsTraceGet(p+4)!=MS_TRACE_CONTINUATION_RUN_FLAGS||
       (MsTraceGet(p+8)&~7u)||(MsTraceGet(p+8)&6u)==6u||!MsTraceGet(p+12)||!MsTraceGet(p+16)||!MsTraceGet(p+20)||(MsTraceGet(p+44)&~1u)||
       ((MsTraceGet(p+44)&1u)?MsTraceGet(p+32)>0x7fffffffu:MsTraceGet(p+32)!=0))return 0;
    out->runFlags=MsTraceGet(p+4);out->actions=MsTraceGet(p+8);out->parentNonce=MsTraceGet(p+12);out->parentRun=MsTraceGet(p+16);
    out->parentChunk=MsTraceGet(p+20);out->parentHash=MsTraceGet(p+24);out->rngSeed=MsTraceGet(p+28);out->qf=MsTraceGet(p+32);out->attempt=MsTraceGet(p+36);
    out->generation=MsTraceGet(p+40);out->contextFlags=MsTraceGet(p+44);return 1;
}
#endif
