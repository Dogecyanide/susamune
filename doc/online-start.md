# Online start reservation (MSR protocol 5)

`localReady` records the player's intent. It may be true while an intro, load,
save dialog or other owner is busy. It is not sufficient to start a race.

`LevelWarp::readyForOnlineRace()` owns the retail departure predicate: the real
loaded stage director must be normal, the fader fully visible, CARD idle, and
no other warp/deferred departure armed. `safeToStart()` adds practice/storage/
playlist/unsaved-ghost constraints. Neither check initiates a warp.

`prepareStart()` opens Online only when another editor does not own input, then
sets `startPrepared`. The main loop holds the normal director before it can
simulate another frame. Online consumes the menu input; A or B cancels readiness.
Practice actions, the warp wheel and savestate binds cannot invalidate the scene
reservation. Transport polling continues while the director is held.

Only this reservation is published as Ready. Two-player START requires both
reservations. Three/four-player `readyMask` has the same meaning; the host waits
for every configured participant. Draft selection feeds the same Ready phase,
and a playlist start uses it once before independent per-player progression.

The reservation ends at successful warp arming, cancellation, round reset or
connection loss. A late START after withdrawal is declined. Group cancellation
can replace a queued Ready request so a refused start is not silently lost.
Protocol 4 peers are rejected because they can publish Ready without reserving
their scene. Everyone in a PR27 room must use PR27-compatible protocol 5.

Draft prompts are edge-triggered on becoming the local actor. A pending prompt
waits through loading or an editor, and is consumed only after opening succeeds.
Closing it with B does not reopen it each frame. Player 2's consecutive opening
bans are one turn; the turn after the opponent acts creates a fresh prompt.

Host tests exercise delayed readiness on either device, cancellation, editor
ownership, draft prompt deferral, all 3/4-player readiness masks and packet loss.
The real Wii acceptance case is one player pressing Ready during a transition,
then waiting for automatic departure after that transition finishes.
