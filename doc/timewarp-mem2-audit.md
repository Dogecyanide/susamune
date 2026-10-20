# Timewarp MEM2 reclamation audit

## PR9 staging and DI-tail reclamation

Runtime ABI `0x10002` adds 2,555,904 bytes to the permanent pool without
shrinking ghost recordings or the 3 MiB ISO/RealDI cache. The logical bank
order is:

| PPC range | Bytes | Previous owner |
| --- | ---: | --- |
| `0x91F00000..0x92EF0000` | 16,711,680 | Existing primary state bank |
| `0x9193F000..0x91B3F000` | 2,097,152 | Existing extra state bank |
| `0x9143E000..0x91700000` | 2,891,776 | Existing third bank plus retired staging |
| `0x91CFF000..0x91E3D000` | 1,302,528 | Existing fourth state bank |
| `0x91710000..0x91780000` | 458,752 | DI scratch tail |

Total capacity is 23,461,888 bytes. The shared transfer window becomes
`0x91300000..0x9143E000` (1,302,528 bytes), retaining the complete maximum
legacy ghost file. Its final 319,488 bytes remain the exclusive import/replay
plan workspace; candidate staging is now 983,040 bytes. Both physical input
banks, ten-minute V6 recordings and legacy ghost limits are unchanged.

The ARM coordinator retires both file workers, then requests the one-way
64 KiB scratch limit through the DI consumer's own queue. Earlier reads,
their copies and patching finish before the consumer changes the limit and
cleans/invalidates the tail. A delayed guest completion or failed reservation
leaves the new map unpublished. The coordinator cleans/invalidates the retired
staging and ghost-payload ranges before READY. PPC invalidates all three
reclaimed banks once after receiving that exact ABI/epoch's READY; later
independent map adopters never invalidate occupied state bytes.

Reset keeps the scratch limit narrow. Existing PPC parking, DI drain and file
worker retirement precede the new epoch, and that epoch negotiates again before
using any reclaimed bank. Unknown/older shared ABIs cannot select this layout.
No in-session rollback returns the tail to a wide DI reader.

The private PPC receipt
`build/timewarp-pr9-acceleration8-stage-tail-1/receipt.json` validates this exact
five-bank geometry, smaller staging and acceleration 8 against Pinna, mixed
levels and the known-tight set, including a changed overwrite. The tight set
retains 291,552 bytes of free pool. This establishes capacity and processor
behavior in the fixture; it does not establish Wii elapsed times or disc-read
throughput with the smaller scratch.

An unimplemented fallback is to permanently retire the 3 MiB ISO cache on
supported Sunshine ISO boots with memory-card emulation disabled. That would
use the existing bounded uncached read path, require DI-consumer fencing and a
reset-persistent cache-disable latch, and exclude physical-disc DMA, Triforce,
AGB and unproved VC paths. It would trade disc-read performance for capacity;
the PR9 map above retains the cache instead.

## Follow-up after Wii State Test 3

The user confirmed all three Pinna 3 loads at 0.267 s on Wii, with saves at
0.500/0.534/0.567 s. Later mixed-level slot-3 cases measured Bianco 5 at
0.800/0.300 s and Noki 1 at 0.934/0.300 s (save/load); the user explicitly
deferred those smaller differences. Test 3 stays frozen. None of the candidate
bytes below is included in that build's 20,905,984-byte pool.

### Upper MEM2 candidate: conditional 1.875 MiB

The strongest new candidate is `0x93400000..0x935E0000` (1,966,080 bytes).
Dolphin's [retail-derived IOS memory table](https://raw.githubusercontent.com/dolphin-emu/dolphin/master/Source/Core/Core/IOS/VersionInfo.cpp)
places IOS58's application boundary at the latter address. The linked launcher
uses libogc 1.8.23 with Arena2Hi `0x933E0000` and PPC IPC at
`0x933E0000..0x93400000`; USB storage also carves 18 KiB below its arena ceiling.
Preserve those owners. The wider `0x93300000..0x935E0000` is not one free range.

`SYS_GetArena2Hi` reads cached launcher state. `__IPC_Reinitialize` resets IPC
queues but does not refresh those arena values after IOS reload. Before granting
anything, a separate read-only Wii receipt must capture fresh uncached IOS
boundary words at low-memory offsets `0x3120/24/28`, `0x3130/34`, `0x3140`,
`0x3148/4C`, plus the libogc arena/IPC getters, exact IOS revision and platform,
after reload and before GameCube boot overwrites low MEM1.

ARM `malloc/malloca` use IOS heap 0; its implementation is absent locally.
Nintendont runs as an IOS thread with USB/HID/FS/network modules still resident.
An allocation-address ledger can corroborate the arena contract but cannot
prove every module's future allocations. Reject unknown or reduced boundaries;
initially exclude vWii/VC. A later capability-gated reservation pilot would need
explicit ownership, reset/reload retirement and hardware verification. Zero
bytes are credited until then.

### Temporary candidate storage

The hardest measured overwrite has a 2,880,832-byte staging shortage. With no
emulated memory cards, the ISO cache contains 3,145,728 bytes and could cover
that shortage numerically. It shares a prefix with optional card images and is
entirely RealDI DMA storage in physical-disc mode, so only an explicitly fenced
ISO-cache suffix is a candidate. The PPC CODEC lease does not retire ARM cache
readers. A loan needs a DI-consumer fence, cache-entry invalidation, scratch-only
reads while loaned, coherent return on all paths, and no committed state pointing
into borrowed storage. It may cause slower disc reads after a save.

The already-inspected stage-heap gap could also hold temporary candidate blocks:
787,800 bytes in the measured Bianco 5 replacement, up to 2,034,088 in Pinna 3.
This requires continuous CPU/DMA quiescence, inward-aligned bounds, preserved
headers/children, and a source reader that skips the canonical-zero interval
instead of reading then masking it. Current alias guards reject this borrowing.
The previous heap-gap pilot did not prove writing scratch into the live gap.

The replay plan itself uses 158,432 of its 319,488-byte reservation, leaving
161,056 bytes potentially available after explicit partitioning. This is a
smaller ownership change but cannot close the measured shortage alone.

A 1.875 MiB permanent bank would reduce the measured shortage arithmetically to
914,752 bytes. Adding the separate 458,752-byte DI tail leaves 456,000 bytes;
Bianco's heap gap could cover that remainder in gross arithmetic. Exact block
placement, alignment and bookkeeping remain unproved; a bank edge can waste
roughly one 128 KiB encoded block. Permanent capacity also helps final occupancy,
whereas cache/heap loans only reduce temporary re-encoding.

## Original audit

Read-only source/ELF audit, 2026-10-08, release `703b33d`. No production,
timer, linker, or shared-map changes were made. Budgets below are conditional
gross savings; none is an integrated capacity increase. The existing proposed
2 MiB shared state/ghost transaction-window saving is excluded.

Evidence: `build/timewarp-mem2-audit/receipt.json` records section addresses,
selected symbol sizes, input paths and SHA-256 hashes. The kernel ELF inspected
is the retained release build under
`C:/Users/Dogec/.codex/worktrees/4e33/susamune/build/launcher/group-arm/kernel/`;
its SHA-256 is
`8db10fbf7b15f67e7c170d2d5acea9066f22d78ea1ddfa02b53a7a2320d11aef`.
The loader ELF is the sibling `group-wii/loader/loader.elf`.

The subsequent local compressed-transport/DI-policy build consumes 12,544
additional ARM text bytes and 32 additional rodata bytes; data/BSS sizes are
unchanged. Its kernel SHA-256 is
`98cdf7380ff81e9958631696be524cabdbe95cd73add78fe8a691652867daf92`.
Thus the baseline code/data-hole estimate below is already reduced by 12,576
bytes before lease integration. None of those holes is advertised to the PPC.

## Ranked candidates

| Candidate | Gross bytes | Principal condition |
| --- | ---: | --- |
| DI scratch: 512 KiB to 64 KiB | 458,752 | Validate all bounded reads and measure FST/uncached SD/USB throughput |
| Retain actual file-patch prefix | 0–258,016 | Publish immutable, checked per-boot extent and preserve it through reset |
| Explicit kernel code/data holes | 124,544 | Linker-owned ranges, new runtime range advertisement, cache ownership |
| Stream split-stat journal; retire boot-only copies | 46,344 | Preserve pending request ownership across reset; move boot migration scratch |
| Explicit unused kernel stack-region tail | 48,128 | Preserve all seven stack extents and boot/reload contracts |
| Shadow BMD: copy mutable structures only | Less than 65,536 | Prove J3D aliases and GPU lifetime; charge replacement structures |

The first four total at most 887,656 bytes, before metadata, alignment, code
growth and safety margin. The optional stack-region tail raises that gross
ceiling to 935,784 bytes. These are not minimum available capacity: a full
file-patch prefix saves zero, and release kernel growth reduces linker holes.

## 1. DI scratch is already consumed in bounded pieces

`include/susamune/mem2_map.h:27–29` reserves
`0x11700000..0x11780000` (PPC `0x91700000..0x91780000`).
`launcher/kernel/DI.c:74–75` derives `DI_READ_BUFFER` and its length from that
map. A retained 64 KiB prefix frees `0x91710000..0x91780000`.

All direct consumers found:

* `FST.c:172–203`: caps each request to the scratch length before reading.
  Its cached-file path rounds the capped length up to 32 bytes; retain an
  aligned capacity and test the final 31 lengths below the boundary.
* `ISO.c:503–516`: uncached requests and requests larger than the separate
  3 MiB ISO cache use bounded scratch. Cache hits/misses that fit that cache
  remain in its own range. `ISOReadDirect` handles partial CISO blocks at
  `ISO.c:123–260`; the 2 MiB CISO block size does not require a 2 MiB scratch.
* `DI.c:894–920`: loops returned pieces, copies each to the final request
  destination, then invokes `DoPatches` once on the complete original request,
  flushes it and acknowledges completion. Reducing chunks does not itself
  split the patcher's input.
* `DI.c:882–887`: synchronous one-sector USB keepalive. Its device sector
  size must be bounded by the retained capacity.
* `Patch.c:2322–2341`: hashes a copied DSP microcode candidate. The largest
  entry in `DspMatches` (`Patch.c:208–229`) is `0x1F20` bytes. The documented
  Sunshine candidate is `0x1CE0`. This is runtime scratch; games can load
  DSP code more than once.

The real-disc DMA buffer is independent: `RealDI.c:40–43,184–290` retains
the complete 3 MiB front/drive/tail-cache reservation. Its read worker waits
for DMA completion before handing a piece back to the DI copy loop. Do not
reduce or alias that buffer as part of this candidate.

Required experiment: compare 512/64 KiB with FST, cache-disabled ISO,
cache-hit/prefix-hit ISO, requests larger than 3 MiB, CISO partial/full-block
boundaries and short/zero reads. Preserve full-request patch and acknowledgement
ordering. Check sector and 32-byte boundary canaries. Console read throughput
is unresolved; retaining features does not imply identical read latency.
The feasibility agent has the exact source paths for this experiment.

Permanent pool adoption needs a new shared map and explicit kernel capability
or advertised range list. The PPC must not claim this tail under an old kernel
that still uses the full 512 KiB. The retained scratch remains exclusively
ARM/DI-owned, so no scratch/pool runtime lease is necessary.

## 2. Retain the used file-patch extent, not its maximum

`mem2_map.h:49–51` reserves `0x3F000` bytes at `0x91900000`.
`loader/source/main.c:809–902` finishes parsing and validating the patch
count before handoff. The runtime kernel consumes exactly the count-prefixed
records in `Patch.c:3905–3933`; a conditional consumes two ordinary eight-byte
entries. It never needs binary file trailing bytes.

Keep `align32(4 + count * 8)` immutable and lend only the aligned tail to the
pool. Zero patches require one 32-byte cache line, giving 258,016 bytes.
The tail can adjoin the existing extra pool bank at `0x9193F000`, avoiding
another physical fragmentation boundary. Preserve the full current patch
capacity; a maximal patch set simply leaves no tail.

The kernel must independently bound the count, latch the retained extent at
boot, and advertise that exact range. `PatchGame` reuses this prefix after
an in-session reset; neither count nor records may subsequently be overwritten.
New launcher handoff must complete every producer before advertisement.
The old Sonic Mega Collection producer is loader-only and its call is
commented out (`main.c:2294–2298`); do not revive it after finalizing the extent.
Reboot/return-to-loader may overwrite the range only after retiring all pool
owners. This is variable capacity, not a new hard guaranteed budget.

## 3. Actual kernel holes, not an assumed free high MEM2 area

The inspected kernel ELF has:

| Section | Physical start | Size |
| --- | --- | ---: |
| `.text` | `0x12F00000` | `0x4E4C0` |
| `.rodata` | `0x12F60000` | `0xC34C` |
| `.data` | `0x12F6C34C` | `0x3F18` |
| `.bss` | `0x12F70264` | `0x6325C` |

`kernel/kernel.ld` leaves two explicit holes:
`0x12F4E4C0..0x12F60000` (72,512 bytes) and
`0x12FD34C0..0x12FE0000` (52,032 bytes). Either reserve them with linker
symbols/assertions, or relink code/data adjacently to consolidate the holes.
Do not freeze release section sizes into runtime constants without build
checks. Small separate banks cannot hold every worst-case 128 KiB Quick
block; they can hold smaller encoded blocks or charged metadata.

All declared thread stacks occupy `0x12FE0000..0x12FE4400`: main 8 KiB,
DI 4 KiB, then five 1 KiB stacks for RealDI, HID read/change, Bluetooth
interrupt/bulk. Consumers are `main.c:384`, `RealDI.c:86`, `HID.c:111,117`,
and `lwbt/physbusif.c:364,369`. The linker reserves through `0x12FF0000`,
leaving an additional 48,128-byte tail; reserve it explicitly before use.
Do not shrink any live stack.

Boot is a distinct ownership phase. The loader decompresses the kernel into
its `0xE0000` image aperture (`loader/source/main.c:1705–1715`), then writes
kernelboot at `0x92FFFE00` and handoff words at `0x92FFFFC0/E0`.
`kernelboot/main.c:34` supplies an initial stack inside `0x12FA6000..8000`;
`kernel/start.s:15` immediately selects the linked main stack. Kernel BSS is
zeroed by `main.c:165`. Publish pool ranges only after kernel initialization;
retire them before a fresh kernel boot. The bootstrap/handoff locations are
excluded from the candidate.

The loader ELF itself is entirely in MEM1. `MALLOC_MEM2 = 0` in its
`main.c:1043` forbids its ordinary heap from consuming MEM2. Discarding its
MEM1 code or assets therefore adds no MEM2 savings.

## 4. ARM split-stat file copies

The baseline ELF contains `SplitStatsFileScratch` = 42,432 bytes and
`SplitStatsV1Selected`/`SplitStatsV2Selected` = 792/3,120 bytes.
The selected legacy copies are only used during migration in
`SusamuneCfg.c:4085–4175`, before PPC release (`main.c:395`). Their boot
workspace can come from an explicitly retired boot buffer, preserving all
legacy formats.

The large scratch is also used at runtime: `WriteSplitStatsFile` at
`SusamuneCfg.c:4571–4630` makes a full file copy and writes it. A bounded
header/trailer plus reads from the stable mailbox payload can produce the
same file and checksum (`SplitStatsChecksum:4279`) without a duplicate
42 KiB payload. Keep journal generation/publication after sync and close.
Charge the small replacement header/checksum workspace.

Normal PPC ownership is suitable: `split_stats.cpp:509–527` keeps the
request immutable until matching acknowledgement, even after timeout.
However, `SplitStats::init:533–566` reads `saveSeq` without adopting an
outstanding `saveSeq != ackSeq`. Direct ARM streaming must first fix the
reset adoption/drain contract, so a new PPC session cannot overwrite payload
still being read. Alternatively, put the entire operation under the proposed
common transaction-window lease. ARM journal priority over ghost/state in
`kernel/main.c:530–552` does not establish buffer exclusivity.

Removing these symbols does not automatically enlarge the state pool:
relink and advertise the enlarged kernel hole before charging it as capacity.

## 5. Shadow asset duplicate needs pointer and GPU proof

The immutable vault is 139,264 bytes and is mostly occupied; its actual
asset envelopes total 136,928 bytes. Shadow has a second 64 KiB working
allocation in the recording-bank tail: `ghost_model.cpp:292–308` copies the
BMD there before model construction and texture replacement at `:866`.
Pianta already reads its immutable master directly (`:316–322`). Its old
boot staging area is reused by the primary model heap, so that staging is
not an additional saving.

A possible rewrite loads Shadow geometry from the immutable master and
copies only structures mutated by `gpScreenTexture->replace` and J3D.
This has a 65,536-byte ceiling, less replacement allocations. It requires
exact J3D load-flag/texture-header alias proof; the display lists and GPU
can retain references into BMD storage after the load call returns.
Do not lend either working storage or master merely because construction
finished. Reuse requires the existing model quiescence/GX completion barrier.
Compression of the master alone does not remove the need for live decoded
geometry; no unmeasured compression saving is credited.

## Exclusions and remaining blockers

* SegaBoot/DIMM/IPL `0x91300000..0x91700000`, loader real-disc
  `0x91780000..0x91900000`, and boot MP3 `0x91F00000..0x92300000` are already
  overlaid by state staging, ghost runtime and the primary pool respectively.
  Removing Triforce paths does not reclaim these bytes a second time.
* ARAM `0x90000000..0x91000000` is the game's live audio/resource DMA backing.
  There is no verified all-region high-water/lifetime proof here. Keep it.
* The 3 MiB disc cache is live ISO cache or RealDI DMA storage. Shrinking it
  trades cache/read performance; it is not a dead duplicate of DI scratch.
* Audio stream buffers at `0x93280000` and `0x9328C400` are read by the PPC
  DSP handler while ARM fills them (`Stream.c:53,152–216`,
  `asm/__DSPHandler.S:21–84`). `StreamInit` writes both even at boot. No proof
  was found that every supported SMS path/reset can never issue streaming
  commands, so this audit grants zero bytes there.
* `0x931C0040` is live AR DMA bookkeeping (`ARStartDMA_Hook.S`,
  `__ARHandler.S`, and `Patch.c:4423`), despite nearby PSO-only addresses.
  Do not reclaim the entire apparent PSO window. `dolPatchBuf` and
  `SHARED_PTR` have no active references beyond declarations, but that is
  not an IOS ownership proof for the surrounding high memory.
* The high region is outside the audited kernel ELF. Kernel allocations use
  IOS heap 0 (`alloc.c:8,18`), and the loader patches IOS memory above
  `0x939F0000`. A sparse repository address search does not prove free RAM.
  No multi-megabyte high-MEM2 claim is made without IOS heap/module maps.
* Bluetooth remains supported. Its `memb_mem_pool_pbufs` = 205,440 bytes
  and `ram_block` = 65,552 bytes are live queues/heap, not idle boot storage.
  Removing unrelated game patches may reduce kernel code, but a measured
  SMS-only build and supported-controller/reset contract are needed first.
* Ghost sample/input banks must still support legacy maxima: 26,974 pose
  samples and 54,000 input frames. Current V6 recordings are smaller in
  pose count, but that does not make the legacy tails permanently free.
  Both model heaps, catalog, metadata and live presentation tails also have
  owners. Timer/presentation storage is outside this task's writable scope.
* Codec workspace is 319,296 bytes in the PPC receipt versus 319,488
  reserved: only 192 bytes of pure padding. Quick and legacy Deflate share
  the same maximum workspace; repack needs a second workspace inside the
  transaction staging range. The 64 KiB local tape is live and may grow.
  Lending either to retained states requires a recoverable capacity protocol,
  not a check that the current cursor is small.
* Compressed boot transport is a separate measured opportunity
  (`build/timewarp-transport-measure/receipt.json`, gross 154–156 KiB).
  Reset still needs its immutable source. That saving is not repeated in
  this audit, and neither decoder nor release-format integration is implied.
