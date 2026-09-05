# FOXTROT memory layout

The MEM1 reservation is 768 KiB. The game arena moves by `0xC2000`, including
the existing 8 KiB debug-stack gap. Compared with V2.2, the game loses exactly
256 KiB of heap capacity. Smaller mod images create development headroom
inside this reservation; they do not return those bytes to the game heap.

## MEM1 ownership

Offsets are relative to each region's linked mod base.

| Range | Owner | Capacity |
|---|---|---:|
| `0x00000–0x58000` | Low code/data span | 352 KiB |
| `0x58000–0x78000` | Attachment model heap | 128 KiB |
| `0x78000–0x7FFC0` | Existing unused tail | 32,704 B |
| `0x7FFC0–0x80000` | Protected timer/scratch ABI | 64 B |
| `0x80000–0xC0000` | Upper code/data span | 256 KiB |

The two code/data spans provide 608 KiB of capacity. Mod-bin V3, launcher
injection and Dolphin DOL/BPS output all carry them separately. Initialized
bytes and trailing BSS are checked separately; zero filling cannot touch the
attachment heap or scratch. The 512 KiB BPS disc-file extent is a separate
storage constraint, not the size of the runtime reservation.

Final console mod builds on 2026-09-05:

| Region | Initialized image | Full runtime image | Free code/data capacity |
|---|---:|---:|---:|
| JP | 346,084 B | 384,768 B | 237,824 B |
| US | 344,788 B | 383,488 B | 239,104 B |
| PAL | 344,920 B | 383,616 B | 238,976 B |

The largest runtime image is about 375.8 KiB; it leaves about 232.3 KiB of
unused code/data capacity inside the requested reservation.

The local 4096-frame input take no longer consumes 65,536 bytes of MEM1 BSS.
It reuses the former ghost-file payload in MEM2. Native timer drawing shares
three vtable copies and bounds its temporary snapshots at 32 panes. All three
retail layouts, and live JP/PAL trees after stage setup, contain 18 panes.
Collection validates the complete tree before changing anything and refuses
unsupported classes, cycles or more than 32 panes.

Dolphin keeps the `Menu` object in MEM1 so its embedded retail text-box matrix
does not reach Dolphin 5.0's paired-single JIT path for fake MEM2. Wii keeps
the menu in actual MEM2. No game heap allocation is added by these buffers.

## Wii MEM2 ownership

All ends below are exclusive. ARM physical aliases subtract `0x80000000`.

| PPC range | Owner |
|---|---|
| `0x91880000–0x91880100` | Existing ghost storage doorbells |
| `0x91880100–0x91890100` | PPC-only local input take |
| `0x918EA000–0x91900000` | Existing secondary ghost model heap |
| `0x91900000–0x91B3F000` | Bounded external file-patch handoff |
| `0x91B3F000–0x91C1F000` | Ghost recording inputs |
| `0x91C1F000–0x91CFF000` | Primary playback inputs |
| `0x91CFF000–0x91E3F000` | Complete ghost file transfer |
| `0x91E3F000–0x91EDE000` | Immutable mod file staging |
| `0x91EDE000–0x91F00000` | Existing immutable model asset vault |
| `0x91F00000–0x92EF0000` | Existing savestate payload window |
| `0x92EF0000–0x92F00000` | Existing configuration/runtime block |

External `patch.bin` and per-game `patch.txt` files now have a
`0x23F000` (2,355,200-byte) limit. The handoff fits up to 294,399 patch
records plus its count header. Global `/apps/gc_devo/patch.txt` retains its
existing limit below 1 MiB. Oversized files, invalid binary record counts,
incomplete reads and generated-output overflow cancel boot with a specific
error; patches are never silently truncated or disabled to fit. This limit
does not apply to the bundled `mod_jp.bin`, `mod_us.bin` or `mod_pal.bin`.

The tape requires ghost storage protocol 4, which moved file I/O out of the
old transfer payload. It does not require a mounted storage device. The ARM
never reads or writes the tape. The mod staging prefix remains immutable so
reset can inject the same image again. Snapshot size and established settings,
split and PB wire offsets are unchanged.

New live binds/settings/menu windows occupy configuration offsets `0x5B80`,
`0x5C00` and `0x6000`; the old live slots stay reserved. Cache-line ownership,
aliases, adjacency and capacities are enforced in `include/susamune/mem2_map.h`.

## Measured scene headroom

Isolated Dolphin 5.0 JIT runs on 2026-09-05 measured Bianco 1 after setup:

| Region | Stage allocation span | Free bytes |
|---|---:|---:|
| JP | 14,898,304 B | 1,366,088 B |
| PAL | 14,942,176 B | 1,382,152 B |

The heap vtables, field offsets and cursor/free arithmetic were checked.
These are emulator measurements for one scene. The user's earlier worst-stage
measurement of roughly 997 KiB predicts roughly 741 KiB after the reservation
increase; actual Wii minimum headroom remains a hardware playtest item.
