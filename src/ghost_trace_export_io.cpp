#include "susamune/ghost_trace_export_io.hxx"
namespace GhostTraceExportIo {
namespace {
namespace A=GhostArena;
bool separate(const void*a,unsigned an,const void*b,unsigned bn){const auto x=reinterpret_cast<A::Address>(a),y=reinterpret_cast<A::Address>(b);return x&&y&&an<=A::Address(-1)-x&&bn<=A::Address(-1)-y&&!A::overlaps(x,an,y,bn);}
void invalidate(Client&c,volatile void*p,unsigned bytes){c.hooks.invalidate(c.hooks.context,const_cast<void*>(p),bytes);}
void flush(Client&c,volatile void*p,unsigned bytes){c.hooks.flush(c.hooks.context,const_cast<void*>(p),bytes);}
bool response(Client&c,MsTraceExportResponse&r){invalidate(c,&c.hooks.mailbox->response,32);__builtin_memcpy(&r,const_cast<const MsTraceExportResponse*>(&c.hooks.mailbox->response),32);
    return r.magic==MS_TRACE_EXPORT_MAGIC&&r.version==MS_TRACE_EXPORT_VERSION&&r.bootNonce==c.bootNonce;}
bool issue(Client&c,unsigned op,unsigned bytes,unsigned adler,unsigned flags){
    if(c.operation)return false;auto&box=*c.hooks.mailbox;MsTraceExportResponse r;
    if(!response(c,r))return false;invalidate(c,&box.request,32);
    if(r.ack!=box.request.sequence||r.ack==~0u)return false;
    const unsigned sequence=r.ack+1;MsTraceExportTransfer b={};A::Span out=A::write(c.arena,c.lease,A::WORKSPACE);
    if(bytes){
        unsigned physical=0;if(!out.data||out.bytes!=MS_TRACE_EXPORT_BUFFER_BYTES||!c.hooks.physical(c.hooks.context,out,physical)||physical!=MS_TRACE_EXPORT_BUFFER_PHYS)return false;
        b={physical,out.bytes,bytes,c.lease.serial,MsTraceHash(2166136261u,out.data,bytes),c.bytes,adler,flags};
        const auto direction=op==MS_TRACE_EXPORT_COMMIT?A::WRITES_MEMORY:A::READS_MEMORY;
        if(!A::pin(c.arena,c.lease,A::WORKSPACE,sequence,direction))return false;
        flush(c,out.data,op==MS_TRACE_EXPORT_COMMIT?out.bytes:(bytes+31u)&~31u);
    }else b.flags=flags;
    MsTraceExportRequest q={MS_TRACE_EXPORT_MAGIC,MS_TRACE_EXPORT_VERSION,c.bootNonce,0,op,c.nonce,c.run,c.game};
    __builtin_memcpy(const_cast<MsTraceExportRequest*>(&box.request),&q,32);__builtin_memcpy(const_cast<MsTraceExportTransfer*>(&box.transfer),&b,32);
    flush(c,&box.request,64);c.canceled=false;c.sequence=sequence;c.operation=op;c.pendingBytes=bytes;c.pendingAdler=adler;c.phase=WAITING;
    box.request.sequence=sequence;flush(c,&box.request,32);return true;
}
}
bool configure(Client&c,const Hooks&h,unsigned nonce){
    if(c.operation||A::find(c.arena,c.lease,A::WORKSPACE)||!nonce||!h.mailbox||!h.flush||!h.invalidate||!h.physical||
       !A::validSpan(h.buffer)||h.buffer.bytes!=MS_TRACE_EXPORT_BUFFER_BYTES||!separate(&c,sizeof(c),h.buffer.data,h.buffer.bytes)||
       !separate(&c,sizeof(c),const_cast<const MsTraceExportMailbox*>(h.mailbox),sizeof(*h.mailbox))||
       !separate(h.buffer.data,h.buffer.bytes,const_cast<const MsTraceExportMailbox*>(h.mailbox),sizeof(*h.mailbox)))return false;
    c={};c.hooks=h;c.bootNonce=nonce;c.adler=1;MsTraceExportResponse r;if(!response(c,r)||(r.phase!=MS_TRACE_EXPORT_IDLE&&r.phase!=MS_TRACE_EXPORT_DONE&&!(r.phase==MS_TRACE_EXPORT_FAILED&&(r.status&MS_TRACE_EXPORT_NO_OWNER))))return false;
    if(!A::configure(c.arena,&h.buffer,1))return false;c.lease=A::acquire(c.arena,A::WORKSPACE,h.buffer.bytes);
    if(!A::find(c.arena,c.lease,A::WORKSPACE))return false;c.phase=IDLE;return true;
}
A::Span buffer(Client&c){return c.operation?A::Span{}:A::write(c.arena,c.lease,A::WORKSPACE);}
bool begin(Client&c,unsigned nonce,unsigned run,unsigned game,unsigned destination){
    if(c.phase!=IDLE||c.nonce||!nonce||!run||(game!=0x474d534au&&game!=0x474d5345u&&game!=0x474d5350u))return false;
    c.nonce=nonce;c.run=run;c.game=game;
    if(issue(c,MS_TRACE_EXPORT_BEGIN,(destination&MS_TRACE_EXPORT_NAMED)?MS_TRACE_EXPORT_NAME_BYTES:0,1,destination))return true;c.nonce=c.run=c.game=0;return false;
}
bool append(Client&c,unsigned bytes){
    if(c.phase!=IDLE||!c.nonce||!bytes||bytes>MS_TRACE_EXPORT_MAX_WRITE||bytes>MS_TRACE_FILE_LIMIT-c.bytes)return false;
    const A::Span out=buffer(c);if(!out.data)return false;return issue(c,MS_TRACE_EXPORT_APPEND,bytes,MsTraceAdler(c.adler,out.data,bytes),0);
}
bool commit(Client&c,unsigned finalAdler){return c.phase==IDLE&&c.nonce&&c.bytes>=96&&issue(c,MS_TRACE_EXPORT_COMMIT,64,finalAdler,0);}
Phase poll(Client&c){
    if(!c.operation)return c.phase;MsTraceExportResponse r;if(!response(c,r)||r.ack!=c.sequence)return WAITING;
    if(!r.status){
        const unsigned phase=c.operation==MS_TRACE_EXPORT_COMMIT?MS_TRACE_EXPORT_DONE:c.operation==MS_TRACE_EXPORT_ABORT?MS_TRACE_EXPORT_IDLE:MS_TRACE_EXPORT_OPEN;
        const unsigned bytes=c.operation==MS_TRACE_EXPORT_APPEND?c.bytes+c.pendingBytes:c.operation==MS_TRACE_EXPORT_BEGIN?0:c.bytes;
        if(r.phase!=phase||r.bytes!=bytes||(c.operation==MS_TRACE_EXPORT_APPEND&&r.checksum!=c.pendingAdler)||
           (c.operation==MS_TRACE_EXPORT_COMMIT&&r.checksum!=c.pendingAdler))return WAITING;
    }
    if(c.pendingBytes){
        if(c.operation==MS_TRACE_EXPORT_COMMIT)invalidate(c,c.hooks.buffer.data,c.hooks.buffer.bytes);
        if(!A::complete(c.arena,c.lease,A::WORKSPACE,c.sequence))return WAITING;
    }
    const unsigned op=c.operation;c.operation=0;
    if(r.status){c.error=r.status&~MS_TRACE_EXPORT_NO_OWNER;if(r.status&MS_TRACE_EXPORT_NO_OWNER)c.nonce=0;c.phase=FAILED;return FAILED;}
    if(op==MS_TRACE_EXPORT_APPEND){c.bytes=r.bytes;c.adler=c.pendingAdler;}
    c.phase=op==MS_TRACE_EXPORT_COMMIT?DONE:op==MS_TRACE_EXPORT_ABORT?CLOSED:IDLE;
    if(op==MS_TRACE_EXPORT_ABORT)c.nonce=0;
    if(op==MS_TRACE_EXPORT_COMMIT){invalidate(c,&c.hooks.mailbox->identity,32);__builtin_memcpy(&c.identity,const_cast<const MsTraceFileIdentity*>(&c.hooks.mailbox->identity),32);
        if(c.identity.bytes!=c.bytes||c.identity.game!=c.game){c.error=MS_TRACE_BAD_SOURCE;c.phase=FAILED;}}
    return c.phase;
}
bool close(Client&c){
    if(c.operation){
        if(!c.canceled&&c.operation!=MS_TRACE_EXPORT_ABORT){c.hooks.mailbox->transfer.flags|=MS_TRACE_EXPORT_CANCEL_FLAG;flush(c,&c.hooks.mailbox->transfer,32);c.canceled=true;}
        poll(c);if(c.operation)return false;
    }
    if(c.nonce&&c.phase!=DONE){if(issue(c,MS_TRACE_EXPORT_ABORT,0,0,0))return false;return false;}
    if(A::find(c.arena,c.lease,A::WORKSPACE)&&!A::release(c.arena,c.lease,A::WORKSPACE))return false;
    c.lease=A::invalid();c.nonce=0;c.phase=CLOSED;return true;
}
}
