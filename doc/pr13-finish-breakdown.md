# End-of-run QFT breakdown

Display > Timers > Finish breakdown enables an end-only panel for completed
ILs spanning multiple loaded stages. It follows the actual stage sequence,
not a Ricco 4 special case. The first part is Entry; subsequent parts use
scene labels such as Park, Hotel, Casino, Secret, Sand Bird and Bowser.

The observer reads the existing absolute QFT clock before and after direct.
A portal entry uses the existing read-only transition timestamp; stages with
no portal timestamp end at their final observed QFT. The next loaded stage's
stage origin is reconstructed from the global QFT and retail director counter:
`global - director + 4`. This gives the same local clock as a standalone stage
with QFT offset -4. PR13 incorrectly used the first ready sample, which could
discard early stage ticks. Entry plus stage durations plus **QFT transition**
allowances sum to the unchanged final QF; displayed values can round separately.

**Load (real)** is a separate OS-clock measurement from the accepted app-state
handoff (above the 0/1 gameplay-loop returns) to completion of the destination's
`setupObjects`.
It includes teardown/setup, intervening movies and asynchronous loading, excludes
the outgoing fade and incoming playable stage frames, and is not added to QFT.
An unobserved departure is shown as unavailable. It is deliberately distinct from
the QFT transition allowance, which PR13 misleadingly labelled as load time.
No official timer state, split/gold calculations or PB rules change.

Tracking is bounded to eight stages and uses no heap. A fresh QFT attempt
starts a new history. Savestate restores, Watch, backwards clocks and excess
stage counts discard incomplete history; they cannot fabricate missing entry
segments. No result is shown for a single-stage attempt. A separate, small copy
of the finished segments keeps the panel readable through a no-animation shine
exit when a timed duration is selected. Durations range from 0.5 to 60 seconds;
**Until leaving level** instead retains it until departure, stage setup, restart,
the next finish, restore or Watch. Menu/modal time does not exhaust timed results.

The editor lives beside the toggle under Display > Timers and Runs > Timer and
splits. Position, size, text colours, opacity, brightness and background use the
shared Creation editor. Title, IL name, Entry, later stages, actual loads, QFT
transition allowances and QFT total can each be shown or hidden. Appearance,
duration and row selection persist per region in their independent 32-byte block.

`scripts/test_finish_breakdown.py` exercises production decomposition: two-
stage and four-stage histories, repeated areas, multiple loads, reset, restore
invalidation, backwards clocks, overflow, late first-ready samples, independent
actual loads, frozen final totals and until-departure/timed lifetimes. Hardware
checks should cover Ricco 4 Full, Sirena 4 Full, a boss/subarea route and a
restart inside a secret. The source guard still verifies protected timing.
