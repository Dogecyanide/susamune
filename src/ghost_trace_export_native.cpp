#include "susamune/ghost_trace_export_io.hxx"
#include "susamune/ghost_memory.hxx"
#include "Dolphin/OS.h"
namespace GhostTraceExportIo {
#if !IS_EMULATOR
namespace {
void flush(void*,const void*p,unsigned bytes){DCFlushRange(const_cast<void*>(p),bytes);}
void invalidate(void*,void*p,unsigned bytes){DCInvalidateRange(p,bytes);}
bool physical(void*,GhostArena::Span span,unsigned&out){
    if(reinterpret_cast<GhostArena::Address>(span.data)!=MS_TRACE_EXPORT_BUFFER_PPC||span.bytes!=MS_TRACE_EXPORT_BUFFER_BYTES)return false;
    out=MS_TRACE_EXPORT_BUFFER_PHYS;return true;
}
}
#endif
bool configureNative(Client&c,unsigned nonce){
#if !IS_EMULATOR
    if(!GhostMemory::admitted())return false;
    const Hooks h={nullptr,reinterpret_cast<volatile MsTraceExportMailbox*>(MS_TRACE_CONTROL_PPC+MS_TRACE_EXPORT_MAILBOX_OFFSET),
        {reinterpret_cast<void*>(MS_TRACE_EXPORT_BUFFER_PPC),MS_TRACE_EXPORT_BUFFER_BYTES},flush,invalidate,physical};return configure(c,h,nonce);
#else
    (void)c;(void)nonce;return false;
#endif
}
}
