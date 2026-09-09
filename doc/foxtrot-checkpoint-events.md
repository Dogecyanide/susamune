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
| Gelato 5 Talk | The accepted dummy NPC talk is connected to Piantissimo's `TEnemyMario`. Ordinary NPCs do not count. |
| Pinna 1 Talk | The accepted talk names the park director, `マーレＢ`, identified by `pinnaParco6/map/sp/enchotalk.sb`. |
| Pinna 8 Talk | The accepted talk names the ride attendant, `係員マーレ`, identified by `pinnaParco5/map/sp/kakaritalk.sb`. |
| Sand castle spawn | `TSandCastle::explode` changes the castle to state 7, when retail enables its collision. The earlier demo queue is not the checkpoint. |
| Gelato mirrors | Accepted message 8 removes the mirror's last enemy. Each of the three mirror actors counts once. |
| Wiggler pounds | `TBossHanachan::execDamage` decreases health after the vulnerable body accepts the ground pound. |
| Mecha-Bowser hits | `TTinKoopa::hitParts` decreases the remaining-hit count after its rejection guards. |
| Noki Hidden launch pad | Mario accepts forced-jump status `0x884` on the static type-7 floor whose value is 30300. This is the two-triangle spring pad directly below the gold bird; a hanging bucket is unrelated. |
| Named Shine appearance | The relevant `TShine` reaches `TItem::appear`, with the exact Shine ID and active scene. Queuing a cutscene or displaying another Shine does not count. |
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

## Verification

`scripts/test_split_event_edges.py` compiles the actual production observer
functions into a small host harness. Its 18 tests exercise accepted/rejected
events, duplicate observations, exact NPC names, all ten Full Reds suffixes,
unfinished prefixes, all seven hundred-coin routes, excluded Delfino 100,
movie carry and every chosen Pinna/Sirena intermediate episode. It changes
only the retail calls and transport inputs needed to drive those functions.
The 17 existing lifecycle/route contracts in `scripts/test_split_events.py`
also pass with the expanded schema.

`scripts/audit_split_event_hooks.py --dol-dir <retail-dol-directory>` verifies
the six new hook entry points against their named map symbols and displaced
instructions, plus the semantic field accesses used by the observers. The
recorded run passed 16 checks for each of JP, US and PAL (48 total), including
NPC offset `0x1D4`, Wiggler health `0x13C`, Mecha hit count `0x1C8`, mirror
enemy count `0x19C`, forced-jump status and the accepted movie flag.

Local evidence is under `build/research/foxtrot-splits/`:

- `retail-hook-audit.json`: all-region DOL hashes and individual audit results.
- `retail-asset-audit.json`: US/PAL scene/script identities and Noki pad checks.
- `requested-checkpoints.json`: the final requested route/event tuple draft,
  reflected by the canonical schema hash `783A6D0F`.

These host and retail-data checks establish the event and lifecycle contracts;
they do not claim that every newly added route has been played through on Wii
or Dolphin. The focused tester list covers that remaining gameplay validation.
