#include "susamune/loading_trace.hxx"
#if MOONSHINE_MEMORY_TELEMETRY && MOONSHINE_GHOST_TRACE && !IS_EMULATOR
#include "susamune/ghost_trace.hxx"
#include "SMS/System/Application.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
namespace LoadingTrace {
namespace {unsigned lastPhase;}
void mark(unsigned phase,unsigned value0){
    if(!phase||phase>MS_LOAD_CANCEL||(phase==lastPhase&&phase!=MS_LOAD_ARM))return;
    unsigned nonce=0;if(!GhostTrace::backendIdentity(nonce))return;
    auto &box=*reinterpret_cast<volatile MsLoadingMailbox*>(MS_TRACE_CONTROL_PPC+MS_LOADING_TRACE_OFFSET);
    DCInvalidateRange(const_cast<unsigned*>(&box.magic),64);
    if(box.magic!=MS_LOADING_TRACE_MAGIC||box.version!=MS_LOADING_TRACE_VERSION||box.nonce!=nonce)return;
    const unsigned sequence=box.writeSequence;
    if(sequence==~0u||sequence-box.readSequence>=MS_LOADING_TRACE_COUNT){++box.dropped;DCStoreRange(const_cast<unsigned*>(&box.magic),32);return;}
    const auto &scene=gpApplication.mCurrentScene;
    const MsLoadingEntry entry={sequence+1,phase,OSGetTick(),(unsigned(scene.mAreaID)<<8)|scene.mEpisodeID,value0,box.dropped,(OS_TIMER_CLOCK),0};
    auto *target=const_cast<MsLoadingEntry*>(&box.entries[sequence&(MS_LOADING_TRACE_COUNT-1)]);
    memcpy(target,&entry,sizeof(entry));DCStoreRange(target,sizeof(entry));
    box.writeSequence=sequence+1;DCStoreRange(const_cast<unsigned*>(&box.magic),32);lastPhase=phase;
}
}
#endif
