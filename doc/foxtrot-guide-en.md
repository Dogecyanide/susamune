# Moonshine Launcher FOXTROT

V2.3.0 pre-release · Feedback update

FOXTROT adds tools for studying movement and comparing attempts. New level splits are deliberately excluded: each checkpoint still needs to be designed and tested individually.

## Install and update

Copy the `moonshine_launcher` folder into your SD card's `apps` folder. Replace the package files, and keep your existing themes, music, `susamune.ini`, records and ghosts. The launcher supports the existing JP, US and PAL disc revisions. Use your own disc or game image. Do not mix FOXTROT's launcher with older mod binaries: its memory format changed.

Open Moonshine Launcher FOXTROT from the Homebrew Channel. Choose the matching **Version**, then **Path** to select your ISO/CISO on SD or USB, or **Disc Drive** for a real disc. Choose **Launch Game**. If Auto Boot is enabled, hold B during startup to return to the launcher menu.

Configuration and saved mod data belong to the device the launcher was opened from. For example, a launcher on SD still saves its configuration on SD when the game is on USB. Settings and binds are separate for JP, US and PAL. Keep the existing `susamune_*` names when updating.

## Find the controls

Open the mod menu with your configured menu combo (default Y + Start). Use L/R for top-level tabs, the C-stick to move between rows, A to select, and B to go back.

- **Quick:** your Shined favourites.
- **Practice:** frames/camera/inputs, savestates, practice rules, RNG and gameplay options.
- **Runs:** ILs, playlists/streaks, records, PB Safety, and timer/split controls.
- **Ghosts:** race, watch, save and manage ghost tracks.
- **Display:** layout editors, HUD overlays, timer/split display and appearance.
- **System:** button binds and the built-in quick guide.

## Pause and advance

| Default combo | Action |
|---|---|
| L + D-Up | Toggle practice pause |
| L + D-Right | Advance one rendered gameplay frame while practice-paused |
| L + D-Down | Toggle free camera |
| L + D-Left | Stop input recording or playback |

All four are configurable in System > Button binds. Z retains its existing function. Recording and playback have no default bind; use the Practice page or assign your own.

Practice pause stops actor movement, animation and collision work. A step releases one normal rendered gameplay frame, not one quarter-frame: normally four 120 Hz ticks at 30 fps, with the game's usual fractional cadence at PAL's 25 fps. Audio, interface, clocks and absolute-time deadlines continue. This is a practice tool, so affected attempts cannot earn PB credit. Restart the stage for a fresh unassisted attempt.

Without free camera, you can hold jump or other gameplay buttons alongside the Step combo. Those gameplay inputs apply to the step; the configured Step combo itself is removed. When choosing Step or Resume from the menu, release A to continue.

For spins, pause and choose **Queue clockwise spin** or **Queue counterclockwise spin** in the same Practice page. Each Step supplies the next stick direction, completing one circle in nine steps. Hold A on the step where you want to jump. Free camera must be off. Optional spin binds are initially unassigned. Resume, Stop, a state load or a scene change clears the queue.

## Free camera

Enter ordinary retail pause, or enable practice pause, then toggle free camera. Move with the main stick, look with the C-stick, and use L/R analog pressure to descend/ascend. **Free camera speed** on the Practice page saves a speed from 0.25x to 4x; hold X for a temporary boost. Recenter from the Practice page. Toggle it off to restore the retail view.

Free camera remains usable while stepping. Steps use neutral gameplay input while camera control is active. The camera is temporary drawing state; it is restored before gameplay and savestate operations. It closes on a scene transition.

Practice pause, stepping and free camera also work in Ghost Watch and Watch2. The ghost playhead stays still while paused. You can keep free camera active when resuming Watch. B or Start exits Watch; opening the mod menu with its full combo leaves Watch active.

## Record and replay an input take

1. Save a savestate during normal gameplay.
2. Choose Practice > Frames, camera and inputs > Record inputs from savestate.
3. Close the menu and release the buttons. The saved state reloads and recording begins.
4. Play the sequence, then use Stop (default L + D-Left). Opening the mod menu also stops recording and keeps the take.
5. Select Replay recorded inputs. It reloads the same seed state and replays the take.

A take holds at most **4096 rendered frames**: about 137 seconds at 30 fps or 164 seconds at 25 fps. It exists only in memory for this session. Replacing the savestate or changing scenes invalidates it. Changed settings are rejected. B or Start aborts playback.

Playback is experimental. It compares a small fingerprint of Mario, RNG and counters after each consumed frame, and pauses on the first mismatch. A matched fingerprint is not proof that every enemy, particle or timed event stayed identical. Keep important ghost tracks separately; this local take is not a shareable replay file.

## Ghost inputs and splits

New ghost files can include the inputs actually consumed during the attempt, plus timestamps for existing supported split endpoints. Earlier pose-only ghost files remain readable and show unavailable input data honestly.

In **Ghosts > Ghost inputs**, choose Off, Ghost, or **Both ghosts**. The same control is available in Display > Layout editor > Controller inputs and Display > HUD and displays > Other HUD. Both ghosts shows both ghost controllers in Watch2, or the live and ghost controller while racing. Ghost input is a teaching overlay; imported tracks do not control Mario.

Ghost recordings made with practice pause, free camera or stepping are marked **TAS**. Their playback omits held time, so pausing to arrange a camera or plan the next input does not create a long pause in the saved ghost. The game timer itself keeps its original behavior. TAS ghosts are for practice and cannot earn an ordinary PB.

In Display > Timer and splits > Timer and splits, choose the comparison: **Off → PB → SOB → Ghost**. SOB means the cumulative sum of your best recorded segments. Ghost uses the selected race target's compatible split timestamps. Missing or incompatible timestamps show `--`; no checkpoint timing is guessed.

These controls are also under Runs > Timer and splits. **Level splits** is the overlay toggle on the first page.

Exported shareable ghosts live under `susamune_ghosts/share/` on the launcher's device. Put incoming `.smsghost` files in `susamune_ghosts/import/`, then import them from Ghosts. Keep internal `.sgh` files in their existing folders. The included Full Reds ILs remain available through Runs: choose the full-level route when you want the approach and secret reds timed together.

## Layout and colours

Display > Layout editor has separate groups for Timers, Controller inputs, Metadata, Native HUD colours, Custom text, Practice feedback, and Menu and notifications. Rollout and dust editors are also beside their settings in HUD and displays > Movement feedback.

**Timers > Sunshine timer** opens the full editor: position, size, opacity, brightness, all 13 characters, TIME/TEMPO and the streak. Its position range spans the full screen. Colours including blue, purple and white no longer multiply against the original yellow artwork. Timer calculations stay unchanged.

**Native HUD colours** includes separate Health counter colour and Underwater air colour controls. Reset restores the retail colours. In RGB controls, hold **Y** while adjusting with the C-stick for increments of 1 instead of 4. A keeps edits, B discards, and Z resets the selected option, with confirmation.

**Metadata** adds Field gap, Row gap, Fields per row and Value widths. C-stick left/right decreases or increases these values. Choose horizontal layout to arrange several fields per row; Fields per row limits the number before wrapping. Auto wraps at the screen edge. Stable widths keep values aligned as digits change; Compact reduces empty space. Per-character colours remain attached to their original fields.

## Dolphin

Use the matching regional BPS patch with a clean ISO; the Wii launcher ZIP is for the Homebrew Channel. For mod settings persistence, enable a memory card in slot B. Set Texture Cache Accuracy to Safe so savestate loads restore goop correctly. Keep ordinary Sunshine saves and Moonshine's slot-B settings file when updating.

Use a current Dolphin release for frame tools. The same FOXTROT image accepts paused-menu input in Dolphin 2606a JIT and 5.0 Interpreter, but Dolphin 5.0 JIT can leave that input stuck.

## Reports and limitations

This pre-release still needs real-console playtesting. Include the game region, scene, settings, reproduction steps and displayed build checksum when reporting problems. Keep the crash text, `.bin` and `.core` files together. The optional `tools/decode_crash.py` script reads the binary reports with Python 3. Crash reporting attempts to preserve a minimal record even if a larger report cannot be completed; storage is still required for a file to survive shutdown.

The mod reserves 768 KiB of MEM1, 256 KiB more than V2.2. Fixed timer scratch, attachment heap and savestate ownership remain separate. This reduces the game heap's capacity by 256 KiB; the remaining free space depends on the scene and needs console measurement.
