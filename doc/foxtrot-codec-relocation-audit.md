# Codec workspace relocation audit

Implemented September 9, 2026 after auditing the current protocol-5 launcher.
This moves scratch memory; it does not add a third state bank or reduce the
game's MEM1 reserve. Final build and live timing evidence is recorded separately
in the state-codec and memory reports.

## Selected memory map

| Owner | Wii cached range | Dolphin range |
| --- | --- | --- |
| Ghost request/response header | `91880000..91880100` | `71100000..71100100` |
| Local input take | `91880100..91890100` | `71100100..71110100` |
| Codec/packed-CRC scratch | `91891000..918DF000` | `71111000..7115F000` |
| Secondary ghost model heap | `918EA000..91900000` | `7116A000..71180000` |
| Full primary state bank | `91F00000..92EF0000` | `70000000..70FF0000` |
| Secondary state bank | `9193F000..91B3F000` | `71910000..71B10000` |

All ranges have exclusive ends. The relocated scratch is `0x4E000` bytes
(312 KiB), with 3,840 bytes between the tape and scratch, and 45,056 bytes
between scratch and the model heap. Shared-map compile checks enforce the
ordering and complete 32-byte cache lines. Both full primary banks end exactly
where their existing configuration/runtime blocks begin.

The primary grows from `0xFA2000` to `0xFF0000`, giving **319,488 additional
bytes** directly to the three slots. With the unchanged two-MiB bank, capacity
is **17.9375 MiB**. Including the preceding 8 KiB padding reduction, the total
gain over the original 320 KiB high-workspace layout is 320 KiB.

## Ownership and lifetime evidence

- Before handoff, `launcher/loader/source/dip.c::ReadRealDisc` owns the broader
  `91780000..91900000` DMA buffer. Each read waits for `DIP_CONTROL` completion
  before copying its result and returning. Loader disc/model-asset reads finish
  before game execution. Runtime `launcher/kernel/RealDI.c` instead uses
  `NIN_MEM2_DISC_CACHE_PHYS_BASE + 0x800`, far below this range.
- `launcher/kernel/SusamuneGhost.c::SusamuneGhostInit` clears and publishes only
  the 256-byte doorbell header. Its file/catalog traffic uses
  `SUSAMUNE_GHOST_STORAGE_DATA_PHYS_PTR`, now the separate `11CFF000` bank.
  The old `SusamuneGhostStorageMailbox.payload` member remains for source/size
  compatibility; current worker code never accesses it. It is not free space
  on an unidentified older worker.
- `src/practice_session.cpp` owns exactly the preceding 64 KiB tape.
  `src/ghost_model.cpp::init` creates the secondary heap at the fixed
  `+0x6A000` offset with size `0x16000`; neither heap creation nor stage resets
  claim the earlier gap. Ghost recording/playback and input-prefix banks are
  separate owners. No split or achievement storage moved.
- `launcher/kernel/main.c` initializes configuration, ghost storage and state
  storage before releasing the PPC. `SusamuneCfgInit` first clears stale
  configuration, and publishes the new capability only on the supported
  configuration path. A missing backend leaves zero magic and uses fallback.
- An in-session reset runs `PatchGame`/`PatchSusamune`, which rereads immutable
  mod staging and reinstalls MEM1 sections. It does not invoke the PPC loader's
  old disc DMA reader. The new mod initializes fresh slot metadata; no old
  codec contents are needed. A complete return to the launcher gives that
  loader its original buffer back after gameplay has ended.
- Scratch is PPC-only throughout gameplay. Codec initialization and each
  packed CRC initialize the state they consume. No per-operation ARM handoff,
  whole-workspace flush, or invalidation is needed. Existing export/import
  flush/receipt ownership still applies to packed state banks. Aligned scratch
  edges cannot write back a cache line belonging to tape, doorbells or models.
- Dolphin's scratch uses the existing `70000000..72000000` fake aperture and
  scalar codec operations. It does not pass these addresses to GX or retail
  paired-single menu rendering, the separate known Dolphin limitation.

## Capability, fallback and stable addressing

`SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED` is bit `0x100000` in the existing
configuration flags word (offset `0x0C`). Wii requires the expected configuration
magic/version plus this bit. The additional state bank retains its independent
`0x40000` capability. Dolphin selects its full layout without an ARM service.

| Configuration | Primary | Scratch | Extra bank |
| --- | --- | --- | --- |
| New relocation capability | `FF0000` | Relocated ghost gap | If separately advertised |
| Valid older configuration | `FA2000` | Primary base + `FA2000` | If separately advertised |
| Missing/unknown configuration | `FA2000` | Primary base + `FA2000` | Disabled |

`SavestateManager` stores its selected `sPoolMemory` at construction.
`codecWorkspace()` derives scratch from that cached primary size; it never
rereads capability flags while saved slots exist. Unexpected primary sizes
produce no workspace. The SD client independently latches its bank map at
initialization and uses it for requests, cancellation and receipt invalidation.
Configuration capability flags are boot-published, not user-editable settings.

State transport is now **4**, because the ARM worker's `PoolPiece` boundary
changed. A new client also requires the full primary layout before enabling
that service. Old protocol-2/3 workers expose no service to this client; an old
mod rejects the new worker's transport. RAM fallback remains usable. This
prevents a logical offset beyond the old primary end from referring to different
physical banks on the two processors. Archive version 1 and its field offsets
remain unchanged; the existing exact-build admission policy still applies.

## Changed source and verification

Production changes are confined to the shared map, one configuration capability
and its kernel publication, transport version, `state_pool_runtime.hxx`, the
small `savestate.cpp::codecWorkspace` delegation, and SD client map latching.
The ARM worker already derives its split point from the shared map. Codec
algorithms, pool compaction, other owners and MEM1 reservation are unchanged by
this relocation.

The focused 55-test run covers both capability pairs, missing/future headers,
Dolphin addresses, layout latching despite changed flag bytes, stale boot
publication, loader/worker ownership, cross-bank archive I/O, old protocol
rejection, dirty-compaction export flushing, and pending receipt invalidation.
Relevant suites are `test_state_workspace`, `test_state_storage_client`,
`test_state_storage_kernel`, `test_savestate_archive`, `test_state_staging` and
`test_practice_tape`. Final live testing should fill/replace/restore all three
slots, independently check each packed CRC, use SD import/direct load, retain
a local input take, and verify both neighboring ghost/tape allocations remain
intact. Crowded-slot speed improvement depends on the new capacity fitting a
faster producer and must be measured rather than inferred from the byte gain.
