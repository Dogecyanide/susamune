# Additional CPU code placement

The opt-in source linker now covers editor, display and gameplay CPU functions
beyond the original menu cluster. The protected timer, its drawing dependencies
and hot codec stay fixed. These are holes inside the existing reserved MEM1
arena; the game heap floor has not moved.

The latest PAL-only relink, at
`build/timewarp-integrated-checkpoint-8-replay-cold/receipt.json`, reuses all
snapshot-8 objects and moves 28 exclusively owned replay-planner functions.
Their 8,252 bytes avoid new MEM1 allocation; four additional 16-byte incoming
gates cost 64 bytes, recovering **8,188 bytes net**. Usable MEM1 is now
**135,391 bytes (132.22 KiB)**, 4,319 bytes above the target. The largest
remaining interval is 64,996 bytes. Retired baseline ranges are byte-for-byte
identical to checkpoint 8; no new old-code hole is claimed. The shared copy
helper remains in MEM1. The 676-function cold payload is 201,280 bytes and
the V4 package is 480,416 bytes. All 96/9/34 protection checks pass. This was
one relink, with no source compilation or runtime checks.

The initial **PAL-only replay checkpoint**, at
`build/timewarp-integrated-checkpoint-8/receipt.json`, enables shared Store,
heap-gap and Quick replay together. Its 70 fresh source objects pass compile,
link and all 96/9/34 protection checks. It leaves **127,203 MEM1 bytes
(124.22 KiB)**: the added replay integration consumes 10,572 bytes versus
checkpoint 7, putting the 128 KiB target **3,869 bytes short**. The largest
remaining interval is 65,060 bytes; the V4 package is 476,544 bytes. Its cold
payload remains 192,960 bytes. `identity.json` records enabled flags and frozen
metadata hashes. This checkpoint made no runtime or other-region checks.

The newer **PAL-only** integration checkpoint at
`build/timewarp-integrated-checkpoint-7/receipt.json` adds the heap-gap
prototype, capacity diagnostics and `3.0.0 Timewarp` branding. It retains
137,775 usable MEM1 bytes (134.55 KiB), a 65,060-byte largest interval, and
a 470,112-byte V4 package. Its 192,960-byte cold payload includes the current
Guide function. All 96 timer symbols, 9 dependency anchors and 34 hook writes
remain exact. The six-way figures below describe the earlier source capture;
this checkpoint did not repeat the other regions or runtime smoke.

## Wider CPU closure

`build/timewarp-integrated-wide-cpu-3b` uses the same immutable integrated
capture as the editor result below. Beyond the 48 editors, its explicit source
selectors include whole standalone functions from Records, MetadataDisplay,
InputDisplay, ILing, StageLoader and Ghost. This is ordinary CPU code, including
per-frame handlers; it is no longer a claim that every moved function is cold.
Mutable state, GPU input storage, codec loops and all protected dependencies
remain in their existing locations.

| Console region | Free MEM1 bytes | Largest free interval | V4 bytes |
|---|---:|---:|---:|
| JP | 141,012 | 65,044 | 472,288 |
| US | 140,984 | 65,032 | 467,936 |
| PAL | 141,020 | 65,060 | 467,904 |

These totals exceed 128 KiB by at least 9,912 bytes, after the shared Store,
RAM/SD adapters, source ownership, retained hook entries and 166 incoming gates.
They are fragmented usable capacity, not one contiguous 128 KiB allocation.
JP's file leaves 76,576 bytes below the 548,864-byte immutable-prefix ceiling.
The cold CPU image is 192,928 bytes on JP and 192,864 on US/PAL.
All six target/region builds pass in the combined `receipt.json`. Dolphin
free capacity is 145,621 / 145,597 / 145,589 bytes for JP / US / PAL; its V4
files are 452,672 / 447,968 / 448,128 bytes. Console has 648 relocated
functions and Dolphin 632, including the original menu set.

The three next modules contribute 74,056 gross bytes: ILing 19,012,
StageLoader 13,852 and Ghost 41,192. Their addition recovers 72,904 net PAL
bytes over the Records/display step. The earlier Records/display step recovers
30,336 net PAL bytes over the 48-editor build. All selected bodies reconstruct
from current source inputs and relocations; source/region-specific dead
functions are declared explicitly in the target inventory.

StageLoader's local `liveQf` has the same mangled spelling as a protected QFT
local helper. The metadata rewriter keys identity by the owned source input
and analysis address, then verifies name, value and whole-function size.
Matching the name alone is insufficient. The wider link preserves all 96 QFT
symbols, nine dependencies and 34 retail hook writes exactly.

No dynamic short-branch installer exists in these six modules. SplitEvents
callbacks remain excluded: their addresses feed runtime-generated short
branches and need separate retained-entry analysis. The broader CPU closure
has link/relocation/transport evidence only. Its live gameplay, ghost,
playlist and display paths still need focused runtime/Wii performance checks.
The previously passed editor smoke below must not be credited to this larger
set. Source capture 3 also predates later capacity-status/CRC/heap-gap work.

## Integrated source result

The source capture at `build/timewarp-integrated-source-snapshot-3` includes
the shared Store, RAM and SD adapters, transfer lease and Shined label. It
precedes the later capacity-status diagnostic. The six links in
`build/timewarp-integrated-extra-3/receipt.json` use that exact capture:

| Target | JP free bytes | US free bytes | PAL free bytes |
|---|---:|---:|---:|
| Console | 37,764 | 37,752 | 37,780 |
| Dolphin | 50,425 | 50,413 | 50,409 |

Each verifies all 96 timer symbols, nine dependencies, 34 retail hook writes
and retained relocations before producing a checked V4 file. Console JP is
largest at 440,448 bytes. This editor-only checkpoint did not reach 128 KiB.

`pinned_cold_extensions.py` lists seven `CreationEditor` methods (6,340 bytes)
and 41 `CreationExtras` methods (9,564 bytes). Every selected body owns a whole
source input, reconstructs from current compiled bytes and authoritative
relocations, and has audited branches/interior jump tables. The allocator
retires its exact old interval. Incoming far-call gates share the original
menu island; 528 additional gateway bytes and 16 bytes of alignment leave
15,360 bytes net. The first seven methods alone recovered 6,276 bytes; the
41-method extension adds another 9,084 bytes.

The owned PAL Dolphin run at
`build/timewarp-cold-runtime/integrated-extra-3/receipt.json` passes all seven
top-level tabs, three nested Practice pages, slot selectors and RNG toggle,
then edits/cancels native HUD colours, wallkick layout and custom keyboard
text. Each cancellation restores its live value. An ordinary RAM save,
movement and load restores Mario's position, and the cold image stays exact.
This uses the emulator legacy RAM path: it does not validate the console
shared Store, ARM installation, whole-state equality or Wii performance.

The runtime helper has been prepared for a larger CPU image and controller/
metadata editor previews, but that new route has not been run. Images above
128 KiB use private boot staging at `0x81000000`, with an early FST-disjoint
check and full clear before hardware initialization. This is an owned fixture
mechanism, not a shipping allocation. The passed editor receipt retains its
exact earlier runtime script, so it does not claim this new staging route.

## Historical measurements

Before the integrated Store callers, the same 48-function extension leaves
71,828 bytes free on PAL console (`build/timewarp-cold-extra-builds`). The
unextended historical source link leaves 56,468 bytes; do not report either
as today's fully integrated capacity. The original menu-only reference at
`build/timewarp-pinned-link/source-console` recovered 67,556 bytes before
subsequent streaming changes consumed space.

## Bounded private proof

`scripts/timewarp_next_cold.py` moves the seven `CreationEditor` methods from
the current source-linked PAL ELF into an appended immutable cold image.
Their per-function source objects reconstruct the linked instructions exactly;
the proof checks authoritative relocations, external branches and interior
jump-table references. These methods are the menu editor at
`src/creation.cpp:178–599`; shared text/glyph helpers are excluded.

| Quantity | Bytes |
|---|---:|
| Seven editor bodies | 6,340 |
| Seven retained entry veneers | 112 |
| Additional MEM1 holes | 6,228 |
| Existing plus additional holes | 73,784 |
| Appended cold image, including outbound gates/alignment | 6,560 |
| Combined cold image | 78,432 |
| Combined V4 file | 401,984 |
| V4 increase over the reference PAL build | 2,144 |

The old entry veneers remain because the already relocated menu calls those
addresses. The original cold prefix is byte-identical. Editor objects, mutable
style state, strings and renderer inputs stay in MEM1; relocated code calls
the retained drawing primitives. The proof preserves all 96 timer symbols,
nine named dependencies and 34 retail hook writes.

Evidence is in `build/timewarp-next-cold/creation-pal/receipt.json` and
`summary.json`. This earlier private proof retained one gate per old function
entry. It is superseded by the source allocator integration above, which can
use fragmented retired inputs and shares incoming gates. Its older byte
totals must not be added to the production result.

## Historical shortlist and limits

The earlier linked ownership inventory suggested these additional PAL bytes.
These are gross candidate bytes, not net proven recovery; every row still
needs a focused source/relocation audit and a charge for its gates.

| Module | Gross candidate bytes | Main restriction |
|---|---:|---|
| creation.cpp | 7,717 | Only the 6,340-byte editor subset proved; retain shared text helpers |
| creation_extras.cpp | 11,791 | 2,392 bytes in a mixed pragma section; menu editor helpers only |
| remaining menu.cpp | 13,676 | 6,108 mixed; retain timer anchors and rendering primitives |
| ghost_storage.cpp | 7,336 | Separate catalog operations from playback and transfer lifecycle |
| settings.cpp | 6,549 | 496 mixed; retain live settings data and timer dependency |
| records.cpp | 9,475 | Rule tables and unlock/event paths are not cold menu-only data |
| iling.cpp | 4,014 | Menu labels/selection candidates; retain live run tracking |
| layout_profiles.cpp | 2,868 | Profile/edit operations; audit shared draw consumers |
| stage_loader.cpp | 2,764 | Queue/playlist operations; retain stage transition mechanism |
| records_persistence.cpp | 945 | Persisted data ownership and transfer lifecycle need review |
| card_encoding.cpp | 260 | Small CPU-only helper; low total benefit |
| tas_project.cpp | 7,724 | 7,712 mixed, and even the broad candidate set includes hot status |

That older menu-oriented total was 75,119 gross bytes, including 16,708 in mixed sections.
Only 58,411 avoid that section-ownership obstacle before hot-path exclusions or
gateway costs. Added to the current 67,556, that is 125,967 bytes: already
5,105 below 128 KiB. It did not include the wider ordinary CPU handlers now
audited above, and it omitted the subsequent shared-store source cost. It is
not a ceiling on the new layout or a current net-capacity figure.

Concrete exclusions: `TasProject::busy` is queried twice in the frame path
(`src/main.cpp:346,441`). `records.cpp` rule arrays feed live PB/streak checks,
and `categoryFor`/`tierFor` also serve unlock updates (`864,888`). The shared
Creation glyph/text helpers serve ordinary overlays. None should move merely
because the earlier broad inventory grouped them with menu-facing code.

The reference JP V4 file is the largest at 404,384 bytes, leaving 144,480
bytes under the 548,864-byte immutable-prefix ceiling. That is transport
headroom, not a prediction of compression after more code is moved. Each
extension must re-pack and validate all target/region variants. No Wii
throughput or execution claim follows from the PAL private link.
