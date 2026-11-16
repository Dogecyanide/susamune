#pragma once
#if MOONSHINE_MEMORY_TELEMETRY
#include "susamune/live_race_session.hxx"
namespace MemoryCapture {
#if !defined(MOONSHINE_MEMORY_CAPTURE) || MOONSHINE_MEMORY_CAPTURE
bool receive(LiveRaceSession::Session &, const void *, unsigned);
void poll(unsigned now);
bool send(LiveRaceSession::Session &, unsigned now);
void cancel();
#else
inline bool receive(LiveRaceSession::Session &,const void *,unsigned){return false;}
inline void poll(unsigned){}
inline bool send(LiveRaceSession::Session &,unsigned){return false;}
inline void cancel(){}
#endif
}
#endif
