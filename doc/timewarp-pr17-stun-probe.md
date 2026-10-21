# STUN probe (online builds only)

The probe learns this console's public UDP address and checks whether the NAT
keeps one public port for every destination. Online play runs it on the race
socket to make the room code (see `timewarp-pr17-p2p-online.md`). It exists
only when `TIMEWARP_LIVE_RACING` is on.

## What it does

On the Online tab, X (or A on the NAT test row) starts the probe while no
session is active. It opens the existing transport (`LiveTransport::begin`).
On a console, that is the MoonshineNet IOS UDP socket in the launcher kernel.
It binds the race's own local port (`LiveRace::LOCAL_PORT`, 48222); Dolphin
uses port 0 through its companion.

Create room and Join room run the same probe in shared mode
(`LiveStun::startShared`). There it neither opens nor stops the transport.
`LiveRace` hands every received packet to `LiveStun::accept` first, and
`LiveStun::cancel` ends a run on disconnect. Shared runs also stop after 15 s. One socket sends a bare RFC 5389 Binding Request
(20 bytes, no attributes) to each server:

| Server | Resolved IPv4 (2026-10-21, from NL) | Port |
| --- | --- | --- |
| stun.l.google.com | 74.125.250.129 | 19302 |
| stun.cloudflare.com | 162.159.207.0 | 3478 |

The IOS socket path has no DNS, so these addresses are fixed in
`src/live_transport.cpp`. If one stops answering, the probe reports one reply.

Each server gets its own transaction ID. A reply counts only if it comes from
that server's IP and port and is a Binding Success Response (0x0101). It must
carry the magic cookie, that transaction ID, consistent lengths and an IPv4
XOR-MAPPED-ADDRESS with a nonzero port. Requests are repeated every 500 ms,
only to servers that have not answered, up to six times. The probe then
stops the transport, which also happens after 15 s or on any transport
failure.

## Reading the result

The NAT test row shows the verdict. With Diagnostics on and no session
active, the last diagnostics line shows:

`STUN <verdict>  A <public ip:port from Google>  B <public ip:port from Cloudflare>`

- `SAME - punching should work`: both servers saw the same public IP and
  port. The NAT mapping is endpoint-independent, the case UDP hole punching
  needs.
- `DIFFERENT - symmetric NAT`: the public port changed with the destination.
  Direct punching is unlikely from this network.
- `one reply` / `no reply`: incomplete; retry with X. If it repeats, the
  firewall may block one server's port.
- `failed, code N`: the transport could not open; N is its error code.

The probe needs no room and no 60 Hz mode; racing itself still requires 60 Hz.
The P2P redesign added the NAT test row to the Online tab's row table.

## Cost (console pinned link, `jp/us/pal`)

| | JP | US | PAL |
| --- | --- | --- | --- |
| Recovered MEM1 remaining before | 742 | 14,926 | 15,033 |
| after | 483 | 14,674 | 14,781 |
| Container bytes before | 558,176 | 554,400 | 554,112 |
| after | 560,640 | 556,608 | 556,512 |

The codec and driver functions (1,832 bytes of code) are listed in the
console cold set for `live_transport.cpp`. The remaining MEM1 cost is their
44 bytes of state, the 16-byte server table, new Online-tab text and the call
from `LiveRace::update`. The JP container already exceeded its reset-safe
ceiling before this probe; see the PR17 handoff notes.

## Tests

`scripts/test_live_stun.py` compiles the real codec and driver blocks for the
host. It checks the request bytes, parsing with preceding padded attributes,
rejection of malformed or foreign replies, the retry schedule, both verdicts,
transport failure and shared mode (no transport ownership, packets handed in,
cancel, time limit). With `MOONSHINE_STUN_LIVE=1`, it also queries both
real servers through the same codec.

Dolphin does not exercise the Wii kernel socket path. Its build reaches the
network through the companion process on the host PC, so only a real Wii
test measures the Wii's own NAT path.
