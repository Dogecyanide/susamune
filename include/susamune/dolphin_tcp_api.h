#ifndef MOONSHINE_DOLPHIN_TCP_API_H
#define MOONSHINE_DOLPHIN_TCP_API_H
#include "dolphin_https.h"
#define DOLPHIN_TCP_API_MAGIC 0x4d545031u
#define DOLPHIN_TCP_API_BASE (DOLPHIN_HTTPS_IMAGE_BASE+0x80u)
#define DOLPHIN_NATIVE_BSS_BASE 0x71BF3000u
#define DOLPHIN_NATIVE_BSS_END 0x71C00000u
#if DOLPHIN_NATIVE_BSS_END != SUSAMUNE_JP_UI_DOLPHIN_BASE || DOLPHIN_NATIVE_BSS_BASE < DOLPHIN_HTTPS_CONTROL_BASE+0x1000u
#error Native globals overlap another Dolphin owner
#endif
struct DolphinTcpIo {
    int (*sendIp)(const void *,unsigned,unsigned);
    unsigned (*ticks)(void);
};
struct DolphinTcpApi {
    unsigned magic,version,apiBytes;
    void (*initialize)(const struct DolphinTcpIo *);
    void (*configure)(unsigned,unsigned,unsigned);
    void (*tick)(unsigned);
    void (*receive)(const unsigned char *,unsigned);
    int (*connect)(unsigned,unsigned short);
    int (*send)(const void *,unsigned);
    int (*read)(void *,unsigned);
    int (*state)(void);
    int (*error)(void);
    void (*close)(void);
    unsigned char *(*dnsBuffer)(void);
};
#ifdef __cplusplus
extern "C" {
#endif
extern const struct DolphinTcpApi dolphin_tcp_api;
#ifdef __cplusplus
}
#endif
#endif
