#pragma once
#include "susamune/ghost_memory.h"
#if TIMEWARP_QF_MEMORY
namespace GhostMemory {
void init();
void update();
bool ready();
bool admitted();
void status(unsigned *out);
void *primary(unsigned bank);
void *tail(unsigned bank);
}
#else
namespace GhostMemory { inline void init() {} inline void update() {} inline bool ready() { return false; } inline bool admitted() { return false; } }
#endif
