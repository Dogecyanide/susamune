#include "susamune/dolphin_entropy.hxx"
#if IS_EMULATOR
#include <Dolphin/mem.h>
#include "susamune/addresses.hxx"
#include "susamune/dolphin_files.hxx"
#include "susamune/ghost_service.h"
namespace DolphinHttps {
const DolphinHttpsApi *api() {
    const auto *p=reinterpret_cast<const DolphinHttpsApi *>(DOLPHIN_HTTPS_IMAGE_BASE);
    if(p->magic!=DOLPHIN_HTTPS_MAGIC || p->version!=DOLPHIN_HTTPS_VERSION ||
       p->apiBytes!=sizeof(*p) || !p->workBytes || p->workBytes>DOLPHIN_HTTPS_WORK_CAPACITY)return nullptr;
    const auto *calls=reinterpret_cast<const u32 *>(&p->initialize);
    for(u32 i=0;i<6;++i)if((calls[i]&3) || calls[i]<DOLPHIN_HTTPS_IMAGE_BASE+sizeof(*p) ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
    return p;
}
}
#endif
