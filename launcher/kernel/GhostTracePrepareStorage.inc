#define PREPBOX ((volatile struct MsTracePrepareMailbox*)MS_TRACE_PREPARE_PHYS)
static unsigned traceHeader(unsigned char h[64],unsigned nonce,unsigned run,unsigned scene,unsigned capabilities,const unsigned*parent) {
    unsigned hash;memset(h,0,64);MsTracePut(h,MS_TRACE_MAGIC);MsTracePut(h+4,MS_TRACE_FILE_VERSION);MsTracePut(h+8,64);
    MsTracePut(h+12,GAME_ID);MsTracePut(h+16,nonce);MsTracePut(h+20,run);MsTracePut(h+24,scene);
    MsTracePut(h+28,capabilities);MsTracePut(h+32,MS_TRACE_BUFFER_BYTES);
    if(parent&&parent[0]){MsTracePut(h+36,MS_TRACE_BRANCH_HEADER_FLAGS);MsTracePut(h+40,MS_TRACE_PROVENANCE_TAG);
        MsTracePut(h+44,MS_TRACE_BRANCH_HEADER_TAG);MsTracePut(h+48,parent[0]);MsTracePut(h+52,parent[1]);MsTracePut(h+56,parent[2]);}
    hash=MsTraceHash(2166136261u,h,60);MsTracePut(h+60,hash);return hash;
}
static void prepareReply(unsigned ack,unsigned phase,unsigned status,unsigned run,unsigned ownerSequence) {
    volatile struct MsTracePrepareResponse*r=&PREPBOX->response;
    r->ack=ack;r->phase=phase;r->status=status|(WRITER->retiring.phase?MS_TRACE_RETIRE_PENDING:0u);r->run=run;r->ownerSequence=ownerSequence;
    sync_after_write((void*)r,32);
}
static void preparePublish(void) {
    struct TracePrepare*p=&WRITER->prepare;
    prepareReply(PREPBOX->response.ack,p->phase,p->error,p->request.run,p->request.sequence);
}
static void prepareInit(void) {
    memset((void*)PREPBOX,0,sizeof(*PREPBOX));sync_after_write((void*)PREPBOX,sizeof(*PREPBOX));
    PREPBOX->response.magic=MS_TRACE_PREPARE_MAGIC;PREPBOX->response.version=MS_TRACE_PREPARE_VERSION;
    PREPBOX->response.bootNonce=WRITER->response.nonce;prepareReply(0,MS_PREP_IDLE,0,0,0);
}
static int prepareDoorbell(void) {
    sync_before_read((void*)&PREPBOX->request,32);
    return PREPBOX->request.sequence&&PREPBOX->request.sequence!=PREPBOX->response.ack;
}
static void prepareReceive(void) {
    struct TracePrepare*p=&WRITER->prepare;struct MsTracePrepareRequest q;
    sync_before_read((void*)&PREPBOX->request,32);memcpy(&q,(const void*)&PREPBOX->request,32);
    if(!q.sequence||q.sequence==PREPBOX->response.ack)return;
    if(q.magic!=MS_TRACE_PREPARE_MAGIC||q.version!=MS_TRACE_PREPARE_VERSION||q.bootNonce!=WRITER->response.nonce||
       q.operation<MS_PREP_HELLO||q.operation>MS_PREP_CANCEL||(q.capabilities&0xff000000u)||
       (q.operation==MS_PREP_HELLO?(q.run||q.capabilities||q.target):!q.run)||(q.operation==MS_PREP_CANCEL&&q.capabilities)) {
        prepareReply(q.sequence,MS_PREP_FAILED,MS_PREP_PROTOCOL,q.run,0);return;
    }
    if(p->phase==MS_PREP_LINKING&&q.operation!=MS_PREP_HELLO){prepareReply(q.sequence,p->phase,MS_PREP_BUSY,p->request.run,p->request.sequence);return;}
    if(q.operation==MS_PREP_HELLO){prepareReply(q.sequence,p->phase,p->error,p->request.run,p->request.sequence);return;}
    if(q.operation==MS_PREP_CANCEL) {
        if(q.run!=p->request.run||q.target!=p->request.sequence){prepareReply(q.sequence,MS_PREP_FAILED,MS_PREP_PROTOCOL,q.run,0);return;}
        p->phase=MS_PREP_CANCELED;p->error=0;if(p->active==2)p->active=1;
        prepareReply(q.sequence,p->phase,0,q.run,p->request.sequence);return;
    }
    if(q.target){prepareReply(q.sequence,MS_PREP_FAILED,MS_PREP_PROTOCOL,q.run,0);return;}
    if(q.run==p->request.run) {
        if(q.capabilities!=p->request.capabilities){p->phase=MS_PREP_FAILED;p->error=MS_PREP_PROTOCOL;}
        p->request.sequence=q.sequence;prepareReply(q.sequence,p->phase,p->error,q.run,p->request.sequence);return;
    }
    if(p->active){prepareReply(q.sequence,p->phase,p->active==2?MS_PREP_IO:MS_PREP_BUSY,p->request.run,p->request.sequence);return;}
    memset(p,0,sizeof(*p));p->request=q;
    p->phase=WRITER->request.run==q.run&&WRITER->response.phase!=MS_TRACE_OPENING?MS_PREP_CONSUMED:MS_PREP_MKDIR;
    prepareReply(q.sequence,p->phase,0,q.run,q.sequence);
}
static void prepareFailed(unsigned error) {
    struct TracePrepare*p=&WRITER->prepare;p->phase=MS_PREP_FAILED;p->error=error;preparePublish();
}
static int prepareWork(void) {
    const struct TracePrepare*p=&WRITER->prepare;
    return (p->phase>=MS_PREP_MKDIR&&p->phase<=MS_PREP_SYNC)||
        (p->active==1&&(p->phase==MS_PREP_FAILED||p->phase==MS_PREP_CANCELED));
}
static int prepareAdmitted(unsigned allowed) {
    struct TracePrepare*p=&WRITER->prepare;struct MsTracePreparePermit q;unsigned now=read32(HW_TIMER);
    sync_before_read((void*)&PREPBOX->permit,32);memcpy(&q,(const void*)&PREPBOX->permit,32);
    if(q.magic!=MS_TRACE_PREPARE_MAGIC||q.version!=MS_TRACE_PREPARE_VERSION||q.bootNonce!=WRITER->response.nonce||
       !q.sequence||!(q.flags&allowed)||(q.flags&~(MS_TRACE_PREPARE_READY_FLAG|MS_TRACE_PREPARE_METADATA_FLAG))||q.queued>MS_TRACE_PREPARE_MAX_QUEUED||q.reserved)return 0;
    if(p->permitSequence!=q.sequence){p->permitReady=p->permitSequence&&now-p->permitTick<1898437u/4u;p->permitSequence=q.sequence;p->permitTick=now;}
    return p->permitReady&&now-p->permitTick<1898437u/4u&&!GhostTraceReadStorageActive();
}
static void prepareService(void) {
    struct TracePrepare*p=&WRITER->prepare;unsigned char h[64];char*suffix;UINT done=0;FRESULT r;int n;
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    unsigned before=read32(HW_TIMER),phase=p->phase;
#endif
    if(p->phase==MS_PREP_FAILED||p->phase==MS_PREP_CANCELED) {
        // Keep incomplete files; a failed close never releases its FIL ownership.
        if(p->active==1){if(f_close(&p->file)==FR_OK)p->active=0;else{p->active=2;p->error=MS_PREP_IO;}}
        preparePublish();return;
    }
    if(!SusamuneCfgStorageAvailable()){prepareFailed(MS_PREP_IO);return;}
    if(p->phase==MS_PREP_MKDIR) {
        if(strlen(SusamuneCfgStoragePrefix())>sizeof(p->path)-70){prepareFailed(MS_PREP_PROTOCOL);return;}
        n=_sprintf(p->path,directoryFormat,SusamuneCfgStoragePrefix());
        if(n<0||(unsigned)n>=sizeof(p->path)){prepareFailed(MS_PREP_PROTOCOL);return;}
        r=f_mkdir_char(p->path);if(r!=FR_OK&&r!=FR_EXIST){prepareFailed(MS_PREP_IO);return;}
        _sprintf(p->path,fileFormat,SusamuneCfgStoragePrefix(),p->request.bootNonce,p->request.run);p->phase=MS_PREP_CHECK;
    } else if(p->phase==MS_PREP_CHECK) {
        suffix=p->path+strlen(p->path)-4;memcpy(suffix,completedSuffix,4);
        r=f_open_char(&p->file,p->path,FA_READ|FA_OPEN_EXISTING);
        memcpy(suffix,"part",4);
        if(r==FR_OK){p->active=1;prepareFailed(MS_PREP_CONFLICT);return;}
        if(r!=FR_NO_FILE&&r!=FR_NO_PATH){prepareFailed(MS_PREP_IO);return;}p->phase=MS_PREP_CREATE;
    } else if(p->phase==MS_PREP_CREATE) {
        if(f_open_char(&p->file,p->path,FA_READ|FA_WRITE|FA_CREATE_NEW)!=FR_OK){prepareFailed(MS_PREP_IO);return;}
        p->active=p->created=1;p->phase=MS_PREP_HEADER;
    } else if(p->phase==MS_PREP_HEADER) {
        p->headerHash=traceHeader(h,p->request.bootNonce,p->request.run,MS_TRACE_PREPARE_UNKNOWN_SCENE,p->request.capabilities,0);
        if(f_write(&p->file,h,64,&done)!=FR_OK||done!=64){prepareFailed(MS_PREP_IO);return;}p->phase=MS_PREP_SYNC;
    } else if(p->phase==MS_PREP_SYNC) {
        if(f_sync(&p->file)!=FR_OK){prepareFailed(MS_PREP_IO);return;}p->phase=MS_PREP_READY;
    }
    preparePublish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    MoonshineNetLogIo("trace_prep",p->request.run,phase,64,read32(HW_TIMER)-before,p->error);
#endif
}
// 1 moves the owned FIL, 0 keeps the original create path, -1 preserves a conflict.
static int prepareTakeInto(const struct MsTraceRequest*q,FIL*file,char*path) {
    struct TracePrepare*p=&WRITER->prepare;unsigned char actual[64],expected[64];unsigned bytes;UINT done=0;
    if(prepareDoorbell())prepareReceive();
    if(p->request.run!=q->run||p->request.bootNonce!=q->nonce)return 0;
    if(p->error||p->phase==MS_PREP_CANCELED||p->phase==MS_PREP_FAILED||p->phase==MS_PREP_CONSUMED||
       p->request.capabilities!=q->capabilities)return -1;
    if(!p->active){p->phase=MS_PREP_CONSUMED;preparePublish();return 0;}
    if(!p->created)return -1;
    bytes=f_size(&p->file);
    if(bytes!=0&&bytes!=64){prepareFailed(MS_PREP_SOURCE);return -1;}
    if(bytes==64) {
        traceHeader(expected,q->nonce,q->run,MS_TRACE_PREPARE_UNKNOWN_SCENE,q->capabilities,0);
        if(f_lseek(&p->file,0)!=FR_OK||f_read(&p->file,actual,64,&done)!=FR_OK||done!=64||memcmp(actual,expected,64)) {
            prepareFailed(MS_PREP_SOURCE);return -1;
        }
    } else if(p->phase!=MS_PREP_HEADER){prepareFailed(MS_PREP_SOURCE);return -1;}
    *file=p->file;strcpy(path,p->path);p->active=p->created=0;p->phase=MS_PREP_CONSUMED;preparePublish();
    return 1;
}

static int prepareTake(const struct MsTraceRequest*q){return prepareTakeInto(q,&WRITER->file,WRITER->path);}
