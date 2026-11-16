#ifndef MOONSHINE_GHOST_TRACE_STREAM_STORAGE_H
#define MOONSHINE_GHOST_TRACE_STREAM_STORAGE_H
#include "ghost_trace.h"
#define MS_TRACE_READ_MAGIC 0x4d535244u
#define MS_TRACE_READ_VERSION 1u
#define MS_TRACE_READ_CHANNELS 2u
#define MS_TRACE_READ_MAILBOX_OFFSET 0x100u
#define MS_TRACE_READ_MAILBOX_BYTES 0x80u
#define MS_TRACE_READ_ARM_OFFSET 0x2000u
#define MS_TRACE_READ_ARM_BYTES 0x400u
#define MS_TRACE_READ_MAX_BYTES 0x4000u
#define MS_TRACE_READ_MAILBOX_PHYS(i) (MS_TRACE_CONTROL_PHYS+MS_TRACE_READ_MAILBOX_OFFSET+(i)*MS_TRACE_READ_MAILBOX_BYTES)
#define MS_TRACE_READ_MAILBOX_PPC(i) (MS_TRACE_CONTROL_PPC+MS_TRACE_READ_MAILBOX_OFFSET+(i)*MS_TRACE_READ_MAILBOX_BYTES)
enum MsTraceReadOperation { MS_TRACE_READ_OPEN=1, MS_TRACE_READ_DATA, MS_TRACE_READ_CLOSE };
enum MsTraceReadRegion { MS_TRACE_READ_JP=1, MS_TRACE_READ_US, MS_TRACE_READ_PAL };
enum MsTraceReadStatus { MS_TRACE_READ_OK, MS_TRACE_READ_PROTOCOL, MS_TRACE_READ_EPOCH,
    MS_TRACE_READ_IO, MS_TRACE_READ_FILE, MS_TRACE_READ_DESTINATION };
struct MsTraceReadRequest { unsigned magic,version,bootNonce,sequence,operation,fileNonce,run,region; };
struct MsTraceReadBuffer { unsigned physical,capacity,bytes,lease,offset,reserved[3]; };
struct MsTraceReadResponse { unsigned magic,version,bootNonce,ack,status,bytes,fileSize,lease; };
struct MsTraceReadMailbox {
    struct MsTraceReadRequest request;
    struct MsTraceReadBuffer buffer;
    struct MsTraceReadResponse response;
    unsigned reserved[8];
};
typedef char MsTraceReadLines[(sizeof(struct MsTraceReadMailbox)==128 &&
    sizeof(struct MsTraceReadRequest)==32 && sizeof(struct MsTraceReadBuffer)==32 &&
    __builtin_offsetof(struct MsTraceReadMailbox,response)==64 &&
    __builtin_offsetof(struct MsTraceReadMailbox,reserved)==96)?1:-1];
typedef char MsTraceReadMailboxesFit[(sizeof(struct MsTraceMailbox)<=MS_TRACE_READ_MAILBOX_OFFSET &&
    MS_TRACE_READ_MAILBOX_OFFSET+MS_TRACE_READ_CHANNELS*MS_TRACE_READ_MAILBOX_BYTES<=MS_TRACE_ARM_OFFSET)?1:-1];
/* One request per stream may be outstanding. Stage with sequence zero, flush
 * both request lines, then publish the nonzero sequence last. ARM owns response
 * only. Keep the whole rounded destination leased until acknowledgement. */
#endif
