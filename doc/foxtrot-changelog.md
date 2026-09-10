# Moonshine Launcher FOXTROT — full-level TAS update

**V2.3.0 pre-release · Build C34FF061**

- TAS recordings continue through normal area changes. Loading time does not consume recorded-input frames. Unsupported transitions stop the take but keep it available to save; limits remain 4096 input frames and 32 area changes.
- Save TAS stores the entire input recording with its Beginning and existing checkpoints. It no longer creates a current-position checkpoint or requires another free memory slot.
- Open TAS keeps the full recording. A compatible selected checkpoint or Beginning opens paused with later inputs retained for Replay. If no point matches the current area, the recording opens without moving Mario. Other-area checkpoint and Replay messages tell you where to return first.
- Newer named settings can be Shined, including Movement speed, Reverse sideways, Look sensitivity and Hide all HUD. Earlier favourites are preserved.
- Make new states and TAS projects with this build. Keep older files with their matching older build; settings, records and ghosts remain usable.

The four current checks are in **TESTING.md**. Keep earlier RC1 results and use the full log only for gaps in team coverage. A short US Dolphin TAS crossed Bianco 3's actual secret entrance and replayed to the exact recorded endpoint. The new SD save/reopen workflow still needs console testing; earlier successful proofs below are historical.

## Earlier RC1 feedback — C66EEB34

**V2.3.0 pre-release · Build C66EEB34**

- **Advance accepts jump-dives.** While practice is paused, A+B and other held gameplay buttons cannot block Advance or turn it into a reset. Each fresh press advances once. Normal reset shortcuts keep working outside practice pause.
- **TAS controls stay together.** Pause / Resume and Advance now let you change their binds directly with X, or clear them with Z. The separate two-row Frame advance page is removed.
- **Optional TAS shortcuts.** Beginning, Save/Go to Checkpoint 1 and 2, Continue and Replay can all have their own binds. All seven start unassigned and can be edited beside the action.
- **Confirm checkpoint replacement.** Saving over a checkpoint asks first, including when using a shortcut. Cancel keeps it. Save TAS still updates the named SD project directly.
- **A visible recording limit.** The project name now shows recorded frames out of 4096.
- **Sound effects after a paused load.** Loading a gameplay state from Sunshine's normal pause screen now releases its retained sound-effect mute. Loading a paused state keeps the appropriate pause audio. Music is not restarted by this fix.

- **A new TAS screen.** Practice > TAS projects has New TAS, Continue, Replay, Save TAS, Open TAS and Checkpoints. New TAS captures its Beginning automatically. Two named checkpoints let you go back and replace a continuation without keeping track of slot numbers.
- **Save the whole TAS together.** Save TAS keeps the current point, Beginning and checkpoints under one name on SD. Open TAS brings them back together, including after rebooting into the matching setup. No separate start/checkpoint imports. Inputs remain experimental and limited to 4096 frames; build, region, scene and settings still need to match.
- **More room for states.** If a new state will not fit, Moonshine can compress older states more tightly while keeping their contents and identities. It only does this when needed. There is still a shared memory limit; a refusal keeps your existing states.
- **New SD states are required.** The state format now includes the used input recording and controller state. Earlier SD states must be resaved with this build. Your settings, records and ghosts remain usable.
- **Separate camera turning speed.** Look sensitivity adjusts C-stick turning from 0.25x to 4x independently of Movement speed. Hide all HUD hides game and Moonshine overlays while filming, with the menu still accessible. Both settings can be kept for your next boot.
- **State failures stay visible.** Turning successful save/load messages Off no longer hides errors. A reported Japanese State 3 failure has not been reproduced as a slot-specific bug; send the exact message if it happens again.
- **Japanese wording and readability.** Applied all 25 new wording amendments, translated the new camera/TAS controls, and made small help brighter and easier to read. The in-game Guide now fits its panel, avoids missing separator symbols and explains checkpoint recording.
- **Language still belongs to the download.** Standard Moonshine stays English even on JP. The Japanese download translates JP game menus and keeps its launcher Japanese regardless of game region. The built-in Guide body and some status messages remain English.
- **Pinna 1 opening Talk split.** Keeps the automatic conversation when it starts immediately after the movie, so the route does not lose its first checkpoint before timing resumes.
- **Fresh streak attempts start clean.** A practice pause in the previous stage no longer makes the next clean IL/streak attempt ineligible. A rejected streak attempt briefly shows the reason beside its counter.

Pinna 1, streaks, camera settings, the third memory state and text readability passed the latest tester checks. Keep those results; this update focuses on TAS controls, checkpoint replacement and sound effects.

Use the complete package and make fresh states. **TESTING.md** is the short update check; keep your earlier successful RC1 results. **RC1_TESTING.md** covers gaps in the team's wider coverage, and **RC1_ROUTES.md** divides the course checks. One useful pass is enough.
