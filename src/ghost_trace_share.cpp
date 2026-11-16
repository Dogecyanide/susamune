#include "susamune/ghost_trace_share.hxx"
#include "susamune/ghost_trace_flat.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_recording_manifest.h"

namespace GhostTraceShare {
namespace {
#if MOONSHINE_GHOST_TRACE && !IS_EMULATOR
unsigned sequence;
#endif
bool pending;
}
bool begin(const void *raw,unsigned bytes) {
#if MOONSHINE_GHOST_TRACE && !IS_EMULATOR
    if(!raw||bytes!=MS_RECORDING_MANIFEST_BYTES||pending||GhostTraceFlat::active()||sequence==0x3fffffffu)return false;
    const auto *p=static_cast<const unsigned char*>(raw);
    const unsigned game=MsRecordingWord(p+32),profile=p[38];
    if(!MsRecordingManifestValid(p,bytes,game,profile))return false;
    unsigned nonce=0;if(!GhostTrace::backendIdentity(nonce))return false;
    const GhostTraceIo::File source={MsRecordingWord(p+16),MsRecordingWord(p+20),unsigned(p[37])+1};
    const GhostTraceIo::File target={nonce,0x40000000u|++sequence,source.region};
    if(!GhostTraceFlat::configureNativeAndBegin(source,target,game,
        MS_TRACE_EXPORT_PUBLIC|MS_TRACE_EXPORT_NAMED|(profile<<MS_TRACE_EXPORT_PROFILE_SHIFT)))return false;
    auto *name=GhostTraceFlat::nativeTask()->exportName;
    MsTracePut(name,MS_TRACE_EXPORT_NAME_MAGIC);MsTracePut(name+4,p[44]);MsTracePut(name+8,p[45]);
    MsTracePut(name+12,p[46]);MsTracePut(name+16,MsRecordingWord(p+48));MsTracePut(name+20,MsRecordingWord(p+64));
    MsTracePut(name+24,0);MsTracePut(name+28,MsTraceHash(2166136261u,name,28));
    pending=true;return true;
#else
    (void)raw;(void)bytes;return false;
#endif
}
Result poll() {
    if(!pending)return IDLE;
    auto *task=GhostTraceFlat::nativeTask();
    if(!task){pending=false;return FAILED;}
    GhostTraceFlat::poll(*task,4);
    const auto result=GhostTraceFlat::status(*task);
    if(result.pending)return RUNNING;
    const bool saved=result.published;
    if(!GhostTraceFlat::close(*task))return RUNNING;
    pending=false;return saved?SAVED:FAILED;
}
bool busy(){return pending;}
void cancel(){if(pending)if(auto *task=GhostTraceFlat::nativeTask())GhostTraceFlat::cancel(*task);}
}
