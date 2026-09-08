# Full ghost prefixes in memory states

Snapshot version 15 stores the active ghost recorder with the game. Loading
restores the recording from level start through the saved frame, discards its
abandoned future, and records the replacement continuation. The restored ghost
carries both `TAS` and `ASSISTED` flags, has no accepted PB token, and remains
eligible for ordinary ghost export. Its original QFT start and saved clock
offset are retained; no earlier poses or inputs are invented.

`Ghost::SavestateData` is a zero-filled 512-byte metadata sidecar. The three
additional compression spans contain only the used pose samples, segment
entries and input samples. Split endpoints and attachment descriptions fit in
the sidecar. Recorder phase, pending stage boundaries and custom endpoint kind
are saved with the prefix. These extra bytes share the existing slot capacity
check, so an oversized candidate must leave all occupied states intact.

`captureSavestate` supplies direct read spans without copying the full prefix.
`savestateRestoreSpans` checks the metadata bounds and the current recorder's
compiled bank ownership, then supplies destinations. Saved pointers are zero;
they can never choose restore addresses. The pose/segment/input banks can swap
when a completed recording becomes playback, so load binds the saved prefix to
the current recorder bank while preserving a pinned opponent in the other bank.

After verified decompression and QFT restoration, `restoreSavestate` restores
the recorder metadata, creates a fresh logical save token and marks the track
TAS. The existing IL restore still disarms normal result and split credit.
The active TAS recorder also invalidates any child-stage IL that is armed while
the same full-route recording continues. A new QFT attempt clears that recorder
state and can regain normal eligibility.

Plant, Death and Transition ILs normally rely on IL code to consume their QFT
endpoint. A restored recorder retains only that endpoint kind and can poll it
while the IL is disarmed; this path cannot start an IL, record a result or award
splits. The endpoint stays in subsequent ghost-prefix snapshots, so repeated TAS
checkpoints do not lose it after the first load clears the live IL state.

Snapshots made without an active recorder contain an explicit empty sidecar and
three zero-length spans. Watch and its cleanup cannot supply a ghost prefix.
Loading such a snapshot does not start an unsolicited recording. Restoring a
real saved prefix through input-take recording/playback follows the same TAS
rules as a manual load.

Nine host tests compile the production capture/restore helpers, pose/input
recording, completion and PB guard. They cover three independent prefixes,
abandoned-future replacement, bank swaps, corrupt metadata, empty/Watch states,
clock and child-segment continuity, repeated custom-endpoint saves, and export
selection/flag contracts. The existing ghost clock, teaching, autosave and IL
tests also passed. Actual compressed integration and file export remain covered
by the parent build/runtime checks; the helper tests do not substitute for those.
