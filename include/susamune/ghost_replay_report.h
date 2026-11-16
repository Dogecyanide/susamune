#ifndef MOONSHINE_GHOST_REPLAY_REPORT_H
#define MOONSHINE_GHOST_REPLAY_REPORT_H
#include "ghost_trace.h"

#define MS_REPLAY_REPORT_MAGIC 0x4d535250u
#define MS_REPLAY_REPORT_VERSION 1u
#define MS_REPLAY_REPORT_END_MAGIC 0x4d535245u
#define MS_REPLAY_REPORT_MAILBOX_OFFSET 0x3200u
#define MS_REPLAY_REPORT_ARM_OFFSET 0x3400u
#define MS_REPLAY_REPORT_ARM_BYTES 0x400u
#define MS_REPLAY_REPORT_MAILBOX_PPC (MS_TRACE_CONTROL_PPC+MS_REPLAY_REPORT_MAILBOX_OFFSET)
#define MS_REPLAY_REPORT_MAILBOX_PHYS (MS_TRACE_CONTROL_PHYS+MS_REPLAY_REPORT_MAILBOX_OFFSET)
#define MS_REPLAY_REPORT_DATA_PPC MS_TRACE_ACTOR_CACHE_PPC
#define MS_REPLAY_REPORT_DATA_PHYS (0x10000000u+MOONSHINE_GHOST_ARAM_START)

enum {
    MS_REPLAY_REPORT_HEADER_BYTES=64, MS_REPLAY_REPORT_STATUS_BYTES=128,
    MS_REPLAY_REPORT_VISUAL_BYTES=128, MS_REPLAY_REPORT_MIN_BYTES=320,
    MS_REPLAY_REPORT_ACTOR_BYTES=256, MS_REPLAY_REPORT_ACTOR_PREFIX_BYTES=244,
    MS_REPLAY_REPORT_MAX_ACTORS=1024, MS_REPLAY_REPORT_MAX_BYTES=MOONSHINE_GHOST_ARAM_BYTES,
    MS_REPLAY_REPORT_FOOTER_BYTES=32, MS_REPLAY_REPORT_TRANSFER_BYTES=0x4000
};
enum MsReplayReportStatus {
    MS_REPLAY_REPORT_OK, MS_REPLAY_REPORT_BAD_REQUEST, MS_REPLAY_REPORT_BAD_PAYLOAD,
    MS_REPLAY_REPORT_NO_STORAGE, MS_REPLAY_REPORT_IO, MS_REPLAY_REPORT_EXISTS,
    MS_REPLAY_REPORT_STALE
};
struct MsReplayReportRequest {
    unsigned magic,version,bootNonce,sequence,payloadBytes,fileNonce,run,checksum;
};
struct MsReplayReportResponse {
    unsigned magic,version,bootNonce,ack,status,bytes,reserved[2];
};
/* Payload and footer words are big-endian on disk. */
struct MsReplayReportHeader {
    unsigned magic,version,headerBytes,payloadBytes,game,fileNonce,run,reason;
    unsigned detail,actorCount,actorBytes,actorStatus,snapshotHash,snapshotScope,snapshotCount,reserved;
};
struct MsReplayReportActor {
    unsigned address,ordinal;
    unsigned char prefix[MS_REPLAY_REPORT_ACTOR_PREFIX_BYTES];
    unsigned padding;
};
struct MsReplayReportFooter {
    unsigned magic,version,bootNonce,sequence,payloadBytes,checksum,reserved[2];
};
typedef char MsReplayReportWireSizes[(sizeof(struct MsReplayReportHeader)==64&&
    sizeof(struct MsReplayReportActor)==256&&__builtin_offsetof(struct MsReplayReportActor,padding)==252&&
    sizeof(struct MsReplayReportFooter)==32)?1:-1];
struct MsReplayReportMailbox {
    struct MsReplayReportRequest request;
    struct MsReplayReportResponse response;
};
typedef char MsReplayReportLines[(sizeof(struct MsReplayReportMailbox)==64 &&
    __builtin_offsetof(struct MsReplayReportMailbox,response)==32 &&
    !(MS_REPLAY_REPORT_MAILBOX_OFFSET&31u) &&
    MS_REPLAY_REPORT_MAILBOX_OFFSET+64<=MS_REPLAY_REPORT_ARM_OFFSET &&
    MS_REPLAY_REPORT_ARM_OFFSET+MS_REPLAY_REPORT_ARM_BYTES<=MS_TRACE_NATIVE_OFFSET &&
    MS_TRACE_NATIVE_OFFSET+MS_TRACE_NATIVE_BYTES<=MS_TRACE_PPC_OFFSET)?1:-1];
typedef char MsReplayReportPayloadFits[
    MS_REPLAY_REPORT_MIN_BYTES+MS_REPLAY_REPORT_MAX_ACTORS*MS_REPLAY_REPORT_ACTOR_BYTES<=MS_REPLAY_REPORT_MAX_BYTES?1:-1];

static inline unsigned MsReplayReportGet(const unsigned char*p) {
    return (unsigned)p[0]<<24|(unsigned)p[1]<<16|(unsigned)p[2]<<8|p[3];
}
static inline void MsReplayReportPut(unsigned char*p,unsigned value) {
    MsTracePut(p,value);
}
static inline unsigned MsReplayReportHash(unsigned hash,const void*p,unsigned bytes) {
    return MsTraceHash(hash,p,bytes);
}
static inline int MsReplayReportRequestValid(const struct MsReplayReportRequest*q,unsigned nonce) {
    return q->magic==MS_REPLAY_REPORT_MAGIC&&q->version==MS_REPLAY_REPORT_VERSION&&
        nonce&&q->bootNonce==nonce&&q->sequence&&q->fileNonce&&q->run&&
        q->payloadBytes>=MS_REPLAY_REPORT_MIN_BYTES&&q->payloadBytes<=MS_REPLAY_REPORT_MAX_BYTES&&
        !((q->payloadBytes-MS_REPLAY_REPORT_MIN_BYTES)%MS_REPLAY_REPORT_ACTOR_BYTES)&&
        (q->payloadBytes-MS_REPLAY_REPORT_MIN_BYTES)/MS_REPLAY_REPORT_ACTOR_BYTES<=MS_REPLAY_REPORT_MAX_ACTORS;
}
// The source actor address and ordinal are data, never native access requests.
static inline int MsReplayReportHeaderValid(const unsigned char*h,const struct MsReplayReportRequest*q,unsigned game) {
    unsigned count=MsReplayReportGet(h+36);
    return MsReplayReportGet(h)==MS_REPLAY_REPORT_MAGIC&&MsReplayReportGet(h+4)==MS_REPLAY_REPORT_VERSION&&
        MsReplayReportGet(h+8)==MS_REPLAY_REPORT_HEADER_BYTES&&MsReplayReportGet(h+12)==q->payloadBytes&&
        MsReplayReportGet(h+16)==game&&MsReplayReportGet(h+20)==q->fileNonce&&MsReplayReportGet(h+24)==q->run&&
        count<=MS_REPLAY_REPORT_MAX_ACTORS&&q->payloadBytes==MS_REPLAY_REPORT_MIN_BYTES+count*MS_REPLAY_REPORT_ACTOR_BYTES&&
        MsReplayReportGet(h+40)==MS_REPLAY_REPORT_ACTOR_BYTES&&!MsReplayReportGet(h+60);
}
#endif
