#include "susamune/ghost_trace_export.h"
struct TraceExportWriter {
    FIL file;char path[160];struct MsTraceExportRequest request;struct MsTraceExportResponse response;
    struct MsTraceFileIdentity identity;unsigned active,owned,offset,adler,verifyAdler,expectedAdler,profile,publicFile,nonce,run,game;
    unsigned char header[64],tail[32],name[MS_TRACE_EXPORT_NAME_BYTES];unsigned fatTime;
};
typedef char TraceExportWriterFits[MS_TRACE_EXPORT_ARM_OFFSET+sizeof(struct TraceExportWriter)<=MS_TRACE_LIBRARY_PIN_OFFSET?1:-1];
#define EXPORT_WRITER ((struct TraceExportWriter*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_ARM_OFFSET))
#define EXPORT_BOX ((volatile struct MsTraceExportMailbox*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_EXPORT_MAILBOX_OFFSET))
#define EXPORT_DATA ((unsigned char*)MS_TRACE_EXPORT_BUFFER_PHYS)
static const char shareDirectory[] TRACE_TEXT="%s/ghosts/share";
static const char shareRegion[] TRACE_TEXT="%s/ghosts/share/%s";
static const char shareProfile[] TRACE_TEXT="%s/ghosts/share/%s/p%u";
static const char shareFile[] TRACE_TEXT="%s/ghosts/share/%s/p%u/trace_%08X_%08X.part";
static const char regionJp[] TRACE_TEXT="jp",regionUs[] TRACE_TEXT="us",regionPal[] TRACE_TEXT="pal";
static void exportPublish(void){
    memcpy((void*)&EXPORT_BOX->identity,&EXPORT_WRITER->identity,32);sync_after_write((void*)&EXPORT_BOX->identity,32);
    memcpy((void*)&EXPORT_BOX->response,&EXPORT_WRITER->response,32);sync_after_write((void*)&EXPORT_BOX->response,32);
}
static void exportFailure(unsigned error){
    struct TraceExportWriter*w=EXPORT_WRITER;
    if(w->active&&f_close(&w->file)==FR_OK)w->active=0;
    w->response.ack=w->request.sequence;w->response.status=error|(!w->owned&&!w->active?MS_TRACE_EXPORT_NO_OWNER:0);w->response.phase=MS_TRACE_EXPORT_FAILED;exportPublish();
}
static void exportAbort(unsigned canceled){
    struct TraceExportWriter*w=EXPORT_WRITER;FRESULT result;
    if(w->active&&f_close(&w->file)!=FR_OK){exportFailure(MS_TRACE_IO);return;}w->active=0;
    result=w->owned?f_unlink_char(w->path):FR_OK;if(result!=FR_OK&&result!=FR_NO_FILE){exportFailure(MS_TRACE_IO);return;}
    w->owned=0;w->response.status=canceled?(MS_TRACE_EXPORT_CANCELED|MS_TRACE_EXPORT_NO_OWNER):0;
    w->response.phase=MS_TRACE_EXPORT_IDLE;w->response.ack=w->request.sequence;exportPublish();
}
static void exportInit(void){
    memset(EXPORT_WRITER,0,sizeof(*EXPORT_WRITER));memset((void*)EXPORT_BOX,0,sizeof(*EXPORT_BOX));
    EXPORT_WRITER->response.magic=MS_TRACE_EXPORT_MAGIC;EXPORT_WRITER->response.version=MS_TRACE_EXPORT_VERSION;
    EXPORT_WRITER->response.bootNonce=WRITER->response.nonce;sync_after_write((void*)EXPORT_BOX,64);exportPublish();
}
static int exportPending(void){sync_before_read((void*)EXPORT_BOX,64);return EXPORT_WRITER->response.phase==MS_TRACE_EXPORT_VERIFY||
    (EXPORT_BOX->request.sequence&&EXPORT_BOX->request.sequence!=EXPORT_WRITER->response.ack);}
// Exported streams are self-contained; dependency edges must be flattened first.
static int exportHeader(const unsigned char*h,const struct MsTraceExportRequest*q){
    return MsTraceGet(h)==MS_TRACE_MAGIC&&MsTraceGet(h+4)==3&&MsTraceGet(h+8)==64&&MsTraceGet(h+12)==q->game&&
        MsTraceGet(h+16)==q->nonce&&MsTraceGet(h+20)==q->run&&MsTraceGet(h+24)<=0xffffu&&!(MsTraceGet(h+28)&0xff000000u)&&
        MsTraceGet(h+32)==MS_TRACE_BUFFER_BYTES&&(!(MsTraceGet(h+36)&0x20u)||(MsTraceGet(h+36)&1u))&&
        (!MsTraceGet(h+40)||MsTraceGet(h+40)==MS_TRACE_PROVENANCE_TAG)&&
        MsTraceParentHeaderValid(h)&&!MsTraceGet(h+MS_TRACE_BRANCH_HEADER_OFFSET)&&
        MsTraceGet(h+60)==MsTraceHash(2166136261u,h,60);
}
static int exportDirectory(const char*path){FRESULT r=f_mkdir_char(path);return r==FR_OK||r==FR_EXIST;}
static void exportNamedPath(const struct TraceExportWriter *w,char *path){
    const unsigned char *p=w->name;unsigned area=MsTraceGet(p+4),episode=MsTraceGet(p+8);
    unsigned long long millis=((unsigned long long)MsTraceGet(p+20)*1001u)/120u;
    const char *route=NULL,*region=w->game==0x474d534au?regionJp:w->game==0x474d5345u?regionUs:regionPal;
    char level[12],time[16];
    if(MsTraceGet(p+12)!=255u&&MsTraceGet(p+16)!=0xffffffffu){area=MsTraceGet(p+12);episode=MsTraceGet(p+16);}
    switch(area){case 0:route="AS";break;case 1:route="DP";break;case 2:route="BH";break;
    case 3:route="RH";break;case 4:route="GB";break;case 5:route="PP";break;case 6:route="SB";break;
    case 8:route="PV";break;case 9:route="NB";break;case 0x34:route="CM";break;case 0x3c:route="BW";break;}
    if(route)_sprintf(level,"%s%u",route,episode+1);else _sprintf(level,"A%02XE%02X",area,episode);
    if(millis>=60000)_sprintf(time,"%u%02u%03u",(unsigned)(millis/60000),(unsigned)((millis/1000)%60),(unsigned)(millis%1000));
    else _sprintf(time,"%u%03u",(unsigned)(millis/1000),(unsigned)(millis%1000));
    _sprintf(path,"%s/ghosts/share/%s/p%u/%04u_%02u_%02u_%s_%s[%08X].msgt",
        SusamuneCfgStoragePrefix(),region,w->profile,1980+(w->fatTime>>25),
        (w->fatTime>>21)&15,(w->fatTime>>16)&31,level,time,w->verifyAdler);
}
static void exportService(void){
    struct TraceExportWriter*w=EXPORT_WRITER;struct MsTraceExportRequest q;struct MsTraceExportTransfer b;
    UINT done=0;FRESULT result;unsigned n;char final[160];
    if(w->response.phase==MS_TRACE_EXPORT_VERIFY){
        sync_before_read((void*)EXPORT_BOX,64);
        if(EXPORT_BOX->request.sequence==w->request.sequence&&EXPORT_BOX->request.bootNonce==w->response.bootNonce&&
           EXPORT_BOX->request.nonce==w->nonce&&EXPORT_BOX->request.run==w->run&&
           (EXPORT_BOX->transfer.flags&MS_TRACE_EXPORT_CANCEL_FLAG)){exportAbort(1);return;}
        n=w->response.bytes-w->offset;if(n>0x4000u)n=0x4000u;
        if(n){
            result=f_read(&w->file,EXPORT_DATA,n,&done);sync_after_write(EXPORT_DATA,n);
            if(result!=FR_OK||done!=n){exportFailure(MS_TRACE_IO);return;}
            w->verifyAdler=MsTraceAdler(w->verifyAdler,EXPORT_DATA,n);w->offset+=n;return;
        }
        if(w->verifyAdler!=w->expectedAdler){exportFailure(MS_TRACE_BAD_SOURCE);return;}
        if(f_close(&w->file)!=FR_OK){exportFailure(MS_TRACE_IO);return;}w->active=0;
        if(w->name[0])exportNamedPath(w,final);
        else{strcpy(final,w->path);strcpy(final+strlen(final)-4,completedSuffix);}
        if(f_rename_char(w->path,final)!=FR_OK){exportFailure(MS_TRACE_IO);return;}
        w->owned=0;w->response.ack=w->request.sequence;w->response.status=0;w->response.phase=MS_TRACE_EXPORT_DONE;
        w->response.checksum=w->verifyAdler;exportPublish();return;
    }
    sync_before_read((void*)EXPORT_BOX,64);memcpy(&q,(const void*)&EXPORT_BOX->request,32);memcpy(&b,(const void*)&EXPORT_BOX->transfer,32);
    if(!q.sequence||q.sequence==w->response.ack)return;w->request=q;
    if(q.magic!=MS_TRACE_EXPORT_MAGIC||q.version!=MS_TRACE_EXPORT_VERSION||q.bootNonce!=w->response.bootNonce||!q.nonce||!q.run||q.game!=GAME_ID||
       q.operation<MS_TRACE_EXPORT_BEGIN||q.operation>MS_TRACE_EXPORT_ABORT){exportFailure(MS_TRACE_PROTOCOL);return;}
    if(b.flags&MS_TRACE_EXPORT_CANCEL_FLAG){
        if((w->active||w->owned)&&(q.nonce!=w->nonce||q.run!=w->run||q.game!=w->game)){exportFailure(MS_TRACE_PROTOCOL);return;}
        exportAbort(1);return;
    }
    if(q.operation==MS_TRACE_EXPORT_BEGIN){
        FILINFO info;const char*region=q.game==0x474d534au?regionJp:q.game==0x474d5345u?regionUs:regionPal;
        if(w->active||w->owned||WRITER->active||!SusamuneCfgStorageAvailable()||strlen(SusamuneCfgStoragePrefix())>60||
           b.totalBytes||(b.flags&~0xff03u)||(b.flags>>8)>4){exportFailure(MS_TRACE_PROTOCOL);return;}
        memset(w->name,0,sizeof(w->name));
        if(b.flags&MS_TRACE_EXPORT_NAMED){
            if(!(b.flags&MS_TRACE_EXPORT_PUBLIC)||b.physical!=MS_TRACE_EXPORT_BUFFER_PHYS||b.capacity!=MS_TRACE_EXPORT_BUFFER_BYTES||
                b.bytes!=MS_TRACE_EXPORT_NAME_BYTES||!b.lease||b.fileAdler!=1){exportFailure(MS_TRACE_PROTOCOL);return;}
            sync_before_read(EXPORT_DATA,b.bytes);
            if(b.checksum!=MsTraceHash(2166136261u,EXPORT_DATA,b.bytes)||!MsTraceExportNameValid(EXPORT_DATA)){exportFailure(MS_TRACE_BAD_SOURCE);return;}
            memcpy(w->name,EXPORT_DATA,sizeof(w->name));w->fatTime=get_fattime();
        }else if(b.physical||b.capacity||b.bytes||b.lease||b.checksum||b.fileAdler){exportFailure(MS_TRACE_PROTOCOL);return;}
        w->profile=b.flags>>8;w->publicFile=b.flags&1;w->response.bytes=0;w->response.checksum=w->adler=1;w->identity.version=0;
        if(w->publicFile){
            _sprintf(w->path,shareDirectory,SusamuneCfgStoragePrefix());if(!exportDirectory(w->path)){exportFailure(MS_TRACE_IO);return;}
            _sprintf(w->path,shareRegion,SusamuneCfgStoragePrefix(),region);if(!exportDirectory(w->path)){exportFailure(MS_TRACE_IO);return;}
            _sprintf(w->path,shareProfile,SusamuneCfgStoragePrefix(),region,w->profile);if(!exportDirectory(w->path)){exportFailure(MS_TRACE_IO);return;}
            _sprintf(w->path,shareFile,SusamuneCfgStoragePrefix(),region,w->profile,q.nonce,q.run);
        }else{
            _sprintf(w->path,directoryFormat,SusamuneCfgStoragePrefix());if(!exportDirectory(w->path)){exportFailure(MS_TRACE_IO);return;}
            _sprintf(w->path,fileFormat,SusamuneCfgStoragePrefix(),q.nonce,q.run);
        }
        strcpy(final,w->path);strcpy(final+strlen(final)-4,completedSuffix);result=f_stat_char(final,&info);
        if(result!=FR_NO_FILE&&result!=FR_NO_PATH){exportFailure(MS_TRACE_BAD_SOURCE);return;}
        if(f_open_char(&w->file,w->path,FA_WRITE|FA_CREATE_NEW)!=FR_OK){exportFailure(MS_TRACE_IO);return;}
        w->active=w->owned=1;w->nonce=q.nonce;w->run=q.run;w->game=q.game;w->response.status=0;w->response.phase=MS_TRACE_EXPORT_OPEN;w->response.ack=q.sequence;exportPublish();return;
    }
    if(q.nonce!=w->nonce||q.run!=w->run||q.game!=w->game){exportFailure(MS_TRACE_PROTOCOL);return;}
    if(q.operation==MS_TRACE_EXPORT_ABORT){exportAbort(0);return;}
    if(!w->active||w->response.phase!=MS_TRACE_EXPORT_OPEN||b.physical!=MS_TRACE_EXPORT_BUFFER_PHYS||b.capacity!=MS_TRACE_EXPORT_BUFFER_BYTES||
       !b.lease||!b.bytes||b.bytes>MS_TRACE_EXPORT_MAX_WRITE||b.totalBytes!=w->response.bytes||b.flags){exportFailure(MS_TRACE_PROTOCOL);return;}
    sync_before_read(EXPORT_DATA,b.bytes);
    if(MsTraceHash(2166136261u,EXPORT_DATA,b.bytes)!=b.checksum){exportFailure(MS_TRACE_BAD_SOURCE);return;}
    if(q.operation==MS_TRACE_EXPORT_APPEND){
        if(b.bytes>MS_TRACE_FILE_LIMIT-w->response.bytes||(!w->response.bytes&&(b.bytes!=64||!exportHeader(EXPORT_DATA,&q)))||
           MsTraceAdler(w->adler,EXPORT_DATA,b.bytes)!=b.fileAdler){exportFailure(MS_TRACE_PROTOCOL);return;}
        if(!w->response.bytes)memcpy(w->header,EXPORT_DATA,64);
        if(f_write(&w->file,EXPORT_DATA,b.bytes,&done)!=FR_OK||done!=b.bytes){exportFailure(MS_TRACE_IO);return;}
        if(b.bytes>=32)memcpy(w->tail,EXPORT_DATA+b.bytes-32,32);
        else{memmove(w->tail,w->tail+b.bytes,32-b.bytes);memcpy(w->tail+32-b.bytes,EXPORT_DATA,b.bytes);}
        w->adler=b.fileAdler;w->response.checksum=w->adler;w->response.bytes+=b.bytes;w->response.ack=q.sequence;w->response.status=0;exportPublish();return;
    }
    if(b.bytes!=64||w->response.bytes<96||!exportHeader(EXPORT_DATA,&q)||
       MsTraceGet(w->tail)!=0x444f4e45u||MsTraceGet(w->tail+4)!=q.run||MsTraceGet(w->tail+12)!=w->response.bytes-32||
       MsTraceGet(w->tail+16)!=MsTraceGet(EXPORT_DATA+28)||MsTraceGet(w->tail+8)>(w->response.bytes-96)/32||
       MsTraceAdlerReplaceHeader(w->adler,w->header,EXPORT_DATA,w->response.bytes)!=b.fileAdler){exportFailure(MS_TRACE_BAD_SOURCE);return;}
    memcpy(w->header,EXPORT_DATA,64);
    if(f_lseek(&w->file,0)!=FR_OK||f_write(&w->file,w->header,64,&done)!=FR_OK||done!=64||f_sync(&w->file)!=FR_OK||f_close(&w->file)!=FR_OK){exportFailure(MS_TRACE_IO);return;}
    w->active=0;
    if(f_open_char(&w->file,w->path,FA_READ|FA_OPEN_EXISTING)!=FR_OK){exportFailure(MS_TRACE_IO);return;}w->active=1;
    if(f_size(&w->file)!=w->response.bytes){exportFailure(MS_TRACE_IO);return;}
    w->identity.version=3;w->identity.game=q.game;w->identity.scene=MsTraceGet(w->header+24);w->identity.capabilities=MsTraceGet(w->header+28);
    w->identity.bytes=w->response.bytes;w->identity.chunks=MsTraceGet(w->tail+8);w->identity.headerHash=MsTraceGet(w->header+60);w->identity.footerHash=MsTraceHash(2166136261u,w->tail,32);
    w->offset=0;w->verifyAdler=1;w->expectedAdler=b.fileAdler;w->response.phase=MS_TRACE_EXPORT_VERIFY;exportPublish();
}
