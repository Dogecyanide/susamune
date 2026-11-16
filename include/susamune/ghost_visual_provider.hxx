#pragma once
#include "susamune/ghost.hxx"
#include "susamune/ghost_trace_index.hxx"
#include "susamune/ghost_camera.hxx"
#include "susamune/ghost_format.h"

namespace GhostVisualProvider {
enum QueryFlags { WATCH=1,HISTORY=2 };
struct Query {
    unsigned runner,segment,scene,attempt,token;
    int qf;
    unsigned flags;
    int routeVariant;
    unsigned routeParentArea,routeFlags;
};
struct Frame { Ghost::VisualState visual; SusamunePracticeInput input; unsigned runFlags; bool hasInput; };
struct Config {
    void *context;
    bool (*valid)(void *,unsigned sourceGeneration);
    bool (*sample)(void *,const Query &,Frame &);
    unsigned runners,sourceGeneration,token;
    bool (*camera)(void *,const Query &,GhostCamera::View &);
    bool (*path)(void *,const Query &,SusamuneGhostPoseSample *,unsigned capacity,unsigned &count);
};
struct Provider {
    Config config;
    Frame frames[2];
    SusamuneGhostPoseSample pathScratch[97];
    unsigned generation,prepared,readyMask;
};
// Zero-initialize once. Callbacks are trusted code, never loaded from a recording.
// Keep provider/context/leases alive until stop succeeds; serialize on the render thread.
bool prepare(Provider &,const Config &,unsigned &generation);
bool activate(Provider &,unsigned generation);
bool stop(Provider &,unsigned generation);
bool stopActive();
bool active();
unsigned runners();
void suspend();
// Sample callbacks must not block or recycle leases. HISTORY is read-only.
bool refresh(const Query *,unsigned count,bool atomicPair);
bool historical(const Query &,Frame &);
bool read(unsigned runner,Frame &);
bool input(unsigned runner,SusamunePracticeInput &);
unsigned runFlags(unsigned runner);
bool cameraAvailable();
bool camera(const Query &,GhostCamera::View &);
bool path(const Query &,const SusamuneGhostPoseSample *&,unsigned &count);
bool fromSample(const GhostTraceIndex::Sample &,unsigned token,Frame &);
}
