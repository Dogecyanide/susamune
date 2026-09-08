# Moonshine Launcher FOXTROT — final test checklist

**V2.3.0 pre-release · Build 5B0EC1B1**

This is the complete reference checklist. **Start with the latest changes below, then anything you previously marked Not tested. Keep earlier results; successful older checks do not need repeating.** Use the full package so the launcher and game files match.

**Tester:**  
**Platform:** Wii / Wii U / Dolphin — version:  
**Game region:** JP / US / PAL  
**Game source:** Disc / ISO / CISO — SD / USB

## Start here — latest changes

- [ ] **Mario colours:** In **Display > Appearance > Mario appearance > Mario colours**, try All in Custom white, then give a few parts different colours. Check the cap, clothes, gloves, shoes and sunglasses; skin should stay normal. Return a part to Original, then Custom. Try the Sunshine shirt if available.
- [ ] **FLUDD colours:** On the same page, open **FLUDD colours**. Try white and a strong colour on the body, tank and nozzle parts, then switch between spray, hover, rocket and turbo. Try Sprayed water and Water highlights while spraying: the stream, outlet mist and impact splashes should change, while the sea and Yoshi juice stay normal. Original should restore each chosen part.
- [ ] **Two timer displays:** Show Sunshine timer and compact QFT together. Pause, Step a few times, save/load a state, then resume. They should follow the same frame; the Sunshine timer rounds to hundredths, so `11.845` can display as `11.85`. Ordinary attempts should still time normally. Both timer appearance modes should remain usable.
- [ ] **A full ghost after loading:** Start a fresh level and record a recognisable opening. Save a state partway through, continue briefly, load it and finish by a different route. Save and Watch the ghost: it should include the original opening and your new ending, without the discarded section or long frame-advance waits. It should say TAS, export normally and receive no ordinary PB credit.
- [ ] **Three states and replacement:** Save different positions in all three slots, then replace one and load all three. The other two must stay intact. If a save reports insufficient space, all previous states must still work. The slots share 17.625 MiB; longer saved ghost recordings also use this space.
- [ ] **SD state after power-off — main hardware check:** Save a memory state, open **Practice > Savestates > SD states**, and choose **Save selected state to SD**. Wait for completion. Fully turn off the console, boot the same package and game setup, and enter the same level/episode. Choose an active memory slot, refresh the SD list and import the file; then use your normal Load action. Check Mario's position, health/water, camera and timers, then play, save/load again and leave the level. Report the exact scene and any refusal message. This still needs real Wii/Wii U verification.
- [ ] **SD choices and saved colours:** Cancel an import once; the current memory state and SD file should stay. An incompatible level/episode should give a clear refusal and preserve existing states. After the reboot above, confirm your kept Mario/FLUDD colours and Original/Custom choices survived. A file from another build, region or launcher setup is not expected to load.

SD files are in `/moonshine_states` on the launcher's device. Keep the device connected until a transfer or cancellation finishes. Matching level names alone may not be enough: the loaded resources must also be compatible. There is no need to deliberately damage files or interrupt writes.

Standalone Dolphin BPS builds do not provide SD states; mark those items **Not available** and test the memory slots normally.

## 1. Launcher and startup

- [ ] **Early text and theme:** Start the launcher with your usual theme. Check the theme appears during startup and all text is readable **before loading finishes**, including progress and error messages. Note any blank-text period or stock-background flash.
- [ ] **Launching:** Select your region and usual disc/ISO/CISO, then launch successfully. If using theme music, check it starts and plays normally.
- [ ] **Auto Boot:** Check it starts the selected game. On another launch, hold B and confirm you can return to the launcher menu.

## 2. Menus and button binds

- [ ] Browse **Quick, Practice, Runs, Ghosts, Display and System**. Enter and leave their submenus; labels should fit and holding A while entering a page should not activate its first action.
- [ ] Under Practice, find the separate **Frame advance**, **Free camera** and **Input replay (experimental)** pages. Select an action, press **X** to change its shortcut, then use it. Finishing or cancelling the bind recorder should not trigger another action or switch tabs.
- [ ] Check existing custom binds still work. Try a setting available in two places and confirm both show the same value. Add/remove a Quick favourite and check it opens the intended feature.

New configurations use **D-Down = pause/resume** and **D-Up = pause/step**. Existing saved binds are preserved; the selected action shows its actual shortcut.

## 3. Frame advance

- [ ] **Pause and Step:** Press Step during normal gameplay: it should pause first. Further presses should advance one frame each. Try while airborne or beside a moving platform, then resume normal control.
- [ ] **Pause after loading:** Tap Pause or Step during loading. It should wait until Mario can move, then pause automatically. Tapping Pause again while waiting should cancel it.
- [ ] **Jumping:** Turn freecam off. Hold A and press Pause: it should pause. Press Step: Mario should jump. Later, release A and press it again between steps; the next Step should register the new press. Keeping A held should not invent extra presses.
- [ ] **Timer:** Stay paused for a few seconds. QFT should stay still with a small **TAS** beside it. Step should move the timer forward, and Resume should continue from there without adding the wait. TAS should remain until a fresh attempt.
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
- [ ] If you have an older ghost without recorded inputs or splits, it should still play and clearly show that the missing data is unavailable.

## 8. Runs, PB protection and split comparisons

- [ ] Complete a normal IL and check the result/PB records. Try an included Full Reds route if you use those. Assisted attempts should stay excluded from normal PBs.
- [ ] With an unsaved PB ghost, request a restart or warp. Check the save/protection prompt; saving should preserve the ghost before continuing. Cancelling should leave you able to decide what to do.
- [ ] Under **Runs > Timer and splits**, enable **Level splits**. On a supported route with recorded times, try Off, PB, SOB and Ghost comparison. PB compares against your best run; SOB uses your best segments.
- [ ] **Reported sharing bug:** Export a new **Bianco 3 Secret ghost on PAL** and race it on **JP** with Ghost comparison. Existing checkpoints should show differences instead of `--`. Other region pairings are useful too.

No new checkpoints were added. Missing or incompatible split data legitimately shows `--`.

## 9. Layout editor and colours

- [ ] **Sunshine timer:** Set **All → Appearance → Original** to restore its normal look. Switch one character to Custom and try white, blue or purple; the others should stay original. Returning it to Original should keep its saved colour and position for later. Save and reboot once to check the choice sticks.
- [ ] **Compact timer and controller displays:** Move/scale them and change colours, opacity and backgrounds. Per-button colours should affect the intended controller element; live and ghost panels should remain readable.
- [ ] **Metadata:** Reduce field/row gaps, change fields per row and try Stable/Compact widths. Changing numbers should stay aligned and keep their assigned colours.
- [ ] **Health and air:** Change the normal health counter and underwater air colours independently. Take damage, recover health and go underwater to check the intended meter changes.
- [ ] **Custom text and menu appearance:** Edit a text overlay and its style; it should remain visible in game. Change menu appearance and check labels remain readable. Find rollout/dust with movement feedback and check their placement.
- [ ] **Editor controls:** Hold **Y** while adjusting RGB for steps of **1 instead of 4**. Try Keep, Discard and Reset; each should apply only the intended edit or reset.

## 10. Normal practice and saving

- [ ] Play a busy level such as **Bianco 5**. Use the menu, savestate save/load, restart and warp wheel. Report crashes, freezes, new slowdown or lost controls.
- [ ] **Three states:** Save different positions in states 1, 2 and 3 under **Practice > Savestates**. Select and load each; Mario, health/water and the camera should return correctly. Changing Active state alone should do nothing to the scene. If you assign **Savestate: cycle states**, check it changes the selection too.
- [ ] **Keeping states:** Cancel Clear once, then confirm it on a disposable state. Only that state should become Empty; the others should still load. If a save reports insufficient space, every earlier state—including the one you tried to replace—should remain usable.
- [ ] Save your edits and reboot once. Check binds, camera options, layouts, custom text, records and saved/imported ghosts remain correct for your region/profile. The three memory slots start Empty; separately saved SD states should remain in the SD list and can be imported again.

## Results to send back

**Sections/items checked:**  
**Passed:**  
**Problems:** item number, level/episode, steps to reproduce, expected result and what happened.  
**Attachments:** clip/photo, affected ghost or crash report files if available.

Mark anything you could not check as **Not tested**. A clear report of what worked is useful too.
