# Filled world collision

Collision viewer remains Off by default. Floor highlights the active triangle
under Mario in yellow. World submits the stage's active map collision as opaque
coloured triangles, with no Mario-distance cutoff. Wireframe uses the same
filled collision overlay; the separate game-mesh pass supplies the rendered
geometry's edges underneath it. `collision_legend` independently hides/shows
the legend. The numeric current-floor type, value and flags remain available.

## Classification

The legend distinguishes floor, slippery, very slippery, slider, no-slip,
wet/water-slip, water, sand, warp/exit, wall, ceiling, OOB/death and current
floor. Plane classification reproduces `TBGCheckData::getPlaneType` without
its wall-facing flag write: exact type `0x801` is floor; otherwise normal Y
above `0.2` is floor, below `-0.2` is ceiling, and the middle range is wall.
Exact OOB `0x600` and death-plane `0x800` take priority over plane colour.

Floor categories follow the retail predicates, including their deliberately
different type-flag masks. Type 1 admits `0001/4001/8001/C001`; type 2 admits
only `0002/8002`, and type 3 only `0003/8003`. Slider admits `000C/800C/A00C`.
Wet/water-slip includes `0004/4004/8004/C004/0500`; water includes `0100..0105`
and `4104`; sand includes `0701/4701/8701/C701`; warp/exit includes `0200..0203`.
Remaining ground triangles receive the general floor colour, while their
numeric type remains visible when Mario stands on them.

These labels describe surface types, not a prediction of sliding. Retail
`isForceSlip` admits type 1 unconditionally. `isSlipStart` admits type 2 at
normal Y below `0.8660254`; ordinary floors can still slip through slope,
pollution and player state. Type 3 suppresses the ordinary slip-start branch
after earlier forced-slip checks.

## Admission, coverage and work

The pass requires a ready current stage, a bounded current MEM1 heap and Mario,
and complete map allocation spans inside that heap. It checks triangle
capacity/count, the normal-list static and descending moving partitions,
and warp capacity/count before reading nodes. Triangles must be aligned
inside the used triangle pool and must not carry the illegal flag.

Retail's active allocation ranges are scanned directly:

- Static nodes occupy `[0, staticCount)` and persist for the stage.
- Moving nodes occupy `(moveRemaining, listMax)` and are rebuilt each frame.
- Warp nodes occupy `[0, warpCount)` and are compacted on removal.

Every allocated node in those ranges is linked by `addCheckDataToList`.
Following the grid links repeats triangles across cells; scanning their
source allocation ranges gives the same active membership with sequential
reads. Retired moving and warp tails are excluded. Owners and list links are
never dereferenced. The allocated triangle array alone does not establish
activity. The current-floor highlight also requires active membership.

A 16 KiB BSS bitset gives exact deduplication over the admitted maximum
131,072 triangles. It is cleared on every draw; no stage pointer or membership
cache survives the call. Each unique triangle is culled once. There is no
8,192-submission cutoff or grid/list visit budget. Up to 4,096 triangles share
one GX primitive, reducing command setup while respecting the 16-bit vertex
count. The hard allocation bounds remain 131,072 triangles, 1,048,576 normal
nodes and 65,535 warp nodes, with complete spans required in the live heap.
Invalid referenced triangles are skipped and reported in the HUD.

Bitwise magnitude checks reject NaNs, infinities and coordinates outside
+/-1,000,000 under production fast-math. This viewer covers active map collision,
including moving/warp surfaces; actors without map collision and decorative
render geometry do not gain coloured collision surfaces.

## Rendering and isolation

The world pass runs immediately before the normal scene's `TEfbCtrlTex`
texture copy. A checked vtable callback identifies that scene by its archive
name and calls the retail callback exactly once. This retains the world's
depth buffer. `GhostCamera::renderMatrices` supplies the exact view and GX
perspective captured for this frame's first render cue, before Freecam restores
its temporary camera fields. Missing frame capture fails closed. The pass
inherits the world viewport and scissor, including interlaced field jitter.

Freecam's Hide HUD option affects the later 2D overlay. It no longer suppresses
enabled world collision after Continue gameplay. Mod menus, the warp wheel
and the stage-loader modal still suppress this world pass.

GX clips crossing triangles before perspective division; common-plane
homogeneous rejection reduces submissions. The projection uses GX's depth
interval `[-w, 0]`. A small projection bias places collision above coplanar
retail geometry. `LEQUAL` and depth writes preserve occlusion by the scene
and nearer collision surfaces. All enabled world modes use filled collision
triangles. The pass disables fog and installs explicit clipping, colour/alpha
and depth state. Its callback reinstalls the retail GX defaults and saved
projection before the texture copy and indirect draws.

Camera data, collision flags, player state, simulation/RNG, timers, memory
reservations and savestate/recording capacity are unchanged. The 16 KiB bitset
uses existing linked MEM1 space and performs no heap allocation. The existing
practice-assistance policy remains in effect.

## Source and focused evidence

Ground truth is the local `build/reference-sms` decomp:

- `src/Map/MapCollisionData.cpp`: pool allocation and moving-list reset.
- `src/Map/MapMakeList.cpp`: active partitions, linking and warp compaction.
- `include/Map/MapData.hpp`, `src/Map/MapData.cpp`: type predicates and plane class.
- `src/Player/MarioMove.cpp`: forced/slippery/no-slip behavior.
- `src/Camera/cameragc.cpp`: final projection and view matrices.
- `libs/dolphin/src/mtx/mtx44.c`: GX clip/depth convention.
- Retail `data/PerformLists.bin`: normal-scene copy follows `ZBufferCatch`,
  which calls `ReInitializeGX`; indirect, wave and particle draws then precede
  the composite/HUD. The callback restores those defaults and projection.

`scripts/test_collision_world.py` executes the production traversal and
projection under fast-math in a private host arena. It checks 9,000 unique
visible triangles in three batches, exact deduplication including across
pool kinds, retired tails and invalid partitions, unchanged game bytes,
moving/warp membership without owner access, nonfinite data, clipping and
near-plane crossings, depth and unchanged viewport/scissor, retail palette
and plane thresholds, Floor/Off/legend, and filled collision in Wireframe mode.
`scripts/test_collision_render.py` checks render-cue and scene admission,
Freecam Hide HUD persistence, and GX restoration before the retail callback.
Host fixtures use host-width pointers; production static assertions check
the actual PPC layouts. PAL PPC object compilation passes.

These are correctness and work-count checks, not measured Wii frame times.
Integrated region links and final runtime visual evidence are recorded by
the parent build; PR13 runtime receipts do not validate these PR14 changes.
