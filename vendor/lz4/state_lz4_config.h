#pragma once

#define LZ4_FREESTANDING 1
#define LZ4_MEMORY_USAGE 15
#define LZ4_FORCE_MEMORY_ACCESS 0
#define LZ4LIB_VISIBILITY static __attribute__((unused))
#define LZ4_memcpy __builtin_memcpy
#define LZ4_memset __builtin_memset
#define LZ4_memmove memmove
extern "C" void *memmove(void *, const void *, __SIZE_TYPE__);

// The bundled freestanding compiler has no C library headers.
typedef __UINTPTR_TYPE__ uintptr_t;
typedef unsigned char uint8_t;
typedef signed char int8_t;
typedef int int32_t;
#define UINT_MAX 4294967295U
#define INT_MAX 2147483647
#undef _MSC_VER
