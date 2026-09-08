#ifndef SUSAMUNE_KERNEL_STATE_STORAGE_H
#define SUSAMUNE_KERNEL_STATE_STORAGE_H
#include "global.h"
void SusamuneStateStorageInit(void);
bool SusamuneStateStoragePending(void);
void SusamuneStateStorageService(void);
#endif
