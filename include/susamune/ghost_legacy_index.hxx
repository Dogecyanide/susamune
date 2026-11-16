#pragma once
#include "susamune/ghost_legacy_stream.hxx"

namespace GhostLegacyIndex {
enum Timeline { POSES,OBSERVATIONS };
struct Adapter {
    const GhostLegacyStream::Metadata *source;
    GhostTraceIndex::Builder poses,observations;
    unsigned poseIndex,inputIndex,inputSegment,inputSerial,target;
};
struct Observation {
    unsigned sourceIndex,qf;
    short cameraYaw;
    unsigned char cameraMode;
    bool present,steering;
};
bool begin(Adapter &,const GhostLegacyStream::Metadata &,
           GhostTraceIndex::Page *poseDirectory,unsigned poseCapacity,void *poseScratch,unsigned poseBytes,
           GhostTraceIndex::Page *inputDirectory,unsigned inputCapacity,void *inputScratch,unsigned inputBytes);
GhostTraceIndex::Result feed(Adapter &,const GhostLegacyStream::Event &);
GhostTraceIndex::Result finish(Adapter &,const GhostLegacyStream::Reader &);
const GhostTraceIndex::Page *pendingPage(const Adapter &);
const void *pendingData(const Adapter &);
bool commitPage(Adapter &);
bool indexSegment(const GhostTraceIndex::Page *,unsigned count,unsigned sourceSegment,unsigned &indexSegment);
// The caller samples the two timelines independently with the shared race sampler.
bool sample(const GhostLegacyStream::Metadata &,unsigned sourceSegment,int qf,
            const GhostTraceIndex::Bracket &pose,const GhostTraceIndex::Bracket *input,
            GhostTraceIndex::Sample &out,Observation *provenance=nullptr);
}
