# Moonshine subsystem map

Current development line: 3.0.0, PR27. Ownership below means code responsibility,
not an assigned person. This is the entry point for human contributors across
the project; detailed formats remain in their shared headers and linked docs.

## Three execution environments

* **Game PPC:** injected hooks, practice logic, UI, capture and playback. The
  live game owns its object lifetimes. Per-stage pointers expire at teardown or
  savestate restore. Hot work must remain bounded and must not wait for storage.
* **Nintendont ARM:** Wii file/network service. It owns FAT and asynchronous IOS
  operations. Mailbox cache lines have one writer each; never reuse a buffer
  while an operation may still reference it.
* **Dolphin host companion:** currently implements the online mailbox only.
  It is not a Wii ARM kernel and does not provide the saved-ghost/state/TAS
  library backend. Settings have their separate emulated memory-card path.

`src/main.cpp` coordinates startup, before-direct work, the retail director,
after-direct work and post-GX restore. It should call owners rather than acquire
new feature state. `onSetup` is not early boot; settings needed by logos/title
must be initialized through `onAppInit`.

## Where to change a feature

| Area | Owner / public contract | Main dependencies and useful checks |
|---|---|---|
| Boot, hooks, memory | `main.cpp`, `scripts/patches.py`, `addresses.hxx`, `mem2_map.h` | `link_pinned_mod.py`, `timewarp_timer_guard.py`; all six regional/environment links |
| Warps / stage lifecycle | `warp_wheel.cpp`, `warp_wheel.hxx`, `iling.cpp` | Two-phase arming then departure; `test_paused_warp_departure`, `test_iling_attempt_lifecycle` |
| Practice speed, frame advance, free camera | `practice_session.cpp`, `retail_input.cpp`, `slowdown_bind.cpp` | Retail input ownership and camera hook order; `test_slowdown_bind`, `test_camera_hook_chain` |
| TAS editing / seeking | `tas_project.cpp`, `tas_scrub.cpp` | State leases, replay/checkpoint identity, assisted-run status; `test_tas_menu`, `test_tas_storage_kernel` |
| Savestate capture / restore | `savestate.cpp`, `state_store.cpp`, `state_codec.cpp`, `state_quick_replay.cpp` | Preserve hardware-owned state and GX barrier; `test_state_store`, `test_state_codec`, `test_state_quick_replay` |
| Named states / sharing | `state_storage.cpp`, `state_import.cpp`; ARM `SusamuneStateStorage.c` | `state_work_lease.cpp`, `transfer_lease.cpp`; `test_state_import_pipeline`, `test_state_storage_kernel` |
| Ghost recording / Watch | `ghost.cpp`, `ghost_scrub.cpp`, `ghost_camera.cpp`, `ghost_camera_track.cpp`, `ghost_path.cpp` | Observer lifetimes, scene segments, independent playback cursors; `test_ghost_initial_rng`, `test_ghost_takeover`, `test_ghost_path` |
| Ghost visuals | `ghost_model.cpp`, `ghost_fludd.cpp`, `ghost_water.cpp` | GPU-visible model memory and immutable asset masters; `test_live_ghost`, `test_ghost_format`; actual rendering checks |
| Ghost files / library | `ghost_storage.cpp`, ARM `SusamuneGhost.c`, `ghost_format.h`, `ghost_storage.h` | [Format](ghost_format.md), `validate_ghost.py`; `test_ghost_storage`, `test_ghost_storage_paging` |
| Timers / splits / eligibility | `qft_timer.cpp`, `split_events.cpp`, `split_stats.cpp`, `iling.cpp`, `hoverless.cpp` | Protected timing code; displays read results rather than replacing measurement; timer guard and applicable lifecycle tests |
| Playlists / streaking | `stage_loader.cpp`, `stage_targets.cpp` | Completion/report ownership before departure; online playlists advance independently |
| Records / persistence | `records.cpp`, `records_persistence.cpp`, `settings.cpp`, `settings_emulator.cpp` | ARM `SusamuneCfg.c`, shared config header; `test_creation_persistence`, `test_storage_retirement` |
| Binds / practice codes | `binds.cpp`, `actions.cpp`, `features.cpp`, `feature_binds.cpp` | Append-only lists, raw controller edges and modal ownership; [porting guide](gecko_porting.md) |
| Menu / search / artwork | `menu.cpp`, `menu_search.inc`, `menu_theme.cpp`, `menu_native_icon.cpp` | No per-frame heap allocation; `test_menu_search_enumeration`, `test_menu_native_icon`, `test_online_menu_routes` |
| Creation / HUD styling | `creation.cpp`, `creation_extras.cpp`, `layout_editor.cpp`, `gradient_motion.cpp`, individual display owners | Shared editor, per-feature persistent styles; `test_creation_menu_routes`, `test_creation_persistence`, `test_gradient_motion` |
| Collision / wireframe | `practice_visuals.cpp`, `game_wireframe.cpp` | GX state restoration, stage geometry lifetimes; runtime tests with/without free camera |
| Online match | `live_race.cpp`, `live_group.cpp`, `live_group_rules.cpp`, `live_draft.cpp`, `live_playlist.cpp`, `live_invites.cpp` | [Start reservation](online-start.md), [guest invitations](online-invites.md); `test_live_race_match`, `test_live_group`, `test_live_race_join` |
| Online transport / smoothing | `live_race_session.cpp`, `live_transport.cpp`, `live_ghost.cpp`; ARM `MoonshineNet.c` | `test_live_p2p`, `test_live_ghost`, `test_moonshine_net_worker`, `test_dolphin_live_transport` |
| Release / distribution | `scripts/release_prerelease.py`, `package_timewarp_dolphin.py`, launcher super-build | Source receipts, protected-code guard, fixed-memory checks, ZIP and SD readback |

Paths without a directory above are under `src/` for implementations and
`include/susamune/` for mod contracts. ARM files are in `launcher/kernel/`.
Tests are `scripts/test_*.py`. Before running a listed suite on another branch,
check that its filename still exists; update this table when moving an owner.

## Contracts that cut across features

**Reservations and ownership:** the memory map is authoritative. Fake Dolphin
VMEM can hold CPU data but is not automatically GPU-readable. Wii PPC/ARM cache
ownership and in-flight I/O retirement are part of correctness, not optional
optimization. Savestates must not restore OS queues, CARD threads or live audio
handles. A restore can invalidate model/observer/online pointers.

**Persisted identity:** setting and bind ordinals are append-only; labels may
change without changing stable keys. A file format version, storage mailbox
version, online wire protocol and release number are different contracts.
Do not infer one from another. Current ghosts are SGHF V9; racing uses MSR V5
after PR27's stronger Ready contract. Check the header when changing either.

**Timing:** QFT and official eligibility are authoritative. Cosmetic display,
ghost playback, online clocks and website metadata must not silently alter
them. Online wall-time additions belong to online results only. Ghost RNG is
recorded metadata; it is never applied while racing a ghost.

**Asynchronous state:** requests carry generation/sequence/identity tokens.
Do not clear a waiting request because a frame changed, reuse shared scratch
before retirement, or treat a queued request as successfully completed.

**Region support:** wire regions use JP=0/US=1/PAL=2, which differs from some
build identifiers. Use conversion helpers. All game addresses and font glyphs
must be checked regionally. Portable ghost transforms do not make raw memory
savestates portable between regions or incompatible builds.

## Next maintainability steps

The shared release entry point, environment check and owner map are implemented
in PR27. The project is not fully refactored. Next, extract one coherent owner
at a time from `menu.cpp`/`ghost.cpp`/`iling.cpp`, keeping public contracts and
before/after fixtures. Replace source-sliced native fixtures with whole compiled
modules as those modules gain independent interfaces. Keep hardware acceptance
results alongside releases, and retire obsolete notes only after current
invariants have a durable home. Avoid one sweeping formatting/refactor change
across rendering, timing, storage and online.
