#include "susamune/ghost_trace_stream.hxx"

namespace GhostTraceStream {
namespace {
namespace A=GhostArena;
namespace F=GhostTraceReader;
namespace D=GhostTraceDecode;
namespace I=GhostTraceIo;
unsigned word(const unsigned char *p) { return unsigned(p[0])<<24|unsigned(p[1])<<16|unsigned(p[2])<<8|p[3]; }
bool separate(const void *a,unsigned an,const void *b,unsigned bn) {
    const A::Address x=reinterpret_cast<A::Address>(a),y=reinterpret_cast<A::Address>(b);
    return x && y && an<=A::Address(-1)-x && bn<=A::Address(-1)-y && !A::overlaps(x,an,y,bn);
}
bool outside(const A::Arena &arena,const void *data,unsigned bytes) {
    for(unsigned i=0;i<arena.banks;++i)if(!separate(data,bytes,arena.bank[i].data,arena.bank[i].bytes))return false;
    return true;
}
bool controlOutput(const Stream &s,const void *data,unsigned bytes) {
    const I::Hooks &hooks=s.transport->hooks;
    return outside(*s.arena,data,bytes) && separate(&s,sizeof(s),data,bytes) &&
        separate(s.arena,sizeof(*s.arena),data,bytes) && separate(s.transport,sizeof(*s.transport),data,bytes) &&
        (!hooks.contextBytes || separate(hooks.context,hooks.contextBytes,data,bytes));
}
void fail(Stream &s,Error error,unsigned detail=0) {
    if(!s.error){s.error=error;s.detail=detail;}
    s.closing=1;
    if(s.transport)I::close(*s.transport,s.channel);
}
bool cleanup(Stream &s) {
    if(!s.transport)return true;
    if(s.borrowed || I::status(*s.transport,s.channel).phase!=I::CLOSED)return false;
    const A::Entry *packed=A::find(*s.arena,s.packed,A::WORKSPACE);
    if(!packed || packed->pending) {if(!s.error)s.error=OWNERSHIP;return false;}
    for(unsigned i=0;i<2;++i) {
        const A::Entry *e=A::find(*s.arena,s.slots[i].lease,A::PLAYBACK);
        if(!e || e->pending!=s.slots[i].sequence || (e->pending && e->direction!=A::READS_MEMORY)) {
            if(!s.error)s.error=OWNERSHIP;return false;
        }
    }
    for(unsigned i=0;i<2;++i) {
        Slot &slot=s.slots[i];
        if(slot.sequence)A::complete(*s.arena,slot.lease,A::PLAYBACK,slot.sequence);
        A::release(*s.arena,slot.lease,A::PLAYBACK);slot={};
    }
    A::release(*s.arena,s.packed,A::WORKSPACE);
    s.transport=nullptr;s.arena=nullptr;s.packed=A::invalid();s.pending={};
    s.current=s.fill=kNoSlot;s.decoderReady=0;return true;
}
bool initializeDecoder(Stream &s) {
    if(s.decoderReady)return true;
    if(s.identityReady!=3 || (s.constrained&&__builtin_memcmp(&s.actual,&s.expected,sizeof(s.actual)))) {fail(s,IDENTITY);return false;}
    if(!F::sameRegion(s.reader,s.game) || s.reader.run!=s.file.run) {fail(s,IDENTITY);return false;}
    if(!D::begin(s.decoder,s.reader.version,s.reader.game,s.reader.capabilities,s.required)) {
        fail(s,DECODER,s.decoder.error);return false;
    }
    s.decoderReady=1;return true;
}
bool seal(Stream &s) {
    if(!initializeDecoder(s))return false;
    if(s.fill>=2)return true;
    Slot &slot=s.slots[s.fill];
    if(!A::pin(*s.arena,slot.lease,A::PLAYBACK,s.reader.chunks,A::READS_MEMORY)) {fail(s,OWNERSHIP);return false;}
    slot.bytes=s.reader.chunkBytes;slot.sequence=s.reader.chunks;slot.ready=1;
    slot.hash=s.reader.expectedHash;slot.fileOffset=s.chunkStart;slot.fileEnd=s.reader.offset;
    slot.frame=s.reader.frame;slot.tick=s.reader.tick;slot.encodedHash=s.encodedHash;s.fill=kNoSlot;return true;
}
bool rotate(Stream &s) {
    for(unsigned i=0;i<2;++i)if(!s.slots[i].ready && s.current!=i) {
        A::Span output=A::write(*s.arena,s.slots[i].lease,A::PLAYBACK);
        if(!output.data || output.bytes!=kOutputBytes) {fail(s,OWNERSHIP);return false;}
        if(!F::releaseChunk(s.reader,output.data,output.bytes)) {fail(s,READER,s.reader.error);return false;}
        s.fill=i;return true;
    }
    return false;
}
bool accept(Stream &s) {
    const A::View data=I::view(*s.transport,s.channel);
    if(!s.pending.bytes || !data.data || data.bytes!=s.cacheBytes || s.pending.offset<s.cacheOffset ||
       s.pending.offset-s.cacheOffset>s.cacheBytes || s.pending.bytes>s.cacheBytes-(s.pending.offset-s.cacheOffset)) {fail(s,IO);return false;}
    if(s.fill>=2) {fail(s,OWNERSHIP);return false;}
    const A::Span output=A::write(*s.arena,s.slots[s.fill].lease,A::PLAYBACK),packed=A::write(*s.arena,s.packed,A::WORKSPACE);
    if(output.data!=s.reader.output || output.bytes!=kOutputBytes || packed.data!=s.reader.packed || packed.bytes!=kScratchBytes) {
        fail(s,OWNERSHIP);return false;
    }
    const A::Address target=reinterpret_cast<A::Address>(s.pending.destination);
    const A::Span destinations[]={output,packed,{s.reader.header,sizeof(s.reader.header)}};
    bool owned=false;
    for(unsigned i=0;i<3;++i) {
        const A::Address base=reinterpret_cast<A::Address>(destinations[i].data);
        if(target>=base && target-base<=destinations[i].bytes && s.pending.bytes<=destinations[i].bytes-(target-base))owned=true;
    }
    if(!owned) {fail(s,OWNERSHIP);return false;}
    const auto *source=static_cast<const unsigned char*>(data.data)+s.pending.offset-s.cacheOffset;
    if(!s.pending.offset && (word(source+16)!=s.file.nonce)) {
        fail(s,IDENTITY);return false;
    }
    __builtin_memcpy(s.pending.destination,source,s.pending.bytes);
    const unsigned bytes=s.pending.bytes,offset=s.pending.offset,chunks=s.reader.chunks;s.pending={};
    if(!F::acceptRead(s.reader,bytes)) {fail(s,READER,s.reader.error);return false;}
    if(!offset){s.actual.version=s.reader.version;s.actual.game=s.reader.game;s.actual.scene=word(source+24);
        s.actual.capabilities=s.reader.capabilities;s.actual.bytes=s.reader.fileBytes;s.actual.headerHash=word(source+60);s.observedRunFlags=word(source+36);s.identityReady|=1;}
    if(offset==s.reader.fileBytes-32&&bytes==32){s.actual.chunks=s.reader.expectedChunks;
        s.actual.footerHash=MsTraceHash(2166136261u,source,32);s.identityReady|=2;
        if(s.constrained&&__builtin_memcmp(&s.actual,&s.expected,sizeof(s.actual))){fail(s,IDENTITY);return false;}}
    if(s.reader.chunks!=chunks){s.chunkStart=offset;s.encodedHash=MsTraceHash(2166136261u,source,bytes);}
    else if(s.reader.chunks&&offset>s.chunkStart&&offset<s.reader.fileBytes-32)s.encodedHash=MsTraceHash(s.encodedHash,source,bytes);
    return true;
}
}
bool open(Stream &s,I::Transport &transport,unsigned channel,I::File file,unsigned game,unsigned required) {
    if(s.transport || !transport.arena || channel>=MS_TRACE_READ_CHANNELS ||
       I::status(transport,channel).phase!=I::CLOSED ||
       (game!=0x474d534au && game!=0x474d5345u && game!=0x474d5350u) ||
       file.region!=(game==0x474d534au?MS_TRACE_READ_JP:game==0x474d5345u?MS_TRACE_READ_US:MS_TRACE_READ_PAL) ||
       !outside(*transport.arena,&s,sizeof(s)) || !separate(&s,sizeof(s),&transport,sizeof(transport)) ||
       !separate(&s,sizeof(s),transport.arena,sizeof(*transport.arena)))return false;
    A::Handle leases[3];
    leases[0]=A::acquire(*transport.arena,A::PLAYBACK,kOutputBytes);
    leases[1]=A::acquire(*transport.arena,A::PLAYBACK,kOutputBytes);
    leases[2]=A::acquire(*transport.arena,A::WORKSPACE,kScratchBytes);
    if(!A::find(*transport.arena,leases[0],A::PLAYBACK) || !A::find(*transport.arena,leases[1],A::PLAYBACK) ||
       !A::find(*transport.arena,leases[2],A::WORKSPACE) || !I::open(transport,channel,file)) {
        A::release(*transport.arena,leases[0],A::PLAYBACK);A::release(*transport.arena,leases[1],A::PLAYBACK);
        A::release(*transport.arena,leases[2],A::WORKSPACE);return false;
    }
    const unsigned ticket=s.ticket;s={};s.ticket=ticket;s.transport=&transport;s.arena=transport.arena;
    s.file=file;s.game=game;s.required=required;s.channel=channel;s.current=kNoSlot;
    s.slots[0].lease=leases[0];s.slots[1].lease=leases[1];s.packed=leases[2];return true;
}
Phase poll(Stream &s,unsigned budget) {
    if(!s.transport)return status(s).phase;
    if(!budget)budget=1;
    if(budget>16)budget=16;
    for(unsigned step=0;step<budget;++step) {
        I::poll(*s.transport,s.channel);
        const I::Status io=I::status(*s.transport,s.channel);
        if(s.closing) {cleanup(s);break;}
        if(io.error==I::REMOTE || io.error==I::OWNERSHIP || io.error==I::BOOT_CHANGED || io.phase==I::BLOCKED) {
            fail(s,IO,io.error==I::REMOTE?io.remoteStatus:unsigned(io.error));break;
        }
        if(io.pending)break;
        if(!s.initialized) {
            if(io.phase!=I::IDLE) {fail(s,IO,io.error);break;}
            const A::Span output=A::write(*s.arena,s.slots[0].lease,A::PLAYBACK),packed=A::write(*s.arena,s.packed,A::WORKSPACE);
            if(!output.data || !packed.data) {fail(s,OWNERSHIP);break;}
            if(!F::begin(s.reader,io.fileBytes,output.data,output.bytes,packed.data,packed.bytes)) {fail(s,READER,s.reader.error);break;}
            s.initialized=1;
        }
        if(io.phase==I::READY && s.pending.bytes && !accept(s))break;
        if(s.ended)break;
        const F::Status state=F::status(s.reader);
        if(state==F::FAILED) {fail(s,READER,s.reader.error);break;}
        if(state==F::COMPLETE) {
            if(s.limit.chunk){fail(s,IDENTITY);break;}
            if(!initializeDecoder(s))break;
            s.ended=1;I::close(*s.transport,s.channel);break;
        }
        if(state==F::CHUNK_READY){
            if(s.limit.chunk&&s.reader.chunks==s.limit.chunk){
                const Limit&l=s.limit;
                if(s.reader.chunkBytes!=l.bytes||s.reader.expectedHash!=l.hash||s.chunkStart!=l.fileOffset||s.reader.offset!=l.fileEnd||
                   s.reader.frame!=l.frame||s.reader.tick!=l.tick||s.actual.headerHash!=l.headerHash){fail(s,IDENTITY);break;}
                if(!seal(s))break;s.ended=1;I::close(*s.transport,s.channel);break;
            }
            if(!seal(s)||!rotate(s))break;
        }
        if(!F::nextRead(s.reader,s.pending)) {fail(s,READER,s.reader.error);break;}
        if(s.pending.bytes>kScratchBytes || s.pending.offset>=s.reader.fileBytes) {fail(s,READER);break;}
        if(I::status(*s.transport,s.channel).phase==I::READY) {
            if(s.pending.offset>=s.cacheOffset && s.pending.offset-s.cacheOffset<=s.cacheBytes &&
               s.pending.bytes<=s.cacheBytes-(s.pending.offset-s.cacheOffset)) {
                if(!accept(s))break;
                continue;
            }
            if(!I::consume(*s.transport,s.channel)) {fail(s,IO);break;}
        }
        // Retain a checked transport view for tiny headers and adjacent compressed blocks.
        s.cacheOffset=s.pending.offset;s.cacheBytes=s.reader.fileBytes-s.pending.offset;
        if(s.cacheBytes>kScratchBytes)s.cacheBytes=kScratchBytes;
        if(!I::read(*s.transport,s.channel,s.cacheOffset,s.cacheBytes)) {
            fail(s,IO,I::status(*s.transport,s.channel).error);break;
        }
    }
    return status(s).phase;
}
Status status(const Stream &s) {
    unsigned buffered=0;for(unsigned i=0;i<2;++i)buffered+=s.slots[i].ready!=0;
    const I::Status io=s.transport?I::status(*s.transport,s.channel):I::Status{};
    const Phase phase=s.error?FAILED:!s.transport?CLOSED:s.closing?DRAINING:
        s.ended && !buffered && s.current==kNoSlot && !s.borrowed?FINISHED:!s.initialized?OPENING:STREAMING;
    return {phase,s.error,s.detail,s.reader.fileBytes,s.reader.chunks,buffered,s.borrowed!=0,io.pending};
}
Result nextEvent(Stream &s,D::Event &event,unsigned &ticket) {
    if(s.borrowed)return BORROWED;
    if(s.mode==2)return ERROR;s.mode=1;
    if(!s.transport || s.error || s.closing)return ERROR;
    if(!controlOutput(s,&event,sizeof(event)) || !controlOutput(s,&ticket,sizeof(ticket)) ||
       !separate(&event,sizeof(event),&ticket,sizeof(ticket)))return ERROR;
    for(unsigned step=0;step<3;++step) {
        if(s.current==kNoSlot) {
            unsigned chosen=kNoSlot;
            for(unsigned i=0;i<2;++i)if(s.slots[i].ready && (chosen==kNoSlot || s.slots[i].sequence<s.slots[chosen].sequence))chosen=i;
            if(chosen==kNoSlot)return s.ended?END:WAIT;
            const A::View chunk=A::read(*s.arena,s.slots[chosen].lease,A::PLAYBACK);
            if(!chunk.data || !D::pushChunk(s.decoder,chunk.data,s.slots[chosen].bytes)) {
                fail(s,chunk.data?DECODER:OWNERSHIP,s.decoder.error);return ERROR;
            }
            s.current=chosen;
        }
        const D::Result decoded=D::next(s.decoder,event);
        if(decoded==D::FAILED) {fail(s,DECODER,s.decoder.error);return ERROR;}
        if(decoded==D::EVENT) {
            if(s.ticket==~0u) {fail(s,EXHAUSTED);return ERROR;}
            if(event.type==D::CONTINUATION)s.observedRunFlags|=event.continuation.runFlags;
            if(event.type==D::PROVENANCE)s.observedRunFlags|=event.runFlags;
            s.recordStart=event.offset;ticket=s.borrowed=++s.ticket;return EVENT;
        }
        Slot &slot=s.slots[s.current];
        if(!A::complete(*s.arena,slot.lease,A::PLAYBACK,slot.sequence)) {fail(s,OWNERSHIP);return ERROR;}
        slot.ready=slot.sequence=slot.bytes=0;s.current=kNoSlot;
    }
    return WAIT;
}
bool releaseEvent(Stream &s,unsigned ticket) {
    if(s.mode!=1||!ticket || ticket!=s.borrowed)return false;
    s.borrowed=0;
    if(s.closing)cleanup(s);
    return true;
}
bool cursor(const Stream &s,unsigned ticket,Cursor &out) {
    if(!s.transport || !ticket || s.borrowed!=ticket || s.current>=2 ||
       !controlOutput(s,&out,sizeof(out)))return false;
    const Slot &slot=s.slots[s.current];
    out={s.file,slot.sequence,slot.bytes,slot.hash,slot.fileOffset,slot.fileEnd,
        s.recordStart,s.decoder.offset,s.decoder.frame,s.decoder.tick,slot.encodedHash};return true;
}
bool constrain(Stream&s,const MsTraceFileIdentity&expected,const Limit&limit){
    if(!s.transport||s.initialized||s.borrowed||expected.game!=s.game||expected.bytes<96||expected.bytes>MS_TRACE_FILE_LIMIT||
       !expected.version||expected.version>3||(expected.capabilities&0xff000000u)||expected.chunks>(expected.bytes-96)/32)return false;
    if(limit.chunk&&(!limit.bytes||limit.bytes>kOutputBytes||limit.chunk>expected.chunks||limit.fileOffset<64||
       limit.fileEnd<=limit.fileOffset||limit.fileEnd>expected.bytes-32||limit.headerHash!=expected.headerHash))return false;
    s.expected=expected;s.limit=limit;s.constrained=1;return true;
}
unsigned runFlags(const Stream&s){return s.observedRunFlags;}
bool identity(const Stream&s,MsTraceFileIdentity&out){
    if(!s.transport||s.identityReady!=3||s.error||!controlOutput(s,&out,sizeof(out)))return false;out=s.actual;return true;
}
Result nextChunk(Stream&s,A::View&out,Cursor&where,unsigned&ticket){
    if(s.borrowed)return BORROWED;
    if(!s.transport||s.error||s.closing||s.mode==1)return ERROR;
    if(!controlOutput(s,&out,sizeof(out))||!controlOutput(s,&where,sizeof(where))||!controlOutput(s,&ticket,sizeof(ticket))||
       !separate(&out,sizeof(out),&where,sizeof(where))||!separate(&out,sizeof(out),&ticket,sizeof(ticket))||
       !separate(&where,sizeof(where),&ticket,sizeof(ticket)))return ERROR;
    s.mode=2;unsigned chosen=kNoSlot;
    for(unsigned i=0;i<2;++i)if(s.slots[i].ready&&(chosen==kNoSlot||s.slots[i].sequence<s.slots[chosen].sequence))chosen=i;
    if(chosen==kNoSlot)return s.ended?END:WAIT;
    const Slot&slot=s.slots[chosen];out=A::read(*s.arena,slot.lease,A::PLAYBACK);
    if(!out.data||s.ticket==~0u){fail(s,OWNERSHIP);return ERROR;}
    if(!D::pushChunk(s.decoder,out.data,slot.bytes)){fail(s,DECODER,s.decoder.error);return ERROR;}
    D::Event checked;D::Result decoded;
    while((decoded=D::next(s.decoder,checked))==D::EVENT){if(checked.type==D::CONTINUATION)s.observedRunFlags|=checked.continuation.runFlags;if(checked.type==D::PROVENANCE)s.observedRunFlags|=checked.runFlags;}
    if(decoded==D::FAILED){fail(s,DECODER,s.decoder.error);return ERROR;}
    out.bytes=slot.bytes;s.current=chosen;
    where={s.file,slot.sequence,slot.bytes,slot.hash,slot.fileOffset,slot.fileEnd,0,slot.bytes,slot.frame,slot.tick,slot.encodedHash};ticket=s.borrowed=++s.ticket;return EVENT;
}
bool releaseChunk(Stream&s,unsigned ticket){
    if(s.mode!=2||!ticket||s.borrowed!=ticket||s.current>=2)return false;Slot&slot=s.slots[s.current];
    if(!A::complete(*s.arena,slot.lease,A::PLAYBACK,slot.sequence)){fail(s,OWNERSHIP);return false;}
    slot.ready=slot.sequence=slot.bytes=0;s.current=kNoSlot;s.borrowed=0;if(s.closing)cleanup(s);return true;
}
bool close(Stream &s) {
    if(!s.transport)return true;
    s.closing=1;
    if(!I::close(*s.transport,s.channel))return false;
    return cleanup(s);
}
bool cancel(Stream &s) { if(s.transport && !s.error)s.error=CANCELLED;return close(s); }
}
