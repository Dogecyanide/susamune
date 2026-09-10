# Sunshine: two memory states and SD states after reboot

**Implementation update:** the current source implements three compressed memory
slots, a menu selector and an optional unassigned Cycle states bind. Replacement
must fit before any occupied slot is changed; nothing is automatically evicted.
Each slot owns its QFT/IL data, and replay pins its original slot and generation.
The staging audit is complete; see [the codec audit](foxtrot-state-codec.md).
SD archives and guarded reboot restoration are now implemented; see the
[SD-state implementation and test evidence](foxtrot-sd-states.md). The optional
2 MiB pool extension is gated on launcher capability. A fresh-process Dolphin
restore passed with exact position, QFT and full-level ghost prefix; real SD/Wii
restoration remains a hardware test. The investigation below records the earlier
single-state build and the evidence behind this work.

Original feasibility investigation, 2026-09-08. At that investigation's end no
SD feature was implemented; the later implementation is documented above.
The DarkMoonshine project was left unchanged. A private Sunshine snapshot was
captured during the input-fix smoke test for the compression measurement below.

**Recommendation:** reboot-persistent Sunshine states are a credible feature,
and DarkMoonshine provides reusable, hardware-exercised SD storage machinery.
Two memory states are also a credible goal using compression. Two raw states
cannot simply be placed into the current memory map. Neither feature
is ready by copying the existing Sunshine snapshot to a file.

## What DarkMoonshine actually has

The active implementation is under
`C:/Users/Dogec/Documents/ChatGPT/Luigi House/Moonshine-Luigis-Mansion/lm_diag/`,
not that repository's inherited Sunshine `src/savestate.cpp`. Its working tree
has extensive uncommitted changes; this report describes the files inspected,
not just Git HEAD `acc4cf814c0b1a0f1faead6303909d357aaeda74`.
Paths prefixed **LM** below are relative to that repository.

- Current code uses snapshot format **27**, storage protocol **6**, and
  **one** resident state: LM `lm_diag/src/lm_state.cpp:165`,
  `include/susamune/lm_state_storage.h:7`, and
  `lm_diag/src/lm_state_storage.inc:3`. The older storage document's 25/5
  heading and original cross-boot plan are historical.
- Reboot support has real user evidence. LM `doc/lm-current-priorities.md:9`
  records successful .42 same-session, soft-reset and full-power-cycle tests;
  line 50 records the .43 cold-boot baseline pass. Later room transitions
  exposed missing fixed owners, corrected in .43/.44. RC1's record reports
  no observed .44 crashes but retains a guarded Secret Altar load limitation
  (LM `doc/darkmoonshine-1.0.0-rc1-verification.md:6`). This supports a bounded
  working feature, not universal cross-scene compatibility.
- SD export writes a fresh numbered archive through a temporary file,
  sync/close and rename. Import transfers at most 16 KiB per service pass,
  into a fixed admitted destination. A compressed backup preserves the old
  memory state on import failure. The browser, names, exact operation receipts,
  and fresh process sessions are reusable designs. See LM
  `launcher/kernel/LmStateStorage.c:617`,
  `include/susamune/lm_state_storage.h:47`, and
  `lm_diag/src/lm_state_storage.inc:378`.
- Persistent archives also bind exact build, game, configuration, a durable SD
  key, payload integrity and a saved resource-owner profile. Import checks
  those; gameplay load repeats live owner/audio checks. See LM
  `lm_diag/src/lm_state_storage.inc:439` and `:535`,
  `lm_diag/src/lm_state.cpp:3786`, and
  `include/susamune/lm_persistent_profile.h:13`.

The portable transaction tests execute production client/kernel/codec logic,
but explicitly use a synthetic game snapshot fixture. They complement the
hardware evidence rather than replace it: LM
`scripts/test_lm_state_transactions.py:1`, `:137`, `:314`,
`scripts/test_lm_state_keys.py:177`, and
`scripts/test_lm_persistent_profile.py:112`. These tests were inspected, not
rerun during this read-only feasibility pass.

## Two states in memory

The current snapshot reservation is **15.9375 MiB**, from `0x91F00000` to
`0x92EF0000`; the next 64 KiB belongs to settings and live mod state, followed
by the kernel. Source: `include/susamune/mem2_map.h:95`.

An existing US Dolphin stage sweep measured **14,918,784 bytes / 14.23 MiB**
of stage payload alone, before the heap object and captured statics
(`build/foxtrot-smoke/stage-sweep-results.json:42`). This is an earlier build's
measurement, not a current all-region maximum. Nevertheless, two such payloads
already need **28.46 MiB**. Splitting today's reservation in half cannot work.
Sunshine currently copies the entire heap extent, including free space
(`src/savestate.cpp:459`, `:581`).

| Candidate memory | Assessment |
| --- | --- |
| Existing 15.9375 MiB state window | Owns one raw state today; could instead hold bounded compressed states. |
| SegaBoot/DIMM `0x91300000..0x91700000` | Potential 4 MiB Sunshine-only reuse after loader/IPL handoff. Requires explicit runtime ownership and reset checks; currently reserved. |
| Unused suffix of `0x91900000..0x91B3F000` | At most about 2.246 MiB, less the aligned live patch count/table. The used prefix is reread on reset and must remain immutable. |
| ARAM, disc/DI buffers, ghosts, mod staging, config/kernel | Already owned; not spare state space. |

Even reclaiming both candidate areas in full gives only **22.18 MiB**, still
less than two observed raw stage payloads. DarkMoonshine's published-unused-
suffix scheme can guide ownership, but Sunshine's patch tail is smaller because
ghost input/file banks occupy it. See `launcher/mem_map.txt:8`,
`launcher/kernel/DI.c:157`, `launcher/kernel/Patch.c:3905`, and LM
`include/susamune/lm_state_storage.h:140`.

The practical next step is measuring compressed Sunshine states across regions
and demanding levels, including time to save and switch on Wii. Then choose
either two compressed states or one raw state plus a compressed second state.
Reserve codec scratch and transactional replacement space explicitly. A save
that will not fit must leave both previous states intact. Do not promise a
compression ratio, instant switching, or universal two-state capacity from the
Luigi measurements.

A real US Bianco 1 snapshot from the input-fix smoke test (image `869DE501`)
contains **14,986,692 bytes** across 18 regions. The current DarkMoonshine
`LmStateDeflate`/`LmStateInflate` implementation and its vendored miniz packed
it to **5,015,626 bytes**, or **33.47%** of its raw size. Both the production
decoder and Python zlib restored the exact original bytes. Two equally sized
compressed samples would take **10,031,252 bytes**, plus the **327,680-byte**
codec workspace and any transactional replacement storage.

Three equally sized samples would take **15,046,878 bytes**. Adding the codec
workspace leaves **1,337,122 bytes** within the current reservation, before
other slot metadata and recovery storage. Three compressed slots are therefore
plausible with a different storage/restore design and per-save capacity checks,
but this sample alone does not establish a reliable three-slot configuration.

This is promising evidence for two compressed slots, not a worst-case capacity
or Wii speed guarantee. It measures one actual emulator scene using a native
host build of the codec. Other stages, regions and bus/cache costs still need
measurement. The private snapshot contains retail game memory and is excluded
from the repository and release ZIPs. Reproduction and results stay under
`build/foxtrot-held-input/measure-compression.py` and `compression.json`.

There is also a correctness issue independent of space: Sunshine's QFT and IL
attempt backups are singletons outside the captured game bytes. They must be
stored with each slot, alongside any practice replay seed association. Otherwise
loading slot A can restore slot B's timer/attempt. See `src/qft_timer.cpp:85`,
`:1020`, `src/iling.cpp:2274`, and `src/practice_session.cpp:765`.

## What Sunshine needs for reboot-persistent SD states

1. **A complete versioned archive.** Add exact mod/disc/config identity,
   full scene identity including secret/boss parent episode, checksums and
   explicit gameplay/mod sidecars. Today's format 13 only records region,
   area/episode, heap geometry, feature state, OS time and copy ranges
   (`src/savestate.cpp:232`). Its version check is not an exact-build check.
2. **A proof for retained Sunshine objects.** Matching numeric heap addresses
   is necessary, but not sufficient after reboot. The current copy includes
   the heap object with its OS mutex and JKR links, whole gamepad objects and
   `TApplication` pointers to live display/archive objects. Split captured
   gameplay fields from retained system ownership, and validate or rebuild
   known links against the fresh boot. See
   `include/JSystem/JKernel/JKRHeap.hxx:50`,
   `include/SMS/System/Application.hxx:46`, and `src/savestate.cpp:205`.
3. **Resource and worker admission.** Initialize the destination scene normally;
   account for shared archives, root allocations, audio owners and resources
   outside the stage heap. Keep fresh OS/DVD/GX/ARAM/audio services. Preserve
   the existing card/GPU barrier and add proved resource/audio quiescence.
   DarkMoonshine's successful reboot fix needed a specific MissionMode archive
   owner, not a relaxed pointer check (LM `doc/lm-map-archive-owner.md:8`).
4. **Clock and assistance continuity.** Serialize QFT/IL state explicitly;
   reset or bind replay seeds to the imported state. Audit absolute deadlines
   against the new uptime. Sunshine already rebases one mission stopwatch
   (`src/savestate.cpp:719`); that is not proof that every clock is covered.
5. **Safe file transactions.** Port the bounded worker, cache-line ownership,
   temporary-file export, full pre-restore validation, and old-slot rollback.
   Use a distinct Sunshine folder/format; do not read or repurpose LM archives
   or keys. A surviving file and a successful import are separate from a
   successful gameplay restore.

Start with the **same build, same region, same launcher setup, same fully
loaded scenario**. After a full power cycle, verify import/load, movement,
another load, and a normal exit/re-entry, including audio, controller and timer
behavior. Refuse unsupported topology before writes. Cross-region,
cross-build and arbitrary-scene restoration should be separate later work.

This is a substantial but supported path: DarkMoonshine supplies much of the
SD machinery and a useful model for proving what stays live. Sunshine needs its
own capture and object-lifetime work before the feature can be called reliable.

## Loading from SD without a complete extra memory slot

Yes: the selected file could be read in bounded chunks and restored into the
game's existing MEM1 regions. It would not need to remain as a full resident
snapshot in spare MEM2. The game would still run from RAM and stay frozen until
the complete restore is finished; this is a load operation, not executing game
objects directly from SD.

The archive and destination manifest need validation before any restore write.
The ARM storage worker could feed a small mailbox while the PPC copies admitted
ranges after the existing GPU/card barrier. Fresh hardware services and the mod's
stack/code must remain live throughout. Compressed input also needs bounded codec
workspace, but does not inherently require a complete second uncompressed image.

Streaming trades away the simple rollback provided by retaining the old state.
A card removal or read failure after the first overwrite leaves a partial game
image; the design must either retain recovery data or keep the game frozen and
recover through a controlled scene restart. A successful pre-read cannot guarantee
the next read succeeds. This recovery policy and reboot compatibility need proving
before exposing direct streaming as a user-facing Load action.

## Agreed controls for the multi-state version

The user chose this control scheme on September 8:

- Keep the existing **Save state** and **Load state** binds. Both act on the
  currently selected memory slot.
- Add **Active state** to the Savestates menu, showing each supported slot's
  number and whether it is empty or saved. Changing it selects a slot without
  saving, loading or replacing anything.
- Add an optional **Cycle states** bind, **unassigned by default**. It selects
  the next supported memory slot, including empty slots, and wraps to the first.
  A short notification identifies the selected slot and its status.
- Future SD state browsing, saving and loading will live in the menu and will
  not require additional default controller combinations.

Append the bind ID and stable INI key after the existing IDs; preserve
all saved bindings, including reserved spin IDs. A default mask of zero persists
as `none`. Place the control beside Savestates through menu presentation instead
of reordering persisted IDs. The menu and shortcut use the same selection operation.

A pending load must retain its original slot and snapshot generation through
confirmation, the card wait and the post-render restore. Slot changes must not
redirect that operation. Input takes must likewise retain their original slot
and generation; QFT/IL sidecars belong to each slot. If Cycle shares a press
with Save or Load, Save/Load takes precedence and cycling is suppressed.

These controls are implemented with three compressed slots. The previous
`F6962C1F` release has one resident state. Capacity is checked for every save;
three unusually large states are not guaranteed to fit together.
