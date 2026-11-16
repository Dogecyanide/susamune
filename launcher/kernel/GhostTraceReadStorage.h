#pragma once
#if MOONSHINE_GHOST_TRACE
struct GhostTraceReadWindow { unsigned physical,bytes; };
/* The strong platform hook grants one explicit map window under a live lease.
 * It must exclude recorder-owned buffers and keep the grant stable through I/O. */
int GhostTraceReadStorageWindow(unsigned channel,unsigned bootNonce,unsigned lease,
                               struct GhostTraceReadWindow *window);
void GhostTraceReadStorageInit(unsigned bootNonce);
int GhostTraceReadStoragePending(void);
int GhostTraceReadStorageActive(void);
/* Called only under the existing DI/FatFS idle guard. Three writer slices per
 * reader slice; reader channels alternate. */
int GhostTraceReadStorageService(int writerPending);
int GhostTraceReadStorageOwns(unsigned fileNonce,unsigned run);
#else
static inline void GhostTraceReadStorageInit(unsigned nonce) {(void)nonce;}
static inline int GhostTraceReadStoragePending(void) {return 0;}
static inline int GhostTraceReadStorageActive(void) {return 0;}
static inline int GhostTraceReadStorageService(int writerPending) {(void)writerPending;return 0;}
static inline int GhostTraceReadStorageOwns(unsigned nonce,unsigned run) {(void)nonce;(void)run;return 0;}
#endif
