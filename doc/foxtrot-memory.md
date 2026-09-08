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

Final console mod builds on 2026-09-08:

| Region | Initialized image | Full runtime image | Free code/data capacity |
|---|---:|---:|---:|
| JP | 366,224 B | 405,888 B | 216,704 B |
| US | 364,944 B | 404,608 B | 217,984 B |
| PAL | 365,060 B | 404,704 B | 217,888 B |

The largest runtime image is about 396.4 KiB; it leaves about 211.6 KiB of
unused code/data capacity inside the requested reservation.

The September 8 feedback update adds 1,500 B to the largest runtime image
relative to the September 7 package. The game arena reservation remains
768 KiB. Metadata spacing and the two health colours reuse
reserved settings bytes; the eight-byte native timer style occupies the final
gap before the fixed playlist mailbox. Original/Custom timer appearance uses
three reserved style bytes. Existing payload offsets do not move.

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

Sharing the kernel's 64-byte CRC table and raw checksum routine removes 100
bytes of ARM code/read-only data. Kernel writable data, BSS and every MEM2
window remain unchanged; model verification now uses two nibble steps per
byte instead of eight bit rounds.

## Measured scene headroom

Isolated Dolphin 5.0 JIT runs on 2026-09-05 measured Bianco 1 after setup:

| Region | Stage allocation span | Free bytes |
|---|---:|---:|
| JP | 14,898,304 B | 1,366,088 B |
| PAL | 14,942,176 B | 1,382,152 B |

The heap vtables, field offsets and cursor/free arithmetic were checked.

JP image `A27A0024`, US image `0391BB7B` and PAL image `BE5E2141` also
reached Bianco 5 through the real warp wheel in Dolphin 2606a JIT. Root-heap
boundaries stayed valid throughout each sampling window:

| Region | Initial free bytes | Minimum sampled free bytes | Window / samples |
|---|---:|---:|---:|
| JP | 759,512 B | 759,512 B (741.71 KiB) | 30.12 s / 30 |
| US | 789,240 B | 789,240 B (770.74 KiB) | 5 s / 96 |
| PAL | 787,800 B | 787,800 B (769.34 KiB) | 30.12 s / 30 |

Bianco 5 was the lowest-memory scene in the earlier console pressure pass
documented in `mem1_stability.md`. Its roughly 997 KiB estimate at a 512 KiB
reservation predicts roughly 741 KiB at 768 KiB, consistent with this JP
sample. Initial values are fully live observations after setup, not values
captured at the setup hook. These stationary emulator samples do not establish
a full-playthrough or Wii minimum. Private controller fixtures and complete
samples are recorded in `build/foxtrot-bianco5/{jp,pal}/proof.json` and
`build/foxtrot-smoke/stage-sweep-results.json`.

The US sweep covered ten scenes, with 95–96 samples over five seconds per
scene. All ten live wheel warps loaded, stage generations advanced once per
warp, and director/heap identities stayed stable within each window. No crash
or loading stall was observed. The root heap object (`0x804E9820`) and usable
start (`0x804E98B0`) remained above the mod region end (`0x804E9800`).

| US scene | Initial and minimum sampled free bytes |
|---|---:|
| Bianco 1 | 1,385,480 B |
| Ricco 1 | 1,428,920 B |
| Gelato 1 | 1,347,672 B |
| Pinna 1 beach entrance | 1,417,452 B |
| Sirena 1 / Manta | 1,731,424 B |
| Pianta 1 | 1,788,692 B |
| Noki 1 | 983,832 B |
| Bianco 5 | 789,240 B |
| Pinna 8 beach entrance | 1,463,672 B |
| Sirena Hotel / episode 2 | 4,252,780 B |

Pinna's park and rollercoaster interiors were not included in this sweep.
Heap field arithmetic was verified against retail `JKRSolidHeap::getFreeSize`;
these release-image probes did not invoke heap checks or enable canaries.

The final ghost-panel placement adjustment changes only three vertical-position
instruction operands per regional mod. The reservation, initialized/runtime
sizes, heap layout and hooks are identical to these measured builds.
