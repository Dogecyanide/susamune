# Moonshine Launcher FOXTROT — final test checklist

**V2.3.0 pre-release · Build 08BDB4CD**

**Only the four checks below are requested for this update.** Keep successful earlier results. The later sections are a reference for anything still marked Not tested; they are not a request to repeat the whole checklist. Use the complete package so the launcher and game files match.

This pass focuses on the new IL episode choices, held Load, crowded-memory SD loading and handmade splits. The checkpoint tables below are a reference for dividing routes among testers.

**Tester:**  
**Platform:** Wii / Wii U / Dolphin — version:  
**Game region:** JP / US / PAL  
**Game source:** Disc / ISO / CISO — SD / USB

## Start here — latest changes

- [ ] **Choose an IL episode:** In **Runs > ILs**, press **Z** on a 100-coin, supported Hidden or Full Reds row. Pick a different episode, press A, and start it. Confirm the right episode loads and the intended Shine still finishes that IL. Reboot once and check your choice remains. Also cancel one edit with B: the old choice should remain.
- [ ] **Hold Load:** Make a state in your usual practice spot. Load it and keep the shortcut held: Mario should stay still until release, with no repeated reloads. Then try once while already practice-paused: releasing Load should leave it paused, and Step should still work.

  If your state is saved during an intro, let the intro finish while holding Load: it should stop on Mario's first controllable frame. Releasing early lets play continue, unless you had practice pause on already.
- [ ] **SD load with three saved slots:** Make a fresh SD state from this build, keep three memory states saved in that same level/setup, and load the SD file using **Y** then your Load shortcut. Afterward, load each memory slot and confirm they all remain. Report a refusal exactly as shown. There is no need to unplug the SD or damage a file. On the next normal launch, also note whether startup feels quicker and whether its text/theme remain visible.
- [ ] **Pick a few new split routes:** Enable **Runs > Timer and splits > Level splits** and choose routes from the [checkpoint reference below](#new-checkpoint-reference). Each listed event should advance the display once, in order, and the finish should complete it. A Full Reds route should retain its approach checkpoints after entering the secret. Tell us the route and first missing, early or repeated split. Nobody needs to cover every route alone.

SD files are in `/moonshine_states` on the launcher's device. Use the same build, region, launcher setup, level and episode; secrets also need the same parent episode. Keep the device connected until the operation finishes. If a read fails during restoration, the game should report the memory slot it restored for recovery. All three saved slots must remain.

Standalone Dolphin BPS builds do not provide SD states; mark that part **Not available** and test the memory slots normally.

## Previous update — 00B63258, reference only

These checks are retained for unfinished reports; successful results do not need repeating.

- [ ] **Guide on the TV:** Choose **Guide** on the launcher home screen. Open a topic with A, scroll with Up/Down, turn a page with Left/Right and return with B. The text should fit and remain readable with your theme.
- [ ] **Input replay:** Turn **Save RNG state** On and make a fresh gameplay state. Under **Practice > Input replay**, choose **Record from savestate**, then release the confirming A button. Walk and jump briefly, open the menu to stop recording, and replay it a few times. Mario should stop immediately when the menu opens, and replay should start consistently. If it stops or refuses, send the exact message and what you recorded.
- [ ] **Save/load waits:** In your usual practice level, save and load a few times. With three states saved, move elsewhere and overwrite one slot, then load each slot. The other states should still restore correctly. Tell us whether saving and loading feel faster; if a save cannot fit, the old states must remain usable.
- [ ] **One fresh SD round trip:** Save a state from this build to SD. Reboot into the same setup and level/episode, select that file with **Y**, then use your Load shortcut. It should restore correctly. This checks the new saved format; previously successful SD file-management tests do not need repeating.

SD files are in `/moonshine_states` on the launcher's device. Use a state made with the same build, region, launcher setup, level and episode; secret areas also need the same parent episode. Loaded resources must match too. Keep the device connected until a transfer or cancellation finishes. There is no need to deliberately damage files or interrupt writes.

Standalone Dolphin BPS builds do not provide SD states; mark those items **Not available** and test the memory slots normally.

## Earlier features — reference only

The checks below are retained for unfinished testing and future bug reports. Successful checks stay complete.

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

- [ ] Turn **Save RNG state** On and save a fresh state during normal gameplay. Choose **Practice > Input replay (experimental) > Record from savestate**, then release the confirming A button. Run, jump and spray briefly, then open the menu to stop and keep the take.
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

Those earlier builds used the existing checkpoints. The new checkpoint reference below applies to this update. Missing or incompatible comparison data still legitimately shows `--`.

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

## New checkpoint reference

**Pick routes you already know; this is not a checklist to complete alone.** Read each row from left to right. The normal IL finish comes after the listed checkpoints. “Reds 2 / 5 / 8” means the red-coin counter reaching 2, then 5, then 8. Each should count once. Full and inside-only entries are separate routes.

### Bianco and Ricco

| Route | Checkpoints before the finish |
|---|---|
| Bianco 1 | Roll out over the wall → first, second and third plant hits |
| Bianco 3 Reds | Reds 2 / 5 / 8 |
| Bianco 6 Reds | Reds 3 / 6 / 8 |
| Bianco 8 | Reds 2 / 5 / 8 |
| Ricco 4 Reds | Reds 1 / 4 / 6 / 8 |
| Ricco 8 | Mount Yoshi **or** collect the Rocket Nozzle; either starts the same single split |

### Gelato

| Route | Checkpoints before the finish |
|---|---|
| Gelato 1 Full | Make the sandcastle appear → enter the secret → cross the two approach markers inside |
| Gelato 1 Secret | Cross those two inside approach markers |
| Gelato 1 Reds | Reds 3 / 5 / 8 |
| Gelato 2 | Clear mirrors 1 / 2 / 3 |
| Gelato 3 | Land the first, second and third successful boss ground pounds |
| Gelato 4 Full | Collect Rocket Nozzle → enter the secret → reds 2 / 7 / 8 |
| Gelato 4 Inside | Reds 2 / 7 / 8 |
| Gelato 5 | Talk to Piantissimo |
| Gelato 6 | Reds 1 / 4 / 8 |

For the Gelato 1 inside markers, follow the normal forward route: they are the two requested X-position crossings, 6400 then 13560. Backtracking should not add repeats.

### Pinna

| Route | Checkpoints before the finish |
|---|---|
| Pinna 1 | Talk to the Noki at Mecha-Bowser → boss hits 1 / 2 / 3 / 4 |
| Pinna 2 Reds | Reds 2 / 5 / 7 |
| Pinna 6 Full | Mount Yoshi → enter the secret → start the existing inside rail |
| Pinna 6 Reds | Reds 2 / 3 / 6 / 8 |
| Pinna 8 | Talk to the balloon-ride Noki → balloons 6 / 11 / 20 |

### Sirena, Noki and Pianta

| Route | Checkpoints before the finish |
|---|---|
| Sirena 2 Reds | Press the red-coin switch → reds 3 / 5 / 6 / 8 |
| Sirena 4 Reds | Reds 3 / 6 / 8 |
| Sirena 8 | Reds 2 / 3 / 6 / 8 |
| Noki 6 Reds | Press the red-coin switch → reds 2 / 4 / 6 / 8 |
| Noki 8 | Enter the underwater area → red coin 8 |
| Noki Hidden | Launch from the spring pad under the gold bird → make the gold bird’s Shine appear |
| Pianta 5 Reds | Reds 2 / 3 / 6 / 8 |
| Pianta 8 | Reds 2 / 4 / 6 / 8 |
| Pianta Hidden | Rise through the requested height marker, Y 9700 |

### Full Reds

The approach stays part of the run after entering the secret. Use the default starting episode first; episode-choice testing can be a separate attempt.

| Route | Checkpoints before the finish |
|---|---|
| Bianco 3 Full Reds | Enter secret → reds 2 / 5 / 8 |
| Bianco 6 Full Reds | Enter secret → reds 3 / 6 / 8 |
| Ricco 4 Full Reds | Existing approach spin jump → enter secret → reds 1 / 4 / 6 / 8 |
| Gelato 1 Full Reds | Make sandcastle appear → enter secret → reds 3 / 5 / 8 |
| Pinna 2 Full Reds | Enter secret → reds 2 / 5 / 7 |
| Pinna 6 Full Reds | Mount Yoshi → enter secret → reds 2 / 3 / 6 / 8 |
| Sirena 2 Full Reds | Talk outside → enter secret → press red-coin switch → reds 3 / 5 / 6 / 8 |
| Sirena 4 Full Reds | First talk → second talk → enter secret → reds 3 / 6 / 8 |
| Noki 6 Full Reds | Cross the existing Y 4000 approach marker → enter secret → press red-coin switch → reds 2 / 4 / 6 / 8 |
| Pianta 5 Full Reds | Existing approach spin jump → enter secret → reds 2 / 3 / 6 / 8 |

Sirena 2 and Noki 6 Full Reds use all eight segments once their finish is included. Their final rows should stay visible and complete normally.

### Shared route types

| Routes | Checkpoints before the finish |
|---|---|
| Main-course 100 coins: Bianco, Ricco, Gelato, Pinna, Sirena, Noki, Pianta | Coins 10 / 25 / 50 / 75 / 100, in the chosen episode |
| Shadow Mario: Delfino, Bianco 7, Ricco 7, Gelato 7, Pinna 7, Noki 7, Pianta 7 | Actually start talking to Shadow Mario after catching him. Merely standing nearby should not split. |
| Sirena 7 | Talk outside → actually talk to Shadow Mario inside |
| Airstrip opening | Begin the FLUDD cutscene → plant hits 1 / 2 / 3 |
| Bianco Plant, Gelato Plant, Travel Skip | Plant hits 1 / 2 / 3 |

### Plaza and bonus areas

| Route | Checkpoints before the finish |
|---|---|
| Airstrip Reds | Reds 2 / 4 / 6 / 8 |
| Pachinko | Reds 4 / 6 / 8 |
| Lily Pad | Reds 2 / 4 / 6 / 8 |
| Grass Secret | Reds 2 / 4 / 6 / 8 |
| Lighthouse, Left Bell, Beach Shine, Gold Bird | Make that route’s Shine appear |
| Right Bell, Shine Gate | Collect Rocket Nozzle → make that route’s Shine appear |
| Sirena Enter | Mount Yoshi |

**Cop Secret stays inside-only with no intermediate split.** Slide, Box Game 1/2, Chuckster, Delfino 100, Underbell and the other Enter routes also retain their finish without new intermediate checkpoints. The remaining unchanged routes do not need another pass solely for this update.

## Results to send back

**Sections/items checked:**  
**Passed:**  
**Problems:** item number, level/episode, steps to reproduce, expected result and what happened.  
**Attachments:** clip/photo, affected ghost or crash report files if available.

Mark anything you could not check as **Not tested**. A clear report of what worked is useful too.
