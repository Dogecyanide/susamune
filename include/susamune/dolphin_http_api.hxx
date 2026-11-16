#ifndef SUSAMUNE_DOLPHIN_HTTP_API_HXX
#define SUSAMUNE_DOLPHIN_HTTP_API_HXX
#include "dolphin_storage_api.hxx"
#define DOLPHIN_HTTP_API_BASE (DOLPHIN_HTTPS_IMAGE_BASE+0x180u)
#define DOLPHIN_HTTP_API_MAGIC 0x4d485431u
struct DolphinHttpApi {
    unsigned magic,version,apiBytes;
    bool (*begin)(const DolphinStorageHost *,unsigned,const char *,const DolphinHttpsRequest *,void *,unsigned);
    void (*update)();
    int (*take)(DolphinHttpsInfo *);
    unsigned (*phase)();
    void (*cancel)();
    bool (*close)();
    bool (*entropyBegin)(const DolphinStorageHost *,unsigned);
    void (*entropyUpdate)();
    int (*entropyTake)(void *);
};
const DolphinHttpApi *dolphinHttpApi();
#endif
