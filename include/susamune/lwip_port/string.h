#ifndef MOONSHINE_LWIP_STRING_H
#define MOONSHINE_LWIP_STRING_H
#ifdef MOONSHINE_LWIP_HOST_TEST
#include_next <string.h>
#else
#include <Dolphin/string.h>
#include <Dolphin/mem.h>
#ifdef __cplusplus
extern "C" {
#endif
int strncmp(const char *, const char *, size_t);
#ifdef __cplusplus
}
#endif
#endif
#endif
