#pragma once
#if MOONSHINE_MEMORY_TELEMETRY
#include "susamune/live_race_session.hxx"
namespace MemoryTelemetry { void update(LiveRaceSession::Session &, unsigned now); }
#else
#define MemoryTelemetryUpdate(session, now) ((void)0)
#endif
