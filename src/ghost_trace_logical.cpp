#include "susamune/ghost_trace_logical.hxx"
namespace GhostTraceLogical {
namespace {
namespace A=GhostArena;namespace M=GhostTraceBranchIo;namespace P=GhostTraceStream;namespace D=GhostTraceDecode;
bool separate(const void*a,unsigned an,const void*b,unsigned bn){const auto x=reinterpret_cast<A::Address>(a),y=reinterpret_cast<A::Address>(b);return x&&y&&an<=A::Address(-1)-x&&bn<=A::Address(-1)-y&&!A::overlaps(x,an,y,bn);}
bool outside(const A::Arena&a,const void*p,unsigned bytes){for(unsigned i=0;i<a.banks;++i)if(!separate(p,bytes,a.bank[i].data,a.bank[i].bytes))return false;return true;}
bool safe(const Stream&s,const void*p,unsigned bytes){return separate(&s,sizeof(s),p,bytes)&&separate(s.plan.segments,s.plan.capacity*sizeof(Segment),p,bytes)&&
    (!s.plan.hash||separate(s.plan.hash,s.plan.hashCapacity*4,p,bytes))&&separate(s.maps,sizeof(*s.maps),p,bytes);}
bool same(GhostTraceIo::File a,GhostTraceIo::File b){return a.nonce==b.nonce&&a.run==b.run&&a.region==b.region;}
unsigned bucket(GhostTraceIo::File file){unsigned h=(file.nonce^file.run)*16777619u;return (h^(h>>16)^file.region)*2246822519u;}
bool seen(const Plan&p,GhostTraceIo::File file,bool insert){
    if(!p.hash){for(unsigned i=0;i<p.count;++i)if(same(p.segments[i].file,file))return true;return false;}
    unsigned at=bucket(file)&(p.hashCapacity-1);
    for(unsigned i=0;i<p.hashCapacity;++i,at=(at+1)&(p.hashCapacity-1)){
        const unsigned value=p.hash[at];if(!value){if(insert)p.hash[at]=p.count+1;return false;}
        if(value>p.count||same(p.segments[value-1].file,file))return true;
    }return true;
}
void fail(Stream&s,Error error,unsigned detail=0){if(!s.error){s.error=error;s.detail=detail;}s.closing=1;if(s.maps)M::cancel(*s.maps);if(s.physical)P::close(*s.physical);}
bool cleanup(Stream&s){
    if(s.borrowed)return false;if(s.maps&&!M::cancel(*s.maps))return false;if(s.physical&&!P::close(*s.physical))return false;
    s.phase=s.error?FAILED:CLOSED;s.closing=0;return true;
}
bool acceptMap(Stream&s){
    const MsTraceLookup*v=M::result(*s.maps);if(!v)return false;
    if(s.plan.count>=s.plan.capacity){fail(s,CAPACITY,s.plan.count+1);return false;}
    if(v->nonce!=s.query.nonce||v->run!=s.query.run||v->file.game!=s.game||seen(s.plan,s.query,false)){fail(s,CYCLE);return false;}
    if(s.pendingCut.chunk&&(v->file.chunks<s.pendingCut.chunk||v->file.bytes<32||s.pendingCut.fileEnd>v->file.bytes-32)) {fail(s,IDENTITY);return false;}
    if(s.plan.count){const Segment&child=s.plan.segments[s.plan.count-1];
        if(v->file.capabilities!=child.identity.capabilities){fail(s,IDENTITY);return false;}}
    s.runFlags|=v->runFlags;
    Segment next={s.query,v->file,s.pendingCut};
    if(s.pendingCut.chunk&&v->file.headerHash!=s.detail){fail(s,IDENTITY);return false;}
    const bool branch=v->kind==MS_TRACE_LOOKUP_BRANCH;if(branch)s.runFlags|=MS_TRACE_CONTINUATION_RUN_FLAGS;
    if(branch&&!(v->file.capabilities&MS_TRACE_HAS_CONTINUATION)){fail(s,CONTINUATION);return false;}
    GhostTraceIo::File parent={};Cut cut={};unsigned parentHash=0;
    if(branch){const auto&b=v->branch;parent={b.parent.nonce,b.parent.run,s.query.region};
        cut={b.parent.chunk,b.parent.recordBytes,b.parent.checksum,b.fence.chunkOffset,b.fence.fileBytes,b.parent.frame,b.parent.tick};parentHash=b.fence.headerHash;
        if(s.pendingCut.chunk&&(cut.frame>s.pendingCut.frame||cut.tick>s.pendingCut.tick)){fail(s,IDENTITY);return false;}}
    if(seen(s.plan,s.query,true)){fail(s,CYCLE);return false;}s.plan.segments[s.plan.count++]=next;M::consume(*s.maps);s.requested=0;
    if(branch){
        if(s.plan.count>=s.plan.capacity){fail(s,CAPACITY,s.plan.count+1);return false;}
        if(seen(s.plan,parent,false)){fail(s,CYCLE);return false;}
        s.query=parent;s.pendingCut=cut;s.detail=parentHash;
    }else{s.index=s.plan.count-1;s.phase=OPENING;s.detail=0;}
    return true;
}
bool openSegment(Stream&s){
    const Segment&segment=s.plan.segments[s.index];const Cut&c=segment.cut;
    const P::Limit limit={c.chunk,c.bytes,c.hash,c.fileOffset,c.fileEnd,c.frame,c.tick,segment.identity.headerHash};
    if(!P::open(*s.physical,*s.transport,s.channel,segment.file,s.game,s.required))return false;
    if(!P::constrain(*s.physical,segment.identity,limit)){fail(s,IDENTITY);return false;}
    s.first=1;s.phase=READING;return true;
}
bool continuation(const Stream&s,const MsTraceContinuation&c,unsigned frame,unsigned tick){
    if(s.index+1>=s.plan.count)return true;const Segment&parent=s.plan.segments[s.index+1];
    return c.parentNonce==parent.file.nonce&&c.parentRun==parent.file.run&&c.parentChunk==parent.cut.chunk&&
        c.parentHash==parent.cut.hash&&frame==parent.cut.frame&&tick==parent.cut.tick;
}
void segmentEnded(Stream&s){
    if(s.first&&s.index+1<s.plan.count){fail(s,CONTINUATION);return;}
    s.phase=SWITCHING;P::close(*s.physical);
}
}
bool open(Stream&s,Plan plan,M::Client&maps,P::Stream&physical,GhostTraceIo::Transport&transport,unsigned channel,GhostTraceIo::File file,unsigned game,unsigned required){
    if(s.closing||s.borrowed||physical.transport||maps.phase==M::WAITING||!transport.arena||channel>=MS_TRACE_READ_CHANNELS||
       !plan.segments||!plan.capacity||plan.capacity>kMaxSegments||(reinterpret_cast<A::Address>(plan.segments)&31u)||
       (plan.hash&&((reinterpret_cast<A::Address>(plan.hash)&3u)||!plan.hashCapacity||(plan.hashCapacity&(plan.hashCapacity-1))||plan.hashCapacity>kMaxHashSlots||plan.hashCapacity<2*plan.capacity))||
       (!plan.hash&&plan.capacity>32)||file.region!=(game==0x474d534au?1u:game==0x474d5345u?2u:game==0x474d5350u?3u:0u)||!file.nonce||!file.run)return false;
    if(!outside(*transport.arena,&s,sizeof(s))||!separate(&s,sizeof(s),&physical,sizeof(physical))||
       !separate(&s,sizeof(s),&maps,sizeof(maps))||!separate(&s,sizeof(s),&transport,sizeof(transport)))return false;
    const unsigned bytes=plan.capacity*sizeof(Segment);
    if(!outside(*transport.arena,plan.segments,bytes)||!separate(&s,sizeof(s),plan.segments,bytes)||!separate(&physical,sizeof(physical),plan.segments,bytes)||
       !separate(&maps,sizeof(maps),plan.segments,bytes)||!separate(&transport,sizeof(transport),plan.segments,bytes)||
       !separate(transport.arena,sizeof(*transport.arena),plan.segments,bytes)||
       !separate(const_cast<const MsTraceBranchMailbox*>(maps.hooks.mailbox),sizeof(MsTraceBranchMailbox),plan.segments,bytes)||
       !separate(const_cast<const MsTraceLookup*>(maps.hooks.result),sizeof(MsTraceLookup),plan.segments,bytes))return false;
    if(plan.hash&&(!outside(*transport.arena,plan.hash,plan.hashCapacity*4)||!separate(plan.hash,plan.hashCapacity*4,plan.segments,bytes)||
       !separate(&s,sizeof(s),plan.hash,plan.hashCapacity*4)||!separate(&physical,sizeof(physical),plan.hash,plan.hashCapacity*4)||
       !separate(&maps,sizeof(maps),plan.hash,plan.hashCapacity*4)||!separate(&transport,sizeof(transport),plan.hash,plan.hashCapacity*4)||
       !separate(transport.arena,sizeof(*transport.arena),plan.hash,plan.hashCapacity*4)||
       !separate(const_cast<const MsTraceBranchMailbox*>(maps.hooks.mailbox),sizeof(MsTraceBranchMailbox),plan.hash,plan.hashCapacity*4)||
       !separate(const_cast<const MsTraceLookup*>(maps.hooks.result),sizeof(MsTraceLookup),plan.hash,plan.hashCapacity*4)))return false;
    if(maps.phase!=M::IDLE&&!M::cancel(maps))return false;
    s={};s.plan=plan;s.plan.count=0;if(plan.hash)__builtin_memset(plan.hash,0,plan.hashCapacity*4);
    s.maps=&maps;s.physical=&physical;s.transport=&transport;s.channel=channel;s.query=file;s.game=game;s.required=required;s.phase=RESOLVING;return true;
}
Phase poll(Stream&s,unsigned budget){
    if(s.closing){if(s.maps)M::poll(*s.maps);if(s.physical)P::poll(*s.physical,budget);cleanup(s);return status(s).phase;}
    if(s.phase==RESOLVING){
        if(!s.requested){if(!M::lookup(*s.maps,s.query.nonce,s.query.run,s.game)){if(s.maps->phase==M::FAILED)fail(s,MAP_IO,s.maps->error);return status(s).phase;}s.requested=1;}
        const auto phase=M::poll(*s.maps);if(phase==M::FAILED)fail(s,MAP_IO,s.maps->error);else if(phase==M::READY)acceptMap(s);
    }
    if(s.phase==OPENING&&!openSegment(s))fail(s,PHYSICAL);
    if(s.phase==READING){if(P::poll(*s.physical,budget)==P::FAILED)fail(s,PHYSICAL,P::status(*s.physical).detail);}
    if(s.phase==SWITCHING){P::poll(*s.physical,budget);if(P::close(*s.physical)){
        if(s.index){--s.index;s.phase=OPENING;}else s.phase=FINISHED;
    }}return status(s).phase;
}
unsigned runFlags(const Stream&s){return s.runFlags;}
Status status(const Stream&s){const bool pending=(s.maps&&s.maps->phase==M::WAITING)||(s.physical&&s.physical->transport!=nullptr);
    return {s.error?FAILED:s.closing?DRAINING:static_cast<Phase>(s.phase),s.error,s.detail,s.plan.count,s.index,s.borrowed!=0,pending};}
Result nextEvent(Stream&s,D::Event&event,unsigned&ticket){
    if(s.borrowed)return BORROWED;if(s.error||s.closing||s.mode==2)return ERROR;if(s.phase==FINISHED)return END;
    if(s.phase!=READING)return WAIT;if(!safe(s,&event,sizeof(event))||!safe(s,&ticket,sizeof(ticket)))return ERROR;s.mode=1;
    const auto result=P::nextEvent(*s.physical,event,ticket);
    if(result==P::END){segmentEnded(s);return s.error?ERROR:WAIT;}
    if(result==P::ERROR){fail(s,PHYSICAL);return ERROR;}if(result!=P::EVENT)return result==P::BORROWED?BORROWED:WAIT;
    s.borrowed=ticket;
    if(event.frame<s.lastFrame||event.tick<s.lastTick||(s.first&&s.index+1<s.plan.count&&
       (event.type!=D::CONTINUATION||!continuation(s,event.continuation,event.frame,event.tick)))){
        P::releaseEvent(*s.physical,ticket);s.borrowed=0;fail(s,CONTINUATION);return ERROR;}
    s.first=0;s.lastFrame=event.frame;s.lastTick=event.tick;if(event.type==D::CONTINUATION)s.runFlags|=event.continuation.runFlags;if(event.type==D::PROVENANCE)s.runFlags|=event.runFlags;return event.type==D::CONTINUATION?BOUNDARY:EVENT;
}
bool releaseEvent(Stream&s,unsigned ticket){if(s.mode!=1||!ticket||s.borrowed!=ticket||!P::releaseEvent(*s.physical,ticket))return false;s.borrowed=0;return true;}
Result nextChunk(Stream&s,A::View&out,P::Cursor&where,unsigned&ticket){
    if(s.borrowed)return BORROWED;if(s.error||s.closing||s.mode==1)return ERROR;if(s.phase==FINISHED)return END;
    if(s.phase!=READING)return WAIT;if(!safe(s,&out,sizeof(out))||!safe(s,&where,sizeof(where))||!safe(s,&ticket,sizeof(ticket)))return ERROR;s.mode=2;
    const auto result=P::nextChunk(*s.physical,out,where,ticket);
    if(result==P::END){segmentEnded(s);return s.error?ERROR:WAIT;}
    if(result==P::ERROR){fail(s,PHYSICAL);return ERROR;}if(result!=P::EVENT)return result==P::BORROWED?BORROWED:WAIT;s.borrowed=ticket;
    if(s.first&&s.index+1<s.plan.count){const auto*p=static_cast<const unsigned char*>(out.data);MsTraceContinuation c;
        if(out.bytes<12+MS_TRACE_CONTINUATION_BYTES||(unsigned(p[0])<<8|p[1])!=MS_TRACE_CONTINUATION||(unsigned(p[2])<<8|p[3])!=MS_TRACE_CONTINUATION_BYTES||
           !MsTraceContinuationDecode(&c,p+12,MS_TRACE_CONTINUATION_BYTES)||!continuation(s,c,MsTraceGet(p+4),MsTraceGet(p+8))){
            P::releaseChunk(*s.physical,ticket);s.borrowed=0;fail(s,CONTINUATION);return ERROR;
        }
    }
    s.first=0;s.lastFrame=where.frame;s.lastTick=where.tick;s.runFlags|=P::runFlags(*s.physical);return EVENT;
}
bool releaseChunk(Stream&s,unsigned ticket){if(s.mode!=2||!ticket||s.borrowed!=ticket||!P::releaseChunk(*s.physical,ticket))return false;s.borrowed=0;return true;}
bool close(Stream&s){s.closing=1;if(s.maps)M::cancel(*s.maps);if(s.physical)P::close(*s.physical);return cleanup(s);}
bool cancel(Stream&s){if(!s.error)s.error=CANCELLED;return close(s);}
}
