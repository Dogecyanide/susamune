#pragma once
#if MOONSHINE_GHOST_TRACE
void GhostTraceStorageInit(void);
int GhostTraceStoragePending(void);
void GhostTraceStorageService(void);
int GhostTraceBackgroundPending(void);
void GhostTraceBackgroundService(void);
#else
static inline void GhostTraceStorageInit(void) {}
static inline int GhostTraceStoragePending(void) {return 0;}
static inline void GhostTraceStorageService(void) {}
static inline int GhostTraceBackgroundPending(void) {return 0;}
static inline void GhostTraceBackgroundService(void) {}
#endif

#if MOONSHINE_GHOST_TRACE && TIMEWARP_LIVE_RACING && MOONSHINE_LOADING_DIAGNOSTICS
/* ARM-main only, no FAT access; also runs while the DI worker is busy. */
void GhostTraceLoadingService(void);
#else
static inline void GhostTraceLoadingService(void) {}
#endif
