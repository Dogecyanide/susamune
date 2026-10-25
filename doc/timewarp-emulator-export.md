# Dolphin patch export

The exporter creates a `.bps` patch and a small verification receipt from a
current Dolphin build and the matching clean, untrimmed retail ISO. The patch
contains the mod and instructions to copy bytes from the user's disc. It does
not contain Sunshine's executable or assets.

For maintainers, using the repository's Python environment:

```text
python scripts/timewarp_emulator_export.py --build build/timewarp-pr13-emu --region pal --iso "path/to/clean PAL.iso" --output "path/to/moonshine-pal.bps"
```

Use `jp`, `us`, or `pal` with the corresponding build artifacts and disc. The
command refuses existing output files, mismatched disc checksums, stale or
inconsistent build artifacts, and insufficient unused disc space. It does not
change the source ISO. Apply the resulting BPS to that same clean ISO with a
BPS patcher, then open the patched ISO in Dolphin.

This build's ghost model heaps require Dolphin's memory override enabled with
32 MiB physical MEM1, 24 MiB simulated memory, and MMU disabled. Keep the final
release's Dolphin configuration instructions with the patch. This exporter
does not provide a Wii or Nintendont boot image.

## Checks and layout

The exporter verifies the existing regional ISO CRC, V4 manifest/container,
cold-image hash, pinned link receipt, current source/partial objects and retained
ELF. It reconstructs the hot segments and hook writes from the ELF and verifies
the protected timer source,
symbols and scratch layout against the existing baseline. It checks the
exported initialized timer bytes again after adding its bootstrap.

The existing disc and DOL parsers establish all file extents. The expanded DOL
is placed in a verified unused gap, preferring `0x01000000`, aligned to 32 bytes,
within the original 1,459,978,240-byte ISO. The gap must exclude boot headers,
the apploader and trailer, the original DOL, the FST, and every FST file. The
clean JP, US and PAL discs have no free trailing space; each has a sufficiently
large unreferenced interior gap containing that preferred offset.
Only the boot header's DOL-offset word changes;
the original file table and every asset remain in place. Unchanged retail DOL
ranges use BPS SourceCopy operations. Modified header words, mod hook words,
mod payload and bootstrap use literal operations.

The DOL loads the two permitted hot spans and stages the cold image at
`0x81000000`. A 420-byte bootstrap lives in a verified unused upper-image tail
at `mod base + 0xBF000`; its reserved tail is 1 KiB. It replaces only the
audited `__init_hardware` call immediately after `__init_registers`. The shim
preserves GPRs, LR, CTR, XER and CR, checks the live FST address and length
against all three loaded spans, copies the cold payload, clears staging,
flushes both ranges, invalidates destination instructions, and tail-branches
to the original hardware initializer. Invalid live FST geometry stops before
the copy. There are no test callboxes, controller substitutions, or runtime
debug hooks.

`scripts/test_timewarp_emulator_export.py` executes the emitted instruction
subset with distinct register values and verifies copy/clear/cache ordering,
FST rejection and adjacency, protected-byte/startup/tail rejection, occupied-gap
refusal, and an applied BPS round trip preserving assets and the file table. These are focused
host checks. The receipt reports export validation only; Dolphin boot and
visual verification are separate release checks.
