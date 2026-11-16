enum { RECOVERY_NONE, RECOVERY_HEADER, RECOVERY_BLOCK, RECOVERY_REFERENCES, RECOVERY_COMMIT, RECOVERY_FAILED };

static int recoveryClose(struct TraceRecovery*r) {
    if(r->open&&f_close(&r->file)!=FR_OK)return 0;
    r->open=0;
    if(r->directoryOpen&&f_closedir(&r->directory)!=FR_OK)return 0;
    r->directoryOpen=0;r->phase=RECOVERY_NONE;return 1;
}
static int recoveryFail(struct TraceRecovery*r) {
    r->phase=RECOVERY_FAILED;
    recoveryClose(r);
    return -1;
}
int GhostTraceStateReferenceCancel(void) {
    struct TraceRecovery*r=&WRITER->recovery;
    if(!r->phase)return 1;
    r->phase=RECOVERY_FAILED;
    return recoveryClose(r);
}
int GhostTraceStateReferenceBusy(void) {return WRITER->recovery.phase!=RECOVERY_NONE;}
void GhostTraceStateReferenceReset(void) { if(!WRITER->recovery.phase)WRITER->statePinValid=0; }

int GhostTraceStateReferencePrepare(const struct MsTraceStateReference*v,unsigned game,
        unsigned project,unsigned id,unsigned generation) {
    struct MsTraceBranch*b=&WRITER->statePin;
    if(WRITER->recovery.phase)return 0;
    WRITER->statePinValid=0;
    if(!admitted()||!v||!MsTraceStateReferenceValid(v,1)||v->game!=game||
       project>99999999u||!id||id>99999999u)return 0;
    memset(b,0,sizeof(*b));b->nonce=v->prefix.nonce;b->run=v->prefix.run;
    b->game=v->game;b->capabilities=v->capabilities;b->parent=v->prefix;b->fence=v->fence;
    b->ownerKind=MS_TRACE_OWNER_STATE|project;b->ownerId=id;b->ownerGeneration=generation;
    if(!MsTraceBranchValid(b,MS_TRACE_BRANCH_CHECKPOINT))return 0;
    retirePreserve(b->parent.nonce,b->parent.run);
    WRITER->statePinValid=1;return 1;
}
int GhostTraceStateReferenceStore(void) {
    return !WRITER->statePinValid||GhostTraceBranchStore(&WRITER->statePin,MS_TRACE_BRANCH_CHECKPOINT);
}
int GhostTraceStateReferenceRelease(void) {
    return !WRITER->statePinValid||GhostTraceBranchRelease(&WRITER->statePin,MS_TRACE_BRANCH_CHECKPOINT);
}

static int recoveryChunk(struct TraceRecovery*r) {
    const struct MsTraceBranch*b=&r->pin;
    ++r->chunks;r->lastComplete=r->offset;r->previousFrame=r->chunkFrame;
    if(r->chunks==b->parent.chunk) {
        if(r->chunkOffset!=b->fence.chunkOffset||r->offset!=b->fence.fileBytes||
           r->chunkBytes!=b->parent.recordBytes||r->chunkHash!=b->parent.checksum||
           r->chunkFrame!=b->parent.frame)return recoveryFail(r);
        r->matched=1;
    }
    r->phase=RECOVERY_HEADER;return 0;
}

int GhostTraceStateReferenceRecover(int begin) {
    struct TraceWriter*w=WRITER;
    struct TraceRecovery*r=&w->recovery;
    const struct MsTraceBranch*b=&w->statePin;
    unsigned char bytes[64];char path[160],finalPath[160];UINT done=0;
    unsigned raw,stored,remaining;FRESULT result;
    if(!w->statePinValid)return 1;
    if(begin) {
        if(r->phase||!retireRecover(b->parent.nonce,b->parent.run)||!prefixSource(b))return -1;
        if(w->active&&w->response.nonce==b->parent.nonce&&w->request.run==b->parent.run)return w->failed?-1:1;
        r->pin=*b;
        _sprintf(path,sourceFormat,SusamuneCfgStoragePrefix(),b->parent.nonce,b->parent.run);
        result=f_open_char(&r->file,path,FA_READ|FA_OPEN_EXISTING);
        if(result==FR_OK) {r->open=1;return recoveryClose(r)?1:recoveryFail(r);}
        if(result!=FR_NO_FILE&&result!=FR_NO_PATH)return -1;
        strcpy(path+strlen(path)-4,"part");
        if(f_open_char(&r->file,path,FA_READ|FA_WRITE|FA_OPEN_EXISTING)!=FR_OK)return -1;
        r->open=1;r->pin=*b;r->size=f_size(&r->file);r->offset=r->lastComplete=64;
        r->chunks=r->matched=r->blocks=r->directoryOpen=r->hasFooter=r->previousFrame=0;
        r->requiredBytes=b->fence.fileBytes;r->requiredChunks=b->parent.chunk;r->phase=RECOVERY_HEADER;
        if(r->size>MS_TRACE_FILE_LIMIT||r->size<b->fence.fileBytes)return recoveryFail(r);
        return 0;
    }
    if(!r->phase||memcmp(&r->pin,b,sizeof(*b)))return -1;
    if(r->phase==RECOVERY_FAILED)return recoveryClose(r)?-1:0;
    if(r->phase==RECOVERY_HEADER) {
        remaining=r->size-r->offset;
        if(remaining<32) {r->phase=RECOVERY_REFERENCES;return 0;}
        if(f_lseek(&r->file,r->offset)!=FR_OK||f_read(&r->file,bytes,32,&done)!=FR_OK||done!=32)return recoveryFail(r);
        if(MsTraceGet(bytes)==0x444f4e45u) {
            if(remaining!=32||MsTraceGet(bytes+4)!=b->parent.run||MsTraceGet(bytes+8)!=r->chunks||
               MsTraceGet(bytes+12)!=r->offset||MsTraceGet(bytes+16)!=b->capabilities)return recoveryFail(r);
            r->hasFooter=1;r->phase=RECOVERY_REFERENCES;return 0;
        }
        raw=MsTraceGet(bytes+8);
        if(MsTraceGet(bytes)!=b->parent.run||MsTraceGet(bytes+4)!=r->chunks+1||!raw||raw>MS_TRACE_BUFFER_BYTES||
           MsTraceGet(bytes+16)>MsTraceGet(bytes+20)||(r->chunks&&MsTraceGet(bytes+16)<r->previousFrame)||MsTraceGet(bytes+24)>1||
           (MsTraceGet(bytes+24)?MsTraceGet(bytes+28)!=MS_TRACE_PACK_BLOCK:MsTraceGet(bytes+28)!=0))return recoveryFail(r);
        r->chunkOffset=r->offset;r->chunkBytes=r->rawLeft=raw;r->chunkHash=MsTraceGet(bytes+12);
        r->chunkFrame=MsTraceGet(bytes+20);r->offset+=32;
        if(!MsTraceGet(bytes+24)) {
            if(raw>r->size-r->offset){r->phase=RECOVERY_REFERENCES;return 0;}
            r->offset+=raw;return recoveryChunk(r);
        }
        r->phase=RECOVERY_BLOCK;return 0;
    }
    if(r->phase==RECOVERY_BLOCK) {
        if(r->size-r->offset<8){r->phase=RECOVERY_REFERENCES;return 0;}
        if(f_lseek(&r->file,r->offset)!=FR_OK||f_read(&r->file,bytes,8,&done)!=FR_OK||done!=8)return recoveryFail(r);
        raw=MsTraceGet(bytes);stored=MsTraceGet(bytes+4)&0x7fffffffu;
        remaining=r->rawLeft<MS_TRACE_PACK_BLOCK?r->rawLeft:MS_TRACE_PACK_BLOCK;
        if(raw!=remaining||!stored||(MsTraceGet(bytes+4)&0x80000000u?stored>=raw:stored!=raw))return recoveryFail(r);
        if(stored>r->size-r->offset-8){r->phase=RECOVERY_REFERENCES;return 0;}
        r->offset+=8+stored;r->rawLeft-=raw;++r->blocks;
        return r->rawLeft?0:recoveryChunk(r);
    }
    if(r->phase==RECOVERY_REFERENCES) {
        FILINFO info;struct MsTraceBranch reference;unsigned kind,i;unsigned char raw[128];char name[128];
        if(!r->matched)return recoveryFail(r);
        if(!r->directoryOpen) {
            _sprintf(path,directoryFormat,SusamuneCfgStoragePrefix());
            if(f_opendir_char(&r->directory,path)!=FR_OK)return recoveryFail(r);
            r->referenceGeneration=w->referenceGeneration;r->directoryOpen=1;return 0;
        }
        if(f_readdir(&r->directory,&info)!=FR_OK)return recoveryFail(r);
        if(!info.fname[0]) {
            if(f_closedir(&r->directory)!=FR_OK)return recoveryFail(r);
            r->directoryOpen=0;r->phase=RECOVERY_COMMIT;return 0;
        }
        if(info.fattrib&AM_DIR)return 0;
        for(i=0;i<sizeof(name)-1&&info.fname[i];++i) {
            if(info.fname[i]>127)return recoveryFail(r);
            name[i]=(char)info.fname[i];
        }
        name[i]=0;
        if(info.fname[i])return recoveryFail(r);
        if(i<5)return 0;
        if(strcmp(name+i-5,".msgb")&&strcmp(name+i-5,".mbpt"))return 0;
        if(strlen(SusamuneCfgStoragePrefix())+sizeof(MOONSHINE_RECORDINGS_DIR)+i>=sizeof(path))return recoveryFail(r);
        _sprintf(path,"%s" MOONSHINE_RECORDINGS_DIR "/%s",SusamuneCfgStoragePrefix(),name);
        if(!branchRead(path,raw)||!MsTraceBranchDecode(&reference,&kind,raw))return recoveryFail(r);
        if(reference.parent.nonce==b->parent.nonce&&reference.parent.run==b->parent.run) {
            if(reference.fence.headerHash!=b->fence.headerHash||reference.game!=b->game||
               reference.capabilities!=b->capabilities)return recoveryFail(r);
            if(reference.fence.fileBytes>r->requiredBytes)r->requiredBytes=reference.fence.fileBytes;
            if(reference.parent.chunk>r->requiredChunks)r->requiredChunks=reference.parent.chunk;
        }
        return 0;
    }
    if(r->phase==RECOVERY_COMMIT) {
        if(r->referenceGeneration!=w->referenceGeneration){r->phase=RECOVERY_REFERENCES;return 0;}
        // Keep every complete chunk, including prefixes owned by other state files.
        if(!r->matched||r->lastComplete<r->requiredBytes||r->chunks<r->requiredChunks||r->lastComplete>MS_TRACE_FILE_LIMIT-32)return recoveryFail(r);
        memset(bytes,0,32);MsTracePut(bytes,0x444f4e45u);MsTracePut(bytes+4,b->parent.run);
        MsTracePut(bytes+8,r->chunks);MsTracePut(bytes+12,r->lastComplete);
        MsTracePut(bytes+16,b->capabilities);MsTracePut(bytes+28,r->blocks);
        if(!r->hasFooter&&(f_lseek(&r->file,r->lastComplete)!=FR_OK||f_truncate(&r->file)!=FR_OK||
           f_write(&r->file,bytes,32,&done)!=FR_OK||done!=32||f_sync(&r->file)!=FR_OK))return recoveryFail(r);
        if(!recoveryClose(r))return recoveryFail(r);
        _sprintf(finalPath,sourceFormat,SusamuneCfgStoragePrefix(),b->parent.nonce,b->parent.run);
        strcpy(path,finalPath);strcpy(path+strlen(path)-4,"part");
        return f_rename_char(path,finalPath)==FR_OK?1:-1;
    }
    return -1;
}
