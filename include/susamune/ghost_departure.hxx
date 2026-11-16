#pragma once
#include "susamune/ghost_recording.hxx"
namespace GhostDeparture {
GhostRecording::Gate begin(unsigned scene,bool selectedIL);
void poll();
bool waiting();
// Commit only at the stage handoff. A late storage failure must not reuse an older attempt.
bool finish();
void cancel();
}
