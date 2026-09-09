# Regional live statistics cache

The V9 split schema contains 132 routes and 495 segments. Its complete
three-region payload is 42,372 bytes. Gameplay and the statistics menu only use
the running build's region, so the live mod now retains one 14,124-byte region.
The full runtime object drops from 42,472 to 14,224 bytes: **28,248 bytes less
MEM1 BSS**. This creates room inside the existing injected image; it does not
change the game's heap reservation or add any MEM2 reservation.

The shared mailbox and on-disk journal still contain all three regions. At
initialization, the mod validates the full mailbox and copies the current
region's route counts, played time, best segments, PB identities and PB segments
into its local cache. When publishing, it updates only those same region fields
in the full mailbox. Other regions remain byte-for-byte intact.

This relies on an audited ownership rule: after boot/migration initialization,
the ARM statistics writer accepts a const mailbox, validates it, copies its
complete payload into private file scratch, and writes only its separate
acknowledgment/status cache line. The PPC does not publish another request while
one is pending, including after a timeout. Changes made while waiting stay in
the local region cache and are published after the matching acknowledgment.
Failed writes retain the same retry behavior. Cache-line stores still cover the
complete request before its sequence is published.

The one-region cache also supplies defaults when no compatible backend exists;
it does not dereference the absent mailbox in standalone Dolphin/session mode.
Read-only backends can initialize the local cache but never receive writes.
No shared schema, configuration offset, journal field or region index changed.

`scripts/test_split_region_cache.py` compiles the actual initialization,
publication and polling functions separately for JP, US and PAL region indices.
It checks complete region copies, untouched other regions, all three runtime
sizes, immutable pending/timed-out payloads, retries, and missing/read-only
backends. The associated ghost comparison and V9 journal tests remain green.
