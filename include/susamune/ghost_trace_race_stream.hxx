#pragma once
#include "susamune/ghost_arena.hxx"
#include "susamune/ghost_trace_index.hxx"

namespace GhostTraceRaceStream {
enum Error { NONE, IO, CORRUPT, OWNERSHIP, EXHAUSTED };
struct Read { unsigned sequence,offset,bytes; void *destination; };
struct Slot { GhostArena::Handle lease; unsigned page,sequence,ready; };
struct Stream {
    GhostArena::Arena *arena;
    const GhostTraceIndex::Page *pages;
    unsigned count,sequence,error,selected;
    GhostTraceIndex::Query query;
    GhostTraceIndex::Needed needed;
    Slot slots[2];
};
// Zero-initialize once. Directory storage remains leased/immutable until close().
bool begin(Stream &,GhostArena::Arena &,const GhostTraceIndex::Page *,unsigned count);
bool request(Stream &,GhostTraceIndex::Query);
bool nextRead(Stream &,Read &);
// Caller performs platform cache maintenance before acknowledging completed I/O.
bool acceptRead(Stream &,unsigned sequence,unsigned bytes,bool success);
bool sample(const Stream &,GhostTraceIndex::Bracket &);
// Pending I/O must complete (including a reported failure) before leases can return.
bool close(Stream &);
}
