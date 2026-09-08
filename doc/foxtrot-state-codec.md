# Compressed state codec and staging audit

This describes the current three-slot RAM codec, the SD restore paths that use it,
and their temporary-memory ownership. The archive format and file worker are
covered in [SD savestates](foxtrot-sd-states.md).

## Codec contract and compression modes

`include/susamune/state_codec.hxx` accepts up to 64 input/output spans. The caller
owns the aligned workspace and all buffers. The freestanding miniz configuration
uses no heap, file APIs, or unaligned native word loads. Its workspace remains
319,360 bytes on the host and 319,296 bytes on PowerPC, within the fixed 0x50000
allocation, including the inflater's 32 KiB dictionary. CMake builds this source
with `-O2` in the upper mod code span; other sources retain their own flags.

The default producer uses one-probe greedy parsing and miniz's fast match loop.
`MINIZ_PORTABLE_FAST_DEFLATE` makes that loop available on big-endian PowerPC by
using byte-safe little-endian reads. Its hash uses all 15 bits of the existing
32,768-entry array, rather than restricting the fast loop to 4,096 entries. That
array was already part of the workspace: this change adds no memory reservation.
Dictionary handling, match bounds and the zlib stream contract remain shared
with the checked codec.

The `compact` producer retains eight-probe lazy parsing. Save first tries the
fast producer. If the complete result cannot fit even after reclaiming the
selected slot, it retries with the compact producer before refusing the save.
The compact retry may take longer, but can retain a state the faster producer
would not fit. The selected mode is reused for any subsequent recompression.

Compression concatenates the actual static/root/stage and used ghost-prefix
spans into one zlib stream without first copying the full raw snapshot. Output
spans are capacities: the save path supplies the 4 MiB transient area and up to
two free pool-bank spans. Once capacity is exhausted, the sink keeps counting
while discarding overflow. `OUTPUT_FULL` therefore includes the complete required
size; the partial candidate is never a retained state.

The replacement planner distinguishes a fully staged commit from a replacement
that fits only after reclaiming its old slot. For the latter, the complete first
pass proves the final size before reclamation. With source spans still immutable
and interrupts still disabled, the same producer recompresses directly into the
pool. Raw length, packed length and Adler-32 must match the measured result; a
broken invariant traps rather than resuming with lost state. A normal capacity
refusal preserves all prior slots and sidecars. No slot is evicted automatically.

## Restore validation and the RAM checksum cache

All entry points validate source/destination bounds, span counts, exact output
capacity, and source/workspace/descriptor overlap before writing. Their stream
ownership differs:

| Path | Admission before game writes | Restore pass |
|---|---|---|
| Local RAM state | Produced by this codec; compiled metadata/ranges and current packed CRC rechecked | One writing inflate through `decompressVerified` |
| SD file imported into RAM | ARM verifies file CRCs; PPC fully validates the stream before committing the slot; subsequent RAM loads recheck its cached CRC and live owner profile | One writing inflate on later RAM loads |
| SD file selected directly for Load | File checks and metadata/owner admission, then full stream validation while staged bytes remain owned | `decompress`: validation inflate followed by writing inflate |

`sPackedChecksums[3]` lives only in mod-owned RAM, outside `StoredState`, the game
snapshot and every archive. A successful local save records a CRC over the exact
committed packed bytes. A successful import records the receipt-verified payload
CRC only after complete zlib validation and slot commit. Initialization/clear
invalidate the corresponding local entries. A file cannot supply a trusted-cache
flag or use its own checksum to opt into the fast restore path.

Immediately before a RAM restore, under the save/load mutation guard, with GX
finished, interrupts disabled and audio DMA muted, `packedChecksum` rereads the
selected slot across its physical banks. A mismatch is refused before any restore
writes. Matching bytes may use `decompressVerified` because their producer or
full import validation has already established stream validity. This CRC is a
local integrity check, not cryptographic authentication of arbitrary files.
Metadata tags, slot identity/generation, compiled destination spans, scenario
checks and durable-owner checks remain independent requirements.

`validate` inflates into a wrapping dictionary, verifies the zlib checksum and
expected Adler-32, and requires exact compressed consumption and decoded length.
`decompress` runs that pass before its scatter-writing pass. `decompressVerified`
omits only the redundant first inflate; its writing pass still verifies the
stream's end, length and checksum. Any failure after writing may have begun is
`COMMIT_FAILED`, and the caller traps. It must not turn such a failure into a
recoverable refusal and resume gameplay.

Source bytes and descriptors remain immutable, and the workspace exclusively
owned, for the entire operation. An optional retained-owner copy callback is
preflighted by the caller, runs only during commit writes, and cannot fail or
change source/workspace/descriptors. Imported and direct SD states use this
filter so old runtime-owner bytes are never written temporarily and repaired
later.

After a successful restore, game spans use `DCStoreRange` for GPU/DMA visibility.
The PPC retains its populated data cache rather than invalidating the whole
restored heap and immediately refetching it. No executable text is restored.

## Validation and measured scope

`scripts/test_state_codec.py` exercises production fast and compact paths with
short inputs, dictionary wrapping, scattered boundaries, exact-full and overflow
capacities, malformed/truncated/appended streams, checksum/length failures,
copy filtering and overlap rejection. The private retail capture is checked
against an independent Python zlib decode and byte-exact roundtrip. The slot,
queue, archive and recompression tests cover the RAM trust cache, capacity
fallback, pinned selections and preservation of other states.

The bounded US Bianco fixture in Dolphin 2606a JIT measured:

| Version | Save | RAM Load |
|---|---:|---:|
| Prior release `5B0EC1B1` | 4.063 s | 1.343 s |
| Fast producer before the RAM-load change, US `F8C4117C` | 1.797 s | 1.422 s |
| Final producer and RAM-load path, US `9726D59B` | 1.891 s | 0.906 s |

The final US image corresponds to console build `4D8AD165`.
`build/foxtrot-fast-load/results.json` records the final restore's exact position,
QFT and native timer, followed by a working Step and Resume. RAM Load fell from
about 1.4 to 0.9 seconds in this sample. These are development-emulator wall times
for one scene and setup, not Wii measurements, controlled benchmark averages or
an all-scene speed guarantee. Compact capacity retries can still take longer.
Older host-only codec comparisons remain in
`build/foxtrot-codec-bench/results.json` as historical evidence, not measurements
of the current end-to-end path.

`build/foxtrot-sd-direct/results.json` records direct SD restoration of exact
position/QFT with all three RAM states unchanged, and rejection of a malformed
zlib stream despite correct file CRCs. Its ARM file receipt was supplied by a
host adapter; its post-delivery duration is not SD-card transfer time. Private
retail memory captures and extracted payloads must never enter release packages.

## Timing and mission countdowns

`rebaseMissionStopwatch` shifts the mission timer's absolute start timestamp by
the time spent blocked. Save calls it on success and failure; success includes
compression, checksum and pool commit. Load rebases the restored stopwatch so
elapsed time rewinds to the saved value. A rejected load preserves live elapsed
time rather than adopting any saved time. SD transfer uses its transaction start
for the full blocked interval; the direct-restore path retains that ownership
through its post-draw load. These adjustments follow retail
`OSCheckStopwatch`'s `total + (now - last)` calculation while active. QFT's normal
timing formulas remain separate from this mission stopwatch.

`scripts/test_savestate_stopwatch.py` compiles the production helper and covers
live elapsed/countdown preservation, normal progress afterward, restored elapsed
time, stopped watches, absent director and tick values above 32 bits. Queue and
archive tests additionally cover the different save/load/refusal time origins.

## Temporary 4 MiB lifetime

The audited PPC range `[0x91300000,0x91700000)` joins SegaBoot's 1 MiB and DIMM's
3 MiB. These are existing allocations, not newly discovered unowned memory.
Their use as transient Sunshine save staging is supported by these source paths:

- `include/susamune/mem2_map.h:15`: SegaBoot and DIMM are adjacent. The real-disc
  and ISO caches finish at 0x91300000, while DI scratch starts at 0x91700000.
  `launcher/kernel/ISO.c:38` and `RealDI.c:42` use those bounded cache constants.
- `launcher/loader/source/main.c:2169`: the validated Sunshine disc IDs bypass
  Triforce probing. SegaBoot staging is in the separate Triforce branch.
- `launcher/loader/source/ipl.c:164`: a normal IPL is decoded and copied out of
  DIMM into MEM1 at 0x81300000. It is flushed before returning. The loader's
  `main.c:2706` finishes this work before transferring execution to MEM1. No
  running game retains this DIMM source as its IPL or font backing storage.
  `launcher/kernel/EXI.c:58` keeps ROM fonts separately at physical 0x13100000.
- `launcher/kernel/DI.c:171`: DIMM clearing belongs to `DIinit(true)` at kernel
  launch. The disc-change path invokes `DIinit(false)` and skips that clearing.
- `launcher/kernel/DI.c`: media-board reads require `TRIGame`; SegaBoot reads
  require `useipltri`. Its formerly unconditional 0xAA arcade write now explicitly
  rejects GMSJ01/GMSE01/GMSP01 through the existing unsupported-command shutdown
  before touching any DMA source or DIMM bytes. Other discs retain their behavior.
- `launcher/kernel/Patch.c:4370`: warm patching uses the already copied MEM1 IPL
  when requested and clears `useipl` at the tail. Cache/SI resets and
  `launcher/kernel/TRI.c:88`'s GCAM reset do not reclaim SegaBoot or DIMM.

RAM saving uses this overlay only after Sunshine's normal readiness checks,
for one synchronous transaction with interrupts disabled. SD reads use the same
range under the separate receipt-confirmed transfer lock: gameplay remains held,
other save/load mutations are excluded, and a direct-load candidate stays owned
until its post-draw restore or rejection. It must never hold an authoritative
retained slot. A fresh loader/kernel launch can reclaim it;
the new run must invalidate its state catalog. The console memory-card-emulation
build exclusion remains essential: its larger allocation would exceed the
shared disc-cache region (`scripts/test_mem2_ownership.py`).

`scripts/test_state_staging.py` runs the production disc guard and unsupported
handler for the three regions, verifies ordinary reads and other games retain
their behavior, and checks the relevant dispatch/reset ownership ordering.
Its three tests and the two existing MEM2 ownership tests passed. The modified
DI source also compiled as an ARM object with its production flags. Console
timing and untested reset/scenario combinations still need hardware feedback.
Basic SD restoration after a Wii reboot was confirmed by the user on the previous
build; that does not prove every staging owner or current file-control path.
