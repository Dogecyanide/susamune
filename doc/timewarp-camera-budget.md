# Bounded ghost camera feasibility

Original read-only assessment for Prototype 10, 2026-10-15. Prototype 11 now
implements the bounded experiment described in
[`timewarp-ghost-camera-v8.md`](timewarp-ghost-camera-v8.md), using quaternion
keys in the same 24-byte budget. The proposals below explain the memory
calculation; the V8 document describes the actual format and verified scope.

## Record the resulting view

C-stick input does not specify the camera. Retail camera state also follows
Mario, geometry and obstruction responses, area scripts, transitions, and
prior camera history. Pose ghosts do not run the original world's complete
simulation. Feeding the same C-stick into their live camera therefore cannot
reconstruct the recorded view.

The existing `readView`/`applyCamera` practice code already identifies final
camera position, target, up direction and FOV, then rebuilds render transforms.
An optional ghost track could record those results after retail camera updates.
The interpolated camera would include autonomous motion because the recorded
data describes the resulting view rather than its inputs. It would remain an
approximation between samples, particularly during fast turns and cuts.

## Available space without shortening recordings

Both V7 pose banks reserve the legacy 431,584-byte sample area before private
model/other owners. The current maximum is 17,983 poses * 16 = 287,728 bytes.
The difference is **143,856 bytes per pose bank**, below the unchanged model
heap at offset `0x695E0`. This is a potential version-specific camera area,
not free space for legacy 15-minute recordings, which still need the entire
legacy pose region. The secondary Watch ghost reuses the recording bank, so
the same bounded layout must work independently in both banks.

The V7 maximum serialized file is 1,154,160 bytes. Its existing file limit is
1,298,016 bytes, leaving the same **143,856-byte** extension budget. Input
banks are not spare: the used 864,000 bytes are followed by state metadata or
presentation owners. The model heap, catalog cache, state pool and transfer
workspace must remain untouched.

An illustrative 24-byte camera sample can carry a 32-bit timestamp, three
signed 24-bit position coordinates, three 16-bit orientation angles, a 16-bit
FOV, flags and two reserved bytes. Quarter-unit position quantization covers
roughly +/-2.1 million game units. Orientation interpolation must use a
shortest rotation/quaternion representation internally, not naïve Euler lerps.
Projection parameters and hard cuts need explicit bounded events rather than
interpolation across a discontinuity. These are design examples, not a frozen
wire format or a claim that all retail coordinate ranges have been measured.

| Proposed sample cadence | Ten-minute sample bytes | With 512 extra events and 32-byte header |
|---|---:|---:|
| 5 Hz, 24 bytes | 72,000 | 84,320 |
| 8 Hz, 24 bytes | 115,200 | **127,520** |
| 10 Hz, 24 bytes | 144,000 | 156,320 (too large) |

The 8 Hz example is 124.5 KiB per active ghost and leaves 16,336 bytes below
both bounds. Its maximum file would be 1,281,680 bytes. It preserves all
17,983 poses, 36,000 input samples and the existing ten-minute duration. A
single initial-view record can be included in the extra-event budget. This
uses memory already reserved for ghosts and takes none from savestates.

The table is a hard upper-bound proposal. Periodic samples need bounded
timestamp scheduling under slowdown, pauses and state loads. Extra cut/FOV/
projection events must be capped. If they exhaust the event budget, the camera
track must visibly become incomplete or fall back; ordinary recording must
still retain its ten minutes. Compression may improve typical file size but
must not be assumed in admission or capacity calculations.

## Remaining work before implementation

- Prove the final capture boundary and the camera's projection/cut semantics
  in the local game/decomp layouts. A correct matrix is 4x4 at camera +0x16C;
  the old header's `Mtx` declaration is not its real extent.
- Add an optional/versioned chunk and update PPC, ARM, host/site validators,
  save/load copying, catalog bounds and legacy rejection rules. Legacy files
  remain playable without recorded camera; their old views are unrecoverable.
- Include the used camera prefix and counters in ghost state continuation.
  Seeking or loading must not retain camera samples from the discarded future.
- Scope render overrides to Watch, select which ghost owns a two-ghost view,
  restore all borrowed transforms before leaving Watch, and define behavior
  for cross-region aspect/video modes. Race and online keep the local camera.
- Compare rapid turns, indoor obstructions, scripted cuts and slowdown on
  hardware before calling 8 Hz visually acceptable. No CPU/linked-size or Wii
  smoothness claim follows from the byte arithmetic alone.

The cheapest useful next experiment is a small final-view capture/interpolation
fixture in these existing gaps. Full deterministic camera reconstruction from
input would require much more of the original world and is not the low-cost path.
