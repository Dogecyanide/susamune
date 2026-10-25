# PR16 memory and boot packing

The guidebook presentation uses the existing MEM1 and MEM2 reservations.
Savestate and ghost capacities, the JP translation staging boundary, and
the reset-safe boot-file ceilings do not change.

## Recovering existing MEM1 space

The pinned linker can use two previously unallocated kinds of space:

- The gap after the last frozen input in each existing reserved MEM1 span.
- The unused suffix of an exclusively owned fixed input that has become
  smaller.

Suffix recovery preserves the original input address, section attributes
and alignment. It rejects moved, cold, merged, shared and protected inputs.
Each surviving definition and every incoming relocation must remain inside
the current bytes; a reference to the removed tail, including one-past-end,
prevents recovery. Source-owned pools additionally retain their existing
ownership verification. The final allocator checks live and protected
ranges against all recovered intervals.

The linker receipt records the original and current sizes, current hash and
checked incoming-reference count for each reused suffix. This is not a
change to the frozen baseline or permission to relocate protected inputs.

Emulator builds exclude the final upper MEM1 page,
`MOD_BASE + 0xBF000..0xC0000`. The production Dolphin bootstrap owns its first
`0x400` bytes; private runtime probes use the rest. Console allocation does
not inherit that emulator-only exclusion.

## Collision bookkeeping

The collision viewer's 16,384-byte active-triangle bitset retains its full
131,072-triangle capacity. Its first 8,448 bytes stay in the original MEM1
input and its last 7,936 bytes occupy presentation scratch
`+0xB100..+0xD000`. That suffix follows the guidebook option-art CPU backup.
Both allocations are scalar CPU storage; GPU textures remain in MEM1.

The split frees 7,936 MEM1 bytes without changing the collision limit or
claiming memory from the three savestate slots. Checked access handles the
split boundary, and clearing covers both halves.

## Console boot packing

New CPU functions already accepted by the cold-code ownership audit may
remain in recovered MEM1 holes. This allows the existing boot transport to
compress them together with the hot image instead of carrying them in the
uncompressed cold image. The console retention list names each eligible
function explicitly; it does not accept arbitrary baseline code. PR16 adds
the Online page's draw and update functions to that console-only list.
The emulator policy remains unchanged.

The offline boot encoder also compares LZ4 HC level 12 against its existing
bounded encoders for each 128 KiB block and chooses the smallest result.
The pinned host dependency is `lz4==4.4.5`. The stream format and production
decoder are unchanged, and every candidate is round-tripped before output.
This has no effect on the runtime savestate encoder or save/load timings.

Focused checks cover reclaimed-range admission and rejection, retained-code
ownership, collision traversal and split boundaries, and HC output through
the production C installer. Final regional sizes and the unchanged
96-symbol, five-string, nine-anchor and 34-hook checks are recorded in
`build/timewarp-pr16-console/console-check-receipt.json`.

The final console build passes the production native installer's exact
decoded-byte comparison for all three regions:

| Region | Boot file | Boot ceiling remaining | MEM1 remaining |
| --- | ---: | ---: | ---: |
| JP | 548,832 bytes | 32 bytes | 418 bytes |
| US | 544,352 bytes | 106,912 bytes | 14,675 bytes |
| PAL | 544,064 bytes | 107,200 bytes | 14,782 bytes |

JP has almost no remaining boot-file capacity. Any subsequent source,
placement or encoder change requires a new complete regional packing check;
the current fit must not be extrapolated to another build.
