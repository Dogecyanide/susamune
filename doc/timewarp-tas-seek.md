# TAS seeking

Prototype 10 source work, 2026-10-15. This is a bounded replay seek, not a
per-frame savestate cache. The 4,096-frame input capacity, three state slots,
state pool, and MEM1/MEM2 reservations do not change.

`TasProject::seek(frame)` chooses the nearest earlier project checkpoint that
passes `PracticeSession::seekAnchorValid`. Admission checks slot generation,
state identity, RNG/pad presence, Beginning identity, gameplay settings,
initial fingerprint, exact input-prefix hash, transition-prefix hash, and
recorded scene. Equal frame numbers alone are insufficient. The existing state
loader still performs its heap, scene, archive and resource-owner checks.
The request pins that identity and rechecks it after the render barrier.
An already queued ordinary savestate load, including a CARD wait or load
approval, blocks admission before the take can be stopped or modified.

The existing owned-load path restores the world and controller history while
skipping writes to the live tape and transition table. Ordinary replay then
consumes at most one recorded simulation input per update. No timer code or
fast-forward path is borrowed. The operation reports its restored/current
position and target, can be canceled, and times out if gameplay stops making
progress. A fingerprint mismatch stops seeking immediately; it does not claim
that the selected frame was reconstructed.

Successful arrival is paused with the complete future retained. **Continue**
is the explicit takeover action and truncates the future through the existing
editor path. Cancellation keeps the tape and pauses at the reached frame.
Failure detaches the live world from editing, so a desynchronized world cannot
quietly become a checkpoint on the old input branch. No seek saves, replaces,
clears, or evicts a state slot.

The current loader can restore only an anchor compatible with the current
area. A request with no eligible earlier anchor asks the user to return to the
Beginning area; changing the cursor does not bypass that restriction. Forward
replay can traverse the tape's recorded loading zones. Targets inside a movie
or another state that cannot safely be paused are refused at arrival, retaining
the take. They are not reported as successful frame-exact seeks.

Main calls the extension immediately after the corresponding existing
`beforeDirect`, `afterDirect`, and `afterDraw` operations, including movie
updates. While seeking, the menu is closed and progress is rendered separately.
Other input/state/warp actions are blocked, while B/Stop cancels. Seeking must
not be added to `stateDiskBusy`, because that would freeze its replay.

The extension lives after the original practice source's section reset. All
four original practice mixed sections match the same source prefix compiled
with current headers. The protected final link remains the integration gate.
The focused host fixture exercises the production sidecar, owned restore,
prefix checks, request/control functions and takeover; its replay progression
is simulated and is not a Wii timing or full-game determinism proof.

`attemptLabelVisible()` suppresses the fallback TAS label during unloaded,
intro and departing scenes. This is presentation-only: it never clears the
practice or timer assistance flags and cannot make an assisted attempt eligible.

## Frozen director phase

The private PAL smoke found New-TAS recordings differing from their first
replay even though the restored Beginning fingerprint matched. A second
capture had byte-identical Mario state across New and Seek 0, but the retail
director's `mTickBudget` at offset `0x54` changed from 0 to 4 while paused.
Retail `direct()` adds `600 / SMSGetVSyncTimesPerSec()` and spends five units
per simulation tick, even when the borrowed state suppresses movement.
Fractional cadences can therefore run a different number of ticks after
different-length pauses. The corrected follow-up measured `VIGetTvFormat=1`:
physical PAL 50 Hz, with the retail getter returning 25 gameplay frames/s.
The private Dolphin `PAL60=True` preference had not selected PAL60 in-game.
This does not establish a PAL Wii boot-failure cause.

`beginFrozenDirector(freeze)` and `endFrozenDirector()` bracket the borrowed
state in the main loop and retain only that tick budget. They require the
same ready, normal-stage director before and after the call. Active frames,
frame steps and replay consume the retail budget normally; stage transitions
are never rewound. The eight-byte guard lives outside the original mixed
practice owner, and neither timer/QFT code nor RNG is modified.

The focused production-function host test checks pause-independent first-tick
counts at fractional cadences, unchanged active cadence, and a changed or
departing director. Its receipt is
`build/pr10-frozen-director-phase/receipt.json`.

The corrected private PAL run created a fresh TAS, waited paused, then recorded
55 frames using Step and Resume with movement. Ordinary Replay matched all
55 fingerprints and the exact final position. Seek 30 arrived without desync
and retained all 55 inputs; Continue shortened the take to 30, then an edited
Step recorded frame 31 and remained paused. All 24 sampled paused tick budgets
stayed at 4. The receipt is
`build/timewarp-pr10-ui-smoke/run3/followup.json`. This is one actual-game
Dolphin smoke, not a Wii, all-stage or cross-loading-zone determinism proof.
The earlier divergent smoke also confirmed that failure retained the full
tape and paused immediately instead of accepting a mismatched world.
