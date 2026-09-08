# Compressed in-memory state codec and staging audit

This covers the first multi-state implementation's codec and temporary memory.
It does not implement states saved to SD or preservation across a fresh boot.

## Codec contract

`include/susamune/state_codec.hxx` accepts up to 64 input/output spans. The caller
owns aligned workspace and all buffers. The miniz configuration uses no heap,
file APIs, or unaligned word loads. The compiled workspace is 319,360 bytes on
the host and 319,296 bytes on PowerPC (confirmed from `workspaceSize`'s compiled
return value). A target static assertion limits it to 0x50000 bytes, including
the inflater's 32 KiB dictionary. The original PowerPC object compiled with
`-Oz`/`-Werror` on 2026-09-08; its only unresolved imports were `memcpy` and
`memset`, with no allocator dependencies. The current CMake build uses `-O2`
specifically for this codec, and its PowerPC section pragma places it in the
upper mod code span. Other sources keep their existing optimization settings.

Compression uses eight lazy match probes and concatenates the actual
static/root/stage regions into one zlib stream without a full raw snapshot
staging buffer. Its two output spans are
capacities. A full output still counts the complete compressed length while
discarding overflow, and returns `OUTPUT_FULL`; that partial candidate must
never replace a previous slot.

Validation fully inflates into a wrapping dictionary, verifies the zlib checksum
and the expected Adler-32, and requires exact compressed consumption and decoded
length. `decompress` repeats that validation before its scatter-writing pass.
All destination ranges and source/workspace/descriptor overlaps are checked
before any game writes. Input and descriptors must remain immutable and the
workspace exclusively owned throughout both passes. `COMMIT_FAILED` means the
second pass failed despite validation and gameplay must not resume. Ordinary
argument/corruption failures make no destination writes.

`scripts/test_state_codec.py` exercises production code: split headers/checksums,
dictionary wrapping, scattered output, exact-full/overflow capacities, corrupt,
truncated and appended streams, incorrect decoded sizes/checksums, overlap and
native-pointer bounds. All seven tests passed again with the current eight-probe
setting. The private US Bianco capture measured 14,986,692 input bytes and
5,113,334 compressed bytes and was restored byte for byte; Python zlib independently
decoded the same stream. The earlier 5,015,626-byte result used 128 probes and is
a baseline, not the current compressed size. This is one scene sample, not an
all-scene capacity guarantee. The capture remains under
`build/foxtrot-held-input/private-us-bianco-state.bin` and must not be packaged.

## Timing and mission countdowns

The host comparison in `build/foxtrot-codec-bench/results.json` used that same
private capture. Each listed variant passed an exact roundtrip:

| Variant | Compressed bytes | Median compression | Median two-pass restore |
| --- | ---: | ---: | ---: |
| Original baseline: `-Oz`, 128 lazy probes | 5,015,626 | 0.499663 s | 0.076239 s |
| Comparison: `-O2`, 128 lazy probes | 5,015,626 | 0.498059 s | 0.063569 s |
| Current: `-O2`, 8 lazy probes | 5,113,334 | 0.189694 s | 0.071570 s |

The chosen setting compressed this capture about 2.6 times faster on the host,
at a 1.95% size increase. These are host codec measurements, not Wii save/load
times or all-scene guarantees. A failed capacity check still completes
compression to determine the required length. Successful replacement may also
move retained packed states; restore validates once before its writing pass.
Those costs require end-to-end runtime measurements.

`rebaseMissionStopwatch` shifts the mission timer's absolute start timestamp by
the time spent blocked. Save calls it after compression on both success and
failure; success includes the pool commit in that interval. Load calls it after
restoring the saved stopwatch so its elapsed value rewinds to the saved value.
A rejected load instead uses the validation start time to preserve the live
elapsed value without adopting any saved time. All paths update the timestamp
before resuming interrupts. This follows retail
`OSCheckStopwatch`'s `total + (now - last)` calculation while active.

The six tests in `scripts/test_savestate_stopwatch.py` compile the production
helper and verify live elapsed time/countdown preservation, subsequent normal
progress, restoration of the saved elapsed time, stopped watches, and absence
of a director. Tick values exceed 32 bits to catch truncation. Source ordering
checks cover both save outcomes and both load outcomes, including their distinct
timestamp origins; all six passed.

## Temporary 4 MiB lifetime

The proposed PPC range `[0x91300000,0x91700000)` joins SegaBoot's 1 MiB and DIMM's
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

Use this overlay only after Sunshine's normal savestate readiness checks, for
one synchronous save transaction with interrupts disabled. It must never hold
an authoritative retained slot. A fresh loader/kernel launch can reclaim it;
the new run must invalidate its state catalog. The console memory-card-emulation
build exclusion remains essential: its larger allocation would exceed the
shared disc-cache region (`scripts/test_mem2_ownership.py`).

`scripts/test_state_staging.py` runs the production disc guard and unsupported
handler for the three regions, verifies ordinary reads and other games retain
their behavior, and checks the relevant dispatch/reset ownership ordering.
Its three tests and the two existing MEM2 ownership tests passed. The modified
DI source also compiled as an ARM object with its production flags. Console
save/restore timing and reset behavior still require runtime testing.
