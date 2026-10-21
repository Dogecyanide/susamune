# Live online ghost racing — feasibility

2026-10-13. Feasibility and prototype requirements. The user has authorized a
private Wii online prototype after the memory savings and three-fast-savestate
target are met. The initial assessment added no runtime code, reservations,
network service, SD install or timer change. The two-player prototype is now
being implemented following the user's successful PAL Wii State Test 3: all three
Pinna 3 loads took 0.267 s, saves took 0.500/0.534/0.567 s. The user deferred
the smaller mixed-level timing differences to later tuning. Preserve Test 3
as the working baseline.

## Recommendation

> **Superseded on 2026-10-21 (PR17).** Online play is now direct
> peer-to-peer with swapped room codes and no relay fallback; the relay
> client was removed from the mod. See `timewarp-pr17-p2p-online.md`. The
> relay server in `tools/live_relay/` is unchanged. The text below records
> the earlier relay decision.

The user chose **a room-code relay server** on October 13, so neither player
needs to configure home-router port forwarding. Each Wii opens one outbound UDP
path to the supplied server IPv4 address and port. The server creates a room
code and forwards poses and control messages between its two admitted players.
This replaces the earlier direct-peer connection plan. The user then chose
**free temporary hosting on their Windows PC**, with a Playit plain-UDP tunnel
forwarding to the local relay at `127.0.0.1:38400`. Both Wiis must use the tunnel's
public IPv4 address and assigned public port, which may differ from 38400.
Packaging a server does not create a Playit account, tunnel or running endpoint.

[Playit currently lists plain UDP as free](https://playit.gg/); its TCP+UDP option
is separate and paid. Only the host PC runs the agent. The included
`tools/live_relay/start-windows.cmd` uses Python 3.10+ without changing system
settings, and `tools/live_relay/README.md` gives the exact tunnel setup. The PC
must remain awake with both programs running. No rental or home-router changes
are required for this first setup.

The first requested test is the user in **the Netherlands against Orange in
Japan**. Orange confirmed JP; the user will use PAL 60 Hz. Measure the actual relayed round-trip time,
jitter and ghost presentation on that route. Do not derive it from a speed test
to a nearby server or geographic distance alone. Playit's free anycast routing
[can take indirect paths](https://playit.gg/support/playit-premium/); this initial
setup tests functionality and local responsiveness before optimizing relay
placement. Each tester first needs a successful Wii Internet Connection Test.

Two players racing independent local games with a live opponent ghost is a
credible next feature. Best-of-X IL rounds fit the existing IL lifecycle well;
StageLoader playlists need a shared playlist/rules contract and explicit scoring.
Four players are plausible, but three simultaneous remote bodies are a separate
rendering and memory milestone. Bandwidth is the easy part.

The user's requirement is native play without network input delay. Each machine
must own its Mario, input, physics, enemies, RNG and camera. The network supplies
only the other runners' visual poses and race events. Never wait for an opponent's
input or a packet before advancing the local game. Do not run a lockstep or
rollback simulation, add collision with remote ghosts, or replay their inputs
through local Mario. CPU/GPU overhead can still reduce frame rate, so absence of
an input-wait mechanism must be backed by performance measurements.

Remote ghosts will have network and interpolation delay. Smooth remote motion
does not mean zero network latency; a delayed ghost can cross the finish after
the result has already arrived. Use exact local result times for adjudication,
not which ghost appears to finish first or which packet reaches the server first.

## Player names

The user requested editable display names above remote ghosts: their tester
enters `Lotfy`, and the other racer sees `Lotfy` above that ghost's head. Include
this in the first two-player prototype. Reuse the menu's text-entry controls,
with a bounded name length and supported display characters. Keep the label
small and readable, positioned using the remote model's head or a checked
head-height anchor; hide it behind the camera or outside the current scene.

Send names with reliable roster updates, not in every pose packet. Names are
display text rather than player identity: bind each to the assigned participant
and session, render as literal text, and keep stable participant IDs for race
results even if names match or a player edits a name between races. Budget the
bounded strings and label rendering alongside the ghost, without adding any
network wait to local input or simulation. The implemented editor accepts 1-16
printable ASCII characters. The live provider draws a clipped label above the
remote body and sends the name in the session handshake. Wii appearance and
readability remain to be tested.

## Required cross-region racing

The user requires PAL, JP and US players to race each other in the first
prototype, explicitly including PAL versus JP. This is a release requirement,
not a stretch goal. Each participant keeps their native regional game. Exchange
canonical scene/episode/parent-scenario identities, poses and race events rather
than regional memory addresses, raw savestates or local input simulation.

The user clarified that runners use PAL's 60 Hz mode, not its slower 25 fps
mode. Target PAL 60 Hz alongside JP and US; slower PAL mode support/testing is
outside the initial prototype's acceptance scope. Audit the actual regional
stage/episode mappings and visual/model identifiers before declaring them
interchangeable. Carry the source region and actual timing mode in the session
contract; derive comparable elapsed times from the existing timer's read-only
outputs and the verified rate. Do not compare unconverted frame counts or
change the protected timer to normalize network results. Specify start/finish events
and any regional route differences in the agreed IL/playlist rules. Native
input and simulation remain independent of remote region and packet arrival.

The compatibility handshake must permit supported mixed-region rooms while
separately checking the online protocol and race-rule versions. This requirement
does not imply compatibility with arbitrary older Moonshine software builds.
The Wii prototype acceptance cases include PAL-60/JP, PAL-60/US and JP/US rooms,
with matching scene display and results. The wire/session implementation permits
all three regions at 60 Hz; fake-wire tests cover mixed-region admission. Actual
cross-region ghost display and race results remain untested on Wii.

## What exists and what does not

| Component | Local evidence | Remaining work |
| --- | --- | --- |
| Local racing presentation | Live snapshot capture/provider, four-sample interpolation, remote name label and existing second body slot are implemented; focused host fixtures pass | First Wii body/name/FLUDD and performance test |
| Timing and IL endpoints | Observer after existing `ILing::recordResult` admission; protected QFT remains read-only; best-of scoring and retry/assistance handling have focused host fixtures | First mixed-region Wii match and exact start/finish validation |
| Playlists | StageLoader has 120 entries, action bits, a frozen active queue/hash, attempts and active-QF totals | Canonical network manifest, per-step identity, agreed retry/scoring rules |
| Wii networking | Dedicated asynchronous ARM UDP worker and 2,720-byte cache-separated mailbox implemented; lifecycle fixtures pass; enabled launcher compiled and frozen | Relay client integration, final protected links and first hardware connection/reset test |
| Relay | Room-code UDP server and heapless client implemented; focused protocol fixtures pass; Windows launcher and optional Linux service packaged separately | Start the local relay and Playit tunnel, supply the public endpoint, and verify two Wiis |
| Dolphin networking | No Moonshine transport in the standalone GameCube build | Implement a BBA transport or an optional host companion |
| Four-player bodies | Two body heaps and two-runner draw paths exist | Third remote instance, attachments/effects bounds, GPU addressing and performance proof |

Source anchors: `include/susamune/ghost_format.h`, `ghost_fludd.h`, `ghost.hxx`,
`qft_timer.hxx`, `stage_loader.hxx`; `src/ghost_model.cpp`, `ghost.cpp`,
`iling.cpp`, `stage_loader.cpp`; `launcher/kernel/syscalls.h`.

The user confirmed Memory Probe 1 boot, menus, RAM state, RESET and relaunch on
Wii using a PAL SD ISO. That validates the tested cold-code path, not networking,
online rendering, another region, or a four-player load.

## Native Wii transport is credible without a PC bridge

The earlier [online feasibility notes](timewarp-feasibility-notes.md) correctly
left gameplay networking unproved. Upstream inspection now provides stronger
precedent: [Nintendont's BBA documentation](https://github.com/FIX94/Nintendont/blob/999aa851542424b82ca230ad7d3ddc31c40a6b6c/BBA_Readme.md)
describes WLAN and USB LAN support, supported online games and local networking.
Sunshine is not one of those supported titles, so enabling a setting does not
give this mod networking automatically.

Upstream [ARM `sock.c`](https://github.com/FIX94/Nintendont/blob/999aa851542424b82ca230ad7d3ddc31c40a6b6c/kernel/sock.c)
opens `/dev/net/ip/top` and `/dev/net/kd/request`, dispatches asynchronous IOS
socket operations and reports completions. Its generic 64-descriptor bridge
reserves a 128 KiB heap at physical `0x13040000`; this is precedent for ARM
network access, not an allocation to copy into Moonshine. Upstream
[`main.c`](https://github.com/FIX94/Nintendont/blob/999aa851542424b82ca230ad7d3ddc31c40a6b6c/kernel/main.c)
initializes that socket service before releasing gameplay.

Our fork initially lacked that socket source, initialization and BBA path. Its loader
reloads patched IOS58 on Wii/vWii, arranges module loading, and launches the
Nintendont ARM thread. It later suspends the WC24 scheduler and destroys its
PPC loader threads before entering the game (`launcher/loader/source/main.c`).
Consequently, a loader socket/worker cannot simply be retained as the gameplay
client. A small dedicated ARM service using IOS sockets is the preferred Wii
direction; initialize it under the final IOS environment and give it an explicit
shutdown/restart protocol. That service now exists as `MoonshineNet` and
`MoonshineNetBridge`; it uses bounded queues and retains IOS-owned buffers until
completion or socket retirement. Suspending WC24 scheduling is not proof that
ordinary sockets are unavailable, nor proof that initialization will succeed.

The current [libogc Wii network source](https://github.com/devkitPro/libogc/blob/e3764ac5688d423662e4e146af6b87da28499cde/libogc/network_wii.c)
shows network configuration/link queries, socket startup and asynchronous IOS
initialization. Its PPC wrapper takes a 64 KiB arena heap plus other resources.
Porting the entire wrapper into the injected game is unnecessary; extracting a
small ARM service still requires a measured memory/stack budget and the correct
IOS operation semantics. Modern TLS compatibility and credentials are separate
unknowns from basic UDP connectivity.

The first private hardware test must prove: open/init after handoff; bounded
UDP send/receive to a controlled relay; progress during SD/USB/disc loading;
disconnect and unavailable Wi-Fi; RESET while I/O is outstanding; relaunch with
stale packets; and no input/frame-time regression. Repeat for Wii U/vWii only
before claiming those targets. Failure must leave offline practice functional.
The enabled launcher has compiled and the asynchronous ownership fixtures pass.
No real Wii network connection has yet been demonstrated.

## The supplied Slippi repositories materially help

The user's [Project Slippi repository](https://github.com/project-slippi/project-slippi)
is a project map linking separate game patches, emulator, launcher and Nintendont
work. Following those links distinguishes two useful implementations: native Wii
replay transport and desktop matchmaking. Melee's age is not the limitation;
which processor/environment owns the transport is what determines reuse.

### Slippi Nintendont: useful native Wii networking

Inspected the requested `slippi` branch at
`bea169ecd170f9b49b73c49e831189afd0dc8c9b`. Its
[SLIPPI.md](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/SLIPPI.md)
documents native replay streaming over Wi-Fi/USB Ethernet and a dedicated ARM
server thread. This is more directly applicable than the desktop emulator. The
document also warns that network initialization timing/disc pressure caused
Melee freezes; the current source initializes in its boot sequence. Treat that
warning as a reason to measure our lifecycle, not a delay value to copy blindly.

| Source | Useful evidence | Moonshine adaptation |
| --- | --- | --- |
| [`kernel/net.c`](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/net.c) | ARM-side IOS network initialization and socket/connect/send/receive/poll wrappers; aligned IOCTL arguments | Small bounded socket backend; preserve errors/timeouts and avoid per-packet allocation/blocking on the PPC path |
| [`kernel/SlippiNetwork.c`](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/SlippiNetwork.c) | Dedicated thread, one TCP replay client on port 51441, handshake/version/session token, keepalive and cursor-based reconnect | Worker/session patterns; use an outbound race-relay connection and latest poses rather than replay catch-up |
| [`kernel/SlippiNetworkBroadcast.c`](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/SlippiNetworkBroadcast.c) | UDP LAN discovery on port 20582, separate thread | Optional LAN room discovery; not internet matchmaking |
| [`kernel/SlippiMemory.c`](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/SlippiMemory.c) | Monotonic replay cursor, bounded ring, explicit lagging-reader overflow | Generation/cursor lessons; keep a tiny snapshot history instead of its complete replay ring |
| [`kernel/main.c`](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/main.c) | Starts network services and cancels the replay thread on shutdown | Integrate explicit in-flight drain/retirement with Moonshine's stronger reset/ownership rules |

This is not Wii online Melee matchmaking or remote gameplay input exchange. The
client consumes replay data; the inspected Wii branch has no counterpart to the
desktop matchmaking class. It is nevertheless concrete source precedent for
network traffic while a native GameCube game runs under a related custom
Nintendont. That strengthens the no-PC-bridge Wii racing case substantially.

Do not merge the fork or its memory map wholesale. Its **3 MiB** replay ring at
physical `0x12B80000–0x12E80000` lies inside Moonshine's savestate pool. It also
uses a **25,000-byte** read buffer, a **25,500-byte** serialized replay buffer,
and an **8 KiB** network-thread stack (plus client/parser/IOS allocations and
other threads). Those are source constants, not a complete measured peak.
Moonshine's small independent poses do not need that backlog. Its network
shutdown is thread cancellation, which does not establish our required proof
that all outstanding writes have retired before a buffer is reused. Its
32-bit replay token is likewise not a substitute for authenticated race sessions.

### Slippi matchmaking: reuse the structure, not its rollback path

The linked emulator branch was inspected at
`60f7b63496fb6ec7b9180a04f16f3edc0ad89fe2`.
[`SlippiMatchmaking.h`](https://github.com/project-slippi/Ishiiruka/blob/60f7b63496fb6ec7b9180a04f16f3edc0ad89fe2/Source/Core/Core/Slippi/SlippiMatchmaking.h)
separates search modes (including direct codes and teams) from connection states.
[`SlippiMatchmaking.cpp`](https://github.com/project-slippi/Ishiiruka/blob/60f7b63496fb6ec7b9180a04f16f3edc0ad89fe2/Source/Core/Core/Slippi/SlippiMatchmaking.cpp)
uses reliable ENet messages for tickets carrying user, search and application
version; responses assign match/roster information and opponent addresses before
the peer connection phase. Its IP/port reuse and hole-punch flow are a reference
if peer-to-peer connectivity is ever desired. A room relay remains simpler for
the initial two-to-four-player design.

The reusable architecture is: explicit account identity → cancellable search or
friend-code join → server-assigned room/roster → compatibility/rules agreement →
connection/ready state → race. It can work without rollback. The actual client
uses desktop threads, dynamic C++/JSON, ENet and Rust extension interfaces; it is
not a drop-in ARM library. Do not port SlippiNetplay's frame/input queues, timing
adjustments or prediction into Sunshine; Moonshine's local Mario continues to
run independently.

These repositories expose client code, not a granted API/service contract for
Moonshine. Use a Moonshine-owned room/matchmaking service or an explicit agreement
with a willing operator. Do not send Moonshine users, tokens or traffic to
Slippi's production endpoints merely because their addresses are public.
No request was made to a Slippi matchmaking endpoint during this assessment.

Source reuse needs a per-file license/notices audit. Slippi Nintendont's kernel
retains GPLv2 notices; the emulator repository ships
[GPLv2 license text](https://github.com/project-slippi/Ishiiruka/blob/60f7b63496fb6ec7b9180a04f16f3edc0ad89fe2/license.txt).
Its vendored [ENet license](https://github.com/project-slippi/Ishiiruka/blob/60f7b63496fb6ec7b9180a04f16f3edc0ad89fe2/Externals/enet/LICENSE)
is MIT. The ARM socket file identifies libogc and FIX94 ancestry but lacks a full
per-file grant in its header, so preserve and resolve upstream notices before
copying it. Architectural study is the current action; no Slippi code has been
imported into runtime sources.

## Standalone Dolphin needs its own backend

The ordinary Moonshine Dolphin build is a GameCube program with fake MEM2,
not the custom Wii ARM kernel. Wii IOS socket code therefore does not provide
it a connection. Dolphin's
[built-in BBA implementation](https://github.com/dolphin-emu/dolphin/blob/e2ad09306e6d371f7272205bdc363da9fe05fe08/Source/Core/Core/HW/EXI/BBA/BuiltIn.cpp)
handles Ethernet/IP traffic and forwards UDP through nonblocking host sockets.
This supports a credible no-extra-companion route using an emulated BBA, but
Moonshine must still supply the GameCube-side device/packet code and bounded
ARP/IP/UDP/configuration handling. Sunshine has no existing online client to reuse.

An optional host companion reading a small explicit mailbox is faster for early
protocol experiments, but it would not satisfy a no-companion product goal.
Keep the application protocol backend-neutral so native Wii, Dolphin BBA and
an optional development bridge can interoperate. Dolphin Netplay is not the
solution for independent local Sunshine games: it synchronizes supported local
multiplayer execution and input, whereas this design exchanges presentation.
See the [official Netplay guide](https://dolphin-emu.org/docs/guides/netplay-guide/).

## Bounded live poses and concrete costs

### Implemented two-player foundation

`live_race_wire.h` defines a 32-byte MSR1 header and 48-byte independently
decodable pose: **80 bytes before relay framing**. It carries canonical scene
and parent-episode identity, sender time, scene generation, position, yaw,
animation, held-object identity, Yoshi and FLUDD observation. It carries no
regional pointer, savestate, ghost file or gameplay input. `live_race.cpp`
publishes at most roughly 30 times per second using monotonic elapsed time.

The relay envelope adds 48 bytes, so each pose is a 128-byte UDP payload.
At 30 poses/second this is 3,840 bytes/second per sender, or 4,680 bytes/second
including IPv4/UDP headers. For two players the relay sends 9,360 bytes/second
of pose traffic in total before link overhead, keepalives, reliable control and
retries. This is protocol arithmetic, not measured bandwidth or a hosting quote.

`live_ghost.cpp` keeps four samples, starts with an 80 ms interpolation delay
and hides a stale ghost after 250 ms without a fresh sample. Scene changes,
teleports and new timelines clear interpolation. These are starting parameters
for the Netherlands-Japan test, not measured end-to-end presentation latency.
The existing personal ghost keeps slot 0; the remote racer borrows slot 1.
Watch retains its existing ownership when active.

The enabled ARM worker's measured code/rodata is 6,092 bytes and mutable data is
11,364 bytes before alignment. The bridge adds 2,832 bytes of code and 2,776
bytes of BSS, including its 2,720-byte cache-separated mailbox. The worker's
socket buffer requests total 8 KiB; IOS overhead is not measured. Its 8 KiB
stack is included in worker mutable data. The frozen enabled kernel has 39,580
code bytes and 37,536 data/BSS bytes spare within its existing reservations.
These are compile/link measurements, not hardware memory or throughput proof.
See `doc/live-transport-lifecycle.md` and the launcher/transport build receipts.

Final PPC and relay-client costs are pending the protected all-region link.
Do not subtract an estimate from savestate capacity or count the same freed
bytes twice. The relay uses the existing transport mailbox and socket.

### Earlier four-player sizing exercise

The existing packed pose is **16 bytes**, FLUDD observation **8 bytes**, and held
object descriptor **6 bytes**. `Ghost::VisualState` is **44 bytes** under the PPC
ABI. A freestanding PowerPC compile checked those actual types in
`build/timewarp-racing-feasibility/abi.cpp`; it also checked the following
arithmetic-only proposed packet at 80 bytes. The following table is the original
planning model; it is distinct from the implemented MSR1 layout above and does
not describe the final relay wrapper or provide encryption/authentication.

| Proposed live snapshot field | Bytes |
| --- | ---: |
| Type/version, room incarnation, round, sender, scene generation, sequence, sender monotonic tick, absolute attempt QF and flags | 32 |
| Existing packed position/yaw/animation pose | 16 |
| Existing FLUDD observation | 8 |
| Held-object identifier/name key and visual flags | 8 |
| Authentication tag allowance | 16 |
| Total application payload | **80** |

Every pose is independently decodable. The existing pose's delta-QF field can
be canonical zero because the envelope carries absolute QF; do not create a
chain in which losing one packet loses later poses. Full route/playlist/build
identity belongs in reliable control messages; the scene generation binds each
pose to that accepted descriptor. No pointers, heap addresses, ghost files,
savestate blocks, complete inputs or camera tracks belong in this stream.

At 20 updates/second, with separate forwarded datagrams per opponent and 28
bytes of IPv4+UDP overhead:

| Players | Client upload | Client download | Relay outgoing per room |
| --- | ---: | ---: | ---: |
| 2 | 2,160 B/s | 2,160 B/s | 4,320 B/s |
| 4 | 2,160 B/s | 6,480 B/s | 25,920 B/s |

These figures include the proposed authentication allowance, but exclude link
overhead, connection setup, control retries and additional encryption framing.
At 30 Hz multiply by 1.5. A four-player room would send about 93.3 MB/hour from
the relay at 20 Hz before those extras; this is arithmetic, not a hosting quote.
Send rate must follow monotonic elapsed time, never the number of frames Dolphin
can render at unlimited speed. Local sample capture occurs after the existing
game update; networking can reuse the latest captured pose.

Proposed **shared application-data ceiling: 16 KiB**, not yet assigned an address:

| Allocation | Bytes |
| --- | ---: |
| Three remote histories: 32 samples × 64 checked bytes | 6,144 |
| Outgoing ring: eight 96-byte aligned slots | 768 |
| Reliable control/event queue: 32 × 128 bytes | 4,096 |
| Canonical playlist manifest: up to 120 × 12-byte entries plus header | 1,536 |
| Three decoded visual states, aligned aggregate | 160 |
| Session/peer scalar state allowance | 512 |
| Cache-line-separated publication/consumption state | 256 |
| Proposed subtotal / ceiling | **13,472 / 16,384** |

That proposed model assumes authentication before placing the 64-byte body in
the receive history. Thirty-two samples retain up to 1.6 seconds at 20 Hz; that is a capacity
bound, not a recommendation to delay the display by 1.6 seconds. Start testing
roughly 50–150 ms interpolation delay, short capped extrapolation, then fade or
hide a stale ghost. Never extrapolate through scene transitions, teleports or
attempt changes. Label connection loss without interrupting local controls.

This ceiling excludes executable code, IOS socket buffers, worker stack,
crypto/TLS state, the Dolphin BBA backend and models. Total implementation cost
is unknown until those compile and are measured. Do not count the 16 KiB as
currently free memory, take it from the new savestate capacity, or borrow the
ghost/savestate transfer area while ARM can own it. A tiny dedicated mailbox
with one writer per cache line and bounded asynchronous work is preferable to
holding the bulk-storage lease for an entire race. Retire it alongside storage
before reinjection/reset; stale sessions and sequence wrap must not revive old
data. Network ownership and assistance latches must stay outside restored game
state.

## Bodies, attachments and the four-player stretch

The renderer has exactly two 90,112-byte body heaps in MEM2, `MODEL_SLOT_COUNT=2`,
two `VisualState`s and six attachment slots (held/Yoshi, FLUDD body, nozzle per
runner). Attachments share the existing **128 KiB MEM1** heap. Two body heaps are
176 KiB; a third with the current allocation strategy would add **88 KiB MEM2**
before attachments and scalar state. The current Mario instance measurement is
83,164 bytes plus 304 heap overhead, with a conservative 87,040-byte usable
preflight. Refer to [Mario ghost evidence](v2.3.3-mario-ghost.md).

An observed FLUDD body/nozzle pair used 33,436 + 7,476 = **40,912 bytes** in a
specific rendering fixture. Three such pairs alone total 122,736 bytes, leaving
8,336 of the MEM1 attachment reservation before heap overhead, Yoshi or held
objects. That is not a proven three-runner fit or a worst-case bound. See
[lighting/animation evidence](v2.3.3-ghost-lighting-animation.md).

The two-player prototype reuses slot 1 for the remote racer and keeps personal
playback in slot 0. Stored recordings are preserved. Watch retains both of its
existing slots while active. Supporting two remotes would need explicit provider
ownership changes; two models do not mean three-player racing already works.
Four-player full bodies require a third
independent model/matrix/packet instance; immutable geometry can potentially be
shared after audit, but sharing mutable animation or draw state is unsafe.

Budget-friendly fallback options are coloured low-detail bodies, disabling
remote held/Yoshi attachments and water effects, or an explicitly simpler
marker/racing line for an opponent. Use consistent lower-detail presentation
if selective full bodies would be confusing. None of these changes local Mario's
gameplay. Culling, animation rate and effect caps need Bianco 5/Pinna 3 stress
measurements with all racers on screen.

There is also an inherited standalone Dolphin obstacle: production ghost body
matrices/display lists use fake-MEM2 addresses that the retail GX path does not
make GPU-accessible. Earlier private proofs placed one body in the MEM1
attachment area and limited attachments. That is not a completed multi-body
Dolphin solution. Solve or separately scope that before promising cross-platform
live ghosts. Real Wii MEM2 has different addressing; it needs its own body tests.

## Race contract and lifecycle

The initial prototype admits JP, US and PAL 60 Hz on the same validated build.
The room creator selects a canonical IL catalogue entry, stable PB slot, episode
and Best of 1/3/5/7 before connecting. Both players must be ready. Reliable
session messages carry configuration, start and results; packet delivery ACKs
do not imply the game accepted a requested transition. Room, session and round
identities reject old traffic. The relay transports these messages; each game
adjudicates the same client-reported local times. There is no authoritative
ranked-result service in this prototype.

Each round compares each player's first admitted eligible IL time. Retries are
allowed before that finish. Lower elapsed QF wins, ties replay, assistance voids
the round, and first to `floor(X/2)+1` wins ends the match. Reconnect with a new
room for another match. This is a best-time IL round, not a synchronized
wall-clock first-to-finish race. Playlist races and a shared countdown are later
features with separate retry, load-time and scoring contracts.

The result observer runs after existing `ILing::recordResult` admission. It
checks the chosen entry and exact starting destination, and does not consume
the timer's one-shot shine/transition/Bowser events a second time. QFT hooks,
source, scratch and timing behavior remain protected. Inputs and physics never
wait for the relay; start skew is not hidden by changing the timer. Focused
fixtures cover scoring, ties, voids, duplicate messages, readiness cancellation
and reordered control delivery. These do not establish hardware timing or
regional route equivalence.

For StageLoader races, serialize the actual canonical route/action for every
entry, including parent episodes, Plaza choices, duplicates and order. Do not
send transient menu indexes or rely solely on the existing local 32-bit hash.
Freeze and validate the complete manifest; use a versioned digest for identity.
Bind each event to playlist index, step/attempt generation and expected endpoint.
Racers advance independently. Display a ghost only when scene/episode/parent
variant and step identity match; otherwise show progress or the opponent's stage.

The fairest first playlist mode is the existing notion of accumulated active
QFs, including failed/retried active attempts, with agreed penalties. StageLoader
already accumulates positive QF deltas in `totalObservedActiveQf`; verify every
failure/departure path before making it authoritative for racing. This avoids
making SD/disc loading speed decide the result. A wall-clock first-to-finish
marathon is another valid mode, but its start skew, loads and pauses count and
must be presented explicitly. Do not mix active-QF ranking with a claim of
first-to-finish wall-clock ranking.

Scene changes invalidate interpolation and require a fresh scene generation.
Hardware/software reset ends the online session and retires network buffers
before code/model reuse. A lost connection requires a new room; the prototype
does not retrieve/resume an old match or replace its guest. A later competitive
disconnect policy must define forfeit, grace and resume behavior explicitly.

Any state/position load, TAS takeover, slowdown, fast-forward, prohibited pause,
warp or rules-changing setting makes a strict round assisted/ineligible. Keep
that verdict monotonic outside savestate restoration. A friendly practice room
may allow assistance when advertised, but cannot submit it as a clean result.
Current CRCs, build identifiers and even authenticated packets do not prove an
honest client. Initial results should be described as friend races with client
reported times, not a cheat-proof ranked system.

## Relay and useful help from the website owner

Use one outbound UDP path to a relay per device rather than requiring friends
to configure port forwarding or peer-to-peer NAT traversal. Unreliable sequenced
pose datagrams can drop old samples; bounded acknowledged control messages carry
join/ready/start/finish. Reject oversized/malformed/out-of-
order/old-session messages and cap processing per frame and worker pass. If the
control queue fills, fail that online session visibly instead of losing a finish
or blocking the game. The relay implementation must validate return reachability
before allocating a room or forwarding traffic, cap room/session lifetimes and
rates, and bind peer messages to the admitted endpoint and session. This is a
private friend-test protocol without encryption, accounts or ranked anti-cheat.
The 16-byte authentication tag in the earlier sizing table is only an allowance;
do not claim it exists in the prototype. A public service requires its own
credential/abuse design and reviewed protection before wider release.

The existing ghost website is useful for identities, account linking and a room
page, but uploading full ghost files or polling a database is not the live-pose
transport. A separate small real-time relay may be needed. No assumption is made
about the website's ability to run arbitrary UDP services.

Helpful information from its owner, when implementation reaches this point:

- Whether they want to own room/account integration and operate a real-time relay,
  or prefer a separately hosted service linked from the site.
- A test environment, account-linking/pairing contract, scoped token issue/revoke
  flow and documented compatibility requirements; no production secrets needed.
- Room lifetime, regions, simultaneous-room budget, abuse/rate limits and whether
  UDP is deployable there; TLS versions/certificates for console pairing.
- Canonical IL/playlist identifiers and whether friend-race results stay separate
  from public leaderboards until a verification/moderation policy exists.

No message was sent to the owner and no service was deployed.

## Remaining release gates

1. Retain the successful State Test 3 behavior and its memory layout. Final
   all-region links must preserve the protected timer and fit current capacities.
2. Finish the room-code relay integration and focused protocol/lifecycle checks.
   Package the frozen enabled launcher with matching JP/US/PAL mod payloads.
3. Start the relay on the user's Windows PC and create the free Playit plain-UDP
   tunnel to `127.0.0.1:38400`. Supply its public IPv4/assigned port to both Wiis.
   Account login/agent claiming remain with the user. No rental is needed.
4. Run the two-Wii Netherlands-Japan test: connection, names, cross-region scene
   display, local responsiveness, best-of scores, departure/reset and reconnect.
   Follow `doc/timewarp-online-testing.txt`; no full savestate retest is needed.
5. Add canonical StageLoader playlists with explicit retries/load/scoring rules.
6. Attempt three remote models after real per-frame and memory measurements;
   keep four-player mode a stretch. Standalone Dolphin needs a separate backend.

Local evidence: `build/timewarp-racing-feasibility/receipt.json` records actual
PPC ABI assertions and arithmetic; `sources.json` pins the downloaded upstream
source revisions and hashes. `slippi-source-files.json` separately pins the
focused Slippi files; the saved tree inventories identify the exact requested
branches. These are source/compile feasibility results, not
live multiplayer, network throughput, hardware latency or full rendering tests.
