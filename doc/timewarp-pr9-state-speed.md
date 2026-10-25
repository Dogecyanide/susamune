# PR9 savestate work

The user's PR8 Pinna 3 Wii results are saves 0.534/0.500/0.533 seconds and loads
0.233/0.267/0.267 seconds. The targets are **every save below 0.400 seconds**
and **every load below 0.200 seconds**, measured from timer freeze until Mario
first becomes visible. These targets have not been achieved or proved by the
component work below.

## Changes

`state_quick_replay.cpp` verifies each distinct retained compressed descriptor
once per commit check. It combines those freshly computed CRCs in the original
order for each occupied root and compares every root's complete expected CRC.
The cache is discarded between verification calls; it never trusts a checksum
left from an earlier save. With fewer than two occupied roots the previous
straight CRC pass remains. Directory fingerprints, exact identities, generations,
admission, full-pool rejection and the final destructive-commit boundary remain.
Novel cached blocks still receive their original complete FNV integrity check.

The 8,392-byte verification cache borrows the plan's existing 131,080-byte
comparison buffer, after its comparison use and before replay. The plan remains
158,428 bytes (158,432 rounded), within the same transfer-tail reservation.
A separate PPC compile assertion confirms comparison offset 27,348 is divisible
by the cache's four-byte alignment. Nothing is placed on an enlarged stack or
in a new MEM1/MEM2 reservation.

`state_codec.cpp` recognizes complete zero blocks. Encoding emits exactly the
vendor LZ4 bytes: one literal, an offset-one run, and five trailing literals.
Decoding uses the fast path only after checking that entire bounded
representation, including every length byte and trailing zero. All other streams
still use the ordinary bounded decoder. Zero output uses aligned word stores;
the existing direct-output policy still decides whether a block may bypass
filtered copying. The exact decoded Adler is advanced algebraically for those
zero bytes. It is still compared with the stored checksum, while the packed
CRC continues to cover the entire input. These two optimizations preserve the
encoded bytes and capacity; the additional experiment below changes compression
effort and requires the accompanying memory redistribution.

## Experimental acceleration and memory redistribution

Quick LZ4 now uses acceleration 8. It samples fewer candidate matches while
retaining the same bounded block format, decoder, raw Adler, packed CRC and
transaction checks. Old Quick and Deflate files remain readable. New Pinna 3
streams are about 13.6% larger, so changing acceleration alone is insufficient:
it refused the third slot in both mixed-level and historically tight sets.
Acceleration 2 also refused the historically tight set with the original pool.

The selected candidate has logical bank lengths `0xFF0000`, `0x200000`,
`0x2C2000`, `0x13E000`, `0x70000`: 23,461,888 bytes in total. Two MiB move from
shared temporary storage into retained state storage, and a separately fenced
448 KiB DI tail becomes the fifth bank. Transaction staging decreases from
`0x2F0000` to `0xF0000`; the existing codec workspace and replay-plan reservation
remain `0x4E000` each. The ARM/PPC memory contract must change together before
this encoder can be distributed. No MEM1 arena, stack, or ISO-cache growth is
required by this geometry.

`build/timewarp-pr9-acceleration8-stage-tail-1/receipt.json` tests those exact
logical lengths with disjoint private fake addresses. All three Pinna 3 slots,
the Pinna 3/Bianco 5/Noki 1 combination, and the historical near-full combination
save and restore exactly. The mixed set retains 2,319,808 bytes free; the tight
set retains 291,552 bytes. These captures establish capacity for the tested
cases, not every possible game state.

The tight changed-state test replaces slot 1 with Bianco 5 while preserving the
other two roots. The smaller stage causes 93 blocks (12,133,112 raw bytes) to be
re-encoded at commit, versus 64 blocks (8,332,024 bytes) for the stable candidate
in the original geometry. Despite that extra work, its component cost falls
from 42,734,064 to 37,065,492 ticks, a 13.26% reduction. All final roots decode,
including a protected output window, with canaries intact. The matching stable
receipt is `build/timewarp-pr9-stable-tight-replacement-1/receipt.json`.

| Pinna 3 operation vs frozen PR8 | Slot 1 reduction | Slot 2 reduction | Slot 3 reduction |
| --- | ---: | ---: | ---: |
| Initial save component | 19.66% | 19.91% | 22.49% |
| Load component, all occupied | 12.67% | 12.67% | 12.69% |
| Occupied-slot overwrite component | 25.84% | 25.90% | 25.91% |

Relative to the first PR9 candidate below, the experiment reduces Pinna saves
16.4–17.1%, loads about 7.8%, and overwrites about 16.5–16.6%. On the mixed-level
set, saves improve 14.9–16.9%, loads 7.7–8.1%, and overwrites 13.3–15.6%.
All are isolated component measurements, not Wii freeze-to-Mario timings.

The exact deficit investigation is in
`build/timewarp-pr9-acceleration8-extra3m-1/receipt.json`: with the old geometry
the mixed set needs 277,312 additional bytes and the tight set needs 2,273,728.
Deduplication savings increase by 7,840 bytes; larger encoded blocks cause the
deficit. Its enlarged final bank is a measurement fixture, not the selected
production layout.

## Focused evidence

`build/timewarp-pr9-state-speed-4/receipt.json` contains the first isolated PPC
candidate comparison with frozen PR8 source/checkpoint 19. Unlike the earlier combined
translation-unit bench, the new runner compiles each production module using
PR8's actual command: codec and CRC at `-O2`, store/replay at `-Oz`.
The comparison uses the same three captured Pinna 3 states, which contain
16 entirely zero blocks (2 MiB) each. The root stream, Adler, CRC and decoded
bytes are compared exactly, and buffer canaries remain intact.

| Operation | Slot 1 reduction | Slot 2 reduction | Slot 3 reduction |
| --- | ---: | ---: | ---: |
| Initial save component | 3.35% | 3.34% | 7.25% |
| Load component, all occupied | 5.29% | 5.27% | 5.27% |
| Occupied-slot overwrite component | 11.23% | 11.16% | 11.16% |

These are guest-timebase component results in a private game-free Dolphin DOL,
with isolated fake-MEM2 banks, synthetic source admission and scalar fixture
memory functions. They exclude game callbacks, Wii memory/cache behavior, ARM
ownership, GPU/display barriers and visible game-frame latency. The percentages
must not be applied directly to the user's stopwatch times. Levels with fewer
zero blocks or less shared compressed data can benefit less.

The focused suites report 53 tests, with two pre-existing opt-in cases skipped:
zero fast path (3), replay transactions (7), canonical zero ranges (5), prepared
blocks (2), and codec (36 including the two skips). They cover exact vendor
streams, Adler with preceding nonzero data, corruption of every byte of the zero
representation, fragmented input, protected output, exact duplicate versus hash
collision, full-pool replacement, cancellation and corrupted retained/candidate
blocks. The replay fixture now allocates the complete 0x4E000 workspace it had
always advertised; the former smaller allocation could spuriously overlap a
neighboring host buffer. This is a fixture correction, not a Wii memory change.

`build/timewarp-pr9-state-tests/alignment.json` records the PPC alignment proof.
`scripts/timewarp_pr9_state_speed.py` can reuse a verified PR8 baseline receipt
when measuring a changed candidate, avoiding repeated baseline runs.

The next useful Wii measurement is Pinna 3 with all slots occupied and one
overwrite per slot, using the same visible-Mario endpoint. Larger reductions
remain a hardware measurement question. After selecting acceleration 8, the
zero, prepared-block, codec and replay suites were rerun: 48 tests reported,
46 passed and the same two optional cases skipped. The vendor comparison uses
acceleration 8 while independent decoders still verify exact original raw bytes.
