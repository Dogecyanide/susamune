# PR10 save and experimental RAM load

The reported PR9 Wii Pinna timings were JP: saves 0.467/0.467/0.500 seconds,
loads 0.267/0.233/0.233 seconds. The requested load target is now 0.167 seconds.
No PR10 Wii freeze-to-visible measurement is available yet.

## Save change

Quick replay now computes one CRC per encoded block and combines those CRCs into
the complete packed-stream CRC. The same block CRC supplies the shared-block
lookup key, replacing the separate bytewise FNV pass. Matching keys still require
exact byte equality, so colliding CRCs cannot merge different blocks. Novel cached
blocks receive a fresh CRC before commit; retained roots still receive complete
fresh integrity validation. Raw Adler, directory/plan fingerprints, generation,
ownership, capacity and destructive-commit guards remain. Imported Quick blocks
use the same lookup-key calculation. Stream bytes and pool geometry are unchanged.

`build/timewarp-pr10-state-candidates-1/receipt.json` compares frozen source22
with this candidate using the shipped per-module PPC flags and the five-bank map.
All three Pinna streams match the previous acceleration-8 streams byte for byte.
Initial-save component time decreases 30.29%, 23.05%, and 22.09%; occupied
overwrites decrease 19.39%, 19.55%, and 19.55%. Load time is unchanged.

Seven replay tests cover a deliberate CRC collision, exact duplicates, mutation
before commit, capacity refusal, retained data and bank seams. Six staged tests
and eleven store tests also passed before the experimental load addition.

## Safe raw-checksum reuse

Quick replay now defers a block's raw Adler until after compression and exact
shared-block lookup. An identical encoded header and payload have the same raw
bytes, so an already checked block's raw Adler can be reused. A CRC-key match
alone is never sufficient. New blocks and cache misses still calculate the full
raw checksum; every block Adler is combined into the original complete raw
Adler. The packed stream, its CRC, fresh commit validation and checked-load
validation remain unchanged.

The cache uses exactly the existing 1,664-byte directory tail at offset 31,104:
a 32-byte header and 204 eight-byte descriptor/checksum entries. The directory
remains 32,768 bytes. Replay scratch is 159,488 bytes within its existing
319,488-byte reservation. Cache publication temporarily borrows the replay
comparison scratch after verification; active readers and pins already prevent
replay admission, and the persistent cache starts after reader control storage.

The cache is bound to the store epoch, all root generations, the complete pool
directory except the transaction target, and its own metadata CRC. Abort leaves
it intact. External commits, imports, repacking and clear invalidate the binding
and fall back to ordinary checksum calculation. Corruption before prepare also
falls back; corruption after a cache was accepted causes commit refusal before
destructive writes. A 205-unique-block test verifies eviction only causes one
extra checksum calculation, with the complete decoded bytes still exact.

`build/timewarp-pr10-adler-reuse-1/receipt.json` compares this production
implementation with the preceding PR10 implementation under identical PPC flags
and inputs. All three streams, full raw/packed checksums and decoded bytes match.

| Operation | Previous guest ticks | Reuse guest ticks | Reduction |
| --- | ---: | ---: | ---: |
| First save | 14,308,494 | 14,325,249 | -0.12% |
| Second save | 15,796,850 | 14,385,880 | 8.93% |
| Third save | 16,555,069 | 15,095,240 | 8.82% |
| Occupied overwrite 1 | 16,915,892 | 14,365,954 | 15.07% |
| Occupied overwrite 2 | 16,977,461 | 14,427,071 | 15.02% |
| Occupied overwrite 3 | 16,976,792 | 14,425,868 | 15.03% |

At the verified 40.5 MHz guest timebase, occupied overwrites save about 63 ms of
emulated component time; first save adds about 0.41 ms. Checked loads have
identical guest ticks. This is not a Wii endpoint measurement.

Eleven replay tests and thirteen store tests pass, including genuine CRC
collisions, exact duplicates, split-span encoding, cache corruption, abort,
external mutation, bounded eviction, reader/pin exclusion and checked decoding.
`build/timewarp-pr10-adler-reuse-proof/receipt.json` binds the final source to
the benchmark and test logs. The final replay PPC object is byte-identical to
the measured object; only a compile-time alignment assertion and comment were
added after measurement.

## Experimental RAM load

At the user's explicit request, `StateStore::restoreSlotExperimental` skips the
full packed CRC and raw Adler scans for Quick RAM roots. It retains directory and
chunk structure, generation/identity, pinning, source/output separation, declared
sizes, Quick framing, bounded LZ4 decoding, and copy/direct-output policies.
The caller must retain exclusive memory ownership. An in-bounds payload mutation
can now be restored without detection; this is an experimental stability tradeoff.
Decode failures after writes still return `COMMIT_FAILED` and must not resume play.

The new codec entry `decompressExperimental` is Quick-only. Deflate roots fall
back to the checked store entry. Existing pin/check/restore/stream APIs keep their
checksum validation. Production routing belongs only to ordinary, non-durable
RAM loads; SD, imports and TAS must continue using the checked paths.

`build/timewarp-pr10-experimental-load-1/receipt.json` measures the exact current
production modules, three occupied Pinna roots, and the same inputs:

| Slot | Checked guest ticks | Experimental guest ticks | Reduction |
| --- | ---: | ---: | ---: |
| 1 | 6,996,733 | 2,570,695 | 63.26% |
| 2 | 7,023,922 | 2,572,259 | 63.38% |
| 3 | 7,022,111 | 2,571,162 | 63.38% |

Every restored byte matches its capture; guard canaries remain intact. Thirteen
store tests and four focused codec tests pass, including stale identities,
active pins/transactions, aliases, output sizes, malformed framing/LZ4 bounds,
and unchanged rejection through checked APIs. A deliberate in-bounds mutation
demonstrates the experimental checksum omission rather than hiding it.

## Measured save phases

`build/timewarp-pr10-save-profile-1/receipt.json` instruments a private copy of
the production modules before raw-checksum reuse. It reads the emulator's 162 MHz bus-clock word
and uses the repository's `OS_TIMER_CLOCK = OS_BUS_CLOCK / 4` conversion: 40.5 MHz.
These are **emulated component milliseconds**, not measured Wii save latency.

| Phase | First Pinna save | Slot 1 overwrite with three occupied roots |
| --- | ---: | ---: |
| Input preparation and compression | 179.92 ms | 179.92 ms |
| Raw Adler | 64.15 ms | 64.15 ms |
| Packed CRC and combining | 45.80 ms | 45.80 ms |
| Shared lookup and exact comparisons | 3.53 ms | 33.12 ms |
| Candidate cache copy | 8.33 ms | 0.00 ms |
| Commit integrity validation | 45.85 ms | 74.22 ms |
| Metadata, admission and other work | 5.75 ms | 20.49 ms |
| Total | 353.31 ms | 417.69 ms |

Both measured saves use 115 encode calls, with no spill/re-encode or physical
chunk moves. Compression accounts for 51%/43%; checksum work accounts for about
44% in both cases. Instrumentation adds about 675 guest ticks versus the clean
candidate. Game capture, audio shutdown, graphics barriers, cache maintenance,
and the first visible frame are outside this harness. The Wii endpoint cannot
be obtained by scaling these numbers to the user's earlier measurements.
