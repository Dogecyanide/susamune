#include "susamune/ghost_arena.hxx"

namespace GhostArena {
bool configure(Arena &a,const Span *spans,unsigned count) {
    if(!spans || !count || count>kBanks)return false;
    if(configured(a))for(unsigned i=0;i<kLeases;++i)if(a.entry[i].owner)return false;
    Span copy[kBanks];unsigned total=0;
    for(unsigned i=0;i<count;++i) {
        copy[i]=spans[i];const Address p=reinterpret_cast<Address>(copy[i].data);
        if(!validSpan(copy[i]) || total>~0u-copy[i].bytes ||
           overlaps(p,copy[i].bytes,reinterpret_cast<Address>(&a),sizeof(a)))return false;
        for(unsigned j=0;j<i;++j)if(overlaps(p,copy[i].bytes,reinterpret_cast<Address>(copy[j].data),copy[j].bytes))return false;
        total+=copy[i].bytes;
    }
    const unsigned serial=configured(a)?a.serial:1;
    if(!serial)return false;
    a={};a.magic=kMagic;a.serial=serial;a.banks=count;
    for(unsigned i=0;i<count;++i)a.bank[i]=copy[i];
    return true;
}
const Entry *find(const Arena &a,Handle h,Owner owner) {
    if(!configured(a)||h.slot>=kLeases||!h.serial||owner<RECORDING||owner>WORKSPACE)return nullptr;
    const Entry &e=a.entry[h.slot];return e.owner==unsigned(owner)&&e.serial==h.serial?&e:nullptr;
}
Handle acquire(Arena &a,Owner owner,unsigned bytes) {
    if(!configured(a)||!a.serial||owner<RECORDING||owner>WORKSPACE||!bytes||bytes>~0u-31u)return invalid();
    bytes=(bytes+31u)&~31u;
    unsigned slot=kLeases;for(unsigned i=0;i<kLeases;++i)if(!a.entry[i].owner){slot=i;break;}
    if(slot==kLeases)return invalid();
    Address best=0;unsigned waste=~0u;
    for(unsigned bank=0;bank<a.banks;++bank) {
        Address cursor=reinterpret_cast<Address>(a.bank[bank].data);
        const Address end=cursor+a.bank[bank].bytes;
        for(unsigned gap=0;gap<=kLeases && cursor<end;++gap) {
            Address next=end,after=end;
            for(unsigned i=0;i<kLeases;++i)if(a.entry[i].owner) {
                const Entry &e=a.entry[i];const Address p=reinterpret_cast<Address>(e.span.data);
                if(p>=cursor&&p<next){next=p;after=p+e.span.bytes;}
            }
            if(next-cursor>=bytes && next-cursor-bytes<waste) {
                best=cursor;waste=static_cast<unsigned>(next-cursor-bytes);
            }
            if(next==end)break;
            cursor=after;
        }
    }
    if(!best)return invalid();
    Entry &e=a.entry[slot];e={{reinterpret_cast<void*>(best),bytes},unsigned(owner),a.serial++,0,0,0};
    return {slot,e.serial};
}
View read(const Arena &a,Handle h,Owner owner) {
    const Entry *e=find(a,h,owner);
    return e && !(e->pending&&e->direction==WRITES_MEMORY)?View{e->span.data,e->span.bytes}:View{};
}
Span write(Arena &a,Handle h,Owner owner) {
    const Entry *e=find(a,h,owner);return e&&!e->pending?e->span:Span{};
}
bool pin(Arena &a,Handle h,Owner owner,unsigned sequence,Transfer direction) {
    const Entry *checked=find(a,h,owner);
    if(!checked||checked->pending||!sequence||sequence<=checked->lastTransfer||
       (direction!=READS_MEMORY&&direction!=WRITES_MEMORY))return false;
    Entry &e=a.entry[h.slot];e.pending=e.lastTransfer=sequence;e.direction=direction;return true;
}
bool complete(Arena &a,Handle h,Owner owner,unsigned sequence) {
    const Entry *checked=find(a,h,owner);
    if(!checked||!sequence||checked->pending!=sequence)return false;
    a.entry[h.slot].pending=0;return true;
}
bool release(Arena &a,Handle h,Owner owner) {
    const Entry *checked=find(a,h,owner);if(!checked||checked->pending)return false;
    a.entry[h.slot]={};return true;
}
unsigned largest(const Arena &a) {
    if(!configured(a))return 0;
    unsigned result=0;
    for(unsigned bank=0;bank<a.banks;++bank) {
        Address cursor=reinterpret_cast<Address>(a.bank[bank].data);
        const Address end=cursor+a.bank[bank].bytes;
        for(unsigned gap=0;gap<=kLeases && cursor<end;++gap) {
            Address next=end,after=end;
            for(unsigned i=0;i<kLeases;++i)if(a.entry[i].owner) {
                const Entry &e=a.entry[i];const Address p=reinterpret_cast<Address>(e.span.data);
                if(p>=cursor&&p<next){next=p;after=p+e.span.bytes;}
            }
            if(next-cursor>result)result=static_cast<unsigned>(next-cursor);
            if(next==end)break;
            cursor=after;
        }
    }
    return result;
}
unsigned available(const Arena &a) {
    if(!configured(a))return 0;
    unsigned bytes=0;for(unsigned i=0;i<a.banks;++i)bytes+=a.bank[i].bytes;
    for(unsigned i=0;i<kLeases;++i)if(a.entry[i].owner)bytes-=a.entry[i].span.bytes;
    return bytes;
}
}
