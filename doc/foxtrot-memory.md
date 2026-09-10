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
attachment heap or scratch. The 640 KiB BPS disc-file extent is a separate
storage constraint, not the size of the runtime reservation.

Console build `9975EF7F`, measured on 2026-09-10 from the two segments in
`build/susamune_manifest_<region>.json`:

| Region | Initialized bytes | Runtime bytes | Low span free | Upper span free | Total free |
|---|---:|---:|---:|---:|---:|
| JP | 526,272 B | 621,188 B | 1,224 B | 180 B | 1,404 B |
| US | 520,512 B | 607,100 B | 14,512 B | 980 B | 15,492 B |
| PAL | 520,640 B | 607,228 B | 14,384 B | 980 B | 15,364 B |

Add each segment's `memory_size` to measure occupied runtime bytes. The
manifest's top-level `memory_size` is an address extent that includes the
protected hole between segments. It must not be subtracted from the combined
code/data capacity. Space in one span also cannot absorb growth in the other.

The subsequent September 10 refactor moves the 5,920-byte live state-owner
profile into slack inside the existing MEM2 metadata allocation. The linked
result saves **5,952 bytes per region**: 5,920 bytes in the upper span and 32
bytes in the low span. Development-build headroom is now:

| Region | Low span free | Upper span free | Total free |
|---|---:|---:|---:|
| JP | 1,256 B | 6,100 B | 7,356 B |
| US | 14,544 B | 6,900 B | 21,444 B |
| PAL | 14,416 B | 6,900 B | 21,316 B |

The `9975EF7F` tester downloads remain unchanged. This is mod capacity, not
additional game heap. Before/after measurements are retained under
`build/foxtrot-quick-refactor/`.

The game arena reservation remains 768 KiB. Metadata spacing and the two health colours reuse
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
| `0x91300000–0x91700000` | Temporary state save/import staging after Sunshine boot; 4 MiB |
| `0x91780000–0x91800000` | Ghost recording poses, catalog cache and segment table |
| `0x91800000–0x91880000` | Ghost playback poses, primary model heap and segment table |
| `0x91880000–0x91880100` | Existing ghost storage doorbells |
| `0x91880100–0x91890100` | PPC-only local input take |
| `0x91891000–0x918DF000` | Shared codec/CRC workspace; 312 KiB |
| `0x918DF000–0x918EA000` | Split-statistics V9 mailbox |
| `0x918EA000–0x91900000` | Existing secondary ghost model heap |
| `0x91900000–0x9193F000` | Bounded immutable external file-patch handoff |
| `0x9193F000–0x91B3F000` | Extra compressed-state pool bank; 2 MiB |
| `0x91B3F000–0x91C11F00` | Ghost recording inputs |
| `0x91C11F00–0x91C1F000` | PPC-only saved-state metadata, candidate and live owner profile |
| `0x91C1F000–0x91CFF000` | Primary playback inputs |
| `0x91CFF000–0x91E3D000` | Complete ghost file transfer |
| `0x91E3D000–0x91E3F000` | SD state/TAS mailbox |
| `0x91E3F000–0x91EDE000` | Immutable mod file staging |
| `0x91EDE000–0x91F00000` | Existing immutable model asset vault |
| `0x91F00000–0x92EF0000` | Existing savestate payload window |
| `0x92EF0000–0x92F00000` | Existing configuration/runtime block |

External `patch.bin` and per-game `patch.txt` files have a
`0x3F000` (258,048-byte) limit. The handoff fits up to 32,255 patch
records plus its count header. Global `/apps/gc_devo/patch.txt` retains its
existing limit below 1 MiB. Oversized files, invalid binary record counts,
incomplete reads and generated-output overflow cancel boot with a specific
error; patches are never silently truncated or disabled to fit. This limit
does not apply to the bundled `mod_jp.bin`, `mod_us.bin` or `mod_pal.bin`.

The tape requires ghost storage protocol 5; earlier protocol 4 moved file I/O out of the
old transfer payload. It does not require a mounted storage device. The ARM
never reads or writes the tape. The mod staging prefix remains immutable so
reset can inject the same image again. The three compressed states share
17.9375 MiB across the two pool banks. The temporary 4 MiB staging area is not
additional persistent slot capacity. Snapshot version 17 and state/TAS transport
protocol 7 retain exact-build compatibility checks; established settings and
PB wire offsets remain fixed.

The live owner profile occupies metadata offsets `0x7000–0x8720`, after room
for four maximum-sized metadata records. Its Wii address is `0x91C18F00`;
Dolphin uses `0x712D9F00`. It is scalar CPU data, never a restore destination
or ARM mailbox. Existing metadata admission precedes all accesses, and each
use captures a fresh profile. Compile checks bind the size, alignment and
separation from archived records. The MEM2 allocation and pool capacity do
not grow.

Regional console/emulator builds and the launcher/kernel builds pass. Host
checks cover admission failures, metadata/profile separation and retained-byte
filtering. An isolated US Dolphin Bianco restore (`89A27770` development
baseline) used the relocated profile for 136 filtered copies across 15,017,504
bytes. Mario returned to the saved position while the profile, neighbouring
metadata, guard words and slot generation stayed intact; a live controller
field remained fresh. The private adapter supplied archive identity and marked
one real RAM state durable. This verifies the durable restore path, not SD
transport or reboot behaviour. Evidence is in
`build/foxtrot-owner-profile-proof/complete.json`.

The September 10 static audit also identifies 150,080 bytes (146.5625 KiB)
of unassigned gaps within the mapped mod windows, the largest 64 KiB. These
are fragmented gaps, not a free heap or savestate capacity. The profile move
uses already-reserved metadata slack, so it does not consume those gaps.
Codec scratch, file-transfer staging, model heaps, immutable assets, reserved
migration slots and Nintendont/IOS allocations are excluded from this count.

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
