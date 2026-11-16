#include "susamune/ghost_replay_report.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/ghost_replay_report.h"
#include "susamune/ghost_trace.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
namespace GhostReplayReport {
namespace {
unsigned sequence,boot,lease;
volatile MsReplayReportMailbox &box=*reinterpret_cast<volatile MsReplayReportMailbox*>(MS_REPLAY_REPORT_MAILBOX_PPC);
bool acknowledged() {
    DCInvalidateRange(const_cast<MsReplayReportResponse*>(&box.response),32);
    return box.response.magic==MS_REPLAY_REPORT_MAGIC&&box.response.version==MS_REPLAY_REPORT_VERSION&&
        box.response.bootNonce==boot&&box.response.ack==sequence;
}
}
bool pending(){return lease&&!acknowledged();}
unsigned poll() {
    if(!lease||!acknowledged())return 0;
    lease=0;return box.response.status+1;
}
bool reserve() {
#if IS_EMULATOR
    return true;
#else
    if(pending()||!GhostTrace::backendIdentity(boot))return false;
    DCInvalidateRange(const_cast<MsReplayReportResponse*>(&box.response),32);
    return box.response.magic==MS_REPLAY_REPORT_MAGIC&&box.response.version==MS_REPLAY_REPORT_VERSION&&
        box.response.bootNonce==boot&&box.response.ack==box.request.sequence&&box.response.ack!=~0u;
#endif
}
bool submit(unsigned bytes,unsigned fileNonce,unsigned run) {
    if(bytes<MS_REPLAY_REPORT_MIN_BYTES||bytes>MS_REPLAY_REPORT_MAX_BYTES)return false;
    const void *payload=reinterpret_cast<const void*>(MS_REPLAY_REPORT_DATA_PPC);
    DCStoreRange(const_cast<void*>(payload),bytes);
#if IS_EMULATOR
    (void)fileNonce;(void)run;return true;
#else
    if(!reserve())return false;
    const unsigned next=box.response.ack+1;
    MsReplayReportRequest request={MS_REPLAY_REPORT_MAGIC,MS_REPLAY_REPORT_VERSION,boot,0,bytes,fileNonce,run,
        MsReplayReportHash(2166136261u,payload,bytes)};
    if(!next||!MsReplayReportHeaderValid(static_cast<const unsigned char*>(payload),&request,
        *reinterpret_cast<volatile const unsigned*>(0x80000000u)))return false;
    memcpy(const_cast<MsReplayReportRequest*>(&box.request),&request,32);
    DCStoreRange(const_cast<MsReplayReportRequest*>(&box.request),32);
    sequence=next;lease=1;box.request.sequence=next;
    DCStoreRange(const_cast<MsReplayReportRequest*>(&box.request),32);return true;
#endif
}
}
#endif
