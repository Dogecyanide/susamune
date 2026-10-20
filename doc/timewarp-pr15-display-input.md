# Prototype 15: display and shortcut feedback

The metadata page now places Layout, Horizontal gap, Value widths, Row gap and Fields per row beside its style editor. Existing persisted values and defaults stay intact. Compact widths remove unused maximum-digit padding; Horizontal gap controls the remaining inter-field spacing from 0 to 32 pixels. The previous controls existed but sat below all field toggles and Reset, making them easy to miss.

Both timer editors have Gradient direction. Horizontal retains per-character colours. Vertical interpolates top to bottom through the existing first and last colours; Sunshine uses normal digit 1/6 and countdown digit 1/4, and compact QFT uses its first/last character slots. The existing presets choose these endpoints. Vertical does not reproduce intermediate horizontal rainbow stops. Sunshine's TIME image and background remain separate. Native drawing temporarily sets corner colours, keeps the black outline/shading through the red-channel texture mapping, and restores all corner colours, texture colours and TEV swap state immediately after each picture draw. There is no gameplay timer calculation change.

X+A inside any scalable Creation editor opens the numeric size editor, preserving X+Start's previous-colour-target shortcut and L/R's quick size steps. It uses the same three-digit controls as slowdown: D-pad left/right selects a digit, up/down changes it, A/Start accepts and B cancels. Display size is exact percentage rather than an assumed font pixel size; mixed displays use different native glyph sizes. Standard bounds are 50–200%, and finish breakdown respects its serialized 25–150% bounds. Cancelling the outer Creation editor restores the original scale too. Streaking's Finishes row opens this numeric editor with 1–999; its existing backend goal is 16-bit. Target-time editing keeps its existing time keyboard.

Button binds has a Feature toggles submenu containing 12 new, initially unassigned shortcuts: Fast text, FLUDD in secrets, Area lock, Infinite juice, Nozzle lock, Stage intro skip, No shine get animation, Fruit never times out, Mute background music, Shadow Mario HP meter, Unlock Yoshi and Unlock nozzles. Booleans toggle; FLUDD and nozzle choices cycle through the same options as their normal setting. A toast states the selected value. Exact button-combo edges prevent repeats while held. Existing modal/action ownership applies, and the shortcuts do not fire while the menu is visible. Settings/binds append within the existing fixed capacities; no region/version remapping or memory reservation change.

The jump display no longer suppresses WallkickDisplay::draw. Each enabled overlay draws independently.

Validation includes production Creation input and cancellation, native timer corner/outline/swap restoration, metadata packing and persisted fields, grouped menu routes, feature shortcut ownership/edges, shared numeric entry bounds and the Streaking entry/commit/cancel path. JP target objects compile; combined region linking and Dolphin/Wii rendering remain root-owned checks. No broad unrelated test suite was run.

An animated gradient is feasible as presentation-only palette updates on these same draw paths. A shared phase plus a bounded palette calculation could avoid new recording data and large buffers. It still needs visual/performance validation and motion-speed controls; no animation was implemented because the request was hypothetical.

The compact timer's protected draw function and its existing Menu drawing dependencies retain their original bytes and addresses. Vertical colouring is selected in the shared text presentation helper only when it receives QFT's own colour array; other displays retain their horizontal colours. The vertical primitive has its own code section, and the editor retains its selected-character arrow. Three focused renderer tests and six existing QFT/TAS layout tests pass.

Console packaging retains 46 explicitly named, already-audited new CPU functions in existing MEM1 holes. This allows the boot container to compress those bytes instead of executing their uncompressed copies from the staged cold image. The list is restricted to `NEW_MODULES`, checked for exclusive complete-function ownership and absence of protected/baseline overlap, and applies only to console builds. Emulator selection and its tested binaries remain unchanged. No runtime source, timer baseline, memory reservation, file format or decompressor changed for this packing adjustment.

The selected functions total 7,492 bytes. Final relocation and gateway changes reduce the JP boot container from 551,680 to 547,616 bytes, saving 4,064 bytes and placing it 1,248 bytes below its 548,864-byte ceiling. All three console links and the production native installer check passed:

| Region | Container bytes | Boot headroom | Unallocated bytes in recovered MEM1 ranges |
|---|---:|---:|---:|
| JP | 547,616 | 1,248 | 617 |
| US | 543,648 | 107,616 | 642 |
| PAL | 543,392 | 107,872 | 681 |

Each link preserves all 96 timer symbols, five protected strings, nine dependency anchors and 34 retail hook writes. The final check is recorded in `build/timewarp-pr15-feedback-console/console-check-receipt.json`; host installation checks do not establish Wii boot/reset or cache execution.
