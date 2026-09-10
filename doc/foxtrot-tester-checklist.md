# Moonshine FOXTROT — latest checks

**V2.3.0 pre-release · Build E4DE048F · RC1 feedback update**

Keep your earlier RC1 results. These are the checks for this update; one useful pass is enough. Reuse the same states and do the reboot once. The full `RC1_TESTING.md` remains available for gaps in the team's earlier coverage.

**Tester / platform / game region / English or Japanese download:**

**Make fresh states with this build. Earlier SD states need resaving and will not load in this update.** Settings, records and ghosts are kept.

- [ ] **Settings stick:** Change Look sensitivity and Hide all HUD, plus one ordinary setting. Keep them for the reboot below. Existing binds, colours and episode choices should remain correct.
- [ ] **Camera:** In Practice > Free camera, try Look sensitivity at a slow and fast setting. It should change C-stick turning speed separately from Movement speed. Hide all HUD should hide game and Moonshine overlays while freecam is On; the menu must still open. Turn it Off and check the normal displays return.
- [ ] **TAS checkpoints:** Save a start state, record a short walk/jump, and save a different slot as a checkpoint. Go farther, load the checkpoint and try another ending. Replay should show the original opening plus the new ending. Keep the start state. A stopped checkpoint should offer Continue editing checkpoint; it stays paused until Step or Resume.
- [ ] **TAS after reboot — console:** Save both the start and latest checkpoint to SD with recognisable names. Reboot once into the same build, region, setup and episode. Import the start into any RAM slot, then load the checkpoint. Continue editing and replay from the beginning should work. The settings saved above should also remain.
- [ ] **States and visible errors:** Save/load all three slots once in a familiar scene. With successful save/load messages Off, try loading in the wrong episode: a readable refusal should still appear. Return to the right episode and load normally. If any slot fails, send its number and exact message; there is no confirmed JP-only State 3 fault.
- [ ] **Pinna 1:** Start through Runs > ILs and use your usual cutscene path. Expect Talk, all four Mecha-Bowser hits and Finish, without losing progress through the movies/skips. Report the first missing event and which skip you used.
- [ ] **Streaks:** Use practice pause in an earlier stage, then start a clean short streak challenge. The clean attempt should count normally. A rejected attempt should briefly show why beside the counter. Check your usual reset shortcut does not accidentally pause the fresh attempt.
- [ ] **Guide and Japanese text:** Open System > FOXTROT guide and turn pages. Text should fit without large gaps. Japanese-download testers: check the corrected IL/playlist/layout terms and small help text. The standard download must still be English even on JP; the Japanese download translates JP game menus. The Guide body and some status messages remain English.
- [ ] **One ordinary run:** Finish a familiar IL without practice assistance, then spot-check Pause/Step and a ghost you already have. Normal timing/PB recording should work, each Step advances one frame, and turning Ghost display Off also hides its input panel. Reuse earlier passes for unchanged features.

For a problem, send **build checksum, route/episode or menu, what you pressed, and the exact message**. A photo or short clip helps. No long report needed.
