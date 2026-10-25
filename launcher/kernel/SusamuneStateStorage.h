#ifndef SUSAMUNE_KERNEL_STATE_STORAGE_H
#define SUSAMUNE_KERNEL_STATE_STORAGE_H
#include "global.h"
void SusamuneStateStorageInit(void);
bool SusamuneStateStoragePending(void);
void SusamuneStateStorageService(void);
bool SusamuneStateStorageQuiescent(void);
/* PPC parked, FAT/DI excluded: drain one pass and latch until Init.
 * A failed close requires a kernel restart; it never certifies quiescence. */
bool SusamuneStateStorageRetire(void);
bool SusamuneStateStorageRetireFailed(void);
bool SusamuneStateStorageRequestReady(u32 seq, u32 session, u32 command);
bool SusamuneStateStorageReceiptReady(u32 seq, u32 session, u32 command);
#endif
