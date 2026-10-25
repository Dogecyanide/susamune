# Guest invitations

`live_invites.cpp` owns up to three independent UDP punch slots for a host.
Each uses the existing two-party punch packet: every guest punches the host,
and the host relays group state. Guests do not connect to each other.
The invitation index is a UI slot, not the roster player number. Session
handshake order still assigns the roster, so display the connected name.

Keep this storage outside `LiveRace::Runtime`, whose retained layout is pinned.
It uses ordinary existing mod BSS, without increasing MEM1/MEM2 reservations.
Changing one invitation must preserve the other pending and connected slots.
Only an explicitly invited endpoint may start a host handshake. Match incoming punches
by endpoint before considering a unique pending public IP with a changed port;
an old guest's packet must never redirect a different invitation.

The shared room secret cannot disambiguate several guests whose NAT changes
their ports behind the same public IP. Do not guess between those invitations.
This remains direct UDP networking, without a relay fallback.

Group drafts remain in `NeedCandidates` until the room is full. Those zeroed
candidate fields are not IL catalogue entries: render the waiting state until
the authoritative candidate list arrives.

Checks: `test_live_race_join`, `test_live_group`, `test_online_menu_routes`.

## Recovery and delivery (PR29)

A reserved session must keep its endpoint in `info.peer` even while LISTENING.
`startHost` initializes it from `allowedPeer`; otherwise the second timeout loses
that reservation. `LiveGroup::receive` routes known endpoints before vacant
listeners, including when their packets are stale and should be rejected.

Only explicit Leave destroys the local room during ordinary network failures.
An authenticated host kick is a separate terminal removal: clear the invitation
before sending it, retry for three seconds, and stop the kicked guest's retries.
The shared room PIN alone must never grant admission to a vacant invitation.
Transport retirement triggers a delayed reopen and new shared STUN probe, retaining
invitations, room rules and scores. STUN lookup failures retry without closing the
menu. Group readiness/racing can cancel on loss; a previously prepared warp must
not remain armed through recovery. A changed public endpoint still needs new codes.

The PPC transport has one replaceable pose mailbox for a two-player link. Group
bundles use the bounded PPC FIFO so all recipients reach the bridge. PR32's ARM
bridge moves these into three endpoint-specific latest slots; RX has equivalent
slots and continues draining IOS even while PPC is stalled. Controls retain their
own bounded FIFO, alternating with movement. Never put all peers into one latest
slot. Protocol 7 removes the eight controller bytes from group entries. The
48-byte movement body still includes held objects, Yoshi and FLUDD visuals.

`MoonshineNetLog.c` captures on ARM main only and writes in the existing idle-disc
FAT service slot. Never write files from the network worker. Logs are capped at
4 MiB per boot and preserve earlier files. They include endpoint metadata but no
room secrets or raw payloads. See `pr32-testing.txt` for collection paths.
