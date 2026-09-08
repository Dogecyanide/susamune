# Moonshine Launcher FOXTROT

V2.3.0 pre-release · Build 5B0EC1B1

FOXTROT adds tools for studying movement and comparing attempts. New level splits are deliberately excluded: each checkpoint still needs to be designed and tested individually.

## Install and update

Copy the `moonshine_launcher` folder into your SD card's `apps` folder. Replace the package files, and keep your existing themes, music, `susamune.ini`, records and ghosts. The launcher supports the existing JP, US and PAL disc revisions. Use your own disc or game image. Do not mix FOXTROT's launcher with older mod binaries: its memory format changed.

Open Moonshine Launcher FOXTROT from the Homebrew Channel. Choose the matching **Version**, then **Path** to select your ISO/CISO on SD or USB, or **Disc Drive** for a real disc. Choose **Launch Game**. If Auto Boot is enabled, hold B during startup to return to the launcher menu.

The launcher loads your theme before the kernel startup screens when its device is available. A USB device that cannot be opened that early is retried after normal storage initialization. Music starts after kernel setup. Startup and error text have explicit drawing state and outlines for dark themes.

Configuration and saved mod data belong to the device the launcher was opened from. For example, a launcher on SD still saves its configuration on SD when the game is on USB. Settings and binds are separate for JP, US and PAL. Keep the existing `susamune_*` names when updating.

## Find the controls

Open the mod menu with your configured menu combo (default Y + Start). Use L/R for top-level tabs, the C-stick to move between rows, A to select, and B to go back.

- **Quick:** your Shined favourites.
- **Practice:** separate Frame advance, Free camera and Input replay pages, savestates, practice rules, RNG and gameplay options.
- **Runs:** ILs, playlists/streaks, records, PB Safety, and timer/split controls.
- **Ghosts:** race, watch, save and manage ghost tracks.
- **Display:** layout editors, HUD overlays, timer/split display and appearance.
- **System:** button binds and the built-in quick guide.

## Pause and advance

Open **Practice > Frame advance**. Selecting an action shows its current shortcut; press **X** to change it there, or use System > Button binds.

| Default shortcut | Action |
|---|---|
| D-Down | Toggle practice pause; cancel a buffered pause |
| D-Up | Pause live gameplay, then advance one frame with each further press |
| Unassigned | Free camera and input recording/replay/stop |

These defaults apply to new configurations. Existing custom binds are preserved, including any earlier L-based combos. Z retains its existing function.

You can press Pause or Step during loading, the stage intro, or while Mario cannot be controlled. **Armed** means it will pause as soon as you can control Mario. You do not have to hold the shortcut. Press Pause again to cancel. Pressing Step again while waiting does not add extra steps.

Practice pause stops gameplay and the QFT. Each Step advances one normal game frame, and the QFT advances with it. Music and the game's background clocks keep running. A small **TAS** appears beside the QFT for an assisted attempt. These attempts cannot earn an ordinary PB; restart the stage to begin a fresh attempt.

The Sunshine timer and compact QFT now show the same frame during a practice hold or Step, including after a savestate load. They use different precision: compact `11.845` can appear as `11.85` on the Sunshine timer. Ordinary QFT timing calculations and event hooks have not changed.

With free camera **Off**, hold A and press Step to jump on that frame. You can also start Pause while holding A, and other gameplay buttons work alongside Pause and Step. To press A again on a later step, release it and press it again before stepping. Holding A continuously counts as keeping it held. The Pause or Step shortcut itself does not reach Mario, including any assigned L/R trigger until you release it. When choosing Step or Resume from the menu, release A to continue.

For spins, use the main stick yourself: choose the next direction before each Step. Free camera must be Off so the stick controls Mario.

## Free camera

Open **Practice > Free camera** and turn it On. This automatically pauses live gameplay. Move with the main stick, look with the C-stick, and use L/R analog pressure to descend/ascend. **Movement speed** saves a speed from 0.25x to 4x; hold X for a temporary boost.

If main-stick left/right feels backwards, enable **Reverse sideways** on the same page. It changes sideways movement only, leaving C-stick look unchanged; the default is Off. Recenter returns to the retail camera's view. Turn free camera Off to restore that view; gameplay stays paused until you choose Resume.

Free camera also works in the ordinary Start pause. It remains usable while stepping, but **Camera On means Mario input Off**: A and the sticks will not control Mario on those steps. Turn it Off before stepping a jump or spin. The camera is temporary drawing state; it is restored before gameplay and savestate operations. It closes on a scene transition.

Practice pause, stepping and free camera also work in Ghost Watch and Watch2. The ghost playhead stays still while paused. You can keep free camera active when resuming Watch. B or Start exits Watch; opening the mod menu with its full combo leaves Watch active.

## Three savestates

Open **Practice > Savestates** and choose **Active state** with A or C-stick left/right. Each of the three states shows Saved or Empty. Your usual Save and Load shortcuts now use the selected state; changing the selection alone does not save or load anything. **System > Button binds > Savestate: cycle states** is an optional shortcut with no button assigned by default.

The three states share **17.625 MiB** of compressed-state memory with this launcher. Their size depends on the scene and the length of any ghost recording included in the state. Nothing is deleted automatically. A replacement can reuse its old state's space once the new save is known to fit. If it cannot fit, all previous states remain, including the state you tried to replace. **Clear selected state** asks for confirmation before freeing that state's space; the other states stay saved. Loading still requires the stage and episode where the state was made. Saving and loading can briefly stop the game while it processes the state.

The three memory slots start empty after closing the game or rebooting. To keep a state, save a separate SD copy before closing the game.

## Keep a state on SD

1. Make a normal memory savestate and select its slot.
2. Open **Practice > Savestates > SD states > Save selected state to SD**. Wait until the save finishes. It creates a new file in `/moonshine_states` on the launcher's device.
3. After rebooting, use the same mod build, game region and launcher setup, then enter the same level and episode. Secret areas also need the same parent episode.
4. Open **SD states**, choose **Active memory state**, then **Refresh / first page**. Select the file and confirm its import. This replaces the chosen memory slot; the SD file remains saved.
5. Use your ordinary **Load** action to restore gameplay from that slot.

The game also checks that its loaded resources match the saved state. A matching level name alone may not be enough. Unsupported setups, incompatible files and damaged files are refused before replacing a memory slot. SD states are specific to their build and game setup; they are not cross-region sharing files like ghosts.

Keep the storage device connected until the transfer or its cancellation finishes. SD files survive power-off, but this experimental feature still needs real Wii/Wii U power-off-and-load testing. Use the latest section of TESTING.md when reporting a result.

## Record and replay an input take

1. Save a savestate during normal gameplay.
2. Choose **Practice > Input replay (experimental) > Record from savestate**.
3. Close the menu and release the buttons. The saved state reloads and recording begins.
4. Play the sequence, then open the mod menu to stop recording and keep the take. Stop recording or replay is on the same page; you can assign it a shortcut with X.
5. Select Replay recorded inputs. It reloads the same seed state and replays the take.

A take holds at most **4096 rendered frames**: about 137 seconds at 30 fps or 164 seconds at 25 fps. It exists only in memory for this session and stays attached to its starting state, even if you select or save another slot. Replacing or clearing that starting state, or changing scenes, invalidates the take. Changed settings are rejected. B or Start aborts playback.

Playback is experimental. It compares a small fingerprint of Mario, RNG and counters after each consumed frame, and pauses on the first mismatch. A matched fingerprint is not proof that every enemy, particle or timed event stayed identical. Keep important ghost tracks separately; this local take is not a shareable replay file.

## Ghost inputs and splits

Personal ghosts and imports now use paged lists with no 45/12-entry or ten-hour library cap. Select **Personal page** or **Imported page** and use C-stick left/right to change pages; A opens the next page. Choose **Save latest ghost** to create a new personal file. Selecting an empty personal ghost row also offers **Save latest ghost**, with confirmation. Existing ghosts stay available, and Watch2 selections remain attached to their files when you browse another page.

Available storage limits the library. The existing per-ghost recording limit remains about 15 minutes. Imported files stay in the import folder; sharing and deleting still act on the file you selected.

New ghost files can include the inputs actually consumed during the attempt, plus timestamps for existing supported split endpoints. Earlier pose-only ghost files remain readable and show unavailable input data honestly.

In **Ghosts > Ghost inputs**, choose Off, Ghost, or **Both ghosts**. The same control is available in Display > Layout editor > Controller inputs and Display > HUD and displays > Other HUD. Both ghosts shows both ghost controllers in Watch2, or the live and ghost controller while racing. Ghost input is a teaching overlay; imported tracks do not control Mario.

Ghost recordings made with practice pause, free camera or stepping are marked **TAS**. Their playback omits paused time, so arranging a camera or planning the next input does not create a long pause in the saved ghost. The QFT also stops during practice pause. TAS ghosts are for practice and cannot earn an ordinary PB.

Saving a state during ghost recording now includes the recording from the level's start to that moment. Loading restores that opening and replaces everything recorded after it with your new continuation. Finish, save and export the resulting full-level TAS ghost as usual. Loading a state made without an active recording does not invent an opening or start a new ghost automatically. Local input takes remain separate and are not saved to SD.

In Display > Timer and splits > Timer and splits, choose the comparison: **Off → PB → SOB → Ghost**. SOB means the cumulative sum of your best recorded segments. Ghost uses the selected race target's compatible split timestamps. Missing or incompatible timestamps show `--`; no checkpoint timing is guessed.

These controls are also under Runs > Timer and splits. **Level splits** is the overlay toggle on the first page.

Exported shareable ghosts live under `susamune_ghosts/share/` on the launcher's device. Put incoming `.smsghost` files in `susamune_ghosts/import/`, then import them from Ghosts. Keep internal `.sgh` files in their existing folders. The included Full Reds ILs remain available through Runs: choose the full-level route when you want the approach and secret reds timed together.

## Layout and colours

Display > Layout editor has separate groups for Timers, Controller inputs, Metadata, Native HUD colours, Custom text, Practice feedback, and Menu and notifications. Rollout and dust editors are also beside their settings in HUD and displays > Movement feedback.

**Timers > Sunshine timer** opens the full editor: position, size, opacity, brightness, all 13 characters, TIME/TEMPO and the streak. Its position range spans the full screen.

The first option, **Appearance**, lets you choose **Original** or **Custom**. Leave the target on All to change the whole timer, or press Start to choose one character or image. Original restores the game's own colours and shading while keeping your position, size and saved custom RGB. Switch back to Custom to use those colours again. Changing an RGB value selects Custom for that target. **Z on Appearance** restores Original, with confirmation. To fix the whole timer's colours quickly, choose **All > Appearance > Original**.

**Native HUD colours** includes separate Health counter colour and Underwater air colour controls. Reset restores the retail colours. In RGB controls, hold **Y** while adjusting with the C-stick for increments of 1 instead of 4. A keeps edits, B discards, and Z resets the selected option, with confirmation.

**Display > Appearance > Mario appearance** contains **Mario colours** and **FLUDD colours**, both using the same Creation editor. Press Start to select All or one part. Choose Original/Custom independently for each part; changing RGB selects Custom. Original keeps the stored custom RGB for later. Keep/Discard/Reset and Y for one-unit RGB adjustments work here too.

| Editor | Parts |
|---|---|
| Mario colours — 7 | Cap, shirt, overalls, gloves, shoes, sunglasses, Sunshine shirt |
| FLUDD colours — 10 | Body paint, metal, straps, tank, spray nozzle, hover nozzle, rocket nozzle, turbo nozzle, sprayed water, water highlights |

Mario's skin stays unchanged. Sprayed water covers the stream, outlet mist and impact splashes; sea water and Yoshi juice keep their normal colours. Keep the edits to save the colours and each part's Original/Custom choice for the next boot.

**Metadata** adds Field gap, Row gap, Fields per row and Value widths. C-stick left/right decreases or increases these values. Choose horizontal layout to arrange several fields per row; Fields per row limits the number before wrapping. Auto wraps at the screen edge. Stable widths keep values aligned as digits change; Compact reduces empty space. Per-character colours remain attached to their original fields.

## Dolphin

Use the matching regional BPS patch with a clean ISO; the Wii launcher ZIP is for the Homebrew Channel. For mod settings persistence, enable a memory card in slot B. Set Texture Cache Accuracy to Safe so savestate loads restore goop correctly. Keep ordinary Sunshine saves and Moonshine's slot-B settings file when updating.

Use a current Dolphin release for frame tools. The same FOXTROT image accepts paused-menu input in Dolphin 2606a JIT and 5.0 Interpreter, but Dolphin 5.0 JIT can leave that input stuck.

The SD states menu requires Moonshine Launcher's storage service; standalone Dolphin BPS builds do not provide it. Their three memory slots still work. The BPS patch now has a 640 KiB disc storage extent; this does not increase the game's MEM1 reservation.

## Reports and limitations

This pre-release still needs real-console playtesting. Include the game region, scene, settings, reproduction steps and displayed build checksum when reporting problems. Keep the crash text, `.bin` and `.core` files together. The optional `tools/decode_crash.py` script reads the binary reports with Python 3. Crash reporting attempts to preserve a minimal record even if a larger report cannot be completed; storage is still required for a file to survive shutdown.

The mod reserves 768 KiB of MEM1, 256 KiB more than V2.2. Fixed timer scratch, attachment heap and savestate ownership remain separate. This reduces the game heap's capacity by 256 KiB; the remaining free space depends on the scene and needs console measurement.
