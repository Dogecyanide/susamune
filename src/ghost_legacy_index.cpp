#include "susamune/ghost_legacy_index.hxx"

namespace GhostLegacyIndex {
namespace {
using namespace GhostTraceIndex;
using GhostLegacyStream::Metadata;
bool overlap(const void *a,unsigned an,const void *b,unsigned bn) {
    const __UINTPTR_TYPE__ x=reinterpret_cast<__UINTPTR_TYPE__>(a),y=reinterpret_cast<__UINTPTR_TYPE__>(b);
    return x<y+bn&&y<x+an;
}
Identity identity(const Metadata &m,unsigned segment) {
    const auto &s=m.segments[segment];return {(unsigned(s.routeArea)<<8)|s.routeEpisode,0,segment+1};
}
Result fail(Adapter &a) { a.poses.error=STATE;return FAILED; }
bool belongs(const Sample &s,const Metadata &m,unsigned segment) {
    const auto &range=m.segments[segment];
    return (s.flags&POSE)&&s.reserved[0]==m.version&&s.movement>=range.firstSample&&s.movement-range.firstSample<range.sampleCount;
}
}
bool begin(Adapter &a,const Metadata &source,Page *poses,unsigned poseCapacity,void *poseScratch,unsigned poseBytes,
           Page *inputs,unsigned inputCapacity,void *inputScratch,unsigned inputBytes) {
    if(!poseCapacity||poseCapacity>kMaxPages||!inputCapacity||inputCapacity>kMaxPages)return false;
    const void *spans[]={&a,&source,poses,poseScratch,inputs,inputScratch};
    const unsigned sizes[]={sizeof(a),sizeof(source),static_cast<unsigned>(poseCapacity*sizeof(Page)),kPageBytes,
        static_cast<unsigned>(inputCapacity*sizeof(Page)),kPageBytes};
    for(unsigned i=0;i<6;++i)for(unsigned j=0;j<i;++j)if(overlap(spans[i],sizes[i],spans[j],sizes[j]))return false;
    a={};a.source=&source;
    return GhostTraceIndex::begin(a.poses,poses,poseCapacity,poseScratch,poseBytes)&&
        GhostTraceIndex::begin(a.observations,inputs,inputCapacity,inputScratch,inputBytes);
}
Result feed(Adapter &a,const GhostLegacyStream::Event &e) {
    if(!a.source||a.poses.error||a.observations.error)return FAILED;
    const Metadata &m=*a.source;
    if(e.type==GhostLegacyStream::POSE_SAMPLE) {
        if(e.index!=a.poseIndex||e.segment>=m.segmentCount)return fail(a);
        a.target=POSES;const Result result=append(a.poses,identity(m,e.segment),e.sample);
        if(result==ACCEPTED)++a.poseIndex;
        return result;
    }
    if(e.type!=GhostLegacyStream::INPUT_SAMPLE)return ACCEPTED;
    if(e.index!=a.inputIndex)return fail(a);
    while(a.inputSegment<m.segmentCount) {
        const auto &segment=m.segments[a.inputSegment];
        if(e.sample.qf<0||unsigned(e.sample.qf)<segment.startQf||unsigned(e.sample.qf)>segment.endQf) { ++a.inputSegment;continue; }
        Sample row=e.sample;row.frame=a.inputSerial+1;a.target=OBSERVATIONS;
        const Result result=append(a.observations,identity(m,a.inputSegment),row);
        if(result!=ACCEPTED)return result;
        ++a.inputSerial;++a.inputSegment;
    }
    a.inputSegment=0;++a.inputIndex;return ACCEPTED;
}
Result finish(Adapter &a,const GhostLegacyStream::Reader &source) {
    if(a.source!=&source.metadata||GhostLegacyStream::status(source)!=GhostLegacyStream::COMPLETE||
       a.poseIndex!=source.metadata.poseCount||a.inputIndex!=source.metadata.inputCount)return fail(a);
    a.target=POSES;Result result=GhostTraceIndex::finish(a.poses);if(result!=FINISHED)return result;
    a.target=OBSERVATIONS;return GhostTraceIndex::finish(a.observations);
}
const Page *pendingPage(const Adapter &a) { return GhostTraceIndex::pendingPage(a.target==POSES?a.poses:a.observations); }
const void *pendingData(const Adapter &a) { return pendingPage(a)?(a.target==POSES?a.poses.samples:a.observations.samples):nullptr; }
bool commitPage(Adapter &a) { return GhostTraceIndex::commitPage(a.target==POSES?a.poses:a.observations); }
bool indexSegment(const Page *pages,unsigned count,unsigned sourceSegment,unsigned &out) {
    if(!pages||!count||count>kMaxPages||sourceSegment>=64)return false;
    unsigned lo=0,hi=count;
    while(lo<hi) { unsigned mid=lo+(hi-lo)/2;if(pages[mid].generation<sourceSegment+1)lo=mid+1;else hi=mid; }
    if(lo==count||pages[lo].generation!=sourceSegment+1)return false;
    out=pages[lo].segment;return true;
}
bool sample(const Metadata &m,unsigned segment,int qf,const Bracket &pose,const Bracket *input,Sample &out,Observation *provenance) {
    if(provenance)*provenance={};
    if(segment>=m.segmentCount||qf<0||unsigned(qf)<m.segments[segment].startQf||unsigned(qf)>m.segments[segment].endQf||
       !pose.before||!pose.after||!belongs(*pose.before,m,segment)||!belongs(*pose.after,m,segment))return false;
    const Sample &a=*pose.before,&b=*pose.after;out=a;
    const int span=b.qf-a.qf,elapsed=qf-a.qf;
    if(elapsed<0||(span>0&&elapsed>span))return false;
    if(span>0) {
        const float t=float(elapsed)/float(span);
        out.x=a.x+(b.x-a.x)*t;out.y=a.y+(b.y-a.y)*t;out.z=a.z+(b.z-a.z)*t;
        int yaw=(int(b.yaw)-int(a.yaw)+32768)&65535;yaw-=32768;
        out.yaw=static_cast<short>(int(a.yaw)+yaw*elapsed/span);
        if(a.animationId==b.animationId) {
            int delta=(int(b.animationPhase)-int(a.animationPhase)+2048)&4095;delta-=2048;
            out.animationPhase=static_cast<unsigned short>((int(a.animationPhase)+int(static_cast<long long>(delta)*elapsed/span))&4095);
        }
    }
    out.qf=qf;out.flags&=~INPUT;out.raw={};out.fludd={};
    const Sample *observation=input?input->before:nullptr;
    if(observation&&(observation->flags&INPUT)&&observation->reserved[0]==m.version&&
       observation->qf>=int(m.segments[segment].startQf)&&observation->qf<=qf&&
       observation->movement<m.inputCount&&
       (!(m.teachingFlags&SUSAMUNE_GHOST_TEACHING_INPUT_TRUNCATED)||unsigned(qf)<=m.lastInputQf)) {
        out.raw=observation->raw;out.fludd=observation->fludd;out.flags|=INPUT;
        if(provenance) {
            provenance->sourceIndex=observation->movement;provenance->qf=static_cast<unsigned>(observation->qf);provenance->present=true;
            if(m.version==10) { provenance->cameraYaw=observation->yaw;provenance->cameraMode=observation->reserved[1]&127u;provenance->steering=provenance->cameraMode!=127; }
        }
    }
    return true;
}
}
