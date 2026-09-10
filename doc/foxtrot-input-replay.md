# FOXTROT full-level TAS recording and storage

The primary workflow is **Practice > TAS projects**. New TAS captures a Beginning with RNG automatically. The take holds at most 4096 input frames and 32 area transitions. Supported retail area changes retain recording/replay state across setup, and loading time consumes no input frames. Each recorded transition links its source, destination and input position to the checked first actionable state. An unsupported transition or exceeded limit stops the take while retaining its existing bytes and origin for saving.

**Save TAS** publishes an independent complete input tape together with the Beginning and any existing checkpoints. It does not capture the current game state. This allows saving a retained take after an area change or when no additional checkpoint can fit. A project manifest is published only after its state components and tape export succeed; a failed tape export leaves the previous manifest intact. Unchanged state files may be reused.

Snapshot version 17 carries the checkpoint's input/transition prefix and controller history. Project manifest version 2 adds a separate tape component and each state's scene identity; SD transport protocol 7 serves the bounded tape payload through existing storage ownership. Older state/project files require their matching older build.

Open imports the necessary states and the complete tape. If the selected checkpoint, or otherwise the Beginning, matches the currently loaded scene, it restores that point and reattaches the full tape at the checkpoint's position. Replay retains later inputs; Continue edits from that point. Manual Go to Checkpoint restores only that checkpoint's prefix into the local take; it does not preserve the later local tail. The published SD take remains unchanged until Save TAS. Without a compatible point, Open retains a detached tape without restoring Mario. The detached tape remains saveable. Checkpoint loads require their matching area/episode; Replay and Go to Beginning require manually returning to the Beginning area. Build, region, setup and state-owner validation remain in force.

Current host coverage in `scripts/test_tas_project.py` exercises the production coordinator against bounded state/storage fakes: no-capture saves with full RAM slots, saving a detached take, zero-frame saves, separate-tape export failure preserving the published manifest, importing in another area without world restoration, retaining a later tape after checkpoint restoration, invalid tape origin/length, and the existing slot/generation/overwrite protections. `test_tas_menu.py` covers the existing menu and Other area presentation. The new Wii reboot workflow still needs hardware testing.

US Dolphin recorded 19 frames through Bianco 3's actual secret entrance, kept the frame count through loading, refused an other-area Beginning load without discarding the take, then replayed after a manual return. All recorded fingerprints and the final Mario position matched; tape bytes were unchanged. The private setup positioned Mario before New TAS; recording and replay used the retail portal collision. Evidence: `build/foxtrot-tas-zone-proof/complete.json`, shipping baseline `233FBD49`. This is a short single-route emulator check, not a complete IL or physical SD test.

The final source, US `8332FAAC` / console `C34FF061`, repeated the same 19-frame portal recording and replay after the in-game guide correction. Endpoint, fingerprints and retained tape bytes matched again. Evidence: `build/foxtrot-tas-zone-final/replay-zone.json`; source/object provenance and cleanup are collected in `build/foxtrot-zone-runtime-proof.json`.

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
Record stores the initial game fingerprint; Replay checks that same fingerprint
before injecting its first input. The original per-frame fingerprint checks
remain intact. A different restored start, a changed setting, damaged take bytes,
and a later frame mismatch now have separate messages. Later mismatches include
the frame number. Gameplay and RNG checks remain intact.

The settings hash excludes only audited presentation values: favourites and RNG
favourites (`settings.cpp` stores menu stars), legacy native-timer coordinates and
scale (`CreationExtras::adoptNativeTimer` reads layout defaults), free-camera speed
and sideways direction, look sensitivity and hide-HUD controls (camera or
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
