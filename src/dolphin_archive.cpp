#include "susamune/dolphin_archive.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include "susamune/addresses.hxx"
namespace DolphinArchive {
namespace {
const DolphinArchiveApi *api(){
    const auto *p=reinterpret_cast<const DolphinArchiveApi *>(DOLPHIN_ARCHIVE_API_BASE);
    if(p->magic!=DOLPHIN_ARCHIVE_API_MAGIC || p->version!=1 || p->apiBytes!=sizeof(*p))return nullptr;
    const u32 *calls=reinterpret_cast<const u32 *>(&p->initialize);
    for(unsigned i=0;i<2;++i)if(calls[i]&3 || calls[i]<DOLPHIN_ARCHIVE_API_BASE+sizeof(*p) ||
        calls[i]>=DOLPHIN_HTTPS_IMAGE_BASE+DOLPHIN_HTTPS_IMAGE_CAPACITY)return nullptr;
    return p;
}
}
void initialize(){const auto *p=api();if(p)p->initialize(dolphinStorageHost(),SUSAMUNE_GAME_VERSION);}
void update(){const auto *p=api();if(p)p->update();}
}
#endif
