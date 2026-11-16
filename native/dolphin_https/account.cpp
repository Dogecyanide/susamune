#include "susamune/dolphin_storage_api.hxx"
#include "susamune/dolphin_web_api.h"
extern "C" {
#include "../../../launcher/kernel/GhostServiceAccount.h"
#include <string.h>
extern const DolphinHttpsApi moonshine_https_api;
void MoonshineNativeInit(void);
}
namespace {
const char kFile[]="ms_delfino_link";
struct Record {
    unsigned magic,version,generation,linked;
    GhostAccountSecret secret;
    unsigned char reserved[64],digest[32];
};
static_assert(sizeof(Record)==256,"Account journal layout");
enum Phase {IDLE,LOAD0,LOAD1,READY,GHOST,HTTP,CREATE,BLANK,WRITE,VERIFY,REMOVE,DONE};
struct Work {
    const DolphinStorageHost *host;
    GhostAccount account;GhostAccountWork protocol;GhostAccountFlow flow;
    Record banks[2],next,check;
    char body[16384];
    SusamuneGhostStorageRequest request;SusamuneGhostStorageResponse response;
    u32 ticket,bytes;unsigned bank,action,generation;
    Phase phase;int result,afterSave;
    bool loaded,exists,corrupt;
};
Work &s=*reinterpret_cast<Work *>(DOLPHIN_ACCOUNT_WORK_BASE);
static_assert(sizeof(Work)<=DOLPHIN_ACCOUNT_WORK_SIZE,"Account work exceeds library gap");
bool initialized;
void *payload(){return reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE);}
bool zero(const void *data,unsigned n){const auto *p=static_cast<const unsigned char *>(data);while(n--)if(*p++)return false;return true;}
void digest(Record *r){moonshine_https_api.sha256(r,224,r->digest);}
bool valid(const Record &r){
    if(r.magic!=0x4d414331u || r.version!=1 || !r.generation || r.linked>1 || !zero(r.reserved,sizeof(r.reserved)))return false;
    if(r.linked?!GhostAccountSecretValid(&r.secret):!zero(&r.secret,sizeof(r.secret)))return false;
    unsigned char hash[32];moonshine_https_api.sha256(&r,224,hash);return !memcmp(hash,r.digest,32);
}
void finish(int result){
    s.response={};auto &r=s.response;r.responseMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;
    r.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;r.flags=SUSAMUNE_GHOST_RESPONSE_READY;
    r.ackSeq=s.request.requestSeq;r.profile=s.request.profile;r.slot=s.request.slot;r.status=result;
    if(!result && s.request.command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT){
        GhostAccountInfo(&s.account,s.host->seconds(),static_cast<GhostServiceAccountInfo *>(payload()));
        r.payloadSize=sizeof(GhostServiceAccountInfo);
    }
    memset(s.protocol.body,0,sizeof(s.protocol.body));memset(s.protocol.headers,0,sizeof(s.protocol.headers));
    memset(s.body,0,sizeof(s.body));memset(&s.next,0,sizeof(s.next));memset(&s.check,0,sizeof(s.check));
    s.phase=DONE;
}
void storageError(){
    // A failed write may already be durable: never retry an old refresh token.
    memset(&s.account,0,sizeof(s.account));s.corrupt=true;finish(SUSAMUNE_GHOST_STATUS_IO(1));
}
void decideJournal(){
    bool a=valid(s.banks[0]),b=valid(s.banks[1]);
    if(a && b){
        s.bank=s.banks[1].generation>s.banks[0].generation?1:0;
        s.corrupt=s.banks[s.bank].generation-s.banks[1-s.bank].generation!=1;
    }else if(a || b){
        s.bank=b?1:0;s.corrupt=s.banks[s.bank].generation!=1 || !zero(&s.banks[1-s.bank],sizeof(Record));
    }else s.corrupt=true;
    if(!s.corrupt){s.generation=s.banks[s.bank].generation;s.account.secret=s.banks[s.bank].secret;}
    memset(s.banks,0,sizeof(s.banks));s.loaded=true;s.phase=READY;
}
void save(const GhostAccountSecret *secret,int after){
    if(s.generation==0xffffffffu){storageError();return;}
    s.next={};s.next.magic=0x4d414331u;s.next.version=1;s.next.generation=s.generation+1;
    if(secret && GhostAccountSecretValid(secret)){s.next.secret=*secret;s.next.linked=1;}
    digest(&s.next);s.afterSave=after;s.phase=s.exists?WRITE:CREATE;
}
void http(){
    const auto &r=s.protocol.request;DolphinHttpsRequest request={r.method,r.headers,r.body,r.bytes};
    if(!s.host->httpBegin(s.protocol.path,&request,s.body,sizeof(s.body))){finish(GHOST_SERVICE_NETWORK);return;}
    s.phase=HTTP;
}
void advance(int result){
    s.result=result;
    if(s.account.changed){s.account.changed=0;save(&s.account.secret,result==1?1:0);return;}
    if(result==1)http();else finish(result);
}
void start(){
    int result=GhostAccountBegin(&s.account,&s.protocol,&s.flow,s.action,s.host->seconds(),payload(),s.bytes);
    if(s.action==GHOST_ACCOUNT_UPLOAD && result==1)s.account.changed=0;
    advance(result);
}
void ready(){
    if(s.corrupt){if(s.action==GHOST_ACCOUNT_UNLINK)s.phase=REMOVE;else finish(SUSAMUNE_GHOST_STATUS_INVALID_FILE);return;}
    if(s.action==GHOST_ACCOUNT_UPLOAD){
        if(!GhostAccountSecretValid(&s.account.secret)){finish(GHOST_SERVICE_LINK_REQUIRED);return;}
        auto request=s.request;request.command=SUSAMUNE_GHOST_CMD_LOAD;request.payloadSize=0;
        if(!s.host->ghostBegin(request)){finish(SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE);return;}
        s.phase=GHOST;return;
    }
    if(s.action==GHOST_ACCOUNT_UNLINK && GhostAccountSecretValid(&s.account.secret))save(nullptr,2);
    else start();
}
bool begin(const SusamuneGhostStorageRequest &r,const DolphinStorageHost *host){
    MoonshineNativeInit();
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    if(s.phase!=IDLE || !host)return false;
    s.host=host;s.request=r;s.bytes=0;s.result=0;s.protocol={};s.account.changed=0;
    s.protocol.json=reinterpret_cast<GhostJson *>(DOLPHIN_WEB_JSON_BASE);
    s.protocol.response=s.body;s.protocol.capacity=sizeof(s.body);s.protocol.clientName="Moonshine Dolphin";
    if(r.requestMagic!=SUSAMUNE_GHOST_STORAGE_MAGIC || r.protocolVersion!=SUSAMUNE_GHOST_STORAGE_VERSION || r.flags || r.reserved){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
    if(r.command==SUSAMUNE_GHOST_CMD_WEB_ACCOUNT){
        if(r.profile!=SUSAMUNE_GHOST_IMPORTED_PROFILE || r.slot>GHOST_ACCOUNT_UNLINK || r.payloadSize){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
        s.action=r.slot;
    }else if(r.command==SUSAMUNE_GHOST_CMD_WEB_UPLOAD){
        if(!SusamuneGhostPersonalProfile(r.profile) || r.payloadSize!=sizeof(GhostServiceUpload)){finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
        memcpy(&s.protocol.upload,payload(),sizeof(GhostServiceUpload));
        if(!GhostServiceDescriptionValid(s.protocol.upload.description)){finish(GHOST_SERVICE_UPLOAD_REJECTED);return true;}
        s.action=GHOST_ACCOUNT_UPLOAD;
    }else{finish(SUSAMUNE_GHOST_STATUS_INVALID_REQUEST);return true;}
    s.phase=s.loaded?READY:LOAD0;return true;
}
void update(){
    if(!initialized || s.phase==IDLE || s.phase==DONE)return;
    if(s.phase==READY){ready();return;}
    if(s.phase==GHOST){
        s.host->ghostUpdate();SusamuneGhostStorageResponse r;
        if(!s.host->ghostTake(&r))return;
        if(r.status){finish(r.status);return;}
        s.bytes=r.payloadSize;save(nullptr,2);return;
    }
    if(s.phase==HTTP){
        s.host->httpUpdate();DolphinHttpsInfo info={};int result=s.host->httpTake(&info);
        if(result!=1)advance(GhostAccountNext(&s.account,&s.protocol,&s.flow,result,info.used,info.httpStatus));
        return;
    }
    if(!s.ticket){
        if(s.phase==LOAD0 || s.phase==LOAD1){unsigned bank=s.phase==LOAD1;s.ticket=s.host->read(kFile,&s.banks[bank],256,bank*8192);}
        else if(s.phase==CREATE)s.ticket=s.host->create(kFile,16384);
        else if(s.phase==BLANK){s.check={};s.ticket=s.host->write(kFile,&s.check,256,8192);}
        else if(s.phase==WRITE)s.ticket=s.host->write(kFile,&s.next,256,(1-s.bank)*8192);
        else if(s.phase==VERIFY)s.ticket=s.host->read(kFile,&s.check,256,(1-s.bank)*8192);
        else if(s.phase==REMOVE)s.ticket=s.host->remove(kFile);
        return;
    }
    DolphinFiles::Result r;if(!s.host->fileTake(s.ticket,&r))return;s.ticket=0;
    if(s.phase==LOAD0 && r.error==-4){s.loaded=true;s.exists=false;s.bank=1;s.phase=READY;return;}
    if(r.error){storageError();return;}
    if(s.phase==LOAD0){s.exists=true;s.phase=LOAD1;return;}
    if(s.phase==LOAD1){decideJournal();return;}
    if(s.phase==REMOVE){memset(&s.account,0,sizeof(s.account));s.corrupt=s.exists=false;s.generation=0;s.bank=1;finish(0);return;}
    if(s.phase==CREATE){s.exists=true;s.phase=BLANK;return;}
    if(s.phase==BLANK){s.phase=WRITE;return;}
    if(s.phase==WRITE){s.phase=VERIFY;return;}
    if(s.phase==VERIFY){
        if(memcmp(&s.next,&s.check,sizeof(Record)) || !valid(s.check)){storageError();return;}
        s.bank=1-s.bank;s.generation=s.next.generation;
        if(s.afterSave==2)start();else if(s.afterSave==1)http();else finish(s.result);
    }
}
bool take(SusamuneGhostStorageResponse *out){
    if(!initialized || s.phase!=DONE || !out)return false;
    *out=s.response;s.phase=IDLE;return true;
}
}
namespace NativeStorage { bool libraryBegin(const SusamuneGhostStorageRequest &,const DolphinStorageHost *,unsigned); }
__attribute__((section(".storageapi"),used)) const DolphinStorageApi moonshine_storage_api={
    DOLPHIN_STORAGE_API_MAGIC,2,sizeof(DolphinStorageApi),begin,update,take,
    NativeStorage::libraryBegin,DolphinGhostLibrary::update,DolphinGhostLibrary::take
};
