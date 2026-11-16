#ifndef MOONSHINE_GHOST_TRACE_EXPORT_H
#define MOONSHINE_GHOST_TRACE_EXPORT_H
#include "ghost_trace_checkpoint.h"
#include "ghost_provenance.h"
#define MS_TRACE_EXPORT_MAGIC 0x4d534558u
#define MS_TRACE_EXPORT_VERSION 1u
#define MS_TRACE_EXPORT_MAILBOX_OFFSET 0x11a0u
#define MS_TRACE_EXPORT_ARM_OFFSET 0x1240u
#define MS_TRACE_EXPORT_BUFFER_BYTES 0x5000u
#define MS_TRACE_EXPORT_BUFFER_OFFSET (MOONSHINE_GHOST_UPPER_SIZE-MS_TRACE_EXPORT_BUFFER_BYTES)
#define MS_TRACE_EXPORT_BUFFER_PPC (MS_TRACE_UPPER_PPC+MS_TRACE_EXPORT_BUFFER_OFFSET)
#define MS_TRACE_EXPORT_BUFFER_PHYS (MOONSHINE_GHOST_UPPER_PHYS_BASE+MS_TRACE_EXPORT_BUFFER_OFFSET)
#define MS_TRACE_EXPORT_PLAN_OFFSET (MS_TRACE_BUFFER1_OFFSET+MS_TRACE_BUFFER_BYTES+0x1000u)
#define MS_TRACE_EXPORT_PLAN_BYTES 0x50000u
#define MS_TRACE_EXPORT_CONTROL_OFFSET (MS_TRACE_EXPORT_PLAN_OFFSET+MS_TRACE_EXPORT_PLAN_BYTES)
#define MS_TRACE_EXPORT_MAX_WRITE 0x4028u
#define MS_TRACE_EXPORT_NO_OWNER 0x80000000u
#define MS_TRACE_EXPORT_CANCEL_FLAG 0x80000000u
#define MS_TRACE_EXPORT_CANCELED 8u
#define MS_TRACE_EXPORT_PUBLIC 1u
#define MS_TRACE_EXPORT_NAMED 2u
#define MS_TRACE_EXPORT_NAME_BYTES 32u
#define MS_TRACE_EXPORT_NAME_MAGIC 0x4d534e4du
#define MS_TRACE_EXPORT_PROFILE_SHIFT 8u
static inline int MsTraceExportNameValid(const unsigned char *p) {
    return MsTraceGet(p)==MS_TRACE_EXPORT_NAME_MAGIC && MsTraceGet(p+4)<=0x3cu &&
        MsTraceGet(p+8)<=9u && (MsTraceGet(p+12)<=0x3cu || MsTraceGet(p+12)==255u) &&
        (MsTraceGet(p+16)<=255u || MsTraceGet(p+16)==0xffffffffu) &&
        MsTraceGet(p+20) && MsTraceGet(p+20)<=0x7fffffffu && !MsTraceGet(p+24) &&
        MsTraceGet(p+28)==MsTraceHash(2166136261u,p,28);
}
enum MsTraceExportOperation { MS_TRACE_EXPORT_BEGIN=1,MS_TRACE_EXPORT_APPEND,MS_TRACE_EXPORT_COMMIT,MS_TRACE_EXPORT_ABORT };
enum MsTraceExportPhase { MS_TRACE_EXPORT_IDLE,MS_TRACE_EXPORT_OPEN,MS_TRACE_EXPORT_VERIFY,MS_TRACE_EXPORT_DONE,MS_TRACE_EXPORT_FAILED };
struct MsTraceExportRequest { unsigned magic,version,bootNonce,sequence,operation,nonce,run,game; };
struct MsTraceExportTransfer { unsigned physical,capacity,bytes,lease,checksum,totalBytes,fileAdler,flags; };
struct MsTraceExportResponse { unsigned magic,version,bootNonce,ack,status,phase,bytes,checksum; };
struct MsTraceExportMailbox { struct MsTraceExportRequest request;struct MsTraceExportTransfer transfer;struct MsTraceExportResponse response;struct MsTraceFileIdentity identity; };
typedef char MsTraceExportPlacement[(sizeof(struct MsTraceExportMailbox)==128 &&
    MS_TRACE_BRANCH_LOOKUP_OFFSET+sizeof(struct MsTraceLookup)==MS_TRACE_EXPORT_MAILBOX_OFFSET &&
    MS_TRACE_EXPORT_MAILBOX_OFFSET+sizeof(struct MsTraceExportMailbox)<=MS_TRACE_EXPORT_ARM_OFFSET &&
    MS_TRACE_EXPORT_CONTROL_OFFSET+0x1000u<=MS_TRACE_EXPORT_BUFFER_OFFSET)?1:-1];
static inline unsigned MsTraceAdler(unsigned adler,const void*data,unsigned bytes) {
    const unsigned char*p=(const unsigned char*)data;unsigned a=adler&65535u,b=adler>>16;
    while(bytes){unsigned n=bytes<5552?bytes:5552;bytes-=n;while(n--){a+=*p++;b+=a;}a%=65521u;b%=65521u;}
    return (b<<16)|a;
}
static inline unsigned MsTraceAdlerReplaceHeader(unsigned adler,const void*oldHeader,const void*newHeader,unsigned total) {
    unsigned old=MsTraceAdler(1,oldHeader,64),next=MsTraceAdler(1,newHeader,64);
    unsigned da=((next&65535u)+65521u-(old&65535u))%65521u;
    unsigned db=((next>>16)+65521u-(old>>16))%65521u;
    unsigned a=((adler&65535u)+da)%65521u,b=((adler>>16)+db+((total-64)%65521u)*da)%65521u;
    return (b<<16)|a;
}
#endif
