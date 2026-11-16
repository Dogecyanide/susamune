#include "susamune/ghost_trace_stream_native.hxx"
#include "susamune/ghost_memory.hxx"
#include "Dolphin/OS.h"

namespace GhostTraceStreamNative {
void publishGrant(void *,const void *,unsigned);
#if !IS_EMULATOR
namespace {
namespace A=GhostArena;
namespace I=GhostTraceIo;
volatile MsTraceReadMailbox *mailbox(void *,unsigned channel) {
    return reinterpret_cast<volatile MsTraceReadMailbox*>(MS_TRACE_READ_MAILBOX_PPC(channel));
}
bool physical(void *raw,A::Handle handle,A::Span span,unsigned &out) {
    Context &context=*static_cast<Context*>(raw);
    const A::Entry *e=A::find(*context.arena,handle,A::WORKSPACE);
    const A::Address address=reinterpret_cast<A::Address>(span.data);
    if(!e || e->span.data!=span.data || e->span.bytes!=MS_TRACE_READ_MAX_BYTES ||
       !span.bytes || span.bytes>e->span.bytes || (span.bytes&31u) ||
       (address!=MS_TRACE_STREAM_IO_PPC(0) && address!=MS_TRACE_STREAM_IO_PPC(1)))return false;
    out=static_cast<unsigned>(address)&0x7fffffffu;return true;
}
void flush(void *raw,const void *data,unsigned bytes) { publishGrant(raw,data,bytes); }
void invalidate(void *,void *data,unsigned bytes) {DCInvalidateRange(data,bytes);}
}
bool idleWriter(unsigned nonce) {
    volatile const MsTraceMailbox *box=reinterpret_cast<volatile const MsTraceMailbox*>(MS_TRACE_CONTROL_PPC);
    DCInvalidateRange(const_cast<MsTraceMailbox*>(box),sizeof(*box));
    return nonce && box->response.magic==MS_TRACE_MAGIC && box->response.version==MS_TRACE_VERSION &&
        box->response.nonce==nonce && box->request.sequence==box->response.ackRequest &&
        (box->response.phase==MS_TRACE_IDLE || box->response.phase==MS_TRACE_SAVED || box->response.phase==MS_TRACE_DISCARDED);
}
bool configure(Context &context,I::Transport &transport,A::Arena &arena,unsigned nonce) {
    if(!GhostMemory::ready() || !idleWriter(nonce))return false;
    for(unsigned i=0;i<MS_TRACE_READ_CHANNELS;++i)
        if(transport.channels[i].lease.serial || transport.channels[i].operation)return false;
    const MoonshineGhostMemoryProof *proof=reinterpret_cast<const MoonshineGhostMemoryProof*>(MOONSHINE_GHOST_PROOF_PPC_BASE);
    DCInvalidateRange(const_cast<MoonshineGhostMemoryProof*>(proof),sizeof(*proof));
    if(!MoonshineGhostMemoryProofValid(proof,proof->word[MGM_GAME]) || proof->word[MGM_NONCE]!=nonce)return false;
    const A::Span banks[]={
        {reinterpret_cast<void*>(MS_TRACE_BUFFER0_PPC),MS_TRACE_BUFFER_BYTES},
        {reinterpret_cast<void*>(MS_TRACE_BUFFER1_PPC),MS_TRACE_BUFFER_BYTES},
        {reinterpret_cast<void*>(MS_TRACE_UPPER_PPC+MS_TRACE_STREAM_PACKED_OFFSET),MS_TRACE_READ_MAX_BYTES},
        {reinterpret_cast<void*>(MS_TRACE_STREAM_IO_PPC(0)),MS_TRACE_READ_MAX_BYTES},
        {reinterpret_cast<void*>(MS_TRACE_STREAM_IO_PPC(1)),MS_TRACE_READ_MAX_BYTES}};
    if(!A::configure(arena,banks,5))return false;
    context={&arena,&transport,nonce};
    const I::Hooks hooks={&context,sizeof(context),mailbox,flush,invalidate,physical,nullptr};
    return I::configure(transport,arena,hooks,nonce);
}
#else
bool idleWriter(unsigned) {return false;}
bool configure(Context &,GhostTraceIo::Transport &,GhostArena::Arena &,unsigned) {return false;}
#endif
__attribute__((noinline)) void publishGrant(void *raw,const void *data,unsigned bytes) {
#if !IS_EMULATOR

    Context &context=*static_cast<Context*>(raw);
    for(unsigned channel=0;channel<MS_TRACE_READ_CHANNELS;++channel) {
        const volatile MsTraceReadMailbox *box=mailbox(nullptr,channel);
        if(data!=const_cast<const MsTraceReadRequest*>(&box->request) || bytes!=32 || !box->request.sequence)continue;
        volatile MsTraceReadGrant *grant=reinterpret_cast<volatile MsTraceReadGrant*>(MS_TRACE_STREAM_GRANT_PPC(channel));
        grant->sequence=0;DCFlushRange(const_cast<MsTraceReadGrant*>(grant),32);
        const I::Channel &c=context.transport->channels[channel];
        const A::Entry *e=A::find(*context.arena,c.lease,A::WORKSPACE);
        unsigned address=0;
        if(c.operation==MS_TRACE_READ_DATA && c.sequence==box->request.sequence && e &&
           e->pending==c.sequence && e->direction==A::WRITES_MEMORY && physical(raw,c.lease,e->span,address)) {
            grant->magic=MS_TRACE_STREAM_GRANT_MAGIC;grant->nonce=context.nonce;grant->lease=c.lease.serial;
            grant->physical=address;grant->bytes=e->span.bytes;grant->owner=A::WORKSPACE;grant->reserved=0;
            DCFlushRange(const_cast<MsTraceReadGrant*>(grant),32);
            grant->sequence=c.sequence;DCFlushRange(const_cast<MsTraceReadGrant*>(grant),32);
        }
    }
    DCFlushRange(const_cast<void*>(data),bytes);

#else
    (void)raw;(void)data;(void)bytes;
#endif
}

}
