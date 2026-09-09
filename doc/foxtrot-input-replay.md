# FOXTROT input replay start handling

Input takes remain local, experimental recordings of up to 4,096 rendered
frames. They require a locally saved gameplay state, including its controller
decoder history and RNG. Importing an SD state does not invent that history:
load it, then make a new memory save before recording an input take.

## Start transaction

Record pins the current **Save to** slot and generation. Replay pins the take's
original slot and generation, independently of the current Save/Load selections.
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
and sideways direction (only `updateCamera` reads them, and replay disables that
camera), metadata orientation (layout/clamping/drawing only), and ghost input
visibility (only the post-draw input overlay). Every other setting, including
Mario appearance flags, RNG controls and new settings, remains guarded. This lets
a user change those display preferences without receiving a false refusal.

The opening menu command now freezes its first frame before the menu's shown
flag changes. Previously it stopped recording before the director ran, then
allowed one extra neutral-input gameplay frame before showing the menu. That
could leave Mario slightly beyond the correctly replayed take's endpoint.

The seed remembers whether **Save RNG state** was enabled when it was saved.
Turning it on afterward is insufficient: a new state must be saved. The user's
last backed-up configuration already had this enabled, so this guard is not
evidence that RNG settings caused their reported intermittent mismatch.

## Verification

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
