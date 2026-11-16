#pragma once
#include "ghost_trace_checkpoint.h"
namespace GhostCheckpoints {
enum { kPins=8, kSlots=3, kNone=8 };
enum Phase { EMPTY, PENDING, DURABLE, FAILED };
struct Pin { MsTracePrefix prefix;MsTraceFenceInfo fence;unsigned phase,request,references,error; };
struct Slot { unsigned generation,pin; };
struct Load { MsTracePrefix prefix;unsigned token; };
struct State { Pin pins[kPins];Slot slots[kSlots];unsigned candidate,loadPin,loadToken,nextToken,loadRequest;bool loadCanceled; };
inline void init(State&s){s={};s.candidate=s.loadPin=kNone;s.nextToken=1;for(unsigned i=0;i<kSlots;++i)s.slots[i].pin=kNone;}
inline Pin*find(State&s,const MsTracePrefix&p){for(unsigned i=0;i<kPins;++i)if(s.pins[i].phase!=EMPTY&&MsTracePrefixSame(&s.pins[i].prefix,&p))return s.pins+i;return nullptr;}
inline void collect(Pin&p){if(!p.references&&p.phase!=PENDING)p={};}
// Candidate ownership begins before RAM compression and survives late I/O receipts.
inline bool capture(State&s,const MsTracePrefix&p,unsigned request){
    if(s.candidate!=kNone||!p.nonce||!p.run||!p.generation||!p.frame||!p.chunk||!p.recordBytes||p.recordBytes>MS_TRACE_BUFFER_BYTES )return false;
    if(Pin*existing=find(s,p)){if(existing->phase==FAILED||existing->references==~0u)return false;++existing->references;s.candidate=static_cast<unsigned>(existing-s.pins);return true;}
    for(unsigned i=0;i<kPins;++i)if(s.pins[i].phase==EMPTY){s.pins[i]={p,{},PENDING,request,1,0};s.candidate=i;return true;}return false;
}
// The archive worker has already checked and pinned this durable file prefix.
inline bool adoptDurable(State&s,const MsTracePrefix&p,const MsTraceFenceInfo&f){
    MsTraceBranch proof={p.nonce,p.run,0x474d534au,0,p,f,MS_TRACE_OWNER_STATE,1,1,0};
    if(!MsTraceBranchValid(&proof,MS_TRACE_BRANCH_CHECKPOINT))return false;
    Pin*existing=find(s,p);
    if(existing){
        if(existing->phase!=DURABLE||__builtin_memcmp(&existing->fence,&f,sizeof(f)))return false;
        if(s.candidate<kPins)return existing==s.pins+s.candidate;
    }
    if(!capture(s,p,0))return false;
    Pin&pin=s.pins[s.candidate];pin.phase=DURABLE;pin.fence=f;pin.request=0;return true;
}
inline bool acknowledge(State&s,unsigned nonce,unsigned run,unsigned request,const MsTraceFenceInfo&f,unsigned error){
    for(unsigned i=0;i<kPins;++i){Pin&p=s.pins[i];if(p.phase!=PENDING||p.request!=request||p.prefix.nonce!=nonce||p.prefix.run!=run)continue;
        if(!error&&(f.sequence!=request||f.recordBytes!=p.prefix.recordBytes||f.checksum!=p.prefix.checksum||f.chunkOffset<64||
            f.fileBytes<=f.chunkOffset||f.fileBytes-f.chunkOffset<44||f.fileBytes>MS_TRACE_FILE_LIMIT-32||f.reserved[0]||f.reserved[1]))return false;
        p.phase=error?FAILED:DURABLE;p.error=error;p.fence=f;collect(p);return true;
    }return false;
}
inline bool commit(State&s,unsigned slot,unsigned generation){
    if(slot>=kSlots||!generation||s.candidate>=kPins||s.pins[s.candidate].phase==FAILED)return false;
    Slot&old=s.slots[slot];if(old.pin<kPins){Pin&p=s.pins[old.pin];if(!p.references)return false;--p.references;collect(p);}
    old={generation,s.candidate};s.candidate=kNone;return true;
}
inline void abandon(State&s){if(s.candidate<kPins){Pin&p=s.pins[s.candidate];--p.references;collect(p);s.candidate=kNone;}}
inline bool clear(State&s,unsigned slot,unsigned generation){
    if(slot>=kSlots||s.slots[slot].generation!=generation||s.slots[slot].pin>=kPins)return false;
    Pin&p=s.pins[s.slots[slot].pin];if(!p.references)return false;--p.references;collect(p);s.slots[slot]={0,kNone};return true;
}
inline Pin*retainPrefixLoad(State&s,const MsTracePrefix&prefix,Load&load){
    Pin*pin=find(s,prefix);
    if(!pin||pin->phase!=DURABLE||!pin->references||pin->references==~0u||s.loadPin!=kNone||!s.nextToken)return nullptr;
    ++pin->references;s.loadPin=static_cast<unsigned>(pin-s.pins);s.loadToken=s.nextToken++;
    s.loadRequest=0;s.loadCanceled=false;load={pin->prefix,s.loadToken};return pin;
}
inline Pin*retainLoad(State&s,unsigned slot,unsigned generation,Load&load){
    if(slot>=kSlots||s.slots[slot].generation!=generation||s.slots[slot].pin>=kPins||s.loadPin!=kNone||!s.nextToken)return nullptr;
    Pin&p=s.pins[s.slots[slot].pin];if(!p.references||p.references==~0u||p.phase==FAILED)return nullptr;
    ++p.references;s.loadPin=s.slots[slot].pin;s.loadToken=s.nextToken++;s.loadRequest=0;s.loadCanceled=false;load={p.prefix,s.loadToken};return &p;
}
inline bool releaseLoad(State&s,const Load&load){
    if(s.loadPin>=kPins||s.loadToken!=load.token||!MsTracePrefixSame(&s.pins[s.loadPin].prefix,&load.prefix))return false;
    if(s.loadRequest){s.loadCanceled=true;return false;}
    Pin&p=s.pins[s.loadPin];if(!p.references)return false;--p.references;collect(p);s.loadPin=kNone;s.loadToken=0;return true;
}
inline bool forkIssued(State&s,const Load&load,unsigned request){
    if(!request||s.loadPin>=kPins||s.loadToken!=load.token||!MsTracePrefixSame(&s.pins[s.loadPin].prefix,&load.prefix)||s.loadRequest||s.pins[s.loadPin].phase!=DURABLE||s.loadCanceled)return false;
    s.loadRequest=request;return true;
}
inline bool forkAcknowledged(State&s,const Load&load,unsigned request){
    if(!request||s.loadPin>=kPins||s.loadToken!=load.token||!MsTracePrefixSame(&s.pins[s.loadPin].prefix,&load.prefix)||s.loadRequest!=request)return false;
    s.loadRequest=0;if(s.loadCanceled)return releaseLoad(s,load);return true;
}
inline bool sourceOwned(const State&s,unsigned nonce,unsigned run){for(unsigned i=0;i<kPins;++i){const Pin&p=s.pins[i];if(p.phase!=EMPTY&&p.prefix.nonce==nonce&&p.prefix.run==run&&(p.references||p.phase==PENDING))return true;}return false;}
inline bool ready(const Pin&p){return p.phase==DURABLE;}
}
