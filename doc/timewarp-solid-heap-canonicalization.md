# Solid-heap free interval: safety audit

This audit covers replacing **only the saved representation** of
`[JKRSolidHeap::mCurStart, JKRSolidHeap::mCurEnd)` with zero bytes. Capture must
not write to the live heap. Restore still restores the full original heap
extent and its allocator header, with zeros in that interval.

The allocator supports this interpretation of the interval: it contains no
currently allocated head or tail block. The remaining uncertainty is game
code that reads old, uninitialized contents after a later allocation, or an
incorrectly retained pointer to a freed temporary. The reviewed sources do
not establish that neither can ever occur. This is a targeted optimization
with a runtime validation gate, not a proof of all future game behavior.

## Allocator evidence

Source of truth examined:
`C:/Users/Dogec/susamune/.agents/sms/src/JSystem/JKernel/JKRSolidHeap.cpp`
and the corresponding `JKRSolidHeap.hpp`, `JKRHeap.cpp/.hpp`, and
`JKRDisposer.cpp`.

* `create` reserves a parent-heap allocation containing the entire solid
  heap; its header precedes `mStart` (lines 5–20).
* The constructor sets `mFreeSize = mSize`, `mCurStart = mStart`,
  `mCurEnd = mEnd`, and the saved-state list at offset `0x74` to null
  (lines 22–29).
* `allocFromHead` rounds size/alignment and advances the head cursor by the
  complete charged extent. `allocFromTail` similarly retreats the tail.
  Both reduce `mFreeSize`, and neither initializes the returned bytes
  (lines 52–93). Alignment padding already charged to an allocation lies
  outside the proposed interval and must remain unchanged.
* `free(void*)` does not free individual blocks (lines 96–99). Therefore
  the proposed optimization does not need to infer holes between objects.
* `freeTail` first disposes tail objects, then moves the tail cursor back
  to `mEnd` and adjusts free size (lines 112–123). `freeAll` disposes all
  registered objects before resetting both cursors (lines 101–109).
* `check` verifies the same accounting identity proposed for admission:
  `mFreeSize + (mCurStart-mStart) + (mEnd-mCurEnd) == mSize`
  (lines 139–153).

The local retail revision-0 JP, US, and PAL DOLs were read without launching
the game or touching SD. Decoding their allocator field loads/stores confirms
the same layout in all three: `mStart=0x30`, `mEnd=0x34`, `mSize=0x38`,
`mFreeSize=0x68`, `mCurStart=0x6c`, `mCurEnd=0x70`, saved-state list `0x74`.
The constructor, both allocation directions, both bulk-free operations, and
`getFreeSize` were checked. Function addresses, instructions and DOL hashes
are in `build/timewarp-crc-pilot/heap-audit/receipt.json`. This is focused
instruction decoding, not a complete retail disassembly audit.

All three retail maps mark `JKRSolidHeap::recordState` and `restoreState`
as `UNUSED`; their rewind-list producer is not linked into these revisions.
`JKRHeap::TState` is different: it records used size and a checksum of the
two cursors, rather than saving free-area contents. The state list/header
must still be preserved. A non-null `0x74` at runtime is a reason to retain
the full bytes until explained.

## Children, disposers and asynchronous work

`JKRHeap` stores its mutex, child-tree links and disposer list in the header,
outside the free interval. An ordinary child heap created through
`JKRSolidHeap::create(size,parent)` or `JKRExpHeap::create(size,parent)` first
allocates its whole backing block from the parent. That block therefore
lies in a charged head/tail extent, including the child's own unused bytes.
Do not recursively zero free space in child heaps.

The explicit-buffer `JKRExpHeap::create(ptr,size,parent)` overload depends
on the caller supplying owned storage; it does not reserve it from the
parent. The mod's ghost model heaps use separately reserved buffers and
attach to the root heap (`src/ghost_model.cpp:1301`). They do not authorize
discarding any portion of the stage heap. A diagnostic child-tree walk
should flag any child extent overlapping the proposed interval, if such a
heap is encountered.

`JKRDisposer` registers each live object with its containing heap; bulk-free
operations unlink/dispose them before making their bytes free. No disposer
nodes or objects in the live head/tail ranges may be changed. A freed
object's stale bytes can remain in the free interval, but a later legal
allocation may overwrite them already.

`TMarDirector::direct` joins `gSetupThread`, calls `setupObjects`, and only
then sets `_260 = 1` (`System/MarDirectorDirect.cpp:46–56`). Existing
`inLoadTransition` rejects `_260 == 0` and the initial intro states.
`setupObjects` finishes its temporary-tail cleanup before returning
(`MarDirectorSetupObjects.cpp:342,480`); particle loading also frees its
temporary tail (`MarDirectorLoadResource.cpp:244`). Thus the existing
readiness gate excludes this known asynchronous setup allocator.

Capture already waits for `GXDrawDone` and disables interrupts before
building the capture spans (`src/savestate.cpp:1779–1785`). Read the heap
header and construct the zero interval inside that same protected period;
an earlier measurement is not sufficient. Disabling interrupts prevents a
new PPC scheduling event, but does not prove another thread was not already
suspended while holding the heap mutex. For a conservative admission check,
require an idle mutex owner/count and fall back to the full snapshot when
the heap is busy. Do not wait for a mutex with interrupts disabled.

## Remaining behavior risk

The solid allocator does not zero or poison allocations. Its error path
reports allocation failure; it does not fill free storage. `fillFreeArea`
has only a declaration in the examined decomp and no named retail-map
entry, so this audit does not rely on a debug-fill invariant.

Many apparent spawn operations use objects created during setup. For
example, `TItemManager::loadAfter` preallocates coins, and the reviewed eel,
Manta and fish allocation sites run in constructors/load/init. That is
useful evidence, but not an exhaustive proof that no later allocation or
uninitialized read exists. The decomp has incomplete functions.

On stage exit, `TApplication::proc` frees the stage heap (Application.cpp:567)
without clearing its backing memory. Canonicalizing a save can consequently
change stale bytes seen by allocations in a later stage, even though every
live object at capture was preserved. This is why gameplay and stage-exit
validation add evidence that a codec byte-roundtrip alone cannot provide.

## Admission and focused runtime gate

Before substituting the interval, require the expected solid-heap type,
stable stage ownership, and non-overflowing bounds:
`heap header <= mStart <= mCurStart <= mCurEnd <= mEnd`,
`mSize == mEnd-mStart`, `mFreeSize == mCurEnd-mCurStart`, and the captured
region must contain the complete header and heap extent. Rejecting this
optimization should retain ordinary full-byte capture. No guessed maximum
shine address or rounded-down allocated boundary belongs in this decision.

The focused runtime and encoder checks cover:

1. A real head allocation and negative-alignment tail allocation both
   survive save/restore exactly; the saved allocator header, cursors,
   alignment padding, and all bytes outside the exact free interval match.
2. Capture and a failed/cancelled save leave the live interval untouched;
   restore zeros precisely the saved free interval, including unaligned
   endpoints and compressed-block boundaries.
3. A subsequent real head/tail allocation follows the restored cursors and
   stays usable, then representative gameplay, restart and a stage change
   work. Bianco 5, Noki 1, and Pinna 3 remain useful later console cases.

These are new lifetime questions. Existing archive ownership, cancellation,
CRC and old-root preservation suites need not be repeated merely to answer
this source audit.

## Measured result and prototype status

`build/timewarp-heap-gap-measure/receipt.json` records actual PPC Quick
encoding of 15 metadata-backed captured states with only the checked gap
canonicalized. Across the five three-state sets, physical pool savings are
219,904–657,280 bytes (about 215–642 KiB). This is compressed storage saved,
not an additional MEM1 reservation or the full raw 0.75–1.94 MiB interval.
The source capture files remain unchanged.

The previously failing Bianco 1 / Noki 1 / Gelato 1 combination now uses
20,566,912 of 20,905,984 bytes, leaving 339,072 bytes. All 2,184 ordered
triples of the 14 distinct canonical captures fit. However, 36 of 84
replacement probes still require more temporary space while retaining the
old root, despite fitting final roots. The largest measured staging deficit
is 2,880,832 bytes. Long recording and TAS payloads remain a separate
capacity limit; see `build/timewarp-capacity-canonical-summary-1/report.txt`.
These results do not establish three always-fast slots.

`build/timewarp-heap-gap-runtime-2/receipt.json` records one owned historical
PAL Dolphin pilot. Retail allocations of 4 KiB at both the head and tail
were filled with distinct canaries before capture. A private saved stream
was changed to contain zeros only in its free interval, with fresh checksums;
the live free bytes were unchanged until the real D-right load. Three loads
restored both canaries, Mario's position, all allocator cursor fields, and
the entire zeroed free interval. Loads also rewound later head/tail
allocations and a `freeTail` call. Subsequent input, Bianco 5 stage setup and
Noki 1 stage setup completed, with valid heap accounting. The owned process
was stopped. This used a Deflate stream to isolate restore semantics; it is
not a shared-store, production-encoder, exhaustive determinism or Wii proof.

The optional `TIMEWARP_HEAP_GAP` prototype is now wired into both legacy and
shared RAM capture paths, including Quick, Deflate and repeated candidate
compression. It is **off by default**. `StateHeapGap::inspect` runs inside the
existing interrupts-off capture window, requires the exact regional solid
heap vtable, idle mutex/queue, null rewind list, matching heap bounds and
accounting, and a bounded consistent child list. Every child header and data
extent must avoid the proposed interval. Any failed check preserves the
ordinary full-byte snapshot.

The codec receives one logical `ZeroRange` by value. Quick substitutes bytes
only in the existing scratch block; Deflate feeds a small constant zero
buffer. Neither mutates the live input, changes workspace reservations, nor
changes the archive format. The zero range remains fixed across a save's
measurement, fallback and commit passes. New focused tests cover codec
boundaries/source immutability and heap admission, including the six real
child heaps in each captured stage. Broad regression repeats are deferred
at the user's request.

The single PAL console integration checkpoint passed with both the shared
store and heap-gap flags enabled: `build/timewarp-integrated-checkpoint-7/receipt.json`.
It includes the 3.0.0 Timewarp branding and expanded cold-code placement,
leaves 137,775 bytes of MEM1 capacity free across the available intervals,
and preserves all 96 protected timer symbols, nine dependency anchors and
34 retail hook writes exactly. The packed mod is 470,112 bytes. This proves
compilation, linking and the protected layout; integrated game execution and
Wii behavior remain gates before enabling the heap optimization by default.

## Additional omission audit

The 15 captured heap trees contain six child solid heaps and no grandchildren.
Captured JPA manager pointers identify the children as particle, emitter and
field pools; their backing lies in the allocated parent head. Their actual
free intervals total only 24 bytes (40 in Noki 1), so additional child-gap
machinery would not produce useful savings. Inactive particle objects remain
allocated and retain pool links and state.

The live THP allocation is already protected from restore, but omitting its
saved bytes needs a separate saved/current lifetime contract. StoredState does
not currently record that saved interval, and the owner profile does not anchor
ActivePlayer. These captures omit ActivePlayer and cannot establish its saved
range or savings. Keep this separate from the checked allocator gap; no THP
omission is implemented.
