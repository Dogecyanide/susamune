#ifndef TIMEWARP_BOOT_QUICK_H
#define TIMEWARP_BOOT_QUICK_H

#include "../../include/susamune/mod_quick.h"

/* Compatibility names keep private proofs on the production implementation. */
#define TWBootQuickAddress SusamuneModQuickAddress
#define TWBootQuickDecode SusamuneModQuickDecode
#define TWBootQuickLength SusamuneModQuickLength
#define TWBootQuickLz4 SusamuneModQuickLz4
#define TWBootQuickPass SusamuneModQuickPass
#define TWBootQuickRange SusamuneModQuickRange
#define TWBootQuickValidate SusamuneModQuickValidate
#define TWBootQuickWord SusamuneModQuickWord
#define TWBootQuickWordIs32 SusamuneModQuickWordIs32
#define TW_BOOT_QUICK_BLOCK SUSAMUNE_MOD_QUICK_BLOCK
#define TW_BOOT_QUICK_COMMIT_FAILED SUSAMUNE_MOD_QUICK_COMMIT_FAILED
#define TW_BOOT_QUICK_CORRUPT SUSAMUNE_MOD_QUICK_CORRUPT
#define TW_BOOT_QUICK_INVALID SUSAMUNE_MOD_QUICK_INVALID
#define TW_BOOT_QUICK_OK SUSAMUNE_MOD_QUICK_OK

#endif
