enum { LINK_SOURCE=1,LINK_EXISTING,LINK_CREATE,LINK_WRITE,LINK_SYNC,LINK_CLOSE,
    LINK_VERIFY_OPEN,LINK_VERIFY,LINK_VERIFY_CLOSE,LINK_RENAME,LINK_CLOSE_FAILED };
static int branchAsyncActive(void){return WRITER->prepare.phase==MS_PREP_LINKING;}
static int branchAsyncWork(void){return branchAsyncActive()&&WRITER->prepare.link.phase!=LINK_CLOSE_FAILED;}
static int branchAsyncOwns(unsigned nonce,unsigned run){
    const struct TraceLink*l=&WRITER->prepare.link;
    return branchAsyncActive()&&((l->branch.parent.nonce==nonce&&l->branch.parent.run==run)||
        (l->branch.nonce==nonce&&l->branch.run==run));
}
static void asyncReply(unsigned sequence,unsigned status,unsigned owner,unsigned primary,unsigned oldRun){
    struct MsTraceBranchResponse*r=&WRITER->branchResponse;
    r->ack=sequence;r->status=status;r->reserved[0]=owner;r->reserved[1]=primary;r->reserved[2]=oldRun;branchPublish();
}
static void branchAsyncFinish(unsigned status){
    struct TracePrepare*p=&WRITER->prepare;struct TraceLink*l=&p->link;
    unsigned sequence=l->sequence,run=l->branch.run,primary=l->primary,old=l->oldRun;
    if(l->open&&f_close(&l->file)!=FR_OK){l->phase=LINK_CLOSE_FAILED;p->phase=MS_PREP_FAILED;p->active=2;p->error=MS_PREP_IO;status=MS_TRACE_IO;}
    else {l->open=0;p->phase=MS_PREP_CONSUMED;p->active=p->created=0;p->error=0;}
    asyncReply(sequence,status,run,primary,old);preparePublish();
}
static void branchAsyncService(void){
    struct TraceWriter*w=WRITER;struct TracePrepare*p=&w->prepare;struct TraceLink*l=&p->link;
    unsigned char raw[128],check[128];char path[160],target[160];UINT done=0;int result=FR_OK;
    if(!branchAsyncWork())return;
    MsTraceBranchEncode(raw,&l->branch,MS_TRACE_BRANCH_FORK);
    if(l->phase==LINK_SOURCE){
        if(retireOwns(l->branch.parent.nonce,l->branch.parent.run)){
            if(!retireWork())branchAsyncFinish(MS_TRACE_IO);return;
        }
        if(!branchSource(&l->branch,MS_TRACE_BRANCH_FORK)){branchAsyncFinish(MS_TRACE_BAD_SOURCE);return;}
        l->phase=LINK_EXISTING;
    }else if(l->phase==LINK_EXISTING){
        if(!branchPath(path,&l->branch)){branchAsyncFinish(MS_TRACE_PROTOCOL);return;}
        result=f_open_char(&l->file,path,FA_READ|FA_OPEN_EXISTING);
        if(result==FR_OK){
            l->open=1;
            if(f_size(&l->file)!=128||f_read(&l->file,check,128,&done)!=FR_OK||done!=128||memcmp(raw,check,128))branchAsyncFinish(MS_TRACE_BAD_SOURCE);
            else branchAsyncFinish(0);
            return;
        }
        if(result!=FR_NO_FILE&&result!=FR_NO_PATH){branchAsyncFinish(MS_TRACE_IO);return;}
        l->phase=LINK_CREATE;return;
    }else if(l->phase==LINK_CREATE){
        if(!branchPath(path,&l->branch)){branchAsyncFinish(MS_TRACE_PROTOCOL);return;}
        strcpy(path+strlen(path)-4,branchTemporary);l->generation=w->referenceGeneration++;
        result=f_open_char(&l->file,path,FA_WRITE|FA_CREATE_NEW);
        if(result==FR_OK){l->open=1;l->phase=LINK_WRITE;}
    }else if(l->phase==LINK_WRITE){
        result=f_write(&l->file,raw,128,&done);if(result==FR_OK&&done!=128)result=FR_DISK_ERR;
        if(result==FR_OK)l->phase=LINK_SYNC;
    }else if(l->phase==LINK_SYNC){result=f_sync(&l->file);if(result==FR_OK)l->phase=LINK_CLOSE;
    }else if(l->phase==LINK_CLOSE||l->phase==LINK_VERIFY_CLOSE){
        result=f_close(&l->file);
        if(result==FR_OK){l->open=0;l->phase=l->phase==LINK_CLOSE?LINK_VERIFY_OPEN:LINK_RENAME;}
        else {l->phase=LINK_CLOSE_FAILED;p->phase=MS_PREP_FAILED;p->active=2;p->error=MS_PREP_IO;asyncReply(l->sequence,MS_TRACE_IO,l->branch.run,l->primary,l->oldRun);preparePublish();return;}
    }else if(l->phase==LINK_VERIFY_OPEN){
        branchPath(path,&l->branch);strcpy(path+strlen(path)-4,branchTemporary);
        result=f_open_char(&l->file,path,FA_READ|FA_OPEN_EXISTING);if(result==FR_OK){l->open=1;l->phase=LINK_VERIFY;}
    }else if(l->phase==LINK_VERIFY){
        if(f_size(&l->file)!=128||f_read(&l->file,check,128,&done)!=FR_OK||done!=128||memcmp(raw,check,128)){branchAsyncFinish(MS_TRACE_BAD_SOURCE);return;}
        l->phase=LINK_VERIFY_CLOSE;
    }else if(l->phase==LINK_RENAME){
        branchPath(target,&l->branch);strcpy(path,target);strcpy(path+strlen(path)-4,branchTemporary);
        result=f_rename_char(path,target);
        if(result==FR_OK){
            if(w->referenceGeneration==l->generation+1u&&referenceCacheCurrent(l->generation)){
                referenceCacheAdd(l->branch.parent.nonce,l->branch.parent.run);referenceCacheSeal();
            }
            branchAsyncFinish(0);return;
        }
    }
    if(result!=FR_OK)branchAsyncFinish(MS_TRACE_IO);
}
static void continueRefuse(const struct MsTraceRequest*q,const struct MsTraceBranchRequest*b,unsigned status){
    struct TraceWriter*w=WRITER;
    if(b&&b->sequence&&!branchAsyncActive())asyncReply(b->sequence,status,0,q->sequence,b->run);
    w->response.ackRequest=q->sequence;w->response.error=status;publish();
}
static int continueStart(const struct MsTraceRequest*q){
    struct TraceWriter*w=WRITER;struct TracePrepare*p=&w->prepare;
    struct MsTraceBranchRequest request;struct MsTraceBranch branch;struct MsTraceRequest old;
    struct RetainPlan retained;FIL next;char path[160];unsigned preserve=0,oldRun;unsigned char header[64];
    sync_before_read((void*)&BRANCHBOX->request,32);memcpy(&request,(const void*)&BRANCHBOX->request,32);
    if(branchAsyncActive()||w->branchDeleting){continueRefuse(q,0,MS_TRACE_BUSY);return 0;}
    if(request.magic!=MS_TRACE_BRANCH_MAGIC||request.version!=MS_TRACE_BRANCH_VERSION||request.bootNonce!=q->nonce||
       !request.sequence||request.sequence==w->branchResponse.ack||request.operation!=MS_TRACE_BRANCH_ASYNC_CONTINUE||
       request.kind!=q->sequence||request.nonce>1||request.run!=w->request.run){continueRefuse(q,&request,MS_TRACE_PROTOCOL);return 0;}
    sync_before_read((void*)&BRANCHBOX->payload,96);memcpy(&branch,(const void*)&BRANCHBOX->payload,96);
    if(!MsTraceBranchValid(&branch,MS_TRACE_BRANCH_FORK)||branch.nonce!=q->nonce||branch.run!=q->run||branch.game!=GAME_ID||
       branch.capabilities!=q->capabilities||branch.ownerKind!=MS_TRACE_BRANCH_FORK_OWNER||branch.ownerId!=1||branch.ownerGeneration!=1||
       q->run==request.run){continueRefuse(q,&request,MS_TRACE_BAD_SOURCE);return 0;}
    if(w->recovery.phase||w->retiring.phase||p->phase!=MS_PREP_READY||p->error||p->active!=1||!p->created||
       p->request.run!=q->run||p->request.bootNonce!=q->nonce||p->request.capabilities!=q->capabilities){continueRefuse(q,&request,MS_TRACE_BUSY);return 0;}
    oldRun=w->request.run;old=w->request;old.operation=MS_TRACE_RETIRE;
    if(w->active){
        if(request.nonce){if(!retainInspect(oldRun,&retained)){continueRefuse(q,&request,MS_TRACE_BUSY);return 0;}preserve=1;}
        else if((branch.parent.nonce==q->nonce&&branch.parent.run==oldRun)||w->retained){continueRefuse(q,&request,MS_TRACE_BUSY);return 0;}
    }
    if(prepareTakeInto(q,&next,path)!=1){continueRefuse(q,&request,MS_TRACE_BUSY);return 0;}
    if(w->active){
        if(preserve)retainMove(&retained);
        else if(!retireDetachOwned(&old,&request)){
            p->file=next;strcpy(p->path,path);p->active=p->created=1;p->phase=MS_PREP_READY;preparePublish();
            continueRefuse(q,&request,MS_TRACE_BUSY);return 0;
        }
    }
    // From here the child owns the live writer, even if its first header write fails.
    w->file=next;strcpy(w->path,path);w->request=*q;w->request.operation=MS_TRACE_START;
    w->response.ackRequest=q->sequence;w->response.phase=MS_TRACE_OPENING;w->response.error=0;w->response.bytes=w->response.ackChunk=0;
    w->offset=w->headerWritten=w->failed=0;w->active=w->owned=1;w->retained=1;
    memset(&w->metrics,0,sizeof(w->metrics));memset(&w->chunk,0,sizeof(w->chunk));w->chunk.run=oldRun;
    w->parent[0]=branch.parent.nonce;w->parent[1]=branch.parent.run;w->parent[2]=branch.parent.chunk;
    memset(&p->link,0,sizeof(p->link));p->link.branch=branch;p->link.sequence=request.sequence;p->link.primary=q->sequence;p->link.oldRun=oldRun;p->link.phase=LINK_SOURCE;
    p->phase=MS_PREP_LINKING;p->active=p->created=0;p->error=0;retirePreserve(branch.parent.nonce,branch.parent.run);
    asyncReply(request.sequence,MS_TRACE_BRANCH_PENDING,q->run,q->sequence,oldRun);preparePublish();
    w->headerHash=traceHeader(header,q->nonce,q->run,q->scene,q->capabilities,w->parent);
    if(f_lseek(&w->file,0)!=FR_OK){fail(MS_TRACE_IO);branchAsyncFinish(MS_TRACE_IO);return 0;}
    if(!writeBytes(header,64)){branchAsyncFinish(MS_TRACE_IO);return 0;}
    w->retained=0;w->response.phase=MS_TRACE_RECORDING;publish();return 1;
}
