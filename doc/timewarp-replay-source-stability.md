# Stable source memory for bounded savestate replay

The proposed Wii replay gate needs both DMA quiescence and a coherent PPC
cache view. `GXDrawDone`, terminated setup, DVD END and disabled interrupts
alone are insufficient: THP locked-cache DMA can still write textures, and
clean cache lines from earlier saves can contain older GPU or DVD output.

This source audit covers the current custom Nintendont and the three supported
revision-0 retail DOLs in `build/timewarp-sd-retail/{jp,us,pal}-0/main.dol`.
It does not establish hardware execution or timing.

## Admission and cache preparation

Keep the CODEC lease and interrupts disabled continuously from admission
through planning, replay and commit. After the existing `GXDrawDone`, require
`OSIsThreadTerminated(&gSetupThread)`, `DVDGetDriveStatus() == DVD_STATE_END`
and an empty locked-cache DMA queue. Finish constructing the source spans and
their sidecars before cache preparation; do not mutate those source bytes
between passes.

The nonblocking locked-cache check is `(HID2 & 0x0F000000u) == 0`, reading
SPR 920. All three retail `LCQueueWait` functions use the identical sequence
`mfspr r4,920; rlwinm r4,r4,8,28,31` to read this queue length. Their addresses
are JP `0x8008E2CC`, US `0x803439AC`, PAL `0x8033BB2C`.
`LCQueueLength` itself is stripped. No wait is required for admission.

For every nonempty checked source span, align its start down and exclusive
end up to 32 bytes, then call `DCFlushRange` on that aligned interval before
the first pass. This is writeback plus invalidation, **not** `DCInvalidateRange`:
dirty CPU data, including THP decoder work, must survive. Aligned calls also
avoid a retail footgun: an unaligned `DCFlushRange` argument adds a whole
32 bytes before rounding and can touch an unnecessary extra line.

Retail `DCFlushRange` is byte-identical across these DOLs: a `dcbf` loop
followed by `sc`. The installed `SystemCallVector` is also identical: save
HID0, set its `0x8` bit, `isync`, `sync`, restore HID0, `rfi`. It neither
enables interrupts nor calls the scheduler; `rfi` restores the caller's
interrupt state. See SMS `src/dolphin/os/OSCache.c:140` and
`src/dolphin/os/OSSync.c:9`.

Only source-intersecting lines should be maintained. Game-range boundary
neighbors are game/JSystem CPU state or allocation headers; the sidecars
are PPC-owned recording storage and mod statics. Main stack, codec workspace,
planned output and ARM mailbox ownership lines must remain outside these
aligned intervals. The CODEC lease excludes concurrent ghost/state transfers
(`src/transfer_lease.cpp:133`); this is essential for MEM2 sidecars.

## Hardware writers

| Writer | Source evidence and consequence |
| --- | --- |
| ARAM | Current `launcher/kernel/asm/ARStartDMA.S` copies synchronously on PPC, stores the destination cache lines, executes `sync`, then requests only a zero-length completion. `ARQPostRequest.S` likewise copies before its callback. All JP/US/PAL retail functions exactly match the launcher's normal pattern tuples: ARStartDMA `(0xEC,9,6,2,0,8)` and ARQPostRequest `(0x158,26,22,5,13,2)`. `Patch.c:2760` selects the normal replacement for SMS; `Patch.c:3197` explicitly enables the ARQ replacement for title GMS, independently of region. |
| DVD | Retail `dvd.c:1010` reports the current command state; its completion sets END after the hardware completion callback. Nintendont finishes the destination write/cache sync before acknowledging the DI request (`launcher/kernel/DI.c:960`). Disabled interrupts and frozen CPU threads prevent another guest command after END admission. |
| THP locked cache | `THPDec.c:1211`, `1522` and `1588` enqueue texture writes with `LCStoreData`. That function enqueues and returns; DVD idle does not drain it. The HID2 queue check closes this independent writer. |
| GPU | `GXDrawDone` waits for issued GPU work. Heap texture-copy targets exist in `BathWaterManager.cpp`, `bossManta.cpp` and `JDREfbCtrl.cpp`; stale CPU lines still require the pre-pass flush. No rendering may be issued between passes. |
| Audio DSP | Muting the DAC does **not** halt the DSP. Its output/channel/effect buffers are allocated in the persistent JASDram audio heap, created before the stage heap (`MSound.cpp:429`, `Application.cpp:307/393`, `JASDSPBuf.cpp:49`, `JASDSPInterface.cpp:73`, `JAIData.cpp:650`). Those buffers are outside the captured ranges. |
| CARD and controllers | CARD DMA targets the boot-allocated sector/mount buffers, outside captured regions (`Application.cpp:317`, `CardManager.cpp:345/570`). CPU callbacks that copy results into game state are frozen. Native SI copies register results from its CPU completion handler (`SIBios.c:74`); Nintendont's SI/PAD buffers live separately in MEM2 (`launcher/kernel/SI.h`). |

## Why the cache pass matters

THP invalidates YUV buffers when allocating them (`THPPlayer.c:277`), then
updates them through LC DMA. DVD auto-invalidation happens before submitting
a read (`dvd.c:853`), not after it. A previous save can nevertheless have
cached a hardware-written buffer. Quiescence stops further writes but does
not clear that stale cached copy; eviction between passes can otherwise
change the bytes seen by the codec. The aligned writeback/invalidate pass
establishes one memory view while preserving dirty CPU-owned state.

With these additions, the inspected writer paths support stable source bytes
through replay on the supported launcher. The assumptions remain a healthy
retail owner layout, successful installation of the matching launcher patches,
nonoverlapping aligned source/work/output ownership, and no source-mutating
callbacks between passes. Patcher signatures prove applicability, not that a
particular running console installed them. The Wii-only admission must not be
extended to standalone Dolphin, where ARAM is still asynchronous, on this
evidence alone. No THP bytes are omitted or canonicalized by this proposal.
