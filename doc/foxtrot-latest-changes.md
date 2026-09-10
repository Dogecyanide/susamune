# Moonshine Launcher FOXTROT — latest changes

**V2.3.0 pre-release · Build C34FF061**

- **Keep a TAS through area changes.** Record the approach, enter a secret or another area, then keep going. Loading time uses no recorded-input frames. The limit is 4096 input frames and 32 area changes; an unsupported transition stops the take without erasing it.
- **Save the recording, even without a new checkpoint.** Save TAS keeps the full input recording, its Beginning and your existing checkpoints under one name. It no longer creates a checkpoint at your current position or needs another empty memory slot.
- **Know where a checkpoint can load.** Other area means it is still saved. Enter its matching area and episode first. Replay and Go to Beginning need the area where the TAS started. Opening a project keeps its full recording even if no checkpoint can load where you are.
- **More Shined favourites.** Newer named settings can be starred, including camera movement speed, sideways direction, look sensitivity and Hide all HUD. Existing stars stay.

**Make new SD states and TAS projects with this build.** Older files need their matching older build. Settings, records and ghosts are kept.

[TESTING.md](foxtrot-tester-checklist.md) has four focused checks. Keep earlier RC1 results; use the [full test log](foxtrot-rc1-test-log.md) only to fill gaps in coverage. The [changelog](foxtrot-changelog.md) keeps the earlier changes.
