#ifndef SUSAMUNE_MOD_BOOT_H
#define SUSAMUNE_MOD_BOOT_H

/* ARM publishes these with RESET_STATUS before releasing FakeEntryLoad.
 * Zero lines means no cold code. The PPC reads the uncached aliases. */
#define SUSAMUNE_MOD_BOOT_COLD_LINES 0x1300342Cu
#define SUSAMUNE_MOD_BOOT_COLD_START 0x13003430u
#define SUSAMUNE_MOD_BOOT_MENU_CODE 0x80000000u

#endif
