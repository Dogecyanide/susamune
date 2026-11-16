#include "susamune/ghost_trace_branch_io.hxx"
#include "Dolphin/OS.h"
#include "susamune/ghost_memory.hxx"
namespace GhostTraceBranchIo {
#if !IS_EMULATOR
namespace {
void flush(void*,const void*p,unsigned bytes){DCFlushRange(const_cast<void*>(p),bytes);}
void invalidate(void*,void*p,unsigned bytes){DCInvalidateRange(p,bytes);}
}
#endif
bool configureNative(Client&c,unsigned nonce){
#if !IS_EMULATOR
    if(!GhostMemory::admitted())return false;
    const Hooks h={nullptr,reinterpret_cast<volatile MsTraceBranchMailbox*>(MS_TRACE_CONTROL_PPC+MS_TRACE_BRANCH_MAILBOX_OFFSET),
        reinterpret_cast<volatile MsTraceLookup*>(MS_TRACE_CONTROL_PPC+MS_TRACE_BRANCH_LOOKUP_OFFSET),flush,invalidate};return configure(c,h,nonce);
#else
    (void)c;(void)nonce;return false;
#endif
}
}
