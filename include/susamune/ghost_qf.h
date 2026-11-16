#ifndef MOONSHINE_GHOST_QF_H
#define MOONSHINE_GHOST_QF_H
#define GHOST_QF_MAGIC 0x53475146u
#define GHOST_QF_VERSION 1u
#define GHOST_QF_HEADER_BYTES 32u
#define GHOST_QF_TICK_BYTES 13u
#define GHOST_QF_FRAME_BYTES 6u
#define GHOST_QF_FRAME_TICKS_MAX 256u
#define GHOST_QF_FRAMES_MAX 36000u
#define GHOST_QF_TICKS_MAX 71929u
#define GHOST_QF_PAYLOAD_MAX (GHOST_QF_FRAMES_MAX*GHOST_QF_FRAME_BYTES+GHOST_QF_TICKS_MAX*GHOST_QF_TICK_BYTES)
#define GHOST_QF_CHUNK_MAX (GHOST_QF_HEADER_BYTES+GHOST_QF_PAYLOAD_MAX)
#define GHOST_QF_TRUNCATED 1u
#define GHOST_QF_MISSING 2u
#define GHOST_QF_FRAME_DELTA 0x8000u
#define GHOST_QF_FRAME_MISSING 0x4000u
#define GHOST_QF_FRAME_COUNT_MASK 0x01ffu
struct GhostQfView { const unsigned char *part[3]; unsigned int bytes[3],count; };
struct GhostQfBuffer { unsigned char *part[2]; unsigned int bytes[2]; };
static inline unsigned int GhostQfRead16(const unsigned char *p) { return ((unsigned int)p[0]<<8)|p[1]; }
static inline unsigned int GhostQfRead32(const unsigned char *p) { return (GhostQfRead16(p)<<16)|GhostQfRead16(p+2); }
static inline void GhostQfPut16(unsigned char *p,unsigned int n) { p[0]=n>>8;p[1]=n; }
static inline void GhostQfPut32(unsigned char *p,unsigned int n) { GhostQfPut16(p,n>>16);GhostQfPut16(p+2,n); }
static inline unsigned int GhostQfViewBytes(const struct GhostQfView *v) {
    unsigned int i,total=0;
    if(!v || !v->count || v->count>3)return 0;
    for(i=0;i<v->count;++i){if((v->bytes[i]&&!v->part[i])||v->bytes[i]>GHOST_QF_CHUNK_MAX-total)return 0;total+=v->bytes[i];}
    return total;
}
static inline int GhostQfRead(const struct GhostQfView *v,unsigned int offset,void *out,unsigned int bytes) {
    unsigned int i,n,j,total=GhostQfViewBytes(v);unsigned char *d=(unsigned char*)out;
    if(!out || offset>total || bytes>total-offset)return 0;
    for(i=0;i<v->count && bytes;++i){
        if(offset>=v->bytes[i]){offset-=v->bytes[i];continue;}
        n=v->bytes[i]-offset;if(n>bytes)n=bytes;
        for(j=0;j<n;++j)d[j]=v->part[i][offset+j];d+=n;bytes-=n;offset=0;
    }
    return !bytes;
}
static inline unsigned int GhostQfBufferBytes(const struct GhostQfBuffer *b) {
    if(!b || (b->bytes[0]&&!b->part[0]) || (b->bytes[1]&&!b->part[1]) ||
        b->bytes[0]>GHOST_QF_CHUNK_MAX || b->bytes[1]>GHOST_QF_CHUNK_MAX-b->bytes[0])return 0;
    return b->bytes[0]+b->bytes[1];
}
static inline void GhostQfWriteByte(const struct GhostQfBuffer *b,unsigned int offset,unsigned char value) {
    if(offset<b->bytes[0])b->part[0][offset]=value;else b->part[1][offset-b->bytes[0]]=value;
}
static inline int GhostQfTickValid(const unsigned char *p) {
    unsigned int mode=p[12]&127u;
    return !(p[0]&0xe0u) && !(p[1]&0x80u) &&
        (mode<=0x49u || (mode==127u && !p[10] && !p[11]));
}
// Every frame starts from its SGTI sample, so trimming never needs earlier frames.
static inline void GhostQfPredictor(unsigned char out[13],const unsigned char frame[24]) {
    unsigned int i;for(i=0;i<10;++i)out[i]=frame[4+i];out[10]=frame[2];out[11]=frame[3];out[12]=frame[15]&127u;
}
static inline int GhostQfOverlap(const void *a,unsigned int an,const void *b,unsigned int bn) {
    const __UINTPTR_TYPE__ x=(__UINTPTR_TYPE__)a,y=(__UINTPTR_TYPE__)b;
    return an && bn && (x>~(__UINTPTR_TYPE__)0-an || y>~(__UINTPTR_TYPE__)0-bn || (x<y+bn && y<x+an));
}
static inline int GhostQfEncodeFrame(const struct GhostQfBuffer *out,unsigned int offset,
        unsigned int serial,const unsigned char *ticks,unsigned int count,
        const unsigned char predictor[13],unsigned int flags,unsigned int *written) {
    unsigned char previous[13],head[6];unsigned int i,j,delta=0,raw,countFlags,pos,mask,total=GhostQfBufferBytes(out);
    if(written)*written=0;
    if(!written || !predictor || !GhostQfTickValid(predictor) || count>GHOST_QF_FRAME_TICKS_MAX ||
        (count&&!ticks) || (flags&~GHOST_QF_FRAME_MISSING) || ((flags&GHOST_QF_FRAME_MISSING)&&count))return 0;
    raw=count*13u;
    for(i=0;i<2;++i)if(GhostQfOverlap(out->part[i],out->bytes[i],ticks,raw)||GhostQfOverlap(out->part[i],out->bytes[i],predictor,13))return 0;
    for(j=0;j<13;++j)previous[j]=predictor[j];
    for(i=0;i<count;++i){
        const unsigned char *tick=ticks+i*13u;if(!GhostQfTickValid(tick))return 0;
        delta+=2;for(j=0;j<13;++j){delta+=tick[j]!=previous[j];previous[j]=tick[j];}
    }
    countFlags=count|flags;if(delta<raw)countFlags|=GHOST_QF_FRAME_DELTA;
    total=GhostQfBufferBytes(out);raw=6u+(delta<raw?delta:raw);
    if(offset>total || raw>total-offset)return 0;
    GhostQfPut32(head,serial);GhostQfPut16(head+4,countFlags);
    for(i=0;i<6;++i)GhostQfWriteByte(out,offset+i,head[i]);pos=offset+6;
    for(j=0;j<13;++j)previous[j]=predictor[j];
    for(i=0;i<count;++i){
        const unsigned char *tick=ticks+i*13u;
        if(countFlags&GHOST_QF_FRAME_DELTA){
            mask=0;for(j=0;j<13;++j)if(tick[j]!=previous[j])mask|=1u<<j;
            GhostQfWriteByte(out,pos++,mask>>8);GhostQfWriteByte(out,pos++,mask);
            for(j=0;j<13;++j)if(mask&(1u<<j))GhostQfWriteByte(out,pos++,tick[j]);
        }else for(j=0;j<13;++j)GhostQfWriteByte(out,pos++,tick[j]);
        for(j=0;j<13;++j)previous[j]=tick[j];
    }
    *written=pos-offset;return 1;
}
static inline int GhostQfDecodeFrame(const struct GhostQfView *view,unsigned int offset,
        const unsigned char predictor[13],unsigned char *ticks,unsigned int capacity,
        unsigned int *consumed,unsigned int *countOut,unsigned int *serialOut,unsigned int *flagsOut) {
    unsigned char head[6],previous[13],maskBytes[2];unsigned int i,j,count,flags,pos,mask;
    if(consumed)*consumed=0;
    if(!consumed||!countOut||!predictor||!GhostQfTickValid(predictor)||!GhostQfRead(view,offset,head,6))return 0;
    flags=GhostQfRead16(head+4);count=flags&GHOST_QF_FRAME_COUNT_MASK;
    if((flags&~(GHOST_QF_FRAME_COUNT_MASK|GHOST_QF_FRAME_DELTA|GHOST_QF_FRAME_MISSING)) ||
        count>GHOST_QF_FRAME_TICKS_MAX || ((flags&GHOST_QF_FRAME_MISSING)&&count) ||
        ((flags&GHOST_QF_FRAME_DELTA)&&!count) || (ticks&&capacity<count*13u))return 0;
    pos=offset+6;for(j=0;j<13;++j)previous[j]=predictor[j];
    for(i=0;i<count;++i){
        if(flags&GHOST_QF_FRAME_DELTA){
            if(!GhostQfRead(view,pos,maskBytes,2))return 0;pos+=2;mask=GhostQfRead16(maskBytes);
            if(mask&~0x1fffu)return 0;
            for(j=0;j<13;++j)if(mask&(1u<<j)){if(!GhostQfRead(view,pos,previous+j,1))return 0;++pos;}
        }else {if(!GhostQfRead(view,pos,previous,13))return 0;pos+=13;}
        if(!GhostQfTickValid(previous))return 0;
        if(ticks)for(j=0;j<13;++j)ticks[i*13u+j]=previous[j];
    }
    if((flags&GHOST_QF_FRAME_DELTA)&&pos-offset-6>=count*13u)return 0;
    *consumed=pos-offset;*countOut=count;if(serialOut)*serialOut=GhostQfRead32(head);
    if(flagsOut)*flagsOut=flags&~GHOST_QF_FRAME_COUNT_MASK;return 1;
}
static inline unsigned int GhostQfCrc(const struct GhostQfView *v,unsigned int offset,unsigned int bytes) {
#if defined(__arm__)
    static const unsigned int table[16] __attribute__((section(".text.ghost_qf_crc"))) = {
#else
    static const unsigned int table[16] = {
#endif
        0,0x1db71064u,0x3b6e20c8u,0x26d930acu,0x76dc4190u,0x6b6b51f4u,0x4db26158u,0x5005713cu,
        0xedb88320u,0xf00f9344u,0xd6d6a3e8u,0xcb61b38cu,0x9b64c2b0u,0x86d3d2d4u,0xa00ae278u,0xbdbdf21cu};
    unsigned int crc=0xffffffffu,i;unsigned char byte;
    if(offset>GhostQfViewBytes(v)||bytes>GhostQfViewBytes(v)-offset)return 0;
    for(i=0;i<bytes;++i){GhostQfRead(v,offset+i,&byte,1);crc^=byte;crc=(crc>>4)^table[crc&15u];crc=(crc>>4)^table[crc&15u];}
    return ~crc;
}
static inline int GhostQfValidate(const struct GhostQfView *view,const unsigned char *frames,
        unsigned int frameBytes,unsigned int inputCount) {
    unsigned char h[32],predictor[13];unsigned int count,ticks,bytes,flags,offset=32,i,seen=0,missing=0;
    if(inputCount>GHOST_QF_FRAMES_MAX || frameBytes<inputCount*24u || (inputCount&&!frames) || !GhostQfRead(view,0,h,32))return 0;
    if(GhostQfRead32(h)!=GHOST_QF_MAGIC || GhostQfRead16(h+4)!=1 || GhostQfRead16(h+6)!=32 ||
        GhostQfRead16(h+28)!=1 || GhostQfRead16(h+30))return 0;
    count=GhostQfRead32(h+8);ticks=GhostQfRead32(h+12);bytes=GhostQfRead32(h+16);flags=GhostQfRead32(h+20);
    if(count>inputCount || (!(flags&GHOST_QF_TRUNCATED)&&count!=inputCount) || ticks>GHOST_QF_TICKS_MAX ||
        (flags&~(GHOST_QF_TRUNCATED|GHOST_QF_MISSING)) || bytes>count*6u+ticks*13u ||
        GhostQfViewBytes(view)!=32u+bytes || GhostQfCrc(view,32,bytes)!=GhostQfRead32(h+24))return 0;
    for(i=0;i<count;++i){
        unsigned int consumed,n,frameFlags;GhostQfPredictor(predictor,frames+i*24u);
        if(!GhostQfDecodeFrame(view,offset,predictor,0,0,&consumed,&n,0,&frameFlags) || n>ticks-seen ||
            (n && frames[i*24u+14]))return 0;
        seen+=n;offset+=consumed;missing|=!!(frameFlags&GHOST_QF_FRAME_MISSING);
    }
    return offset==32u+bytes && seen==ticks && missing==!!(flags&GHOST_QF_MISSING);
}
#endif
