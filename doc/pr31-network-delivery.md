# PR31 network ownership and timelines

`MoonshineNet.c` uses one socket with two independent asynchronous request
lanes after initialization: RX and TX. Initialization and close use the TX
lane. Each lane owns its message, vectors and buffers until its own completion
arrives. Timer/wake messages do not release either lane. Stop, failure and
shutdown wait for both lanes before closing the socket or releasing resources.
RX reserves space in the bounded receive queue before submitting; a full queue
waits for the bridge consumer. No memory reservation or mailbox ABI changed.

The former single request lane serialized receiving behind sending and vice
versa. Four players require roughly 90 incoming poses and 60 outgoing group
bundles per second at NTSC rates. The regression harness delays each IOS
completion by 10 ms and verifies simultaneous traffic stays bounded. This
models request latency; it is not an IOS58 performance measurement.

The host owns each relayed player's sequence and scene epoch. A newly accepted
guest session clears its pose-valid bit; its next pose advances the relay
epoch even if the guest is in the same area. Raw guest sequence resets and
reboots therefore cannot make other guests reject the new timeline as old.
The original guest scene epoch is tracked separately to retain normal area
transition behavior. A reconnecting local guest also clears its interpolators.
Initial roster synchronization precedes bundles, but later reliable control
acknowledgements do not gate animation delivery.

Ping probes carry their individual send timestamp in both sequence and payload.
Replies must echo it, be newer than the last accepted reply, not be from the
future, and be inside the session timeout. A later probe does not invalidate a
still useful earlier reply. This avoids counting lost-probe retries as RTT.
Reliable control retries back off after sustained loss instead of reverting
to four copies per second when the measured ping exceeds one second.

The PR30 live capture reproduced long silences, delayed acknowledgements and
reconnects on a local Wii/Dolphin link. Reducing only Dolphin's pose traffic
after reconnects had begun did not isolate the cause. Local ICMP was also
uneven. These observations do not establish whether all remaining delay comes
from the worker, IOS scheduling, Wi-Fi loss, or a combination.
