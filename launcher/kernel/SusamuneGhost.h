#ifndef __SUSAMUNE_GHOST_H__
#define __SUSAMUNE_GHOST_H__

#include "global.h"

void SusamuneGhostInit(void);
bool SusamuneGhostPending(void);
void SusamuneGhostService(void);
bool SusamuneGhostQuiescent(void);
/* PPC parked, FAT/DI excluded: drain one pass and latch until Init.
 * A failed close requires a kernel restart; it never certifies quiescence. */
bool SusamuneGhostRetire(void);
bool SusamuneGhostRetireFailed(void);
bool SusamuneGhostRequestReady(u32 seq, u32 command);
bool SusamuneGhostReceiptReady(u32 seq, u32 command);

#endif
