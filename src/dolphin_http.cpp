#include "susamune/dolphin_http.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/dolphin_http_api.hxx"
#include "susamune/addresses.hxx"
#include "susamune/ghost_service.h"
const DolphinHttpApi *dolphinHttpApi(){
    const auto *p=reinterpret_cast<const DolphinHttpApi *>(DOLPHIN_HTTP_API_BASE);
    if(p->magic!=DOLPHIN_HTTP_API_MAGIC || p->version!=1 || p->apiBytes!=sizeof(*p))return nullptr;
    const u32 *calls=reinterpret_cast<const u32 *>(&p->begin);
    for(unsigned i=0;i<9;++i)if(calls[i]&3 || calls[i]<DOLPHIN_HTTP_API_BASE+sizeof(*p) ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
    return p;
}
namespace DolphinHttp {
bool begin(const char *path,const DolphinHttpsRequest *r,void *out,unsigned capacity){const auto *p=dolphinHttpApi();return p && p->begin(dolphinStorageHost(),SUSAMUNE_GAME_VERSION,path,r,out,capacity);}
void update(){const auto *p=dolphinHttpApi();if(p)p->update();}
unsigned phase(){const auto *p=dolphinHttpApi();return p?p->phase():0;}
int take(DolphinHttpsInfo *out){const auto *p=dolphinHttpApi();return p?p->take(out):GHOST_SERVICE_NETWORK;}
void cancel(){const auto *p=dolphinHttpApi();if(p)p->cancel();}
bool close(){const auto *p=dolphinHttpApi();return !p || p->close();}
}
#endif
