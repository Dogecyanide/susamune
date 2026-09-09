# SD savestates

Savestates are new numbered `.mss` files in `/moonshine_states` on the launcher's
configuration device. Display names are chosen before export and can be renamed
later. Files survive reboot and require the same mod build, disc region, launcher
configuration, scenario and compatible checked resource layout.

`Save to` and `Load from` are independent. On an SD file, A imports into the
pinned Save to RAM slot without changing Load from. Y selects the file for the
normal Load bind; that path stages and restores without replacing or consuming
any of the three RAM slots. Start renames and X requests deletion with confirmation.
Selecting a source alone does not restore gameplay. Pending actions pin identities
before waiting or approval rather than rereading whichever selection is current.

Build C4AF447B received user confirmation for SD file loading, with loading
reported as good and saving still slow. Earlier build 5B0EC1B1 received confirmation
for restoration after a real Wii reboot, full ghost continuation with frame advance, timer alignment and colour
persistence. The new direct-load and file-management paths have separate host and
Dolphin evidence below; this is not a claim that every scene, Wii U configuration
or hardware file-operation failure has been tested.

The current quick-format decoder has also passed a separate private Dolphin
proof: valid MSL4 direct restore, malformed-block refusal despite corrected
archive CRCs, exact position/QFT, and all RAM entries unchanged. Its host adapter
supplied file bytes/ARM receipts, so it does not measure actual SD speed or prove
cold-reboot behavior for this new build. See `build/foxtrot-speed-sd-proof` and the
codec document for the exact evidence.

## Archive version 1, transport protocol 5

`include/susamune/state_storage.h` keeps archive version 1: a 96-byte big-endian
header, bounded opaque metadata, then the exact compressed stream (bounded MSL4
or zlib). Current PowerPC
`StoredState` sizes are 6,896 bytes for JP and 6,872 bytes for US/PAL, below the
7,168-byte metadata limit. This includes QFT, IL and ghost sidecars plus the
5,920-byte owner profile; the used ghost pose/input/segment prefix is part of the
compressed stream. Separate CRCs cover header, metadata and compressed payload.
The header contains no restore pointers or pool offsets. Its printable name is
at most 31 characters and never becomes a path.

The mailbox transport is now protocol 5. This requires the bounded window reader
and rejects older workers, including those whose primary pool boundary predates
workspace relocation (now 0xFF0000). Its 8,000-byte structure
remains inside
the same 8 KiB allocation; the appended request/result name buffers occupy their
own 32-byte lines at offsets 7,904 and 7,936. Request, response and receipt also
have separate cache lines. A receipt must match request sequence, process session,
command and archive ID. The effective returned name has its own receipt CRC.
The appended 32-byte window receipt at offset 7,968 identifies the returned
payload offset, length and CRC; its five reserved words must remain zero.
An incompatible transport is rejected rather than interpreted using an older pool map.

Transport changes do not rewrite existing archives. The original `.mss` file and
its header CRC remain immutable after successful export, including across renames.
Build/region/configuration restrictions still apply independently of archive-format
compatibility.

## File creation, names and deletion

Export holds the selected compressed pool bytes immutable. The ARM creates a new
`state_00000001.tmp`, writes metadata/payload, computes checksums, rewrites and syncs
the completed header, closes, then renames it to `.mss`. It never overwrites an
existing archive. Incomplete temporary files are ignored by the catalog and their
IDs are skipped by later exports. Each service pass handles at most 16 KiB of file
data, or a bounded directory scan, while the shared FatFS/DI path is idle.

Rename writes a separate 64-byte version-1 name record to alternating
`state_00000001.name0` and `.name1` sidecars. Each record binds its generation and
printable name to the numeric archive ID and immutable header CRC, with its own
checksum. The worker writes/syncs/closes a temporary record before replacing the
inactive sidecar. The previously active generation survives a failed update.
Catalogs and read receipts use the newest valid matching name; absent/invalid
sidecars fall back to the name in the archive header. Unreadable, contradictory
or newer-version name records prevent an unsafe replacement.

Deletion first writes, syncs and closes a `.used` marker that reserves the numeric
identity, then removes the archive and its name sidecars. Later exports skip that
ID, preventing a stale selection from silently naming a new file. Rename/delete
check the selected header CRC before mutating it. Their small metadata transaction
is not cancellable once accepted; the menu waits for its matching receipt.

## Read paths and ownership

Import and the fully staged direct Load read only into the fixed 4 MiB transient area plus
currently unused pool tail. The request carries the tail boundary, expected file
length/CRC identity and session. The ARM checks exact file size, region/configuration
and all file CRCs. The PPC checks metadata tag, build/snapshot/scenario, compiled
game/root/heap restore ranges, ghost-prefix bounds and owner-profile admission.

For A/Import, PPC `StateCodec::validate` fully inflates the staged stream without
game writes. Only a valid stream can be committed to the pinned RAM slot and
receive a fresh generation. Other slots and the Load from selection remain intact.
The imported slot becomes locally durable and receives a trusted packed-CRC cache
entry only after full validation/commit.

For Y/Load, the file identity is retained as the Load source. Each Load reads the
file again; no permanent fourth slot or retained SD-state cache is created. After
the receipt and metadata admission, `sDiskLoadReady` retains exclusive ownership
of the staged bytes until the post-draw restore. At that barrier, the live owner
profile is captured again and `StateCodec::decompress` fully validates the compressed
stream before its writing pass. A file with correct CRCs but malformed compressed
data is still refused before game writes. The direct path does not create or
replace any RAM slot, generation, sidecar or trusted CRC cache entry.

When `4 MiB + poolCapacity - pool.used` cannot hold the complete direct-load file,
the streaming fallback uses the same fixed 4 MiB window. It requires an intact
RAM recovery state from the current scene with a matching owner profile. Before
any SD writes reach the game, that recovery state's descriptors and complete
compressed stream are validated, then the whole SD stream is checked without
writes. Each window gets a checksum; the second pass requires the same immutable
file identity and identical window bytes before consuming them.

Preflight failure preserves the current game frame. A late SD error, such as
removing the card during the second pass, restores the prevalidated RAM state
and explicitly reports "SD read failed; restored state N". Its precompiled spans
are used without consulting the partially restored world. All three retained
slots, generations and prefixes remain unchanged. Missing compatible recovery
is refused safely with a prompt to save a RAM state in the current scene. Import
retains its own commit-capacity check and never uses streaming to evict a slot.
See [the streaming design and tests](foxtrot-sd-streaming-design.md).

The RAM-only optimization is separate: `sPackedChecksums[3]` is mod-owned storage,
not an archive field. Only this codec's successful local producer or a fully
validated import establishes an entry. RAM Load checks the current packed CRC
again under exclusive ownership before using a single writing inflate. Files
cannot set this trust state. Imported RAM states still recheck live owners on
every restore. See [the codec contract](foxtrot-state-codec.md) for failure and
`COMMIT_FAILED` handling.

New SD requests require a fully live director in `STATE_NORMAL`; an open menu
cannot start a transfer during death, demo or departure. Gameplay/input remain
held through transfer and candidate processing. Changing a request cancels the
old worker operation, but affected memory stays owned until the cancellation
itself has a matching receipt. A missing response never unlocks buffers merely
because a timeout elapsed. A selected direct-load candidate remains locked past
its file receipt until restore/rejection cleanup finishes.

## Memory banks and cache handling

- The current primary pool is `0x91F00000..0x92EF0000`, with codec scratch relocated
  to `0x91891000..0x918DF000`. The optional 2 MiB bank is `0x9193F000..0x91B3F000`. Only a launcher
  advertising `SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION` enables that bank; combined
  capacity is 17.9375 MiB. Dolphin bases are `0x70000000` and `0x71910000`.
  Full primary and relocated scratch require the paired relocation capability;
  incompatible launchers retain the smaller legacy layout with SD service disabled.
- Logical packed offsets cross those noncontiguous banks. File I/O and cache
  maintenance stop at each physical boundary. The stream never includes the
  workspace or intervening physical gap.
- The ghost-file window is `0x13E000` bytes, still larger than a maximum canonical
  ghost. Its final 8 KiB hold the state mailbox at `0x91E3D000..0x91E3F000`, or
  `0x714FE000..0x71500000` in Dolphin. Immutable mod staging remains unchanged.
- A free tail may begin inside a cache line shared with retained slot bytes. PPC
  flushes the range before publishing; ARM invalidates each piece before writing
  and stores completed bytes. PPC invalidates only after the matching completion
  or cancellation receipt, preserving the occupied part of a shared line.

## Reboot boundaries

`state_archive_profile.cpp` derives its bounded owner graph from compiled addresses
and live game objects. Anchors cover root/system/stage heaps, tracked root
allocations, resource volumes and retained runtime links. The restore callback
receives only a newly captured, matched live profile. It skips current setup-thread
storage, heap mutex/tree ownership, controller runtime/reset fields and application
service pointers; it never writes old owners temporarily and repairs them later.

A RAM save captures the profile alongside game state. Failed profile capture keeps
the RAM save usable but prevents SD export. Imported and direct SD states require
compatible live resources and settled setup/DVD activity before restore. A matching
level name by itself is insufficient; unsupported profiles are conservatively
refused.

The native mission stopwatch rebases its absolute start using current versus saved
uptime, including a fresh boot whose uptime is lower. Rejected reads preserve the
live stopwatch instead; transfer time is excluded. QFT restores its own sidecar.
A saved ghost prefix restores the full level opening and records a replacement
continuation as TAS/assisted without ordinary PB eligibility.

## Evidence and remaining hardware scope

The file-worker design follows the bounded-worker/atomic-new-file approach in
DarkMoonshine's `launcher/kernel/LmStateStorage.c`, inspected at
`C:/Users/Dogec/Documents/ChatGPT/Luigi House/Moonshine-Luigis-Mansion`. Sunshine has
its own magic, directory, metadata and owner profile. It does not load Luigi's
Mansion archives or keys.

Production host tests cover the ARM worker, PPC client, name/delete operations,
CRC implementation, stale selection/receipt rejection, late cancellation,
failed writes/sync/rename, bank boundaries, archive admission, both load paths,
RAM trust cache and pinned generations. Relevant files are
`test_state_storage_kernel.py`, `test_state_storage_client.py`,
`test_state_storage_crc.py`, `test_savestate_archive.py`,
`test_state_archive_profile.py`, `test_state_codec.py`,
`test_state_pool_memory.py`, `test_savestate_recompression.py`,
`test_savestate_queue.py` and `test_savestate_stopwatch.py`. Host tests are not
physical SD-card or Wii filesystem timing measurements.

The new direct-load proof is in `build/foxtrot-sd-direct/results.json`, on interim
US target `DE29BE2F`. It saved three distinct RAM states, restored the first through
the production selected-SD queue/validation/restore path, and compared all three
retained slots unchanged. Position and QFT restored exactly and movement continued.
A deliberately malformed zlib stream wrapped in correct file CRCs was rejected
with the live position and all three RAM states unchanged. A private host adapter
supplied the ARM file receipt because standalone Dolphin lacks that worker; this
proves the PPC path, not physical SD reads. Its post-delivery timing excludes
transfer and must not be reported as an SD load time.

The earlier cross-process proof below covers reboot ownership and ghost-prefix
continuation. Both are distinct from the user's successful prior-build Wii reboot
restore; the newer file controls still need hardware feedback.

The integrated private proof is recorded in `build/foxtrot-archive-proof/capture.json` and `restore-results.json`. A compile-gated adapter was generated into copied sources under that private directory; shipping sources and flags do not include it. The verified private BPS target CRC was `B1615F41`, based on the frozen interim build. Process 36000 produced a 5,112,156-byte packed state; process 34276 imported it through `updateDisk` and restored it through `loadSlot`. A checksummed archive with one altered owner anchor was rejected without changing the existing slot's bytes, generation or live position. The successful restore reproduced position `(-7823.87890625, 2908.670166015625, 19888.36328125)` and QFT `1:42.902`. A subsequent RAM save retained all 95,152 ghost-prefix bytes (2,995 poses, 2,950 inputs) exactly, with QF start zero, TAS/assisted flags and no PB token. One Step and resumed movement then advanced normally. Both owned proof processes were closed afterward.

Private game-memory captures, extracted payloads and proof adapters are development inputs and must not be included in release packages.
