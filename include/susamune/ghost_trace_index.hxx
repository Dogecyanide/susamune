#pragma once
#include "susamune/ghost_trace_decode.hxx"

namespace GhostTraceIndex {
enum { kSamplesPerPage=128, kPageBytes=8192, kMaxPages=65535 };
enum SampleFlags { POSE=1, QFT=2, INPUT=4, FROZEN=8, SUPPRESSED=16 };
enum Clock { QF_CLOCK, FRAME_CLOCK };
enum Result { ACCEPTED, PAGE_READY, FINISHED, FAILED };
enum Error { NONE, ARGUMENT, ORDER, VALUE, CAPACITY, STATE };
struct Identity { unsigned scene, attempt, generation; };
// Internal derived data, native-endian; never a public recording or native snapshot.
struct Sample {
    unsigned frame, movement;
    int qf;
    float x,y,z;
    unsigned heldObjectId;
    short yaw;
    unsigned short animationId,animationPhase,heldNameKey;
    SusamuneGhostFluddSample fludd;
    GhostTraceDecode::RawPad raw;
    unsigned flags;
    // reserved: zero for MSGT; legacy source version and original steering flags.
    unsigned char yoshi,visible,reserved[2];
};
struct Page {
    unsigned ordinal,segment,scene,attempt,generation,count;
    int firstQf,lastQf;
    unsigned firstFrame,lastFrame,hash,flags;
};
struct Query { unsigned segment; Clock clock; unsigned time; };
struct Needed { unsigned first,second; };
struct Bracket { const Sample *before,*after; float alpha; bool clamped; };
struct Builder {
    Page *pages;
    Sample *samples;
    unsigned capacity,count,used,segment,error,pending,done;
    Identity identity;
    Sample last;
    bool seen;
};
struct Capture { Builder builder; Sample sample; Identity identity; bool pending; };
inline Query byQf(unsigned segment,int qf) { return {segment,QF_CLOCK,static_cast<unsigned>(qf)^0x80000000u}; }
inline Query byFrame(unsigned segment,unsigned frame) { return {segment,FRAME_CLOCK,frame}; }
bool begin(Builder &,Page *,unsigned capacity,void *scratch,unsigned scratchBytes);
// PAGE_READY never consumes the supplied sample/event; retry it after commitPage().
Result append(Builder &,const Identity &,const Sample &);
Result finish(Builder &);
const Page *pendingPage(const Builder &);
bool commitPage(Builder &);
bool begin(Capture &,Page *,unsigned capacity,void *scratch,unsigned scratchBytes);
Result feed(Capture &,const GhostTraceDecode::Event &);
Result finish(Capture &);
bool validDirectory(const Page *,unsigned count);
bool validPage(const Page &,const void *,unsigned bytes);
bool locate(const Page *,unsigned count,Query,Needed &);
bool bracket(Query,const Page &,const Sample *,const Page &,const Sample *,Bracket &);
static_assert(sizeof(Sample)==64,"compact visual/input sample");
static_assert(sizeof(Page)==48,"compact visual page descriptor");
static_assert(sizeof(Sample)*kSamplesPerPage==kPageBytes,"compact page size");
}
