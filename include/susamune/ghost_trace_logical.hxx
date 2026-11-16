#pragma once
#include "ghost_trace_branch_io.hxx"
#include "ghost_trace_stream.hxx"
namespace GhostTraceLogical {
enum { kMaxSegments=4096, kMaxHashSlots=8192 };
struct Cut { unsigned chunk,bytes,hash,fileOffset,fileEnd,frame,tick; };
struct Segment { GhostTraceIo::File file;MsTraceFileIdentity identity;Cut cut; };
struct Workspace { Segment segments[kMaxSegments];unsigned hash[kMaxHashSlots]; };
static_assert(sizeof(Segment)==72&&sizeof(Workspace)==0x50000,"bounded branch workspace");
struct Plan { Segment*segments;unsigned capacity;unsigned*hash;unsigned hashCapacity,count; };
enum Phase { CLOSED, RESOLVING, OPENING, READING, SWITCHING, FINISHED, DRAINING, FAILED };
enum Result { WAIT, EVENT, BOUNDARY, END, ERROR, BORROWED };
enum Error { NONE, ARGUMENT, MAP_IO, CAPACITY, CYCLE, IDENTITY, PHYSICAL, CONTINUATION, CANCELLED };
struct Stream {
    Plan plan;GhostTraceBranchIo::Client*maps;GhostTraceStream::Stream*physical;
    GhostTraceIo::Transport*transport;GhostTraceIo::File query;Cut pendingCut;
    unsigned game,required,channel,index,phase,error,detail,requested,borrowed,mode,first,lastFrame,lastTick,closing,runFlags;
};
struct Status { Phase phase;unsigned error,detail,segments,segment;bool borrowed,pending; };
// Caller exclusively owns plan/control storage outside the physical arena banks.
// capacity=1 and no hash table suffice for an ordinary self-contained file.
// Capacities above 32 require a power-of-two hash table with >=2*capacity slots.
bool open(Stream&,Plan,GhostTraceBranchIo::Client&,GhostTraceStream::Stream&,GhostTraceIo::Transport&,
          unsigned channel,GhostTraceIo::File,unsigned game,unsigned required=0);
Phase poll(Stream&,unsigned budget=4);
Status status(const Stream&);
unsigned runFlags(const Stream&);
Result nextEvent(Stream&,GhostTraceDecode::Event&,unsigned&ticket);
// BOUNDARY is an AFTER-prefix barrier, even when its frame equals the prior event.
// Finish the previous native frame before applying the constrained audio/reseed action.
bool releaseEvent(Stream&,unsigned ticket);
Result nextChunk(Stream&,GhostArena::View&,GhostTraceStream::Cursor&,unsigned&ticket);
bool releaseChunk(Stream&,unsigned ticket);
bool close(Stream&);bool cancel(Stream&);
}
