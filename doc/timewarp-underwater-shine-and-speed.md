# Underwater shine release and practice speed

## No Shine Get Animation

The old `winDemo+0xAC` cave wrote ground idle (`0x0C400201`) directly into Mario's status.
Retail `TMario::changePlayerStatus` explicitly refuses that status in diving maps, where its accepted statuses are Taken, underwater movement (`0x891`), and the shine demo.
The source reference is `build/reference-sms/src/Player/MarioMove.cpp`; `System/StageUtil.cpp` identifies map IDs `0x39`, `0x2C`, and `0x10` as diving maps.
Those include the underwater Noki scenarios reported by the user.

The existing six-word release cave now calls a small C helper.
On diving maps it calls the retail forced transition to underwater movement, including the normal previous-status/substate initialization.
Elsewhere it preserves the previous idle and substate/timer writes.
The shine touch, shine collision reset, attempt publication, and QFT caves are unchanged.
No hook site, cave size, or memory reservation changes.

`test_underwater_shine_release.py` executes the production helper in a host fixture and checks land/underwater behavior.
It also audits the saved LR, callee-saved Mario pointer, release instruction, return path, and exact diving predicate against the user's JP/US/PAL retail DOLs.
All three tests passed, and `features.cpp` compiled for all three regions.
The user subsequently confirmed on Wii with Prototype 8 that the underwater shine crash is fixed.

## Gameplay speed

`Gameplay speed` is append-only setting 151 in Practice tools.
It supports every integer percentage from 1 through 100; persisted zero means normal 100%, and 1–99 store their displayed percentage.
The existing settings tail and runtime reservations have capacity for it.
The new setting participates in the normal INI key table; a fresh launcher build is needed to persist its key.

Prototype 9 opens a three-digit editor when Gameplay speed is selected with A,
including from Shined. D-pad Left/Right chooses a digit, Up/Down changes it,
A/Start commits 001-100%, and B cancels. Values remain untouched until a valid
commit. The modal waits for the opening buttons to be released, owns its input,
and cancels a stale draft when its tab is focused again. Category tabs remain
eight bytes and the editor allocates no heap. Four executable host checks cover
the release gate, deferred commit/cancel, bounds/100% encoding, and modal ownership;
the new source and menu compile with the PAL production flags.

The scheduler distributes whole gameplay frames with a bounded integer accumulator.
At normal speed its fast path does not hold gameplay or mark an attempt assisted.
At lower speeds, the existing practice freeze keeps rendering and networking serviced and uses the existing QFT practice-pause interface.
The ordinary timer implementation and hook bytes are not edited.
Manual pause/Step, free camera, menus, load holds, stage transitions, unavailable hooks, and fast-forward take precedence.
Only ordinary controllable gameplay is slowed; loading and cutscenes retain their normal cadence.

The existing input-history release handling is retained.
Short digital-button and analog-trigger presses during skipped frames are delivered once on the next simulated frame.
Replay owns its recorded inputs; physical taps are not merged into replay.
Menus, ownership changes, stage setup, savestate load, speed changes, and warps clear pending taps.
This is a bounded one-frame latch, not a queue of multiple taps.
Movement axes use the latest sample; the spin history extension below also retains skipped stick directions.

Using slowdown latches the existing assisted-attempt flag and invalidates ordinary IL, global, and ghost records.
Returning to 100% cannot requalify the attempt.
The setting also blocks IL PB eligibility and therefore competitive online results, including when it is enabled and disabled entirely while a menu is open.

Ten focused host tests passed: all 1–99% cadences over 1,000 frames each, owner/hook guards, short-tap delivery, held-button/replay behavior, normal-speed restoration, lifecycle reset calls, call ordering, and sticky IL ineligibility while a menu is open.
The existing 45 load-hold/Step/transition tests passed after adapting their fixture to the new optional scheduler call.
Practice and settings sources compile for JP/US/PAL.
The user subsequently confirmed on Wii with Prototype 8 that slowdown works well, while requesting normal-speed stick spinning during slowed gameplay.
That confirmation does not individually establish every pause/Step and transition combination.

The slowdown extension is appended outside the original practice module's
fixed text/BSS sections. Main runs input preparation, the original
`beforeDirect`, then slowdown application. If slowdown freezes that frame,
the extension retains the original paused-release bookkeeping. Stage setup,
savestate restore and warp reset pending speed inputs explicitly. This keeps
the original code/data and timer dependency anchors in place; the protected
link must verify that invariant before packaging.

## Spin input during slowdown

Retail already reads the controller and runs `TMarioGamePad::updateMeaning` on every rendered frame.
The missed inputs came from `TMario::makeHistory`, which records stick angles only when gameplay advances.
The references are `System/Application.cpp::gameLoop`, `System/MarioGamePad.cpp::updateMeaning`, and `Player/MarioMove.cpp::{checkController,makeHistory,checkStickRotate}` in the decomp.
`MarioInit.cpp` allocates 60 signed angles; the ordinary rotation window is 24 frames, retaining at most 23 recent angles.

The extension keeps a private, bounded copy of that history while frames are skipped.
It samples the retail compensated axes at pad offsets `0xA8` and `0xAC`, applies the native integer deadzone and sinking scale, and calls the regional retail `matan` with the current camera yaw.
It publishes those samples immediately before the next simulated frame, when native history recording and spin/jump decisions resume.
It does not call Mario's controller, physics, action, or animation updates on skipped frames.
The private state costs 132 B on PPC, with no allocation or reservation growth.

The user's explicit constraint is that normal gameplay remains unchanged outside slowdown.
At stored zero (100%) or values at least 100, the scheduler returns before the spin helper, discards private queued samples and taps, and never reads or writes Mario's spin history.
It never changes the retail rotation-window parameter or patches the retail spin recognizer.
Returning to 100% leaves the current native history intact and cannot publish stale skipped inputs.

Menus, manual pause/Step, load holds, setup/load/warp resets, owner changes, and unavailable controls discard private history without restoring old bytes into game RAM.
TAS recording/replay and ghost observation retain the previous sampling behavior, because the tape records simulation samples only.
The extra sampler also declines dizzy input, whose angle perturbation belongs to Mario's gameplay update, and refuses invalid history pointers/counts/limits.
Neutral stick clears the private window, and old directions age out at the native rendered-frame window; completed gestures are not queued indefinitely at very low percentages.

Seventeen focused production-code host tests passed after this change.
These include a complete fast stick revolution between gameplay updates, retention windows at 1/10/25/50/99%, native real-frame appends, deadzones/sinking/camera-relative angles, ownership/lifecycle guards, sticky assistance, and zero native-history/input mutation at 100%.
The host math stub uses the exact tested cardinal/diagonal results of Sunshine's `matan(z,x)` convention; arbitrary angles still use the retail function in the mod.
The PAL source compiled, and the object comparison preserved all bytes, symbols, offsets, and sizes of the four original `.foxtrot` practice sections, including the 28,064 B text and 1,888 B BSS owners.
New float constants add 20 B to this source's anonymous numeric pool; the existing `cameraStick` relocations move by that amount but still identify the same values.
No timer dependency anchor acquires a changed relocation.
See `build/timewarp-practice-owner-probe/speed-spin.json` and `build/timewarp-speed-spin/receipt.json` for the source-bound evidence.
This narrow object proof is not a replacement for the final all-region protected link, and the new spin behavior still needs Wii testing.
