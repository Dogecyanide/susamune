# Phase-0 STUN probe (online builds only)

This is a measurement for peer-to-peer hole punching. It does not change the
relay race path. It exists only when `TIMEWARP_LIVE_RACING` is on.

## What it does

On the Online tab, X starts the probe while no session is active. It opens
the existing transport (`LiveTransport::begin`). On a console, that is the
MoonshineNet IOS UDP socket in the launcher kernel. It binds the race's own
local port (the Server port setting, 48222 by default); Dolphin uses port 0
through its companion. One socket sends a bare RFC 5389 Binding Request
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

Diagnostics opens automatically. The last diagnostics line becomes:

`STUN <verdict>  A <public ip:port from Google>  B <public ip:port from Cloudflare>`

- `SAME - punching should work`: both servers saw the same public IP and
  port. The NAT mapping is endpoint-independent, the case UDP hole punching
  needs.
- `DIFFERENT - symmetric NAT`: the public port changed with the destination.
  Direct punching is unlikely from this network; the relay stays necessary.
- `one reply` / `no reply`: incomplete; retry with X. If it repeats, the
  firewall may block one server's port.
- `failed`: the transport could not open (the network-error line shows the
  code).

The first line still shows the Wii's local IP and port.

## Cost (console pinned link, `jp/us/pal`)

| | JP | US | PAL |
| --- | --- | --- | --- |
| Recovered MEM1 remaining before | 742 | 14,926 | 15,033 |
| after | 491 | 14,682 | 14,789 |
| Container bytes before | 558,176 | 554,400 | 554,112 |
| after | 560,576 | 556,576 | 556,448 |

The codec and driver functions (1,832 bytes of code) are listed in the
console cold set for `live_transport.cpp`. The remaining MEM1 cost is their
44 bytes of state, the 16-byte server table, new Online-tab text and the call
from `LiveRace::update`. The JP container already exceeded its reset-safe
ceiling before this probe; see the PR17 handoff notes.

## Tests

`scripts/test_live_stun.py` compiles the real codec and driver blocks for the
host. It checks the request bytes, parsing with preceding padded attributes,
rejection of malformed or foreign replies, the retry schedule, both verdicts
and transport failure. With `MOONSHINE_STUN_LIVE=1`, it also queries both
real servers through the same codec.

Dolphin does not exercise the Wii kernel socket path. Its build reaches the
network through the companion process on the host PC, so only a real Wii
test measures the Wii's own NAT path.
