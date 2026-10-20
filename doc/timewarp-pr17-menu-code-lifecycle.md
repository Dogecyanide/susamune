# PR17 menu code ownership

The smaller native-art backup ends at presentation offset `0x7000`.
CPU-only menu code occupies `[0x7000, 0xB100)`; collision spill bits still
begin at `0xB100`. This is `0x91CF9000..0x91CFD100` on Wii and
`0x713BA000..0x713BE100` in Dolphin. No reservation, recording limit or
savestate pool grows or shrinks.

The presentation area belongs to the physical playback-input bank, even
when logical record/playback roles swap. Both legacy 54,000 × 16-byte
inputs and current 36,000 × 24-byte inputs end at bank offset `0xD2F00`.
Presentation begins at `0xD3000`.

Reviewed write paths:

- `ghost.cpp`: recording checks the version-specific input limit before
  writing; canonical import validates counts and copies count × stride.
  Savestate capture/restore validates version, counts and physical bank
  identities before returning bounded spans. Track clearing resets metadata;
  promotion swaps pointers without clearing or copying whole banks.
- `SusamuneGhost.c`: file reads target the separately mapped transfer payload,
  and initialization clears mailboxes/list metadata, not input banks.
  `SusamuneTransfer.c` stages in reclaimed Segaboot storage or the file-transfer
  pool beginning after the complete input bank.
- `savestate.cpp`: ordinary restored game ranges are in MEM1; input-prefix
  writes use the validated ghost spans. Pool metadata lives elsewhere.
- Presentation owners stay disjoint: timer backup below `0x1600`, 257
  six-byte HSL entries below `0x2000`, water storage below `0x4000`, bounded
  artwork backup below `0x7000`, collision spill at/above `0xB100`.
- Launcher startup/reset clears were checked: ARAM clearing ends at
  `0x91000000`; kernel and loader work buffers lie outside this code span.
  The segment installer and executable cache synchronization must run on
  every boot/reinstall.

`test_ghost_savestate_prefix.py` exercises production input capture and
prefix span generation with full physical banks. At the V5, V7 and V8 input
limits it fills the complete unused suffix with canaries, attempts one extra
input, swaps banks, restores the maximum prefix and clears the recorder.
The suffix must remain identical throughout. This is a host boundary check;
it does not replace the combined build's installation/cache checks or Wii
runtime testing.
