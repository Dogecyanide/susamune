# Read-only loading batches

The kernel's checked read-only cluster map can submit up to 128 KiB from one
physical extent per request. It previously stopped at 64 KiB. This changes only
`clmt_read_sectors`; unmapped files and writable handles retain their original
cluster-by-cluster paths. Adjacent map rows remain separate extents. Bounds are
applied before extent multiplication, including large exFAT extents.

No buffer, stack or memory reservation grows. Aligned SD reads already pass the
requested block count directly to the existing multi-block command. Unaligned
SD reads still split through their 64 KiB bounce buffer. USB READ(10) preserves
the complete sector count while its existing bulk cycle splits at 16 KiB.

The production reader passed ten host checks for exact bytes, distinct extent
boundaries, EOF, seek state and latched errors. Six driver checks execute the
production SD reader and USB read/cycle code with guarded transfer buffers,
including 256-sector requests, unaligned output, standard SD byte addressing,
SDHC sector addressing and transfer errors.

Retained PAL request fixtures, through the production cache and FatFS reader:

| Fixture | Before device reads | After | ISO bytes read |
| --- | ---: | ---: | ---: |
| Lifecycle: 8,978 requests | 3,539 | 3,198 | 87,109,844 (unchanged) |
| Boot: 17 requests | 87 | 52 | 4,623,168 (unchanged) |

Contiguous and fragmented map fixtures return identical address-pattern bytes
and preserve all guards. These are work counts, not measured Wii timings.
The lifecycle fixture is not a new Sirena 4 hardware benchmark. The 128 KiB
ceiling should receive the same short Wii room/reset comparison before any
elapsed-time claim. Larger speculative read-ahead is not enabled.

The exact ARM object has unchanged section totals: 33,460 text bytes, 10 BSS
bytes, zero mutable data bytes and 160 read-only bytes. The final linked build
must still pass the kernel's normal reservation checks.

Private reproducible evidence is under `build/pr72-loading-performance`:
`measure_read_batch.py`, `read-batch-proof.json`, both test logs, object-size
receipts and `handoff.json`.
