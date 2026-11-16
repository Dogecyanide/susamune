#ifndef MOONSHINE_GHOST_TRACE_PREPARE_H
#define MOONSHINE_GHOST_TRACE_PREPARE_H
#include "ghost_trace_stream_storage.h"
#define MS_TRACE_PREPARE_MAGIC 0x4d535450u
#define MS_TRACE_PREPARE_VERSION 3u
#define MS_TRACE_PREPARE_LEGACY_VERSION 1u
#define MS_TRACE_RETIRE_PENDING 0x100u
#define MS_TRACE_PREPARE_ERROR_MASK 0xffu
#define MS_TRACE_RETIRE_MAX_BYTES 0x100000u
#define MS_TRACE_RETIRE_MAX_CLUSTERS 32u
#define MS_TRACE_PREPARE_OFFSET 0xa0u
#define MS_TRACE_PREPARE_UNKNOWN_SCENE 0xffffu
#define MS_TRACE_PREPARE_READY_FLAG 1u
#define MS_TRACE_PREPARE_METADATA_FLAG 2u
#define MS_TRACE_PREPARE_MAX_QUEUED 0x40000u
#define MS_TRACE_PREPARE_PPC (MS_TRACE_CONTROL_PPC+MS_TRACE_PREPARE_OFFSET)
#define MS_TRACE_PREPARE_PHYS (MS_TRACE_CONTROL_PHYS+MS_TRACE_PREPARE_OFFSET)
enum MsTracePrepareOperation { MS_PREP_HELLO=1, MS_PREP_FILE, MS_PREP_CANCEL };
enum MsTracePreparePhase { MS_PREP_IDLE, MS_PREP_MKDIR, MS_PREP_CHECK, MS_PREP_CREATE,
    MS_PREP_HEADER, MS_PREP_SYNC, MS_PREP_READY, MS_PREP_FAILED, MS_PREP_CANCELED, MS_PREP_CONSUMED, MS_PREP_LINKING };
enum MsTracePrepareError { MS_PREP_OK, MS_PREP_PROTOCOL, MS_PREP_IO, MS_PREP_CONFLICT, MS_PREP_SOURCE, MS_PREP_BUSY };
struct MsTracePrepareRequest { unsigned magic,version,bootNonce,sequence,operation,run,capabilities,target; };
struct MsTracePrepareResponse { unsigned magic,version,bootNonce,ack,phase,status,run,ownerSequence; };
struct MsTracePreparePermit { unsigned magic,version,bootNonce,sequence,flags,queued,frame,reserved; };
struct MsTracePrepareMailbox { struct MsTracePrepareRequest request;struct MsTracePrepareResponse response;struct MsTracePreparePermit permit; };
typedef char MsPrepareOwnership[(sizeof(struct MsTraceMailbox)==MS_TRACE_PREPARE_OFFSET&&sizeof(struct MsTracePrepareMailbox)==96&&
    __builtin_offsetof(struct MsTracePrepareMailbox,response)==32&&__builtin_offsetof(struct MsTracePrepareMailbox,permit)==64&&
    MS_TRACE_PREPARE_OFFSET+sizeof(struct MsTracePrepareMailbox)==MS_TRACE_READ_MAILBOX_OFFSET)?1:-1];
#endif
