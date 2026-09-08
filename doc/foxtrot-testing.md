# FOXTROT validation record

Status: pre-release. The short runner checklist is in
[foxtrot-tester-checklist.md](foxtrot-tester-checklist.md); it ships as TESTING.md.
This file records developer verification and the scope of earlier checks.

## Input and timer feedback update on 2026-09-08

- Final host suite: **613 tests pass**. Launcher checksum: **`F6962C1F`**.
- JP/US/PAL console and emulator builds pass their linker memory checks. Full
  BPS application verifies JP `F62D6D32`, US `A74FDD62` and PAL `913325E9`,
  all 31 hook writes, both runtime spans and the protected attachment/scratch hole.
- The final US `A74FDD62` image passed a bounded Dolphin 2606a JIT check using
  private controller packets at the retail PADRead boundary. It accepted Pause
  with A held, fresh/held/repressed A on Step, and a grounded A+Step jump.
  Each Step added four QFs. The held compact text advanced
  `0:05.438 → 0:05.472 → 0:05.505 → 0:05.538`, stayed fixed while waiting,
  and the underlying clock continued on Resume with TAS retained. Normal
  configured event-freeze display behavior resumes outside frame hold.
  Evidence: `build/foxtrot-held-input/results.json`. All owned test processes
  were stopped. This does not test a physical controller or Wii rendering.
- Production tests cover physical releases between steps, no invented repeated
  presses, inert retired spin binds, event timestamps, QFT hold/step/reset/state
  load, and the actual before/after-direct order for both ghost Watch modes.
  Watch now settles a Step's elapsed time before the next frozen frame.
- Six production display-command tests cover TAS badge edges, opacity, split
  spacing and attempt lifetime. New live Watch and badge screenshot checks
  were not part of the final bounded run.
- Native timer tests cover All/per-target Original and Custom modes, retained
  RGB/placement, keep/discard/reset, old INI migration and exact retail endpoint
  restoration. Configuration offsets and fixed memory ownership remain unchanged.
- Empty-personal-row tests use the production menu flow and preserve occupied,
  unsafe and imported entries and the exact recording confirmation token.
- Launcher status tests model the queued framebuffer copy and require completion
  before VI presentation. This addresses one-off missing storage status text;
  actual startup appearance still needs Wii confirmation.
- A real US Bianco 1 snapshot compressed from 14,986,692 to 5,015,626 bytes
  with DarkMoonshine's production deflate codec and restored byte-for-byte.
  This is one host-codec measurement, not Wii timing or a worst-case ratio.
  See [the state feasibility report](foxtrot-savestate-feasibility.md).

Everything below records earlier builds, with their own scope and checksums.

## Controls and ghost-library update on 2026-09-06

- Final host suite: 582 tests pass. Launcher build checksum: `2BC0E2E1`.
- JP/US/PAL console and emulator images compile within their fixed memory spans.
  Full BPS application passes for JP `46EF7CF9`, US `A68B3EEF` and PAL
  `A2B59038`: original/target checksums, 31 hook writes, initialized/BSS spans
  and the protected attachment/scratch hole all match.
- A private US `4AF65F76` image passed Dolphin 2606a checks for D-Up buffered
  during black loading, hold at the first actionable update after the intro,
  one Step, D-Up+A jump, X rebinding, and the old L+D-Up Pause shortcut combined
  with a D-Up Step shortcut. Holding L after resume caused no re-pause or
  ground pound. Freecam auto-pause, Off retaining pause, and the sideways
  direction toggle passed with Mario stationary.
- That live fixture feeds controller packets at the retail PADRead boundary;
  it does not test a physical controller or Wii storage. The tested image
  precedes final ghost/menu integration. Reproducible results are in
  `build/foxtrot-pr3-controls/results-final.json`; the original QFT code is unchanged.
- Production menu tests cover the three practice pages, held entry/rebind
  buttons, four-button bind completion, cross-page Watch2 identities and page
  wrap. PB auto-save tests keep a pending warp blocked until its exact protected
  recording has been acknowledged as saved.
- Production PPC mailbox tests cover 50,000 catalog entries, 64-bit duration
  totals, page changes during a transfer, stale identities, automatic saves
  and delayed acknowledgements. Two cached pages use 7,360 of the existing
  7,680 bytes; no snapshot, configuration or active playback bank moved.
- Native tests drive the production ARM storage state machine with a fake
  filesystem. They cover libraries beyond 45/12 entries and ten hours, extended
  IDs, page enumeration, old A/B recovery, interrupted writes, stale selections,
  chunked loading and reclaiming deleted payloads after committing a tombstone.
- Launcher tests cover early theme ordering, first-frame visibility, explicit
  text depth state, fallback fonts and storage-probe cleanup. The launcher
  builds, but the user's early blank-text symptom still needs Wii confirmation.

Real-console startup appearance, storage durability and large-library browsing
performance remain hardware playtest items. The checks below are historical
evidence for the preceding packages, with their own image checksums.

## Feedback update checks on 2026-09-05

- Complete BPS application passes for JP `63C843C7`, US `048295BC` and PAL
  `01965304`, including all 31 hooks, initialized/BSS spans and protected gaps.
- Production menu tests exercise the seven layout groups, health/air routing,
  all metadata rows, decreasing/increasing spacing, and held-button entry.
- Production persistence tests cover the unchanged metadata payload, health
  colours in reserved bytes, the eight-byte native timer style, and Dolphin
  settings migration from the preceding record format. Older mailbox offsets
  remain fixed.
- Native draw tests cover exact restoration after default, preview, cancel and
  invalid-tree paths. Blue, purple and white endpoint tests pass. Health and
  air tests cover all retail meter modes, independent palettes, inactive petals,
  visibility and derived opacity restoration.
- Final PAL `01965304` reached Bianco 5 with 787,800 B free stage heap.
  Live captures contain exact pure blue, purple and white digit pixels, and
  the underwater-air colour editor displays its independent palette. The
  remaining normal/underwater gameplay and SD persistence matrix is pending.
- Launcher text tests cover the built-in fallback font, failed FreeType setup,
  glyph widths, padded/negative bitmap pitch and monochrome masks. The exact
  cause of the reported blank launcher on hardware has not been reproduced.
- On US `5FF0C16B`, a visible Dolphin 2606a JIT test used actual controller
  packets to pause, jump-step, move the camera right/left, select 2x speed and
  use X boost while Mario stayed fixed. Both queued spin directions produced
  retail spin-jump states after nine actual steps. Native-pause camera movement
  also passed. This image precedes the final health-preview restoration change.
- On JP `672D17BE`, the user's exact exported PAL Bianco 3 Secret payload
  supplied its original 712/1700 QF checkpoints. Crossing the existing detector
  displayed a numeric ghost delta. Watch2 held both playheads while the raw
  timer advanced; one Step moved both together. Free camera moved during hold.
  An assisted recording added no poses or inputs while held, then added one
  of each for a Step and carried the TAS flag. Observer cleanup passed.
  This image precedes the final health-preview restoration change.
- Ghost tests used a host-validated real file installed as a private runtime
  track. They exercise the production detector, comparison, clock and rendering,
  while ARM import/export, storage and a completed TAS save remain hardware
  playtest items. The QFT implementation and callback ordering are unchanged.

The following first-build checks remain historical evidence with their own
image checksums; they are not repeated whole-game validation of this update.

## First-build checks completed on 2026-09-05

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
- JP `A27A0024` and PAL `BE5E2141` images reached Bianco 5 through the
  real warp wheel in Dolphin 2606a JIT. Each remained fully loaded for 30.12
  seconds; 30 stationary samples gave minimum free heaps of 759,512 and
  787,800 bytes. Root-heap boundaries and heap cursor arithmetic stayed valid.
  These are sampled emulator values, not Wii or full-playthrough minima.
- US `0391BB7B` passed ten live wheel warps in Dolphin 2606a JIT:
  all seven main-course episode 1 entrances, Bianco 5, Pinna 8's beach entrance
  and Sirena Hotel. Each had 95–96 stationary samples over five seconds.
  Bianco 5 had the lowest observed free heap, 789,240 bytes (770.74 KiB).
  Stage generations, director/heap identities and the root floor stayed
  consistent; no crash or loading stall was observed. Pinna interiors were
  not sampled. Full values and scope are in the source repository's
  `doc/foxtrot-memory.md`.
- A 330-frame moving take replayed with matching diagnostic fingerprints. A
  separate replay stopped on the next sample after a deliberate position change
  in the test process. This does not establish full-world determinism.
- An identical untraced image accepted held-menu navigation under Dolphin
  2606a JIT and Dolphin 5.0 Interpreter. The old 5.0 JIT failed that check;
  use a current release for frame tools. Interpreter also passed a single
  step with jump held and a warp out of practice hold.
- US image CRC32 `5F9FF69D` passed Dolphin 2606a JIT checks for
  holding with jump/stick input, menu navigation during hold, one step with
  jump held, free-camera activation and movement in both pause modes, camera
  handoff to the menu, and a completed warp from practice hold.
- US image `14403536` passed a captured menu-entry check: holding A
  opens the frame controls without activating Pause; a fresh press activates
  it. The title, pre-release badge and all seven control rows fit at 640×480.
  A fresh 68-frame moving/jumping take replayed with all fingerprints matching
  and the same final position. Held-menu input and Step with A also passed.
- The recording settings hash remains byte-for-byte equivalent after removing
  126 helper calls per frame. Launcher asset validation retains every checksum
  while hashing 135,776 fewer bytes per two-model load.
- The launcher decoder no longer calls a helper or saves registers for every
  output byte. Production decoding and checksum validation passed both model
  archives from all three owned retail discs, with output guards intact.
- The kernel shares one nibble-table CRC across model, mod-file and crash
  validation. All six retail model payloads pass, corruption still rejects,
  and the original cache synchronization ranges are retained.
- Basic Bianco 1 pixel checks show free-camera viewpoint movement while
  Mario's position remains fixed, and native timer position/scale changes.
- US image `0391BB7B` keeps both frame controls and Creation open
  through a held selecting press. The shared child-page guard also skips
  the release callback, so a stale decoded button cannot activate an editor.
  Final captures verify notification/banner priority, free-camera movement,
  and a clean native timer at +60 X, -40 Y and 140% scale.
- The production ghost input lookup passed 47,969 independent host comparisons,
  including sparse samples, segment boundaries, truncated tails and 54,000
  inputs. Synthetic runtime tracks also passed Watch/Watch2 display checks
  on Dolphin: Off/Ghost/Both, recorded A-to-B changes with neutral live input,
  distinct second-ghost inputs and an explicit no-input message for V3.
  The fixture bypassed file import and SD storage; it tests the observer and
  rendering paths. Source-repository evidence is in
  `doc/foxtrot-ghost-validation.md`.
- Final US `9B61FABE` clears the native HUD with both ghost input panels and
  the legacy no-input label. Regional mods change only three position operands
  from the stage-tested images; memory, hooks and all other bytes are identical.
  Full BPS validation passes for JP `B8A0ADEB`, US `9B61FABE` and PAL `E735EBF3`.
- The protected QFT timer implementation and existing callback order are
  unchanged. No new level splits were added.

The live control fixture supplies controller packets at the retail input
boundary in a private test image; it does not test a physical controller or
Wii storage. Camera observations cover sampled views and hook phases.
Full ghost teaching export and loading from SD, hardware frame pacing and the
device matrix below still need playtesting.

## Runner checklist

The current concise checklist, including PR1, is
[foxtrot-tester-checklist.md](foxtrot-tester-checklist.md).
