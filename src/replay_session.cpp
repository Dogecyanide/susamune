#include "susamune/replay_session.hxx"
#if MOONSHINE_GHOST_TRACE
#include "susamune/replay_policy.h"
#include "susamune/ghost_trace.h"
#include "susamune/menu.hxx"
#include "susamune/qft_timer.hxx"
#include "JSystem/J2D/J2DOrthoGraph.hxx"
namespace ReplaySession {
namespace {
ReplayPolicy::State &state=*reinterpret_cast<ReplayPolicy::State*>(MS_TRACE_CONTROL_PPC+0x3240);
bool initialized;
static_assert(sizeof(ReplayPolicy::State)<=0x100,"replay policy excludes the report worker");
}
void begin(bool tas){initialized=true;ReplayPolicy::begin(state,tas);}
void stop(){
    if(!initialized)return;
    if(ReplayPolicy::playing(state))gQFTTimer.markPracticeAssisted();
    ReplayPolicy::stop(state);
}
void stageEntry(bool replaying){if(initialized)ReplayPolicy::stageEntry(state,replaying);}
bool blocksResults(){return initialized&&ReplayPolicy::blocksResults(state);}
bool sourceTas(){return initialized&&ReplayPolicy::sourceTas(state);}
void markSourceTas(){if(initialized)state.flags|=ReplayPolicy::SOURCE_TAS;}
bool advance(){return !initialized||ReplayPolicy::advance(state);}
void draw(Menu *menu){
    if(!menu||!initialized||!ReplayPolicy::playing(state))return;
    J2DOrthoGraph ortho(0,0,640,480);ortho.setup2D();
    menu->drawReplayMarker(&ortho,sourceTas());ReplayPolicy::paint(state);
}
}
#endif
