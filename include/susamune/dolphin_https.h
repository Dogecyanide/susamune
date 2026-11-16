#ifndef SUSAMUNE_DOLPHIN_HTTPS_H
#define SUSAMUNE_DOLPHIN_HTTPS_H
#include "japanese_ui.h"
#define DOLPHIN_HTTPS_MAGIC 0x4d485431u
#define DOLPHIN_HTTPS_VERSION 2u
#define DOLPHIN_HTTPS_IMAGE_BASE 0x71B20000u
#define DOLPHIN_HTTPS_IMAGE_CAPACITY 0x000C0000u
#define DOLPHIN_LIBRARY_WORK_BASE 0x71BE0000u
#define DOLPHIN_LIBRARY_WORK_SIZE 0x00010000u
#define DOLPHIN_FILES_WORK_BASE 0x71BF0000u
#define DOLPHIN_ENTROPY_WORK_BASE 0x71BF1000u
#define DOLPHIN_HTTPS_CONTROL_BASE 0x71BF2000u
#define DOLPHIN_HTTPS_WORK_BASE 0x71B10000u
#define DOLPHIN_HTTPS_WORK_CAPACITY 0x00010000u
#if DOLPHIN_HTTPS_WORK_BASE != SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE + SUSAMUNE_STATE_POOL_EXTRA_SIZE || DOLPHIN_HTTPS_WORK_BASE + DOLPHIN_HTTPS_WORK_CAPACITY != DOLPHIN_HTTPS_IMAGE_BASE || DOLPHIN_HTTPS_IMAGE_BASE + DOLPHIN_HTTPS_IMAGE_CAPACITY != DOLPHIN_LIBRARY_WORK_BASE || DOLPHIN_LIBRARY_WORK_BASE + DOLPHIN_LIBRARY_WORK_SIZE != DOLPHIN_FILES_WORK_BASE || DOLPHIN_HTTPS_CONTROL_BASE + 0x1000u > SUSAMUNE_JP_UI_DOLPHIN_BASE
#error Native HTTPS overlaps an existing Dolphin owner
#endif
struct DolphinHttpsRequest { const char *method,*headers;const void *body;unsigned bytes; };
struct DolphinHttpsIo {
    void *context;
    int (*send)(void *,const void *,unsigned);
    int (*recv)(void *,void *,unsigned);
};
struct DolphinHttpsInfo { unsigned used,httpStatus,tlsError,reusable,complete; };
struct DolphinHttpsApi {
    unsigned magic,version,apiBytes,workBytes;
    int (*initialize)(void *,unsigned,const unsigned char *);
    int (*start)(void *,const char *,const struct DolphinHttpsRequest *,void *,unsigned);
    int (*step)(void *,const struct DolphinHttpsIo *);
    void (*info)(const void *,struct DolphinHttpsInfo *);
    void (*derive)(const void *,void *,void *);
    void (*sha256)(const void *,unsigned,void *);
};
#endif
