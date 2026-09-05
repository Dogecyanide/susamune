# FOXTROT first-build test sheet

Status: pre-release. All six regional/platform builds and 463 host tests pass.
Wii hardware playtesting is pending.

## Checks completed on 2026-09-05

- JP, US and PAL launcher images pass the shared V3 manifest validator. Complete
  BPS application to owned retail images passes source/target CRCs, all 31 hook
  writes, both initialized/BSS spans and the protected attachment/scratch gap.
- Retail-binary audits pass for input, movement, camera, collision, crash display
  and native timer drawing in all three regions. All three native timer layouts
  contain the supported 18-pane tree.
- An isolated Dolphin 5.0 US JIT session reached Bianco 1 through the warp wheel.
  Practice hold kept Mario stationary, three Step presses completed three
  updates, free-camera state moved during both practice hold and retail pause,
  and savestate load restored Mario's saved position.
- JP and PAL JIT sessions also reached Bianco 1 and stayed stable for 180
  seconds each. Their stage heaps reported 1,366,088 and 1,382,152 free bytes,
  respectively. These are emulator measurements for Bianco 1, not worst-stage
  or Wii measurements.
- A 330-frame moving take replayed with matching diagnostic fingerprints. A
  separate replay stopped on the next sample after a deliberate position change
  in the test process. This does not establish full-world determinism.
- An identical untraced image accepted held-menu navigation under Dolphin
  2606a JIT and Dolphin 5.0 Interpreter. The old 5.0 JIT failed that check;
  use a current release for frame tools. Interpreter also passed a single
  step with jump held and a warp out of practice hold.
- The final US image (CRC32 `5F9FF69D`) passed Dolphin 2606a JIT checks for
  holding with jump/stick input, menu navigation during hold, one step with
  jump held, free-camera activation and movement in both pause modes, camera
  handoff to the menu, and a completed warp from practice hold.
- The protected QFT timer implementation and existing callback order are
  unchanged. No new level splits were added.

The live control fixture supplies controller packets at the retail input
boundary in a private test image; it does not test a physical controller or
Wii storage. Camera observations verify state and hook phases, not visual
quality. Full ghost teaching export/Watch, hardware frame pacing and the
device matrix below still need playtesting.

## Runner test checklist

Record game region, console/Dolphin version, scene, settings, and the displayed build checksum with each report.

1. Boot from disc and from your own ISO/CISO. Test automatic boot and B to return to the launcher.
2. Load the most demanding scene and note free memory. Enter/exit the menu and use the warp wheel.
3. L + D-Up pauses actor simulation; L + D-Right releases one rendered gameplay frame; L + D-Up resumes. Repeat with Mario airborne, an enemy active, and a moving platform. Clocks and absolute-time deadlines remain live.
4. During retail pause, L + D-Down toggles free camera. Test both sticks and L/R height. Turn it off and check the restored camera. Repeat while practice-paused and while stepping.
5. Save during normal gameplay, record a short take, stop, then replay. Check start state, button edges, analog triggers, B/Start abort, scene changes, new savestates and changed settings. Mismatch detection is diagnostic, not proof of full determinism.
6. Record a successful ghost on an already supported split route. Export and reload it. Compare Off/PB/SOB/Ghost, race it, and inspect inputs in Watch/Watch2. Old ghosts should show no input data.
7. Move/resize the native timer, collect coins and trigger the native layout shift, save/load, warp, and restore default layout. Verify HUD artwork/visibility and the original timing behavior.
8. Save settings and restart. Existing region-specific settings, records, ghosts and binds should survive.
9. Retain crash .bin, .core and text files with the exact package checksum. Avoid deliberately crashing during a save.

No new level splits were added.
