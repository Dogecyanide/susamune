# Moonshine Launcher FOXTROT

V2.3.0 pre-release, feedback update.

- Layout editor groups for timers, inputs, metadata, native HUD colours, custom text, practice feedback and menu appearance.
- Full Sunshine timer editor, accurate blue/purple/white colours, and independent health/underwater-air colours.
- Hold Y for one-unit RGB adjustments; metadata field/row spacing, column limits and compact widths.
- Corrected free-camera strafe direction, five saved speeds and an X speed boost.
- Pause, step and free camera during ghost Watch; queued spin inputs while frame advancing.
- Assisted ghost recordings omit held time and carry a TAS label; ordinary PB eligibility stays separate.
- Ghost input controls in the Ghosts page and Layout editor, with the clearer Both ghosts label.
- Rollout and dust editors now appear beside their movement settings; timer/split controls also appear under Runs.
- Exported ghosts retain split comparisons across JP, US and PAL when their route and checkpoint schema match. Automatic last-attempt/success targets also supply split deltas.
- Launcher text now has a built-in fallback if its normal font cannot initialize or render, with explicit drawing state and corrected bitmap sampling.

- Practice pause and single rendered-frame advance, with configurable controls.
- Free camera during retail pause and frame advance.
- Experimental local input recording and playback from an existing savestate.
- Ghost input teaching tracks and existing split timestamps; older pose-only ghosts remain readable.
- Ghost input panels sit above the native HUD in Watch and racing views.
- Split comparisons: Off, PB, sum of best segments, or a selected ghost. No new level checkpoint definitions.
- Six menu roots: Quick, Practice, Runs, Ghosts, Display, System.
- Native Sunshine timer position and size controls through scoped display transforms.
- Reduced launcher startup work, CISO asset reading, and richer crash diagnostics.
- Oversized, incomplete or unreadable external patch files cancel boot with a clear error.
- 768 KiB MEM1 reservation; fixed timer scratch and attachment heap remain at their established addresses.
- Reused MEM2 space for the 64 KiB local input take and reduced temporary native timer display storage.
- Reduced per-frame recording work and duplicate launcher asset checksum work.

This is a testing build. Hardware behavior, frame pacing and replay consistency need playtesting. See TESTING.md and the English/Japanese guides.
