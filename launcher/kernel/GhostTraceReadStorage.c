#include "GhostTraceReadStorage.h"
#include "GhostTraceBranchStorage.h"
#if MOONSHINE_GHOST_TRACE
#include "global.h"
#include "SusamuneCfg.h"
#include "ff_utf8.h"
#include "susamune/ghost_trace_stream_storage.h"
#include "susamune/ghost_trace_compression.h"
#include <string.h>

struct TraceReader {
    FIL file;
    unsigned active,failed,fileNonce,run,region,fileSize,sequence,seenNonce;
    struct MsTraceReadResponse response;
};
struct TraceReaders {
    struct TraceReader stream[MS_TRACE_READ_CHANNELS];
    unsigned nonce,next,writerSlices;
    char path[160];
    unsigned char header[64] ALIGNED(32);
};
typedef char TraceReadersFit[sizeof(struct TraceReaders)<=MS_TRACE_READ_ARM_BYTES?1:-1];
#define READERS ((struct TraceReaders*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_READ_ARM_OFFSET))
#define READ_MAILBOX(i) ((volatile struct MsTraceReadMailbox*)MS_TRACE_READ_MAILBOX_PHYS(i))
static unsigned initialized;
static const char readPath[] __attribute__((section(".text.trace_names")))="%s" MOONSHINE_RECORDINGS_DIR "/trace_%08X_%08X.msgt";

__attribute__((weak)) int GhostTraceReadStorageWindow(unsigned channel,unsigned nonce,unsigned lease,
                                                     struct GhostTraceReadWindow *window) {
    (void)channel;(void)nonce;(void)lease;(void)window;return 0;
}
static unsigned word(const unsigned char *p) {
    return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3];
}
static unsigned bootNonce(void) {
    const struct MoonshineGhostMemoryProof *proof=(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE;
    sync_before_read((void*)proof,sizeof(*proof));return proof->word[MGM_NONCE];
}
static int closeReader(struct TraceReader *s) {
    if(s->active && f_close(&s->file)!=FR_OK){s->failed=1;return 0;}
    s->active=s->failed=0;return 1;
}
static void publish(unsigned channel,unsigned sequence,unsigned status,unsigned bytes,unsigned lease,unsigned requestNonce) {
    struct TraceReader *s=&READERS->stream[channel];
    struct MsTraceReadResponse *r=&s->response;
    r->magic=MS_TRACE_READ_MAGIC;r->version=MS_TRACE_READ_VERSION;r->bootNonce=READERS->nonce;
    s->seenNonce=requestNonce;
    r->ack=sequence;r->status=status;r->bytes=bytes;r->fileSize=s->active?s->fileSize:0;r->lease=lease;
    memcpy((void*)&READ_MAILBOX(channel)->response,r,sizeof(*r));
    sync_after_write((void*)&READ_MAILBOX(channel)->response,sizeof(*r));
}
void GhostTraceReadStorageInit(unsigned nonce) {
    unsigned i;
    for(i=0;i<MS_TRACE_READ_CHANNELS;++i){
        struct TraceReader *s=&READERS->stream[i];
        if(!initialized || closeReader(s))memset(s,0,sizeof(*s));
        s->sequence=0;
    }
    READERS->nonce=nonce;READERS->next=READERS->writerSlices=0;
    for(i=0;i<MS_TRACE_READ_CHANNELS;++i){
        if(!initialized){memset((void*)READ_MAILBOX(i),0,sizeof(struct MsTraceReadMailbox));
            sync_after_write((void*)READ_MAILBOX(i),sizeof(struct MsTraceReadMailbox));}
        publish(i,0,READERS->stream[i].failed?MS_TRACE_READ_IO:MS_TRACE_READ_OK,0,0,0);
    }
    initialized=1;
}
static int pending(unsigned i) {
    volatile struct MsTraceReadMailbox *m=READ_MAILBOX(i);
    sync_before_read((void*)m,64);
    return m->request.sequence && (m->request.sequence!=READERS->stream[i].response.ack ||
        m->request.bootNonce!=READERS->stream[i].seenNonce);
}
int GhostTraceReadStoragePending(void) {
    return initialized && (bootNonce()!=READERS->nonce || pending(0) || pending(1));
}
int GhostTraceReadStorageActive(void) {
    return initialized&&(READERS->stream[0].active||READERS->stream[1].active);
}
int GhostTraceReadStorageOwns(unsigned nonce,unsigned run) {
    unsigned i;
    if(initialized)for(i=0;i<MS_TRACE_READ_CHANNELS;++i){
        const struct TraceReader *s=&READERS->stream[i];
        if(s->active && s->fileNonce==nonce && s->run==run)return 1;
    }
    return 0;
}
static int readAt(struct TraceReader *s,unsigned offset,void *data,unsigned bytes) {
    UINT done=0;
    return f_lseek(&s->file,offset)==FR_OK && f_read(&s->file,data,bytes,&done)==FR_OK && done==bytes;
}
static unsigned openReader(struct TraceReader *s,const struct MsTraceReadRequest *q) {
    unsigned char *h=READERS->header;unsigned capabilities,version;int n;
    static const unsigned games[]={0x474d534au,0x474d5345u,0x474d5350u};
    if(!closeReader(s))return MS_TRACE_READ_IO;
    if(!SusamuneCfgStorageAvailable() || strlen(SusamuneCfgStoragePrefix())>sizeof(READERS->path)-40)return MS_TRACE_READ_IO;
    n=_sprintf(READERS->path,readPath,SusamuneCfgStoragePrefix(),q->fileNonce,q->run);
    if(n<0 || (unsigned)n>=sizeof(READERS->path))return MS_TRACE_READ_PROTOCOL;
    if(f_open_char(&s->file,READERS->path,FA_READ|FA_OPEN_EXISTING)!=FR_OK)return MS_TRACE_READ_IO;
    s->active=1;s->fileNonce=q->fileNonce;s->run=q->run;s->region=q->region;
    if(f_size(&s->file)<96 || f_size(&s->file)>MS_TRACE_FILE_LIMIT)return MS_TRACE_READ_FILE;
    s->fileSize=(unsigned)f_size(&s->file);
    if(!readAt(s,0,h,64))return MS_TRACE_READ_IO;
    version=word(h+4);capabilities=word(h+28);
    if(word(h)!=MS_TRACE_MAGIC || !version || version>MS_TRACE_FILE_VERSION || word(h+8)!=64 ||
        word(h+12)!=games[q->region-1] || word(h+16)!=q->fileNonce || word(h+20)!=q->run ||
        (capabilities&0xff000000u) || word(h+32)!=MS_TRACE_BUFFER_BYTES ||
        word(h+60)!=MsTraceHash(2166136261u,h,60))return MS_TRACE_READ_FILE;
    if(!GhostTraceChildDependencyValid(h,q->fileNonce,q->run,games[q->region-1]))return MS_TRACE_READ_FILE;
    if(!readAt(s,s->fileSize-32,h,32))return MS_TRACE_READ_IO;
    if(word(h)!=0x444f4e45u || word(h+4)!=q->run || word(h+12)!=s->fileSize-32 ||
        word(h+16)!=capabilities || word(h+8)>(s->fileSize-96)/32)return MS_TRACE_READ_FILE;
    return MS_TRACE_READ_OK;
}
static int destination(unsigned channel,const struct MsTraceReadBuffer *b) {
    struct GhostTraceReadWindow w;
    const unsigned first=MOONSHINE_GHOST_UPPER_PHYS_BASE+MOONSHINE_GHOST_CORE_SIZE;
    const unsigned end=MOONSHINE_GHOST_UPPER_PHYS_BASE+MOONSHINE_GHOST_UPPER_SIZE;
    if(!b->bytes || b->bytes>MS_TRACE_READ_MAX_BYTES || !b->lease ||
        (b->physical&31u) || b->capacity!=((b->bytes+31u)&~31u) ||
        !GhostTraceReadStorageWindow(channel,READERS->nonce,b->lease,&w))return 0;
    /* Only admitted upper data windows exist today; code/control/codec stay out. */
    return w.physical>=first && w.physical<end && w.bytes && w.bytes<=end-w.physical &&
        !(w.physical<MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES &&
          w.physical+w.bytes>MS_TRACE_CONTROL_PHYS) &&
        b->physical>=w.physical && b->physical-w.physical<=w.bytes &&
        b->capacity<=w.bytes-(b->physical-w.physical);
}
static void service(unsigned channel) {
    struct TraceReader *s=&READERS->stream[channel];
    struct MsTraceReadRequest q;struct MsTraceReadBuffer b;unsigned status=MS_TRACE_READ_PROTOCOL,bytes=0;
    volatile struct MsTraceReadMailbox *m=READ_MAILBOX(channel);
    sync_before_read((void*)m,64);memcpy(&q,(const void*)&m->request,sizeof(q));memcpy(&b,(const void*)&m->buffer,sizeof(b));
    if(q.sequence<=s->sequence || q.magic!=MS_TRACE_READ_MAGIC || q.version!=MS_TRACE_READ_VERSION ||
        !q.fileNonce || !q.run || q.region<MS_TRACE_READ_JP || q.region>MS_TRACE_READ_PAL ||
        b.reserved[0] || b.reserved[1] || b.reserved[2] || !b.lease)goto done;
    s->sequence=q.sequence;
    if(!READERS->nonce || q.bootNonce!=READERS->nonce){status=MS_TRACE_READ_EPOCH;goto done;}
    if(q.operation==MS_TRACE_READ_OPEN){
        if(b.physical || b.capacity || b.bytes || b.offset)goto done;
        status=openReader(s,&q);
    }else if(!s->active || q.fileNonce!=s->fileNonce || q.run!=s->run || q.region!=s->region)goto done;
    else if(q.operation==MS_TRACE_READ_CLOSE){
        if(b.physical || b.capacity || b.bytes || b.offset)goto done;
        status=closeReader(s)?MS_TRACE_READ_OK:MS_TRACE_READ_IO;
    }else if(q.operation==MS_TRACE_READ_DATA){
        if(s->failed){status=MS_TRACE_READ_IO;goto done;}
        if(b.offset>s->fileSize || b.bytes>s->fileSize-b.offset || f_size(&s->file)!=s->fileSize){status=MS_TRACE_READ_FILE;goto done;}
        if(!destination(channel,&b)){status=MS_TRACE_READ_DESTINATION;goto done;}
        sync_before_read((void*)b.physical,b.capacity);
        status=readAt(s,b.offset,(void*)b.physical,b.bytes)?MS_TRACE_READ_OK:MS_TRACE_READ_IO;
        sync_after_write((void*)b.physical,b.capacity);
        if(status==MS_TRACE_READ_OK && bootNonce()!=READERS->nonce)status=MS_TRACE_READ_EPOCH;
        if(status==MS_TRACE_READ_OK && !destination(channel,&b))status=MS_TRACE_READ_DESTINATION;
        if(status==MS_TRACE_READ_OK)bytes=b.bytes;
    }
done:
    if(status!=MS_TRACE_READ_OK && !closeReader(s))status=MS_TRACE_READ_IO;
    publish(channel,q.sequence,status,bytes,b.lease,q.bootNonce);
}
int GhostTraceReadStorageService(int writerPending) {
    unsigned i,nonce;
    if(!GhostTraceReadStoragePending())return 0;
    if(writerPending && READERS->writerSlices++<3)return 0;
    READERS->writerSlices=0;nonce=bootNonce();
    if(nonce!=READERS->nonce){
        GhostTraceReadStorageInit(nonce);
        for(i=0;i<MS_TRACE_READ_CHANNELS;++i){
            volatile struct MsTraceReadMailbox *m=READ_MAILBOX(i);
            sync_before_read((void*)m,64);
            publish(i,m->request.sequence,MS_TRACE_READ_EPOCH,0,m->buffer.lease,m->request.bootNonce);
        }
        return 1;
    }
    for(i=0;i<MS_TRACE_READ_CHANNELS;++i){
        unsigned channel=(READERS->next+i)&1u;
        if(pending(channel)){service(channel);READERS->next=channel^1u;return 1;}
    }
    return 0;
}
#endif
