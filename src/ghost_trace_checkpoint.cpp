#include "susamune/ghost_trace_producer.hxx"
namespace GhostTrace {
bool checkpointValid(const CheckpointSnapshot&v){
    if(!v.magic){const unsigned*p=reinterpret_cast<const unsigned*>(&v);for(unsigned i=0;i<sizeof(v)/4;++i)if(p[i])return false;return true;}
    if(v.magic!=kCheckpointMagic||v.version!=kCheckpointVersion||!v.prefix.nonce||!v.prefix.run||!v.prefix.generation||!v.prefix.frame||!v.prefix.chunk||
       !v.prefix.recordBytes||v.prefix.recordBytes>MS_TRACE_BUFFER_BYTES||v.scene>0xffffu||v.reserved[0]||v.reserved[1]||
       (v.game!=0x474d534au&&v.game!=0x474d5345u&&v.game!=0x474d5350u)||(v.capabilities&0xff000000u))return false;
    const unsigned*p=reinterpret_cast<const unsigned*>(&v.fence);bool any=false;for(unsigned i=0;i<8;++i)any|=p[i]!=0;
    if(!any)return true;MsTraceBranch b={v.prefix.nonce,v.prefix.run^0x40000000u,v.game,v.capabilities,v.prefix,v.fence,kForkOwner,1,1,0};
    return MsTraceBranchValid(&b,MS_TRACE_BRANCH_FORK);
}
}
