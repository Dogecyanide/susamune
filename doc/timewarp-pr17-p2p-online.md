# PR17 online: direct (peer-to-peer) play

The Online tab now connects two players directly. There is no relay server and
no relay fallback. Racing itself is unchanged: the session handshake, setup,
draft, Ready, results and Disconnect all work as before. Only the way the two
consoles find each other changed. Online still needs 60 Hz.

The relay client is deleted from the mod: `src/live_relay.cpp`,
`include/susamune/live_relay.hxx`, `include/susamune/live_relay_wire.h` and
`scripts/test_live_relay.py`. These stay unchanged:

- `tools/live_relay/server.py` and its socket test
- the Dolphin companion (`tools/dolphin_online/`)

## Flow

1. **Create room** (host) or **Join room** (joiner) opens the race socket. A
   console uses the fixed local port 48222; Dolphin uses port 0.
2. STUN runs on that same socket (`LiveStun::startShared`), so the public
   address it learns is the one the other player has to reach. Its NAT verdict
   appears on the NAT test row.
3. **Your code** shows that public address as a 16-character room code.
4. The players swap codes. The joiner enters the host's code under
   **Friend's code**; the host enters the joiner's code the same way. Join room
   opens the keyboard straight away.
5. Both consoles send small punch packets to each other every 200 ms. The
   joiner's session also sends its HELLO every second. The first packets open
   each NAT for the other side.
6. The existing `LiveRaceSession` takes over: the host calls `startHost`,
   listening for any HELLO that carries its PIN, and the joiner calls
   `startGuest` with the host's address. Once connected, punching stops; the
   session's one-second pings keep both NAT mappings open.

## Online tab

Status lines at the top:

1. `<connection>  |  Peer: <name>  |  <ping>`. The connection text is one of:
   Offline, Starting network, Getting your address..., Waiting for friend,
   Connecting directly..., Can't connect directly, Connected.
2. Score
3. Race message
4. Until connected, a hint:
   - Host: "Swap codes: send yours, enter theirs as Friend's code"
   - Joiner: "Swap codes: enter the host's, send yours to the host"
   - After a failure: "Check both codes. A strict router or firewall may block direct play"
   - Symmetric NAT, shown as soon as STUN detects it: "Symmetric NAT: the router changes ports per peer; direct play fails"

   Once connected, this line shows Ready/Peer/setup as before.

Rows:

| Row | Value / action |
| --- | --- |
| Name | Online name (keyboard; offline only) |
| Create room | Start / Unavailable |
| Join room | Start / Unavailable; then opens the Friend's code keyboard |
| Your code | `XXXX-XXXX-XXXX-XXXX`, "Getting address..." or `--`; A: "Send this code to your friend" |
| Friend's code | The entered code, "Enter" or `--`; A opens the keyboard |
| IL race, Episode, Best of, Mode, IL pool, Set length | unchanged |
| Ready, Apply next setup, Draft IL list, Disconnect | unchanged |
| NAT test | STUN verdict ("Press A or X", "probing...", "SAME - punching should work", "DIFFERENT - symmetric NAT", ...); A or X runs it offline |
| Opponent inputs, Diagnostics | unchanged |

Removed: Server IP, Server port, the six-digit Room code, their digit editor
and every relay status string. The packet diagnostics line reads
`PPC TX n RX n OK n`.

Code entry errors appear as toasts. For example, "Code not valid - check every
character", "That is a host code - enter the joiner's code" and "That is your
own code".

## Room code

16 symbols from `23456789ABCDEFGHJKLMNPQRSTUVWXYZ`, so there is no 0/O or
1/I. Each symbol carries 5 bits, 80 bits in all:

| Bits | Field |
| --- | --- |
| 32 | public IPv4 address, masked |
| 16 | public UDP port, masked |
| 20 | room secret, 1 to 999,999 |
| 1 | role: host or joiner |
| 11 | checksum (FNV-1a over all fields) |

- **Masking.** The address and port are XORed with an xorshift keystream seeded
  from the secret and role. The secret, role and checksum word is XORed with a
  fixed constant. Two codes for the same address therefore share no readable
  prefix. This hides the address from a casual reader; it is not encryption.
- **Secret.** The host's secret is the session PIN for the room, carried in
  every HELLO and punch.
- **Entry.** Lowercase, dashes and spaces are accepted on entry.
- **Typos.** Validation also rejects port 0 and addresses 0.x and 224 or above.
  The host-side test measures single-symbol typos: fewer than 0.5% of them still
  decode.

The code lives in `LiveP2P::encode/decode/format` in
`src/live_race_session.cpp`.

## Punching

Punch packet, 12 bytes:

| Bytes | Field |
| --- | --- |
| 0-3 | `MSP1` |
| 4-7 | PIN |
| 8 | sender participant |
| 9 | flags (1 = "I hear you") |
| 10-11 | zero |

- **Separate magic.** The magic differs from the race header (`MSR1`), and the
  MSR wire format is unchanged. `LiveRace::update` gives each received packet
  to STUN first, then to the punch table, then to the session.
- **Peer table.** `LiveP2P::Punch` holds `MAX_PEERS - 1` remote slots. Each is
  EMPTY, PUNCHING or OPEN. A punch with the room PIN from a known address opens
  that slot.
- **Adoption.** While not connected, the host also adopts an unknown sender
  that has the right PIN. If the sender is the joiner it is already punching,
  but from another port, the host retargets that slot to the real address.
- **Timeouts.**
  - The host restarts its listener silently whenever the session's 30-second
    handshake timer expires.
  - If 30 s pass after a friend's code is entered without a connection, the tab
    says "Can't connect directly" and shows the hint.
  - A joiner whose session times out also shows "Can't connect directly". Entering a code again
    retries.

### Why a two-way swap

Hole punching works when both NATs keep one public port for every destination
(endpoint-independent mapping, STUN verdict SAME). Most home routers then filter
by address and port, so each side must first send to the other's public
address. That needs both addresses, hence both codes. A symmetric NAT changes
the port per destination, so the code shows the wrong port. Direct play then
fails unless the other side is a full-cone NAT; that case works because of the
adoption above.

The host-side NAT model in `test_live_p2p.py` gives:

| Host NAT | Joiner NAT | Two codes | Host code only |
| --- | --- | --- | --- |
| cone (port-restricted) | cone | connects | fails |
| full cone | cone | connects | connects |
| full cone | symmetric | connects | connects |
| cone | symmetric | fails | fails |
| symmetric | cone or symmetric | fails | fails |

## One-code join: findings

The host keeps listening for any HELLO with its PIN and adopts punches from
unknown senders. So when the host's NAT filters endpoint-independently (full
cone), the joiner gets in with the host's code alone, with no extra code or
setting. With any other NAT, the host must enter the joiner's code. The two-way
swap is therefore the documented default, and one-code join happens on its own
when the network allows it.

Options evaluated:

- **(a) Host sprays or polls.** Not possible without the joiner's port. Even if
  the joiner's NAT keeps port 48222, the host would still need the joiner's
  IP. Guessing ports is slow, noisy and unreliable.
- **(b) Learning the joiner's address another way.** That needs a third party
  to tell the host, which is a server.
- **(c) Endpoint-independent filtering detection.** Detecting it requires a
  STUN server that answers from a second IP/port (RFC 5780 CHANGE-REQUEST).
  The two fixed servers (Google, Cloudflare) do not support it, so the Wii
  cannot tell in advance. The listener above covers that case at no cost.
- **(d) Public rendezvous.** Out of scope: no outside services.
- **(e) UPnP / NAT-PMP from the Wii.**
  - **UPnP** needs an SSDP multicast search (UDP to 239.255.255.250:1900),
    then HTTP and SOAP over TCP to the router. MoonshineNet's ARM side offers
    UDP only, and the PPC session code rejects multicast addresses. It would
    need TCP support in the launcher kernel, a SOAP client and XML scanning:
    about 3-5 KB of PPC code plus ARM work. JP has 1.8 KB of container
    headroom left.
  - **NAT-PMP/PCP** is a 12-byte UDP request to the gateway on port 5351. It
    would cost roughly 300-500 bytes, but it needs the gateway address, which
    the current transport does not expose (it reports only the local address). Many routers disable both
    protocols, and neither can be tested from here.
  - Neither was implemented.

## Four players: what is ready and what is left

Ready now; the build uses `MAX_PEERS = 2`:

- `LIVE_P2P_MAX_PEERS` (2 to 4) sizes the punch table. The codec and punch
  code use it everywhere and assume no fixed count. Participant numbers stay
  below 4, as the MSR header requires.
- The host collects joiners: it adopts any punch with its PIN until the table
  is full. `LiveP2P::roster` forwards the other open joiners' addresses to one
  joiner. A joiner accepts a roster only from the host, once the host path is
  open, and starts punching the listed peers.
- `test_live_p2p.py` builds the same source with `MAX_PEERS = 4`. It checks
  host collection, full-room refusal, roster bytes, stranger and torn roster
  rejection, and the joiners' new punch slots.

Remaining work:

- **Session.** `LiveRaceSession` is single-peer. It needs one session state per
  participant, or a host-star session, with participant numbers assigned by
  the host instead of the fixed 0 (host) / 1 (guest).
- **LiveRace.** Wire `LiveP2P::roster` into `LiveRace::update`: send it on
  each new OPEN joiner, and resend it until acknowledged.
- **Race logic.** Ready, results, score, draft and match rules are written for
  two players.
- **Display.** Ghost rendering, names and input display exist for one
  opponent.
- **Online tab.** Rows for several friend codes and per-peer status.
- **Memory.** MEM1 and container budget for the larger state; JP is tight.

## Known limits

- **Same network.** Two players behind the same router see the same public
  address. Without hairpin NAT support in the router they cannot reach each
  other. This includes two Dolphins on one PC.
- **Dolphin.** The companion admits only senders it has already sent to, like
  a port-restricted NAT. Use two codes there. Dolphin results do not show Wii
  network behaviour.
- **Unsupported networks.** IPv4 only. A carrier-grade NAT or a symmetric NAT
  usually cannot be punched.
- **Security.** The PIN is a room password, not encryption.

## Sizes (pinned link, 96/5/9/34 protection holds in every receipt)

| Build | JP | US | PAL |
| --- | --- | --- | --- |
| Console container before (`ad752b0`) | 547,552 | 544,000 | 543,456 |
| Console container after | 547,072 | 543,232 | 542,720 |
| Console MEM1 bytes free before | 6,843 | 20,630 | 20,737 |
| Console MEM1 bytes free after | 7,308 | 21,092 | 21,199 |
| Emulator container before | 527,616 | 524,224 | 524,160 |
| Emulator container after | 527,872 | 523,328 | 522,944 |

The JP ceiling is 548,864, so 1,792 bytes remain. Removing the relay client
and the numeric IP/port/room editor paid for the codec, punching, roster and
new text. The new `LiveStun` functions are in the console cold set; LiveP2P
and LiveRace stay in MEM1.

## Tests

- **`test_live_p2p.py`.** Code round trips, the alphabet, masking, refusals
  and typo detection. Also the punch timing, packet bytes, PIN checks,
  adoption and peer-reflexive retargeting, the NAT matrix above, and the
  four-player roster.
- **`test_live_race_lifecycle.py`.** The production `LiveRace` flow with
  stubbed transport, STUN and session: the host code and listener, joiner
  punching and PIN, code checks, failure hints, host restart, the 30 s limit
  and one-code adoption. Also the existing transport lifecycle cases.
- **`test_live_stun.py`.** Shared mode: no transport begin/stop, packets handed
  in by the owner, cancel, and the 15 s limit.
- **`test_dolphin_live_transport.py`.** The real punch and session code through
  two Dolphin companions on loopback. With swapped codes both connect. With
  only the host's code, the host companion drops the joiner.
