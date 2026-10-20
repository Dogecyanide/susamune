# Timewarp feature feasibility — bounded assessment

2026-10-08. Read-only source assessment against the V2.3.3-derived Timewarp
checkout. No game source, protected timer source, timer cave or scratch was
changed. These are design recommendations and measured format arithmetic,
not Wii runtime results. The overall implementation plan is maintained by the
lead assessment.

## Online ghosts and community data

Public repository pin: `zeldocto/delfino-ghosts`
`f2940b9754096cc2d50fb0b62b567073f491bb7e`. GitHub's public commit endpoint
returned this pin during this assessment. The downloaded `README.md`,
`src/lib/ghosts.ts`, `src/lib/downloads.ts` and storage migration match the
pinned files after newline normalization. No mutation API was called, and no
personal data was sent. Deployment configuration and live service health were
not verified.

- A writable API exists: [`src/lib/ghosts.ts`](https://github.com/zeldocto/delfino-ghosts/blob/f2940b9754096cc2d50fb0b62b567073f491bb7e/src/lib/ghosts.ts)
  calls the paged `list_ghosts` RPC (line 38), and `createGhost` (line 117)
  uploads the object before inserting its database metadata. It attempts to
  remove an orphan object if insertion fails. This is Supabase Auth, Storage
  and Postgres access, not a hypothetical write endpoint.
- [`src/lib/downloads.ts`](https://github.com/zeldocto/delfino-ghosts/blob/f2940b9754096cc2d50fb0b62b567073f491bb7e/src/lib/downloads.ts)
  downloads the unchanged bytes from public Storage. Download counting is a
  separate authenticated mutation, and is unnecessary for file delivery.
- The pinned [storage migration](https://github.com/zeldocto/delfino-ghosts/blob/f2940b9754096cc2d50fb0b62b567073f491bb7e/supabase/migrations/0002_storage.sql)
  enforces **2,097,152 bytes per object**, allows public reads, and confines
  authenticated writes to the user's folder. The documented database cap is
  200 ghosts per account. Authentication/refresh, authorization, bounded
  transport, cancellation and atomic local publication still need clients.
- The pinned [README](https://github.com/zeldocto/delfino-ghosts/blob/f2940b9754096cc2d50fb0b62b567073f491bb7e/README.md)
  explicitly says binary validation occurs in the browser and can be bypassed
  by calling Storage directly (lines 434–440). All downloaded files must pass
  Moonshine's full independent format/length/CRC/route checks. Metadata,
  filenames, times and TAS labels from this service are untrusted.
- The website's MDP leaderboard ranks download popularity. Its `level` and
  nullable `time_ms` fields also support fastest-time browsing, but the client
  supplies those fields and `is_tas`. That is not a verified IL leaderboard.
  No achievement-participation scheme is established by the inspected source.

**Wii/Nintendont:** `launcher/loader/source/update.c:193` already initializes
networking and `ssl.c` implements a loader TLS adapter. This supports a
launcher-side prototype; it does not prove availability once the game and
custom ARM kernel take ownership. The bounded kernel search found Bluetooth
sockets, not a gameplay HTTP/TLS service. In-game access needs a separately
proved transport and explicit PPC/ARM transaction protocol, with network work
outside frame-sensitive paths and existing storage exclusion rules retained.
Modern endpoint TLS compatibility, credentials, network resources and actual
concurrent disc I/O behavior require hardware evidence.

**Standalone Dolphin:** the mod's fake-MEM2 and CARD backends do not themselves
provide host HTTP access. A host companion importing/exporting validated local
files is the shortest demonstrable route. A real direct in-mod connection
needs an implemented and verified emulated network/device bridge; emulator
network capabilities alone are not an existing Moonshine transport.

Recommended online order: public download/catalog prototype, then explicitly
linked accounts and user-selected uploads, then a separate service contract
for community records. Keep practice fully functional offline. Display the
selected file and public identity before an upload; do not silently queue
personal runs. Pairing/revocation and a narrow upload credential need backend
design if account credentials are to stay out of the console UI.

Competitive results need canonical region/revision, route, ruleset and build
identities; independently parsed timing and assistance flags; idempotent run
IDs; moderation and eligibility rules. CRCs prove integrity, not honest play.
Slowdown, takeover, savestate and TAS runs must retain their assisted status.
Achievement percentages require explicit participation, a versioned eligible
population/denominator and versioned achievement definitions. Count distinct
participating players, not installations, downloads or uploaded files; do not
describe percentages as applying to all players.

## Recorded gameplay camera and directed replay

Current V6 stores 16-byte poses at a minimum interval of four QFs, plus
24-byte controller/FLUDD samples. Bounds are 17,983 poses, 36,000 inputs and
71,928 QFs (`ghost_format.h`, `ghost_fludd.h`, `ghost_teaching.h`). No recorded
camera exists. Single Watch currently lends an invisible observer Mario pose
to the live game camera; it cannot recover the original camera from that.

The camera fields needed for an unquantized look-at representation are
position, target and up (nine floats = 36 bytes), plus FOV, aspect, near and
far (four floats = 16 bytes). With a four-byte synchronization key that is
**56 bytes per sample**. Capturing the final 3x4 view and 4x4 projection
matrices instead is **116 bytes per sample** including the same key. These
are payload lower bounds, before track/segment metadata, viewport/cut flags
or additional render state. Reconstructing a view from scalar fields has
not been proved bit-identical to all gameplay/cutscene render paths.

| Camera payload | 17,983 samples | 36,000 samples |
| --- | ---: | ---: |
| 52-byte scalar view + 4-byte key | 1,007,048 B | 2,016,000 B |
| 112-byte matrices + 4-byte key | 2,086,028 B | 4,176,000 B |

The maximum V6 file using its actual version-specific bounds is
`256 + 2048 + 17983*16 + 32 + 36000*24 + 8*12 = 1,154,160` bytes.
Even the first camera option at only 17,983 samples yields **2,161,208 bytes**,
exceeding the site's current 2 MiB ceiling by **64,056 bytes** before new
headers. At 36,000 samples the scalar option yields **3,170,160 bytes**.
The shared legacy transport maximum is 1,298,016 bytes. Neither the current
transfer reservation nor the website limit admits all these extensions.
Compression must be measured and may not be assumed to solve worst-case fit.

Those sample counts are capacity comparisons, not proof of camera sampling
frequency. Determine the actual final-camera update/render boundary first.
Recording only on existing pose samples and interpolating between them cannot
be advertised as exact original rendered camera playback without that proof.
Synchronization must distinguish scene changes, camera cuts, repeated QFs,
pause/slowdown and replay seeks. Keyframes and original-camera playback must
share a clear exclusive camera owner.

Useful existing implementation points:

- `practice_session.cpp:584` reads the existing free camera's 40-byte
  position/target/up/FOV view. Extend a new camera-track representation with
  aspect/near/far rather than silently inheriting the viewer's settings.
- `practice_session.cpp:591` applies the view and rebuilds cached projection
  and view matrices; the cue wrapper at line 936 restores and reapplies it.
  This provides an insertion point for Watch camera ownership. Preserve its
  lifecycle, restore and stage-generation rules.
- `PolarSubCamera.hxx:132` calls its projection member `Mtx`, but the existing
  apply path correctly treats address `+0x16c` as a **4x4** perspective matrix.
  Do not capture `sizeof(mProjectionMatrix)` and assume it contains all 64
  projection bytes. This declaration requires an explicit audited access.

Use a new bounded optional/versioned camera track and keep the V3–V6 readers.
Old ghosts should explicitly offer the current observer camera. A separate
keyframe track can store `(segment, frame, view, interpolation/cut mode)`;
capture from freecam, interpolate position/target with a clamped spline and
orientation with normalized quaternion interpolation, and preserve intentional
cuts. Seek by timeline position, never wall time. Exact recorded-camera mode
and an authored cinematic camera are distinct choices.

## Branching TAS

Current `practice_session.cpp:57` records 16 bytes per frame into a fixed
4,096-frame/65,536-byte tape. The V2 project manifest is 160 bytes with three
state components (Beginning and two checkpoints), one tape and up to 32
16-byte scene transitions (`tas_storage.h`). A full serialized tape payload
bound is **66,052 bytes** (`4 + 4096*16 + 32*16`), before its envelope.

`requestContinue()` at `practice_session.cpp:1849` validates the attached
scene/settings and tape hash, then sets `sCount = sTakePosition` and truncates
the transitions. It overwrites the old future. Calling this function from a
new Branch button would therefore lose Branch A unless A has first been
durably retained.

Recommended format: immutable tape chunks plus a bounded branch directory,
with branch IDs, parent/fork frame, chunk references, name, scene/settings
identity and checkpoint references. Publish a new generation only after its
referenced chunks and anchors validate. The first implementation may save a
complete immutable 66 KiB tape per branch on SD before takeover, which is
cheap relative to a multi-MiB state and much simpler than input deduplication.
Keep only the active tape in the current working bank. Lack of space or an
interrupted save must leave the previous branch/project generation loadable.

For seeking, restore the closest compatible earlier sparse anchor and replay
recorded input through ordinary update scheduling to the requested frame.
An anchor must bind branch/prefix identity, scene, settings and state-owner
admission; an equal frame number is insufficient. Scrubbing is asynchronous
and may need loading-zone traversal. The present checkpoint UI rejects loading
another area's checkpoint (`tas_project.cpp:265`); cross-area seek therefore
needs its own proved traversal/re-entry lifecycle.

Preserve the current replay distinction: fingerprint differences call
`warnDesync` (`practice_session.cpp:767`) and playback continues; unexpected
scene/settings or damaged tape stop structurally unsafe replay with the take
kept. A warning must not masquerade as verified branch provenance. Initial
editing/checkpoint policy should retain current admission restrictions until
an explicit handling of a diverged live state is proved.

Adapt the concept UI to D-pad frame/checkpoint navigation, shoulder-button
page/branch changes, an explicit A takeover action, and visible branch name,
frame/cursor, checkpoint markers, seek progress and unsaved state. Route
controls through existing modal input ownership so navigation cannot also
trigger savestate/pause binds. Camera keyframes can use the same timeline
frame identity without being gameplay input.

## Shareable states

Existing durable state support is narrower than arbitrary portability.
`doc/foxtrot-sd-states.md:181` describes full ARM envelope checks and PPC
build/snapshot/scenario/span/owner checks. `StateArchiveProfile` binds live
owner addresses/topology and retains fresh OS, heap, controller, archive and
resource owners; matching heap addresses is insufficient. Unknown archive
variants refuse admission. Persistent restore includes recovery for a failed
second streaming pass, and rejected imports preserve the prior state.

There is useful prior evidence: `doc/foxtrot-sd-states.md:320` records a
successful cross-process US Dolphin import and continued gameplay in one
scenario, and altered-owner rejection preserving the previous slot. That
does not establish arbitrary cross-player, all-stage or all-build safety.

First support shareable files **only under the existing exact compatibility
and owner checks**, with a readable refusal reason. Test independent boots
and players with varying prior stage histories, settings/save progression,
all supported regions and hardware. Cross-region/build pointer remapping is
a separate serialization/reconstruction project, not an import flag. No
automatic relaxed mode or heap-owner repair should be added to make a shared
file load. Keep the original file intact after rejection.

## Collision overlay and ghost path

Both can start with small read-only prototypes without a ghost-format change.

- Collision: `Mario.hxx:1100` exposes Mario's actual `mFloorTriangle`.
  `BGCheck.hxx:21` defines triangle type, value, flags, vertices, normal and
  owner. Highlight that exact admitted live triangle and show its numeric type
  even when a friendly type name is unknown. Check illegal/sentinel data and
  stage lifetime. Do not substitute a new ground query as evidence of the
  triangle Mario is using, and do not write collision/standing flags.
- Nearby geometry: `MapCollisionData.hxx:42` provides static/moving grids,
  the triangle array and bounded counts. Validate the layout against decomp
  and all regional maps, use nearby cells/distance limits and a fixed draw
  budget, deduplicate triangles repeated between cells and clip geometry at
  the near plane. Dynamic collision owners need separate lifetime checks.
  The parent task's general geometry overlay should not imply it visualizes
  every actor collision primitive.
- Ghost path: decode existing pose samples without allocating a second track,
  draw a bounded visible/time window, and break at segments, scene changes
  and discontinuities. `practice_visuals.cpp:67` already has camera projection
  helpers and `ghost.cpp:2485` projects recorded positions. A real depth-tested
  3D racing line needs a world draw pass; a HUD projection has different
  occlusion behavior. Do not label either as collision geometry.

Suggested order is current-floor diagnostics and bounded path rendering,
then exact camera capture/projection proof, then a versioned camera/storage
extension and keyframes, followed by immutable branches and sparse seeking.
Online and general shared-state claims stay gated on their independent
transport, service and cross-session validation evidence. None of this work
requires editing or relocating the protected timer.

## Narrow follow-up: executing cold code from immutable staging

**The actual launcher establishes a MEM2 instruction mapping.** This is more
than evidence that MEM2 loads/stores work. The existing V2.3.3 checkout's
`build/launcher/group-wii/loader/loader.elf` has SHA-256
`8ff0693be701c85b38c0511c0b4a69c44558c5831a17c3a65e8b3955fc92178e`.
Its map attributes `__InitBATS`/`__configBATS` to libogc's `system_asm.o`.
Direct decoding of this ELF establishes:

- Startup at `0x80004020` calls `__InitBATS` (`0x800277a0`), which selects
  `__configBATS` (`0x80027364`).
- `0x80027374..0x80027378` writes HID4 (`SPR 1011`) with `0x82000000`.
- `0x80027430..0x80027444` constructs `r3=0x10000002` and
  `r4=0x90001fff`, writes IBAT4L/U (`SPR 561/560`), and writes matching
  DBAT4L/U (`SPR 569/568`). The mapping covers effective
  `0x90000000..0x9fffffff` to physical `0x10000000..0x1fffffff`, including
  `0x91e3f000 -> 0x11e3f000`. This mapping range is not a claim of that much
  physical RAM.
- `launcher/loader/source/global.c:66` changes HID4 to `0x83900000` and
  clears only selected low BATs, leaving these extended BAT4 registers alone.
  `launcher/multidol/crt0.S:7` only initializes stack/BSS and enters its main;
  its `global.c:24` does not rewrite BATs.
- `launcher/resetstub/crt0.S:102` independently installs the same IBAT4 and
  DBAT4 mapping, then restores instruction/data translation. That is reset
  stub evidence, not proof that every retail in-session reset takes this path.

No new BAT installation appears necessary for the initial Nintendont loader
path. The pilot still must read/confirm the actual live IBAT4/HID4 after retail
game startup and after each supported reset path; this assessment did not
audit every retail executable instruction or prove Wii execution. Dolphin's
fake-VMEM instruction translation remains a separate test.

**The existing immutable image has the right lifetime, but its format is not
yet execute-in-place.** `mem2_map.h:117` reserves
`0x91e3f000..0x91ede000` for the reset-safe file, with model assets from
`0x91ede000..0x91f00000`. JP also reserves offset `0x86000..0x9f000` for
its immutable translation file (`japanese_ui.h:6`), and the loader refuses a
JP mod exceeding the lower ceiling (`SusamuneMod.c:103`). Do not put cold code
in that translation span or the asset vault.

`Patch.c:4089` validates the retained prefix whenever it is consumed.
`Patch.c:4327` copies the two current segments into their linked MEM1
destinations and clears their BSS; `PatchGame` calls it again at line 4398.
`SusamunePreserveGhostModelAssets` starts at the fixed file ceiling and refuses
an oversized overlap. Therefore the image prefix can be referenced directly
for immutable code, but mutable/static state cannot be placed there. A cold
section needs a stable file offset and a linked runtime address equal to
`staging base + 32-byte header + payload offset`, plus manifest validation
that explicitly describes it instead of copying it as another MEM1 segment.

**Cache work is incomplete for executing the staging image today.** The PPC
loader flushes staged bytes at `SusamuneMod.c:128`; it does not invalidate
their instruction cache. ARM's `sync_after_write` handles its own publishing
side. `FakeEntryLoad.S:18` invalidates only the specified loaded DOL span and
low MEM1 patch area, which excludes the retained MEM2 file. The pilot needs
a checked PPC instruction-cache invalidation and ordering before its first
cold call, repeated appropriately after a fresh image is staged. Ensure ARM
published bytes are visible before invalidation/execution; do not flush stale
PPC data over ARM modifications. A MEM1 entry thunk must remain callable before
this preparation and after a reset.

**One minimal real module: `src/card_encoding.cpp`.** It has no persistent
mod-owned BSS or GPU data. The existing linked US emulator map contains
`susamuneCardMount` (0xa8 bytes) and `mountCard` (0x5c bytes): **260 bytes**
before any veneers/alignment. It calls retail `CARDMountAsync`, CARD sync and
`CARDUnmount`, so it tests return paths and calls back into the game. Its
existing temporary encoding change is ordinary production behavior and must
remain identical. It should first be exercised with controlled absent/wrong
encoding test cards so a format/save action is never inferred by the pilot.

`scripts/patches.py:45` currently hooks it with a retail MEM1 `b`. That
instruction cannot reach `0x91e3f000`; keep a MEM1 gateway and use an absolute
indirect transfer preserving LR/ABI. Calls from the cold module back to MEM1
also require checked long-call stubs or indirect calls, not masked REL24
overflows. The 260-byte module proves the path and is not a meaningful savings
claim. Verify the linked instruction locations, no duplicate cold payload,
unchanged timer layout, normal/error return behavior, soft reset/reload,
instruction-cache handling and actual Wii/Dolphin execution before moving a
larger module.

### Private cold-code execution result

`scripts/timewarp_cold_pilot.py` now compiles the unchanged
`src/card_encoding.cpp` with the repository's production compiler/options,
links a cold image at both `0x71e3f040` (Dolphin fake VMEM) and `0x91e3f040`
(Wii, link-only), and checks every direct branch plus the exact outbound
absolute-gateway words. The resulting aligned image is **320 bytes**,
including the two 16-byte outbound gateways and alignment. Mutable test
state is separate; there are no allocated writable sections in the cold ELF.

The standalone owned Dolphin process successfully ran **18 cases**: nine
normal/error/encoding-retry scenarios, repeated after clearing test state and
invalidating the retained cold code's instruction cache again. Return
addresses observed by the MEM1 test doubles fall inside fake-VMEM cold code.
Arguments, callbacks, encoding preservation/retry behavior and the return to
MEM1 all match the expected results. Each case compares the cold bytes to the
embedded immutable source byte for byte; the host separately compares that
source to the linked binary. Surrounding canaries remain intact.

The private receipt is `build/timewarp-cold-pilot/receipt.json`. It records
the compiler commands, addresses, hashes, all case outputs, fresh private
profile and stopped owned process. It uses the existing Dolphin executable
whose SHA-256 is
`d2bc0da070540c31227d934b75903005c96f30ac1d200cfe65e7d85783a0efce`, with
`CPUCore=1`, `CPUThread=False`, `Fastmem=False`, `MMU=False`.

This proves actual fake-VMEM instruction execution and MEM1 call/return
transport for one real module. Its CARD routines are harmless test doubles;
there is no retail game, card I/O, actual retail reset or Wii execution in this
proof. The standalone boot image deliberately retains a duplicate copy for
staging: **zero MEM1 savings are claimed**. No production source, manifest,
loader, map, timer source, cave or scratch was changed by the pilot.

### Exact sharing across three different levels

Fresh captures now cover **Bianco 1 (area 2), Ricco 1 (area 3), and Gelato 1
(area 4), all episode 0**, from one historical PAL Snapshot17 build. A
contemporaneous control holds three Gelato 1 positions. These are separate
actual areas, not different Plaza variants. The source fixture is the private
`build/v2.3.3-feedback5/final-lifecycle/input.iso` in the release checkout;
its source receipt names release image CRC `E06FED31`. The exact private
input ISO SHA-256 is
`bb19aef7b9b5761c2f1ac80eaa059434640887824ff7b4ce7d2023416f4cbe37`.

The capture used a fresh isolated profile and an owned Dolphin process. Its
existing game-thread adapter entered Plaza through `ILing::start`, then the
real warp wheel selected each level. Ordinary D-left input saved slot 1.
The reader copied the immutable compressed slot and its exact 6,936-byte
`StoredState`, checked that metadata/pool/checksum stayed unchanged while
reading, verified the packed CRC and decoded Adler, and required agreement
between live scene, stored header and decoded `TApplication` scene. Raw,
packed and metadata bytes plus hashes remain under
`build/cross-level/lifecycle/{mixed,same-level}`. The capture receipt records
the source hashes and confirms the owned process stopped and timer source
remained unchanged.

Current production PPC Quick encoding reproduced **all six captured streams
byte for byte**. Because Gelato's output exceeds the standalone harness's
single output buffer, encoding used 4 MiB batches aligned to the existing
128 KiB independent block boundary. Each batch executes the production PPC
codec; independent decoding verifies the combined stream. Full-stream PPC
controls for Bianco and Ricco additionally match the batched result exactly.
The codec clears its LZ4 state for each block (`src/state_codec.cpp:75`), so
batch boundaries do not introduce a dictionary or change block boundaries.

| Three-state set | Separate Quick streams | Exact shared-block savings | Gross remaining bytes |
| --- | ---: | ---: | ---: |
| Bianco / Ricco / Gelato | 21,301,842 | 1,011,333 (4.7476%) | 20,290,509 |
| Gelato / Gelato / Gelato | 22,492,392 | 9,919,481 (44.1015%) | 12,572,911 |

There are **9 whole raw blocks identical in all three different levels at
the same offsets**: 1,179,648 bytes per state. The corresponding unique
compressed blocks occupy 371,661 bytes. Pairwise compressed overlap is
430,676 bytes (Bianco/Ricco), 371,661 (Bianco/Gelato), and 580,657
(Ricco/Gelato). The same-level control shares 65 complete blocks across all
three positions. Neither trio contains duplicate blocks within an individual
state, so the listed saving is entirely from sharing between states.

The mixed trio remains **1,481,677 bytes over the current 18,808,832-byte
pool even before allocator overhead**. Thus the large same-level savings
cannot be generalized to unrelated levels. These are exact block-sharing
measurements of this sample, not the fraction of individual equal bytes,
not a universal worst case, and not a production allocator or cross-level
restore proof. The older capture build limitation remains explicit even
though its encoded bytes equal current PPC output.

`build/cross-level/current-ppc/receipt.json` retains the common
`sets / slots / ppc_quick` schema for the parent's allocator tests, source
hashes, input/stream paths and hashes, scene evidence, metadata paths/hashes,
batch controls, and stopped owned codec process. Reproduce with
`scripts/timewarp_cross_level_slots.py` for capture and
`scripts/timewarp_cross_level_ppc.py` for encoding/measurement. All output
is private task build data; neither historical fixture nor production game
source is modified.
