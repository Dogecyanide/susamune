#ifndef MOONSHINE_GHOST_TRACE_CHECKPOINT_H
#define MOONSHINE_GHOST_TRACE_CHECKPOINT_H
#include "ghost_trace.h"
#include "ghost_provenance.h"
#ifndef MS_TRACE_BRANCH_RETENTION_READY
#define MS_TRACE_BRANCH_RETENTION_READY 1
#endif
struct MsTracePrefix { unsigned nonce,run,generation,frame,tick,chunk,recordBytes,checksum; };
struct MsTraceFenceInfo { unsigned sequence,fileBytes,chunkOffset,recordBytes,checksum,headerHash,reserved[2]; };
struct MsTraceBranch {
    unsigned nonce,run,game,capabilities;
    struct MsTracePrefix parent;
    struct MsTraceFenceInfo fence;
    unsigned ownerKind,ownerId,ownerGeneration,reserved;
};
enum { MS_TRACE_BRANCH_MAGIC=0x4d534742u, MS_TRACE_BRANCH_VERSION=1, MS_TRACE_BRANCH_BYTES=128,
       MS_TRACE_BRANCH_FORK=1, MS_TRACE_BRANCH_PIN=2, MS_TRACE_BRANCH_CHECKPOINT=3 };
#define MS_TRACE_BRANCH_MAILBOX_OFFSET 0x1040u
#define MS_TRACE_FENCE_INFO_OFFSET 0x10e0u
enum MsTraceBranchOperation { MS_TRACE_BRANCH_STORE=1, MS_TRACE_BRANCH_UNPIN, MS_TRACE_BRANCH_DELETE, MS_TRACE_BRANCH_LOOKUP, MS_TRACE_BRANCH_ASYNC_CONTINUE };
#define MS_TRACE_BRANCH_PENDING 0x100u
#define MS_TRACE_BRANCH_HEADER_TAG 0x42524348u
#define MS_TRACE_BRANCH_HEADER_FLAGS 0x23u
#define MS_TRACE_BRANCH_HEADER_OFFSET 44u
#define MS_TRACE_BRANCH_PARENT_OFFSET 48u
// Async kind/nonce/run bind the primary sequence, preserve flag and old run.
struct MsTraceBranchRequest { unsigned magic,version,bootNonce,sequence,operation,kind,nonce,run; };
struct MsTraceBranchResponse { unsigned magic,version,bootNonce,ack,status,reserved[3]; };
struct MsTraceBranchMailbox { struct MsTraceBranch payload;struct MsTraceBranchRequest request;struct MsTraceBranchResponse response; };
#define MS_TRACE_BRANCH_LOOKUP_OFFSET 0x1100u
#define MS_TRACE_BRANCH_FORK_OWNER 0x464f524bu
#define MS_TRACE_LIBRARY_PIN_OFFSET 0x1c00u
#define MS_TRACE_OWNER_LIBRARY 0x4c420000u
#define MS_TRACE_OWNER_STATE 0x80000000u
struct MsTraceFileIdentity { unsigned version,game,scene,capabilities,bytes,chunks,headerHash,footerHash; };
struct MsTraceLookup {
    struct MsTraceBranch branch;
    struct MsTraceFileIdentity file;
    unsigned bootNonce,sequence,nonce,run,kind,runFlags,reserved[2];
};
enum { MS_TRACE_LOOKUP_ORDINARY=0, MS_TRACE_LOOKUP_BRANCH=1 };
typedef char MsTraceLookupPlacement[(sizeof(struct MsTraceLookup)==160 &&
    MS_TRACE_FENCE_INFO_OFFSET+sizeof(struct MsTraceFenceInfo)==MS_TRACE_BRANCH_LOOKUP_OFFSET &&
    MS_TRACE_BRANCH_LOOKUP_OFFSET+sizeof(struct MsTraceLookup)<=0x2000u)?1:-1];
typedef char MsTraceBranchMailboxSize[(sizeof(struct MsTraceBranchMailbox)==160 &&
    __builtin_offsetof(struct MsTraceBranchMailbox,request)==96 && __builtin_offsetof(struct MsTraceBranchMailbox,response)==128 &&
    MS_TRACE_BRANCH_MAILBOX_OFFSET+sizeof(struct MsTraceBranchMailbox)<=0x2000u)?1:-1];
typedef char MsTraceFencePlacement[(MS_TRACE_BRANCH_MAILBOX_OFFSET+sizeof(struct MsTraceBranchMailbox)==MS_TRACE_FENCE_INFO_OFFSET &&
    !(MS_TRACE_FENCE_INFO_OFFSET&31u) && MS_TRACE_FENCE_INFO_OFFSET+sizeof(struct MsTraceFenceInfo)<=0x2000u)?1:-1];

typedef char MsTracePrefixSize[(sizeof(struct MsTracePrefix)==32 && sizeof(struct MsTraceFenceInfo)==32 && sizeof(struct MsTraceBranch)==96)?1:-1];
static inline unsigned MsTraceGet(const unsigned char*p) {return (unsigned)p[0]<<24|(unsigned)p[1]<<16|(unsigned)p[2]<<8|p[3];}
static inline int MsTraceParentHeaderValid(const unsigned char*h) {
    unsigned tag,nonce,run,chunk;
    if(!h)return 0;tag=MsTraceGet(h+44);nonce=MsTraceGet(h+48);run=MsTraceGet(h+52);chunk=MsTraceGet(h+56);
    if(!tag)return !nonce&&!run&&!chunk;
    return tag==MS_TRACE_BRANCH_HEADER_TAG&&nonce&&run&&chunk&&(MsTraceGet(h+28)&MS_TRACE_HAS_CONTINUATION)&&
        (nonce!=MsTraceGet(h+16)||run!=MsTraceGet(h+20))&&
        MsTraceGet(h+36)==MS_TRACE_BRANCH_HEADER_FLAGS&&MsTraceGet(h+40)==MS_TRACE_PROVENANCE_TAG;
}
static inline int MsTracePrefixSame(const struct MsTracePrefix*a,const struct MsTracePrefix*b) {
    const unsigned*x=(const unsigned*)a,*y=(const unsigned*)b;unsigned i;
    for(i=0;i<8;++i)if(x[i]!=y[i])return 0;return 1;
}
static inline int MsTraceBranchValid(const struct MsTraceBranch*b,unsigned kind) {
    if((kind!=MS_TRACE_BRANCH_FORK && kind!=MS_TRACE_BRANCH_PIN && kind!=MS_TRACE_BRANCH_CHECKPOINT) || !b->nonce || !b->run ||
       (b->game!=0x474d534au && b->game!=0x474d5345u && b->game!=0x474d5350u) || (b->capabilities&0xff000000u) ||
       !b->parent.nonce || !b->parent.run || !b->parent.generation || !b->parent.frame || !b->parent.chunk ||
       b->fence.fileBytes<64 || b->fence.fileBytes>MS_TRACE_FILE_LIMIT-32 ||
       b->fence.reserved[0] || b->fence.reserved[1] || !b->ownerKind || !b->ownerId || (!b->ownerGeneration && kind!=MS_TRACE_BRANCH_CHECKPOINT) || b->reserved)return 0;
    if(kind==MS_TRACE_BRANCH_PIN)return !b->parent.recordBytes && !b->parent.checksum && !b->fence.chunkOffset &&
        !b->fence.recordBytes && !b->fence.checksum && !b->fence.sequence;
    if(kind==MS_TRACE_BRANCH_CHECKPOINT && (!(b->ownerKind&MS_TRACE_OWNER_STATE) ||
        (b->ownerKind&~MS_TRACE_OWNER_STATE)>99999999u || b->ownerId>99999999u))return 0;
    return b->parent.recordBytes && b->parent.recordBytes<=MS_TRACE_BUFFER_BYTES && b->fence.sequence &&
        b->fence.chunkOffset>=64 && b->fence.chunkOffset<b->fence.fileBytes && b->fence.fileBytes-b->fence.chunkOffset>=44 &&
        b->fence.recordBytes==b->parent.recordBytes && b->fence.checksum==b->parent.checksum &&
        (kind==MS_TRACE_BRANCH_CHECKPOINT ? b->nonce==b->parent.nonce && b->run==b->parent.run :
         b->nonce!=b->parent.nonce || b->run!=b->parent.run);
}
static inline void MsTraceBranchEncode(unsigned char out[128],const struct MsTraceBranch*b,unsigned kind) {
    unsigned i;const unsigned*words=(const unsigned*)b;
    for(i=0;i<128;++i)out[i]=0;
    MsTracePut(out,MS_TRACE_BRANCH_MAGIC);MsTracePut(out+4,MS_TRACE_BRANCH_VERSION);MsTracePut(out+8,128);MsTracePut(out+12,kind);
    for(i=0;i<24;++i)MsTracePut(out+16+i*4,words[i]);
    MsTracePut(out+124,MsTraceHash(2166136261u,out,124));
}
static inline int MsTraceBranchDecode(struct MsTraceBranch*b,unsigned*kind,const unsigned char in[128]) {
    unsigned i,*words=(unsigned*)b;
    if(MsTraceGet(in)!=MS_TRACE_BRANCH_MAGIC || MsTraceGet(in+4)!=MS_TRACE_BRANCH_VERSION || MsTraceGet(in+8)!=128 ||
       MsTraceGet(in+112) || MsTraceGet(in+116) || MsTraceGet(in+120) || MsTraceGet(in+124)!=MsTraceHash(2166136261u,in,124))return 0;
    *kind=MsTraceGet(in+12);for(i=0;i<24;++i)words[i]=MsTraceGet(in+16+i*4);
    return MsTraceBranchValid(b,*kind);
}
#endif
