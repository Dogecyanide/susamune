#pragma once
namespace GhostReplayTest {
#if MOONSHINE_GHOST_TRACE
void update();
void finished();
bool action(unsigned row);
const char *status();
const char *recordLabel();
#else
inline void update() {}
inline void finished() {}
#endif
}
