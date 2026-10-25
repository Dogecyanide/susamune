# Dolphin companion and ghost memory

`tools/dolphin_online/bridge.py` carries the existing region-independent UDP
protocol between an emulator build and the same relay used by Wii clients.
It discovers a supported running Windows Dolphin process and a checked game
identity at `0x71901000`. The 2,784-byte mailbox ends at `0x71901AE0`, after
the existing settings/hoverless windows and before the extra state pool.
Its C header asserts the bounds and cache-line ownership.

PPC writes the game identity, command, producer/consumer indices, TX slots
and replaceable latest pose. The companion writes its identity, status,
RX slots and diagnostics. Each publication withdraws its generation before
copying, then commits the new non-wrapping generation. Readers reject torn
copies. Both sides reject old epochs and queue counts outside four slots;
the companion verifies the immutable game identity before every write.
The companion accepts incoming UDP only from endpoints it has sent to.
Relay credentials, room generations and peer session checks remain in the
existing native clients. There is no input injection or frame lockstep.

Game and companion heartbeats advance every 100 ms. Three seconds without
progress retires the connection. The game instance binds an attachment to
one boot, and a fresh companion chooses a new nonzero epoch. Publication or
heartbeat rollback retires a detected Dolphin rewind. Startup and restart
do not reuse queued packets. A Windows named mutex excludes a second
companion for one process. Emulator sockets use an ephemeral local port,
allowing a relay or another Dolphin to run on the same PC.

## Graphics storage

Dolphin's CPU fake-VMEM cannot back ghost display lists, vertices or textures:
`MemoryManager::GetSpanForAddress` resolves device accesses only into real
MEM1/EXRAM. The emulator build therefore puts its existing two 90,112-byte
body heaps at `0x81800000` and `0x81816000`; both end at `0x8182C000` inside
the bounded `0x81800000..0x81850000` window. Wii addresses and heap sizes,
the existing MEM1 attachment heap, recording bounds and state pools do not
change.

The user enables 32 MiB physical MEM1 in Dolphin. The disc still requests
24 MiB simulated memory. Retail `Config24MB` narrows DBAT2 to an 8 MiB map
at `0x81000000`, so physical storage alone is insufficient. Before creating
the ghost heaps the emulator checks physical size, simulated size, root
heap end and DBAT2's exact retail mapping, then widens that data map to
16 MiB. The original mapped prefix is unchanged. It does not change an
instruction BAT, the game's arena or simulated-memory word. Unexpected
configurations fail closed before creating these heaps.

Sources:

- [Dolphin memory initialization and device pointer resolution](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/Memmap.cpp)
- [Dolphin physical memory settings](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/Config/MainSettings.cpp)
- `build/reference-sms/libs/dolphin/src/os/OSMemory.c`, `Config24MB`.

## Focused validation

`scripts/test_dolphin_live_transport.py` checks ownership/bounds, torn and
exhausted publications, old epochs, invalid counters, heartbeat retirement,
game identity replacement, latest-pose replacement, foreign UDP senders and
oversized packets. Its loopback test runs the actual C++ JP/PAL relay/session
clients through two companion mailboxes and real UDP sockets, including
two-way poses, departure and stale-session rejection.

`build/timewarp-pr13-memory-probe/receipt.json` records an actual Dolphin
2606a PPC memory probe using an isolated profile and historical PAL fixture.
Physical memory was 32 MiB while simulated memory stayed 24 MiB and the root
heap/arena ended at `0x817FEBE0`. An actual PPC `memset` reached the extra
MEM1 after the checked DBAT2 change. This is CPU/address evidence; it alone
does not establish a rendered ghost or Wii/Dolphin gameplay result.

`build/timewarp-pr13-runtime/run3/transport-verification.json` records the current PAL build
executing its real PPC transport through a local UDP socket: control send and
receive, latest-pose publication, stop/reopen, and companion restart all pass.
The running production bootstrap matches the exporter byte for byte, and the
complete cold payload matches after its early copy. Diagnostic input and
callbox code occupy a separate private section. This is PAL transport/boot
evidence, not a real Wii peer or a standalone Dolphin library-import test.

The same run's `ghost-render-verification.json` binds a fresh session recording,
ordinary same-route promotion, six successful model submissions and the inspected
`session-ghost-4.png`. The image shows a translucent Mario body partly overlapping
the live player in Plaza episode 2. Both ghost heaps use the bounded extra MEM1
window. Choose Mario appearance on standalone Dolphin; the launcher-provided
Shadow/Piantissimo asset bundles are unavailable there. This check does not
cover saved-file Watch, two bodies or a real Wii peer.
