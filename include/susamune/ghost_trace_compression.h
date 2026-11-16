#ifndef MOONSHINE_GHOST_TRACE_COMPRESSION_H
#define MOONSHINE_GHOST_TRACE_COMPRESSION_H
#include "ghost_trace.h"
#define MS_TRACE_FILE_VERSION 3u
#define MS_TRACE_PACK_BLOCK 0x4000u
#define MS_TRACE_PACK_BOUND (MS_TRACE_PACK_BLOCK+MS_TRACE_PACK_BLOCK/255u+16u)
#define MS_TRACE_PACK_WORK_PHYS ((SUSAMUNE_TRACE_MENU_CODE_CONSOLE_PPC_BASE&0x7fffffffu)+SUSAMUNE_TRACE_MENU_CODE_SIZE)
#define MS_TRACE_PACK_WORK_BYTES 0xc000u
#define MS_TRACE_PACK_OUTPUT_OFFSET 0x5000u
#if MS_TRACE_PACK_WORK_PHYS+MS_TRACE_PACK_WORK_BYTES > (MOONSHINE_GHOST_UPPER_PHYS_BASE+MS_TRACE_BUFFER1_OFFSET)
#error Compression workspace overlaps the second producer buffer
#endif
#if MS_TRACE_PACK_OUTPUT_OFFSET+MS_TRACE_PACK_BOUND > MS_TRACE_PACK_WORK_BYTES
#error Compression output exceeds its private workspace
#endif
int MsTraceCompress(void *state,const unsigned char *source,unsigned bytes,unsigned char *output);
#endif
