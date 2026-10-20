#include "susamune/state_quick_producer.hxx"
#include "../../src/state_codec.cpp"
#include "../../src/state_crc.cpp"

extern "C" {
void *memcpy(void *d, const void *s, __SIZE_TYPE__ n) {
    unsigned char *a=(unsigned char*)d; const unsigned char *b=(const unsigned char*)s;
    while(n--) *a++=*b++; return d;
}
void *memset(void *d, int v, __SIZE_TYPE__ n) {
    unsigned char *a=(unsigned char*)d; while(n--) *a++=(unsigned char)v; return d;
}
int memcmp(const void *a,const void *b,__SIZE_TYPE__ n) {
    const unsigned char *x=(const unsigned char*)a,*y=(const unsigned char*)b;
    while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;
}
void *memmove(void *d,const void *s,__SIZE_TYPE__ n) {
    unsigned char *a=(unsigned char*)d;const unsigned char *b=(const unsigned char*)s;
    if(a<b){for(__SIZE_TYPE__ i=0;i<n;++i)a[i]=b[i];}else{while(n){--n;a[n]=b[n];}}return d;
}

static TWBankMemory Memory = {{(unsigned char*)0x70010000,(unsigned char*)0x71800000,
    (unsigned char*)0x71100000,(unsigned char*)0x71b00000,0},
    {0xff0000,0x200000,0xc2000,0x13e000,0},4};
static TWStageMemory Stage = {&Memory,(unsigned char*)0x71200000,0x2f0000};
static TWStageToken Token;
struct Identity {unsigned raw,packed,adler,crc,tag;};
static Identity Id[4];
static const unsigned Input = 0x80080000, Work = 0x81600000;
#if TIMEWARP_LARGE_INPUT
static const unsigned Output = 0x815a0000, OutputSize = 0x30000, InputLimit = 0x151ffe0;
#else
static const unsigned Output = 0x80f00000, OutputSize = 0x6f0000, InputLimit = 0xe7ffe0;
#endif
static const unsigned Canary = 0x6e92bc47;
static volatile unsigned *const Box = (volatile unsigned*)0x81700000;
static unsigned ProtectFirst, ProtectLast;

static void setGuards() {
    for(unsigned i=0;i<Memory.count;++i) {
        *(volatile unsigned*)(Memory.banks[i]-4)=Canary;
        *(volatile unsigned*)(Memory.banks[i]+Memory.sizes[i])=Canary;
    }
    *(volatile unsigned*)(Stage.staging-4)=Canary;
    *(volatile unsigned*)(Stage.staging+Stage.size)=Canary;
    *(volatile unsigned*)(Work-4)=Canary;
    *(volatile unsigned*)(Work+0x4e000)=Canary;
    *(volatile unsigned*)(Output+OutputSize)=Canary;
#if TIMEWARP_LARGE_INPUT
    *(volatile unsigned*)(Input-4)=Canary;
    *(volatile unsigned*)(Input+InputLimit)=Canary;
    *(volatile unsigned*)(Output-4)=Canary;
#endif
}
static bool guards() {
#if TIMEWARP_LARGE_INPUT
    if (*(volatile unsigned*)(Input-4)!=Canary ||
        *(volatile unsigned*)(Input+InputLimit)!=Canary ||
        *(volatile unsigned*)(Output-4)!=Canary) return false;
#endif
    for(unsigned i=0;i<Memory.count;++i)
        if(*(volatile unsigned*)(Memory.banks[i]-4)!=Canary ||
           *(volatile unsigned*)(Memory.banks[i]+Memory.sizes[i])!=Canary)return false;
    return *(volatile unsigned*)(Stage.staging-4)==Canary &&
        *(volatile unsigned*)(Stage.staging+Stage.size)==Canary &&
        *(volatile unsigned*)(Work-4)==Canary && *(volatile unsigned*)(Work+0x4e000)==Canary &&
        *(volatile unsigned*)(Output+OutputSize)==Canary;
}
static void copy(void*,void *d,const void *s,unsigned n) {
    unsigned char *a=(unsigned char*)d;const unsigned char *b=(const unsigned char*)s;
    for(unsigned i=0;i<n;++i)if((unsigned)(a+i)<ProtectFirst || (unsigned)(a+i)>=ProtectLast)a[i]=b[i];
}
static bool direct(void*,void*d,unsigned n) {
    unsigned a=(unsigned)d;return a+n<=ProtectFirst || a>=ProtectLast;
}
static bool reset() {
    memset(Id,0,sizeof(Id)); Token={};setGuards();
    return TWChunkInit(&Memory) && TWSAttach(&Stage,73);
}
static unsigned run(unsigned command,unsigned slot,unsigned size,unsigned tag) {
    TWChunkPool *pool=TWChunkDirectory(&Memory);
    if(command==1)return reset()?0:90;
    if(slot>3)return 91;
    if(command==2) {
        if(slot==3)return 91;
        return TWRBegin(&Stage,slot,TWSControl(&Stage)->generations[slot],pool->slots[slot].metadataTag,&Token)?0:92;
    }
    if(command==3) {
        if(!size || size>InputLimit)return 93;
        StateCodec::ReadSpan source={(void*)Input,size};
        StateCodec::Result r=TWQuickProduce(&Stage,Token,(void*)Work,0x4e000,&source,1);
        Box[5]=r.compressedBytes;Box[6]=r.rawBytes;Box[7]=r.adler32;
        Id[3]={r.rawBytes,r.compressedBytes,r.adler32,0,tag};
        if(r.status==StateCodec::SUCCESS)Id[3].crc=TWSChecksum(&Stage,&pool->slots[3]);
        Box[8]=Id[3].crc;
        return r.status;
    }
    if(command==4) {
        Identity id=Id[3];
        if(!TWRCommit(&Stage,Token,id.raw,id.packed,id.crc,id.tag))return 94;
        Id[Token.slot]=id;return 0;
    }
    if(command==5)return TWRAbort(&Stage,Token)?0:95;
    if(command==6) {
        if(!TWSValid(&Stage) || !pool->slots[slot].count || size>=Id[slot].packed)return 96;
        const unsigned char frame[]={0x4d,0x53,0x4c,0x34,0,2,0,0};
        unsigned char *next=(unsigned char*)Output;
        unsigned offset=0,left=OutputSize;
        const TWChunkSlot *root=&pool->slots[slot];
        for(unsigned i=0;i<=root->count && left;++i) {
            const TWChunk *chunk=i?&pool->chunks[root->ids[i-1]-1]:0;
            const unsigned char *bytes=i?TWSData(&Stage,chunk):frame;
            unsigned length=i?chunk->size:8;
            if(!bytes)return 97;
            if(offset+length>size) {
                unsigned skip=size>offset?size-offset:0;
                unsigned copied=length-skip<left?length-skip:left;
                memcpy(next,bytes+skip,copied);next+=copied;left-=copied;
            }
            offset+=length;
        }
        Box[5]=next-(unsigned char*)Output;Box[6]=Id[slot].packed;
        return Box[5] && Box[5]<=Id[slot].packed-size?0:98;
    }
    if(command==7) {
        Identity id=Id[slot];if(!id.raw || id.raw>InputLimit)return 99;
        unsigned generation=slot==3?Token.generation+1:TWSControl(&Stage)->generations[slot];
        unsigned borrow=TWRBuild(&Stage,slot,generation,id.tag,id.raw,id.packed,id.adler,id.crc,Token,0,0);
        if(!borrow)return 100;
        unsigned count=TWRControl(&Stage)->spanCount;
        const StateCodec::ReadSpan *input=TWRTable(&Stage,0,0);
        StateCodec::WriteSpan output={(void*)Input,id.raw};
        memset((void*)Input,0xa7,id.raw);
        ProtectFirst=tag?Input+0x4000d:0;ProtectLast=tag?ProtectFirst+31:0;
        unsigned status=StateCodec::validateRestore((void*)Work,0x4e000,input,count,&output,1,id.raw,id.adler);
        if(!status && !TWRCheck(&Stage,borrow,id.adler,0,0))status=101;
        if(!status)status=StateCodec::decompressVerified((void*)Work,0x4e000,input,count,&output,1,id.raw,id.adler,copy,0,direct);
        if(!TWRRelease(&Stage,borrow))return 102;
        return status;
    }
    return 103;
}
void bench() {
    for(unsigned i=0;i<32;++i)Box[i]=0;
    Box[4]=reset()?0:90;Box[11]=3;Box[0]=0x54575042;
    unsigned seen=0;
    for(;;) {
        unsigned sequence=Box[1];if(sequence==seen)continue;seen=sequence;
        unsigned command=Box[2],slot=Box[12],size=Box[13],tag=Box[14];
        Box[4]=run(command,slot,size,tag);
        Box[9]=guards();Box[10]=TWChunkDirectory(&Memory)->highWater;
        Box[15]=TWChunkDirectory(&Memory)->slots[3].count;
        Box[16]=TWSControl(&Stage)->stagePeak;Box[17]=TWSControl(&Stage)->copiedBytes;
        for(unsigned i=0;i<3;++i)Box[18+i]=TWSControl(&Stage)->generations[i];
        unsigned live=0,aligned=0;
        for(unsigned i=0;i<TW_CHUNK_DESCRIPTORS;++i) {
            const TWChunk *c=&TWChunkDirectory(&Memory)->chunks[i];
            if(c->refs){++live;aligned+=TWChunkAlign(c->size);}
        }
        Box[21]=live;Box[22]=aligned;
        asm volatile("sync" ::: "memory");Box[3]=sequence;
    }
}
}
asm(".section .text.start,\"ax\"\n.globl _start\n_start:\n"
    "lis 1,0x815f\nori 1,1,0xf000\nli 0,0\nstw 0,0(1)\n"
    "mfmsr 3\nrlwinm 3,3,0,17,15\nmtmsr 3\nisync\nbl bench\nb .\n");
