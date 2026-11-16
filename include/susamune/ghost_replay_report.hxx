#pragma once
namespace GhostReplayReport {
#if MOONSHINE_GHOST_TRACE
bool reserve();
bool submit(unsigned payloadBytes,unsigned fileNonce,unsigned run);
bool pending();
unsigned poll();
#else
inline bool pending(){return false;}
inline unsigned poll(){return 0;}
#endif
}
