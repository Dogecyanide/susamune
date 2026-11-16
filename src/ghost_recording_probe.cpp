#if MOONSHINE_GHOST_TRACE && IS_EMULATOR
#include "susamune/ghost_recording.hxx"
#include "susamune/ghost_trace.hxx"

namespace GhostRecordingProbe {
namespace {
bool load(const void *,unsigned,bool,bool) { return false; }
bool checkpoint(GhostRecording::Checkpoint &,bool) { return false; }
int discard(GhostRecording::Identity,bool) { return -1; }
}
// Private capture fixture; library operations remain unavailable.
bool install() {
    unsigned nonce=0;
    if(!GhostTrace::backendIdentity(nonce))return false;
    auto &runtime=*reinterpret_cast<GhostRecording::Runtime*>(MS_TRACE_CONTROL_PPC+0x2400);
    const GhostRecording::Backend backend={load,checkpoint,discard};
    return GhostRecording::install(runtime,nonce,GhostRecordingLifecycle::kRequired,backend);
}
}
#endif
