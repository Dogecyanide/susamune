#ifndef MOONSHINE_LWIP_STDIO_H
#define MOONSHINE_LWIP_STDIO_H
#ifdef MOONSHINE_LWIP_HOST_TEST
#include_next <stdio.h>
#else
#include <Dolphin/types.h>
#ifdef __cplusplus
extern "C" {
#endif
int snprintf(char *, size_t, const char *, ...);
#ifdef __cplusplus
}
#endif
#endif
#endif
