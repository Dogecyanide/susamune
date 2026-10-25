# Game mesh wireframe

Collision view **Wireframe** replaces supported base-world J3D mesh surfaces with their edges, then draws the same filled, coloured collision surfaces as **World**. Vertex colours, textures, skinning indices, loaded matrices and material state remain the game's. This is an edge view, without a hidden-line depth fill: edges on back-facing geometry can be visible through empty surfaces. Particles, the HUD and models drawn after the normal-scene texture copy retain their normal rendering.

`game_wireframe.cpp` hooks two call sites inside retail `J3DShape::draw`. Both call `GXCallDisplayList`; the compiler inlined `J3DShapeDraw::draw` at the second site. No object layout or displaced-instruction trampoline is required.

| Revision | VCD/VAT call, offset +0x24 | Geometry call, offset +0x134 |
|---|---|---|
| JP GMSJ01 | 0x80029EE8, original 0x48083489 | 0x80029FF8, original 0x48083379 |
| US GMSE01 | 0x802E03B4, original 0x4808269D | 0x802E04C4, original 0x4808258D |
| PAL GMSP01 | 0x802D855C, original 0x48082715 | 0x802D866C, original 0x48082605 |

These words and their adjacent argument loads were checked against the user's retail DOLs. Installation verifies both branch targets and the load instructions before changing either site. Hooks remain transparent outside Wireframe mode, an initialized stage, and the current world-camera projection. The existing collision frame hook resets the conversion budget; the normal-scene copy callback closes the conversion window before drawing collision fill. Modal menus and the warp wheel suppress conversion.

J3D's 192-byte descriptor list writes VCD/VAT directly, so the SDK's cached attribute layout is not authoritative. The parser reads those actual CP commands, including direct attributes, matrix bytes and three-index NBT normals. It accepts VAT0, as emitted by Sunshine's `J3DShape::makeVcdVatCmd`. It validates the entire geometry list before touching the FIFO. Triangle strips use three connected edge paths: adjacent vertices, even vertices and odd vertices. A three-vertex strip uses one closed path. These contain the same edges without drawing each shared edge twice. Fans and separate triangles retain their triangle edges; quads retain their perimeter. Existing lines, line strips and points pass through. All original vertex attributes and matrix indices remain unchanged.

The first `GXBegin` in each accepted list performs the same pending-state and flush preparation as `GXCallDisplayList`. Later primitive headers go directly to the FIFO: no material or graphics-state writes occur between them, so there is no further dirty state to flush. Larger contiguous vertex spans use aligned word loads with bounded byte prefixes/tails. Short unaligned vertex records retain byte assembly. Neither path reads outside the validated list.

Unsupported commands, other VAT selections, invalid layouts/counts, inaccessible memory and exhausted budgets fall back to the original display-list call. Limits are 1 MiB per list, 4 MiB of examined source packets and 16 MiB of expanded FIFO commands per frame. Line batches contain at most 60,000 vertices. There is no allocation, retained converted mesh, extra memory reservation, game asset modification, or gameplay/timer update. The extra CPU/FIFO work has not been measured on Wii.

`scripts/test_game_wireframe.py` runs the production parser, emitter and FIFO writer through 13 focused host tests. They cover attribute widths, actual J3D descriptors, exact edge sets including small and degenerate strips, unchanged attribute bytes, malformed tails before any output, exact budgets, the 60,000-vertex boundary and maximum strip size, one SDK preamble per list, and aligned/unaligned copies. The FIFO fixture replaces hardware ports with byte collectors and emulates big-endian aligned word loads on the host. The revised JP object compiles, adds 832 code bytes and adds no BSS or read-only table identities. Final integrated link and visual results belong to the tested build's separate receipts.

## PR14 feedback: measured work reduction

A PAL source-asset audit reads `SHP1` using the retail `J3DShapeBlock`, `J3DShapeInitData` and `J3DShapeDrawInitData` layouts. Plaza's `data/scene/dolpic1.szs` contains 106 BMDs with 317 matrix-group lists; `data/mario.szs` contains 26 BMDs with 61 lists. All 26,210 primitive packets in this sample are triangle strips. The production converter's emitted edge sets match the original triangles, comparing complete vertex records, for every list.

| One submission of each source list | PR14 FIFO bytes | Revised FIFO bytes | Reduction |
|---|---:|---:|---:|
| Plaza models | 2,812,440 | 1,683,338 | 40.15% |
| Mario models | 334,662 | 172,706 | 48.39% |

Line-segment submissions drop 21.69% and 25.48% respectively. SDK preamble calls drop from 26,210 to 378 across the sample. These are source-asset work counts, not a visible-frame trace or Wii frame-time measurement; culling and repeated model instances change per-frame totals. There is no cross-frame pointer/validation cache or new heap use. Private comparison evidence is in `build/pr14-wireframe-perf/comparison.json`.

## PR17: Wii freeze after closing the menu

The frozen PR16 PAL build reproduces the user's Plaza failure with Free camera Off. World resumes normally; switching to Wireframe while the menu is open and closing it stops the input-frame counter after three frames. Only the first 160-byte geometry list has reached conversion, with stride 6 and 267 planned output bytes. Dolphin reports invalid FIFO opcodes while the CPU remains inside `Fifo::bytes`. This is an unbounded copy, not a heavy-scene performance limit or a menu graphics-state conflict.

The production PPC compiler miscompiles the pointer-conditioned byte-alignment loop for addresses ending in `1`. The failing call reads 18 bytes from `0x80DD3475`: its prefix should contain three bytes. The generated loop instead initializes CTR with `(1 - address) & 3`, which is zero, then decrements CTR before testing it. It copies beyond the packet while the counter wraps through nearly four billion iterations, corrupting the graphics command stream. The stalled retail thread context and emitted PPC assembly agree on that address, length and loop.

The prefix is now counted explicitly as `(-address) & 3` before copying. Generated PPC initializes CTR with that count **plus one**, keeping it within 1–4, then copies the unchanged aligned words and tail. No descriptor, geometry, graphics-state or memory-reservation changes are needed. The compiled PAL copy helper shrinks from 352 to 340 bytes.

The controlled comparison under `build/timewarp-pr17-wireframe-runtime/` preserves the original PR16 ISO, source inventory and production-bootstrap hashes. `pr16-repro` contains the failing run and stalled MEM1 capture; `pr16-fixed` changes only this one function at its existing address, with its sole `read32` branch relocated to the original target. The fixed run passes World → Wireframe → menu reopen → Off in native Plaza gameplay, accepts stick movement and produces no invalid-FIFO or graphics-configuration errors. The 13 existing parser/emitter/copy tests also pass, including every source alignment and lengths 0–65. Those host tests alone cannot detect this PPC-only compiler fault. The combined PR17 build and real Wii confirmation remain separate checks.
