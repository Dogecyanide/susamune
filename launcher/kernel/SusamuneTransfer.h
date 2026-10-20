#ifndef SUSAMUNE_KERNEL_TRANSFER_H
#define SUSAMUNE_KERNEL_TRANSFER_H
#include "global.h"
#include "susamune/transfer_layout.h"

void SusamuneTransferInit(void);
bool SusamuneTransferPending(void);
void SusamuneTransferService(void);
/* PPC parked and FAT/DI excluded throughout retirement and ResumeLegacy. */
void SusamuneTransferBeginRetire(void);
bool SusamuneTransferRetireStep(void);
bool SusamuneTransferRetireFailed(void);
bool SusamuneTransferResumeLegacy(void);
bool SusamuneTransferActive(void);
bool SusamuneTransferAllows(u32 owner, u32 seq, u32 session, u32 command);
bool SusamuneTransferCancelled(u32 owner);
u8 *SusamuneTransferStageBase(void);
u32 SusamuneTransferStageSize(void);
u8 *SusamuneTransferGhostBase(void);
u32 SusamuneTransferPoolSize(void);
u8 *SusamuneTransferPoolPiece(u32 offset, u32 *size);
bool SusamuneTransferPoolRange(u32 offset, u32 size);
bool SusamuneTransferImportRange(u32 offset, u32 size);
bool SusamuneTransferWindowRange(u32 packed, u32 offset, u32 size);
#endif
