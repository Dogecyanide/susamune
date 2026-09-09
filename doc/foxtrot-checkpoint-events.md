# FOXTROT checkpoint event audit

The September 9 checkpoint expansion keeps the 132 stable route identities and
uses the V9 schema's 495 segments. Route prefixes and internal red-coin
checkpoints share their original event order; a later event cannot fill in a
missing earlier checkpoint. Explicitly excluded routes have only their finish.
Persistence and exact old-segment migration are documented in
[foxtrot-split-stats-v9.md](foxtrot-split-stats-v9.md).

## Event boundaries

These observers wrap retail methods and inspect their accepted state change.
They do not alter the ordinary QFT timer formulas or inject gameplay actions.

| Checkpoint | Accepted boundary |
| --- | --- |
| Airstrip FLUDD cutscene | `fireStreamingMovie(2)` newly sets the director's movie flag and selects Airstrip episode 1. The `airport0` StartDemo object's movie ID is 2. |
| Plant hits | Gatekeeper health decreases, capped at three hits. Waking the plant does not count. |
| Shadow Mario Talk | `TTalk2D::openTalkWindow` runs for the dummy NPC connected to the actual Shadow Mario actor. Falling down or becoming talkable does not count. |
| Gelato 5 Talk | The game accepts an NPC talk in Gelato episode 5. The user requested a generic Talk checkpoint. |
| Pinna 1 Talk | The game accepts an NPC talk in the route's retail park scenario 0, 6 or 7. The following boss transition remains exactly `0x3A:1`. |
| Pinna 8 Talk | The accepted talk names the ride attendant, `係員マーレ`, identified by `pinnaParco5/map/sp/kakaritalk.sb`. |
| Sand castle spawn | `TSandCastle::explode` changes the castle to state 7, when retail enables its collision. The earlier demo queue is not the checkpoint. |
| Gelato mirrors | Accepted message 8 removes the mirror's last enemy. Each of the three mirror actors counts once. |
| Wiggler pounds | `TBossHanachan::execDamage` decreases health after the vulnerable body accepts the ground pound. |
| Mecha-Bowser hits | `TTinKoopa::hitParts` decreases the remaining-hit count after its rejection guards. |
| Noki Hidden launch pad | Mario accepts forced-jump status `0x884` on the static type-7 floor whose value is 30300. This is the two-triangle spring pad directly below the gold bird; a hanging bucket is unrelated. |
| Named Shine appearance | The relevant `TShine` reaches `TMapObjGeneral::appear`, with the exact Shine ID and active scene. Both retail Shine spawn methods call this entry; their `TItem::appear` logic is inlined. Queuing a cutscene or displaying another Shine does not count. |
| Red-coin button | `TRedCoinSwitch::receiveMessage` accepts message 1 and changes its ready state 1 to pressed state 2. This records the press before the animation finishes and the script flag changes. |
| Rocket collection | The accepted existing nozzle pickup callback has retail object ID `0x20000022`. Turbo boxes do not count. |
| Red and gold coins / balloons | The retail counts cross each requested threshold. Repeated observations of the same count do not duplicate a checkpoint. |

The Noki pad spans X 5822.3789–6322.3789, Y 2115.7734 and
Z −10443.5469–−10043.5469 in the retail collision map. Both Noki episodes 7
and 8 have the same two type-7 / value-30300 triangles in the inspected US and
PAL archives. The floor-owner check excludes actor-driven bounce surfaces.

## Scene continuity

The observer carries only an active, unchanged attempt through an armed retail
transition. It keeps the exact final secret destination even when the player
selects another parent episode. Pinna 6 Full Reds includes the additional
beach-to-park hop; Sirena Full Reds follows the chosen hotel/casino scenario.
The retail `TMarDirector::moveStage` parent tables are:

- Pinna park: `{0, 0, 1, 0, 2, 3, 4, 5}`.
- Sirena hotel: `{0, 0, 1, 2, 2, 0, 3, 4}`.
- Sirena casino: parent episode 5 uses scenario 1; all other parents use 0.

Pinna and Sirena hundred-coin attempts can retain their observer through
cross-area transitions within that same course. Same-area restarts and
unrelated courses do not use this exception. Airstrip and Pinna 1 preserve
their verified movie transitions. Savestate loads still invalidate ordinary
split/PB eligibility through the established assisted-attempt path.

Pinna 1 newly accepted movies 7 and 8 arm the same carry as the two retail
Exit Area skips: park `0x0D:0` → `0x0D:6`, then boss `0x3A:1` → `0x0D:7`.
Retail stage words `0x0E06` and `0x0E07` use `setNextStage`'s encoded form,
which subtracts one from the high byte to obtain the area. The Talk-to-boss
hop uses the existing exact `0x3A:1` transition. No movie-number exception
applies outside that active Pinna 1 attempt.

## Verification

`scripts/test_split_event_edges.py` compiles the actual production observer
functions into a small host harness. Its 25 tests exercise accepted/rejected
events, duplicate observations, exact NPC names, all ten Full Reds suffixes,
unfinished prefixes, all seven hundred-coin routes, excluded Delfino 100,
movie carry, all three Pinna 1 park scenarios, immediate red-button presses,
and every chosen Pinna/Sirena intermediate episode. Both Pinna 1 movie watching
and its two Exit Area skips exercise the complete observer lifecycle through
Talk and four boss hits; stale or rejected movie queues cannot arm a carry. It changes
only the retail calls and transport inputs needed to drive those functions.
The 17 existing lifecycle/route contracts in `scripts/test_split_events.py`
also pass with the expanded schema.

`scripts/audit_split_event_hooks.py --dol-dir <retail-dol-directory>` verifies
the seven new hook entry points against their named map symbols and displaced
instructions, plus the semantic field accesses used by the observers. The
recorded repair run passed 24 checks for each of JP, US and PAL (72 total), including
NPC offset `0x1D4`, Wiggler health `0x13C`, Mecha hit count `0x1C8`, mirror
enemy count `0x19C`, forced-jump status and the accepted movie flag. The audit
also proves that both retail Shine spawn methods call the hooked entry, and
checks the red switch's accepted message and state write. The two Pinna movie
destinations are read from each revision's actual dispatch table.

Local evidence is under `build/research/foxtrot-splits/`:

- `retail-hook-audit.json`: all-region DOL hashes and individual audit results.
- `retail-asset-audit.json`: US/PAL scene/script identities and Noki pad checks.
- `requested-checkpoints.json`: the final requested route/event tuple draft,
  reflected by the canonical schema hash `783A6D0F`.

The repaired hook/call-graph audit is separately recorded in
`build/research/foxtrot-split-repair/retail-hook-audit.json`, preserving the
initial implementation's evidence.
The subsequent Pinna movie audit is recorded in
`build/research/foxtrot-split-repair/movie-carry-retail-audit.json`.

The private US Dolphin repair proof uses shipping objects from build `C5AE8526`
with a separate request adapter. It invokes actual retail methods on actors
enumerated from the current conductor/map/item managers and reads the observer
without changing it. Lighthouse and Gold Bird Shine appearances, Sirena 2 Reds
and Noki 6 Reds switches, and Gelato 5/Pinna 1 NPC talks each advanced exactly
one checkpoint; repeated callbacks did not advance again. Noki Hidden also
passed the real launch-pad physics after controlled placement above the pad,
followed by the correct bird Shine appearance, advancing 0 → 1 → 2. Evidence,
adapter source and source hashes are in `build/foxtrot-split-repair-proof/`.

These are controlled retail-method checks, not complete human-played ILs.
A later natural Pinna 1 attempt reported no checkpoints; reviewing the full
lifecycle found that watching the first movie invalidated the observer before
Talk. The movie-carry repair now has host coverage, but its full gameplay
sequence and real-Wii validation remain on the focused tester list.
