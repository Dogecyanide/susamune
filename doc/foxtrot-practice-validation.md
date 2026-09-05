# FOXTROT practice controls: implementation and validation

The module is `src/practice_session.cpp`. Its 64 KiB input take occupies the
PPC-only interval `0x91880100–0x91890100` on Wii, or
`0x71100100–0x71110100` in Dolphin. This reuses the old ghost file payload
space after its live 256-byte mailbox header and before the secondary model
heap at slot offset `0x6A000`. Protocol 4 moved ghost files to a separate bank.
Console Record and Replay require that protocol's header magic and version;
they work even when SD storage is unavailable. Pause and free camera do not
depend on this storage capability.

The tape owns complete 32-byte cache lines and has no ARM reader or writer.
Only initialized samples up to the current count are read; stage setup
invalidates that count without clearing unrelated mailbox or model memory.
The move frees 65,536 bytes of mod BSS capacity. The requested 768 KiB MEM1
reservation remains unchanged. Two 236-byte controller histories and under
512 bytes of camera view state remain in MEM1. No heap is allocated and no
timer source, callback or clock is changed.

## Gameplay hold and Step

Hold borrows the existing state-12 director gate. The retail movement and
animation cues are disabled in that state. `TMarDirector::movement()` calls
`movement_game()` only in state 4, verified against all three retail binaries.
The module also suppresses the director's collision-check and collision-clear
calls while holding. UI, rendering, audio stage service, the director budget
and its unconditional counter continue. Absolute-time deadlines continue.

Step releases one ordinary director update, then holds again. This is a
display-frame workload, usually four 120 Hz logic ticks at 30 frames per
second, with the retail fractional budget at 25 frames per second. Screen
refresh rates of 60/50 Hz are distinct from that 30/25 fps game workload.
It is not one QF or an emulator pause.
The configured Step/Resume combo is removed from the gameplay sample,
including an associated analog trigger; the remaining controller input is
decoded normally. With free camera active, a step uses neutral gameplay input.
Step is the explicit subset-match exception to exact action binds: holding
extra gameplay buttons still allows the configured Step combo to fire. Menu
Step/Resume waits for A to be released before gameplay advances. Retail
director results 0 (WAIT) and 1 (DEFAULT) both continue the current scene.

## Free camera

Free camera works with practice hold or ordinary retail pause. The main stick
moves, C-stick looks, L/R change height, and X moves faster. The initial view
uses the retail final eye and target, including camera interpolation.

The camera wrapper uses retail render cues 4 and 16. Those cues copy cached
matrices; they do not rebuild them from the base eye and target. The wrapper
therefore saves the camera's render state and rebuilds its projection and
look-at matrices before those cues. It restores the gameplay camera before
collision, movement, subsequent pad sampling, and after the director returns.
Stage generation and pointer checks prevent stale camera restoration.

## Local input takes

Save a normal gameplay state first. Record and Replay both reload that same
existing slot after the GX barrier, after the menu closes and physical buttons
are released. A busy card operation waits at most 600 rendered frames. The
take contains at most 4096 samples: approximately 136 seconds at 30 fps or
164 seconds at 25 fps. Replacing the slot or entering another scene invalidates
its seed. The take is local to this running session, not an SD replay file.

Each sample contains the 12-byte controller packet and a diagnostic
fingerprint of Mario's position, speed, state, health, RNG seed and coin count.
Playback stops and holds on its first mismatch. Settings, display cadence and
controller normalization must match. B or Start aborts playback. Menus,
cutscenes, disconnects and fast-forward end the current input session.
Matching fingerprints do not prove full-world deterministic replay: audio,
asynchronous services, absolute clocks and uncaptured system state remain
outside the seed. Assisted practice never becomes an eligible PB.

## Retail evidence

`scripts/audit_practice_hooks.py <directory>` checks `jp.dol`, `us.dol` and
`pal.dol` without modifying them. It verifies the relocated entry instructions,
the state-4 movement gate, camera vtable slot, render cue/matrix instructions,
normalization mode, and exact collision branch destinations and unique callers.
All checks passed for the supplied binaries on 2026-09-05:

| Region | SHA-256 |
|---|---|
| JP | `4fa5b5f816a939ee1dcab7a98296120d92e2b7b091bcc21ab2850975f54af7f2` |
| US | `13934c863d649b1ddca1ca4d7748f49d28a571685cbee5fb1542545c32869955` |
| PAL | `c0a22ed5847b779a31e8e54ca10aa9b38c378d36b1ed37a775b0bab594be9bca` |

The companion decomp's [director loop](https://github.com/doldecomp/sms/blob/9b62e09d59340d87b77be5a38d875a8914b2d627/src/System/MarDirectorDirect.cpp)
describes the retained phases. Camera implementation is incomplete upstream;
the matrix and render-cue decisions above were verified from all three retail
binaries, not inferred from a JP-only camera implementation.

## Smoke-test scope

Tests on 2026-09-05 used isolated profiles under `build/foxtrot-smoke`, the
user's own disc images, and privately copied BPS-patched images. The controller
fixture replaces only the retail US `PADRead` call at `0x802C8BB8` with a NOP
in that private copy, then feeds raw controller packets to the normal JUT
decoder. This fixture is absent from release images. Captured symbol tables
identify each running build; memory samples are taken from the owned process.

Live US Bianco Hills checks established:

| Check | Result |
|---|---|
| Hold with A and the main stick held | Mario's position remained unchanged. |
| Three separate Step presses | The practice counter advanced exactly three times and returned to hold after each press. |
| Step with A and the main stick held | The subset binding advanced once and Mario began a jump. |
| Free camera during hold and retail pause | The camera view changed while Mario's position stayed fixed; retail pause remained state 5. |
| Save, move, then load | Mario returned to the exact saved position. |
| Record and replay | All 330 recorded diagnostic fingerprints matched on playback; playback then held. |
| Deliberate mismatch | A private test changed Mario's X by 100 at cursor 13; playback stopped and held at frame 14 with the divergence message. |
| Warp while holding | The wheel accepted the destination and released the practice hold so departure could proceed. |

The 330-frame take and deliberate-mismatch evidence are in
`build/foxtrot-smoke/live-replay.json` and `live-divergence.json`; those checks
used Dolphin 5.0 JIT and the preceding `FF1C16BC` image. They demonstrate this
particular take and the mismatch detector, not full-world determinism.

US image CRC `5F9FF69D` was then checked in Dolphin 2606a JIT.
`build/foxtrot-smoke/final-current-jit-smoke.json` records held menu input,
Step with A, camera activation without movement from the enabling combo,
camera/menu input handoff, camera movement during hold and ordinary retail
pause, and a completed warp from hold. The warp advanced stage generation
from 2 to 3 and returned to normal gameplay state 4. Menu ownership remained
true in every one of 20 samples for both handoff checks; decoded C-stick input
was observed across rendered frames. A temporary zero in decoded input within
a frame is expected when the wrapper suppresses retail gameplay controls.

The `14403536` image includes a child-page focus fix found during pixel
capture. Holding A for 1.2 seconds when entering frame controls leaves the menu
open and practice live. Releasing A and pressing it again pauses. The captured
640×480 control pages show all seven rows, the local take count and help text
without overlap. Evidence is under `build/foxtrot-visual`.

The same image recorded and replayed a fresh 68-frame moving/jumping
take with all fingerprints matching and the identical ending position. It
also passed held-menu input ownership in 20/20 samples and one Step with A.
`build/foxtrot-smoke/optimized-current-jit-replay.json` records these checks.

Image `0391BB7B` adds a shared child-page release guard for both raw-
and decoded-input pages. Held-A captures confirm that entering frame controls
or Creation does not activate a row. The guard also suppresses action binds
until release and skips the release callback before handing input to the page.
`scripts/test_nested_menu_focus.py` exercises these behaviors, stale decoded
input, protected entry and the next fresh Back press.
Final captures also show pause/camera notifications taking priority over the
practice banner, which returns after the notification expires. Clean native
timer captures use +60 X, -40 Y and 140% scale with the input overlay hidden;
the draw path reports 18 panes. Camera movement leaves Mario's exact position
unchanged. Final capture evidence is under `build/foxtrot-visual`.

The final settings fingerprint loop uses the identical unsigned FNV byte step
directly. The compiled loop drops 126 helper calls per recorded/replayed frame;
the cadence and stick-mode suffixes retain their original code and read order.
Comparison covered 526,080 single-byte cases, all 65,536 two-byte streams and
32,848 full settings/cadence/mode streams. The function also shrank by 44 bytes
and uses a 32-byte stack frame instead of 48. Evidence is under
`build/optimization`.

Dolphin 5.0 JIT has a reproducible held-menu/warp input failure with the
untraced `4D9B651E` image: controller ownership can read false despite an open
overlay, and decoded input stays stale. The **same exact image** works in
Dolphin 5.0 Interpreter and official Dolphin 2606a JIT. Both correctly retain
modal ownership and decode held C-stick input. The interpreter also passed
Step with A held and warp release while holding. No speculative controller
logic change was made to mask the old JIT discrepancy. The temporary tracing
code used to investigate it has been removed.

An earlier Dolphin 5.0 host crash also occurred with the previous V2.2 mod.
The captured fault was a paired-single matrix load from the menu's J2D object
in FakeVMEM. Keeping the 440-byte Menu object in MEM1 on emulator builds
resolved that crash; the remaining menu runtime stays in its reserved bank.

Additional Bianco 1 captures show the rendered camera moving while Mario's
recorded position remains fixed, and native timer position/scale changes.
These sampled views do not cover every enemy/water interaction, controller
edge case, stage or Wii hardware behavior. No Wii result is claimed. Audio, rendering,
absolute clocks and asynchronous services continue during practice hold.
