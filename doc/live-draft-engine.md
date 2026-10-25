# Online draft and set engine

`LiveDraft` is a deterministic, allocation-free state machine with 28 bytes of state.
It does not read game state, launch levels, transmit packets, select random entries, or enforce catalogue membership.
The host chooses five distinct eligible catalogue IDs; the integration validates their pool membership on both peers.
The engine rejects duplicate IDs and the reserved `NO_ENTRY` value.

`begin` initializes a fresh nonzero generation at revision 1 with a Bo3 or Bo5 set.
Every subsequent accepted action increments the revision.
Commands carry a `Token` containing the expected generation and revision; stale, future, or invalid actions leave state unchanged.
The revision stops accepting actions at `UINT32_MAX`, preventing wraparound from admitting old commands.
State is local runtime data, not a wire format.

The opening draft gives host one ban, guest two bans, and host the pick from the remaining two.
Every IL is first to two round wins, independently of set length.
After an IL, its winner bans one of a fresh five and its loser picks one of the remaining four.
The set ends after two IL wins for Bo3, or three for Bo5.
`currentActor` returns host, guest, or no player according to the current phase.

`pick` enters `IL_MATCH` and resets the per-IL round scores.
It never warps either player; the live session must retain its separate both-Ready gate.
`recordRound` consumes a completed round once, with host/guest winner or `NO_PLAYER` for a tie, cancellation, or assisted result.
No-contest results advance revision without awarding points.
The previous IL's scores remain available during the next draft until a new IL is picked.

The integration must serialize authoritative commands, verify the peer and phase before applying them, and compare revisions before acknowledging an application action.
Transport delivery alone is not proof that an action was accepted.
Do not advance the same round through both a duplicate packet and a local finish callback.

`test_live_draft.py` compiles the production engine and covers all 120 opening draft paths, actor/phase rejection, atomic malformed-input rejection, tied and invalid rounds, full Bo3/Bo5 sets with changing counterpickers, stale generations/revisions, counter rollover, and matching replica state after each command.

## Catalogue pools

`ILing::onlinePoolContains(entry, pool)` validates catalogue IDs independently of episode choices and PB profiles.
Pool IDs are Any% 0, All 1, and Non Any% 2.
All three exclude Noki 5, Pianta 2, Gelato 5, Bianco II Enter, and Noki Enter.

Any% contains the exact existing theory route plus its Secret-only variants.
The EYG route admits Pinna 6 Secret, but does not admit ordinary Pinna 6 Full.
GBS does not admit Gelato 1 Secret or ordinary Gelato 8.
Ricco 2 Race, Noki 4 Eel Only, and Bowser-only are alternate starts rather than exact-route or Secret-only entries.
Non Any% is the entry-level complement within the allowed All pool, including these alternate starts and the new Gelato Enter movement IL.
Bonus Reds, Full Reds, hidden Shines, and 100-coin entries do not inherit their parent secret's classification.

For the current 133-entry catalogue, the pools contain 60, 128, and 68 entries respectively.
`test_online_il_pools.py` verifies every catalogue entry against an explicit expected list, the shared exclusions, the disjoint/complement relationship, movement entries, secret variants, and invalid IDs.

## Live session integration

`LiveRace` sends host-authoritative begin, next-five and applied-choice events
through the existing reliable control channel. A guest sends a request with
the expected draft generation/revision; it does not advance its draft until
the host's accepted event arrives. Neither side advances on local queue
backpressure. Events encode fields explicitly, rather than copying `State`
bytes onto the wire. Both peers validate catalogue membership and the engine
checks the actor, candidate, phase and token.

Five distinct candidates are sampled from the selected pool with a private
host PRNG; the game's RNG is untouched. Round results are exchanged before
the host sends the next five. Both sides convert local/peer winners to the
same host/guest identity. A selected IL still needs the normal offer and both
Ready gates. Continuing offers must retain the agreed configuration; changing
the pool, entry or match rules requires the completed-match setup flow.

`ILing::onlineDefaultEpisode` uses catalogue starts independently of saved
episode choices, including Gelato Enter's plaza-state selector. Production
`startOnline` temporarily applies that choice and restores the user's saved
one. The catalogue fixture checks all 133 destinations against all nine
persisted episode values.

The two-peer session fixture covers 24 cases, including full Bo3/Bo5 sets,
changing counterpickers, ties/assistance, both-Ready gating, invalid messages,
backpressure, lost/retransmitted events, same-room rematches and free roam.
These are executable source checks; console UI, network timing and match
flow still require the PAL60/JP Wii test.
