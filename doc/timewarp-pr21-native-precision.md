# PR21 native Sunshine timer precision

The mod-owned Sunshine timer displays `MM:SS.mmm`. Milliseconds use the same
integer QF conversion as compact QFT: `QF * 1001 / 120`, truncated. This exposes
existing timing precision; it does not introduce a faster clock or new capture
points. Native race/countdown timers and their stopped results retain two decimals.

`NativeHudPrecision::capture()` runs immediately after the pre-direct QFT HUD
update. It reads `currentQf`, `transitionEntryQf`, and the existing 96-byte timer
sidecar. The sidecar's retail-ownership byte remains set after a race stops, so
the decision does not depend on stage names or on the race still running.
Practice holds keep the native earlier render phase; a Step uses the live phase.
No timer state, protected source, hook, or persistent format changes.

The draw scope temporarily borrows the six native digit textures and draws the
last native picture once more for milliseconds. It retains the existing colour
wrapper, black outline, alpha and scaling. The extra picture follows the native
27-pixel right / 5-pixel up spacing observed in `standard_1.blo`; the spacing is
read from the current last two panes rather than hardcoded. Both original
normal-timer ancestors and the last digit receive a temporary wider scissor.
Textures, vtables, clipping and the extra-draw matrix translation are restored.
The native background is already wide enough; no picture, texture or heap is
allocated, and no reservation grows.

The decimal textures are the console's existing ten-entry table at `+0xE0`.
All ten accesses in retail `setTimer` were checked in the local JP, US and PAL
DOLs. Later timer fields differ between JP and US/PAL and are not accessed.

Validation: `scripts/test_native_hud_precision.py` executes the production scope
against bounded fixtures: rounding/carries/cap, 50–200% scale, diagonal placement,
exact borrowed-field restoration, unsuccessful admission, running/stopped native
ownership, practice hold/Step, transition freeze and final stop. JP PPC compilation
passed before integration; final regional builds belong to the package check.

Wii checks:

- Ordinary timed IL: three decimals, including the stopped shine result.
- Piantissimo and blooper race: two decimals while running and at the result.
- Restart/warp out of the race: normal mod timer returns to three decimals.
- Native timer with chosen colours/animation/size: outline and diagonal spacing
  remain intact; pause and frame advance do not add visible timer ticks.

These host checks do not substitute for a Wii/Dolphin visual pass.
