# Moonshine Launcher FOXTROT

V2.3.0 pre-release, three-state and practice feedback update.

- Up to three compressed savestates share the available memory. Choose Active state under Practice > Savestates; existing Save/Load shortcuts use that selection. An optional Savestate: cycle states shortcut starts unassigned.
- Clear selected state asks for confirmation. Nothing is removed automatically, and a save that cannot fit preserves all previous states. These states are memory-only and do not survive closing the game or rebooting.
- Local input replay stays attached to its original starting state when another state is selected or saved. Replacing or clearing its starting state invalidates the take.

- Pause accepts held gameplay buttons. Releasing and pressing a button again between steps now registers on the next Step; held buttons do not create extra presses.
- QFT stops during frame holds and advances on Step. A small TAS label stays beside it for the assisted attempt.
- Removed queued spin actions and shortcuts. Manual stick input remains available during frame advance.
- Sunshine timer Appearance can be Original or Custom, for All or individual characters, TIME and streak. Original restores retail shading while retaining custom colours and placement.
- Empty personal ghost rows offer to save the latest recording instead of requesting another scan.
- Startup frames now finish copying before display, addressing missing one-off status text such as Checking storage devices.

Controls and ghost library update:

- Theme preload before kernel startup when the launch device is ready; corrected first-frame reveal, depth state and startup/error text contrast.
- Separate Frame advance, Free camera and Input replay pages, showing current shortcuts with X to change them directly.
- D-Up now pauses/steps and D-Down pauses/resumes by default. Existing saved bindings are preserved; camera and replay-stop shortcuts are optional.
- Buffered frame pause catches Mario's first controllable frame after a load or intro. An armed pause can be cancelled.
- Step accepts held gameplay buttons with freecam off; practice modifiers stay stripped until released, including analog L/R pressure.
- Pause/Resume takes priority when an older shortcut overlaps a newly assigned Step button.
- Freecam can pause live gameplay automatically, with a separate Reverse sideways option and clearer camera/input status.
- Paged personal/imported ghost libraries remove the 45/12-entry and ten-hour caps. Save latest ghost creates a new file; existing files and cross-page Watch2 selections are preserved.

Earlier feedback update:

- Layout editor groups for timers, inputs, metadata, native HUD colours, custom text, practice feedback and menu appearance.
- Full Sunshine timer editor, accurate blue/purple/white colours, and independent health/underwater-air colours.
- Hold Y for one-unit RGB adjustments; metadata field/row spacing, column limits and compact widths.
- Corrected free-camera strafe direction, five saved speeds and an X speed boost.
- Pause, step and free camera during ghost Watch.
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
