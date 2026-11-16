#ifndef GHOST_SERVICE_NATIVE_H
#define GHOST_SERVICE_NATIVE_H
#include "susamune/ghost_service.h"
/* Called only while the existing GHOST transfer lease is held. No worker does FAT IO. */
int GhostServiceStart(void *stage, unsigned stageSize, const char *region,
    unsigned unixTime, const struct GhostServiceEntry *download, void *session);
struct GhostAccount;
int GhostServiceAction(void *stage, unsigned stageSize, unsigned unixTime,
    unsigned action, unsigned uploadBytes, struct GhostAccount *, void *session,
    const struct GhostServiceUpload *upload);
/* Session storage outlives the transfer lease. Forget only after Release. */
void GhostServiceForget(void);
unsigned GhostServiceProgress(void);
unsigned GhostServiceMainDelay(void);
const struct GhostServiceTrace *GhostServiceTrace(unsigned index);
void GhostServiceCancel(void);
int GhostServicePoll(unsigned *bytes);
unsigned GhostServiceRead(void **data);
void GhostServiceReadAck(unsigned bytes);
void GhostServiceRelease(void);
int GhostServiceShutdown(void);
#endif
