# Moonshine Launcher FOXTROT — final test checklist

**V2.3.0 pre-release · Build C4AF447B**

This is the complete reference checklist. **There are six checks for this update. Keep earlier results; successful older checks do not need repeating.** The later sections are a reference for anything still marked Not tested. Use the full package so the launcher and game files match.

Already confirmed on the previous build: SD restoration after a real Wii reboot, full ghosts with frame advance, aligned timer displays and colours surviving reboot. The new SD controls below are the main focus now.

**Tester:**  
**Platform:** Wii / Wii U / Dolphin — version:  
**Game region:** JP / US / PAL  
**Game source:** Disc / ISO / CISO — SD / USB

## Start here — latest changes

- [ ] **Startup message:** Start the launcher with your usual theme. During the wait before its menu, **Checking storage devices...** should stay visible instead of leaving a blank message area.
- [ ] **Magenta without red marks:** In **Display > Appearance > Mario appearance > Mario colours**, set the cap and shirt to Custom **255, 0, 255**. Look for the small red marks reported before; they should be gone. Skin and the cap emblem should keep their usual details.
- [ ] **Separate Save and Load:** In **Practice > Savestates**, choose **Save to State 1** and **Load from State 2**. Save somewhere new, then Load: it should still restore State 2. Note whether the Save/Load wait feels shorter. If you assign the new cycle-save/cycle-load shortcuts, each should change only its own selection.
- [ ] **SD names:** Under **SD states**, choose **Save memory state to SD**, name it and finish with Start. Rename that file with Start. On a disposable file, cancel X/Delete once, then confirm it. Only that file should disappear; memory states stay saved.
- [ ] **Load an SD file directly:** Highlight a compatible file and press **Y**. Close the menu and use the normal Load shortcut. It should restore that file while keeping all three memory states. Save another memory state and Load again: the SD file should still be the source. If temporary space is insufficient, report the message; existing states must remain usable.
- [ ] **Import keeps the Load choice:** Set Save to State 3 while Load from uses another slot or SD file. Press **A** on an SD file, cancel once, then confirm import. Only State 3 should be replaced; Load from should stay unchanged. Select State 3 to use it. If practical, try the new Y/Load route after rebooting into the same build, setup and scene; note the scene and result.

SD files are in `/moonshine_states` on the launcher's device. Use a state made with the same build, region, launcher setup, level and episode; secret areas also need the same parent episode. Loaded resources must match too. Keep the device connected until a transfer or cancellation finishes. There is no need to deliberately damage files or interrupt writes.

Standalone Dolphin BPS builds do not provide SD states; mark those items **Not available** and test the memory slots normally.

## 1. Launcher and startup

- [ ] **Early text and theme:** Start the launcher with your usual theme. Check the theme appears during startup and all text is readable **before loading finishes**, including progress and error messages. Note any blank-text period or stock-background flash.
- [ ] **Launching:** Select your region and usual disc/ISO/CISO, then launch successfully. If using theme music, check it starts and plays normally.
- [ ] **Auto Boot:** Check it starts the selected game. On another launch, hold B and confirm you can return to the launcher menu.

## 2. Menus and button binds

- [ ] Browse **Quick, Practice, Runs, Records, Ghosts, Display and System**. Records should be on the top row again and still open from its Runs shortcut. Enter and leave submenus; holding A while entering a page should not activate its first action.
- [ ] Under Practice, find the separate **Frame advance**, **Free camera** and **Input replay (experimental)** pages. Select an action, press **X** to change its shortcut, then use it. Finishing or cancelling the bind recorder should not trigger another action or switch tabs.
- [ ] Check existing custom binds still work. Try a setting available in two places and confirm both show the same value. Add/remove a Quick favourite and check it opens the intended feature.

New configurations use **D-Down = pause/resume** and **D-Up = pause/step**. Existing saved binds are preserved; the selected action shows its actual shortcut.

## 3. Frame advance

- [ ] **Pause and Step:** Press Step during normal gameplay: it should pause first. Further presses should advance one frame each. Try while airborne or beside a moving platform, then resume normal control.
- [ ] **Pause after loading:** Tap Pause or Step during loading. It should wait until Mario can move, then pause automatically. Tapping Pause again while waiting should cancel it.
- [ ] **Jumping:** Turn freecam off. Hold A and press Pause: it should pause. Press Step: Mario should jump. Later, release A and press it again between steps; the next Step should register the new press. Keeping A held should not invent extra presses.
- [ ] **Timer:** Stay paused for a few seconds. QFT should stay still with a small **TAS** beside it. Step should move the timer forward, and Resume should continue from there without adding the wait. TAS should remain until a fresh attempt.
- [ ] **Two timer displays:** Show Sunshine timer and compact QFT together during pause, Step and a state load. They should follow the same frame. Sunshine rounds to hundredths, so `11.845` can show as `11.85`. Ordinary attempts should still time normally.
- [ ] **L-based shortcuts:** If using an old L-based pause/step bind, pause airborne and resume while still holding the shortcut briefly. Mario should not unexpectedly ground-pound or immediately pause again.
- [ ] **Manual spins:** With freecam off, rotate the main stick yourself across steps and jump. There should be no Queue spin option or working spin shortcut.

Audio and some effects may continue while paused. Pause/step-assisted attempts must not earn ordinary PBs; restart for a fresh attempt.

## 4. Free camera

- [ ] Turn freecam on from live gameplay. Gameplay should pause automatically. Move with the main stick, look with the C-stick and change height with L/R. Mario should stay fixed while you position the camera.
- [ ] Change **Movement speed**, try **X** boost and toggle **Reverse sideways**. Main-stick left/right should reverse when that option changes; C-stick look should keep its direction.
- [ ] Try **Recenter**, then turn freecam off. The usual view should return and gameplay should remain paused until Resume. Resuming should restore normal control.
- [ ] Use freecam during ordinary Start pause and while frame advancing. With freecam on, inputs control the camera; turn it off before stepping Mario's jumps or spins. Warp afterward and check normal camera behavior returns.

## 5. Local input recording and replay

- [ ] Save a savestate during normal gameplay. Choose **Practice > Input replay (experimental) > Record from savestate**, close the menu and release buttons. Run, jump and spray briefly, then open the menu to stop and keep the take.
- [ ] Choose **Replay recorded inputs**. It should start from the saved state and repeat the take. Check B/Start cancels. Report any different movement or mismatch message, with the scene and actions recorded.
- [ ] Select or save another state, then replay the take: it should still use its original starting state. Replace or clear that original state, or change scenes, and check the old take refuses to play. Incompatible settings should also produce a clear refusal.

This is a short, experimental, session-only input take. It is separate from saved/shareable ghosts.

## 6. Ghost library and file management

- [ ] Complete a ghost and select an **empty personal row**. It should offer to save your latest recording. Confirm, then load it; existing ghosts should remain. **Save latest ghost** should also work. Export it, put the shared file in the import folder and scan imports; confirm it appears and plays.
- [ ] Change **Personal page** and **Imported page** with C-stick left/right. Check the first/last pages and return to an earlier entry. Names and selected actions should stay attached to the correct ghost.
- [ ] After changing pages, load/export a known ghost and delete a **disposable** one. Verify the selected file is affected and neighbouring entries remain. Cancel a deletion once and confirm the file stays.
- [ ] If you have a larger collection, check entries beyond **45 personal**, **12 imported**, or **ten hours combined** remain accessible. Use existing files; there is no need to record ten hours for this test. The roughly 15-minute limit for one recording remains.
- [ ] Switch PB profiles and check personal libraries stay separate. Existing ghosts from before this update should remain available.

## 7. Racing, Watch and TAS ghosts

- [ ] Race a saved or imported ghost. Check its movement, start timing and recorded inputs. **Ghost inputs → Both ghosts** should show your controller and the ghost's while racing.
- [ ] Select **Watch2** ghosts from different pages. Both should load correctly. Pause, Step and use freecam: the ghosts should stay together, remain still during the hold and advance together on Step.
- [ ] In Watch2, **Both ghosts** should show both recorded controllers clearly above the HUD. Opening the mod menu should keep Watch active; B/Start should exit Watch when the menu is closed.
- [ ] Record an attempt using pause/step/freecam, then save and watch it. Expect a **TAS** label, no waiting pauses in playback and no ordinary PB credit. Export/re-import it and check those properties survive.
- [ ] **Full ghost after a state load:** Record a recognisable opening, save a state, then load it and finish by a different route. The saved ghost should contain that opening and the new ending, without the discarded section. Watch and export should still work; it should be TAS with no ordinary PB credit.
- [ ] If you have an older ghost without recorded inputs or splits, it should still play and clearly show that the missing data is unavailable.

## 8. Runs, PB protection and split comparisons

- [ ] Complete a normal IL and check the result/PB records. Try an included Full Reds route if you use those. Assisted attempts should stay excluded from normal PBs.
- [ ] With an unsaved PB ghost, request a restart or warp. Check the save/protection prompt; saving should preserve the ghost before continuing. Cancelling should leave you able to decide what to do.
- [ ] Under **Runs > Timer and splits**, enable **Level splits**. On a supported route with recorded times, try Off, PB, SOB and Ghost comparison. PB compares against your best run; SOB uses your best segments.
- [ ] **Reported sharing bug:** Export a new **Bianco 3 Secret ghost on PAL** and race it on **JP** with Ghost comparison. Existing checkpoints should show differences instead of `--`. Other region pairings are useful too.

No new checkpoints were added. Missing or incompatible split data legitimately shows `--`.

## 9. Layout editor and colours

- [ ] **Sunshine timer:** Try both Appearance modes on one character. RGB changes should keep the selected mode. To restore all normal colours, choose **All → Appearance → Original**, then reset Red, Green and Blue separately with Z and confirmation. Position and size should stay unchanged.
- [ ] **Mario colours:** Try Custom white on All, then different colours on a few parts. Check clothes, gloves, shoes and sunglasses; skin should stay normal. Switch a part to Original and back to Custom. Try the Sunshine shirt if available.
- [ ] **FLUDD colours:** Try the body, tank and each nozzle, then Sprayed water and Water highlights. The stream, mist and splashes should change; the sea and Yoshi juice should stay normal. Original restores each chosen part. Kept Mario/FLUDD colours and appearance choices should survive rebooting.
- [ ] **Compact timer and controller displays:** Move/scale them and change colours, opacity and backgrounds. Per-button colours should affect the intended controller element; live and ghost panels should remain readable.
- [ ] **Metadata:** Reduce field/row gaps, change fields per row and try Stable/Compact widths. Changing numbers should stay aligned and keep their assigned colours.
- [ ] **Health and air:** Change the normal health counter and underwater air colours independently. Take damage, recover health and go underwater to check the intended meter changes.
- [ ] **Custom text and menu appearance:** Edit a text overlay and its style; it should remain visible in game. Change menu appearance and check labels remain readable. Find rollout/dust with movement feedback and check their placement.
- [ ] **Editor controls:** Hold **Y** while adjusting RGB for steps of **1 instead of 4**. Try Keep, Discard and Reset; each should apply only the intended edit or reset.

## 10. Normal practice and saving

- [ ] Play a busy level such as **Bianco 5**. Use the menu, savestate save/load, restart and warp wheel. Report crashes, freezes, new slowdown or lost controls.
- [ ] **Three states:** Save different positions in states 1, 2 and 3 under **Practice > Savestates**, then replace one and load each using Load from. The other two must stay intact. Changing Save to or Load from alone should do nothing to the scene. The slots share 17.625 MiB; longer saved ghost recordings also use that space.
- [ ] **Keeping states:** Cancel Clear once, then confirm it on a disposable state. Only that state should become Empty; the others should still load. If a save reports insufficient space, every earlier state—including the one you tried to replace—should remain usable.
- [ ] Save your edits and reboot once. Check binds, camera options, layouts, custom text, records and saved/imported ghosts remain correct for your region/profile. The three memory slots start Empty; separately saved SD states should remain in the SD list and can be imported again.

## Results to send back

**Sections/items checked:**  
**Passed:**  
**Problems:** item number, level/episode, steps to reproduce, expected result and what happened.  
**Attachments:** clip/photo, affected ghost or crash report files if available.

Mark anything you could not check as **Not tested**. A clear report of what worked is useful too.
