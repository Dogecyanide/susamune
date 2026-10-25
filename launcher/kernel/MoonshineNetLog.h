#ifndef MOONSHINE_NET_LOG_H
#define MOONSHINE_NET_LOG_H
#include "MoonshineNet.h"
#include "susamune/live_transport.h"
/* Capture is ARM-main only; Service needs the existing idle-disc FAT guard. */
void MoonshineNetLogPacket(int outgoing, const TWLiveEndpoint *, const void *, unsigned);
void MoonshineNetLogEvent(const char *, unsigned epoch, unsigned state, int error);
void MoonshineNetLogSample(const struct MoonshineNetStatus *, unsigned txQueued,
    unsigned rxQueued, unsigned ppcConsumed);
int MoonshineNetLogPending(void);
void MoonshineNetLogService(void);
#endif
