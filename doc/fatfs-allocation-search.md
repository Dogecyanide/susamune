# Kernel allocation search hints

The recording predeparture delay had two filesystem costs: scanning the flat
recordings directory, then allocating the new file's first cluster. On the
returned FAT32 card, a progress-journal replacement could rewind FatFS's global
allocation cursor from the free region near cluster 140,000 to its older journal
near cluster 65,557. The next recording's 64-byte header then searched through
586 FAT sectors before finding free space. A normal header needed one.

`MOONSHINE_FATFS_FORWARD_ALLOC_HINT` is defined only for `fatfs-arm`. After a
successful FAT12/16/32 truncation, `f_open` retains a valid cursor strictly ahead
of the freed starting cluster. Unknown/out-of-range cursors and equal/earlier
cursors retain upstream hole reuse. The allocator still reads the FAT before
every allocation and performs its complete wrap search. The loader and exFAT
truncation path keep their original behavior.

This is a search hint, never a claim that a cluster is free. No file format,
header, filename, structure size, reservation or write-admission check changes.
Small replacement files may move into the current free region instead of their
old hole. Free low holes remain available after wrapping; near-full disk tests
exercise that case. File contents, lengths and free-space accounting remain the
same.

A read-only raw-volume reproduction uses the real card's geometry, directories
and FAT. Every simulated write goes to a RAM sector overlay; no raw write handle
or commit path exists. Replacing an 864-byte progress file and then opening the
next recording takes the following native FatFS device operations:

| Work | Before | Forward hint |
| --- | ---: | ---: |
| Reads | 968 | 383 |
| FAT reads | 592 | 7 |
| Writes | 13 | 13 |
| Sectors written | 13 | 13 |

The journal transaction itself retains 28 reads and nine writes; the reduction
is the subsequent header allocation. These are request counts, not elapsed Wii
times. The separate approximately 330-read directory-create cost remains;
preparing and synchronizing an allocated file in advance can remove both costs
from the departure path. Preparing a zero-length filename alone cannot remove
the first-cluster search.

Ten native FAT16/FAT32 tests cover readback/remount, unchanged sizes/free counts,
full-disk and fragmented-hole wrap, equal/invalid hints, readonly/CREATE_NEW
protection, corrupt-chain and injected-I/O failure equivalence, loader exclusion
and the unchanged exFAT branch. Long-name, mapped-read and INI attribute
regressions also pass. The exact ARM object adds 80 text bytes and no mutable or
read-only data. Final linked reservation checks and Wii timings still apply.

Private evidence and safe reproduction scripts are under
`build/pr74-loading-followup/raw-fat-cow`; `handoff-final.json` records source
hashes and verification scope.
