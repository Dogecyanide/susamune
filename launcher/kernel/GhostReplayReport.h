#pragma once
#if MOONSHINE_GHOST_TRACE
void GhostReplayReportInit(void);
int GhostReplayReportPending(void);
void GhostReplayReportService(void);
#else
static inline void GhostReplayReportInit(void) {}
static inline int GhostReplayReportPending(void) {return 0;}
static inline void GhostReplayReportService(void) {}
#endif
