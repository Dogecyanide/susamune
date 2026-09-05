# Moonshine Launcher FOXTROT

V2.3.0 pre-release, first build.

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
