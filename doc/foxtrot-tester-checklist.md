# Moonshine Launcher FOXTROT — V2.3.0 pre-release

Covers **PR1 and the latest controls, launcher and ghost-library fixes**. Use the complete current package. Pick a few sections; you don't need to test every combination.

## 1. Launcher and normal practice

- Boot your usual disc/ISO/CISO. Check that your theme appears during startup and text stays readable **before loading finishes**. With Auto Boot, check B returns to the launcher.
- Play a busy level such as Bianco 5. Try the menu, savestates, restart and warp wheel; report freezes or unusual slowdown.
- Check your saved binds and the reorganised menus. Mention confusing placement or actions accidentally triggered when opening pages.

## 2. Frame advance and free camera

Practice now has separate **Frame advance**, **Free camera** and **Input replay (experimental)** pages. Select an action to see its shortcut; **X** changes it there. New defaults are **D-Down** for pause/resume and **D-Up** for pause/step. Your existing binds stay as you set them.

- Press Pause or Step during a load/intro. **Armed** should catch the first frame where Mario can act. Pause again cancels it.
- Pause airborne. Each Step should advance one frame. With freecam off, hold **A** alongside Step to jump. Resume should restore control without an unwanted ground pound.
- Try freecam during ordinary Start pause, practice pause and stepping. Check movement, height, saved speed and **X** boost. Try **Reverse sideways** if left/right feels backwards. Turning freecam off restores the view; resume separately.
- With freecam off, queue either spin direction on Frame advance. Step through its nine inputs, holding **A** on your jump step.

Freecam takes over Mario's controls while active. Clocks continuing during practice pause is expected. Assisted attempts must not earn normal PBs; restart for an unassisted attempt.

## 3. Local input recording and replay — PR1

Save a savestate, then choose **Record from savestate** under Input replay. Close the menu, release buttons and run/jump/spray briefly. Open the menu to stop; choose **Replay recorded inputs** to repeat the take. Check B/Start cancels and report mismatch messages or different movement.

This experimental take lasts only for the session and is separate from shareable ghosts. Replacing the savestate or changing scenes clears it.

## 4. Ghost libraries, watching and sharing

- Save, export, reload/import and race/watch a ghost. Existing files should still work. **Save latest ghost** should create a new entry.
- Browse **Personal page** and **Imported page** with C-stick left/right. Libraries can exceed 45 personal ghosts, 12 imports and ten hours combined. Larger collections are useful tests; the roughly 15-minute limit for one recording remains.
- Choose Watch2 ghosts from different pages. Pause, step and use freecam; both should stay together. **Ghost inputs → Both ghosts** should show both controllers.
- Record with pause/step/freecam, then save and watch again. Expect a **TAS** label, no waiting pauses and no ordinary PB credit.

## 5. Split comparisons — including PR1

- Under **Runs > Timer and splits**, enable **Level splits**. Try PB, SOB and Ghost comparison on a supported route with recorded times.
- Share a **new Bianco 3 Secret ghost from PAL to JP** and race with Ghost comparison. Expect checkpoint differences instead of `--`. Other region pairings help too.

No new checkpoints were added. Missing times legitimately show `--`; older ghosts may lack splits or inputs.

## 6. Layout editor and saving

- Move/resize the Sunshine timer and try **white, blue and purple** on its digits, label and streak. Check after coins, a state load or warp.
- Change normal health and underwater air colours independently.
- Tighten metadata gaps and change fields per row; changing values should remain readable.
- Hold **Y** while adjusting RGB colours for changes of **1 instead of 4**.

Try keeping, discarding and resetting edits. Save and reboot: layout, settings, binds, records and ghosts should remain intact.

## Send back

- Wii / Wii U / Dolphin, JP / US / PAL, and the launcher's build checksum:
- What you tested and whether it worked:
- For a problem: level, steps to reproduce and what happened:
- A clip/photo, affected ghost or crash report files, if available.

A simple “tested these three things, all worked” is useful too!
