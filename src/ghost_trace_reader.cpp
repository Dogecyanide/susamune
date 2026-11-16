#include "susamune/ghost_trace_reader.hxx"
#include "susamune/ghost_trace_compression.h"
#include "susamune/state_codec.hxx"

namespace GhostTraceReader {
namespace {
enum Phase { FILE_HEADER, FILE_FOOTER, CHUNK_HEADER, BLOCK_HEADER, RAW_BLOCK, PACKED_BLOCK, READY, DONE, BAD };
unsigned word(const unsigned char *p) {
    return unsigned(p[0]) << 24 | unsigned(p[1]) << 16 | unsigned(p[2]) << 8 | p[3];
}
bool fail(Reader &r, Error error) { r.error=error;r.phase=BAD;r.pending=0;return false; }
bool gameId(unsigned game) {
    return game==0x474d534au || game==0x474d5345u || game==0x474d5350u;
}
bool separate(const void *a,unsigned an,const void *b,unsigned bn) {
    const auto x=reinterpret_cast<__UINTPTR_TYPE__>(a),y=reinterpret_cast<__UINTPTR_TYPE__>(b);
    return a && b && x+an>=x && y+bn>=y && (x+an<=y || y+bn<=x);
}
bool validateRecords(Reader &r) {
    unsigned at=0,frame=r.frame,tick=r.tick,first=0;
    while(at<r.chunkBytes) {
        if(r.chunkBytes-at<12)return fail(r,RECORD);
        const unsigned char *p=r.output+at;
        const unsigned kind=unsigned(p[0])<<8|p[1],bytes=unsigned(p[2])<<8|p[3];
        const unsigned nextFrame=word(p+4),nextTick=word(p+8);
        if(!kind || bytes>r.chunkBytes-at-12 || nextFrame<frame || nextTick<tick)
            return fail(r,RECORD);
        if(!at)first=nextFrame;
        frame=nextFrame;tick=nextTick;at+=12+bytes;
    }
    if(first!=r.firstFrame || frame!=r.lastFrame)return fail(r,RECORD);
    r.frame=frame;r.tick=tick;r.phase=READY;return true;
}
bool finishBlock(Reader &r) {
    r.hash=MsTraceHash(r.hash,r.output+r.filled,r.blockRaw);
    r.filled+=r.blockRaw;
    if(r.filled==r.chunkBytes) {
        if(r.hash!=r.expectedHash)return fail(r,CHECKSUM);
        return validateRecords(r);
    }
    r.phase=r.codec?BLOCK_HEADER:RAW_BLOCK;return true;
}
}
bool begin(Reader &r,unsigned fileBytes,void *output,unsigned outputBytes,
           void *packed,unsigned packedBytes) {
    // Invalid or aliased buffers must not let initialization overwrite the reader.
    if(fileBytes<96 || fileBytes>MS_TRACE_FILE_LIMIT || outputBytes<MS_TRACE_BUFFER_BYTES ||
       packedBytes<MS_TRACE_PACK_BLOCK || !separate(&r,sizeof(r),output,outputBytes) ||
       !separate(&r,sizeof(r),packed,packedBytes) || !separate(output,outputBytes,packed,packedBytes))
        return fail(r,ARGUMENT);
    r={};r.fileBytes=fileBytes;r.output=static_cast<unsigned char*>(output);
    r.packed=static_cast<unsigned char*>(packed);r.phase=FILE_HEADER;return true;
}
Status status(const Reader &r) {
    if(r.phase==READY)return CHUNK_READY;
    if(r.phase==DONE)return COMPLETE;
    if(r.phase==BAD)return FAILED;
    return NEED_DATA;
}
bool sameRegion(const Reader &r,unsigned game) { return r.phase!=BAD && gameId(game) && game==r.game; }
bool nextRead(Reader &r,Read &read) {
    if(status(r)!=NEED_DATA || r.pending)return false;
    unsigned bytes=0;void *destination=r.header;
    switch(r.phase) {
    case FILE_HEADER:bytes=64;break;
    case FILE_FOOTER:
    case CHUNK_HEADER:bytes=32;break;
    case BLOCK_HEADER:bytes=8;break;
    case RAW_BLOCK:
        if(!r.codec)r.blockRaw=(r.chunkBytes-r.filled<MS_TRACE_PACK_BLOCK)?r.chunkBytes-r.filled:MS_TRACE_PACK_BLOCK;
        bytes=r.blockRaw;destination=r.output+r.filled;break;
    case PACKED_BLOCK:bytes=r.blockStored;destination=r.packed;break;
    default:return fail(r,ARGUMENT);
    }
    const unsigned end=(r.phase==FILE_HEADER || r.phase==FILE_FOOTER ||
        (r.phase==CHUNK_HEADER && r.offset==r.fileBytes-32))?r.fileBytes:r.fileBytes-32;
    if(!bytes || r.offset>end || bytes>end-r.offset)return fail(r,SHORT_READ);
    r.pending=bytes;read={r.offset,bytes,destination};return true;
}
bool acceptRead(Reader &r,unsigned bytes) {
    if(status(r)!=NEED_DATA || !r.pending || bytes!=r.pending)return fail(r,SHORT_READ);
    const unsigned start=r.offset;r.offset+=bytes;r.pending=0;
    const unsigned char *h=r.header;
    switch(r.phase) {
    case FILE_HEADER:
        if(word(h)!=MS_TRACE_MAGIC || word(h+4)<1 || word(h+4)>MS_TRACE_FILE_VERSION ||
           word(h+8)!=64 || !gameId(word(h+12)) || !word(h+20) || (word(h+28)&0xff000000u) || word(h+32)!=MS_TRACE_BUFFER_BYTES ||
           MsTraceHash(2166136261u,h,60)!=word(h+60))return fail(r,HEADER);
        r.version=word(h+4);r.game=word(h+12);r.run=word(h+20);r.capabilities=word(h+28);
        r.offset=r.fileBytes-32;r.phase=FILE_FOOTER;return true;
    case FILE_FOOTER:
        if(word(h)!=0x444f4e45u || word(h+4)!=r.run || word(h+12)!=r.fileBytes-32 ||
           (word(h+16)&0xffffffu)!=r.capabilities)return fail(r,CHUNK);
        if(word(h+16)>>24)return fail(r,CAPTURE_FAILED);
        r.expectedChunks=word(h+8);
        if(r.expectedChunks>(r.fileBytes-96)/32)return fail(r,CHUNK);
        r.offset=64;r.phase=CHUNK_HEADER;return true;
    case CHUNK_HEADER:
        if(word(h)==0x444f4e45u) {
            if(word(h+4)!=r.run || word(h+8)!=r.chunks || r.chunks!=r.expectedChunks || word(h+12)!=start ||
               r.offset!=r.fileBytes || (word(h+16)&0xffffffu)!=r.capabilities)return fail(r,CHUNK);
            if(word(h+16)>>24)return fail(r,CAPTURE_FAILED);
            r.phase=DONE;return true;
        }
        r.chunkBytes=word(h+8);r.expectedHash=word(h+12);r.firstFrame=word(h+16);r.lastFrame=word(h+20);
        r.codec=word(h+24);r.filled=0;r.hash=2166136261u;
        if(r.chunks>=r.expectedChunks || word(h)!=r.run || word(h+4)!=r.chunks+1 || !r.chunkBytes || r.chunkBytes>MS_TRACE_BUFFER_BYTES ||
           r.firstFrame<r.frame || r.lastFrame<r.firstFrame ||
           (r.codec?(r.version<3 || r.codec!=1 || word(h+28)!=MS_TRACE_PACK_BLOCK):word(h+28)!=0))
            return fail(r,CHUNK);
        ++r.chunks;r.phase=r.codec?BLOCK_HEADER:RAW_BLOCK;return true;
    case BLOCK_HEADER: {
        r.blockRaw=word(h);const unsigned stored=word(h+4);r.blockStored=stored&0x7fffffffu;
        const bool compressed=(stored&0x80000000u)!=0;
        if(!r.blockRaw || r.blockRaw>MS_TRACE_PACK_BLOCK || r.blockRaw>r.chunkBytes-r.filled ||
           !r.blockStored || (compressed?r.blockStored>=r.blockRaw:r.blockStored!=r.blockRaw))
            return fail(r,COMPRESSION);
        r.phase=compressed?PACKED_BLOCK:RAW_BLOCK;return true;
    }
    case PACKED_BLOCK:
        if(!StateCodec::decodeLz4Block(r.packed,r.blockStored,r.output+r.filled,r.blockRaw))
            return fail(r,COMPRESSION);
        return finishBlock(r);
    case RAW_BLOCK:return finishBlock(r);
    default:return fail(r,ARGUMENT);
    }
}
bool releaseChunk(Reader &r) {
    if(r.phase!=READY)return false;
    r.phase=CHUNK_HEADER;return true;
}
bool releaseChunk(Reader &r,void *nextOutput,unsigned outputBytes) {
    if(r.phase!=READY || r.pending || outputBytes<MS_TRACE_BUFFER_BYTES ||
       !separate(&r,sizeof(r),nextOutput,outputBytes) ||
       !separate(r.packed,MS_TRACE_PACK_BLOCK,nextOutput,outputBytes))return false;
    r.output=static_cast<unsigned char*>(nextOutput);r.phase=CHUNK_HEADER;return true;
}
}
