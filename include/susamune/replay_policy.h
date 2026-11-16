#pragma once
namespace ReplayPolicy {
enum { PLAYING=1, DERIVED=2, SOURCE_TAS=4 };
struct State {unsigned flags,frame,painted;};
inline void begin(State &s,bool tas) {s={PLAYING|DERIVED|(tas?SOURCE_TAS:0u),0,0};}
inline void stop(State &s) {s.flags&=~PLAYING;}
inline void stageEntry(State &s,bool replaying) {if(!replaying)s={};}
inline bool playing(const State &s) {return (s.flags&PLAYING)!=0;}
inline bool blocksResults(const State &s) {return (s.flags&DERIVED)!=0;}
inline bool sourceTas(const State &s) {return (s.flags&SOURCE_TAS)!=0;}
inline void paint(State &s) {s.painted=s.frame;}
inline bool advance(State &s) {return !(s.flags&PLAYING)||++s.frame-s.painted<=2;}
}
