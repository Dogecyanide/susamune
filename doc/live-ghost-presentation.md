# Live ghost presentation prototype

The implementation is compiled only with `TIMEWARP_LIVE_RACING`. It does not
connect to a network or join a race by itself. The session layer owns peer
identity, canonical scene matching, timing and the main-loop calls.

`reset()` starts a new peer/session. `setName()` accepts one to sixteen
printable ASCII bytes. `submit()` accepts a validated visual observation,
sequence, remote milliseconds, scene epoch and local receipt milliseconds.
Those counters use modulo-32 ordering: consecutive observations must remain
within half the counter range. Scene epochs increase within a session;
reset before accepting a different session. Timestamp units are monotonic
milliseconds, not game frames or writes to QFT state.

Call `tick(now, sameCanonicalScene)` once before the frame's render passes.
It latches a pose from four observations with an 80 ms interpolation delay,
holds at the newest observation rather than extrapolating, and hides after
250 ms without an accepted observation. A later packet cannot rewind the
latched timeline. Scene changes, gaps over one second and displacements over
1,000 game units reset interpolation. Yaw and equal-animation phase take the
shortest modular path. Animation changes, attachments and visibility step at
their sample boundary. Input pose clocks/tokens are ignored; the presentation
owns a separate timeline/token for cosmetic water, without changing game RNG,
timers, recordings or gameplay actors.

`Ghost::renderVisualState()` supplies runner 0 from the existing personal
ghost and runner 1 from this live latch. Watch preparation, playback and
cleanup retain their existing secondary provider. Both body and water use
this selector. The two existing model heaps and attachment heap are reused;
no ghost recording or playback payload is overwritten. The new scalar state
is 296 bytes in the focused PAL object.

The existing Ghost Display setting, opacity/appearance choices and menu
visibility policy still apply. Call `drawName()` during the established Menu
2D pass, after `Menu::draw()`. It never opens the menu. The label uses the
latched position plus a fixed 140-unit height, rejects invalid projection
values and clips its bounds to the 640 by 480 logical viewport. Watch hides
the live label. The session must pass `false` to `tick` outside its verified
matching scene; a matching area alone is insufficient for child stages.

`scripts/test_live_ghost.py` executes the production timeline and selector
with native doubles. Its focused cases cover interpolation, late-packet
monotonicity, stale hiding, sequence/scene ordering, timestamp wrap, teleport
resets, bounded names, malformed poses including NaN under fast-math, and
Watch ownership. Four PAL objects compile with the flag enabled. These are
not network, final-link, projection-rendering or Wii lifecycle tests.
