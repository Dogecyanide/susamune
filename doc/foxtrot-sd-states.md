# SD savestates

Savestates can be saved as new numbered files in `/moonshine_states` on the same device as the launcher configuration. The SD menu imports a selected file into the active memory slot; the ordinary Load action then restores it. Files survive reboot. They require the same Moonshine mod build, disc region, launcher configuration, scenario and checked resource layout. A refused file leaves the existing memory slots intact.

The feature is experimental. Host tests exercise the production file worker, client, codec and slot commit path. An integrated US Bianco 1 test also restored a state from one Dolphin process in a fresh process, including exact position, QFT time and ghost-prefix bytes, then continued stepping and moving. Dolphin's absent SD worker was simulated by the private test harness; a completed SD restore on Wii still needs testing. The current owner profile admits checked memory archives and conservatively refuses unsupported archive types or unsettled DVD/setup activity.

## Format and transfer ownership

`include/susamune/state_storage.h` defines archive version 1: a 96-byte big-endian header, up to 7,168 bytes of opaque mod metadata, then the exact zlib stream. The metadata is the region-specific `StoredState` (6,872 bytes in the tested US image), including the QFT, IL and complete ghost-prefix sidecars plus the 5,920-byte owner profile. Separate CRCs cover header, metadata and compressed payload. The header contains no restore addresses or pool offsets; its printable 31-character name never becomes a path.

The dedicated mailbox is 7,904 bytes inside an 8 KiB allocation. Request, response and receipt use separate cache lines. A receipt must match the request sequence, process session, command and selected archive ID. Changing a request cancels the old worker operation; the client continues to own all affected memory until the cancellation request itself is acknowledged. A missing response never unlocks the buffers on a timeout.

Export holds compressed pool bytes immutable. The ARM writes `state_00000001.tmp`, computes the payload checksum, rewrites and syncs the completed header, closes the file and renames it to a new `.mss` name. Existing archives are never overwritten. Failed or interrupted temporary files are ignored by the catalog and their IDs are skipped by later exports. Each service pass processes at most 16 KiB of file data, or a bounded directory scan, only while the shared FatFS/DI path is idle.

Import writes only into the fixed 4 MiB transient staging buffer and the currently unused pool tail. It validates the exact file length, selected header checksum, region, configuration and all file checksums. The PPC then checks the stored-state tag, compiled game/root/heap ranges, scenario, ghost-prefix bounds, matched owner profile and the entire compressed stream before it commits the pinned slot. The slot and generation stay pinned throughout the transfer. Other slots are preserved if validation or capacity admission fails.

New SD requests require a fully live director in `STATE_NORMAL`; an already open menu cannot start a transfer during death, demo or departure states. The main update holds gameplay and input throughout transfer and candidate validation, including cancellation acknowledgement.

## Memory banks and cache handling

- The primary pool remains `0x91F00000..0x92EA0000`; the codec workspace remains immediately above it. The optional 2 MiB bank is `0x9193F000..0x91B3F000`. Only a launcher advertising `SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION` permits that bank; an older launcher retains the original capacity. Dolphin uses `0x70000000` and `0x71910000` respectively.
- Slot offsets are logical, byte-packed offsets across these noncontiguous banks. File I/O and cache maintenance stop at each physical bank boundary. The compressed stream never includes the codec workspace or the physical gap between banks.
- Ghost file transfer shrinks to `0x13E000` bytes, still exceeding the 1,297,992-byte maximum canonical ghost. Its tail now holds the mailbox at `0x91E3D000..0x91E3F000`, or `0x714FE000..0x71500000` in Dolphin. Immutable mod staging remains unchanged.
- A free tail can begin partway through a cache line. The PPC flushes the affected range before publishing a request. The ARM invalidates each destination piece before writing it, preserving the occupied portion of a shared line, then stores its completed bytes. The PPC invalidates the affected pieces only after the matching completion or cancellation receipt.

## Reboot boundaries

`state_archive_profile.cpp` derives the owner profile from compiled addresses and validates its bounded graph against the live game. Its anchors cover root/system/stage heap identities, root allocations, resource volumes and their retained runtime links. The restore callback receives only a newly captured and matched live profile. It skips current setup-thread storage, heap mutex/tree ownership, controller runtime links/reset timers and application service pointers without temporarily overwriting them.

A memory save captures its profile at the same time as the compressed game state. A failed profile capture keeps the RAM save usable but prevents its SD export. An imported slot is marked durable locally; every later Load rechecks the live profile before decompression and applies the retained-owner copy policy. The native mission stopwatch shifts its absolute start timestamp by the difference between current and saved uptime, including when a new boot's uptime is lower. QFT uses its existing savestate sidecar; loading a saved ghost prefix continues a full-level TAS ghost and retains PB disqualification.

## Evidence

The implementation follows the bounded-worker and atomic-new-file approach in DarkMoonshine's `launcher/kernel/LmStateStorage.c`, inspected at `C:/Users/Dogec/Documents/ChatGPT/Luigi House/Moonshine-Luigis-Mansion`. Sunshine has its own archive magic, directory, metadata and owner profile. It does not consume Luigi's Mansion archives or persistent keys.

Focused tests:

- `test_state_storage_kernel.py`: eight tests drive the production ARM worker through two-segment and two-bank roundtrips, CRC failures, truncated/extended files, stale selections, wrong configuration, capacity boundaries, cancellation receipts, failed write/sync/rename and paged catalogs.
- `test_state_storage_client.py`: six tests run the production PPC client against stale receipts, late cancellation, long waits, reinjection, legacy capacity and exact cache-bank boundaries.
- `test_savestate_archive.py`: five tests use the real codec and banked commit helper with the production completion path, covering each pinned slot, unchanged surviving slots, rejection paths, validation/commit ordering and normal-play admission with clear refusal feedback.
- `test_state_archive_profile.py`, `test_state_codec.py`, `test_state_pool_memory.py`, `test_savestate_recompression.py`, `test_savestate_queue.py` and `test_savestate_stopwatch.py` cover their respective production components. Runtime hardware admission and cold-boot restore are separate checks.

The integrated private proof is recorded in `build/foxtrot-archive-proof/capture.json` and `restore-results.json`. A compile-gated adapter was generated into copied sources under that private directory; shipping sources and flags do not include it. The verified private BPS target CRC was `B1615F41`, based on the frozen interim build. Process 36000 produced a 5,112,156-byte packed state; process 34276 imported it through `updateDisk` and restored it through `loadSlot`. A checksummed archive with one altered owner anchor was rejected without changing the existing slot's bytes, generation or live position. The successful restore reproduced position `(-7823.87890625, 2908.670166015625, 19888.36328125)` and QFT `1:42.902`. A subsequent RAM save retained all 95,152 ghost-prefix bytes (2,995 poses, 2,950 inputs) exactly, with QF start zero, TAS/assisted flags and no PB token. One Step and resumed movement then advanced normally. Both owned proof processes were closed afterward.

Private game-memory captures and extracted state payloads are development inputs and must not be included in release packages.
