#ifndef MOONSHINE_GHOST_TRACE_CODEC_H
#define MOONSHINE_GHOST_TRACE_CODEC_H
#include "ghost_trace.h"
/* Changed native words remain byte-exact, including pointers, padding and NaNs. */
static inline unsigned MsTraceWordDelta(unsigned char *out,const unsigned char *previous,
                                        const unsigned char *current,unsigned bytes) {
    if(!bytes||bytes>512||(bytes&3))return 0;
    unsigned masks[4]={0,0,0,0},maskCount=(bytes+127)/128,at=maskCount*4;
    for(unsigned word=0;word<bytes/4;++word){
        const unsigned offset=word*4;
        if(current[offset]==previous[offset]&&current[offset+1]==previous[offset+1]&&
           current[offset+2]==previous[offset+2]&&current[offset+3]==previous[offset+3])continue;
        masks[word/32]|=1u<<(word%32);
        if(at+4>=bytes)return 0;
        for(unsigned i=0;i<4;++i)out[at+i]=current[offset+i];at+=4;
    }
    for(unsigned i=0;i<maskCount;++i)MsTracePut(out+i*4,masks[i]);
    return at;
}
#endif
