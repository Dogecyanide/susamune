#include "GhostReplayReport.h"
#if MOONSHINE_GHOST_TRACE
#include "global.h"
#include "SusamuneCfg.h"
#include "ff_utf8.h"
#include "susamune/ghost_replay_report.h"
#include "susamune/susamune_cfg.h"
#include <string.h>

extern u32 GAME_ID;
enum ReportPhase {
    REPORT_IDLE, REPORT_OPEN, REPORT_WRITE, REPORT_FOOTER, REPORT_SYNC,
    REPORT_CLOSE_WRITE, REPORT_OPEN_VERIFY, REPORT_VERIFY, REPORT_VERIFY_FOOTER,
    REPORT_CLOSE_VERIFY, REPORT_PUBLISH, REPORT_CLEANUP
};
struct ReplayReportWriter {
    FIL file;
    char path[128];
    struct MsReplayReportRequest request;
    struct MsReplayReportResponse response;
    unsigned phase,open,owned,offset,checksum,error;
    unsigned char header[64],verify[512];
};
typedef char ReplayReportWriterFits[sizeof(struct ReplayReportWriter)<=MS_REPLAY_REPORT_ARM_BYTES?1:-1];
#define REPORT_WRITER ((struct ReplayReportWriter*)(MS_TRACE_CONTROL_PHYS+MS_REPLAY_REPORT_ARM_OFFSET))
#define REPORT_BOX ((volatile struct MsReplayReportMailbox*)MS_REPLAY_REPORT_MAILBOX_PHYS)
#define REPORT_DATA ((const unsigned char*)MS_REPLAY_REPORT_DATA_PHYS)
static int reportInitialized;

static unsigned reportNonce(void) {
    const struct MoonshineGhostMemoryProof*proof=(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE;
    const struct SusamuneCfg*cfg=SUSAMUNE_CFG_PHYS_PTR;
    if(cfg->magic!=SUSAMUNE_CFG_MAGIC||cfg->version!=SUSAMUNE_CFG_VERSION||
       !(cfg->flags&MOONSHINE_GHOST_MEMORY_FLAG))return 0;
    sync_before_read((void*)proof,sizeof(*proof));
    return MoonshineGhostMemoryProofValid(proof,GAME_ID)?proof->word[MGM_NONCE]:0;
}
static void reportPublish(void) {
    memcpy((void*)&REPORT_BOX->response,&REPORT_WRITER->response,32);
    sync_after_write((void*)&REPORT_BOX->response,32);
}
static void reportFinish(unsigned status) {
    struct ReplayReportWriter*w=REPORT_WRITER;
    w->response.status=status;
    w->response.bytes=status?0:w->request.payloadBytes;
    w->response.ack=w->request.sequence;
    w->phase=REPORT_IDLE;
    reportPublish();
}
static void reportFail(unsigned status) {
    REPORT_WRITER->error=status;
    REPORT_WRITER->phase=REPORT_CLEANUP;
}
static int reportClose(void) {
    struct ReplayReportWriter*w=REPORT_WRITER;
    if(w->open&&f_close(&w->file)!=FR_OK)return 0;
    w->open=0;
    return 1;
}
static void reportCleanup(void) {
    struct ReplayReportWriter*w=REPORT_WRITER;
    FRESULT result;
    if(!reportClose())return;
    if(w->owned) {
        result=f_unlink_char(w->path);
        if(result!=FR_OK&&result!=FR_NO_FILE&&result!=FR_NO_PATH)return;
        w->owned=0;
    }
    reportFinish(w->error);
}
static void reportFinalPath(char*path) {
    strcpy(path,REPORT_WRITER->path);
    strcpy(path+strlen(path)-4,"bin");
}
static void reportFooter(unsigned char footer[32]) {
    const struct MsReplayReportRequest*q=&REPORT_WRITER->request;
    memset(footer,0,32);
    MsReplayReportPut(footer,MS_REPLAY_REPORT_END_MAGIC);
    MsReplayReportPut(footer+4,MS_REPLAY_REPORT_VERSION);
    MsReplayReportPut(footer+8,q->bootNonce);
    MsReplayReportPut(footer+12,q->sequence);
    MsReplayReportPut(footer+16,q->payloadBytes);
    MsReplayReportPut(footer+20,q->checksum);
}
void GhostReplayReportInit(void) {
    struct ReplayReportWriter*w=REPORT_WRITER;
    unsigned nonce;
    // Reinjection cannot erase an open handle or an unacknowledged source lease.
    if(reportInitialized&&w->phase!=REPORT_IDLE)return;
    nonce=reportNonce();
    if(!nonce)return;
    if(reportInitialized&&w->response.bootNonce==nonce)return;
    memset(w,0,sizeof(*w));
    w->response.magic=MS_REPLAY_REPORT_MAGIC;
    w->response.version=MS_REPLAY_REPORT_VERSION;
    w->response.bootNonce=nonce;
    memset((void*)&REPORT_BOX->request,0,32);
    sync_after_write((void*)&REPORT_BOX->request,32);
    reportInitialized=1;
    reportPublish();
}
int GhostReplayReportPending(void) {
    if(!reportInitialized)return 0;
    if(REPORT_WRITER->phase!=REPORT_IDLE)return 1;
    if(reportNonce()!=REPORT_WRITER->response.bootNonce)return 0;
    sync_before_read((void*)&REPORT_BOX->request,32);
    return REPORT_BOX->request.sequence&&REPORT_BOX->request.sequence!=REPORT_WRITER->response.ack;
}
void GhostReplayReportService(void) {
    struct ReplayReportWriter*w=REPORT_WRITER;
    struct MsReplayReportRequest request;
    FILINFO info;
    FRESULT result;
    UINT done=0;
    unsigned amount,budget,i;
    unsigned char footer[32];
    char path[128];
    if(!reportInitialized)return;
    if(w->phase==REPORT_CLEANUP){reportCleanup();return;}
    sync_before_read((void*)&REPORT_BOX->request,32);
    memcpy(&request,(const void*)&REPORT_BOX->request,32);
    if(w->phase==REPORT_IDLE) {
        if(!request.sequence||request.sequence==w->response.ack)return;
        w->request=request;w->offset=w->owned=w->open=0;
        if(reportNonce()!=w->response.bootNonce||!MsReplayReportRequestValid(&request,w->response.bootNonce)) {
            reportFinish(MS_REPLAY_REPORT_BAD_REQUEST);return;
        }
        sync_before_read((void*)REPORT_DATA,64);
        memcpy(w->header,REPORT_DATA,64);
        if(!MsReplayReportHeaderValid(w->header,&request,GAME_ID)) {
            reportFinish(MS_REPLAY_REPORT_BAD_PAYLOAD);return;
        }
        if(!SusamuneCfgStorageAvailable()){reportFinish(MS_REPLAY_REPORT_NO_STORAGE);return;}
        if(strlen(SusamuneCfgStoragePrefix())>sizeof(w->path)-36) {
            reportFinish(MS_REPLAY_REPORT_BAD_REQUEST);return;
        }
        _sprintf(w->path,"%s/logs/replay_%08X_%08X.part",SusamuneCfgStoragePrefix(),request.bootNonce,request.sequence);
        w->phase=REPORT_OPEN;return;
    }
    if(reportNonce()!=w->response.bootNonce||memcmp(&request,&w->request,32)) {
        reportFail(MS_REPLAY_REPORT_STALE);return;
    }
    if(w->phase==REPORT_OPEN) {
        reportFinalPath(path);result=f_stat_char(path,&info);
        if(result==FR_OK){reportFail(MS_REPLAY_REPORT_EXISTS);return;}
        if(result!=FR_NO_FILE&&result!=FR_NO_PATH){reportFail(MS_REPLAY_REPORT_IO);return;}
        result=f_mkdir_char(SusamuneCfgStoragePrefix());
        if(result!=FR_OK&&result!=FR_EXIST){reportFail(MS_REPLAY_REPORT_IO);return;}
        _sprintf(path,"%s/logs",SusamuneCfgStoragePrefix());result=f_mkdir_char(path);
        if(result!=FR_OK&&result!=FR_EXIST){reportFail(MS_REPLAY_REPORT_IO);return;}
        result=f_open_char(&w->file,w->path,FA_WRITE|FA_CREATE_NEW);
        if(result!=FR_OK){reportFail(result==FR_EXIST?MS_REPLAY_REPORT_EXISTS:MS_REPLAY_REPORT_IO);return;}
        w->open=w->owned=1;w->phase=REPORT_WRITE;return;
    }
    if(w->phase==REPORT_WRITE) {
        amount=w->request.payloadBytes-w->offset;
        if(amount>MS_REPLAY_REPORT_TRANSFER_BYTES)amount=MS_REPLAY_REPORT_TRANSFER_BYTES;
        sync_before_read((void*)(REPORT_DATA+w->offset),amount);
        result=f_write(&w->file,REPORT_DATA+w->offset,amount,&done);
        if(result!=FR_OK||done!=amount){reportFail(MS_REPLAY_REPORT_IO);return;}
        w->offset+=amount;
        if(w->offset==w->request.payloadBytes)w->phase=REPORT_FOOTER;
        return;
    }
    if(w->phase==REPORT_FOOTER) {
        reportFooter(footer);
        if(f_write(&w->file,footer,32,&done)!=FR_OK||done!=32){reportFail(MS_REPLAY_REPORT_IO);return;}
        w->phase=REPORT_SYNC;return;
    }
    if(w->phase==REPORT_SYNC) {
        if(f_sync(&w->file)!=FR_OK){reportFail(MS_REPLAY_REPORT_IO);return;}
        w->phase=REPORT_CLOSE_WRITE;return;
    }
    if(w->phase==REPORT_CLOSE_WRITE) {
        if(!reportClose())return;
        w->phase=REPORT_OPEN_VERIFY;return;
    }
    if(w->phase==REPORT_OPEN_VERIFY) {
        if(f_open_char(&w->file,w->path,FA_READ|FA_OPEN_EXISTING)!=FR_OK){reportFail(MS_REPLAY_REPORT_IO);return;}
        w->open=1;
        if(f_size(&w->file)!=w->request.payloadBytes+32){reportFail(MS_REPLAY_REPORT_BAD_PAYLOAD);return;}
        w->offset=0;w->checksum=2166136261u;w->phase=REPORT_VERIFY;return;
    }
    if(w->phase==REPORT_VERIFY) {
        for(budget=0;budget<MS_REPLAY_REPORT_TRANSFER_BYTES&&w->offset<w->request.payloadBytes;budget+=amount) {
            amount=w->request.payloadBytes-w->offset;
            if(amount>sizeof(w->verify))amount=sizeof(w->verify);
            if(f_read(&w->file,w->verify,amount,&done)!=FR_OK||done!=amount){reportFail(MS_REPLAY_REPORT_IO);return;}
            if(!w->offset&&memcmp(w->verify,w->header,64)){reportFail(MS_REPLAY_REPORT_BAD_PAYLOAD);return;}
            for(i=0;i<amount;++i) {
                unsigned at=w->offset+i;
                if(at>=MS_REPLAY_REPORT_MIN_BYTES&&
                   (at-MS_REPLAY_REPORT_MIN_BYTES)%MS_REPLAY_REPORT_ACTOR_BYTES>=252&&w->verify[i]) {
                    reportFail(MS_REPLAY_REPORT_BAD_PAYLOAD);return;
                }
            }
            w->checksum=MsReplayReportHash(w->checksum,w->verify,amount);
            w->offset+=amount;
        }
        if(w->offset==w->request.payloadBytes) {
            if(w->checksum!=w->request.checksum){reportFail(MS_REPLAY_REPORT_BAD_PAYLOAD);return;}
            w->phase=REPORT_VERIFY_FOOTER;
        }
        return;
    }
    if(w->phase==REPORT_VERIFY_FOOTER) {
        reportFooter(footer);
        if(f_read(&w->file,w->verify,32,&done)!=FR_OK||done!=32||memcmp(w->verify,footer,32)) {
            reportFail(MS_REPLAY_REPORT_BAD_PAYLOAD);return;
        }
        w->phase=REPORT_CLOSE_VERIFY;return;
    }
    if(w->phase==REPORT_CLOSE_VERIFY) {
        if(!reportClose())return;
        w->phase=REPORT_PUBLISH;return;
    }
    if(w->phase==REPORT_PUBLISH) {
        reportFinalPath(path);result=f_stat_char(path,&info);
        if(result==FR_OK){reportFail(MS_REPLAY_REPORT_EXISTS);return;}
        if(result!=FR_NO_FILE&&result!=FR_NO_PATH){reportFail(MS_REPLAY_REPORT_IO);return;}
        if(f_rename_char(w->path,path)!=FR_OK){reportFail(MS_REPLAY_REPORT_IO);return;}
        w->owned=0;reportFinish(MS_REPLAY_REPORT_OK);
    }
}
#endif
