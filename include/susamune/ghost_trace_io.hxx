#pragma once
#include "ghost_arena.hxx"
#include "ghost_trace_stream_storage.h"

namespace GhostTraceIo {
enum Phase { UNCONFIGURED, CLOSED, OPENING, IDLE, READING, READY, CLOSING, BLOCKED };
enum Error { NONE, ARGUMENT, NOT_READY, OWNERSHIP, TRANSLATION, EXHAUSTED, BAD_ACK, BOOT_CHANGED, REMOTE, CANCELLED };
struct File { unsigned nonce,run,region; };
struct Hooks {
    void *context;
    unsigned contextBytes;
    volatile MsTraceReadMailbox *(*mailbox)(void *,unsigned channel);
    void (*flush)(void *,const void *,unsigned);
    void (*invalidate)(void *,void *,unsigned);
    bool (*physical)(void *,GhostArena::Handle,GhostArena::Span,unsigned &);
    // Optional proof that old I/O and the remote handle are both gone. No timeout is a proof.
    bool (*quiescent)(void *,unsigned channel,unsigned bootNonce,unsigned lease,unsigned sequence);
};
struct Channel {
    GhostArena::Handle lease;
    File file;
    unsigned sequence,operation,bytes,capacity,physical,fileBytes,readyBytes,cancel;
    Phase phase;
    Error error;
    unsigned remoteStatus,failedStatus;
};
struct Transport {
    Hooks hooks;
    GhostArena::Arena *arena;
    volatile MsTraceReadMailbox *mailboxes[MS_TRACE_READ_CHANNELS];
    unsigned bootNonce,scratchBytes;
    Channel channels[MS_TRACE_READ_CHANNELS];
};
struct Status { Phase phase; Error error; unsigned remoteStatus,fileBytes,sequence; bool pending; };
// Zero-initialize once. Hooks/context/control must remain outside all arena banks.
// Serialize calls and keep cache/translation hooks synchronous and non-reentrant.
bool configure(Transport &,GhostArena::Arena &,const Hooks &,unsigned bootNonce,unsigned scratchBytes=MS_TRACE_READ_MAX_BYTES);
bool open(Transport &,unsigned channel,File);
bool read(Transport &,unsigned channel,unsigned offset,unsigned bytes);
Phase poll(Transport &,unsigned channel);
Status status(const Transport &,unsigned channel);
// The checked view lasts until consume/close/another operation. Never borrow the raw lease pointer.
GhostArena::View view(const Transport &,unsigned channel);
bool consume(Transport &,unsigned channel);
// Queues cancellation if I/O is pending; release waits for its exact ACK and remote close.
bool close(Transport &,unsigned channel);
// Only the explicit platform quiescence hook can retire an unacknowledged old epoch.
bool abandon(Transport &,unsigned channel);
}
