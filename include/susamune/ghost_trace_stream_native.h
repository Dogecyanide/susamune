#ifndef MOONSHINE_GHOST_TRACE_STREAM_NATIVE_H
#define MOONSHINE_GHOST_TRACE_STREAM_NATIVE_H
#include "susamune/ghost_trace_stream_storage.h"
#include "susamune/ghost_trace_compression.h"
#include "susamune/ghost_trace_checkpoint.h"
#define MS_TRACE_STREAM_GRANT_MAGIC 0x4d535247u
#define MS_TRACE_STREAM_GRANT_OFFSET 0x1000u
#define MS_TRACE_STREAM_PACKED_OFFSET (MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES-MOONSHINE_GHOST_UPPER_PHYS_BASE)
#define MS_TRACE_STREAM_IO_OFFSET (MS_TRACE_STREAM_PACKED_OFFSET+MS_TRACE_READ_MAX_BYTES)
#define MS_TRACE_STREAM_IO_PHYS(i) (MOONSHINE_GHOST_UPPER_PHYS_BASE+MS_TRACE_STREAM_IO_OFFSET+(i)*MS_TRACE_READ_MAX_BYTES)
#define MS_TRACE_STREAM_IO_PPC(i) (MS_TRACE_UPPER_PPC+MS_TRACE_STREAM_IO_OFFSET+(i)*MS_TRACE_READ_MAX_BYTES)
#define MS_TRACE_STREAM_GRANT_PHYS(i) (MS_TRACE_CONTROL_PHYS+MS_TRACE_STREAM_GRANT_OFFSET+(i)*32u)
#define MS_TRACE_STREAM_GRANT_PPC(i) (MS_TRACE_CONTROL_PPC+MS_TRACE_STREAM_GRANT_OFFSET+(i)*32u)
struct MsTraceReadGrant { unsigned magic,nonce,sequence,lease,physical,bytes,owner,reserved; };
/* Only these fixed scratch slots are addressable, even with a forged grant. */
static inline int MsTraceReadGrantValid(const struct MsTraceReadGrant *g,
    const struct MsTraceReadRequest *q,const struct MsTraceReadBuffer *b,unsigned nonce) {
    return nonce && g->magic==MS_TRACE_STREAM_GRANT_MAGIC && g->nonce==nonce &&
        g->sequence && g->sequence==q->sequence && g->lease && g->lease==b->lease &&
        g->owner==4u && !g->reserved && q->magic==MS_TRACE_READ_MAGIC &&
        q->version==MS_TRACE_READ_VERSION && q->bootNonce==nonce && q->operation==MS_TRACE_READ_DATA &&
        (g->physical==MS_TRACE_STREAM_IO_PHYS(0) || g->physical==MS_TRACE_STREAM_IO_PHYS(1)) &&
        g->bytes==MS_TRACE_READ_MAX_BYTES && b->physical==g->physical &&
        b->bytes && b->bytes<=g->bytes && b->capacity==((b->bytes+31u)&~31u) &&
        !b->reserved[0] && !b->reserved[1] && !b->reserved[2];
}
typedef char MsTraceReadGrantLine[sizeof(struct MsTraceReadGrant)==32?1:-1];
typedef char MsTraceReadGrantControl[(MS_TRACE_STREAM_GRANT_OFFSET>=0x400u &&
    MS_TRACE_STREAM_GRANT_OFFSET+MS_TRACE_READ_CHANNELS*32u<=MS_TRACE_BRANCH_MAILBOX_OFFSET)?1:-1];
typedef char MsTraceStreamScratchBounds[(MOONSHINE_GHOST_UPPER_PHYS_BASE+MS_TRACE_STREAM_PACKED_OFFSET>=
    MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES &&
    MS_TRACE_STREAM_PACKED_OFFSET+MS_TRACE_READ_MAX_BYTES==MS_TRACE_STREAM_IO_OFFSET &&
    MS_TRACE_STREAM_IO_PPC(MS_TRACE_READ_CHANNELS)<=MS_TRACE_BUFFER1_PPC)?1:-1];
#endif
