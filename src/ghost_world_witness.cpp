#include "susamune/ghost_world_witness.h"
#if defined(__powerpc__)
#include "SMS/Enemy/Conductor.hxx"
static_assert(__builtin_offsetof(TConductor,_10)==0x10&&__builtin_offsetof(TConductor,_20)==0x20&&
    __builtin_offsetof(TConductor,_30)==0x30&&sizeof(JGadget::TList<TLiveActor*>)==16,"conductor roster layout");
static_assert(__builtin_offsetof(TLiveManager,mMaxObjs)==0x10&&__builtin_offsetof(TLiveManager,mObjCount)==0x14&&
    __builtin_offsetof(TLiveManager,mObjAry)==0x18,"live manager array layout");
static_assert(__builtin_offsetof(TLiveActor,mKeyCode)==8&&__builtin_offsetof(TLiveActor,mTranslation)==0x10&&
    __builtin_offsetof(TLiveActor,mScale)==0x24&&__builtin_offsetof(TLiveActor,mRotation)==0x30&&
    __builtin_offsetof(TLiveActor,mObjectID)==0x4c&&__builtin_offsetof(TLiveActor,mObjectType)==0x64&&
    __builtin_offsetof(TLiveActor,mPositionalVelocity)==0x94&&__builtin_offsetof(TLiveActor,mRotationalVelocity)==0xa0&&
    __builtin_offsetof(TLiveActor,mSpeed)==0xac&&__builtin_offsetof(TLiveActor,mStateFlags)==0xf0,"audited live actor fields");
#endif
namespace GhostWorldWitness {
namespace {
unsigned word(const unsigned char *p) { return unsigned(p[0])<<24|unsigned(p[1])<<16|unsigned(p[2])<<8|p[3]; }
void put(unsigned char *p,unsigned value) { p[0]=value>>24;p[1]=value>>16;p[2]=value>>8;p[3]=value; }
unsigned hashWord(unsigned hash,unsigned value) {
    for(unsigned shift=24;;shift-=8){hash=(hash^((value>>shift)&255u))*16777619u;if(!shift)return hash;}
}
bool fail(Hash &h,Status status) { if(!h.status)h.status=status;return false; }
bool address(unsigned p,unsigned bytes) { return !(p&3u)&&p>=0x80003100u&&bytes<=0x1800000u&&p<=0x81800000u-bytes; }
bool read(const Memory &m,unsigned p,void *out,unsigned bytes) { return address(p,bytes)&&m.read(m.context,p,out,bytes); }
bool actor(const Memory &m,Hash &h,unsigned p) {
    // Identity is used for dedup only; duplicate manager registrations hash once.
    if(!address(p,0xf4))return fail(h,BAD_SOURCE);
    unsigned slot=(p>>4)&(h.slots-1);
    for(unsigned i=0;i<h.slots;++i,slot=(slot+1)&(h.slots-1)) {
        if(h.seen[slot]==p){if(++h.references>kMaxReferences)return fail(h,CAPACITY);return true;}
        if(!h.seen[slot])break;
    }
    unsigned char raw[0xf4];Actor a;
    if(!read(m,p,raw,sizeof(raw)))return fail(h,BAD_SOURCE);
    a.nameKey=unsigned(raw[8])<<8|raw[9];a.type=word(raw+0x4c);
    static const unsigned char offsets[]={0x10,0x30,0x24,0x94,0xa0,0xac};
    for(unsigned group=0;group<6;++group)for(unsigned axis=0;axis<3;++axis)
        a.scalar[group*3+axis]=word(raw+offsets[group]+axis*4);
    a.hitFlags=word(raw+0x64);a.liveFlags=word(raw+0xf0);
    return add(h,p,a);
}
bool list(const Memory &m,Hash &h,unsigned p,bool managers,unsigned &managerCount) {
    unsigned char bytes[16];
    if(!read(m,p,bytes,16))return fail(h,BAD_SOURCE);
    const unsigned count=word(bytes+4),end=p+8,last=word(bytes+12);
    unsigned node=word(bytes+8),previous=end;
    if(count>(managers?kMaxManagers:kMaxActors))return fail(h,CAPACITY);
    for(unsigned i=0;i<count;++i) {
        if(node==end||!read(m,node,bytes,12))return fail(h,BAD_ROSTER);
        const unsigned next=word(bytes),back=word(bytes+4),item=word(bytes+8);
        if(back!=previous)return fail(h,BAD_ROSTER);
        if(managers) {
            if(++managerCount>kMaxManagers)return fail(h,CAPACITY);
            if(!address(item,0x38)||!read(m,item+0x10,bytes,12))return fail(h,BAD_SOURCE);
            const unsigned capacity=word(bytes),actors=word(bytes+4),array=word(bytes+8);
            if(actors>capacity||capacity>2048)return fail(h,BAD_ROSTER);
            if(actors&&!address(array,actors*4))return fail(h,BAD_SOURCE);
            for(unsigned n=0;n<actors;++n) {
                if(!read(m,array+n*4,bytes,4))return fail(h,BAD_SOURCE);
                if(!actor(m,h,word(bytes)))return false;
            }
        } else if(!actor(m,h,item))return false;
        previous=node;node=next;
    }
    return (node==end&&previous==last)||fail(h,BAD_ROSTER);
}
}
bool begin(Hash &h,unsigned *scratch,unsigned slots) {
    h={};h.seen=scratch;h.slots=slots;
    const auto p=reinterpret_cast<__UINTPTR_TYPE__>(scratch),q=reinterpret_cast<__UINTPTR_TYPE__>(&h);
    if(!scratch||!slots||slots>4096||(slots&(slots-1))||(p&3u)||p+slots*4u<p||
       (p<q+sizeof(h)&&q<p+slots*4u))return fail(h,ARGUMENT);
    for(unsigned i=0;i<slots;++i)scratch[i]=0;
    h.value=hashWord(hashWord(2166136261u,0x57574e31u),kScope);return true;
}
bool add(Hash &h,unsigned identity,const Actor &a) {
    if(h.status)return false;
    if(!address(identity,0xf4)||a.nameKey>0xffffu)return fail(h,ARGUMENT);
    if(++h.references>kMaxReferences)return fail(h,CAPACITY);
    unsigned slot=(identity>>4)&(h.slots-1);
    for(unsigned i=0;i<h.slots;++i,slot=(slot+1)&(h.slots-1)) {
        if(h.seen[slot]==identity)return true;
        if(!h.seen[slot]) {
            if(h.count==kMaxActors)return fail(h,CAPACITY);
            for(unsigned n=0;n<18;++n)if((a.scalar[n]&0x7f800000u)==0x7f800000u)return fail(h,NONFINITE);
            h.seen[slot]=identity;h.value=hashWord(h.value,++h.count);
            h.value=hashWord(hashWord(h.value,a.nameKey),a.type);
            for(unsigned n=0;n<18;++n)h.value=hashWord(h.value,(a.scalar[n]&0x7fffffffu)?a.scalar[n]:0);
            h.value=hashWord(hashWord(h.value,a.hitFlags),a.liveFlags);return true;
        }
    }
    return fail(h,CAPACITY);
}
Record finish(const Hash &h) { return {kScope,h.status,h.status?0u:h.count,h.status?0u:hashWord(h.value,h.count)}; }
Record capture(const Memory &m,unsigned conductor,unsigned *scratch,unsigned slots) {
    Hash h;if(!begin(h,scratch,slots))return finish(h);
    if(!m.read||!address(conductor,0x40)){fail(h,BAD_SOURCE);return finish(h);}
    unsigned managers=0;
    if(list(m,h,conductor+0x20,true,managers)&&list(m,h,conductor+0x10,true,managers))
        list(m,h,conductor+0x30,false,managers);
    return finish(h);
}
namespace {
struct Snapshot {Memory memory;unsigned char *rows;unsigned capacity,count;};
bool snapshotRead(void *raw,unsigned address,void *out,unsigned bytes) {
    Snapshot &s=*static_cast<Snapshot*>(raw);
    if(!s.memory.read(s.memory.context,address,out,bytes))return false;
    if(bytes==0xf4) {
        if(s.count==s.capacity)return false;
        unsigned char *row=s.rows+s.count*256;
        put(row,address);put(row+4,s.count);__builtin_memcpy(row+8,out,0xf4);put(row+252,0);++s.count;
    }
    return true;
}
}
Record captureSnapshot(const Memory &memory,unsigned conductor,unsigned *scratch,unsigned slots,
                       unsigned char *rows,unsigned capacity,unsigned &count) {
    count=0;
    if(!memory.read||!rows||!capacity||capacity>kMaxActors)return {kScope,ARGUMENT,0,0};
    Snapshot snapshot={memory,rows,capacity,0};
    const Record result=capture({&snapshot,snapshotRead},conductor,scratch,slots);
    count=snapshot.count;return result;
}
void encode(unsigned char (&wire)[kWireBytes],const Record &r) {
    put(wire,kSchema);put(wire+4,r.scope);put(wire+8,r.status);put(wire+12,r.count);put(wire+16,r.hash);
}
bool decode(const void *data,unsigned bytes,Record &out) {
    if(!data||bytes!=kWireBytes)return false;
    const auto *p=static_cast<const unsigned char*>(data);
    const Record r={word(p+4),word(p+8),word(p+12),word(p+16)};
    if(word(p)!=kSchema||r.scope!=kScope||r.status>ARGUMENT||r.count>kMaxActors||
       (r.status&&(r.count||r.hash)))return false;
    out=r;return true;
}
bool matches(const Record &a,const Record &b) {
    return a.status==COMPLETE&&b.status==COMPLETE&&a.scope==kScope&&b.scope==a.scope&&a.count==b.count&&a.hash==b.hash;
}
#if defined(__powerpc__)
namespace {
bool nativeRead(void *,unsigned p,void *out,unsigned bytes) {
    __builtin_memcpy(out,reinterpret_cast<const void*>(p),bytes);return true;
}
}
Record captureNative(unsigned conductor,unsigned *scratch,unsigned slots) {
    return capture({nullptr,nativeRead},conductor,scratch,slots);
}
Record snapshotNative(unsigned conductor,unsigned *scratch,unsigned slots,unsigned char *rows,unsigned capacity,unsigned &count) {
    return captureSnapshot({nullptr,nativeRead},conductor,scratch,slots,rows,capacity,count);
}
#endif
}
