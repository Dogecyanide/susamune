#pragma once
#include "susamune/ghost_trace_io.hxx"
#include "susamune/ghost_trace_reader.hxx"
#include "susamune/ghost_trace_decode.hxx"
#include "susamune/ghost_trace_checkpoint.h"

namespace GhostTraceStream {
enum Phase { CLOSED, OPENING, STREAMING, DRAINING, FINISHED, FAILED };
enum Result { WAIT, EVENT, END, ERROR, BORROWED };
enum Error { NONE, ARGUMENT, OWNERSHIP, IO, READER, DECODER, IDENTITY, EXHAUSTED, CANCELLED };
enum { kNoSlot=2, kOutputBytes=0x80000, kScratchBytes=0x4000 };
struct Slot { GhostArena::Handle lease; unsigned bytes,sequence,ready,hash,fileOffset,fileEnd,frame,tick,encodedHash; };
struct Cursor {
    GhostTraceIo::File file;
    unsigned chunk,chunkBytes,chunkHash,fileOffset,fileEnd,recordOffset,recordEnd,frame,tick,encodedHash;
};
struct Limit { unsigned chunk,bytes,hash,fileOffset,fileEnd,frame,tick,headerHash; };
struct Stream {
    GhostTraceReader::Reader reader;
    GhostTraceDecode::Decoder decoder;
    GhostTraceReader::Read pending;
    GhostTraceIo::Transport *transport;
    GhostArena::Arena *arena;
    GhostTraceIo::File file;
    Slot slots[2];
    GhostArena::Handle packed;
    unsigned channel,game,required,fill,current,ticket,borrowed,chunkStart,recordStart;
    unsigned initialized,decoderReady,ended,closing,error,detail;
    unsigned cacheOffset,cacheBytes;
    MsTraceFileIdentity actual,expected;Limit limit;
    unsigned identityReady,constrained,mode,encodedHash,observedRunFlags;
};
struct Status { Phase phase; unsigned error,detail,fileBytes,chunks,buffered; bool borrowed,pending; };
// Zero-initialize once. Control/Event storage stays outside arena banks. Calls are serialized.
// The configured arena grants only caller-owned data; open takes two 512 KiB outputs
// and 16 KiB packed scratch before the transport takes its own 16 KiB scratch.
bool open(Stream &,GhostTraceIo::Transport &,unsigned channel,GhostTraceIo::File,
          unsigned targetGame,unsigned requiredCapabilities=0);
// Set immediately after open, before poll. A zero limit means the complete file.
bool constrain(Stream&,const MsTraceFileIdentity&,const Limit&);
bool identity(const Stream&,MsTraceFileIdentity&);
unsigned runFlags(const Stream&);
// Raw mode is exclusive with Event mode. The complete checked chunk stays borrowed
// through its exact ticket; this is the source for self-contained MSGT export.
Result nextChunk(Stream&,GhostArena::View&,Cursor&,unsigned&ticket);
bool releaseChunk(Stream&,unsigned ticket);
// At most budget accepted reads (each <=16 KiB) per call. I/O itself is asynchronous.
Phase poll(Stream &,unsigned budget=4);
Status status(const Stream &);
Result nextEvent(Stream &,GhostTraceDecode::Event &,unsigned &ticket);
// All pointer fields in the returned Event expire at this exact ticket's release.
bool releaseEvent(Stream &,unsigned ticket);
// Scalar checkpoint identity; no pointer survives a release or a new physical segment.
bool cursor(const Stream &,unsigned ticket,Cursor &);
// Close/cancel may return false while an Event or ARM operation still owns memory.
// Continue polling and release the borrowed Event; no timeout releases a pin.
bool close(Stream &);
bool cancel(Stream &);
}
