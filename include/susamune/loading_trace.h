#ifndef MOONSHINE_LOADING_TRACE_H
#define MOONSHINE_LOADING_TRACE_H
#include "ghost_trace.h"
#define MS_LOADING_TRACE_MAGIC 0x4d534c54u
#define MS_LOADING_TRACE_VERSION 1u
#define MS_LOADING_TRACE_OFFSET 0x3c00u
#define MS_LOADING_TRACE_COUNT 8u
enum MsLoadingPhase { MS_LOAD_ARM=1,MS_LOAD_KICK,MS_LOAD_GHOST_WAIT,MS_LOAD_COMMIT,MS_LOAD_THREAD_BEGIN,MS_LOAD_OBJECTS_BEGIN,MS_LOAD_OBJECTS_END,MS_LOAD_CANCEL };
struct MsLoadingEntry { unsigned sequence,phase,tick,scene,value0,dropped,clockHz,reserved; };
struct MsLoadingMailbox {
    unsigned magic,version,nonce,writeSequence,dropped,reserved[3];
    unsigned readSequence,ackReserved[7];
    struct MsLoadingEntry entries[MS_LOADING_TRACE_COUNT];
};
typedef char MsLoadingCacheLines[(sizeof(struct MsLoadingEntry)==32 && __builtin_offsetof(struct MsLoadingMailbox,readSequence)==32 && __builtin_offsetof(struct MsLoadingMailbox,entries)==64)?1:-1];
typedef char MsLoadingOwnership[(MS_TRACE_NATIVE_OFFSET+MS_TRACE_NATIVE_BYTES<=MS_LOADING_TRACE_OFFSET && MS_LOADING_TRACE_OFFSET+sizeof(struct MsLoadingMailbox)<=0x3f00u)?1:-1];
#endif
