#ifndef MOONSHINE_LWIP_CC_H
#define MOONSHINE_LWIP_CC_H
#ifdef MOONSHINE_LWIP_HOST_TEST
#include <stddef.h>
#define SSIZE_MAX 0x7fffffffffffffffLL
#else
#include <Dolphin/types.h>
#endif
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define BYTE_ORDER LITTLE_ENDIAN
#else
#define BYTE_ORDER BIG_ENDIAN
#endif
#define LWIP_NO_STDDEF_H 1
#define INT_MAX 2147483647
#define LWIP_NO_STDINT_H 1
#define LWIP_NO_INTTYPES_H 1
#define LWIP_NO_LIMITS_H 1
#define LWIP_NO_CTYPE_H 1
typedef unsigned char u8_t;
typedef signed char s8_t;
typedef unsigned short u16_t;
typedef short s16_t;
typedef unsigned int u32_t;
typedef int s32_t;
typedef unsigned long long u64_t;
typedef long long s64_t;
typedef __UINTPTR_TYPE__ mem_ptr_t;
#define U8_F "u"
#define S8_F "d"
#define X8_F "x"
#define U16_F "u"
#define S16_F "d"
#define X16_F "x"
#define U32_F "u"
#define S32_F "d"
#define X32_F "x"
#define SZT_F "u"
#define LWIP_PLATFORM_DIAG(x) ((void)0)
#define LWIP_PLATFORM_ASSERT(x) ((void)0)
#ifdef __cplusplus
extern "C" {
#endif
unsigned moonshine_tcp_random(void);
#ifdef __cplusplus
}
#endif
#define LWIP_RAND() moonshine_tcp_random()
#endif
