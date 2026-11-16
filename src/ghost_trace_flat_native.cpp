#include "susamune/ghost_recording_native.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/ghost_trace_stream_native.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_world_runtime.hxx"
namespace GhostTraceFlat {
namespace {
struct Native { Task task;GhostTraceLogical::Stream logical;GhostTraceBranchIo::Client maps;GhostTraceStream::Stream physical;
    GhostTraceIo::Transport transport;GhostArena::Arena arena;GhostTraceStreamNative::Context reader;GhostTraceExportIo::Client writer; };
static_assert(sizeof(Native)<=MS_TRACE_EXPORT_BUFFER_OFFSET-MS_TRACE_EXPORT_CONTROL_OFFSET,"flat export control workspace");
Native*installed;
}
Task*nativeTask(){return installed?&installed->task:nullptr;}
bool configureNativeAndBegin(GhostTraceIo::File source,GhostTraceIo::File target,unsigned game,unsigned destination,unsigned capacity){
#if !IS_EMULATOR
    unsigned nonce=0;if(active()||GhostRecordingNative::fileBusy()||GhostWorldRuntime::busy()||!GhostTrace::backendIdentity(nonce)||!GhostTraceStreamNative::idleWriter(nonce)||!capacity||capacity>4096)return false;
    auto*n=reinterpret_cast<Native*>(MS_TRACE_UPPER_PPC+MS_TRACE_EXPORT_CONTROL_OFFSET);*n={};
    if(!GhostTraceStreamNative::configure(n->reader,n->transport,n->arena,nonce)||!GhostTraceBranchIo::configureNative(n->maps,nonce)||
       !GhostTraceExportIo::configureNative(n->writer,nonce))return false;
    auto*work=reinterpret_cast<GhostTraceLogical::Workspace*>(MS_TRACE_UPPER_PPC+MS_TRACE_EXPORT_PLAN_OFFSET);
    const GhostTraceLogical::Plan plan={work->segments,capacity,capacity>32?work->hash:nullptr,capacity>32?8192u:0u,0};
    if(!begin(n->task,n->logical,plan,n->maps,n->physical,n->transport,n->writer,0,1,source,target,game,destination)){GhostTraceExportIo::close(n->writer);return false;}
    installed=n;return true;
#else
    (void)source;(void)target;(void)game;(void)destination;(void)capacity;return false;
#endif
}
}
