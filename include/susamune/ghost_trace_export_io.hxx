#pragma once
#include "ghost_trace_export.h"
#include "ghost_arena.hxx"
namespace GhostTraceExportIo {
enum Phase { UNCONFIGURED, IDLE, WAITING, DONE, FAILED, CLOSED };
struct Hooks { void*context;volatile MsTraceExportMailbox*mailbox;GhostArena::Span buffer;
    void(*flush)(void*,const void*,unsigned);void(*invalidate)(void*,void*,unsigned);
    bool(*physical)(void*,GhostArena::Span,unsigned&); };
struct Client { Hooks hooks;GhostArena::Arena arena;GhostArena::Handle lease;
    unsigned bootNonce,sequence,operation,nonce,run,game,bytes,adler,pendingBytes,pendingAdler,error;Phase phase;bool canceled;MsTraceFileIdentity identity; };
bool configure(Client&,const Hooks&,unsigned bootNonce);
bool configureNative(Client&,unsigned bootNonce);
GhostArena::Span buffer(Client&);
bool begin(Client&,unsigned nonce,unsigned run,unsigned game,unsigned destinationFlags);
bool append(Client&,unsigned bytes);
bool commit(Client&,unsigned finalAdler);
Phase poll(Client&);
bool close(Client&);
}
