# Expanded checkpoint records

The current checkpoint journal is version 9. Its 132 stable routes contain 495
segments, with at most eight segments per route including the finish. The
semantic definitions and their generated hash live in
`scripts/split_checkpoint_schema.py`; runtime route counts and the ARM reader
are checked against those definitions by the host tests.

The new files are `susamune_il_stats_v9_a.bin` and
`susamune_il_stats_v9_b.bin`. Writes alternate generations. The reader rejects
unknown versions or schemas and unsafe reads rather than replacing potentially
newer records. Corrupt copies may fall back to a healthy copy; conflicting
payloads with the same generation disable writes.

On the first boot without a V9 journal, the existing V1–V8 migration chain loads
into the reserved old V8 mailbox. V8 is frozen at 285 segments and schema
`1AF7E430`, with its earlier supported schema normalization retained. Migration
never rewrites those older files. V9 copies all regions and PB profiles, keeping
attempts, finishes, play time and PB identities. A segment's gold and PB duration
survive only if **both consecutive semantic endpoints** still match. A changed
route's gold count resets because its old number describes a different set of
segments. New durations remain unset instead of inventing comparisons.

The V9 payload is 42,372 bytes; its shared mailbox is 42,464 bytes and an on-disk
generation is 42,432 bytes. The mailbox uses the aligned 44 KiB window at ghost
transfer offset `0x5F000`, immediately after the codec workspace and before the
secondary model heap at `0x6A000`. Compile-time map checks enforce both
boundaries. Configuration offset `0x8280` remains reserved for V8 migration and
the existing PB mirror does not move. Capability `0x200000` identifies the
relocated V9 service, so an older launcher cannot expose an unrelated memory
range as current statistics.

After initialization, the PowerPC owns the shared payload. The ARM worker reads
and copies it into private file scratch, then only publishes status and the
acknowledgement line. It does not replace payload data while the game runs.

Ghost V5 retains its existing wire version and supports up to eight split
endpoints. Older files remain readable. An older checkpoint schema cannot
provide a guessed delta for a changed current route. The independent host and
ARM validators exercise a full 54,000-input, maximum-pose ghost with all eight
endpoints; its 1,298,016 bytes remain within the existing transfer reservation.

`test_split_stats_v9.py` compiles the production migration and A/B journal code
with bounded host storage. It tests every old-to-new segment pair, all regions
and profiles, legacy file preservation, corrupted and unknown files, same-
generation conflicts, interrupted writes, and subsequent V9 reloads. The frozen
legacy tests continue to cover the older migration chain.
