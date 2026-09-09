# FOXTROT memory audit — September 9, 2026

Baseline: `52c1be8`, packaged build C4AF447B. Values below come from the linked
objects and the preserved C4AF447B release report, before this session's new code.

## What is available

| Region | Mod runtime bytes | Low-span space left | Upper-span space left |
| --- | ---: | ---: | ---: |
| JP | 579,852 | 18,612 | 24,128 |
| US | 578,476 | 19,508 | 24,608 |
| PAL | 578,572 | 19,412 | 24,608 |

These are bytes available **inside the mod reservation**, not free Sunshine
heap. The arena reserve remains `0xC2000`; removing code or static arrays does
not move the game's heap floor. Keep that reserve while additional splits and
achievements are being authored. The codec changes below reclaim padding and
move scratch into an audited MEM2 gap; persistent archive version 1 is unchanged.

The state pool now has **17.9375 MiB** across two banks: a `0xFF0000` primary
pool and an unchanged `0x200000` secondary bank. Its **312 KiB** (`0x4E000`)
codec workspace occupies the former ghost-transfer gap. Older launchers retain
the paired `0xFA2000` primary and high workspace. The four-MiB temporary save/import area is already reclaimed
from inactive IPL/Triforce buffers and cannot simultaneously become persistent
state storage. The mod staging prefix must survive in-session resets; it is
not disposable after the first injection.

## Final linked result (00B63258)

Current values are from `build/release/memory-final.json` after scratch
relocation and the final direct-output decoder changes. The preceding
8118304C build was an intermediate result.

| Region | Mod runtime bytes | Low-span space left | Upper-span space left |
| --- | ---: | ---: | ---: |
| JP | 591,524 | 11,476 | 19,592 |
| US | 590,116 | 12,404 | 20,072 |
| PAL | 590,244 | 12,276 | 20,072 |

The added quick codec, replay checks and faster copies outweigh the duplicate-table
savings: net mod code/data grows by about 11.5 KiB. Game MEM1 heap reservation is
unchanged; this is not a claim of net MEM1 heap recovery. The JP build retains
31,068 bytes across its two code spans. The launcher guide adds about 12.5 KiB in
loader-only read-only data and does not occupy the game heap.

## Implemented: one shared state CRC table

`SusamuneStateCrcUpdate` previously had internal linkage in each C++ caller,
giving `savestate.cpp` and `state_storage.cpp` separate 1,024-byte tables.
It now uses ordinary inline linkage in C++, allowing the partial linker to
retain one table. The ARM C worker keeps its existing local definition.

The actual PPC callers were compiled and partially linked in
`build/foxtrot-memory-audit`; their shared table is exactly 1,024 bytes, versus
2,048 previously. This recovers **1,024 bytes of mod capacity**, without changing
the checksum calculation. Production checksum vector, seed, chunk, archive,
client and kernel tests pass. A new two-translation-unit PPC test checks that
the linked table remains unique.

The codec's unused miniz CRC implementation is also omitted through its existing
`USE_EXTERNAL_MZCRC` option. This removes its separate 1,024-byte table and CRC
routine; state/archive CRCs still use the shared implementation above. These are
mod-image savings, not additional game heap or savestate capacity.

The faster packed-state CRC builds four lookup slices in the first 4 KiB of the
idle codec workspace. It adds no persistent table allocation or reservation.
Each checksum rebuilds the slices after compression; RAM restore checks its
packed bytes before the decoder reuses that workspace. The aligned PowerPC
word-read compiles to `lwbrx`, with byte reads for unaligned prefixes and tails.
Archive header/file CRCs retain their existing byte-compatible calculation.

## Implemented: reclaim 8 KiB of codec padding

The production codec needs 319,296 bytes on PowerPC and 319,360 bytes in the host
tests. Reducing its old `0x50000` reservation to `0x4E000` leaves 192/128 bytes
of checked slack respectively and gives **8,192 bytes directly to the state
pool**. Workspace and bank addresses remain derived from the shared map, with
compile-time bounds checking. The MEM1 reserve and the secondary bank are unchanged.

That intermediate change used transport protocol 3; the relocation below now
uses protocol 4. Archive version 1 stays unchanged. Client/kernel tests derive
their boundaries from compiled constants, exercise cross-bank import and export,
and prove that older workers expose no service.

PPC-only pool edits no longer write the whole pool back to RAM eagerly. Export
flushes the exact selected ranges before publishing its ARM request; import
flushes its staging/tail before handoff and invalidates them only after the
matching receipt. A cache-visibility test uses actual banked slot compaction,
then proves both dirty pieces become visible before the export request while
adjacent bytes remain untouched.

## Implemented: relocate the remaining 312 KiB workspace

The codec and packed-state CRC now share scratch at
`[0x91891000,0x918DF000)` on Wii, or `[0x71111000,0x7115F000)` in Dolphin.
This returns another **319,488 bytes** to the primary pool, for **320 KiB total
capacity recovered** including the preceding padding reduction. A new explicit
kernel capability selects the larger pool and relocated workspace together.
Both savestate and SD client layouts are latched; older/unknown launchers keep
the original pair. Transport protocol 4 prevents mismatched bank addressing.
See [the relocation audit](foxtrot-codec-relocation-audit.md) for complete owners,
reset/cache reasoning, fallback details and verification.

## Further opportunities, requiring separate validation

- **Remaining former ghost-transfer padding:** relocation leaves 3,840 bytes
  before scratch and 45,056 bytes after it. These remain unused; reusing them
  still needs explicit ownership, alignment and fallback checks.
- **Scalar mod data:** the baseline contains a 29,864-byte split-statistics runtime,
  20,616-byte state-slot metadata, a 6,872-byte save candidate, and a 5,920-byte
  live archive owner profile in MEM1. Moving an independently owned scalar
  block to a verified MEM2 gap could return that amount to mod capacity. It
  does not directly enlarge the game heap or state pool. Avoid overlaying the
  live profile with the candidate: both participate in archive validation.
- **Texture arrays:** Mario's colour atlas uses 32,768 bytes and FLUDD's five
  atlases use 20,480 bytes. They are simultaneous live draw resources. Reusing
  one buffer across them is unsafe, and moving them to MEM2 requires GPU/cache
  validation in both Wii and Dolphin's emulated memory aperture. They are not
  a low-risk scalar relocation.

Do not claim the fixed attachment/model heaps' current free space as general
capacity. Their worst-case bounds cover two simultaneous ghosts and held
objects. Shrinking these regions needs new measured worst-case evidence.

The Japanese Task Edition's full game font additionally needs about 1.13 MiB;
its old location overlaps current state storage. See
[RC translation notes](foxtrot-rc-japanese-notes.md) before planning that port.
