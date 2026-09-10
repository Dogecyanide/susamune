# Moonshine FOXTROT — latest checks

**V2.3.0 pre-release · Build 9975EF7F · Intros, movies and menu closing**

Keep your earlier passes. These are the three checks for this update.

**Tester / platform / game region / English or Japanese download:**

Make fresh states/projects with this build; older files need their matching build. Dolphin has no launcher SD service, so skip Save/Open there.

- [ ] **TAS through an intro or movie.** Start recording before entering a secret or triggering a movie. Use your usual skip input, then record a short recognisable movement afterward. Return to the Beginning area and Replay: the skip and following movement should play back without losing the take. If available, include FLUDD's movie sequence. Pause/Step requested during the intro or movie should wait until Mario is controllable. The input counter may grow during movies; the limit remains 4096.
- [ ] **Watch a ghost through movies.** Watch a ghost on a route with a movie. It should skip the movie automatically, keep Watch active and continue the ghost at the correct point. Pause/Step should still work when gameplay returns.
- [ ] **Close the TAS submenu.** Open Practice > TAS projects > Checkpoints, then use your normal Close shortcut: the menu should close. Try it after editing a shortcut too. While actually recording a new bind, those buttons must be recorded instead of closing the menu; release them, finish the edit and press Close again.

For a problem, send **build checksum, route/episode, what you pressed, and the exact message**. A photo or short clip helps. If Replay shows **DESYNC fN**, include the frame number and whether playback continued. The full `RC1_TESTING.md` remains available for gaps in the team's coverage.
