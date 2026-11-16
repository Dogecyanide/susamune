#include "susamune/ghost_trace_index.hxx"
#include "susamune/ghost_format.h"

namespace GhostTraceIndex {
namespace {
using Address=__UINTPTR_TYPE__;
bool range(const void *p,unsigned n) { const Address a=reinterpret_cast<Address>(p);return a&&n&&a+n>=a; }
bool overlap(const void *a,unsigned an,const void *b,unsigned bn) {
    const Address x=reinterpret_cast<Address>(a),y=reinterpret_cast<Address>(b);
    return x<y+bn&&y<x+an;
}
unsigned hash(const void *data,unsigned n) {
    const unsigned char *p=static_cast<const unsigned char*>(data);unsigned h=2166136261u;
    while(n--)h=(h^*p++)*16777619u;
    return h;
}
bool finite(float v) { unsigned u;__builtin_memcpy(&u,&v,4);return (u&0x7f800000u)!=0x7f800000u; }
bool valid(const Sample &s) {
    const unsigned version=s.reserved[0];
    const bool legacy=version>=3&&version<=10,observation=legacy&&(s.flags&INPUT)&&!(s.flags&POSE);
    if(!s.frame||(s.flags&~31u)||(version&&!legacy)||(!legacy&&s.reserved[1])||s.raw.reserved||s.visible>1||
       s.animationId>SUSAMUNE_GHOST_ANIMATION_ID_MAX||s.animationPhase>SUSAMUNE_GHOST_ANIMATION_PHASE_MAX||
       s.yoshi>5||(s.raw.buttons&~0x1f7fu)||((s.flags&POSE)&&(s.fludd.mode&SUSAMUNE_GHOST_VISUAL_YOSHI)&&!s.yoshi)||
       !finite(s.x)||!finite(s.y)||!finite(s.z)||
       !SusamuneGhostVisualValid(reinterpret_cast<const unsigned char*>(&s.fludd),version?version>=7:1))return false;
    if(legacy&&((version<5&&(s.flags&INPUT))||(version<6&&s.fludd.mode)||(s.flags&(FROZEN|SUPPRESSED))||(!(s.flags&INPUT)&&s.reserved[1])||
       (version<10&&s.reserved[1])||(observation&&version<10&&s.yaw)))return false;
    if(observation&&version==10) {
        const unsigned mode=s.reserved[1]&127u;
        if(mode>0x49u&&(mode!=127u||s.yaw))return false;
    }
    if(!(s.flags&POSE)&&(s.x||s.y||s.z||(!observation&&s.yaw)||s.animationId||s.animationPhase||s.heldNameKey||
       s.heldObjectId||s.yoshi||s.visible||(!observation&&s.fludd.mode)))return false;
    if(!(s.flags&QFT)&&s.qf)return false;
    if(!(s.flags&INPUT)) {
        const GhostTraceDecode::RawPad zero={};
        if(__builtin_memcmp(&s.raw,&zero,sizeof(zero))||(s.flags&(FROZEN|SUPPRESSED)))return false;
    }
    return true;
}
bool same(Identity a,Identity b) { return a.scene==b.scene&&a.attempt==b.attempt&&a.generation==b.generation; }
Identity identity(const Page &p) { return {p.scene,p.attempt,p.generation}; }
unsigned key(const Sample &s,Clock c) { return c==QF_CLOCK?(static_cast<unsigned>(s.qf)^0x80000000u):s.frame; }
unsigned firstKey(const Page &p,Clock c) { return c==QF_CLOCK?(static_cast<unsigned>(p.firstQf)^0x80000000u):p.firstFrame; }
unsigned lastKey(const Page &p,Clock c) { return c==QF_CLOCK?(static_cast<unsigned>(p.lastQf)^0x80000000u):p.lastFrame; }
Result fail(Builder &b,Error error) { b.error=error;return FAILED; }
Result seal(Builder &b) {
    if(b.error)return FAILED;
    if(b.pending)return PAGE_READY;
    if(!b.used)return ACCEPTED;
    if(b.count==b.capacity)return fail(b,CAPACITY);
    const Sample &first=b.samples[0],&last=b.samples[b.used-1];
    b.pages[b.count]={b.count,b.segment,b.identity.scene,b.identity.attempt,b.identity.generation,b.used,
        first.qf,last.qf,first.frame,last.frame,hash(b.samples,b.used*sizeof(Sample)),first.flags&QFT};
    __builtin_memset(b.samples+b.used,0,(kSamplesPerPage-b.used)*sizeof(Sample));
    b.pending=1;return PAGE_READY;
}
}
bool begin(Builder &b,Page *pages,unsigned capacity,void *scratch,unsigned bytes) {
    if(!capacity||capacity>kMaxPages||bytes<kPageBytes||
       !range(pages,capacity*sizeof(Page))||!range(scratch,kPageBytes)||
       (reinterpret_cast<Address>(pages)&3u)||(reinterpret_cast<Address>(scratch)&31u)||
       overlap(pages,capacity*sizeof(Page),scratch,kPageBytes)||
       overlap(&b,sizeof(b),pages,capacity*sizeof(Page))||overlap(&b,sizeof(b),scratch,kPageBytes))return false;
    b={};b.pages=pages;b.samples=static_cast<Sample*>(scratch);b.capacity=capacity;return true;
}
Result append(Builder &b,const Identity &id,const Sample &s) {
    if(b.error)return FAILED;
    if(!b.pages||!b.samples||b.done)return fail(b,STATE);
    if(b.pending)return PAGE_READY;
    if(id.scene>0xffffu||!valid(s))return fail(b,VALUE);
    if(b.seen&&s.frame<=b.last.frame)return fail(b,ORDER);
    const bool changed=b.seen&&(!same(id,b.identity)||((s.flags^b.last.flags)&QFT)||
        ((s.flags&QFT)&&s.qf<b.last.qf));
    if(b.used&&(b.used==kSamplesPerPage||changed))return seal(b);
    if(b.count==b.capacity)return fail(b,CAPACITY);
    if(changed)++b.segment;
    b.identity=id;b.samples[b.used++]=s;b.last=s;b.seen=true;return ACCEPTED;
}
Result finish(Builder &b) {
    if(b.error)return FAILED;
    if(!b.pages||!b.samples)return fail(b,STATE);
    const Result result=seal(b);if(result!=ACCEPTED)return result;
    b.done=1;return FINISHED;
}
const Page *pendingPage(const Builder &b) { return b.pending&&!b.error?b.pages+b.count:nullptr; }
bool commitPage(Builder &b) {
    if(!b.pending||b.error)return false;
    ++b.count;b.used=0;b.pending=0;return true;
}
bool begin(Capture &c,Page *pages,unsigned capacity,void *scratch,unsigned bytes) {
    if(overlap(&c,sizeof(c),pages,capacity<=kMaxPages?capacity*sizeof(Page):0)||
       overlap(&c,sizeof(c),scratch,kPageBytes))return false;
    if(!begin(c.builder,pages,capacity,scratch,bytes))return false;
    c.sample={};c.identity={};c.pending=false;return true;
}
Result feed(Capture &c,const GhostTraceDecode::Event &e) {
    if(c.builder.error)return FAILED;
    if(c.builder.done)return fail(c.builder,STATE);
    if(c.pending&&e.frame<c.sample.frame)return fail(c.builder,ORDER);
    if(c.pending&&e.frame>c.sample.frame) {
        const Result result=append(c.builder,c.identity,c.sample);
        if(result!=ACCEPTED)return result;
        c.pending=false;
    }
    if(e.type==GhostTraceDecode::VISUAL) {
        if(c.pending)return fail(c.builder,ORDER);
        const GhostTraceDecode::Visual &v=e.visual;
        c.sample={};c.sample.frame=e.frame;c.sample.movement=v.directorTick;c.sample.qf=(v.flags&QFT)?v.qf:0;
        c.sample.x=v.x;c.sample.y=v.y;c.sample.z=v.z;c.sample.heldObjectId=v.heldObjectId;
        c.sample.yaw=v.yaw;c.sample.animationId=v.animationId;c.sample.animationPhase=v.animationPhase;
        c.sample.heldNameKey=v.heldNameKey;c.sample.fludd=v.fludd;c.sample.flags=v.flags;
        c.sample.yoshi=v.yoshi;c.sample.visible=v.visible;
        c.identity={v.scene,v.attempt,v.generation};c.pending=true;
    } else if(e.type==GhostTraceDecode::INPUT&&c.pending&&(e.input.flags&GhostTraceDecode::kFrameInput)) {
        if(c.sample.flags&INPUT)return fail(c.builder,ORDER);
        c.sample.raw=e.input.raw;c.sample.flags|=INPUT;
        if(e.input.flags&GhostTraceDecode::kInputFrozen)c.sample.flags|=FROZEN;
        if(e.input.flags&GhostTraceDecode::kInputSuppressed)c.sample.flags|=SUPPRESSED;
    }
    return ACCEPTED;
}
Result finish(Capture &c) {
    if(c.pending) {
        const Result result=append(c.builder,c.identity,c.sample);
        if(result!=ACCEPTED)return result;
        c.pending=false;
    }
    return finish(c.builder);
}
bool validDirectory(const Page *pages,unsigned count) {
    if(!pages||!count||count>kMaxPages)return false;
    for(unsigned i=0;i<count;++i) {
        const Page &p=pages[i];
        if(p.ordinal!=i||p.scene>0xffffu||!p.count||p.count>kSamplesPerPage||p.flags&~QFT||
           !p.firstFrame||p.lastFrame<p.firstFrame||p.count-1>p.lastFrame-p.firstFrame||
           ((p.flags&QFT)?p.lastQf<p.firstQf:(p.firstQf||p.lastQf)))return false;
        if(!i) { if(p.segment)return false;continue; }
        const Page &prior=pages[i-1];
        if(p.firstFrame<=prior.lastFrame||p.segment<prior.segment||p.segment-prior.segment>1)return false;
        if(p.segment==prior.segment&&(!same(identity(p),identity(prior))||p.flags!=prior.flags||
            ((p.flags&QFT)&&p.firstQf<prior.lastQf)))return false;
    }
    return true;
}
bool validPage(const Page &p,const void *data,unsigned bytes) {
    if(!data||!p.count||p.count>kSamplesPerPage||bytes!=p.count*sizeof(Sample)||
       (reinterpret_cast<Address>(data)&3u)||p.flags&~QFT||hash(data,bytes)!=p.hash)return false;
    const Sample *samples=static_cast<const Sample*>(data);
    for(unsigned i=0;i<p.count;++i) {
        const Sample &s=samples[i];
        if(!valid(s)||(s.flags&QFT)!=p.flags)return false;
        if(i&&(s.frame<=samples[i-1].frame||((p.flags&QFT)&&s.qf<samples[i-1].qf)))return false;
    }
    return samples[0].frame==p.firstFrame&&samples[p.count-1].frame==p.lastFrame&&
        samples[0].qf==p.firstQf&&samples[p.count-1].qf==p.lastQf;
}
bool locate(const Page *pages,unsigned count,Query q,Needed &out) {
    if(!pages||!count||count>kMaxPages||(q.clock!=QF_CLOCK&&q.clock!=FRAME_CLOCK))return false;
    unsigned lo=0,hi=count;
    while(lo<hi) { const unsigned mid=lo+(hi-lo)/2;if(pages[mid].segment<q.segment)lo=mid+1;else hi=mid; }
    const unsigned first=lo;
    if(first==count||pages[first].segment!=q.segment||(q.clock==QF_CLOCK&&!(pages[first].flags&QFT)))return false;
    hi=count;
    while(lo<hi) { const unsigned mid=lo+(hi-lo)/2;if(pages[mid].segment<=q.segment)lo=mid+1;else hi=mid; }
    const unsigned end=lo;lo=first;hi=end;
    while(lo<hi) { const unsigned mid=lo+(hi-lo)/2;if(firstKey(pages[mid],q.clock)<=q.time)lo=mid+1;else hi=mid; }
    out.first=lo==first?first:lo-1;out.second=out.first;
    if(q.time>=firstKey(pages[out.first],q.clock)&&out.first+1<end)out.second=out.first+1;
    return true;
}
bool bracket(Query q,const Page &a,const Sample *as,const Page &b,const Sample *bs,Bracket &out) {
    if(!as||!bs||!a.count||a.count>kSamplesPerPage||!b.count||b.count>kSamplesPerPage||
       a.segment!=q.segment||b.segment!=q.segment||(q.clock!=QF_CLOCK&&q.clock!=FRAME_CLOCK)||
       (q.clock==QF_CLOCK&&(!(a.flags&QFT)||!(b.flags&QFT)))||
       !(b.ordinal==a.ordinal||b.ordinal==a.ordinal+1))return false;
    unsigned lo=0,hi=a.count;
    while(lo<hi) { const unsigned mid=lo+(hi-lo)/2;if(key(as[mid],q.clock)<=q.time)lo=mid+1;else hi=mid; }
    if(!lo) { out={as,as,0.0f,q.time<key(as[0],q.clock)};return true; }
    const Sample *before=as+lo-1,*after=before;
    if(lo<a.count)after=as+lo;
    else if(a.ordinal!=b.ordinal)after=bs;
    const unsigned start=key(*before,q.clock),end=key(*after,q.clock);
    if(q.time>=end) { out={after,after,0.0f,q.time>end};return true; }
    // Missing poses and capture-frame gaps are discontinuities, not paths through the origin.
    const bool contiguous=(before->flags&POSE)&&(after->flags&POSE)&&after->frame==before->frame+1;
    const float alpha=contiguous&&end>start?float(q.time-start)/float(end-start):0.0f;
    out={before,contiguous?after:before,alpha,q.time>lastKey(b,q.clock)};return true;
}
}
