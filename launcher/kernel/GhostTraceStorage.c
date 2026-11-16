#include "GhostTraceStorage.h"
#include "GhostTraceReadStorage.h"
#include "MoonshineNetLog.h"
#include "susamune/loading_trace.h"
#if MOONSHINE_GHOST_TRACE
#include "global.h"
#include "ISO.h"
#include "DI.h"
#include "SusamuneCfg.h"
#include "SusamuneStateStorage.h"
#include "ff_utf8.h"
extern u32 GAME_ID;
#include "susamune/ghost_trace.h"
#include "susamune/ghost_trace_stream_storage.h"
#include "susamune/ghost_trace_compression.h"
#include "susamune/ghost_trace_prepare.h"
#include "susamune/ghost_trace_checkpoint.h"
#include "susamune/ghost_state_reference.h"
#include "susamune/susamune_cfg.h"
#include <string.h>

struct TraceReferenceCache {
    DIR directory;
    unsigned generation,active,valid,failed,checksum;
    unsigned char bits[2048];
};
struct TraceDiscard { DIR directory;unsigned nonce,run,headerHash,generation,active; };
struct TraceRecovery {
    FIL file;DIR directory;struct MsTraceBranch pin;
    unsigned phase,open,size,offset,lastComplete,chunks,matched,blocks;
    unsigned chunkOffset,chunkBytes,chunkHash,chunkFrame,rawLeft;
    unsigned directoryOpen,requiredBytes,requiredChunks,hasFooter,previousFrame,referenceGeneration;
};
struct TraceLink {
    FIL file;struct MsTraceBranch branch;
    unsigned phase,sequence,primary,oldRun,open,generation;
};
typedef char TraceLinkFits[sizeof(struct TraceLink)<=sizeof(FIL)+160?1:-1];
typedef char TraceLinkFileAlias[__builtin_offsetof(struct TraceLink,file)==0?1:-1];
struct TracePrepare {
    union { struct { FIL file;char path[160]; };struct TraceLink link; };
    struct MsTracePrepareRequest request;
    unsigned phase,active,created,headerHash,error,permitSequence,permitTick,permitReady;
};
struct TraceRetire {
    FIL file;unsigned nonce,run,headerHash,bytes,phase,preserve,capabilities,generation;
};
struct TraceWriter {
    FIL file;
    char path[160];
    struct MsTraceRequest request;
    struct MsTraceChunk chunk;
    struct MsTraceResponse response;
    struct MsTraceMetrics metrics;
    unsigned active, offset, checksum, headerWritten, failed, owned, chunkOffset, headerHash, referenceGeneration;
    unsigned parent[3];
    struct TraceDiscard discard;
    struct MsTraceBranchRequest branchRequest;
    struct MsTraceBranchResponse branchResponse;
    unsigned branchDeleting,retained,statePinValid;
    struct MsTraceBranch statePin;
    struct TraceRecovery recovery;
    struct TraceReferenceCache references;
    struct TracePrepare prepare;
    struct TraceRetire retiring;
};
typedef char TraceWriterFits[sizeof(struct TraceWriter)<0x1000u-MS_TRACE_ARM_OFFSET?1:-1];
#define WRITER ((struct TraceWriter*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_ARM_OFFSET))
#define MAILBOX ((volatile struct MsTraceMailbox*)MS_TRACE_CONTROL_PHYS)
#define FENCE_MAILBOX ((volatile struct MsTraceFenceInfo*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_FENCE_INFO_OFFSET))
#define TRACE_TEXT __attribute__((section(".text.trace_names")))
static const char directoryFormat[] TRACE_TEXT="%s" MOONSHINE_RECORDINGS_DIR "";
static const char fileFormat[] TRACE_TEXT="%s" MOONSHINE_RECORDINGS_DIR "/trace_%08X_%08X.part";
static const char completedSuffix[] TRACE_TEXT="msgt";
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
static unsigned TraceRequestStartedTick;
#endif

static int admitted(void) {
    const struct SusamuneCfg *cfg=SUSAMUNE_CFG_PHYS_PTR;
    return cfg->magic==SUSAMUNE_CFG_MAGIC && cfg->version==SUSAMUNE_CFG_VERSION &&
        (cfg->flags&MOONSHINE_GHOST_MEMORY_FLAG);
}
static void publish(void) {
    memcpy((void*)&MAILBOX->response,&WRITER->response,sizeof(WRITER->response));
    memcpy((void*)&MAILBOX->metrics,&WRITER->metrics,sizeof(WRITER->metrics));
    sync_after_write((void*)&MAILBOX->response,64);
}
static void fail(unsigned error) {
    if(WRITER->active&&f_close(&WRITER->file)==FR_OK)WRITER->active=0;
    WRITER->response.error=error;WRITER->response.phase=MS_TRACE_FAILED;WRITER->failed=1;publish();
}
static int writeBytes(const void *p,unsigned bytes) {
    UINT done=0;unsigned before=read32(HW_TIMER),elapsed;FRESULT result;
    if(bytes>MS_TRACE_FILE_LIMIT-WRITER->response.bytes){fail(MS_TRACE_LIMIT);return 0;}
    result=f_write(&WRITER->file,p,bytes,&done);elapsed=read32(HW_TIMER)-before;
    if(elapsed>WRITER->metrics.maxWriteTicks)WRITER->metrics.maxWriteTicks=elapsed;
    ++WRITER->metrics.writes;
    if(result!=FR_OK || done!=bytes){fail(MS_TRACE_IO);return 0;}
    WRITER->response.bytes+=bytes;return 1;
}
#define LOADBOX ((volatile struct MsLoadingMailbox*)(MS_TRACE_CONTROL_PHYS+MS_LOADING_TRACE_OFFSET))
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
void GhostTraceLoadingService(void){
    volatile struct MsLoadingMailbox*b=LOADBOX;unsigned write,next,iso[4];struct MsLoadingEntry entry;
    if(!admitted())return;
    sync_before_read((void*)b,32);
    if(b->magic!=MS_LOADING_TRACE_MAGIC||b->version!=MS_LOADING_TRACE_VERSION||b->nonce!=WRITER->response.nonce)return;
    write=b->writeSequence;next=b->readSequence;
    if(write-next>MS_LOADING_TRACE_COUNT)return;
    while(next!=write){
        volatile struct MsLoadingEntry*slot=&b->entries[next&(MS_LOADING_TRACE_COUNT-1)];
        sync_before_read((void*)slot,32);memcpy(&entry,(const void*)slot,32);
        if(entry.sequence!=next+1||!entry.phase||entry.phase>MS_LOAD_CANCEL||entry.reserved)break;
        ISOReadTiming(iso);MoonshineNetLogLoading(&entry,iso);++next;
    }
    b->readSequence=next;sync_after_write((void*)&b->readSequence,32);
}
#endif
static void prepareInit(void);
static int retireOwns(unsigned nonce,unsigned run);
static void retirePreserve(unsigned nonce,unsigned run);
static int retireRecover(unsigned nonce,unsigned run);
static int branchAsyncActive(void);
static int branchAsyncWork(void);
static int branchAsyncOwns(unsigned nonce,unsigned run);
static void branchAsyncService(void);
static int continueStart(const struct MsTraceRequest*);
static void branchInit(void);
static void exportInit(void);
void GhostTraceStorageInit(void) {
    const struct MoonshineGhostMemoryProof *proof=(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE;
    if(!admitted())return;
    sync_before_read((void*)proof,sizeof(*proof));
    memset((void*)MAILBOX,0,sizeof(*MAILBOX));
    memset((void*)FENCE_MAILBOX,0,sizeof(*FENCE_MAILBOX));
    sync_after_write((void*)FENCE_MAILBOX,sizeof(*FENCE_MAILBOX));memset(WRITER,0,sizeof(*WRITER));
    WRITER->response.magic=MS_TRACE_MAGIC;WRITER->response.version=MS_TRACE_VERSION;
    WRITER->response.nonce=proof->word[MGM_NONCE];publish();
    sync_after_write((void*)MAILBOX,96);
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    memset((void*)LOADBOX,0,sizeof(*LOADBOX));LOADBOX->magic=MS_LOADING_TRACE_MAGIC;
    LOADBOX->version=MS_LOADING_TRACE_VERSION;LOADBOX->nonce=WRITER->response.nonce;
    sync_after_write((void*)LOADBOX,sizeof(*LOADBOX));
#endif
    prepareInit();
    GhostTraceReadStorageInit(WRITER->response.nonce);
    branchInit();
    exportInit();
}
#include "GhostTracePrepareStorage.inc"
#include "GhostTraceBranchStorage.inc"
#include "GhostTraceRecoveryStorage.inc"
#include "GhostTraceExportStorage.inc"
#include "GhostTraceRetireStorage.inc"
#include "GhostTraceAsyncStorage.inc"
static int staleOldBank(unsigned run){
    const struct TraceWriter*w=WRITER;
    return w->parent[0]&&!w->response.ackChunk&&!w->headerWritten&&!w->chunk.sequence&&w->chunk.run&&run==w->chunk.run;
}
static int writerPending(void) {
    if(!admitted())return 0;
    sync_before_read((void*)&MAILBOX->request,96);
    return (MAILBOX->request.sequence && MAILBOX->request.sequence!=WRITER->response.ackRequest) ||
        (WRITER->active && !WRITER->failed && (WRITER->headerWritten || (!staleOldBank(MAILBOX->chunks[WRITER->response.ackChunk&1u].run)&&MAILBOX->chunks[WRITER->response.ackChunk&1u].sequence==WRITER->response.ackChunk+1)));
}
static void writerService(void) {
    struct TraceWriter *w=WRITER;struct MsTraceRequest request;struct MsTraceChunk candidate;unsigned next,index,part;const unsigned char *data;
    if(!admitted())return;
    sync_before_read((void*)&MAILBOX->request,96);memcpy(&request,(const void*)&MAILBOX->request,sizeof(request));
    if(request.sequence!=w->response.ackRequest){
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
        if(request.sequence!=w->request.sequence){
            TraceRequestStartedTick=read32(HW_TIMER);
        }
#endif
        if(request.magic!=MS_TRACE_MAGIC || request.version!=MS_TRACE_VERSION || request.nonce!=w->response.nonce ||
            !request.run || request.operation<MS_TRACE_START || request.operation>MS_TRACE_CONTINUE){
            w->response.ackRequest=request.sequence;fail(MS_TRACE_PROTOCOL);return;}
        if(request.operation==MS_TRACE_CONTINUE){continueStart(&request);return;}
        if(request.operation==MS_TRACE_START){
            if(branchAsyncActive()){w->response.ackRequest=request.sequence;w->response.error=MS_TRACE_BUSY;publish();return;}
            unsigned char header[64];FRESULT result;int n,warm;
#if MOONSHINE_LOADING_DIAGNOSTICS
            unsigned began=read32(HW_TIMER);
#endif
            if(w->active||w->recovery.phase||retireOwns(request.nonce,request.run)){w->response.ackRequest=request.sequence;fail(MS_TRACE_PROTOCOL);return;}
            w->request=request;w->response.ackRequest=request.sequence;w->response.phase=MS_TRACE_OPENING;
            w->response.error=0;w->response.ackChunk=w->response.bytes=0;w->offset=w->headerWritten=w->failed=w->owned=w->retained=0;memset(w->parent,0,sizeof(w->parent));memset(&w->chunk,0,sizeof(w->chunk));
            memset(&w->metrics,0,sizeof(w->metrics));
            if(!SusamuneCfgStorageAvailable()){fail(MS_TRACE_NO_STORAGE);return;}
            if(strlen(SusamuneCfgStoragePrefix())>sizeof(w->path)-70){fail(MS_TRACE_PROTOCOL);return;}
            warm=prepareTake(&request);if(warm<0){fail(MS_TRACE_IO);return;}
            if(!warm) {
                n=_sprintf(w->path,directoryFormat,SusamuneCfgStoragePrefix());
                if(n<0 || (unsigned)n>=sizeof(w->path)){fail(MS_TRACE_PROTOCOL);return;}
                result=f_mkdir_char(w->path);if(result!=FR_OK && result!=FR_EXIST){fail(MS_TRACE_IO);return;}
                n=_sprintf(w->path,fileFormat,SusamuneCfgStoragePrefix(),request.nonce,request.run);
                if(n<0 || (unsigned)n>=sizeof(w->path)){fail(MS_TRACE_PROTOCOL);return;}
                if(f_open_char(&w->file,w->path,FA_READ|FA_WRITE|FA_CREATE_NEW)!=FR_OK){fail(MS_TRACE_IO);return;}
            }
            w->active=w->owned=1;w->retained=warm!=0;
            if(warm&&f_lseek(&w->file,0)!=FR_OK){fail(MS_TRACE_IO);return;}
            w->headerHash=traceHeader(header,request.nonce,request.run,request.scene,request.capabilities,w->parent);
            if(!writeBytes(header,sizeof(header)))return;
            w->retained=0;
            w->response.phase=MS_TRACE_RECORDING;publish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
            MoonshineNetLogIo("trace_open",request.run,request.scene,w->response.bytes,read32(HW_TIMER)-began,0);
#endif
            return;
        }
        if(request.run!=w->request.run){w->response.ackRequest=request.sequence;fail(MS_TRACE_PROTOCOL);return;}
        if(request.operation==MS_TRACE_RETAIN){
            struct RetainPlan plan;
            if(request.capabilities!=w->request.capabilities||!retainInspect(request.run,&plan)){
                w->response.ackRequest=request.sequence;w->response.error=MS_TRACE_BUSY;publish();return;
            }
            retainMove(&plan);w->response.ackRequest=request.sequence;w->owned=w->failed=w->headerWritten=0;
            w->response.error=0;w->response.phase=MS_TRACE_DISCARDED;publish();return;
        }
        if(request.operation==MS_TRACE_DISCARD || request.operation==MS_TRACE_RELEASE || request.operation==MS_TRACE_RETIRE){
            FRESULT result;
#if MOONSHINE_LOADING_DIAGNOSTICS
            unsigned began=read32(HW_TIMER);
#endif
            if(request.operation==MS_TRACE_RETIRE&&(branchAsyncOwns(w->response.nonce,w->request.run)||branchPending()||SusamuneStateStoragePending()||
               GhostTraceReadStorageOwns(w->response.nonce,w->request.run)||
               (w->statePinValid&&w->statePin.parent.nonce==w->response.nonce&&w->statePin.parent.run==w->request.run)||
               !referenceCacheUnreferenced(w->response.nonce,w->request.run)))w->retained=1;
            if(request.operation==MS_TRACE_RETIRE&&retireDetach(&request)) {
                w->response.ackRequest=request.sequence;w->owned=w->failed=w->headerWritten=0;
                w->response.error=0;w->response.phase=MS_TRACE_DISCARDED;publish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
                MoonshineNetLogIo("trace_discard",request.run,request.operation,w->response.bytes,read32(HW_TIMER)-began,0);
#endif
                return;
            }
            if(w->active && f_close(&w->file)!=FR_OK){w->response.ackRequest=request.sequence;fail(MS_TRACE_IO);return;}
            w->active=0;result=w->owned&&!w->retained&&request.operation!=MS_TRACE_RELEASE?f_unlink_char(w->path):FR_OK;w->response.ackRequest=request.sequence;
            if(result!=FR_OK && result!=FR_NO_FILE){fail(MS_TRACE_IO);return;}
            w->owned=w->failed=0;w->response.error=0;w->response.phase=MS_TRACE_DISCARDED;w->headerWritten=0;publish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
            MoonshineNetLogIo("trace_discard",request.run,request.operation,w->response.bytes,read32(HW_TIMER)-began,0);
#endif
            return;
        }
        if(w->failed || !w->active){w->response.ackRequest=request.sequence;publish();return;}
        if(request.scene<w->response.ackChunk){w->response.ackRequest=request.sequence;fail(MS_TRACE_PROTOCOL);return;}
        w->request=request;
    }
    if(!w->active || w->failed)return;
    if(w->request.operation==MS_TRACE_FENCE && !w->headerWritten && w->response.ackChunk==w->request.scene){
        struct MsTraceFenceInfo fence;
        if(!w->response.ackChunk){w->response.ackRequest=w->request.sequence;fail(MS_TRACE_PROTOCOL);return;}
        if(f_sync(&w->file)!=FR_OK){w->response.ackRequest=w->request.sequence;fail(MS_TRACE_IO);return;}
        memset(&fence,0,sizeof(fence));fence.sequence=w->request.sequence;fence.fileBytes=w->response.bytes;
        fence.chunkOffset=w->chunkOffset;fence.recordBytes=w->chunk.bytes;fence.checksum=w->checksum;fence.headerHash=w->headerHash;
        memcpy((void*)FENCE_MAILBOX,&fence,sizeof(fence));sync_after_write((void*)FENCE_MAILBOX,32);
        w->response.ackRequest=w->request.sequence;w->request.operation=MS_TRACE_START;publish();return;
    }
    next=w->response.ackChunk+1;index=w->response.ackChunk&1u;
    if(!w->headerWritten){
        sync_before_read((void*)&MAILBOX->chunks[index],32);memcpy(&candidate,(const void*)&MAILBOX->chunks[index],32);
        if(staleOldBank(candidate.run))return;
        if(candidate.sequence!=next){
            if(w->request.operation==MS_TRACE_KEEP && w->response.ackChunk==w->request.scene){
                unsigned char end[32];char finalPath[160];FRESULT result;
                memset(end,0,sizeof(end));MsTracePut(end,0x444f4e45u);MsTracePut(end+4,w->request.run);
                MsTracePut(end+8,w->response.ackChunk);MsTracePut(end+12,w->response.bytes);MsTracePut(end+16,w->request.capabilities);
                MsTracePut(end+20,w->metrics.reserved[0]);MsTracePut(end+24,w->metrics.reserved[1]);MsTracePut(end+28,w->metrics.reserved[3]);
                if(!writeBytes(end,sizeof(end)))return;
                result=f_close(&w->file);
                if(result!=FR_OK){fail(MS_TRACE_IO);return;}
                w->active=0;
                strcpy(finalPath,w->path);strcpy(finalPath+strlen(finalPath)-4,completedSuffix);
                if(f_rename_char(w->path,finalPath)!=FR_OK){fail(MS_TRACE_IO);return;}
                w->owned=0;w->response.ackRequest=w->request.sequence;w->response.phase=MS_TRACE_SAVED;publish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
                MoonshineNetLogIo("trace_keep",w->request.run,w->response.ackChunk,w->response.bytes,read32(HW_TIMER)-TraceRequestStartedTick,0);
#endif
            }
            return;
        }
        if(((w->request.operation==MS_TRACE_KEEP || w->request.operation==MS_TRACE_FENCE) && next>w->request.scene) || candidate.run!=w->request.run || !candidate.bytes || candidate.bytes>MS_TRACE_BUFFER_BYTES ||
            candidate.reserved[0] || candidate.reserved[1]){fail(MS_TRACE_PROTOCOL);return;}
        w->chunk=candidate;
        {
            unsigned char header[32];unsigned i;const unsigned *words=(const unsigned*)&w->chunk;
            w->chunkOffset=w->response.bytes;
            for(i=0;i<8;++i)MsTracePut(header+4*i,words[i]);
            MsTracePut(header+24,1);MsTracePut(header+28,MS_TRACE_PACK_BLOCK);
            if(!writeBytes(header,sizeof(header)))return;
        }
        w->offset=0;w->checksum=2166136261u;w->headerWritten=1;
    }
    data=(const unsigned char*)((index?MS_TRACE_BUFFER1_PPC:MS_TRACE_BUFFER0_PPC)&0x7fffffffu);
    part=w->chunk.bytes-w->offset;if(part>MS_TRACE_PACK_BLOCK)part=MS_TRACE_PACK_BLOCK;
    sync_before_read((void*)(data+w->offset),part);
    {
        unsigned before,elapsed,stored;int packed;unsigned char header[8];
        unsigned char *output=(unsigned char*)(MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_OUTPUT_OFFSET);
        const unsigned char *payload=data+w->offset;
        if(part>MS_TRACE_FILE_LIMIT-w->metrics.reserved[2]){fail(MS_TRACE_LIMIT);return;}
        before=read32(HW_TIMER);
        packed=MsTraceCompress((void*)MS_TRACE_PACK_WORK_PHYS,payload,part,output);
        elapsed=read32(HW_TIMER)-before;
        if(elapsed>w->metrics.reserved[0])w->metrics.reserved[0]=elapsed;
        w->metrics.reserved[1]+=elapsed;w->metrics.reserved[2]+=part;++w->metrics.reserved[3];
        stored=part;
        if(packed>0 && (unsigned)packed<part){stored=(unsigned)packed;payload=output;sync_after_write(output,stored);}
        MsTracePut(header,part);MsTracePut(header+4,stored|(payload==output?0x80000000u:0));
        if(!writeBytes(header,sizeof(header))||!writeBytes(payload,stored))return;
    }
    w->checksum=MsTraceHash(w->checksum,data+w->offset,part);w->offset+=part;
    if(w->offset==w->chunk.bytes){
        if(w->checksum!=w->chunk.checksum){fail(MS_TRACE_PROTOCOL);return;}
        w->headerWritten=0;w->response.ackChunk=next;++w->metrics.chunks;w->metrics.lastChecksum=w->checksum;
    }
    publish();
}
static unsigned retirementPermitFlags(void) {
    const struct TraceLink*l=&WRITER->prepare.link;
    return MS_TRACE_PREPARE_READY_FLAG|((branchAsyncActive()&&retireRetaining(&WRITER->retiring)&&
        retireOwns(l->branch.parent.nonce,l->branch.parent.run))?MS_TRACE_PREPARE_METADATA_FLAG:0u);
}
int GhostTraceBackgroundPending(void) {
    return admitted()&&!WRITER->recovery.phase&&TimerDiffTicks(DILastReadTick)>=1898437u/4u&&
        ((!branchAsyncActive()&&referenceCachePending())||
        (prepareWork()&&prepareAdmitted(MS_TRACE_PREPARE_READY_FLAG))||
        (retireWork()&&prepareAdmitted(retirementPermitFlags()))||
        (branchAsyncWork()&&prepareAdmitted(MS_TRACE_PREPARE_READY_FLAG|MS_TRACE_PREPARE_METADATA_FLAG)));
}
void GhostTraceBackgroundService(void) {
    if(!GhostTraceBackgroundPending())return;
    // Admit newly posted game reads before starting any optional FAT operation.
    _ahbMemFlush(1);DIUpdateRegisters();
    if(!DI_IRQ&&DiscCheckAsync()&&GhostTraceBackgroundPending()) {
        if(writerPending()||GhostTraceReadStoragePending()||branchPending()||exportPending()||prepareDoorbell())return;
        if(retireWork()&&prepareAdmitted(retirementPermitFlags()))retireService();
        else if(branchAsyncWork()&&prepareAdmitted(MS_TRACE_PREPARE_READY_FLAG|MS_TRACE_PREPARE_METADATA_FLAG))branchAsyncService();
        else if(prepareWork()&&prepareAdmitted(MS_TRACE_PREPARE_READY_FLAG))prepareService();else if(!branchAsyncActive())referenceCacheService();
    }
}
int GhostTraceStoragePending(void) {
    return admitted() && (WRITER->recovery.phase==RECOVERY_FAILED || prepareDoorbell() || writerPending() || GhostTraceReadStoragePending() || branchPending() || exportPending());
}
void GhostTraceStorageService(void) {
    int writer;
    if(!admitted())return;
    if(WRITER->recovery.phase==RECOVERY_FAILED){GhostTraceStateReferenceCancel();return;}
    writer=writerPending();
    if(!writer&&!GhostTraceReadStoragePending()&&prepareDoorbell()){prepareReceive();return;}
    if(branchPending() && !writer){branchService();return;}
    if(exportPending() && !writer){exportService();return;}
    if(!GhostTraceReadStorageService(writer) && writer)writerService();
}
#endif
