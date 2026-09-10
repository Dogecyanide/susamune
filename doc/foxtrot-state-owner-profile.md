# Persistent Sunshine state owner admission

`StateArchiveProfile` is a bounded, optional sidecar for a saved memory state.
Its 5,920 bytes fit beside the existing 984-byte state metadata in the SD
mailbox's 7,168-byte metadata allowance. A failed profile capture leaves a zero
sidecar; it does not invalidate an ordinary memory save.

The profile is captured with the state, then recaptured and compared before an
imported state is restored. The archive envelope separately binds the exact
build, game revision, snapshot format, setup configuration and scenario. The
profile compares live owner addresses and topology; matching the stage heap's
numeric address alone is insufficient.

## Retained owners

- Heap identity, parent/disposer links, mutex, bounds and child tree at offsets
  `0..0x58` remain fresh. The stage disposer list at `0x58..0x64` and allocator
  state beginning at `0x68` rewind with their game allocations. Every traversed
  MEM1 heap must have an idle mutex and a known ExpHeap/SolidHeap vtable.
- Root and system allocation lists are bounded to 4,096 entries per heap. Each
  node's signature, size, previous link and containment are checked. Two ordered
  hashes and the count bind those outside-stage allocations. Child traversal
  allows at most 32 heaps. Mod-owned MEM2 heaps are not state destinations;
  their mutable ghost allocations are excluded from the game owner proof.
- The application service pointers must match. Controller disposer/list links,
  rumble, recording/reset transport fields and reset uptime remain fresh; the
  game input/meaning state still rewinds. The hardware-facing TTimeRec profiler
  and rumble manager remain live.
- `gSetupThread` is an actual `OSThread` inside the previously captured game BSS:
  JP `803F2390`, US `803FCBE8`, PAL `803F4388`, each `0x310` bytes. The fresh
  thread and stack pointer are excluded. Capture requires a terminated setup
  thread and an idle DVD drive.
- Mounted MemArchive owner objects remain fresh. Their list/disposer topology,
  typed fields, resource backing and RARC headers must match. At most 16 volumes
  are admitted. ARAM, DVD and Comp archive owners currently refuse persistent
  admission because their transport/worker lifetime has not been proved here.

The heap offsets follow the pinned SMS decompilation's
[JKRHeap definition](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/include/JSystem/JKernel/JKRHeap.hpp).
Controller transport ownership follows
[JUTGamePad](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/JSystem/JUtility/JUTGamePad.cpp),
and profiler ownership follows
[TimeRec](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/System/TimeRec.cpp).
Region-specific addresses are checked against the three retail symbol maps.

## Restore ordering

The caller retains the existing scene, card and GPU barriers and exclusive
ownership of the source and codec workspace. A locally captured matching live
profile supplies the codec copy callback. The compressed stream is validated
completely before the callback is invoked. Its bounded, sorted skip ranges keep
fresh runtime bytes untouched, including when a decoded fragment starts or ends
inside a retained range. No old OS object is written temporarily and repaired
afterward. The archive's stored ranges never become independent write authority.

The callback cannot fail after preflight. The caller must retain the admitted
profile and source unchanged through both inflate passes. Any later codec failure
is an interrupted commit, not a harmless load refusal.

## Evidence and remaining proof

Production host tests cover changed heap/resource owners, busy mutexes, unknown
archive variants, malformed lists/backing, corrupt profile bounds and retained
bytes across arbitrary decoder fragments. Codec tests verify that its callback
is never invoked for an invalid stream.

Two independent US Dolphin boots of interim image `7C2E07DF`, both in Bianco 1,
produced matching profiles: 439 anchors, 33 retained ranges, 771 root allocations
and 25 system allocations. The second boot's fake-MEM2 dump supplied only links
through uncaptured mod heaps when comparing the first boot's MEM1 dump. This is
owner-admission evidence, not a completed cold-boot gameplay restore. Private
memory dumps and comparison outputs stay under `build/` and must not be shipped.

An integrated export, emulator restart, import, restored gameplay, repeated load
and ordinary stage departure remain required before claiming reboot restoration
has been demonstrated. Wii power-cycle behavior requires hardware validation.
