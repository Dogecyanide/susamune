#ifndef MOONSHINE_DOLPHIN_WEB_API_H
#define MOONSHINE_DOLPHIN_WEB_API_H
#include "dolphin_https.h"
#include "ghost_service.h"
#include "ghost_storage.h"
#define DOLPHIN_WEB_API_BASE (DOLPHIN_HTTPS_IMAGE_BASE+0xC0u)
#define DOLPHIN_WEB_API_MAGIC 0x4D574231u
#define DOLPHIN_WEB_JSON_BASE (DOLPHIN_HTTPS_WORK_BASE+0x8000u)
struct DolphinWebApi {
    unsigned magic,version,apiBytes;
    int (*query)(const struct GhostServiceQuery *,unsigned,char *,unsigned);
    int (*page)(const void *,unsigned,struct GhostServicePage *);
    int (*entryValid)(const struct GhostServiceEntry *);
    int (*routeSort)(const void *,unsigned);
    int (*describe)(const void *,unsigned,unsigned,unsigned,int,struct SusamuneGhostSlotInfo *);
    int (*catalog)(const struct SusamuneGhostSlotInfo *,struct SusamuneGhostSlotInfo *,unsigned,unsigned);
};
#endif
