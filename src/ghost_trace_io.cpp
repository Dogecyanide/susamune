#include "susamune/state_save_probe.hxx"
#include "susamune/ghost_trace_io.hxx"

namespace GhostTraceIo {
namespace {
using GhostArena::Address;
const GhostArena::Owner kOwner=GhostArena::WORKSPACE;
bool span(const void *p,unsigned bytes) {
    const Address a=reinterpret_cast<Address>(p);return a && bytes && bytes<=Address(-1)-a;
}
bool separate(const void *a,unsigned an,const void *b,unsigned bn) {
    if(!bn)return true;
    const Address x=reinterpret_cast<Address>(a),y=reinterpret_cast<Address>(b);
    return span(a,an)&&span(b,bn)&&(x<=y?an<=y-x:bn<=x-y);
}
bool configured(const Transport &t,unsigned channel) {
    return t.arena && t.bootNonce && channel<MS_TRACE_READ_CHANNELS;
}
const GhostArena::Entry *entry(const Transport &t,const Channel &c) {
    return GhostArena::find(*t.arena,c.lease,kOwner);
}
void invalidate(const Transport &t,void *p,unsigned bytes) {t.hooks.invalidate(t.hooks.context,p,bytes);}
void flush(const Transport &t,const void *p,unsigned bytes) {t.hooks.flush(t.hooks.context,p,bytes);}
MsTraceReadResponse response(const Transport &t,unsigned channel) {
    volatile MsTraceReadResponse *source=&t.mailboxes[channel]->response;
    invalidate(t,const_cast<MsTraceReadResponse*>(source),sizeof(*source));
    MsTraceReadResponse result;unsigned *to=reinterpret_cast<unsigned*>(&result);
    const volatile unsigned *from=reinterpret_cast<const volatile unsigned*>(source);
    for(unsigned i=0;i<8;++i)to[i]=from[i];
    return result;
}
bool release(Transport &t,Channel &c) {
    if(!GhostArena::release(*t.arena,c.lease,kOwner)){c.error=OWNERSHIP;c.phase=BLOCKED;return false;}
    c.lease=GhostArena::invalid();c.operation=c.readyBytes=c.cancel=c.fileBytes=0;c.phase=CLOSED;return true;
}
bool submit(Transport &t,unsigned channel,unsigned operation,unsigned offset=0,unsigned bytes=0) {
    Channel &c=t.channels[channel];
    const GhostArena::Span buffer=GhostArena::write(*t.arena,c.lease,kOwner);
    if(!buffer.data || buffer.bytes!=t.scratchBytes){c.error=OWNERSHIP;return false;}
    if(c.sequence==~0u){c.error=EXHAUSTED;return false;}
    const unsigned capacity=(bytes+31u)&~31u;
    unsigned physical=0;
    if(operation==MS_TRACE_READ_DATA && (!t.hooks.physical(t.hooks.context,c.lease,{buffer.data,capacity},physical) ||
        !physical || (physical&31u) || capacity>~0u-physical)){c.error=TRANSLATION;return false;}
    const unsigned next=c.sequence+1;
    if(!GhostArena::pin(*t.arena,c.lease,kOwner,next,GhostArena::WRITES_MEMORY)){c.error=OWNERSHIP;return false;}
    c.sequence=next;c.operation=operation;c.bytes=bytes;c.capacity=capacity;c.physical=physical;c.readyBytes=0;
    c.error=c.failedStatus?REMOTE:NONE;c.remoteStatus=c.failedStatus;
    c.phase=operation==MS_TRACE_READ_OPEN?OPENING:operation==MS_TRACE_READ_DATA?READING:CLOSING;
    if(capacity){flush(t,buffer.data,capacity);invalidate(t,buffer.data,capacity);}
    volatile MsTraceReadMailbox *m=t.mailboxes[channel];
    m->request.sequence=0;flush(t,const_cast<MsTraceReadRequest*>(&m->request),32);
    const MsTraceReadRequest q={MS_TRACE_READ_MAGIC,MS_TRACE_READ_VERSION,t.bootNonce,0,operation,c.file.nonce,c.file.run,c.file.region};
    const MsTraceReadBuffer b={physical,capacity,bytes,c.lease.serial,offset,{0,0,0}};
    volatile unsigned *to=reinterpret_cast<volatile unsigned*>(m);
    const unsigned *from=reinterpret_cast<const unsigned*>(&q);
    for(unsigned i=0;i<8;++i)to[i]=from[i];
    from=reinterpret_cast<const unsigned*>(&b);
    for(unsigned i=0;i<8;++i)to[8+i]=from[i];
    flush(t,const_cast<MsTraceReadMailbox*>(m),64);
    m->request.sequence=next;flush(t,const_cast<MsTraceReadRequest*>(&m->request),32);
    return true;
}
}
bool configure(Transport &t,GhostArena::Arena &arena,const Hooks &hooks,unsigned nonce,unsigned scratchBytes) {
    if(!nonce || !GhostArena::configured(arena) || !scratchBytes || scratchBytes>MS_TRACE_READ_MAX_BYTES || (scratchBytes&31u) ||
        !hooks.mailbox || !hooks.flush || !hooks.invalidate || !hooks.physical ||
        (hooks.context && !span(hooks.context,hooks.contextBytes)) || (!hooks.context && hooks.contextBytes) ||
        !separate(&t,sizeof(t),&arena,sizeof(arena)) || !separate(&t,sizeof(t),hooks.context,hooks.contextBytes))return false;
    for(unsigned i=0;i<MS_TRACE_READ_CHANNELS;++i)
        if(t.channels[i].lease.serial || t.channels[i].operation)return false;
    volatile MsTraceReadMailbox *mailboxes[MS_TRACE_READ_CHANNELS];
    for(unsigned i=0;i<MS_TRACE_READ_CHANNELS;++i){
        mailboxes[i]=hooks.mailbox(hooks.context,i);
        const void *m=const_cast<const MsTraceReadMailbox*>(mailboxes[i]);
        if((reinterpret_cast<Address>(m)&31u) || !span(m,128) || !separate(m,128,&t,sizeof(t)) ||
            !separate(m,128,&arena,sizeof(arena)) || !separate(m,128,hooks.context,hooks.contextBytes))return false;
        for(unsigned j=0;j<i;++j)if(!separate(m,128,const_cast<const MsTraceReadMailbox*>(mailboxes[j]),128))return false;
    }
    for(unsigned i=0;i<arena.banks;++i){
        const GhostArena::Span b=arena.bank[i];
        if(!separate(b.data,b.bytes,&t,sizeof(t)) || !separate(b.data,b.bytes,hooks.context,hooks.contextBytes))return false;
        for(unsigned j=0;j<MS_TRACE_READ_CHANNELS;++j)
            if(!separate(b.data,b.bytes,const_cast<const MsTraceReadMailbox*>(mailboxes[j]),128))return false;
    }
    t.hooks=hooks;t.arena=&arena;t.bootNonce=nonce;t.scratchBytes=scratchBytes;
    for(unsigned i=0;i<MS_TRACE_READ_CHANNELS;++i){
        t.mailboxes[i]=mailboxes[i];const unsigned sequence=t.channels[i].sequence;
        t.channels[i]={};t.channels[i].sequence=sequence;t.channels[i].lease=GhostArena::invalid();t.channels[i].phase=CLOSED;
    }
    return true;
}
bool open(Transport &t,unsigned channel,File file) {
    if(StateSaveProbe::enabled())return false;
    if(!configured(t,channel))return false;
    Channel &c=t.channels[channel];
    if(c.phase!=CLOSED || c.lease.serial || !file.nonce || !file.run || file.region<MS_TRACE_READ_JP || file.region>MS_TRACE_READ_PAL){c.error=ARGUMENT;return false;}
    const MsTraceReadResponse r=response(t,channel);
    if(r.magic!=MS_TRACE_READ_MAGIC || r.version!=MS_TRACE_READ_VERSION || r.bootNonce!=t.bootNonce){c.error=NOT_READY;return false;}
    if(r.ack>c.sequence)c.sequence=r.ack;
    if(c.sequence==~0u){c.error=EXHAUSTED;return false;}
    c.lease=GhostArena::acquire(*t.arena,kOwner,t.scratchBytes);
    if(!entry(t,c)){c.error=OWNERSHIP;return false;}
    c.file=file;c.fileBytes=0;c.cancel=c.failedStatus=0;
    if(submit(t,channel,MS_TRACE_READ_OPEN))return true;
    release(t,c);return false;
}
bool read(Transport &t,unsigned channel,unsigned offset,unsigned bytes) {
    if(!configured(t,channel))return false;
    Channel &c=t.channels[channel];
    if(c.phase!=IDLE || !bytes || bytes>t.scratchBytes || offset>c.fileBytes || bytes>c.fileBytes-offset){c.error=ARGUMENT;return false;}
    return submit(t,channel,MS_TRACE_READ_DATA,offset,bytes);
}
Phase poll(Transport &t,unsigned channel) {
    if(!configured(t,channel))return UNCONFIGURED;
    Channel &c=t.channels[channel];if(!c.operation)return c.phase;
    const GhostArena::Entry *e=entry(t,c);
    if(!e || e->pending!=c.sequence || e->direction!=GhostArena::WRITES_MEMORY){c.error=OWNERSHIP;return c.phase;}
    const MsTraceReadResponse r=response(t,channel);
    if(r.magic!=MS_TRACE_READ_MAGIC || r.version!=MS_TRACE_READ_VERSION){c.error=BAD_ACK;return c.phase;}
    if(r.bootNonce!=t.bootNonce){c.error=BOOT_CHANGED;return c.phase;}
    if(r.ack!=c.sequence){if(r.ack>c.sequence)c.error=BAD_ACK;return c.phase;}
    if(r.lease!=c.lease.serial || r.status>MS_TRACE_READ_DESTINATION ||
        (r.status==MS_TRACE_READ_OK?(r.bytes!=c.bytes ||
            (c.operation==MS_TRACE_READ_OPEN?(r.fileSize<96 || r.fileSize>MS_TRACE_FILE_LIMIT):
             r.fileSize!=(c.operation==MS_TRACE_READ_CLOSE?0:c.fileBytes))):
            (r.bytes || (r.fileSize && (c.operation==MS_TRACE_READ_OPEN?r.fileSize>MS_TRACE_FILE_LIMIT:r.fileSize!=c.fileBytes))))){c.error=BAD_ACK;return c.phase;}
    if(c.capacity)invalidate(t,e->span.data,c.capacity);
    if(!GhostArena::complete(*t.arena,c.lease,kOwner,c.sequence)){c.error=OWNERSHIP;return c.phase;}
    const unsigned operation=c.operation;c.operation=0;
    if(r.status && !c.failedStatus)c.failedStatus=r.status;
    c.error=c.failedStatus?REMOTE:NONE;c.remoteStatus=c.failedStatus;
    if(r.status){
        // IO can also mean close failed before a file size was known. Confirm
        // closure explicitly instead of treating an error's zero size as proof.
        if(!r.fileSize && r.status!=MS_TRACE_READ_IO){release(t,c);return c.phase;}
        if(operation==MS_TRACE_READ_CLOSE){c.phase=BLOCKED;c.readyBytes=0;c.cancel=0;return c.phase;}
        if(operation==MS_TRACE_READ_OPEN)c.fileBytes=r.fileSize;
        c.cancel=1;if(!submit(t,channel,MS_TRACE_READ_CLOSE))c.phase=BLOCKED;return c.phase;
    }
    if(operation==MS_TRACE_READ_CLOSE){release(t,c);return c.phase;}
    c.fileBytes=r.fileSize;
    if(c.cancel){if(!submit(t,channel,MS_TRACE_READ_CLOSE))c.phase=BLOCKED;return c.phase;}
    c.readyBytes=operation==MS_TRACE_READ_DATA?r.bytes:0;c.phase=c.readyBytes?READY:IDLE;return c.phase;
}
Status status(const Transport &t,unsigned channel) {
    if(!configured(t,channel))return {UNCONFIGURED,channel<MS_TRACE_READ_CHANNELS?NONE:ARGUMENT,0,0,0,false};
    const Channel &c=t.channels[channel];return {c.phase,c.error,c.remoteStatus,c.fileBytes,c.sequence,c.operation!=0};
}
GhostArena::View view(const Transport &t,unsigned channel) {
    if(!configured(t,channel))return {};
    const Channel &c=t.channels[channel];
    if(c.phase!=READY || c.operation || c.cancel || c.error || !c.readyBytes)return {};
    const GhostArena::View v=GhostArena::read(*t.arena,c.lease,kOwner);
    return v.data && v.bytes==t.scratchBytes && c.readyBytes<=v.bytes?GhostArena::View{v.data,c.readyBytes}:GhostArena::View{};
}
bool consume(Transport &t,unsigned channel) {
    if(!view(t,channel).data)return false;
    Channel &c=t.channels[channel];c.readyBytes=0;c.phase=IDLE;return true;
}
bool close(Transport &t,unsigned channel) {
    if(!configured(t,channel))return false;
    Channel &c=t.channels[channel];
    if(c.phase==CLOSED)return true;
    if(!entry(t,c)){c.error=OWNERSHIP;return false;}
    c.cancel=1;c.readyBytes=0;
    if(c.operation)return true;
    return submit(t,channel,MS_TRACE_READ_CLOSE);
}
bool abandon(Transport &t,unsigned channel) {
    if(!configured(t,channel))return false;
    Channel &c=t.channels[channel];if(c.phase==CLOSED)return true;
    const GhostArena::Entry *e=entry(t,c);
    if(!e || !t.hooks.quiescent || !t.hooks.quiescent(t.hooks.context,channel,t.bootNonce,c.lease.serial,c.sequence))return false;
    if(e->pending){
        if(!c.operation || e->pending!=c.sequence || e->direction!=GhostArena::WRITES_MEMORY)return false;
        invalidate(t,e->span.data,e->span.bytes);
        if(!GhostArena::complete(*t.arena,c.lease,kOwner,c.sequence))return false;
    }else if(c.operation)return false;
    c.error=CANCELLED;return release(t,c);
}
}
