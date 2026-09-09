# LZ4 1.10.0

Source: https://github.com/lz4/lz4/tree/v1.10.0/lib

`lz4.c` and `lz4.h` retain upstream's BSD 2-Clause notices. The only source
adaptation removes the `stddef.h`, `stdint.h`, and `limits.h` includes; the
freestanding configuration supplies those types/constants before inclusion.
No compression or decompression algorithm is modified.

The mod uses caller-owned workspace, independent 128 KiB blocks, checked
decompression, portable memory access, and no allocation or file APIs.
`state_lz4_config.h` selects a 32 KiB hash table. Unused library entry points
are removed by the final section-garbage-collecting link.
