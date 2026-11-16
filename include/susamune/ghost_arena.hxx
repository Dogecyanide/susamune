#pragma once

namespace GhostArena {
using Address = __UINTPTR_TYPE__;
enum { kBanks=8, kLeases=24, kAlignment=32, kMagic=0x47415231u };
enum Owner { NO_OWNER, RECORDING, PLAYBACK, RACING, WORKSPACE };
enum Transfer { READS_MEMORY=1, WRITES_MEMORY=2 };
struct Span { void *data; unsigned bytes; };
struct View { const void *data; unsigned bytes; };
struct Handle { unsigned slot, serial; };
struct Entry { Span span; unsigned owner, serial, pending, lastTransfer, direction; };
struct Arena { unsigned magic, serial, banks; Span bank[kBanks]; Entry entry[kLeases]; };
inline Handle invalid() { return {kLeases,0}; }
inline bool validSpan(Span s) {
    const Address p=reinterpret_cast<Address>(s.data);
    return p && s.bytes && !(p&31u) && !(s.bytes&31u) && p+s.bytes>=p;
}
inline bool overlaps(Address a,Address an,Address b,Address bn) {
    return a<b+bn && b<a+an;
}
inline bool configured(const Arena &a) { return a.magic==kMagic && a.banks && a.banks<=kBanks; }
// Zero-initialize once; callers serialize access and perform cache maintenance.
// Live leases, including pending I/O, prevent reconfiguration.
bool configure(Arena &a,const Span *spans,unsigned count);
const Entry *find(const Arena &a,Handle h,Owner owner);
Handle acquire(Arena &a,Owner owner,unsigned bytes);
View read(const Arena &a,Handle h,Owner owner);
Span write(Arena &a,Handle h,Owner owner);
// An exact generation and increasing transfer sequence prevent stale completion from freeing a new buffer.
bool pin(Arena &a,Handle h,Owner owner,unsigned sequence,Transfer direction);
bool complete(Arena &a,Handle h,Owner owner,unsigned sequence);
bool release(Arena &a,Handle h,Owner owner);
unsigned largest(const Arena &a);
unsigned available(const Arena &a);
}
