#ifndef MOONSHINE_NATIVE_STDINT_H
#define MOONSHINE_NATIVE_STDINT_H
typedef signed char int8_t;
typedef unsigned char uint8_t;
typedef short int16_t;
typedef unsigned short uint16_t;
typedef int int32_t;
typedef unsigned int uint32_t;
typedef long long int64_t;
typedef unsigned long long uint64_t;
typedef __UINTPTR_TYPE__ uintptr_t;
typedef __INTPTR_TYPE__ intptr_t;
#define UINT32_MAX 0xffffffffu
#define UINT64_MAX 0xffffffffffffffffull
#define UINT32_C(x) x##u
#define UINT64_C(x) x##ull
#endif
