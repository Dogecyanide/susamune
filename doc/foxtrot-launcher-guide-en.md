# Moonshine guide

## Getting started

Choose Version to match your Sunshine disc: JP, US or PAL. Choose Path, then your game image on SD or USB, or Disc Drive. Choose Launch Game.

Hold B while opening the launcher to cancel Auto Boot and return to its menu.

In the game, open the mod menu with Y + Start. This is the default; your own button binds stay as you set them.

Use L/R to change top-level tabs, the C-stick to move through rows, A to select, and B to go back.

Settings and binds are saved separately for JP, US and PAL. They belong to the device you opened the launcher from, even if your game is on another device.

## Where to find things

Quick: your Shined favourites.

Practice: savestates, frame advance, free camera, input replay, RNG and gameplay options.

Runs: individual levels, playlists, timer and splits, and PB Safety.

Records: achievements and practice statistics. There is also a Records shortcut inside Runs.

Ghosts: record, save, race, watch and share ghosts.

Display: layout editors, HUD overlays, timers and Mario/FLUDD appearance.

System: button binds and a short in-game guide.

## Button binds

Open System > Button binds to change a shortcut. Follow the prompts to record your button combination.

On a Practice action, press X to change its shortcut without leaving that page.

Default savestate buttons: D-Left saves; D-Right loads. D-Down toggles practice pause; D-Up advances a frame.

These are defaults for new settings. Updating keeps your existing shortcuts.

Free camera, input replay and the state-slot cycling shortcuts start unassigned.

Choose a Step shortcut that you can comfortably press while holding Mario's other buttons. Pause and Step accept held gameplay buttons.

## Save and load states

Open Practice > Savestates. There are three memory slots, shared between your saves.

Save to chooses the slot your Save shortcut writes into. Load from chooses the slot or SD file your Load shortcut restores.

The two choices are independent. Changing a choice does not save or load anything.

For example, Save to State 1 and Load from State 2 lets you replace State 1 while practising from State 2.

System > Button binds has separate cycle-save-slot and cycle-load-slot shortcuts. Both start unassigned. The older cycle-both-slots shortcut is still available.

You must be in the same level and episode to load a state. Nothing is deleted automatically if a new save cannot fit: all your previous states stay intact.

Hold your Load shortcut to keep gameplay still after loading. Release it to move. If practice pause was already on, it stays on after you release Load.

An intro finishes before the hold begins. Keep Load held to stop on Mario's first controllable frame, or release early to continue. A previous practice pause still takes effect when Mario can move.

Clear save slot asks before clearing the slot under Save to. Other slots are kept.

Memory states are lost when you close the game or reboot. Save a separate copy to SD if you want to keep one.

## Keep a state on SD

First make a memory savestate. Under Practice > Savestates, set Save to to that slot.

Open SD states > Save memory state to SD. Give it a name, then press Start to finish. X + Start cancels naming.

Wait until saving finishes before removing the storage device. Files live in /moonshine_states on the launcher's device.

To use a saved file after rebooting, launch the same mod build, game region and setup. Enter the same level and episode. A secret also needs the same parent episode.

Open SD states > Refresh / first page, then highlight your file.

Y selects the file for your usual Load shortcut. Close the menu and press Load. All three memory slots stay saved.

A imports it into the slot under Save to, after confirmation. Load from does not change; choose the imported slot there when you want to load it.

Start renames the file. X asks to delete it.

Loading an SD file reads it each time. Import a frequently used state into memory for faster repeated loads.

Large SD files can load with three full memory slots if one saved slot matches the current scene and setup. That slot is kept as a recovery point; all three slots stay saved.

If an SD read fails partway through, the game restores that recovery state and tells you its slot number. If there is no suitable recovery state and too little temporary space, loading is refused safely.

SD states are specific to their build and setup. Use ghosts when you want to share an attempt across game regions.

## Pause and frame advance

Open Practice > Frame advance. D-Down toggles practice pause. D-Up pauses gameplay, then advances one frame with each further press.

You can press Pause or Step during loading or an intro. Armed means it will pause as soon as you can control Mario. Press Pause again to cancel.

While paused, the QFT stays still. Each Step advances it by one game frame. TAS appears beside the QFT for an assisted attempt. Restart the stage for a fresh, ordinary attempt.

Hold A, then press Step to jump on that frame. To press A again on a later frame, release A and press it again before stepping. Keeping A held counts as holding it continuously.

The Pause or Step shortcut itself is kept away from Mario. After choosing Step or Resume in the menu, release A to continue.

Free camera must be Off to control Mario during a Step. For a spin, choose the next main-stick direction yourself before each Step.

The Sunshine timer and compact QFT use different decimal precision, so their last digits can look different even on the same frame.

## Free camera

Open Practice > Free camera and turn it On. This also pauses live gameplay.

Main stick: move. C-stick: look. L/R analog pressure: move down/up. Hold X for a temporary speed boost.

Movement speed saves a speed from 0.25x to 4x. Reverse sideways changes main-stick left/right movement if it feels backwards to you.

Recenter returns to the game's camera view. Turning free camera Off also restores that view; gameplay stays paused until you choose Resume.

Camera On means Mario input Off. Turn it Off before stepping a jump or spin.

Free camera also works in the normal Start pause and while watching ghosts. During Ghost Watch you can resume playback with free camera still On.

## Record and replay inputs

Input replay repeats your actual button presses from a starting savestate. It is separate from ghost playback and is still experimental.

1. Turn Save RNG state On, then save a new memory state during normal gameplay. Record uses the slot under Save to.

2. Open Practice > Input replay (experimental), then choose Record from savestate.

3. The menu closes. Release the A button used to confirm; you can keep Mario's other buttons held. The starting state reloads and recording begins.

4. Play the sequence. Open the mod menu to stop recording and keep the take.

5. Choose Replay recorded inputs to reload that same starting state and replay the take. Changing Save to or Load from does not change its starting state.

Stop recording or replay is on the same page. B or Start also stops playback.

Keep the starting memory state. Replacing or clearing it, or leaving the scene, makes the take unusable. Other memory slots can still be used.

A take lasts about 2 minutes at most. It is kept only for this session and cannot be saved to SD or shared as a replay file.

For an imported SD state, load it first, then make a new memory save before recording inputs.

Starting means the take is waiting to begin. Settings changed means you need to restore the settings used for that take or make a new one.

Menu favourites, timer position/size, free-camera speed/sideways controls, metadata layout and the ghost input display can still be adjusted. Settings that affect the recorded setup must match.

If the replay says the game state differs, it has stopped rather than continuing with the wrong movement. Make a fresh starting state and take. Experimental replay cannot reproduce every timed event reliably.

## Save, race and watch ghosts

Open Ghosts to manage tracks. Save latest ghost creates a new personal file. An empty personal row also offers to save your latest ghost.

Personal and imported lists have pages. On the page row, use C-stick left/right, or A for the next page. Your library is limited by storage space, not a fixed number of files.

Choose a ghost to race it or watch it. Watch2 shows two tracks together. B or Start leaves Watch. Your full menu combo opens the menu without leaving Watch.

Pause, Step and free camera work while watching. The ghost stays still while paused.

Ghosts > Ghost inputs turns on the ghost's controller display. Both ghosts shows two ghost controllers in Watch2, or your live input and the ghost's input while racing.

Older ghosts may have no recorded inputs to display. Ghost input displays teach you the movement; they do not control Mario.

Shared .smsghost files go in susamune_ghosts/import. Import them from Ghosts. Your exported files appear in susamune_ghosts/share.

## TAS ghosts and splits

Ghosts made using practice pause, Step, free camera or savestate loads are marked TAS. Time spent paused is omitted from the ghost.

Saving a state while recording a ghost keeps the recording from the level's start up to that point. Load it, try a new continuation, then finish and save the full-level TAS ghost.

A state made without an active ghost recording cannot invent the missing opening. Local input takes and ghost recordings are separate features.

TAS attempts cannot earn an ordinary PB. Restart the stage to begin a fresh attempt.

Runs > Timer and splits contains the Level splits display toggle. Display > Timer and splits has the same controls.

The new handmade checkpoints include the remaining level routes and Full Reds. A route can have up to eight segments, including its finish. Existing records are kept where the checkpoint timing still means the same thing.

In Runs > ILs, press Z on a supported row to choose its starting episode. Use C-stick Up/Down, A to keep or B to cancel. Your choice is saved separately for JP, US and PAL.

Episode choices cover the seven main-course 100-coin ILs, Gelato/Noki/Pianta Hidden, and the ten Full Reds ILs. Other IL starts stay fixed.

Choose Off, PB, SOB or Ghost for comparison. SOB adds your best recorded segments together. Ghost compares against your selected race ghost.

The -- display means the required split time is missing or incompatible. Old ghost files and unsupported checkpoints cannot supply a comparison.

## Layout and HUD colours

Open Display > Layout editor. Choose Timers, Controller inputs, Metadata, Native HUD colours, Custom text, Practice feedback, or Menu and notifications.

In an editor, C-stick up/down chooses an option; left/right changes it. Start selects All or the next character/part. X + Start goes backwards.

For Red, Green and Blue, hold Y to change by 1 instead of 4.

A keeps your edits, B discards them, and Z resets the selected option. Each asks for confirmation.

Timers > Sunshine timer edits position, size, opacity, brightness, the characters, TIME and the streak.

Appearance has Original and Custom choices for All or individual parts. Original keeps the game's shading and can still be tinted. Custom uses the chosen colours more directly. Editing RGB does not switch this timer's appearance mode.

Native HUD colours has separate controls for the normal health counter and underwater air meter.

Metadata has Field gap, Row gap, Fields per row and Value widths. Horizontal layout puts several fields on each row. Compact widths reduce empty space.

Rollout and dust controls are also beside their settings under HUD and displays > Movement feedback.

## Mario and FLUDD colours

Open Display > Appearance > Mario appearance, then Mario colours or FLUDD colours.

Mario parts: cap, shirt, overalls, gloves, shoes, sunglasses and Sunshine shirt.

FLUDD parts: body paint, metal, straps, tank, spray/hover/rocket/turbo nozzles, sprayed water and water highlights.

Use the same editor controls: Start selects a part; C-stick chooses and adjusts an option; hold Y for one-unit RGB changes.

Each part has its own Original/Custom choice. Here, editing RGB selects Custom. Choosing Original keeps your custom colour for later.

Keep the edits to save the colours for your next boot. Mario's skin stays unchanged. Sprayed water colours affect the stream, its mist and splashes, while sea water and Yoshi juice keep their own colours.

## Updates and help

Keep your settings, theme, records and ghosts when updating. Replace the packaged launcher files together; do not mix a new launcher with old mod files.

Put background.png and bgm.mp3 in Moonshine_Theme at the root of the SD card. A launcher opened from USB uses Moonshine_Theme on USB. The old theme folder beside boot.dol is no longer used.

Keep existing susamune.ini and susamune_ghosts names. The launcher still uses them.

When reporting a problem, include the build checksum shown on the launcher's home screen, game region, level/episode and the steps that caused it.

For a crash, keep its text and any .bin/.core reports together.

The longer foxtrot-guide-en.md is included beside boot.dol. This Guide works even without that file.
