# FOXTROT ghost input validation

The V5 wire tests cover the independent host decoder and production C
validators, including maximum pose/input/split payloads, legacy V3/V4 files,
malformed timestamps, flags, split endpoints and checksums. ARM validation
retains its bounded 16 KiB work per pass.

The exact production `playbackInput` function was also compiled for the host
and compared with an independent reverse-linear predecessor lookup. All
47,969 cases passed, including sparse inputs, segment-start cutoffs, truncated
tails, missing legacy input and 54,000 samples. Every returned input byte was
compared. This checks lookup behavior, not the PPC ABI or rendering. Evidence:
`build/foxtrot-ghost-seek/proof.json`.

An isolated Dolphin 2606a fixture exercised the real observer preparation,
start, warp, clock and draw paths using host-validated synthetic tracks. Two
V5 tracks had 1,201 poses and nine input snapshots each; a V3 track had no
inputs. Watch showed recorded A then B while live controller input stayed
neutral. Watch2 showed distinct A/X then B/L inputs. Off hid ghost panels,
Ghost hid the second panel, and Both showed two panels only during Watch2.
Single Watch retained one panel. V3 displayed “Inputs not recorded.”

This fixture installed runtime track state through a private callback in
unused reserved memory. The production emulator links out the file import
path because ghost SD storage is unavailable. These checks therefore do not
prove PPC file parsing, catalog integration or ARM storage. No fixture code
ships in the release. Initial screenshots and exact instrumentation are in
`build/foxtrot-ghost-live/proof.json`.

That capture exposed overlap with native FLUDD artwork. The ghost panels and
legacy label now use Y=218. A binary comparison against the previous Wii
package finds only three changed position operands per regional mod; all
other bytes, headers, segment sizes and hooks are identical. Evidence:
`build/foxtrot-ghost-live/layout-byte-diff.json`.

Final US image `9B61FABE` passed an updated private-fixture capture after the
native HUD returned: both Watch2 panels and the legacy label remain clear of
FLUDD and coin artwork. The original mod sections are byte-identical to that
release image. All owned test processes were closed. Updated captures and
instrumentation are in `build/foxtrot-ghost-live-layout/proof.json`.
