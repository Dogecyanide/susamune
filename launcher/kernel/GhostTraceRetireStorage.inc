static unsigned retireClusterBytes(const FIL*);
enum { RETIRE_NONE, RETIRE_HEADER, RETIRE_TAIL, RETIRE_CLOSE, RETIRE_DELETE, RETIRE_CLOSE_FAILED,
    RETAIN_TRUNCATE, RETAIN_FOOTER, RETAIN_SYNC, RETAIN_CLOSE, RETAIN_RENAME, RETAIN_FAILED, RETAIN_CLOSE_FAILED };
static int retireRetaining(const struct TraceRetire*r){return r->phase>=RETAIN_TRUNCATE;}
static unsigned retireNonce(const struct TraceRetire*r){return retireRetaining(r)?WRITER->response.nonce:r->nonce;}
struct RetainPlan {unsigned bytes,chunks,maximum,total,blocks;};
static int retainInspect(unsigned run,struct RetainPlan*out) {
    struct TraceWriter*w=WRITER;struct MsTraceFenceInfo f;unsigned char raw[64],expected[64];UINT done=0;unsigned partial=0,boundary;int readOk;char path[160];
    if(w->retiring.phase||!w->active||!w->owned||w->failed||w->recovery.phase||w->request.run!=run||
       w->response.phase!=MS_TRACE_RECORDING||w->request.operation!=MS_TRACE_START||!w->response.ackChunk||!retireClusterBytes(&w->file))return 0;
    memcpy(&f,(const void*)FENCE_MAILBOX,sizeof(f));boundary=w->headerWritten?w->chunkOffset:w->response.bytes;
    if(!f.sequence||f.sequence!=w->response.ackRequest||f.headerHash!=w->headerHash||
       f.fileBytes<64||f.fileBytes>boundary||f.chunkOffset<64||f.chunkOffset>=f.fileBytes||
       f.recordBytes==0||f.recordBytes>MS_TRACE_BUFFER_BYTES||f.reserved[0]||f.reserved[1]||
       boundary<64||boundary>MS_TRACE_FILE_LIMIT-32||f_size(&w->file)!=w->response.bytes)return 0;
    if(w->headerWritten){
        if(w->offset>=w->chunk.bytes||w->offset%MS_TRACE_PACK_BLOCK)return 0;
        partial=w->offset/MS_TRACE_PACK_BLOCK;
    }
    if(partial>w->metrics.reserved[3]||strlen(SusamuneCfgStoragePrefix())>sizeof(path)-70)return 0;
    _sprintf(path,fileFormat,SusamuneCfgStoragePrefix(),w->response.nonce,run);if(strcmp(path,w->path))return 0;
    readOk=f_lseek(&w->file,0)==FR_OK&&f_read(&w->file,raw,64,&done)==FR_OK&&done==64;
    // Refusal may resume the old writer; never leave its cursor in the prefix.
    if(f_lseek(&w->file,w->response.bytes)!=FR_OK){fail(MS_TRACE_IO);return 0;}
    if(!readOk)return 0;
    traceHeader(expected,w->response.nonce,run,MsTraceGet(raw+24),w->request.capabilities,w->parent);
    if(memcmp(raw,expected,64)||MsTraceGet(raw+60)!=w->headerHash)return 0;
    out->bytes=boundary;out->chunks=w->response.ackChunk;out->maximum=w->metrics.reserved[0];
    out->total=w->metrics.reserved[1];out->blocks=w->metrics.reserved[3]-partial;return 1;
}
static void retainMove(const struct RetainPlan*p) {
    struct TraceWriter*w=WRITER;struct TraceRetire*r=&w->retiring;
    r->file=w->file;r->run=w->request.run;r->bytes=p->bytes;r->capabilities=w->request.capabilities&0xffffffu;
    // Retained phases borrow these deletion-only scalars for their footer.
    r->headerHash=p->chunks;r->preserve=p->maximum;r->generation=p->total;r->nonce=p->blocks;
    r->phase=RETAIN_TRUNCATE;w->active=0;preparePublish();
}
static void retainService(void) {
    struct TraceRetire*r=&WRITER->retiring;unsigned char end[32];char path[160],target[160];UINT done=0;int result=FR_OK;
    if(r->phase==RETAIN_TRUNCATE){
        if(f_size(&r->file)<r->bytes||f_lseek(&r->file,r->bytes)!=FR_OK)result=FR_INVALID_OBJECT;
        else if(f_size(&r->file)!=r->bytes)result=f_truncate(&r->file);
        if(result==FR_OK)r->phase=RETAIN_FOOTER;
    }else if(r->phase==RETAIN_FOOTER){
        memset(end,0,32);MsTracePut(end,0x444f4e45u);MsTracePut(end+4,r->run);MsTracePut(end+8,r->headerHash);
        MsTracePut(end+12,r->bytes);MsTracePut(end+16,r->capabilities);MsTracePut(end+20,r->preserve);
        MsTracePut(end+24,r->generation);MsTracePut(end+28,r->nonce);
        result=f_write(&r->file,end,32,&done);if(result==FR_OK&&done!=32)result=FR_DISK_ERR;
        if(result==FR_OK)r->phase=RETAIN_SYNC;
    }else if(r->phase==RETAIN_SYNC){result=f_sync(&r->file);if(result==FR_OK)r->phase=RETAIN_CLOSE;
    }else if(r->phase==RETAIN_CLOSE){
        result=f_close(&r->file);r->phase=result==FR_OK?RETAIN_RENAME:RETAIN_CLOSE_FAILED;
    }else if(r->phase==RETAIN_RENAME){
        _sprintf(path,fileFormat,SusamuneCfgStoragePrefix(),WRITER->response.nonce,r->run);
        _sprintf(target,sourceFormat,SusamuneCfgStoragePrefix(),WRITER->response.nonce,r->run);
        result=f_rename_char(path,target);if(result==FR_OK)r->phase=RETIRE_NONE;
    }
    if(result!=FR_OK&&r->phase!=RETAIN_CLOSE_FAILED)r->phase=RETAIN_FAILED;
    preparePublish();
}
static int retireOwns(unsigned nonce,unsigned run) {
    const struct TraceRetire*r=&WRITER->retiring;
    return r->phase&&retireNonce(r)==nonce&&r->run==run;
}
static void retirePreserve(unsigned nonce,unsigned run) {
    if(retireOwns(nonce,run)&&!retireRetaining(&WRITER->retiring))WRITER->retiring.preserve=1;
}
static unsigned retireClusterBytes(const FIL*f) {
    const FATFS*fs=f->obj.fs;unsigned sector;
    if(!fs||!fs->fs_type||f->obj.id!=fs->id)return 0;
#if _MAX_SS == _MIN_SS
    sector=_MAX_SS;
#else
    sector=fs->ssize;
#endif
    if(sector<512||sector>4096||(sector&(sector-1))||!fs->csize)return 0;
    sector*=fs->csize;return sector<=0x80000u?sector:0;
}
static int retireOtherBranch(const struct MsTraceBranchRequest*owned){
    struct MsTraceBranchRequest current;
    if(!branchPending())return 0;
    if(!owned||WRITER->branchDeleting)return 1;
    sync_before_read((void*)&BRANCHBOX->request,32);memcpy(&current,(const void*)&BRANCHBOX->request,32);
    return owned->operation!=MS_TRACE_BRANCH_ASYNC_CONTINUE||owned->nonce||owned->run!=WRITER->request.run||
        memcmp(owned,&current,sizeof(current));
}
static int retireDetachOwned(const struct MsTraceRequest*q,const struct MsTraceBranchRequest*owned) {
    struct TraceWriter*w=WRITER;struct TraceRetire*r=&w->retiring;char path[160];unsigned cluster;
    if(r->phase||!w->active||!w->owned||w->retained||w->failed||w->response.phase!=MS_TRACE_RECORDING||
       w->request.operation!=MS_TRACE_START||q->capabilities!=w->request.capabilities||w->recovery.phase||retireOtherBranch(owned)||
       SusamuneStateStoragePending()||
       GhostTraceReadStorageOwns(w->response.nonce,w->request.run)||
       (w->statePinValid&&w->statePin.parent.nonce==w->response.nonce&&w->statePin.parent.run==w->request.run)||
       !referenceCacheUnreferenced(w->response.nonce,w->request.run))return 0;
    cluster=retireClusterBytes(&w->file);
    if(!cluster||w->response.bytes<64||w->response.bytes>MS_TRACE_RETIRE_MAX_BYTES||
       strlen(SusamuneCfgStoragePrefix())>sizeof(path)-70||
       w->response.bytes>cluster*MS_TRACE_RETIRE_MAX_CLUSTERS||f_size(&w->file)!=w->response.bytes)return 0;
    _sprintf(path,fileFormat,SusamuneCfgStoragePrefix(),w->response.nonce,w->request.run);
    if(strcmp(path,w->path))return 0;
    r->file=w->file;r->nonce=w->response.nonce;r->run=w->request.run;r->headerHash=w->headerHash;
    r->bytes=w->response.bytes;r->phase=RETIRE_HEADER;r->preserve=0;
    r->capabilities=w->request.capabilities&0xffffffu;r->generation=w->referenceGeneration;
    w->active=0;preparePublish();return 1;
}
static int retireDetach(const struct MsTraceRequest*q){return retireDetachOwned(q,0);}
// A matching explicit state load may close, but never delete, its old source.
static int retireRecover(unsigned nonce,unsigned run) {
    struct TraceRetire*r=&WRITER->retiring;
    if(!retireOwns(nonce,run))return 1;
    if(retireRetaining(r))return 0;
    r->preserve=1;
    if(r->phase!=RETIRE_DELETE&&f_close(&r->file)!=FR_OK){r->phase=RETIRE_CLOSE_FAILED;preparePublish();return 0;}
    r->phase=RETIRE_NONE;preparePublish();return 1;
}
static int retireWork(void) {
    const struct TraceRetire*r=&WRITER->retiring;
    return r->phase&&r->phase!=RETIRE_CLOSE_FAILED&&r->phase!=RETAIN_FAILED&&r->phase!=RETAIN_CLOSE_FAILED;
}
static void retireService(void) {
    struct TraceWriter*w=WRITER;struct TraceRetire*r=&w->retiring;
    unsigned char raw[64],expected[64];char path[160];UINT done=0;unsigned hash;FRESULT result;
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    unsigned before=read32(HW_TIMER),phase=r->phase;
#endif
    if(retireRetaining(r)){retainService();return;}
    if(r->phase==RETIRE_HEADER) {
        if(f_size(&r->file)!=r->bytes||f_lseek(&r->file,0)!=FR_OK||f_read(&r->file,raw,64,&done)!=FR_OK||done!=64)r->preserve=1;
        else {
            unsigned parent[3]={0,0,0};
            if(MsTraceGet(raw+44)==MS_TRACE_BRANCH_HEADER_TAG){parent[0]=MsTraceGet(raw+48);parent[1]=MsTraceGet(raw+52);parent[2]=MsTraceGet(raw+56);}
            hash=traceHeader(expected,r->nonce,r->run,MsTraceGet(raw+24),r->capabilities,parent);
            if(hash!=r->headerHash||memcmp(raw,expected,64))r->preserve=1;
        }
        r->phase=r->preserve?RETIRE_CLOSE:RETIRE_TAIL;
    } else if(r->phase==RETIRE_TAIL) {
        if(r->bytes>=96&&(f_lseek(&r->file,r->bytes-32)!=FR_OK||f_read(&r->file,raw,32,&done)!=FR_OK||done!=32||MsTraceGet(raw)==0x444f4e45u))r->preserve=1;
        r->phase=RETIRE_CLOSE;
    } else if(r->phase==RETIRE_CLOSE) {
        if(f_close(&r->file)!=FR_OK){r->preserve=1;r->phase=RETIRE_CLOSE_FAILED;}
        else r->phase=r->preserve?RETIRE_NONE:RETIRE_DELETE;
    } else if(r->phase==RETIRE_DELETE) {
        // No callback or FAT operation may separate this fresh proof from unlink.
        if(!r->preserve&&!branchAsyncOwns(retireNonce(r),r->run)&&!branchPending()&&!SusamuneStateStoragePending()&&!GhostTraceReadStorageOwns(r->nonce,r->run)&&
           referenceCacheUnreferenced(r->nonce,r->run)) {
            r->generation=w->referenceGeneration;
            _sprintf(path,fileFormat,SusamuneCfgStoragePrefix(),r->nonce,r->run);
            result=f_unlink_char(path);if(result!=FR_OK&&result!=FR_NO_FILE)r->preserve=1;
        } else r->preserve=1;
        r->phase=RETIRE_NONE;
    }
    preparePublish();
#if TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
    MoonshineNetLogIo("trace_retire",r->run,phase,r->bytes,read32(HW_TIMER)-before,r->preserve);
#endif
}
