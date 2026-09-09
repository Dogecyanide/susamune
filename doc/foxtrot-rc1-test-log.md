# Moonshine 2.3.0 — RC1 test log

**FOXTROT candidate · Build 1CF3F641**

This is the full RC1 check, covering new features and normal practice. `TESTING.md` is the shorter latest-fixes sheet. `RC1_ROUTES.md` lists the expected checkpoints for the course tests below.

## How to split the work

Choose sections and courses you can test. **One clear pass is enough.** Reuse the same normal run, assisted run, ghosts and states across sections. Do the final reboot once to check everything you saved together. Mark **Pass / Problem / Not tried**, with an item number for problems.

Across the team, cover JP, US and PAL; Wii, Wii U and a current Dolphin; and the SD, USB or disc setups people actually use. Each tester can use their usual setup. Dolphin has memory states but no launcher SD-state service, so mark those checks Not available.

Dolphin testers: enable a memory card in slot B for mod settings, and set Texture Cache Accuracy to Safe for goop restoration after state loads.

**Tester:**

**Platform / Dolphin version:**

**Game region:** JP / US / PAL

**Game source:** Disc / ISO / CISO — SD / USB

**Sections and courses claimed:**

## 1. Launcher, menus and settings

- [ ] **1A — Startup.** Open the updated launcher with your usual theme and music. Text must be readable before loading finishes, including any storage wait. The theme should appear early. An SD-only setup should not wait for an unused USB drive.
- [ ] **1B — Remembered game.** Launch your usual version. If you own another supported version or use another storage device, select it and launch it once. Returning to the first selection should keep its path. An incorrect game/version selection should give a readable error.
- [ ] **1C — Auto Boot and Guide.** If you use Auto Boot, check normal boot and holding B to reach the menu. Open the launcher's **Guide**, read a topic, turn a page and back out successfully.
- [ ] **1D — Menu navigation.** Browse Quick, Practice, Runs, Records, Ghosts, Display and System. Records should also open from Runs. Enter/back out of submenus; the A used to open a page must not also trigger an action inside it. Add and remove a Quick favourite. Check one duplicated setting shows the same value in both locations.
- [ ] **1E — Binds and saving.** Assign one shortcut from a Practice page with X, and check it under System > Button binds. Try cancelling a bind edit too. Existing shortcuts should remain. Close the menu after changing a setting: no false “storage access denied” error. Leave a harmless change saved for the reboot check.
- [ ] **1F — Japanese version.** JP testers: check launcher and game menus, corrected wording, long setting/bind names and button labels for missing characters or overlapping text. Check the Japanese download's flag fits with a round circle. Some changing status messages and diagnostics, plus the launcher's built-in guide, still use English; report other missing translations.

Themes now use **/Moonshine_Theme** at the root of the launcher's device. The Japanese download includes its flag there; the standard download keeps your own theme. Selecting JP does not switch backgrounds.

## 2. Normal runs, records and PB protection

- [ ] **2A — A normal IL.** Start a familiar route through **Runs > ILs** and finish normally. Check its result, PB if improved, attempt/finish counts and recent history. The QFT must start, run and stop normally. With both timer displays shown, their times should agree after allowing for Sunshine's rounding: `11.845` can display as `11.85`.
- [ ] **2B — Timer controls.** Toggle one QFT event freeze, such as coin or Talk, and check the displayed freeze follows it without freezing gameplay. Check QFT visibility, leading zero and section history if you use them.
- [ ] **2C — PB Safety.** With a completed PB ghost still unsaved, request a restart/warp. Check the protection prompt: cancel keeps your choice open; saving preserves the ghost before continuing. Practice-assisted runs must not replace an ordinary PB. Restart into a fresh normal attempt and check normal PB recording becomes available again.
- [ ] **2D — Records and profiles.** Open achievements and statistics from Records and its Runs shortcut. Existing records should remain. Switch to another profile and back; its PBs and ghosts should stay separate. Use a spare profile for a delete/reset check: cancel once, then delete one disposable PB or segment record and check neighbouring records remain.
- [ ] **2E — Playlists and streaks.** Try a two-entry playlist and a short streak challenge. Finishing should advance/count correctly; a failed attempt or reset should follow the selected streak rule. Ending the session should return normal menu and warp control.

## 3. Frame advance, free camera and timers

- [ ] **3A — Pause and Step.** From live gameplay, press Step to pause, then advance a few frames and resume. During the hold, QFT stays still; each Step advances one frame of game time. There should be a small **TAS** label, with no paused waiting time added when you resume. Check both timer displays follow the same frame, including after the state load in section 4.
- [ ] **3B — Held inputs and spins.** With freecam Off, hold A when starting Pause, then Step to jump. Release and press A again between later steps; that new press must register. Turn the main stick yourself across steps for a spin. Holding a button must not create repeated new presses. There should be no Queue spin option.
- [ ] **3C — Pause ready for control.** Tap Pause/Step during a level intro or loading. It should pause on Mario's first controllable frame. On another transition, cancel the waiting pause and check play continues normally. If Pause is D-Up and Reset is B+D-Up, hold B then press D-Up: reset must not also pause or mark the new attempt TAS. Testers with an L-based shortcut should check it does not cause an unwanted ground-pound.
- [ ] **3D — Camera controls.** Turn freecam on from gameplay: Mario pauses. Check movement, looking, height, Movement speed, X boost and Reverse sideways. Recenter and Off should restore the usual view; Resume restores Mario's controls. With Camera On, movement buttons belong to the camera; turn it Off before stepping Mario's jump.
- [ ] **3E — Camera in pause.** Use it in ordinary Start pause and while stepping, then leave the area. The normal camera should return. Check camera use during Ghost Watch in section 7 rather than repeating this whole exercise there.

## 4. Three memory states

Use three recognisably different positions in the same level and episode.

- [ ] **4A — Independent selections.** Save State 1, 2 and 3. Set Save to 1 and Load from 2: saving changes only 1, loading restores 2. Include one visible game change—coin, health, enemy or cleaned goop—to check it restores too. Selecting a slot alone should not change the scene. If you assign cycle-save/cycle-load shortcuts, each must change only its own selection; these start unassigned on a fresh setup.
- [ ] **4B — Replace and clear.** Replace one state, then load the three positions to check the other two survived. Cancel Clear once, then clear a disposable state; only the Save to slot becomes Empty.
- [ ] **4C — Hold Load.** Hold the Load shortcut: after restoration, gameplay should stay still until you release it, without an extra message across the bottom. With practice pause already On, release should keep that pause and Step should still work. Timers and Mario's position should return together.
- [ ] **4D — Busy scene and speed.** In a busy scene you practise, save, replace and load a state. Note whether the waits feel reasonable and report any new freeze, crash or slowdown. If a crowded save refuses for lack of room, all previous states—including the attempted replacement—must still load. No need to manufacture a failure if it fits.

Keep a state with a short, recognisable ghost recording in progress for the continuation check in section 7.

## 5. SD states — console testers

Use states from this build and the same region, setup, level and episode. Secret areas also need the same parent episode.

- [ ] **5A — Names and file actions.** Save a memory state to SD, enter a name and confirm with Start. Rename it. On a disposable copy, cancel X/Delete once, then delete it. The correct file should change; your other SD and memory states should remain.
- [ ] **5B — Y selects the Load source.** With all three memory slots occupied, highlight an SD state and press Y. Close the menu and use Load. The SD state should restore while the three memory states remain usable. Save another memory state and press Load again: the selected SD file should still be the source. Include a crowded/busy-scene file among the team's checks. When memory is full, keep at least one usable memory state for the current scene/setup as a recovery point; otherwise a safe lack-of-space refusal can be expected.
- [ ] **5C — A imports.** Set Save to 3 and Load from another slot or SD file. Press A on an SD file: cancel once, then confirm import. Only State 3 should be replaced; Load from must keep its choice. Select 3 to use the imported state.
- [ ] **5D — Wrong episode.** Try loading a state while in a different episode. It should refuse clearly and leave the game and saved states usable. Return to the correct episode to use it. Check restoration after reboot in section 11.

Keep the SD connected during transfers. Testing does not require corrupting files or pulling the card mid-save.

## 6. Local input recording and replay

This is the short experimental take under **Practice > Input replay**, separate from saved ghosts.

- [ ] **6A — Start from the menu.** Turn Save RNG state On and make a fresh memory save during gameplay. Choose Record from savestate, then release the A used to confirm. A different held gameplay button should not prevent starting. Walk, jump and spray briefly; open the menu to stop and keep the take.
- [ ] **6B — Replay and stop.** Replay the take: it should reload the starting state and repeat the sequence. Check B/Start can stop playback. Report an unexpected refusal or mismatch with the exact message and what was recorded.
- [ ] **6C — Correct starting state.** Select or save another slot, move the Sunshine timer or change metadata layout, then replay again. It should still use the take's original state. Replacing/clearing that original state or changing scenes should make the old take unavailable. A gameplay setting that no longer matches should produce a clear explanation.

## 7. Ghosts, sharing and TAS continuation

Reuse the normal IL from section 2 and the assisted run/state from sections 3–4.

- [ ] **7A — Save and browse.** Complete a recording and choose an empty personal ghost row: it should offer to save there. Check Save latest ghost too when you have another recording. Browse pages, return to a known entry, and cancel/delete one disposable ghost. Names, playback and file actions must refer to the selected ghost.
- [ ] **7B — Race and inputs.** Race a saved/imported ghost. Check its start, movement and recorded input display. Both ghosts should show the live and ghost controller while racing. Ghost display Off must hide the ghost and its inputs; On restores the chosen input mode. Your separate input overlay stays independent.
- [ ] **7C — Watch2.** Select two ghosts, from different pages if available. Pause, Step and move freecam: both playheads stay together and omit the waiting time. Both ghosts shows both recorded controllers. Opening the mod menu keeps Watch active; B/Start exits Watch when the menu is closed.
- [ ] **7D — Full TAS ghost after loading.** Record a recognisable opening, save a state, go farther, load the state and finish with a different continuation. Save and watch it. Expect the original level opening plus the new ending, with the discarded ending gone. Paused time is omitted, it is marked TAS, and it earns no ordinary PB. Export/import should keep that result.
- [ ] **7E — Sharing and deltas.** Export a fresh ghost and have another tester import and race it on the same IL with Ghost comparison. Across the team, include **PAL → JP Bianco 3 Secret**, the reported failure. Compatible checkpoints should show a delta instead of `--`. Also check PB and SOB comparison using fresh recorded splits. Old/mismatched files may legitimately lack split or input data.
- [ ] **7F — Existing libraries.** Testers who already have older ghosts or large libraries: check an old ghost still plays, and entries beyond 45 personal / 12 imported / ten hours total remain accessible. Use existing collections; nobody needs to record hours to fill a quota.

## 8. Layout editors, colours and visual helpers

Exercise the shared Keep, Discard, Reset and Y-for-fine-RGB controls once, then check each target below. Y should adjust RGB by 1 instead of 4.

- [ ] **8A — Sunshine timer.** Move it to the screen edges and resize it. Mix Original and Custom on individual characters, TIME and streak. RGB changes must keep the selected mode. Custom should give readable white, blue and magenta; Original deliberately keeps the retail shading. Restoring original colours must not reset its position/size.
- [ ] **8B — Compact QFT and controllers.** Move/style the compact timer and controller panels. Check per-character/per-button colours, opacity and backgrounds affect the intended parts. Sticks and analog triggers should reflect the inputs you use.
- [ ] **8C — Metadata.** Reduce field/row gaps, arrange several fields horizontally and try Stable/Compact widths. Let a number gain a digit: spacing should remain usable and colours must stay attached to the correct field.
- [ ] **8D — Native HUD and text.** Change normal health and underwater air colours independently; check damage/recovery and swimming. Spot-check the other HUD targets you use. Edit custom text and its style, and menu/notification appearance. The text should remain visible. Rollout/dust editors should be with movement feedback and keep their chosen positions.
- [ ] **8E — All Mario parts.** Check cap, shirt, overalls, gloves, shoes, sunglasses and Sunshine shirt. Change each visible part, then switch a part Original → Custom. Skin and intended details should remain normal. In particular, inspect a magenta cap/shirt for stray red specks.
- [ ] **8F — All FLUDD parts.** Check body paint, metal, straps, tank, spray/hover/rocket/turbo nozzles, sprayed water and water highlights. Use the relevant nozzle to see it. Water colour should affect the stream, mist and splashes; world water and Yoshi juice keep their usual colours.

## 9. Existing practice features

Divide these options among testers who use them; one useful example per feature is enough.

- [ ] **9A — Movement and warps.** Use the warp wheel, restart and instant restart, Exit Area and area lock. Check normal controls return after menus/pauses. Spot-check save/load position and your other frequently used action shortcuts.
- [ ] **9B — Gameplay helpers.** Check your usual FLUDD-in-secrets/nozzle lock, Yoshi/fruit, fast text and intro/shine skip options. Turn a changed option back Off/Original and check normal behaviour returns. Startup options apply on the next boot. Note the specific options tested.
- [ ] **9C — Patterns.** Try a pattern or RNG option in a course you know, then return it to normal. Across the team, cover the existing Petey, King Boo, Piantissimo, Ricco machinery and Gelato options. Check PB Safety still recognises practice-affecting choices.
- [ ] **9D — Visual aids and counters.** Spot-check rollout, dust, wallkick, attempts/session display, hidden-item markers, enemy hurtboxes and Ricco 2 checkpoints where relevant. Each should show the intended information and disappear when switched Off. Record which aids you checked.

## 10. ILs, episode choices and handmade checkpoints

**Start routes through Runs > ILs.** Enable Runs > Timer and splits > Level splits. Divide `RC1_ROUTES.md` by course and record the route, episode, region and result there. One completion per assigned route is enough. A Full Reds run can also cover that secret's internal red-coin checks.

- [ ] **10A — Course coverage.** Check each assigned route's checkpoints happen once, in order, at the listed event. The finish and stored segment times should agree. Include old working boss/secret transitions and routes with no intermediate split, which should still finish normally.
- [ ] **10B — Episode picker.** Across the team, choose one 100-coin IL, one Hidden and one Full Reds. Use Z to choose an episode; check cancel, keep, launch and restart. Include a Pinna/Sirena route with an area transition. Only supported ILs should offer this choice; keep it for the reboot check.
- [ ] **10C — Pinna 1 priority.** Assign a normal movie route and the usual two Exit Area skips to separate runs/testers. Expect Talk, four Mecha-Bowser hits and finish, with progress retained through the transitions. Report the first missing checkpoint and which skip route you used.
- [ ] **10D — Other repaired events.** Assign Gelato 5 Talk, Sirena 2 Reds/Noki 6 Reds button presses, Noki Hidden's launch then bird, and the Spawn Shine routes. Button splits should happen on the press. Shadow Mario splits should happen on actual Talk, not merely when he becomes talkable.

## 11. One final reboot and report

- [ ] **11A — Persistence.** Reboot once after saving the checks above. Confirm kept settings, binds, camera speed/direction, layouts, custom text, Mario/FLUDD colours, episode choices, records/profiles and ghosts remain correct. Check an earned achievement if you earned one during the session.
- [ ] **11B — States after reboot.** The three memory slots should start Empty. Console: the named SD state should still be listed. Enter its matching level/episode, select it and restore it successfully. Its saved ghost opening should still be usable for a TAS continuation.
- [ ] **11C — Ordinary play.** Finish with a short normal practice session. Report a new crash, slowdown, stuck input or camera problem, including the last action before it happened.

**Items passed:**

**Items not tried / not available:**

**Problems:** item number; route/episode; what you pressed; what happened; what you expected.

**Clip/photo or affected ghost/state/crash report:** attach if available. Keep the on-screen build checksum with the report.
