# Live transport lifecycle

`TIMEWARP_LIVE_RACING` defaults to OFF in both root and standalone launcher
CMake configurations. The root forwards it to the launcher, which forwards it
to its ARM group. Only enabled kernels compile `MoonshineNet` and its bridge.

The bridge initializes after `SusamuneCfgInit`, before PPC release. Its boot
descriptor occupies the existing ARM-owned 24-byte padding at config offset
`0x28`; the config remains 5,152 bytes. The 2,720-byte mailbox is an aligned
kernel BSS object, with its actual PPC address advertised at boot. It does not
consume the state pool, transfer directory or a new fixed MEM2 reservation.

ARM main services the bridge before its disc/FAT dispatch chain. Each call
handles at most one control send, one latest-pose update and one received
packet; only the worker calls network IOS. PPC reads are bounded and reject
uncommitted or changing publications. Directional indices have the same cache
line owner as their writer. The local IP/port has a separate ARM-owned line
and is accepted only for the current session epoch.

`PatchGame` calls bridge retirement before reinjection. Retirement advances the
epoch once, withdraws the local address and requests worker stop. The game may
resume offline while IOS drains; the bridge cannot start a new session until
the worker reports retirement. Repeated patch attempts do not advance the
epoch again. Kernel BSS is not cleared by this path.

Final exit requests retirement and terminal worker shutdown before device
teardown. Shutdown attempts are nonblocking. The existing 100 ms IOS-reload
wait retries shutdown, yielding CPU to the worker; there is no new exit wait.
An outstanding IOS request retains its worker, queue, stack and static request
buffers. Failure to close or cancel does not release that ownership.

DI, SD and HID close their own handles; FAT/BT cleanup does not own the network
module's static buffers. USB storage is different: `USBStorage_Shutdown` calls
`USB_Deinitialize`, which sends `USBV5_IOCTL_SHUTDOWN` to `/dev/usb/ven`. Its
interaction with a USB network adapter has not been established. Therefore USB
storage teardown runs only after successful network shutdown. Otherwise its
resources also remain resident until IOS reload. There is no late USB close
after the PPC has been told to reload IOS.

The focused mailbox test uses the actual ARM bridge with an in-memory worker.
It covers cache ownership, torn poses, sequence recovery, ring bounds/wrap,
stale epochs, reset draining and local-address invalidation. Object compilation
checks the PPC and ARM ABIs. Neither establishes real network connectivity or
console reset behavior; those remain private-prototype validation steps.

## ARM IOS replies and startup errors

The network worker and IOS resource managers share the ARM CPU. Completion
messages and output buffers are read directly after their queued reply; unlike
the PPC mailbox, they must not be invalidated after IOS writes them. An
invalidate without a clean can discard the new cached result. Nintendont's
Bluetooth callbacks use the same direct-read pattern. Primary references are
[ResourceReply](https://github.com/DacoTaco/StarStruck/blob/0ade5c370fdbeb132728780c42bd55ec35004edf/kernel/source/messaging/ipc.c#L395)
and the [cache syscall mapping](https://github.com/DacoTaco/StarStruck/blob/0ade5c370fdbeb132728780c42bd55ec35004edf/kernel/source/interrupt/syscall.cpp).
The worker fixture models discarded dirty replies so a no-op cache stub cannot
hide this defect. This models the failure mechanism; Wii connectivity still
requires a hardware test.

Fatal IOS errors from -1 through -999 appear in the existing error field as
`-(200000 + step * 1000 + abs(raw_error))`. Steps 1/2/3/4 mean timer creation,
KD open, IP-top open and KD's returned status. Steps `16 + op` mean submission
failure and `32 + op` mean completion failure. Operations 1..12 are KD, startup,
host ID, socket, nonblock, receive buffer, send buffer, bind, local name, send,
receive and close. For example, -217008 means KD submission returned -8;
-237008 means nonblock completion returned -8. Internal -10001 timeout and
-10002 malformed reply remain distinct. Cleanup preserves the first fatal
error. No shared layout or PPC code changes are needed for these diagnostics.

The Prototype 2 Wii test reached socket creation and returned -236068:
completion of operation 4 returned `SO_EPROTONOSUPPORT` (-68). Socket creation
must use `(AF_INET=2, SOCK_DGRAM=2, protocol=0)`; IOS rejects the conventional
explicit UDP protocol value 17. This matches
[Slippi's UDP broadcaster](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/SlippiNetworkBroadcast.c#L79)
and [Dolphin's Wii socket implementation](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/IOS/Network/Socket.cpp#L890).
The worker fixture rejects a nonzero protocol even when the caller supplies a
successful socket completion. The failure/retry case also verifies that a
rejected socket does not acquire a descriptor or prevent a new session.

## Prototype 5 packet diagnostics

The local-address publication's existing three reserved words carry diagnostics
without changing its 32-byte size or ABI. Word 0 contains saturated 16-bit
successful socket-send and receive counts (high/low halves). Word 1 contains
version 1 in its top byte, then saturated 8-bit drop, send-error and receive-error
counts. Word 2 carries the signed raw socket error. ARM republishes only when
the packed values change or the socket first becomes ready. The PPC accepts
only the current epoch and diagnostic version, retaining its last valid copy
after retirement withdraws the live publication. A new attempt clears it.

The Online menu also counts successful PPC packet submissions, mailbox receives
and relay-accepted packets. These distinguish an unsent request, socket failure,
discarded network reply and relay validation failure. The companion server's
optional anonymous five-second counters establish whether requests reached the
PC and whether it sent a challenge or welcome. Prototype 4's -1002 alone cannot
distinguish these cases; no datagram arguments were changed without evidence.

## Prototype 6 send compatibility test

Prototype 5 on Wii reported PPC TX 30, socket TX/RX 0/0, send/receive errors
30/0 and raw socket error -63 before relay timeout -1002. In the Wii socket
error enumeration, -63 is `SO_EOPNOTSUPP`. All attempted sends were rejected
locally; this result does not test the public tunnel's delivery from Wii.

Prototype 6 removes the per-message flag 4 from sends, using flags 0 as in
[Slippi's Wii UDP broadcaster](https://github.com/project-slippi/Nintendont/blob/bea169ecd170f9b49b73c49e831189afd0dc8c9b/kernel/SlippiNetworkBroadcast.c#L101).
The socket is already nonblocking through `F_SETFL(4)`; receive flags and IOS
request framing remain unchanged. The focused worker case verifies those
settings and queue progress after a would-block send. This is a narrow
compatibility test, not proof that IOS58 rejects flag 4 on every UDP socket.
At packaging, real Wii room creation was unconfirmed.

The next Prototype 6 Wii test succeeded: the tester reported a generated room
code, and the PC relay recorded OPEN/PROVE/WELCOME at 13:52 on 2026-10-13
(Europe/Amsterdam), followed by regular keepalive traffic and one active room.
That verifies Wii room creation and bidirectional relay traffic with send
flags 0. It does not yet verify a second Wii joining or live ghost racing.

The menu's local IP becomes 0.0.0.0 after disconnect because the live address
publication is withdrawn. It is not evidence of failed DHCP; the worker
requires a valid host address before publishing READY.
