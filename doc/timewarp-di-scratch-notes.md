# DI scratch reduction and one-way runtime handoff

Keep 512 KiB through the first executable load, then retain 64 KiB for the
remainder of that kernel session. The production reader/fence implementation
and host replay support this policy without extra first-boot reads. The
candidate tail is 458,752 bytes. Capability publication and pool integration
remain separate work; this change alone does not increase state capacity.

| Scratch size | Permanently released tail | Potential released PPC range |
| --- | ---: | --- |
| 512 KiB | 0 | — |
| 128 KiB | 393,216 B (384 KiB) | `0x91720000..0x91780000` |
| 64 KiB | 458,752 B (448 KiB) | `0x91710000..0x91780000` |

The full 512 KiB physical reservation remains unchanged. This pass adds the
64 KiB retained-prefix constant, the kernel's one-way getter/fence and reader
calls to that getter. No address, state capacity, timer, cave or timer scratch
was changed. Host I/O counts do not establish Wii throughput.

## Implemented fence and caller contract

`DI.c:75` initializes the private limit to the existing 512 KiB reservation.
`GetDIBufferLimit()` exposes it; ISO and FST sample it once per read
(`ISO.c:510`, `FST.c:174`). The only runtime assignment is the 64 KiB value
inside `DIHandleScratchReservation` (`DI.c:83`). Neither `DIinit(false)` nor
ISO cache reinitialization widens it. A fresh kernel image initializes the
large value again.

`DIReserveScratchTail()` (`DI.c:99`) is for the kernel main thread. It rejects
a missing DI handle and calls from the DI thread, then:

1. Returns immediately if already narrowed.
2. Waits through `DIFinishAsync()` for the tracked asynchronous read.
3. Services a pending `DI_IRQ` once. If `ReadSpeed_End()` still defers its
   guest completion, the API returns false and leaves the interrupt pending.
4. Sends synchronous internal ioctl `0x53555344`. The single DI consumer
   handles it before the ordinary-read branch (`DI.c:919`), changes the limit,
   then acknowledges. It rejects nonempty request buffers/lengths.
5. Returns true only after successful acknowledgement and observing 64 KiB.

The limit is changed by the read thread, so a previously dispatched wide
read cannot still write its tail after acknowledgement. Ordinary reads
queued after the fence choose their chunk length through the getter when
executed; an empty queue is not required. Async acknowledgement messages use
no scratch. USB keepalive is a serial one-sector request; streaming reads
use the same synchronous wrapper (`Stream.c:166`, `:197`, `:202`). DSP patch
scratch use is less than 8 KiB and does not enter the candidate tail.

False grants no ownership. Do not widen on failure or assume an interrupted
IPC operation left the old limit unchanged. There is no new timeout:
`DIFinishAsync` and synchronous `IOS_Ioctl` inherit potentially blocking
existing I/O semantics. The self-thread check prevents the straightforward
queue deadlock. Actual IOS scheduling and hardware completion remain Wii
validation work.

## First publication and reset ordering

The first publication point is inside `PatchGame`, after successful validated
matching-mod installation and `ISOSetupCache`, before writing the game entry
to `RESET_STATUS`. At the audited source revision these are `Patch.c:4415`,
`:4423`, and `:4455`; use the function anchors as integration changes lines.
`FakeEntryLoad.S:10` parks the PPC at `0x4DEA` until that final write. The
existing main loop reaches `PatchGame` for `0x4DEA` (`main.c:847`). Drain any
outstanding DI read before main-thread patching as well; the reservation API
protects the later handoff, not earlier concurrent scratch use.

The caller must require the exact supported Sunshine revision, a successfully
installed mod that advertises the new layout/protocol, and a true reservation
result. A game ID or transport V4 alone is not a declaration that the mod
understands the extra state bank. Current V4 reserved words are required to
be zero; adding a layout feature needs coordinated format validation. Keep
the new capability absent for older/mismatched pairs and failed injection.

A strictly first-boot publication may update `SusamuneCfg.flags` before the
PPC starts: that cache line is kernel-owned at boot, then PPC-owned on save
(`susamune_cfg.h:1285`, `settings.cpp:350`). A later kernel update to that
line is unsafe without an ownership protocol. An independent ARM-owned
capability line would support later publication; `pad1[24]` is on the
existing ARM-only line, although any reuse needs layout checks. The current
PPC pool/storage clients latch their layout (`state_pool_runtime.hxx:7`,
`state_storage.cpp:86`, `savestate.cpp:988`), so simply clearing a flag cannot
revoke memory already in use.

Retail title reset keeps the 64 KiB phase. `onUpdate` explicitly distinguishes
`APP_STATE_DONE`/file select from level reloads (`main.cpp:312`), and the
manager is initialized once (`main.cpp:294`). Kernel fake-reset handling
raises the ordinary reset IRQ (`kernel/main.c:818`); it does not restart DI.

Actual same-kernel DOL reinjection also keeps 64 KiB. The apploader/DOL
detectors are in `DoPatches`, after the reads (`Patch.c:1166`, `:1316`), so
they cannot safely restore a wide buffer before those reads. This monotonic
policy deliberately accepts extra reads on that rarer path. No old state
needs retirement merely to keep the scratch tail protected.

Storage-client retirement still matters when the new mod reuses old state
metadata or payloads. State storage can retain an open import/export worker
between main-loop iterations; `PoolPiece` accesses the pool in `PAYLOAD_IO`
(`SusamuneStateStorage.c:39`, `:425`). Its `Finish` closes handles and retires
the phase (`:170`); blindly re-running its initializer would lose those open
handles. The reinjected PPC submits an asynchronous CANCEL during
`StateStorage::init` (`state_storage.cpp:99`), after DOL loading. Preserve or
strengthen that ownership barrier when adding a bank. It is not a reason to
widen the DI buffer, and is not proven by these reader tests.

## Phased trace result

The 17-request PAL executable trace runs at 512 KiB, then the 8,978-request
PAL lifecycle trace runs at 64 KiB without resetting reader statistics or
data. Every byte of the 458,752-byte tail is filled with a checked pattern
before runtime reads. Cache-enabled ISO traffic is exactly the same as the
512/512 control:

| Phase | Backend calls | FAT device calls | Compared with 512/512 |
| --- | ---: | ---: | --- |
| Initial executable load, cache not yet enabled | 23 | 97 | Identical |
| Gameplay, unchanged 3 MiB cache | 1,819 | 3,579 | Identical |
| Combined | 1,842 | 3,676 | Identical |

The candidate tail remains byte-identical after all four runtime modes,
after >3 MiB and rounding boundary requests, and after sparse CISO crossings.
The real-disc path retains its separate buffer and identical traffic.
Cache-disabled gameplay still costs 62 extra FAT calls (17,998 to 18,060);
synthetic FST costs 121 extra calls (20,721 to 20,842). Those costs are not
hidden by the first-boot policy.

Reopening the ISO cache and replaying the executable trace in the same
kernel session retains 64 KiB and preserves the entire owned tail. That
uncached reload uses 82 backend calls / 156 FAT calls versus the initial
23 / 97. Repeated reservation performs no second ioctl and never widens.

The production fence test schedules a 131,105-byte read before the fence and
another after it. They use one 512 KiB chunk and three 64 KiB chunks,
respectively. The acknowledgement observer sees the small limit before
ownership begins. Both complete their full destination before one patch,
sync and acknowledgement. A negative control emulates an already-dispatched
wide write after ownership and correctly detects tail corruption.

This executes actual getter, reservation API/handler, wait loop and readers.
Syscalls, thread scheduling, storage, IRQ timing and patch callbacks are
controlled host doubles. The game/layout capability checks in the phase
experiment remain a proposed caller model until production integration.

## Actual source constraints

- `include/susamune/mem2_map.h:27` defines the allocation; `DI.c:74` exposes
  its pointer. `ISO.c:510` caps uncached/oversized ISO reads and
  `FST.c:174` caps every FST path to the runtime getter.
- The FST cached-file path rounds its read length up to 32 bytes
  (`FST.c:202`). Both candidate capacities are multiples of 32; even lengths
  65,505 through 65,536 round within the 64 KiB allocation.
- `DI.c:894` loops returned pieces into the final destination; only after
  the complete request does it call `DoPatches`, `ReadSpeed_Setup`, sync and
  acknowledgement (`DI.c:916`). Patch matches spanning scratch boundaries
  therefore retain their complete original destination.
- `Patch.c:2322` uses the scratch for DSP hashes. The largest of the 16
  `DspMatches` lengths is `0x1F20` = 7,968 bytes; Sunshine's listed length is
  `0x1CE0`. Both fit every candidate. The synchronous USB keepalive consumes
  one sector (`DI.c:885`); FatFS permits at most 4,096-byte sectors.
- `ReadRealDisc` uses a separate 3 MiB allocation, with its own front,
  drive and tail buffers (`RealDI.c:42`, `:184`). Its transfer cap and DVD-R
  2,048-byte rounding do not depend on DI scratch. ISO's 3 MiB cache is also
  separate. Neither allocation is reclaimed by this proposal.

## Trace results and the non-free startup cost

The retained PAL lifecycle trace contains 8,978 reads totaling 98,729,984
requested bytes. Only 62 exceed 64 KiB; none exceeds 128 KiB. The PAL boot
trace contains 17 reads totaling 4,471,872 requested bytes, including the
large main executable. Trace paths and SHA-256 hashes are in the receipt.

The actual production FatFS reader was executed against a synthetic FAT
file with contiguous and fragmented extent maps, using the read requests
emitted by the production ISO reader. The resulting device-read counts are:

| Workload | 512 KiB | 128 KiB | 64 KiB |
| --- | ---: | ---: | ---: |
| PAL lifecycle, ISO cache enabled | 3,579 | 3,579 | 3,579 |
| PAL lifecycle, cache disabled | 17,998 | 17,998 | 18,060 |
| PAL boot, cache enabled | 87 | 90 | 93 |
| PAL boot, cache disabled | 97 | 122 | 156 |

The read-only link-map path already limits each device transfer to 64 KiB
(`fatfs/ff.c:1366`, `:3702`). Nevertheless, splitting a larger *unaligned*
file read creates additional sector-edge work. Cache-disabled PAL boot
logical backend calls increase from **23 to 48 to 82**, and device calls
increase **25.8% at 128 KiB** or **60.8% at 64 KiB**. Requested file bytes
stay constant; these percentages are operation counts, not elapsed-time
regressions.

This boot case is relevant: `PatchGame` calls `ISOSetupCache` only after
loading and patching the executable (`Patch.c:4370`, `:4403`). Gameplay with
the unchanged cache showed identical reader traffic across all three sizes.
Physical-disc replay also remained identical: 8,968 drive reads for the
lifecycle trace and 14 for the boot trace, regardless of scratch size.

FST's cached-file cap/rounding was exercised too. Its trace replay uses one
synthetic file address space and ordinary cluster-sized FatFS reads; it
does not model the real extracted-file boundaries, lookup/open cost, or
device-specific placement. Its synthetic boot device calls were
174 / 224 / 292. Treat this as another splitting counterexample, not a
prediction for a real extracted game.

## Verification and limits

`scripts/timewarp_di_scratch.py` compiles extracted production `ISORead`,
`ISOReadDirect` (including CISO), `ISOSetupCache`, `ReadRealDisc`, and the DI
copy/patch loop. Controlled backends generate deterministic bytes and track
reads. The FST fixture executes its actual common cap and cached-file
rounded-read expression. Hardware registers, storage and `DoPatches` are
test doubles; the patch observer verifies the complete original destination
before modifying its first/last bytes, then checks sync/ack order.

All 24 trace variants and 1,356 synthetic boundary requests passed exact
output and canaries. Cases cover zero/small requests, 32-byte rounding,
64/128/512 KiB edges, cache prefix/wrap, >3 MiB reads, sparse CISO crossings
around 2 MiB, and DVD-R sector rounding. Ordinary disc mode is tested only
at representable four-byte-aligned disc offsets. The low physical-MEM1
`0x31A0` backup branch cannot run at its real destination in the host;
its maximum scratch index `0x31A0 + 4` remains below 64 KiB.

Twelve explicit short/error-read cases expose an **existing limitation at
all three sizes**: the DI caller can still patch and acknowledge incomplete
backend data. Canaries remain intact. This is not evidence that failure
propagation is safe, and the experiment does not silently treat short reads
as correct output.

The focused suites passed: 5 DI fence/tail tests, 9 FatFS tests, 17 ISO cache
tests, and 3 CISO mapping tests. The actual big-endian ARM GCC compiled the
three changed DI/ISO/FST modules without warnings. The receipt's source
hashes mean unchanged **during the measurement**, not absence of this
authorized production change. Timer code was not edited. Real Wii SD/USB
timings, cache coherency and DMA hardware remain untested. Sector-aligned
chunk boundaries have not been implemented or credited.

Private evidence: `build/timewarp-di-scratch/receipt.json`, generated native
fixture and `run.log`. Reproduce with the repository Python environment and
`scripts/timewarp_di_scratch.py`; all output stays in this task's build tree.
