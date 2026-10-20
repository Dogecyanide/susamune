# Recorded ghost camera: Prototype 11

New ghosts retain a compact record of the actual rendered camera. In Ghost
visuals, **Camera: Recorded** is the default for Watch. **Free** retains the
existing Watch camera/free-camera controls. Legacy files have no camera track
and fall back to Free. In Watch 2, the primary ghost owns the recorded view.
Race ghosts and online play never apply a recorded camera. No RNG is captured
or restored by this feature, and it does not reproduce boss/enemy simulation.
Closing the menu with a chord containing Start/B now waits for those buttons
to be released before Watch can treat a subsequent press as its exit command.

The camera wrapper chains the existing practice hook. It captures the final
`CPolarSubCamera` world position (+0x124), view matrix (+0x1EC), and vertical
FOV after the retail render cue. This includes natural tracking, obstruction
responses and scripted camera movement, rather than attempting to infer them
from C-stick input. Watch borrows the camera's render fields only; the previous
values return after the final overlay, before subsequent game simulation or
ordinary state loads. Stage generation, director, camera and heap ownership
guard restoration; stage setup discards an old owner without dereferencing it.

## Format and bounds

Canonical **SGHF V8** requires feature mask **31**. Pose, segment, attachment,
and SGTI V3 input layouts are unchanged. A mandatory SGCA chunk follows the
teaching/split prefix, although it may contain zero keys. All integers are big
endian. Readers continue accepting V3–V7. Older programs that do not know V8
reject its required feature/version rather than misreading the tail.

The SGCA header is 32 bytes: magic `0x53474341`, u16 version 1, u16 header size
32, u32 key count, u32 flags (bit 0 means truncated), u32 CRC32 over key bytes,
then three zero u32 words. SGTI's CRC covers only its own inputs/splits; the
outer file/payload checksums cover both chunks.

Each 24-byte key contains:

| Offset | Bytes | Value |
|---|---:|---|
| 0 | 4 | absolute mapped QF |
| 4 | 9 | three signed 24-bit world positions, quarter-unit precision |
| 13 | 8 | normalized x/y/z/w quaternion, four signed 16-bit values /32767 |
| 21 | 2 | vertical FOV in 1/256 degree |
| 23 | 1 | segment index in bits 0–5; cut in bit 6; bit 7 reserved |

Capture samples the final rendered view when at least **15 QFs** have elapsed
since the previous key. Frame quantization makes the practical rate roughly
7–8 Hz at normal speed. A segment boundary, over-500-unit displacement,
over-90-degree rotation, or over-15-degree FOV change inserts a cut sooner.
This is a heuristic: a discontinuity smaller than those thresholds can still
interpolate, and rapid continuous turns are approximate between keys.

Interpolation uses linear position/FOV and normalized shortest-path quaternion
interpolation. It does not blend across cuts or scene boundaries. Near/far
planes and aspect ratio remain those of the local game/video mode. A camera
track is a viewing aid, not an exact frame-by-frame cinematic recording.

There are at most **5,312 keys**. The header plus keys occupy **127,520 bytes**
(124.5 KiB) from the existing spare pose-bank tail at offset 287,728. Both banks
remain within the old 431,584-byte pose region; all model heaps, input banks,
MEM1/MEM2 reservations and state pool reservations remain unchanged. The
existing global file maximum is unchanged. V8 retains 17,983 poses, 36,000
inputs and the full **71,928-QF ten-minute limit**.

The finite key budget is shared between periodic samples and early cuts. A
pathological number of cuts can exhaust it before ten minutes; ordinary ghost
recording continues, marks the camera truncated, and Watch falls back to Free
past the last captured camera key. Invalid/unavailable views are skipped.
The format does not invent camera data for old recordings.

## Savestates and checks

`Track`, `SavedPrefix`, the 512-byte ghost metadata and snapshot version 18
retain their layouts. V8 uses reserved metadata words 126/127 for checked
camera-prefix size/magic, and appends a fourth payload span. V3–V7 recording
continuations have a zero fourth span and preserve the old payload stream.
Restoring a V8 prefix restores its key count and keys, removing abandoned
future camera samples. Existing strict build/region/scene/owner checks remain.

Focused host checks execute the production quantizer/interpolator under
fast-math, test shortest-path rotation, cuts, scene boundaries, ten-minute
capacity, overflow fallback and untouched adjacent bytes. Prefix tests cover
old V7 metadata and V8 rewind. ARM storage and independent host validators
check malformed lengths, timestamps, segments, quaternion norms, flags and
separate checksums, including the maximum tail.

The private PAL Dolphin run in `build/timewarp-pr11-camera-smoke/run2` exported
and independently validated a real 35,144-byte V8 recording containing 176
camera keys and 57 distinct views. In paused Watch, the final rendered camera
matched its evaluated recorded position and FOV exactly; quaternion agreement
was within float rounding. Free changed the actual camera, and returning to
Recorded restored agreement. An imported V8 Race ghost exposed no Watch
camera override. A validated V7 counterpart, derived by removing the camera
chunk and resealing the older envelope, used Free and reported no camera data.
Native renderer screenshots show the resulting world views. The owned process
was stopped and the copied cold payload remained unchanged.

That run measured actual PAL50 output / 25-Hz game loop, despite the emulator's
PAL60 preference; it proves neither Wii nor PAL60/JP/US camera appearance. It
used a temporary menu chord after detecting the inherited held-Start exit
issue. The final corrected build passed the separate follow-up in
`build/timewarp-pr11-camera-smoke/run3/menu-summary.json`: holding the default
Start+Y chord for half a second through close/open/close kept Watch active and
the recorded camera available; releasing it and pressing B freshly still
exited. Both private processes were closed. Rapid cuts, stage transitions,
ten-minute visual quality and cross-region video-mode appearance remain
hardware test items.
