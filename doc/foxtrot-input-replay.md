# FOXTROT full-level TAS recording and storage

The primary workflow is **Practice > TAS projects**. New TAS captures a Beginning with RNG automatically. The take holds at most 4096 input frames and 32 area/movie transitions. Every ready retail stage-director call consumes an input frame, including intros, fades, demos and native menus. Ready movie calls in states 0–4 also consume frames, preserving skip inputs and their timing. Actual asynchronous load polling does not. Supported context changes retain the tape across setup and bind the input position to the next ready director. An unsupported transition or exceeded limit keeps the existing bytes and origin available for saving.

Stage and movie access checks the live director's retail type before reading its fields. Movie scene identities are exactly `0xFE000000..0xFE000013`; these tags are only for the input timeline, never permission to restore a game snapshot into a movie director. FLUDD's movie chain uses the same bounded transition table as area changes. Intros/movies run live; Pause/Step requests remain buffered until Mario is controllable. The former artificial arrival hold is removed so it cannot replace a cinematic input with a neutral frame. Ordinary QFT code remains unchanged.

During movies, only Pause/Step/Stop practice shortcuts are handled; other chords remain retail input. An active TAS intro does not open a new Moonshine menu or warp wheel, avoiding a modal hold that consumes its skip input. Ordinary menu behavior outside that cinematic TAS context is unchanged. Checkpoint restores require an actual stage director before any scene-state access.

**Save TAS** publishes an independent complete input tape together with the Beginning and any existing checkpoints. It does not capture the current game state. This allows saving a retained take after an area change or when no additional checkpoint can fit. A project manifest is published only after its state components and tape export succeed; a failed tape export leaves the previous manifest intact. Unchanged state files may be reused.

Snapshot version 17 carries the checkpoint's input/transition prefix and controller history. Project manifest version 2 adds a separate tape component and each state's scene identity; SD transport protocol 7 serves the bounded tape payload through existing storage ownership. Older state/project files require their matching older build.

Open imports the necessary states and the complete tape. If the selected checkpoint, or otherwise the Beginning, matches the currently loaded scene, it restores that point and reattaches the full tape at the checkpoint's position. Beginning, compatible checkpoint/Open and save-pause paths arm editing while retaining the compatible future inputs. Only the first consumed input from Step or Resume replaces that future; waiting, menu navigation and Save/Open alone do not truncate it. Explicit Stop and replay completion do not arm a new edit. Continue remains an explicit paused editing command. The published SD take remains unchanged until Save TAS. Without a compatible point, Open retains a detached tape without restoring Mario. The detached tape remains saveable. Checkpoint loads require their matching area/episode; Replay and Go to Beginning require manually returning to the Beginning area. Build, region, setup and state-owner validation remain in force.

Diagnostic mismatches are warnings. Replay keeps the first differing frame and continues with subsequent recorded inputs, including a mismatch in the restored start or ready arrival. Frame 0 means the start; later numbers identify consumed input frames. Further mismatches cannot replace the first warning. Tape CRC/hash/schema, prefix/origin identity, settings, scene and restore-owner checks remain hard guards. A warning does not imply the replay remains deterministic or repairs its state.

An early or late transition to the expected destination also warns without skipping or retiming input frames. Checkpoint/Continue temporarily refuse while the actual scene differs from the scene at the current recorded input index; saving the independent full take remains available. The destination identity itself remains a hard guard. This avoids publishing a checkpoint with scene metadata that disagrees with its input prefix.

The default-On TAS banner setting (ID 138) is presentation-only and shared by TAS projects and Display > Other HUD. Disabling it hides recording/replay progress and help while retaining a small DESYNC badge during replay. It fits the existing configuration capacity; snapshot 17, project manifest 2 and transport 7 are unchanged.

The current update, console `9975EF7F` / US `135D7393`, passed 1,237 host tests and a private US Dolphin check in `build/foxtrot-tas-cutscene-proof`. A 103-frame secret-intro take and a 105-frame FLUDD take replayed every recorded input without physical skip assistance; fingerprints, final Mario positions and retained tape bytes matched. The latter traversed movies 2 and 18 and the real repeat-explanation dialog before returning to airport episode 1. Actual Checkpoints navigation closed with Y+Start and preserved the take and all memory slots. Host tests also execute the production menu update against all six TAS pages, including shortcut recording's exclusive ownership; the old grab policy reproduces the close failure. The checked aggregate is `build/foxtrot-tas-cutscene-runtime-proof.json`. The bounded natural Ghost Watch trial did not reach a ready movie consumer, so automatic movie skipping remains unverified at runtime. This is neither a complete level playthrough nor physical-console/SD evidence. Earlier runtime results below retain their own source/build identities.

Ghost Watch skips ready movies through the retail movie-skip path while its existing ghost clock retains pose timing. This is separate from TAS input replay, which must use the recorded skip input.

The earlier polish build, console `2BF27B14` / US `162DD499`, passed 1,212 host tests and a bounded private US Dolphin check. Beginning preserved a six-frame future until the first new Step, then 64 replacement frames recorded without Continue and saved successfully as Checkpoint 1. A deliberate live Mario-position change produced the first warning at frame 4 and replay still consumed all 64 inputs without changing the tape. A second deliberate discrepancy at Bianco 3's natural secret arrival warned at frame 14 and replay finished all 19 inputs. These warned endpoints intentionally differ from their recordings; no deterministic match is claimed. Banner On/Off screenshots preserved the position, input count, QFT/input overlays and retail HUD while hiding only the large TAS panel. Evidence is in `build/foxtrot-tas-polish-proof`; the checked aggregate is `build/foxtrot-tas-polish-runtime-proof.json`. The two private callbacks and raw-input patch are documented there. A later console-only section-placement change leaves the emulator binary unchanged and has its own equivalence receipt. This is not SD/reboot, Japanese visual or physical-console evidence. Earlier full-level results follow under their original build identities.

Current host coverage in `scripts/test_tas_project.py` exercises the production coordinator against bounded state/storage fakes: no-capture saves with full RAM slots, saving a detached take, zero-frame saves, separate-tape export failure preserving the published manifest, importing in another area without world restoration, retaining a later tape after checkpoint restoration, invalid tape origin/length, and the existing slot/generation/overwrite protections. `test_tas_menu.py` covers the existing menu and Other area presentation. The new Wii reboot workflow still needs hardware testing.

US Dolphin recorded 19 frames through Bianco 3's actual secret entrance, kept the frame count through loading, refused an other-area Beginning load without discarding the take, then replayed after a manual return. All recorded fingerprints and the final Mario position matched; tape bytes were unchanged. The private setup positioned Mario before New TAS; recording and replay used the retail portal collision. Evidence: `build/foxtrot-tas-zone-proof/complete.json`, shipping baseline `233FBD49`. This is a short single-route emulator check, not a complete IL or physical SD test.

The earlier full-level release, US `8332FAAC` / console `C34FF061`, repeated the same 19-frame portal recording and replay after the in-game guide correction. Endpoint, fingerprints and retained tape bytes matched again. Evidence: `build/foxtrot-tas-zone-final/replay-zone.json`; source/object provenance and cleanup are collected in `build/foxtrot-zone-runtime-proof.json`. This predates the lazy-edit and warn-and-continue changes.

Frames remain 16 bytes. The 21-bit history of physical releases between steps
uses spare input bits and the top fingerprint bit, so those edges remain
lossless without enlarging the tape. The local per-frame diagnostic comparison
uses 31 bits; whole-tape, pad, archive and start hashes retain all 32 bits. Modal
menu navigation keeps separate gameplay controller history. Removing the old
three-seed cache saves about 532 bytes against the intermediate checkpoint
implementation; no memory reserve changed.

An earlier, single-area implementation passed an isolated US Dolphin check of saving two
checkpoints, rewinding, replacing the ending and replaying with matching
fingerprints and position. Opening the actual Y+Start menu, navigating and
saving a checkpoint also retained replay history. Evidence is in
`build/rc1-tas-camera-proof/complete.json` and `menu-checkpoint-result.json`
(private image `94714F34`, final TAS sources, before the final HUD draw gates).
This does not establish physical-console or cross-reboot behavior.

## Start transaction

New TAS pins its explicitly chosen Beginning slot and generation; the older optional Record action still uses Save to. Replay resolves the matching Beginning identity to a RAM slot, then pins its generation independently of the ordinary Save/Load selections. Open TAS imports and resolves that Beginning automatically.
The request clears an earlier buffered frame pause or queued Step. While waiting,
gameplay stays held and the request defers to menus, warp confirmations, the SD
service and memory-card work. Only the buttons that issued the request must be
released: A for a menu request, or the assigned shortcut. Other gameplay buttons
may stay held. A disconnected controller cancels the request before restoring.

After the existing drawing barrier, the state loads and its saved controller
history is restored. Old pause, Step and button-consumption latches are cleared.
Record stores the initial game fingerprint; Replay compares it before injecting
the first input and checks each consumed frame. Start, per-frame and arrival
diagnostic differences latch a warning and continue. Changed settings and
damaged take bytes still refuse playback. File, scene and ownership validation
are separate from these diagnostic comparisons.

The settings hash excludes only audited presentation values: favourites and RNG
favourites (`settings.cpp` stores menu stars), legacy native-timer coordinates and
scale (`CreationExtras::adoptNativeTimer` reads layout defaults), free-camera speed
and sideways direction, look sensitivity, hide-HUD and TAS banner controls (camera or
presentation only; replay disables the camera), metadata orientation (layout/clamping/drawing only), and ghost input
visibility (only the post-draw input overlay). Every other setting, including
Mario appearance flags, RNG controls and new settings, remains guarded. This lets
a user change those display preferences without receiving a false refusal.

The opening menu command now freezes its first frame before the menu's shown
flag changes. Previously it stopped recording before the director ran, then
allowed one extra neutral-input gameplay frame before showing the menu. That
could leave Mario slightly beyond the correctly replayed take's endpoint.

New TAS always captures RNG for its Beginning. The older Record-from-state shortcut still requires a state saved with RNG; turning the setting on afterward cannot add missing state. This guard remains separate from the transition/tape workflow.

## Earlier verification

The results below predate snapshot version 17 and project version 2; they do not establish the new full-level or reboot workflow. Existing focused checkpoint tests are in
`test_practice_checkpoints.py` and `test_savestate_checkpoint_contract.py`;
real-console checkpoint/reboot checks remain on the RC1 tester sheet.


`scripts/test_practice_slot_seeds.py` compiles the production request, queue,
restore-start and slot-callback functions. It exercises independent slot
generations, replacement/clear invalidation, menu and shortcut release handling,
stale frame-pause cancellation, SD/prompt waits, disconnects, the saved RNG gate,
changed settings, damaged take bytes and a mismatched restored start. Existing
practice input, held-button, pause and camera tests remain applicable.

`test_practice_replay_settings.py` exercises every setting ID, requiring the exact
audited exclusions and rejecting changes to every other value, retail stick
decoder mode and frame rate. `test_practice_menu_open.py` executes the production
menu-input and freeze expressions, including the first opening frame and the
boot/cutscene exclusions.

US Dolphin build `BDDD0EC6` (corresponding console build `8118304C`)
passed a menu-started 36-frame walking take twice and a 27-frame take started
while holding R. Both repeated playback and the held-button case preserved the
take bytes, matched every recorded fingerprint, and ended at the exact recorded
Mario position. The latter also verifies that opening the menu to stop recording
does not allow an extra gameplay frame. Evidence is in
`build/foxtrot-speed-8118304C/replay-results.json`.

The final US `782E8578` / console `00B63258` build repeats those checks after
workspace relocation and direct decoding. Walking replay twice and the held-R
start all passed with exact endpoints and take bytes; the final held-R take
contained 29 frames. Evidence: `build/foxtrot-speed-final/replay-results.json`.

These checks cover the request lifecycle and short takes in one US Bianco scene.
They do not establish that every retail scene is deterministic: clocks and
hardware services remain live, and the fingerprint covers only selected Mario,
RNG and counter state. Console replay and other scenes still require testing.
