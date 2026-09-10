# Moonshine Launcher FOXTROT — latest changes

**V2.3.0 pre-release · Build 9975EF7F**

- **TAS includes intros and movies.** Skip inputs are recorded and replayed with their timing, including FLUDD's movie sequence. Intro and movie input frames count toward the existing 4096-frame limit. Loading waits do not.
- **Pause when control returns.** Pause or Step during an intro or movie waits for Mario's first controllable frame.
- **Ghost Watch skips movies automatically.** Watching a ghost should get past movies and keep its movement timing.
- **Close works inside TAS submenus.** Your usual close shortcut, Y + Start by default, works from Checkpoints and the other TAS pages. While assigning a shortcut, the recorder still owns those buttons.

**Make new SD states and TAS projects with this build.** Older files need their matching older build. Settings, records and ghosts are kept.

[TESTING.md](foxtrot-tester-checklist.md) has three focused checks. Keep earlier RC1 results; use the [full test log](foxtrot-rc1-test-log.md) only to fill gaps in coverage. The [changelog](foxtrot-changelog.md) keeps the earlier changes.
