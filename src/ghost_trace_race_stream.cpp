#include "susamune/state_save_probe.hxx"
#include "susamune/ghost_trace_race_stream.hxx"

namespace GhostTraceRaceStream {
namespace {
const unsigned kEmpty=~0u;
using namespace GhostTraceIndex;
bool active(const Stream &s) { return s.arena&&s.pages&&s.count; }
bool pending(const Stream &s) { return s.slots[0].sequence||s.slots[1].sequence; }
bool alias(const void *a,unsigned an,const void *b,unsigned bn) {
    const GhostArena::Address x=reinterpret_cast<GhostArena::Address>(a),y=reinterpret_cast<GhostArena::Address>(b);
    return x<y+bn&&y<x+an;
}
const Slot *slot(const Stream &s,unsigned page) {
    for(unsigned i=0;i<2;++i)if(s.slots[i].page==page)return &s.slots[i];
    return nullptr;
}
}
bool begin(Stream &s,GhostArena::Arena &arena,const Page *pages,unsigned count) {
    if(StateSaveProbe::enabled()||s.arena||!validDirectory(pages,count))return false;
    GhostArena::Handle leases[2];
    leases[0]=GhostArena::acquire(arena,GhostArena::RACING,kPageBytes);
    if(!GhostArena::find(arena,leases[0],GhostArena::RACING))return false;
    leases[1]=GhostArena::acquire(arena,GhostArena::RACING,kPageBytes);
    bool good=GhostArena::find(arena,leases[1],GhostArena::RACING)!=nullptr;
    for(unsigned i=0;i<2&&good;++i) {
        const GhostArena::View view=GhostArena::read(arena,leases[i],GhostArena::RACING);
        good=!alias(view.data,view.bytes,pages,count*sizeof(Page))&&!alias(view.data,view.bytes,&s,sizeof(s));
    }
    if(!good) {
        GhostArena::release(arena,leases[0],GhostArena::RACING);
        GhostArena::release(arena,leases[1],GhostArena::RACING);return false;
    }
    const unsigned sequence=s.sequence;
    s={};s.arena=&arena;s.pages=pages;s.count=count;s.sequence=sequence;
    for(unsigned i=0;i<2;++i)s.slots[i]={leases[i],kEmpty,0,0};
    return true;
}
bool request(Stream &s,Query query) {
    if(!active(s)||s.error||pending(s))return false;
    Needed needed;
    if(!locate(s.pages,s.count,query,needed))return false;
    s.query=query;s.needed=needed;s.selected=1;return true;
}
bool nextRead(Stream &s,Read &out) {
    if(!active(s)||s.error||!s.selected)return false;
    const unsigned needed[2]={s.needed.first,s.needed.second};
    for(unsigned n=0;n<2;++n) {
        if(slot(s,needed[n]))continue;
        for(unsigned i=0;i<2;++i) {
            Slot &target=s.slots[i];
            if(target.sequence||target.page==needed[0]||target.page==needed[1])continue;
            if(s.sequence==~0u) { s.error=EXHAUSTED;return false; }
            const GhostArena::Span buffer=GhostArena::write(*s.arena,target.lease,GhostArena::RACING);
            if(!buffer.data||buffer.bytes<kPageBytes||!GhostArena::pin(*s.arena,target.lease,
                GhostArena::RACING,s.sequence+1,GhostArena::WRITES_MEMORY)) { s.error=OWNERSHIP;return false; }
            target.page=needed[n];target.sequence=++s.sequence;target.ready=0;
            out={target.sequence,target.page*kPageBytes,static_cast<unsigned>(s.pages[target.page].count*sizeof(Sample)),buffer.data};
            return true;
        }
    }
    return false;
}
bool acceptRead(Stream &s,unsigned sequence,unsigned bytes,bool success) {
    if(!active(s)||!sequence)return false;
    for(unsigned i=0;i<2;++i) {
        Slot &target=s.slots[i];if(target.sequence!=sequence)continue;
        if(!GhostArena::complete(*s.arena,target.lease,GhostArena::RACING,sequence)) { s.error=OWNERSHIP;return false; }
        target.sequence=0;
        if(!success) { s.error=IO;return false; }
        const GhostArena::View view=GhostArena::read(*s.arena,target.lease,GhostArena::RACING);
        if(!view.data||bytes>view.bytes||!validPage(s.pages[target.page],view.data,bytes)) { s.error=CORRUPT;return false; }
        target.ready=1;return true;
    }
    return false;
}
bool sample(const Stream &s,Bracket &out) {
    if(!active(s)||s.error||!s.selected)return false;
    const Slot *a=slot(s,s.needed.first),*b=slot(s,s.needed.second);
    if(!a||!b||!a->ready||!b->ready)return false;
    const GhostArena::View av=GhostArena::read(*s.arena,a->lease,GhostArena::RACING),
        bv=GhostArena::read(*s.arena,b->lease,GhostArena::RACING);
    return av.data&&bv.data&&bracket(s.query,s.pages[a->page],static_cast<const Sample*>(av.data),
        s.pages[b->page],static_cast<const Sample*>(bv.data),out);
}
bool close(Stream &s) {
    if(!s.arena)return true;
    if(pending(s))return false;
    for(unsigned i=0;i<2;++i)if(!GhostArena::find(*s.arena,s.slots[i].lease,GhostArena::RACING))return false;
    for(unsigned i=0;i<2;++i)if(!GhostArena::release(*s.arena,s.slots[i].lease,GhostArena::RACING))return false;
    // Retain request generations across close/reopen to reject delayed duplicate ACKs.
    const unsigned sequence=s.sequence;s={};s.sequence=sequence;return true;
}
}
