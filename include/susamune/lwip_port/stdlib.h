#ifndef MOONSHINE_LWIP_STDLIB_H
#define MOONSHINE_LWIP_STDLIB_H
#ifdef MOONSHINE_LWIP_HOST_TEST
#include_next <stdlib.h>
#else
#include <Dolphin/types.h>
#ifdef __cplusplus
extern "C" {
#endif
int atoi(const char *);
#ifdef __cplusplus
}
#endif
#endif
#endif
