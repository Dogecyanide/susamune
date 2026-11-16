#pragma once
namespace GhostWorldWitness {
enum { kSchema=1, kWireBytes=20, kMaxActors=1024, kMaxReferences=8192, kMaxManagers=256 };
enum Scope { IDENTITY=1, POSITION=2, ROTATION=4, SCALE=8, LINEAR_VELOCITY=16,
             ANGULAR_VELOCITY=32, VELOCITY=64, HIT_AND_LIVE_FLAGS=128, ORDERED_CONDUCTOR=256,
             kScope=511 };
enum Status { COMPLETE, NOT_READY, CAPACITY, BAD_SOURCE, NONFINITE, BAD_ROSTER, ARGUMENT };
struct Record { unsigned scope,status,count,hash; };
// Float fields are IEEE754 words, in position/rotation/scale/linear/angular/velocity order.
struct Actor { unsigned nameKey,type,scalar[18],hitFlags,liveFlags; };
struct Hash { unsigned *seen; unsigned slots,count,value,references,status; };
struct Memory {
    void *context;
    // Reads native big-endian bytes from an owned live snapshot, never file-provided pointers.
    bool (*read)(void *,unsigned address,void *output,unsigned bytes);
};
bool begin(Hash &,unsigned *scratch,unsigned slots);
bool add(Hash &,unsigned identity,const Actor &);
Record finish(const Hash &);
// Caller serializes the same pre-direct phase and verifies stage/setup ownership.
// Scratch is a power-of-two table, at most4096 words; no addresses enter the hash.
Record capture(const Memory &,unsigned conductor,unsigned *scratch,unsigned slots);
// Diagnostic rows contain address/ordinal, the native0xF4 prefix, and zero padding.
Record captureSnapshot(const Memory &,unsigned conductor,unsigned *scratch,unsigned slots,
                       unsigned char *rows,unsigned capacity,unsigned &count);

void encode(unsigned char (&wire)[kWireBytes],const Record &);
bool decode(const void *,unsigned bytes,Record &);
bool matches(const Record &,const Record &);
inline Record unavailable() { return {kScope,NOT_READY,0,0}; }
#if defined(__powerpc__)
Record captureNative(unsigned conductor,unsigned *scratch,unsigned slots);
Record snapshotNative(unsigned conductor,unsigned *scratch,unsigned slots,unsigned char *rows,unsigned capacity,unsigned &count);
#endif
static_assert(sizeof(Actor)==88,"canonical common actor fields");
}
