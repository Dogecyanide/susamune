# Moonshine Launcher FOXTROT — RC1 feedback update

**V2.3.0 pre-release · Build AE95E374**

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

Pinna 1, streaks, camera settings and other sampled splits passed the user's latest console checks. Keep those results; this update's main checks are state capacity and the new TAS workflow.

Use the complete package and make fresh states. **TESTING.md** is the short update check; keep your earlier successful RC1 results. **RC1_TESTING.md** covers gaps in the team's wider coverage, and **RC1_ROUTES.md** divides the course checks. One useful pass is enough.
