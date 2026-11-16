#include "susamune/dolphin_ghost_web.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include <Dolphin/mem.h>
#include "susamune/addresses.hxx"
#include "susamune/dolphin_http.hxx"
#include "susamune/dolphin_web_api.h"
#include "susamune/dolphin_files.hxx"
#include "susamune/dolphin_entropy.hxx"
#include "susamune/dolphin_ghost_library.hxx"
#include "susamune/ghost.hxx"
namespace DolphinGhostWeb {
namespace {
enum Step {HTTP,STORE};
struct Work {
    char path[704];GhostServiceQuery query;DolphinHttpsInfo info;
    GhostServiceEntry entry;Step step;
    bool active,complete,closing,download;int result;
};
Work &s=*reinterpret_cast<Work *>(DOLPHIN_HTTPS_WORK_BASE+0xD000u);
static_assert(DOLPHIN_HTTPS_WORK_BASE+0xD000u+sizeof(Work)<=DOLPHIN_HTTPS_IMAGE_BASE,"Native ghost browser work overlaps its image");
bool initialized;
const DolphinWebApi *api() {
    const auto *p=reinterpret_cast<const DolphinWebApi *>(DOLPHIN_WEB_API_BASE);
    if(p->magic!=DOLPHIN_WEB_API_MAGIC || p->version!=3 || p->apiBytes!=sizeof(*p))return nullptr;
    const u32 *calls=reinterpret_cast<const u32 *>(&p->query);
    for(u32 i=0;i<6;++i)if(calls[i]&3 || calls[i]<DOLPHIN_WEB_API_BASE+sizeof(*p) ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
    return p;
}
void *buffer(){return reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE);}
}
bool sanitizeSlot(const SusamuneGhostSlotInfo &raw,SusamuneGhostSlotInfo *out,bool imported) {
    const auto *p=api();return p && p->catalog(&raw,out,imported,SUSAMUNE_GAME_VERSION);
}
bool begin(const GhostServiceQuery &query) {
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    const auto *p=api();
    if(s.active || s.closing || !p || !p->query(&query,SUSAMUNE_GAME_VERSION,s.path,sizeof(s.path)))return false;
    s.query=query;s.info={};s.result=0;s.complete=false;s.download=false;s.step=HTTP;
    if(!DolphinHttp::begin(s.path,nullptr,buffer(),32768))return false;
    s.active=true;return true;
}
bool download(const GhostServiceEntry &entry) {
    if(!initialized){memset(&s,0,sizeof(s));initialized=true;}
    const auto *p=api();
    if(s.active || s.closing || !p || !p->entryValid(&entry) || !DolphinFiles::available())return false;
    s.entry=entry;s.info={};s.result=0;s.complete=false;s.download=true;s.step=HTTP;
    if(!DolphinHttp::begin(entry.path,nullptr,buffer(),entry.bytes))return false;
    s.active=true;return true;
}
void update() {
    if(!initialized || !s.active || s.complete)return;
    if(s.step==HTTP){
        DolphinHttp::update();s.result=DolphinHttp::take(&s.info);
        if(s.result==1)return;
        if(!s.result && s.info.httpStatus!=200)s.result=s.info.httpStatus==429?GHOST_SERVICE_RATE_LIMIT:
            s.info.httpStatus>=500?GHOST_SERVICE_UNAVAILABLE:GHOST_SERVICE_RESPONSE;
        if(s.result || !s.download){s.complete=true;return;}
        unsigned char digest[32];DolphinHttps::api()->sha256(buffer(),s.info.used,digest);
        if(s.info.used!=s.entry.bytes || memcmp(digest,s.entry.sha256,32))s.result=GHOST_SERVICE_HASH;
        if(s.result){s.complete=true;return;}
        SusamuneGhostStorageRequest request={};
        request.requestMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;request.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;
        request.command=SUSAMUNE_GHOST_CMD_SAVE;request.requestSeq=1;
        request.profile=SUSAMUNE_GHOST_IMPORTED_PROFILE;request.slot=SUSAMUNE_GHOST_SLOT_AUTO;request.payloadSize=s.info.used;
        if(!DolphinGhostLibrary::begin(request)){s.result=SUSAMUNE_GHOST_STATUS_STORAGE_UNAVAILABLE;s.complete=true;return;}
        s.step=STORE;
    }
    DolphinGhostLibrary::update();SusamuneGhostStorageResponse response;
    if(DolphinGhostLibrary::take(&response)){s.result=response.status;s.complete=true;}
}
int take(GhostServicePage *out) {
    if(!initialized || !s.active || !out)return GHOST_SERVICE_RESPONSE;
    if(!s.complete)return 1;
    int result=s.result;const auto *p=api();
    if(!s.download && !result && (!p || !p->page(buffer(),s.info.used,out)))result=GHOST_SERVICE_RESPONSE;
    if(!s.download && !result)out->reserved=(s.query.sortRoute?GHOST_SERVICE_SORTED_ROUTE:0)|(s.query.filter<<8);
    s.active=s.complete=false;
    if(s.closing){s.closing=false;DolphinHttp::close();}
    return result;
}
unsigned phase(){return initialized && s.download && s.step!=HTTP?GHOST_WEB_VALIDATE:DolphinHttp::phase();}
void close() {
    if(!initialized)return;
    if(s.active){s.closing=true;if(s.step==HTTP)DolphinHttp::cancel();}
    else DolphinHttp::close();
}
}
#endif
