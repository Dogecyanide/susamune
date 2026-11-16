#pragma once
#include "loading_trace.h"
namespace LoadingTrace {
#if MOONSHINE_MEMORY_TELEMETRY && MOONSHINE_GHOST_TRACE && !IS_EMULATOR
void mark(unsigned phase,unsigned value0=0);
#else
inline void mark(unsigned,unsigned=0) {}
#endif
}
