#include "susamune/ghost_trace_branch_io.hxx"
#include "susamune/ghost_trace_branch_owner.hxx"
namespace GhostTraceBranchOwner { State state; }
namespace GhostTraceBranchIo {
namespace {
bool separate(const void*a,unsigned an,const void*b,unsigned bn){const auto x=reinterpret_cast<__UINTPTR_TYPE__>(a),y=reinterpret_cast<__UINTPTR_TYPE__>(b);return x&&y&&an<=static_cast<__UINTPTR_TYPE__>(-1)-x&&bn<=static_cast<__UINTPTR_TYPE__>(-1)-y&&(x+an<=y||y+bn<=x);}
void invalidate(Client&c,volatile void*p,unsigned bytes){c.hooks.invalidate(c.hooks.context,const_cast<void*>(p),bytes);}
void flush(Client&c,volatile void*p,unsigned bytes){c.hooks.flush(c.hooks.context,const_cast<void*>(p),bytes);}
bool header(const Client&c,const MsTraceBranchResponse&r){return r.magic==MS_TRACE_BRANCH_MAGIC&&r.version==MS_TRACE_BRANCH_VERSION&&r.bootNonce==c.nonce;}
}
bool configure(Client&c,const Hooks&h,unsigned nonce){
    if(!nonce||!h.mailbox||!h.result||!h.flush||!h.invalidate||c.phase==WAITING||
       !separate(&c,sizeof(c),const_cast<const MsTraceBranchMailbox*>(h.mailbox),sizeof(*h.mailbox))||
       !separate(&c,sizeof(c),const_cast<const MsTraceLookup*>(h.result),sizeof(*h.result))||
       !separate(const_cast<const MsTraceBranchMailbox*>(h.mailbox),sizeof(*h.mailbox),const_cast<const MsTraceLookup*>(h.result),sizeof(*h.result)))return false;
    c={};c.hooks=h;c.nonce=nonce;invalidate(c,&h.mailbox->response,32);MsTraceBranchResponse response;
    __builtin_memcpy(&response,const_cast<const MsTraceBranchResponse*>(&h.mailbox->response),32);
    if(!header(c,response)){c.phase=FAILED;return false;}c.phase=IDLE;return true;
}
bool lookup(Client&c,unsigned nonce,unsigned run,unsigned game){
    if(c.phase!=IDLE||!nonce||!run||(game!=0x474d534au&&game!=0x474d5345u&&game!=0x474d5350u))return false;
    auto&box=*c.hooks.mailbox;invalidate(c,&box.response,32);invalidate(c,&box.request,32);MsTraceBranchResponse response;
    __builtin_memcpy(&response,const_cast<const MsTraceBranchResponse*>(&box.response),32);
    if(!header(c,response)){c.error=MS_TRACE_PROTOCOL;c.phase=FAILED;return false;}
    if(response.ack!=box.request.sequence||response.ack==~0u||!GhostTraceBranchOwner::claim(&box,c.nonce,&c))return false;
    c.operation=MS_TRACE_BRANCH_LOOKUP;c.sequence=response.ack+1;c.fileNonce=nonce;c.run=run;c.game=game;c.canceled=false;
    MsTraceBranchRequest q={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,c.nonce,0,MS_TRACE_BRANCH_LOOKUP,game,nonce,run};
    __builtin_memcpy(const_cast<MsTraceBranchRequest*>(&box.request),&q,32);flush(c,&box.request,32);
    c.phase=WAITING;box.request.sequence=c.sequence;flush(c,&box.request,32);return true;
}
bool erase(Client&c,unsigned nonce,unsigned run,unsigned hash){
    if(c.phase!=IDLE||!nonce||!run)return false;
    auto&box=*c.hooks.mailbox;invalidate(c,&box.response,32);invalidate(c,&box.request,32);MsTraceBranchResponse r;
    __builtin_memcpy(&r,const_cast<const MsTraceBranchResponse*>(&box.response),32);
    if(!header(c,r)||r.ack!=box.request.sequence||r.ack==~0u||!GhostTraceBranchOwner::claim(&box,c.nonce,&c))return false;
    c.operation=MS_TRACE_BRANCH_DELETE;c.sequence=r.ack+1;c.fileNonce=nonce;c.run=run;c.game=0;c.canceled=false;
    MsTraceBranchRequest q={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,c.nonce,0,MS_TRACE_BRANCH_DELETE,hash,nonce,run};
    __builtin_memcpy(const_cast<MsTraceBranchRequest*>(&box.request),&q,32);flush(c,&box.request,32);
    c.phase=WAITING;box.request.sequence=c.sequence;flush(c,&box.request,32);return true;
}
Phase poll(Client&c){
    if(c.phase!=WAITING)return c.phase;auto&box=*c.hooks.mailbox;invalidate(c,&box.response,32);MsTraceBranchResponse r;
    __builtin_memcpy(&r,const_cast<const MsTraceBranchResponse*>(&box.response),32);
    if(!header(c,r)){c.error=MS_TRACE_PROTOCOL;return WAITING;}
    if(r.ack!=c.sequence)return WAITING;
    if(c.canceled){GhostTraceBranchOwner::release(&box,c.nonce,&c);c.phase=IDLE;return IDLE;}
    if(r.status){c.error=r.status;c.phase=FAILED;return FAILED;}
    if(c.operation!=MS_TRACE_BRANCH_LOOKUP){c.phase=READY;return READY;}
    invalidate(c,c.hooks.result,sizeof(MsTraceLookup));__builtin_memcpy(&c.value,const_cast<const MsTraceLookup*>(c.hooks.result),sizeof(c.value));
    const auto&v=c.value;
    if(v.bootNonce!=c.nonce||v.sequence!=c.sequence||v.nonce!=c.fileNonce||v.run!=c.run||v.file.game!=c.game||
       v.kind>MS_TRACE_LOOKUP_BRANCH||v.reserved[0]||v.reserved[1]||((v.runFlags&0x20u)&&!(v.runFlags&1u))||!v.file.version||v.file.version>3||
       v.file.scene>0xffffu||v.file.bytes<96||v.file.bytes>MS_TRACE_FILE_LIMIT||(v.file.capabilities&0xff000000u)||v.file.chunks>(v.file.bytes-96)/32||
       (v.kind==MS_TRACE_LOOKUP_BRANCH&&(!MsTraceBranchValid(&v.branch,MS_TRACE_BRANCH_FORK)||v.branch.nonce!=v.nonce||v.branch.run!=v.run||
           v.branch.game!=v.file.game||v.branch.capabilities!=v.file.capabilities||v.branch.ownerKind!=MS_TRACE_BRANCH_FORK_OWNER||v.branch.ownerId!=1||v.branch.ownerGeneration!=1))){
        c.error=MS_TRACE_BAD_SOURCE;c.phase=FAILED;return FAILED;
    }
    if(!v.kind){const unsigned*p=reinterpret_cast<const unsigned*>(&v.branch);for(unsigned i=0;i<24;++i)if(p[i]){c.error=MS_TRACE_BAD_SOURCE;c.phase=FAILED;return FAILED;}}
    c.phase=READY;return READY;
}
bool pin(Client&c,const MsTraceBranch&value,bool release){
    if(c.phase!=IDLE||!MsTraceBranchValid(&value,MS_TRACE_BRANCH_PIN))return false;
    auto&box=*c.hooks.mailbox;invalidate(c,&box.response,32);invalidate(c,&box.request,32);MsTraceBranchResponse r;
    __builtin_memcpy(&r,const_cast<const MsTraceBranchResponse*>(&box.response),32);
    if(!header(c,r)||r.ack!=box.request.sequence||r.ack==~0u||!GhostTraceBranchOwner::claim(&box,c.nonce,&c))return false;
    c.sequence=r.ack+1;c.operation=release?MS_TRACE_BRANCH_UNPIN:MS_TRACE_BRANCH_STORE;c.fileNonce=value.nonce;c.run=value.run;c.game=value.game;c.canceled=false;
    MsTraceBranchRequest q={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,c.nonce,0,c.operation,MS_TRACE_BRANCH_PIN,value.nonce,value.run};
    __builtin_memcpy(const_cast<MsTraceBranch*>(&box.payload),&value,96);__builtin_memcpy(const_cast<MsTraceBranchRequest*>(&box.request),&q,32);
    flush(c,&box.payload,128);c.phase=WAITING;box.request.sequence=c.sequence;flush(c,&box.request,32);return true;
}
const MsTraceLookup*result(const Client&c){return c.phase==READY&&c.operation==MS_TRACE_BRANCH_LOOKUP?&c.value:nullptr;}
bool consume(Client&c){if(c.phase!=READY)return false;GhostTraceBranchOwner::release(c.hooks.mailbox,c.nonce,&c);c.phase=IDLE;c.value={};return true;}
bool cancel(Client&c){if(c.phase==WAITING){c.canceled=true;return poll(c)!=WAITING;}if(c.phase!=UNCONFIGURED){GhostTraceBranchOwner::release(c.hooks.mailbox,c.nonce,&c);c.phase=IDLE;}return true;}
}
