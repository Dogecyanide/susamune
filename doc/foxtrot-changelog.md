# Moonshine Launcher FOXTROT

V2.3.0 pre-release · Build 08BDB4CD

Latest update:

- **Z — Episode** in Runs > ILs selects the start for 20 supported ILs: the seven main-course 100-coin routes, Gelato/Noki/Pianta Hidden and ten Full Reds. Choices persist separately by game region.
- Holding the Load shortcut keeps gameplay still after restoration. Release it to move; an existing practice pause remains paused.
- Added the newly handmade checkpoints for remaining routes and Full Reds. Routes support up to eight segments including the finish. Existing attempts, finishes, play time and PB identities carry forward; segment times remain only where both endpoints still match. Older journal files are preserved.
- Large SD states can load while all three memory slots are full, using a compatible saved state as a recovery point. The slots remain intact. A read failure during restoration returns to that recovery state and identifies its slot; missing recovery/temporary capacity produces a safe refusal.
- The launcher reads the two required character assets in larger batches: about 1,314 decoder reads become 167, with identical validated output across JP/US/PAL. This is a read-count improvement, not a measured Wii startup-time claim.
- The tester sheet starts with four focused checks and a grouped reference for new checkpoints. Successful earlier tests remain complete. Make fresh SD states for this build.

Previous release — 00B63258:

- **Guide** is selectable from the launcher's home screen. It contains 13 topics with scrolling and page controls, readable directly on your TV without a separate guide file.
- Improved input replay startup and restored starting inputs. Opening the menu now freezes movement immediately when ending a recording. **Starting** identifies a pending start; refusal messages distinguish changed settings, damaged input recordings, a mismatched starting state and a later playback mismatch. Replay remains experimental, with its checks retained.
- Faster state saves and loads. A quick save format is used where it fits; regular and tighter compression remain automatic fallbacks when memory is crowded. State copying and checking also take less work. Failed replacements preserve all previous states.
- Reclaimed **320 KiB** of existing reserved memory for the state pool. The three slots remain, with no additional reservation from Sunshine's game heap.
- SD states and the previous load-time changes received positive Wii feedback. The latest TESTING.md section has four focused checks; earlier successful results do not need repeating. Make new SD states for this build because archives are build-specific.

Previous release — C4AF447B:

- **Records** is a top-level tab again, between Runs and Ghosts. Its shortcut inside Runs remains available.
- Faster memory-state saves and loads, with less work spent checking SD files. Waits still depend on the scene, saved ghost length and available space; the measured improvements are from Dolphin and need Wii feedback.
- **Save to** and **Load from** are independent. Save can write State 1 while Load keeps using State 2 or an SD file. New optional cycle-save and cycle-load shortcuts start unassigned; the older cycle-both shortcut is preserved.
- SD files can be named before saving, renamed with Start, or deleted with X and confirmation. On a file, **A** imports it into the Save to memory slot without changing Load from. **Y** chooses the file for the normal Load shortcut; it loads through temporary space and preserves all three memory slots. Exceptionally full memory can leave too little temporary space, in which case the load is refused without discarding states.
- **Checking storage devices...** remains visible during the menu's slower second device scan. That scan previously ran after a background-only frame had cleared the status text.
- Fixed red specks on magenta Mario cap/shirt colours. Texture colours that round to one value now stay that colour, without a red sample being introduced. Skin and emblem selection are unchanged.
- The previous build received real Wii confirmation for SD restoration after reboot, full ghost continuation with frame advance, aligned timer displays and kept colours surviving reboot. The new controls above still need focused feedback; the short latest section of TESTING.md replaces a full retest.

Previous release — 5B0EC1B1:

- Mario colours in the Creation editor: cap, shirt, overalls, gloves, shoes, sunglasses and Sunshine shirt. Each part has Original/Custom and its own RGB; skin stays unchanged.
- FLUDD colours use the same editor for paint, metal, straps, tank, the four nozzle colours, sprayed water and water highlights. Original restores the normal appearance. Water colours cover the stream, mist and splashes; sea water and Yoshi juice keep their normal colours.
- Sunshine timer and compact QFT now show the same frame during practice pause, Step and state restores, allowing for their different number of decimal places. Ordinary QFT calculations and timing hooks are unchanged. Sunshine timer Original/Custom remains editable per character, TIME and streak.
- Savestates now keep a recording's whole ghost history up to the saved moment. Load, change the continuation and finish to produce a full-level TAS ghost; the abandoned future is removed. These ghosts remain shareable and cannot earn ordinary PBs.
- The three compressed states now share 17.625 MiB with this launcher. Replacing a state can reuse its old space after the new state is proved to fit; needing a temporary second copy no longer causes that save to fail. If it still cannot fit, all old states remain.
- **Practice > Savestates > SD states** saves a memory state as a new file in `/moonshine_states`. Import a file into a memory slot, then use Load. The files remain after reboot; the three memory slots themselves do not.
- SD states require the same mod build, game region, launcher setup, level/episode and compatible loaded resources. Unsupported or damaged files are refused before replacing a memory state. That build's basic Wii reboot restore has since been confirmed by a tester; this is not cross-build or cross-region state sharing.

Earlier three-state and practice feedback update:

- Added three compressed savestates sharing the available memory, initially using one Active state choice for Save and Load. The latest update separates those choices and retains the older combined cycle shortcut.
- Added confirmation when clearing a memory state. Nothing is removed automatically, and a save that cannot fit preserves all previous states. The SD states page keeps a separate copy across reboots.
- Local input replay stays attached to its original starting state when another state is selected or saved. Replacing or clearing its starting state invalidates the take.

- Pause accepts held gameplay buttons. Releasing and pressing a button again between steps now registers on the next Step; held buttons do not create extra presses.
- QFT stops during frame holds and advances on Step. A small TAS label stays beside it for the assisted attempt.
- Removed queued spin actions and shortcuts. Manual stick input remains available during frame advance.
- Sunshine timer Appearance can be Original or Custom, for All or individual characters, TIME and streak. Original restores retail shading while retaining custom colours and placement.
- Empty personal ghost rows offer to save the latest recording instead of requesting another scan.
- Startup frames finish copying before display. The separate blank screen during the later device scan is fixed in the latest update above.

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
- Initially grouped the menu into six roots; Records has since returned as the seventh top-level tab in this update.
- Native Sunshine timer position and size controls through scoped display transforms.
- Reduced launcher startup work, CISO asset reading, and richer crash diagnostics.
- Oversized, incomplete or unreadable external patch files cancel boot with a clear error.
- 768 KiB MEM1 reservation; fixed timer scratch and attachment heap remain at their established addresses.
- Reused MEM2 space for the 64 KiB local input take and reduced temporary native timer display storage.
- Reduced per-frame recording work and duplicate launcher asset checksum work.

This is a testing build. Hardware behavior, frame pacing and replay consistency need playtesting. See TESTING.md and the English/Japanese guides.
