# Finish-breakdown persistence

The independent 32-byte `SusamuneFinishBreakdownCfg` carries Creation style,
three RGB colours (title, rows, total), the seven-bit row mask, and duration
in half-seconds. Duration 0 means until leaving the level; 1..120 means
0.5..60 seconds. From PR15, shared initialization gives 20 seconds and all rows
except actual load time: QFT transition allowance is shown by default, while
actual load remains available for testing. Valid saved row masks, including
PR14's old default of 95, are preserved. The new mask of 111 applies to reset
and missing configuration only. Padding 255 means Off. Invalid INI fields leave
the previous valid value intact; missing fields retain shared defaults.

The original proposal at config offset 0x1A20 was occupied by Hoverless.
The new line is instead `[cfg+0x1EA0,cfg+0x1EC0)`, immediately after the
Hoverless live PB values and before progress at 0x2000. Capability
0x08000000 is distinct from Hoverless's 0x04000000. Compile-time checks cover
size, field offsets, cache-line alignment and both neighboring ranges.
Settings publishes the whole payload before the existing settings doorbell;
ARM reads it under the existing guarded INI transaction and never writes
the PPC-owned line during play. Unsupported older launchers keep defaults.

Wii writes `finish_breakdown_*` keys into `[creation_<region>]` using the
existing region copy-through path. Style keys match other Creation groups;
`1_rgb`, `2_rgb`, `3_rgb` mean title, rows and total. `rows` is the mask and
`duration_half_seconds` stores duration. Other regions and comments survive.

Dolphin CARD V14 appends 32 bytes after the unchanged V13 Hoverless payload.
The two 8 KiB sectors and complete-sector checksum remain unchanged. Older
versions keep all existing values and initialize breakdown defaults; a
newer legacy candidate cannot inherit a prior candidate's custom style.
The live line is 0x719005C0 and the mutex-owned pending-write copy is
0x719005E0, both within the existing gap before transport at 0x71901000.
The 6 KiB persistence State remains unchanged in size and layout. Failed
writes retain the preceding valid record and the staged copy for retry.
Layout-profile formats and allowlists are unchanged.

Focused validation passed: regional INI roundtrips and invalid/partial
fields; V12/V13 migration and V14 transactions; corrupted-record fallback;
legacy tail isolation; original settings, colours, episodes and Hoverless
PB preservation; immutable commit snapshots and failed-write retry. The
changed PPC units compiled for JP/US/PAL in emulator and console modes, and
the ARM settings parser compiled with the release compiler. No reservation,
saved prefix, existing mailbox offset, or cache ownership changed.
