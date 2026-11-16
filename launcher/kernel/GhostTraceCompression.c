#if MOONSHINE_GHOST_TRACE
#include <string.h>
#include <stdint.h>
#include <limits.h>
#define LZ4_FREESTANDING 1
#define LZ4_MEMORY_USAGE 14
#define LZ4_FORCE_MEMORY_ACCESS 0
#define LZ4LIB_VISIBILITY static __attribute__((unused))
#define LZ4_memcpy __builtin_memcpy
#define LZ4_memset __builtin_memset
#define LZ4_memmove memmove
#include "../../vendor/lz4/lz4.c"
#include "susamune/ghost_trace_compression.h"
typedef char TraceLz4StateFits[sizeof(LZ4_stream_t)<=MS_TRACE_PACK_OUTPUT_OFFSET?1:-1];
int MsTraceCompress(void *state,const unsigned char *source,unsigned bytes,unsigned char *output) {
    LZ4_stream_t *stream;
    if(!bytes||bytes>MS_TRACE_PACK_BLOCK)return 0;
    stream=LZ4_initStream(state,MS_TRACE_PACK_OUTPUT_OFFSET);
    if(!stream)return 0;
    return LZ4_compress_generic(&stream->internal_donotuse,(const char*)source,
        (char*)output,bytes,NULL,0,notLimited,byU16,noDict,noDictIssue,1);
}
#endif
