#include "susamune/ghost_departure.hxx"
#include "susamune/ghost.hxx"
namespace GhostDeparture {
namespace {
struct Pending {unsigned scene;GhostRecording::Gate gate;bool active,selected;} s;
}
GhostRecording::Gate begin(unsigned scene,bool selectedIL){
    if(s.active)return s.scene==scene&&s.selected==selectedIL?s.gate:GhostRecording::DEPART_REFUSED;
    Ghost::prepareStreamDeparture(false);
    s={scene,GhostRecording::beforeDeparture(scene,selectedIL),true,selectedIL};
    return s.gate;
}
void poll(){if(s.active&&s.gate==GhostRecording::DEPART_WAIT)s.gate=GhostRecording::beforeDeparture(s.scene,s.selected);}
bool waiting(){return s.active&&s.gate==GhostRecording::DEPART_WAIT;}
bool finish(){
    if(!s.active||waiting())return false;
    const bool failed=s.gate==GhostRecording::DEPART_REFUSED;
    if(failed){GhostRecording::cancelArmed();GhostRecording::unrecordedDeparture();}
    s={};return failed;
}
void cancel(){if(s.active)GhostRecording::cancelArmed();s={};}
}
