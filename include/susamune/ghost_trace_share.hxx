#pragma once
namespace GhostTraceShare {
enum Result { IDLE, RUNNING, SAVED, FAILED };
bool begin(const void *manifest, unsigned bytes);
Result poll();
bool busy();
void cancel();
}
