#pragma once
#include "ghost_trace_logical.hxx"
#include "ghost_trace_export_io.hxx"
namespace GhostTraceFlat {
enum Phase { CLOSED, RESOLVE, PIN_SOURCE, BEGIN_OUTPUT, HEADER, NEXT_CHUNK, OPEN_SOURCE, SOURCE_HEADER, SOURCE_FOOTER,
    COPY_REQUEST, COPY_DATA, WRITE_WAIT, FOOTER, CLOSE_INPUT, COMMIT_WAIT, UNPIN, CLEANUP, DONE, FAILED };
enum Error { NONE, ARGUMENT, SOURCE, OUTPUT, SOURCE_CHANGED, OWNERSHIP, CANCELED };
struct Task {
    GhostTraceLogical::Stream*logical;GhostTraceIo::Transport*transport;GhostTraceExportIo::Client*output;
    GhostTraceBranchIo::Client*maps;GhostTraceIo::File target,copyFile;
    GhostTraceStream::Cursor cursor;MsTraceFileIdentity expected,result;MsTraceBranch pin;
    unsigned phase,error,detail,channel,destination,game,chunks,copyAt,copyHash,pendingCopy,nextPhase,runFlags;
    unsigned pinMayExist,unpinIssued,cleanupError,copyVerified;
    bool canceled,published;
    unsigned char header[64],initialHeader[64],exportName[MS_TRACE_EXPORT_NAME_BYTES];
};
struct Status { Phase phase;unsigned error,detail,bytes,chunks,runFlags,cleanupError;bool pending,published; };
// Client/workspace lifetimes extend through close. The lifecycle owner must keep
// all recorder/playback modes out of these shared data banks while active().
bool begin(Task&,GhostTraceLogical::Stream&,GhostTraceLogical::Plan,GhostTraceBranchIo::Client&,
           GhostTraceStream::Stream&,GhostTraceIo::Transport&,GhostTraceExportIo::Client&,
           unsigned readChannel,unsigned copyChannel,GhostTraceIo::File source,GhostTraceIo::File target,unsigned game,unsigned destinationFlags);
Phase poll(Task&,unsigned budget=4);
Status status(const Task&);
bool cancel(Task&);bool close(Task&);bool active();
bool configureNativeAndBegin(GhostTraceIo::File source,GhostTraceIo::File target,unsigned game,unsigned destinationFlags,unsigned segmentCapacity=4096);
Task* nativeTask();
}
