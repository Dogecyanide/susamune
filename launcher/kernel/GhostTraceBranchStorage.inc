#include "GhostTraceBranchStorage.h"
static const char branchFormat[] TRACE_TEXT="%s" MOONSHINE_RECORDINGS_DIR "/ref_%08X_%08X_%08X_%08X_%08X.msgb";
static const char sourceFormat[] TRACE_TEXT="%s" MOONSHINE_RECORDINGS_DIR "/trace_%08X_%08X.msgt";
static const char branchTemporary[] TRACE_TEXT="mbpt";
static int branchPath(char*path,const struct MsTraceBranch*b) {
    int n;if(strlen(SusamuneCfgStoragePrefix())>40)return 0;
    n=_sprintf(path,branchFormat,SusamuneCfgStoragePrefix(),b->nonce,b->run,b->ownerKind,b->ownerId,b->ownerGeneration);
    return n>0&&(unsigned)n<160;
}
static int branchRead(const char*path,unsigned char raw[128]) {
    FIL f;UINT done=0;int ok;
    if(f_open_char(&f,path,FA_READ|FA_OPEN_EXISTING)!=FR_OK)return 0;
    ok=f_size(&f)==128&&f_read(&f,raw,128,&done)==FR_OK&&done==128;
    if(f_close(&f)!=FR_OK)ok=0;return ok;
}
static unsigned referenceBit(unsigned nonce,unsigned run,unsigned index) {
    const unsigned first=(nonce*0x9e3779b9u)^run;
    const unsigned step=((run*0x85ebca6bu)^(nonce>>16))|1u;
    return (first+index*step)&16383u;
}
static int referenceCachePending(void) {
    const struct TraceReferenceCache*c=&WRITER->references;
    return c->generation!=WRITER->referenceGeneration || (!c->valid&&!c->failed);
}
static int referenceCacheCurrent(unsigned generation) {
    const struct TraceReferenceCache*c=&WRITER->references;
    return c->valid&&!c->active&&!c->failed&&c->generation==generation&&
        c->checksum==MsTraceHash(2166136261u,c->bits,sizeof(c->bits));
}
static void referenceCacheAdd(unsigned nonce,unsigned run) {
    struct TraceReferenceCache*c=&WRITER->references;unsigned i,bit;
    for(i=0;i<4;++i){bit=referenceBit(nonce,run,i);c->bits[bit>>3]|=1u<<(bit&7);}
}
static void referenceCacheSeal(void) {
    struct TraceReferenceCache*c=&WRITER->references;
    c->checksum=MsTraceHash(2166136261u,c->bits,sizeof(c->bits));
    c->generation=WRITER->referenceGeneration;c->valid=1;
}
static int referenceCacheUnreferenced(unsigned nonce,unsigned run) {
    const struct TraceReferenceCache*c=&WRITER->references;unsigned i,bit;
    if(!referenceCacheCurrent(WRITER->referenceGeneration))return 0;
    // This filter can only prove absence. Possible matches keep the full scan.
    for(i=0;i<4;++i){bit=referenceBit(nonce,run,i);if(!(c->bits[bit>>3]&(1u<<(bit&7))))return 1;}
    return 0;
}
static void referenceCacheService(void) {
    struct TraceReferenceCache*c=&WRITER->references;FILINFO info;
    char path[160],name[128];unsigned char raw[128];struct MsTraceBranch branch;
    unsigned work,n,kind;FRESULT result;
    if(c->generation!=WRITER->referenceGeneration){
        if(c->active)f_closedir(&c->directory);
        memset(c,0,sizeof(*c));c->generation=WRITER->referenceGeneration;
    }
    if(c->valid||c->failed)return;
    if(!c->active){
        memset(c->bits,0,sizeof(c->bits));
        if(strlen(SusamuneCfgStoragePrefix())>30)goto failed;
        _sprintf(path,directoryFormat,SusamuneCfgStoragePrefix());
        result=f_opendir_char(&c->directory,path);
        if(result==FR_NO_PATH||result==FR_NO_FILE)goto complete;
        if(result!=FR_OK)goto failed;c->active=1;
    }
    for(work=0;work<4;++work){
        if(f_readdir(&c->directory,&info)!=FR_OK)goto failed;
        if(!info.fname[0]){
            if(f_closedir(&c->directory)!=FR_OK)goto failed;c->active=0;goto complete;
        }
        if(info.fattrib&AM_DIR)continue;
        for(n=0;n<sizeof(name)-1&&info.fname[n];++n){if(info.fname[n]>127)goto failed;name[n]=(char)info.fname[n];}name[n]=0;
        if(info.fname[n]||n<5)goto failed;
        if(strcmp(name+n-5,".msgb")&&strcmp(name+n-5,".mbpt"))continue;
        if(strlen(SusamuneCfgStoragePrefix())+sizeof(MOONSHINE_RECORDINGS_DIR)+strlen(name)>=sizeof(path))goto failed;
        _sprintf(path,"%s" MOONSHINE_RECORDINGS_DIR "/%s",SusamuneCfgStoragePrefix(),name);
        if(!branchRead(path,raw)||!MsTraceBranchDecode(&branch,&kind,raw))goto failed;
        referenceCacheAdd(branch.parent.nonce,branch.parent.run);
        return;
    }
    return;
complete:
    if(c->generation==WRITER->referenceGeneration)referenceCacheSeal();
    return;
failed:
    if(c->active)f_closedir(&c->directory);c->active=0;c->valid=0;c->failed=1;
}
static int sourceRead(unsigned nonce,unsigned run,unsigned char h[64],unsigned char end[32],FIL*f,char path[160]) {
    UINT done=0;unsigned bytes;
    if(strlen(SusamuneCfgStoragePrefix())>70)return 0;
    _sprintf(path,sourceFormat,SusamuneCfgStoragePrefix(),nonce,run);
    if(f_open_char(f,path,FA_READ|FA_OPEN_EXISTING)!=FR_OK)return 0;
    bytes=f_size(f);
    if(bytes<96||bytes>MS_TRACE_FILE_LIMIT||f_read(f,h,64,&done)!=FR_OK||done!=64||f_lseek(f,bytes-32)!=FR_OK||
       f_read(f,end,32,&done)!=FR_OK||done!=32||MsTraceGet(h)!=MS_TRACE_MAGIC||MsTraceGet(h+4)>MS_TRACE_FILE_VERSION||
       !MsTraceGet(h+4)||MsTraceGet(h+8)!=64||MsTraceGet(h+16)!=nonce||MsTraceGet(h+20)!=run||
       MsTraceGet(h+32)!=MS_TRACE_BUFFER_BYTES||!MsTraceParentHeaderValid(h)||MsTraceGet(h+60)!=MsTraceHash(2166136261u,h,60)||
       MsTraceGet(end)!=0x444f4e45u||MsTraceGet(end+4)!=run||MsTraceGet(end+12)!=bytes-32||
       MsTraceGet(end+16)!=MsTraceGet(h+28)||(MsTraceGet(end+16)&0xff000000u)){
        f_close(f);return 0;
    }return 1;
}

static int prefixSource(const struct MsTraceBranch*b) {
    FIL f;char path[160];unsigned char h[64],chunk[32],end[32],block[8];
    UINT done=0;unsigned bytes,offset,left,raw,stored;FRESULT result;int partial=0,ok;
    if(strlen(SusamuneCfgStoragePrefix())>70)return 0;
    _sprintf(path,sourceFormat,SusamuneCfgStoragePrefix(),b->parent.nonce,b->parent.run);
    result=f_open_char(&f,path,FA_READ|FA_OPEN_EXISTING);
    if(result==FR_NO_FILE||result==FR_NO_PATH) {
        strcpy(path+strlen(path)-4,"part");partial=1;
        result=f_open_char(&f,path,FA_READ|FA_OPEN_EXISTING);
    }
    if(result!=FR_OK)return 0;
    bytes=f_size(&f);
    ok=bytes>=b->fence.fileBytes&&bytes<=MS_TRACE_FILE_LIMIT&&f_read(&f,h,64,&done)==FR_OK&&done==64&&
       MsTraceGet(h)==MS_TRACE_MAGIC&&MsTraceGet(h+4)&&MsTraceGet(h+4)<=MS_TRACE_FILE_VERSION&&MsTraceGet(h+8)==64&&
       MsTraceGet(h+12)==b->game&&MsTraceGet(h+16)==b->parent.nonce&&MsTraceGet(h+20)==b->parent.run&&
       MsTraceGet(h+28)==b->capabilities&&MsTraceGet(h+32)==MS_TRACE_BUFFER_BYTES&&
       MsTraceGet(h+60)==b->fence.headerHash&&MsTraceGet(h+60)==MsTraceHash(2166136261u,h,60);
    if(ok&&!partial)ok=bytes>=96&&f_lseek(&f,bytes-32)==FR_OK&&f_read(&f,end,32,&done)==FR_OK&&done==32&&
       MsTraceGet(end)==0x444f4e45u&&MsTraceGet(end+4)==b->parent.run&&MsTraceGet(end+8)>=b->parent.chunk&&
       MsTraceGet(end+12)==bytes-32&&MsTraceGet(end+16)==b->capabilities;
    if(ok)ok=f_lseek(&f,b->fence.chunkOffset)==FR_OK&&f_read(&f,chunk,32,&done)==FR_OK&&done==32&&
       MsTraceGet(chunk)==b->parent.run&&MsTraceGet(chunk+4)==b->parent.chunk&&MsTraceGet(chunk+8)==b->parent.recordBytes&&
       MsTraceGet(chunk+12)==b->parent.checksum&&MsTraceGet(chunk+16)<=b->parent.frame&&MsTraceGet(chunk+20)==b->parent.frame&&
       MsTraceGet(chunk+24)<=1&&(MsTraceGet(chunk+24)?MsTraceGet(chunk+28)==MS_TRACE_PACK_BLOCK:MsTraceGet(chunk+28)==0);
    offset=b->fence.chunkOffset+32;left=b->parent.recordBytes;
    if(ok&&!MsTraceGet(chunk+24))ok=left==b->fence.fileBytes-offset;
    else while(ok&&left) {
        if(offset>b->fence.fileBytes||b->fence.fileBytes-offset<8||f_lseek(&f,offset)!=FR_OK||
           f_read(&f,block,8,&done)!=FR_OK||done!=8){ok=0;break;}
        raw=MsTraceGet(block);stored=MsTraceGet(block+4)&0x7fffffffu;
        if(raw!=(left<MS_TRACE_PACK_BLOCK?left:MS_TRACE_PACK_BLOCK)||!stored||
           (MsTraceGet(block+4)&0x80000000u?stored>=raw:stored!=raw)||stored>b->fence.fileBytes-offset-8){ok=0;break;}
        offset+=8+stored;left-=raw;
        if(!left&&offset!=b->fence.fileBytes)ok=0;
    }
    if(f_close(&f)!=FR_OK)ok=0;
    return ok;
}

static int branchSource(const struct MsTraceBranch*b,unsigned kind) {
    if(kind==MS_TRACE_BRANCH_CHECKPOINT)return prefixSource(b);
    FIL f;char path[160];unsigned char h[64],end[32],chunk[32];UINT done=0;int ok;
    if(!sourceRead(b->parent.nonce,b->parent.run,h,end,&f,path))return 0;
    ok=MsTraceGet(h+12)==b->game&&MsTraceGet(h+28)==b->capabilities&&MsTraceGet(h+60)==b->fence.headerHash&&
       MsTraceGet(end+8)>=b->parent.chunk&&MsTraceGet(end+12)>=b->fence.fileBytes;
    if(ok&&kind==MS_TRACE_BRANCH_FORK){
        ok=f_lseek(&f,b->fence.chunkOffset)==FR_OK&&f_read(&f,chunk,32,&done)==FR_OK&&done==32&&
           MsTraceGet(chunk)==b->parent.run&&MsTraceGet(chunk+4)==b->parent.chunk&&MsTraceGet(chunk+8)==b->parent.recordBytes&&
           MsTraceGet(chunk+12)==b->parent.checksum&&MsTraceGet(chunk+20)==b->parent.frame;
    }
    if(f_close(&f)!=FR_OK)ok=0;return ok;
}
int GhostTraceStorageAdmitted(void){return admitted();}
static int traceIdentity(unsigned nonce,unsigned run,unsigned game,struct MsTraceFileIdentity*out,unsigned*flags,unsigned*parent) {
    FIL f;char path[160];unsigned char h[64],end[32];int ok;
    if(!out||!sourceRead(nonce,run,h,end,&f,path))return 0;
    ok=MsTraceGet(h+12)==game&&(!(MsTraceGet(h+36)&0x20u)||(MsTraceGet(h+36)&1u));
    if(ok&&flags)*flags=MsTraceGet(h+36);
    if(ok&&parent){parent[0]=MsTraceGet(h+48);parent[1]=MsTraceGet(h+52);parent[2]=MsTraceGet(h+56);}
    if(ok){out->version=MsTraceGet(h+4);out->game=game;out->scene=MsTraceGet(h+24);out->capabilities=MsTraceGet(h+28);
        out->bytes=f_size(&f);out->chunks=MsTraceGet(end+8);out->headerHash=MsTraceGet(h+60);out->footerHash=MsTraceHash(2166136261u,end,32);}
    if(f_close(&f)!=FR_OK)ok=0;return ok;
}
int GhostTraceBranchLookup(unsigned nonce,unsigned run,unsigned game,struct MsTraceLookup*out) {
    struct MsTraceBranch key;FIL f;FILINFO info;char path[160];unsigned char raw[128];UINT done=0;unsigned kind,parent[3];FRESULT result;int ok;
    if(!out||!nonce||!run||(game!=0x474d534au&&game!=0x474d5345u&&game!=0x474d5350u))return 0;
    memset(out,0,sizeof(*out));out->nonce=nonce;out->run=run;
    if(!traceIdentity(nonce,run,game,&out->file,&out->runFlags,parent))return 0;
    memset(&key,0,sizeof(key));key.nonce=nonce;key.run=run;key.ownerKind=MS_TRACE_BRANCH_FORK_OWNER;key.ownerId=key.ownerGeneration=1;
    if(!branchPath(path,&key))return 0;
    result=f_open_char(&f,path,FA_READ|FA_OPEN_EXISTING);
    if(result==FR_NO_FILE||result==FR_NO_PATH){
        strcpy(path+strlen(path)-4,branchTemporary);result=f_stat_char(path,&info);
        return !parent[0]&&(result==FR_NO_FILE||result==FR_NO_PATH);
    }
    if(result!=FR_OK)return 0;
    ok=f_size(&f)==128&&f_read(&f,raw,128,&done)==FR_OK&&done==128;
    if(f_close(&f)!=FR_OK)ok=0;
    if(!ok||!MsTraceBranchDecode(&out->branch,&kind,raw)||kind!=MS_TRACE_BRANCH_FORK||out->branch.nonce!=nonce||out->branch.run!=run||
       out->branch.game!=game||out->branch.capabilities!=out->file.capabilities||out->branch.ownerKind!=MS_TRACE_BRANCH_FORK_OWNER||
       out->branch.ownerId!=1||out->branch.ownerGeneration!=1||!branchSource(&out->branch,kind))return 0;
    if(parent[0]&&(out->branch.parent.nonce!=parent[0]||out->branch.parent.run!=parent[1]||out->branch.parent.chunk!=parent[2]))return 0;
    out->kind=MS_TRACE_LOOKUP_BRANCH;return 1;
}
int GhostTraceFileIdentity(unsigned nonce,unsigned run,unsigned game,struct MsTraceFileIdentity*out){
    unsigned parent[3];struct MsTraceLookup lookup;
    if(!traceIdentity(nonce,run,game,out,0,parent))return 0;
    return !parent[0]||(GhostTraceBranchLookup(nonce,run,game,&lookup)&&lookup.file.headerHash==out->headerHash&&lookup.file.footerHash==out->footerHash&&lookup.file.bytes==out->bytes);
}
int GhostTraceChildDependencyValid(const unsigned char*h,unsigned nonce,unsigned run,unsigned game){
    struct MsTraceLookup lookup;
    if(!MsTraceParentHeaderValid(h))return 0;
    if(!MsTraceGet(h+44))return 1;
    return GhostTraceBranchLookup(nonce,run,game,&lookup)&&lookup.kind==MS_TRACE_LOOKUP_BRANCH&&
        lookup.file.game==game&&lookup.file.headerHash==MsTraceGet(h+60)&&
        lookup.branch.nonce==nonce&&lookup.branch.run==run&&lookup.branch.parent.nonce==MsTraceGet(h+48)&&
        lookup.branch.parent.run==MsTraceGet(h+52)&&lookup.branch.parent.chunk==MsTraceGet(h+56);
}
int GhostTraceBranchStore(const struct MsTraceBranch*b,unsigned kind) {
    FIL f;char path[160],temp[160];unsigned char raw[128],check[128];UINT done=0;FRESULT result;int ok;
    if(!admitted()||!SusamuneCfgStorageAvailable()||b->game!=GAME_ID||!MsTraceBranchValid(b,kind)||!branchPath(path,b))return 0;
    retirePreserve(b->parent.nonce,b->parent.run);
    if(!branchSource(b,kind))return 0;
    if(kind==MS_TRACE_BRANCH_FORK && (!WRITER->active || WRITER->response.phase!=MS_TRACE_RECORDING ||
       WRITER->request.nonce!=b->nonce || WRITER->request.run!=b->run || WRITER->request.capabilities!=b->capabilities))return 0;
    if(kind==MS_TRACE_BRANCH_CHECKPOINT&&WRITER->response.nonce==b->parent.nonce&&WRITER->request.run==b->parent.run)
        WRITER->retained=1;
    MsTraceBranchEncode(raw,b,kind);
    if(branchRead(path,check))return !memcmp(raw,check,128);
    strcpy(temp,path);strcpy(temp+strlen(temp)-4,branchTemporary);
    const unsigned previousGeneration=WRITER->referenceGeneration++;
    result=f_open_char(&f,temp,FA_WRITE|FA_CREATE_NEW);if(result!=FR_OK)return 0;
    ok=f_write(&f,raw,128,&done)==FR_OK&&done==128&&f_sync(&f)==FR_OK;
    if(f_close(&f)!=FR_OK)ok=0;
    if(!ok||!branchRead(temp,check)||memcmp(raw,check,128)||f_rename_char(temp,path)!=FR_OK)return 0;
    // A verified new edge extends a complete summary without another directory walk.
    if(WRITER->referenceGeneration==previousGeneration+1u&&referenceCacheCurrent(previousGeneration)){
        referenceCacheAdd(b->parent.nonce,b->parent.run);referenceCacheSeal();
    }
    return 1;
}
int GhostTraceBranchRelease(const struct MsTraceBranch*b,unsigned kind) {
    char path[160];unsigned char raw[128],check[128];
    // A committed branch is an immutable parent edge, never a transient pin.
    if((kind!=MS_TRACE_BRANCH_PIN&&kind!=MS_TRACE_BRANCH_CHECKPOINT)||!MsTraceBranchValid(b,kind)||!branchPath(path,b))return 0;
    MsTraceBranchEncode(raw,b,kind);
    if(!branchRead(path,check)||memcmp(raw,check,128))return 0;
    const unsigned previousGeneration=WRITER->referenceGeneration++;
    if(f_unlink_char(path)!=FR_OK)return 0;
    // Retaining deleted edges produces only safe false positives.
    if(WRITER->referenceGeneration==previousGeneration+1u&&referenceCacheCurrent(previousGeneration))referenceCacheSeal();
    return 1;
}
int GhostTraceRetainedDiscard(unsigned nonce,unsigned run,unsigned headerHash,int begin) {
    struct TraceDiscard*d=&WRITER->discard;FILINFO info;FIL f;unsigned kind,i;struct MsTraceBranch b;
    char path[160],name[128];unsigned char h[128],end[32];int result;
    if(!MS_TRACE_BRANCH_RETENTION_READY||!admitted()||!nonce||!run||strlen(SusamuneCfgStoragePrefix())>30)return -1;
    if(branchAsyncOwns(nonce,run))return -1;
    if(begin){
        if(d->active||(nonce==WRITER->response.nonce&&run==WRITER->request.run&&(WRITER->active||WRITER->owned)))return -1;
        if(!sourceRead(nonce,run,h,end,&f,path))return -1;
        result=MsTraceGet(h+60)==headerHash;if(f_close(&f)!=FR_OK)result=0;if(!result)return -1;
        if(referenceCacheUnreferenced(nonce,run))return f_unlink_char(path)==FR_OK?1:-1;
        _sprintf(path,directoryFormat,SusamuneCfgStoragePrefix());
        if(f_opendir_char(&d->directory,path)!=FR_OK)return -1;
        d->nonce=nonce;d->run=run;d->headerHash=headerHash;d->generation=WRITER->referenceGeneration;d->active=1;return 0;
    }
    if(!d->active||d->nonce!=nonce||d->run!=run||d->headerHash!=headerHash)return -1;
    if(f_readdir(&d->directory,&info)!=FR_OK)goto failed;
    if(!info.fname[0]){
        if(f_closedir(&d->directory)!=FR_OK){d->active=0;return -1;}d->active=0;
        if(d->generation!=WRITER->referenceGeneration)return GhostTraceRetainedDiscard(nonce,run,headerHash,1);
        if((nonce==WRITER->response.nonce&&run==WRITER->request.run&&WRITER->active)||!sourceRead(nonce,run,h,end,&f,path))return -1;
        result=MsTraceGet(h+60)==headerHash;if(f_close(&f)!=FR_OK)result=0;
        return result&&f_unlink_char(path)==FR_OK?1:-1;
    }
    if(info.fattrib&AM_DIR)return 0;
    for(i=0;i<sizeof(name)-1&&info.fname[i];++i){if(info.fname[i]>127)goto failed;name[i]=(char)info.fname[i];}name[i]=0;
    if(info.fname[i]||i<5)goto failed;
    if(strcmp(name+i-5,".msgb")&&strcmp(name+i-5,".mbpt"))return 0;
    if(strlen(SusamuneCfgStoragePrefix())+sizeof(MOONSHINE_RECORDINGS_DIR)+strlen(name)>=sizeof(path))goto failed;
    _sprintf(path,"%s" MOONSHINE_RECORDINGS_DIR "/%s",SusamuneCfgStoragePrefix(),name);
    if(!branchRead(path,h)||!MsTraceBranchDecode(&b,&kind,h))goto failed;
    if(b.parent.nonce==nonce&&b.parent.run==run)goto failed;
    return 0;
failed:
    f_closedir(&d->directory);d->active=0;return -1;
}

#define BRANCHBOX ((volatile struct MsTraceBranchMailbox*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_BRANCH_MAILBOX_OFFSET))
#define LOOKUP_RESULT ((struct MsTraceLookup*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_BRANCH_LOOKUP_OFFSET))
static void branchPublish(void) {
    memcpy((void*)&BRANCHBOX->response,&WRITER->branchResponse,32);sync_after_write((void*)&BRANCHBOX->response,32);
}
static void branchInit(void) {
    memset(LOOKUP_RESULT,0,sizeof(*LOOKUP_RESULT));sync_after_write(LOOKUP_RESULT,sizeof(*LOOKUP_RESULT));
    memset((void*)BRANCHBOX,0,sizeof(*BRANCHBOX));WRITER->branchResponse.magic=MS_TRACE_BRANCH_MAGIC;
    WRITER->branchResponse.version=MS_TRACE_BRANCH_VERSION;WRITER->branchResponse.bootNonce=WRITER->response.nonce;
    sync_after_write((void*)BRANCHBOX,128);branchPublish();
}
static int branchPending(void) {
    sync_before_read((void*)&BRANCHBOX->request,32);
    return WRITER->branchDeleting || (BRANCHBOX->request.sequence && BRANCHBOX->request.sequence!=WRITER->branchResponse.ack);
}
static void branchService(void) {
    struct TraceWriter*w=WRITER;struct MsTraceBranchRequest q;struct MsTraceBranch b;int result=0;
    if(w->branchDeleting){
        q=w->branchRequest;result=GhostTraceRetainedDiscard(q.nonce,q.run,q.kind,0);if(!result)return;
        w->branchDeleting=0;
    }else{
        sync_before_read((void*)&BRANCHBOX->request,32);memcpy(&q,(const void*)&BRANCHBOX->request,32);
        if(!q.sequence||q.sequence==w->branchResponse.ack)return;
        if(q.operation==MS_TRACE_BRANCH_ASYNC_CONTINUE)return;
        if(q.magic!=MS_TRACE_BRANCH_MAGIC||q.version!=MS_TRACE_BRANCH_VERSION||q.bootNonce!=w->response.nonce||
           q.operation<MS_TRACE_BRANCH_STORE||q.operation>MS_TRACE_BRANCH_LOOKUP)result=-1;
        else if(q.operation==MS_TRACE_BRANCH_LOOKUP){
            result=GhostTraceBranchLookup(q.nonce,q.run,q.kind,LOOKUP_RESULT)?1:-1;
            LOOKUP_RESULT->sequence=q.sequence;LOOKUP_RESULT->bootNonce=w->response.nonce;
            sync_after_write(LOOKUP_RESULT,sizeof(*LOOKUP_RESULT));
        }
        else if(q.operation==MS_TRACE_BRANCH_DELETE){
            result=GhostTraceRetainedDiscard(q.nonce,q.run,q.kind,1);
            if(!result){w->branchRequest=q;w->branchDeleting=1;return;}
        }else{
            sync_before_read((void*)&BRANCHBOX->payload,96);memcpy(&b,(const void*)&BRANCHBOX->payload,96);
            result=b.nonce==q.nonce&&b.run==q.run&&(q.operation==MS_TRACE_BRANCH_STORE?
                GhostTraceBranchStore(&b,q.kind):GhostTraceBranchRelease(&b,q.kind));
            result=result?1:-1;
        }
    }
    w->branchResponse.ack=q.sequence;w->branchResponse.status=result>0?0:MS_TRACE_BAD_SOURCE;memset(w->branchResponse.reserved,0,sizeof(w->branchResponse.reserved));branchPublish();
}
