#ifndef MOONSHINE_GHOST_STATE_REFERENCE_H
#define MOONSHINE_GHOST_STATE_REFERENCE_H
#include "ghost_trace_checkpoint.h"

#define MS_TRACE_CHECKPOINT_MAGIC 0x4d534743u
#define MS_TRACE_CHECKPOINT_VERSION 1u
#define MS_STATE_TRACE_REFERENCE_MAGIC 0x4d535243u
#define MS_STATE_TRACE_REFERENCE_BYTES 96u

struct MsTraceStateReference {
    unsigned magic,version;
    struct MsTracePrefix prefix;
    unsigned game,scene,capabilities,ownerToken;
    struct MsTraceFenceInfo fence;
    unsigned reserved[2];
};
typedef char MsTraceStateReferenceSize[sizeof(struct MsTraceStateReference)==MS_STATE_TRACE_REFERENCE_BYTES?1:-1];

static inline int MsTraceStateReferenceValid(const struct MsTraceStateReference*v,int durable) {
    const unsigned*words=(const unsigned*)v;
    struct MsTraceBranch b={0};
    unsigned i,any=0;
    if(!v->magic) {
        if(durable)return 0;
        for(i=0;i<sizeof(*v)/4;++i)if(words[i])return 0;
        return 1;
    }
    if(v->magic!=MS_TRACE_CHECKPOINT_MAGIC||v->version!=MS_TRACE_CHECKPOINT_VERSION||
       v->scene>0xffffu||v->reserved[0]||v->reserved[1])return 0;
    b.nonce=v->prefix.nonce;b.run=v->prefix.run;b.game=v->game;b.capabilities=v->capabilities;
    b.parent=v->prefix;b.fence=v->fence;b.ownerKind=MS_TRACE_OWNER_STATE;b.ownerId=b.ownerGeneration=1;
    words=(const unsigned*)&v->fence;
    for(i=0;i<sizeof(v->fence)/4;++i)any|=words[i];
    if(!any&&!durable) {
        b.fence.sequence=1;b.fence.fileBytes=108;b.fence.chunkOffset=64;
        b.fence.recordBytes=b.parent.recordBytes;b.fence.checksum=b.parent.checksum;
    }
    return MsTraceBranchValid(&b,MS_TRACE_BRANCH_CHECKPOINT);
}
#endif
