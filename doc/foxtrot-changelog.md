# Moonshine Launcher FOXTROT — RC1 feedback update

**V2.3.0 pre-release · Build E4DE048F**

- **Keep and edit a TAS with checkpoints.** Save another state while recording, load it to rewind the inputs, and try a different continuation. A stopped take has Continue editing checkpoint. Replay still uses the matching start state.
- **Keep the TAS across reboot.** Save both the start state and latest checkpoint to SD. After rebooting into the matching setup, import the start into any memory slot and load the checkpoint. Inputs remain experimental and limited to 4096 frames; the existing build, region, scene and settings checks still apply.
- **New SD states are required.** The state format now includes the used input recording and controller state. Earlier SD states must be resaved with this build. Your settings, records and ghosts remain usable.
- **Separate camera turning speed.** Look sensitivity adjusts C-stick turning from 0.25x to 4x independently of Movement speed. Hide all HUD hides game and Moonshine overlays while filming, with the menu still accessible. Both settings can be kept for your next boot.
- **State failures stay visible.** Turning successful save/load messages Off no longer hides errors. A reported Japanese State 3 failure has not been reproduced as a slot-specific bug; send the exact message if it happens again.
- **Japanese wording and readability.** Applied all 25 new wording amendments, translated the new camera/TAS controls, and made small help brighter and easier to read. The in-game Guide now fits its panel, avoids missing separator symbols and explains checkpoint recording.
- **Language still belongs to the download.** Standard Moonshine stays English even on JP. The Japanese download translates JP game menus and keeps its launcher Japanese regardless of game region. The built-in Guide body and some status messages remain English.
- **Pinna 1 opening Talk split.** Keeps the automatic conversation when it starts immediately after the movie, so the route does not lose its first checkpoint before timing resumes.
- **Fresh streak attempts start clean.** A practice pause in the previous stage no longer makes the next clean IL/streak attempt ineligible. A rejected streak attempt briefly shows the reason beside its counter.

The earlier Pinna and streak failures were reproduced in Dolphin. Please confirm the corrections on console using the focused checks in the tester sheet.

Use the complete package and make fresh states. **TESTING.md** is the short update check; keep your earlier successful RC1 results. **RC1_TESTING.md** covers gaps in the team's wider coverage, and **RC1_ROUTES.md** divides the course checks. One useful pass is enough.
