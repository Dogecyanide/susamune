# Prototype 9 ghost observations

PR12 Wii feedback, 2026-10-15: Yoshi animations now look good, Mario's accepted
R+A burst spray works, and all held fruit render correctly. Mounted Yoshi's
equivalent burst is repaired in PR13 source but still needs Wii confirmation.
These results supersede the older pending visual checks below.

Hardware feedback for Prototype 8 confirms Turbo and Rocket rendering and the
underwater shine fix. Its Yoshi animation is visibly wrong; R+A burst spray is
indistinguishable from a normal stream. Those observations supersede the earlier
unverified attachment notes.

## Bounded visual storage

SGHF V7 retains V6's 24-byte input stride, 36,000-input limit, 17,983-pose limit
and 71,928-QF timeline. These visual observations need no additional storage;
the separate PR9 savestate work redistributes temporary MEM2 storage without
reducing these limits. V7 requires feature mask 15 and teaching section SGTI V3; V6 keeps
mask 7 and SGTI V2. PPC, ARM, catalog admission and the host validator recognize
the exact version pairs. V3 through V6 remain readable; their observations never
gain the new semantics implicitly. A resumed V6 recording strips the new data.

The existing eight-byte FLUDD observation gains an accepted burst bit. While
mounted it is instead tagged as Yoshi data: actual body BCK index and frame
(1/16-frame precision), walk/run blend, upper-body BCK and phase, and head angle.
Controller bytes remain untouched. Dismounting returns to the ordinary FLUDD
layout. Missing/invalid live actor data produces an empty observation and the
legacy fallback rather than unchecked model reads. Live protocol 3 also rejects
Yoshi observations attached to a non-mounted pose.

Capture reads the retail actor and emission results. It never advances an actor,
emits water, consumes RNG, changes collisions or calls animation setters.
Rendering saves/restores every temporarily borrowed joint transform, callback
and calculator. The upper animation is restricted to joint 18's descendants;
joint 21's private callback applies the recorded head pitch. Capture checks the
actual body controller rather than Mario's rider controller. The latter loses
distinct Yoshi animations and runs at a different phase.

Walk/run transforms use bounded local blending, not the retail quaternion blend;
tongue-tip geometry and alternative hand models remain limitations. Head pitch,
body frame and upper frame are quantized. Yoshi juice uses the recorded firing
bit and reconstructed mouth/aim, so its particles remain approximate. These
changes require a fresh recording to provide the new Yoshi/burst observations;
old files retain the old approximation. Real-Wii visual confirmation is pending.

Burst observation checks accepted emission while the normal nozzle's bomb
sub-nozzle is active, not merely R+A input. If normal emission follows a burst
within the same drawn frame, the burst retains that frame's observation. The
visual water pool remains 64 droplets per runner, with at most 24 new droplets
per burst update. Scatter uses the bomb's directional/power spread and local
deterministic arithmetic, never the game's RNG or water pool.

PR13 records the same accepted-burst bit for mounted Yoshi and uses Yoshi's
own bomb sub-nozzle for replay count, spread and power. Retail
`TNozzleDeform::emit(3)` emits ordinary juice only while its nested bomb is
inactive, then invokes that bomb; the accepted-emission hook therefore reads
the Yoshi bomb's state rather than Mario's. Both reference decomps place this
object at `TWaterGun + 0x11B8` (`0x0E34 + 0x384`), already represented by the
local header. No controller guess or game RNG is involved.

The eight-byte layout, format versions, ten-minute capacity and memory pools
stay unchanged. `0x20` still means accepted burst; Yoshi observations may now
combine it with firing (`0xB0`). Burst without firing remains invalid. Existing
files play identically, but a new recording is needed to retain Yoshi bursts.
Older builds reject the new combination; use the updated build on both peers.

Both live players need Prototype 9. Its 56-byte pose packet is unchanged in
size, but the inner protocol is 3 so older peers cannot reinterpret the new
bits. Relay Server 5 forwards inner protocols 1/2/3; existing Prototype 8 rooms
still require two Prototype 8 clients. The outer room-code protocol is unchanged.

## Held pepper follow-up

The supplied JP `Delfino Plaza - 0:59.392` V7 recording already contains the
held pepper descriptor `0x40000395 / 0x1720`. Capture was intact; the renderer's
fruit range stopped at Banana (`0x40000394`). Retail `TMapObjBase::isFruit`
also accepts RedPepper, and `RedPepper_data` registers it in the enemy group.
The renderer now includes that sixth fruit and reads its model through the
common `TLiveActor` base. It retains the exact object-ID/name-key lookup and
existing private-model budget. Existing files containing the descriptor benefit
without re-recording; no format, bank, reservation or timeline limit changes.

That same recording contains 471 tagged Yoshi observations, seven body
animations, 181 distinct body/frame combinations, walk blending, upper-body
animation and four accepted burst-spray observations. This confirms the V7
capture paths are present in the supplied file. It does not establish visual
accuracy, and the original PR8 feedback alone is not evidence that those newer
paths still fail. The documented Yoshi and water approximations remain.

Three focused host tests exercise all six fruit IDs, exact identity/group
selection, absent model handling and the separate jump-base path. Production
PAL compilation succeeds with unchanged allocated section sizes and identical
`.foxtrot.text`; only the existing renderer section's instructions change.
Evidence is in `build/ghost-held-pepper-followup/`. The pepper rendering fix
still needs a Wii visual check.

## Boss and enemy RNG: Watch only

The requested behavior is the original boss/enemy sequence while watching a
recording. Racing a ghost, live online, selecting/loading a file, and subsequent
practice attempts must retain their own RNG/world. No RNG replay is enabled by
this visual-format update.

A start seed alone cannot provide this. `ghost.cpp`'s observer hides the live
Mario and follows recorded positions/floor contact without replaying his
physics, water hits, thrown fruit or enemy attacks. `ghost_water.cpp` deliberately
does not submit gameplay particles. Petey's `gotWaterDamage`, navel hit handling,
nerve timers, movement and tornado decisions depend on those interactions;
`BossPakkun.cpp` consumes `rand()` conditionally in those states. Existing
`rng_control.cpp` shows King Boo's result belongs to a particular slot/nerve
cycle, not an independent visual random stream. Global RNG also advances for
unrelated actors, so a different call order diverges even from the same seed.

Two viable scopes need separate engineering:

1. A bounded Watch event track for selected actors: record actor identity,
   decision time and actual random outcome, plus the relevant interaction/state
   transitions. Begin with King Boo and Petey. Replaying outcome rolls alone
   remains insufficient when the hidden observer never performs the hit that
   advances the boss. This can reproduce selected behavior without claiming an
   exact complete-world replay.
2. Deterministic Watch: establish the same starting stage state, replay the
   recorded inputs through the real simulation, preserve every interacting RNG
   source/timing dependency, and verify checkpoints against recorded poses.
   Mid-level starts need a state/checkpoint or equivalent reconstruction. This
   is substantially larger than pose playback; cross-region determinism is not
   established by the current portable ghost format.

Either needs explicit ownership on Watch entry, stage/actor generation checks,
fail-closed event exhaustion/divergence, and cleanup on stop/error/warp/reset.
Returning to normal play must restore the pre-Watch world and all RNG state, or
start a fresh ordinary stage; restoring only a global seed would leave modified
boss state behind. Two-ghost Watch needs a chosen world owner because their
recorded outcomes can disagree. Existing files lack the required observations,
so their original boss/enemy behavior cannot be recovered reliably.

## Focused evidence

The focused host suite covers canonical V7 and legacy rejection, actual ARM
chunked admission, attachment restoration and independent Yoshi frame selection,
burst spread/count, live wire validation, and actual relay/session clients.
Production PAL compilation accepts the affected six translation units. Final
protected-link and console checks belong to the integrated build receipt.
