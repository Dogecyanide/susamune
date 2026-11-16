#include "susamune/dolphin_ghost_account.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include <Dolphin/OS.h>
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/ghost.hxx"
#include "susamune/live_transport.hxx"
#include "susamune/live_race.hxx"
namespace {
unsigned milliseconds(){return static_cast<unsigned>(OSGetTime()/(OS_TIMER_CLOCK/1000));}
unsigned networkState(){return LiveTransport::poll().state;}
bool networkBegin(){return LiveTransport::begin(0);}
void networkStopIfIdle(){if(!LiveRace::status().active)LiveTransport::stop();}
unsigned seconds(){return static_cast<unsigned>(OSGetTime()/(OS_TIMER_CLOCK));}
const DolphinStorageHost dolphinStorageCallbacks={DolphinFiles::read,DolphinFiles::write,DolphinFiles::create,
    DolphinFiles::remove,DolphinFiles::take,DolphinHttp::begin,DolphinHttp::update,DolphinHttp::take,
    DolphinGhostLibrary::begin,DolphinGhostLibrary::update,DolphinGhostLibrary::take,seconds,DolphinFiles::list,Ghost::inspectFile,milliseconds,networkState,networkBegin,networkStopIfIdle,DolphinNetwork::resolve,DolphinNetwork::dnsResult,DolphinNetwork::cancelResolve};
}
const DolphinStorageHost *dolphinStorageHost(){return &dolphinStorageCallbacks;}
const DolphinStorageApi *dolphinStorageApi(){
    const auto *p=reinterpret_cast<const DolphinStorageApi *>(DOLPHIN_STORAGE_API_BASE);
    if(p->magic!=DOLPHIN_STORAGE_API_MAGIC || p->version!=2 || p->apiBytes!=sizeof(*p))return nullptr;
    const u32 *calls=reinterpret_cast<const u32 *>(&p->begin);
    for(unsigned i=0;i<6;++i)if(calls[i]&3 || calls[i]<DOLPHIN_STORAGE_API_BASE+sizeof(*p) ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
    return p;
}
namespace DolphinGhostAccount {
bool begin(const SusamuneGhostStorageRequest &r){const auto *p=dolphinStorageApi();return p && p->begin(r,&dolphinStorageCallbacks);}
void update(){const auto *p=dolphinStorageApi();if(p)p->update();}
bool take(SusamuneGhostStorageResponse *out){const auto *p=dolphinStorageApi();return p && p->take(out);}
}
#endif
