# Shared ghost/state transfer lease

Production ARM coordinator and executable protocol proof, 2026-10-08.
The canonical headers are `include/susamune/transfer_lease.h`,
`transfer_publication.h`, and `transfer_layout.h`; the old private headers
delegate to them. Twelve native transition tests and seven adversarial
publication tests cover individual-word cache transfers. PPC and big-endian
ARM/GNU89 frontends compile both protocol headers. Thirteen retirement tests
exercise actual worker transaction phases, and thirteen coordinator tests
exercise each actual worker with a bounded peer. The existing 59 ghost,
state, and TAS worker tests also pass. The ARM implementation and reset
barrier, PPC ghost consumer, and PPC state/result consumers are integrated.
Local RAM-work guard wiring and explicit activation remain separate gates. The
legacy map remains the default. Timer source/reserves are unchanged; actual
Wii execution and the final linked footprint remain separate gates.

## Capacity and accounting

The existing allocations total `0x400000 + 0x13E000 = 0x53E000` bytes.
A contiguous shared `0x33E000` transaction window leaves exactly `0x200000`
bytes for the state pool. With the proposed window anchored at `0x91300000`,
the two released pieces are `0x9163E000..0x91700000` (`0xC2000`) and the old
ghost file bank `0x91CFF000..0x91E3D000` (`0x13E000`). The pool therefore needs
four-bank addressing; expanding the existing extra bank would enter live
ghost input storage. `transfer_layout.h` defines these opt-in ranges without
changing legacy constants or claiming any DI scratch tail. This is not yet an
achieved runtime saving: every PPC consumer must adopt the ownership rules.

| Consumer | Maximum transaction-window use |
|---|---:|
| Normal state compression/import window | 3,399,680 bytes (`0x33E000`) |
| Retained-state repack | 319,488-byte second codec workspace + 3,080,192-byte candidate prefix |
| Ghost canonical file | 1,298,016 bytes; current dedicated capacity is 1,302,528 |
| Ghost catalog response | 3,680 bytes |
| Imported ghost filename preparation | 96 bytes |
| TAS tape transfer | 66,052 bytes |
| ARM TAS component verification scratch | 16,384 bytes |

The primary `0x4E000` codec workspace remains separately owned; repack needs
both workspaces simultaneously. Reducing the window changes transactional
admission and streaming frequency: all span counts, stream-window bounds,
pool-tail ranges, and frozen-input capacity tests must use the new size.
The lease alone does not prove every existing save still fits.

Use four currently reserved ghost-mailbox cache lines:

| Address relative to ghost mailbox | Writer | Eight u32 fields |
|---|---|---|
| `+64` (`0x91880040`, ARM `0x11880040`) | PPC | magic/version, epoch, ticket, owner, phase, worker sequence, worker session, worker command |
| `+96` (`0x91880060`, ARM `0x11880060`) | ARM | same identity, with receipt phase |
| `+128` (`0x91880080`, ARM `0x11880080`) | PPC | publication generation, issued high-water generation, six reserved words |
| `+160` (`0x918800A0`, ARM `0x118800A0`) | ARM | publication generation, issued high-water generation, six reserved words |

These consume 128 of the existing 192 reserved header bytes; offsets
192..255 remain reserved. They neither touch the local tape at +256 nor
enlarge the mailbox. `TWLeaseControl` is 128 bytes, central PPC runtime is
48 bytes, and central ARM runtime is 52 bytes, enforced by compile checks.
Each processor also owns a four-byte publication counter. The production ARM
coordinator additionally retains a private 128-byte control snapshot and four
four-byte mode/activation/dispatch fields, for exactly 200 BSS bytes. The two
workers add another 16 BSS bytes for retirement and failed-close latches
(GNU ARM uses four-byte bools). There is no new payload allocation. The reader
has a 32-byte temporary snapshot before compiler frame costs; callback tables
may be optimized away. PPC owner/borrow tokens and adapter fields must be
charged from its final implementation rather than only the 48-byte core.
Never store private drafts directly into shared memory before withdrawing
publication. Final linked code and stack high-water need separate measurement.

## Ownership and the exact quiescence certificate

Choose immediate PPC acquisition after proven quiescence. An asynchronous
grant for each RAM save would add a needless ARM round trip. There is one
asynchronous map-activation handshake at boot; subsequent local claims need
no ARM service. PPC transitions are serialized with a short interrupt guard
around the central bookkeeping, never across disk I/O or a frame wait.

The complete lifecycle is:

`IDLE -> LOCAL preparation -> REMOTE -> RESULT -> BORROWED -> LOCAL -> IDLE`.

The same owner can submit another ARM window from LOCAL without releasing
the operation. A local RAM save/repack is simply `IDLE -> LOCAL -> IDLE`.
No feature may acquire recursively, even when it is already the named owner.
Explicit owner tokens let the caller retain ownership across helper calls.

The certificate is **a validated snapshot of the ARM response at +96 and
its publication line at +160**, with
matching protocol/epoch and a READY or DONE ticket already observed by the
PPC coordinator. It is not a ghost ACK, state ACK, `busy()==false`, or the
return of a single FAT call. The only publisher of DONE is the central ARM
coordinator, after all three assertions hold:

1. `SusamuneGhostQuiescent()` succeeds: idle, no tracked handles, no failed
   file/directory close, and no deferred payload access remaining.
2. `SusamuneStateStorageQuiescent()` succeeds with the same conditions.
3. The operation's payload writes and ordinary module receipt have been
   flushed before the lease completion line is flushed.

Normal completions move the worker to idle before the coordinator publishes
DONE. State `Finish` flushes its ordinary response before setting `Phase = IDLE`;
coordinator `Complete` runs after the entire service call returns. Ghost's
`FinishRequest` sets idle before its response flush, but each path must first
prove all open handles are closed. The native retirement traces exercise
both successful commit phases and failed-close paths.

All new-map ARM dispatch passes the central gate before reading any shared
payload or accepting a legacy doorbell. The gate matches owner, epoch,
ticket, command, sequence, and session, and accepts each ticket once. Both
`Pending` functions must respect this gate too: an old ghost request must
neither revive nor starve state service because ghost has higher priority in
the main-loop worker chain. `SusamuneTransferPending/Service` precede both
workers and explicitly progress the accepted owner. The ordinary worker
gates refuse independent dispatch while shared mode is active. Legacy mode
retains the original dispatch and nonoverlapping addresses.

Submission first flushes all PPC payload, ordinary request, and metadata
lines ARM may access. Completion first flushes ARM payload and ordinary
receipts. Both then publish the central body with this exact sequence:

1. Set publication generation to zero and issued to a fresh generation;
   flush the publication line and complete the barrier.
2. Copy the private draft into the body, flush that line, complete the barrier.
3. Set the single aligned publication generation word to the new generation,
   flush its line, complete the barrier.

Readers invalidate the publication line and complete the barrier, read a
nonzero generation, invalidate/read the body into private storage, then
invalidate/barrier/read the generation again. Accept only equal nonzero
generations; discard any previous snapshot on failure. A 32-byte cache-line
transfer is never assumed atomic. Each single generation word must be atomic.
The tests reproduce a new ticket mixed with an old ARM phase/owner that
revives a stale ghost request without this gate, then reject it with the gate.
They cover both directions, every 256 old/new body-word subset, and writer
progress at every reader word boundary for multiple cache-transfer orders.

Publication generations increase independently of request tickets: cancellation
and completion can change phase without changing a ticket. Never wrap or reuse
a publication generation. The durable issued high-water survives a withdrawal
and PPC BSS reset; resume it only while its old writer is parked. Exhaustion or
an inconsistent resumed publication refuses reuse until a full kernel restart.
Cold kernel initialization may clear all control lines only while neither old
processor nor old worker can retain a reference. Ordinary `Init` preserves them.

The PPC adapter needs aligned volatile word loads/stores and compiler memory
barriers, `DCFlushRange(line,32)` plus `sync` for writer completion, and
`DCInvalidateRange(line,32)` plus `sync` before reader loads. Serialize the whole
publication against local reentrancy. ARM uses the existing synchronous
`sync_after_write(line,32)` and `sync_before_read(line,32)` cache syscalls,
with compiler memory barriers around publication loads/stores. The local
`syscalls.s` stubs expose those IOS calls; their internals are outside this
repository, so actual IOS completion behavior remains a hardware integration
assumption to verify. Do not substitute a compiler barrier for cache completion
or issue privileged CP15 instructions from an unproved execution mode.

Tickets increase without wrapping, including each new ARM command/window.
The legacy worker sequence may wrap from `0xffffffff` to 1 because the new
ticket remains distinct. Exhausted tickets refuse new submissions until a
proper epoch transition; exhausted epochs refuse activation. Epochs come
from the persistent ARM coordinator and are not a PPC clock hash. Old
receipts, worker callbacks, borrowed tokens, and owners cannot release a new
operation. The model intentionally does not treat a timeout as a transition.

## Boot, reinjection, and legacy compatibility

V3/V4 is transport format, not runtime memory-map capability. The kernel
starts in legacy-map mode, advertises CAPABLE only after both services are
quiescent, and continues supporting old images on the old map. CAPABLE,
ACTIVATE, and READY carry runtime ABI `0x00010001` in `command`; a mismatched
ABI cannot activate. New PPC code
requests ACTIVATE before any ghost/state initialization can queue work.
ARM switches both worker payload addresses and the advertised pool layout
only after validating ACTIVATE and retiring both old doorbells, then publishes
READY for that epoch. PPC uses the smaller shared window and new pool banks
only after receiving READY. No SD backend is required for local RAM leases;
storage availability and lease/map capability are separate properties.
State submissions still require the ordinary backend's `available` flag;
callers must refresh it after activation and refuse unavailable submissions
before transitioning a local lease to REMOTE. A local codec operation needs
no storage request and remains usable without a storage backend.

New code under an old kernel retains its legacy path/map. A fresh PPC image
finding an already-active lease epoch cannot infer it is safe from its own
zeroed BSS. It must wait for the kernel's global reinjection retirement; it
must not silently fall back to legacy addresses while the shared map is
already active. Boot/reset metadata cannot be included in a savestate.

The retirement barrier is at the beginning of `PatchGame`, before
`DoPatches`, installation, any buffer reuse, and the RESET_STATUS game-entry
acknowledgement. Preconditions: PPC is parked in the entry handshake, and
FatFS is exclusively available. Finish the DI asynchronous backend and deal
with its outstanding guest completion under the existing DI rule; do not
equate `DIFinishAsync()` alone with clearing `DI_IRQ`.

The production worker hooks are `SusamuneGhostRetire()` and
`SusamuneStateStorageRetire()`, plus `...Quiescent()` and `...RetireFailed()`.
`SusamuneTransferBeginRetire/RetireStep` coordinate both. The coordinator
first publishes DRAINING and rejects fresh dispatch. Each retire hook drains
an **already accepted** request through the existing service phases and
terminal status, with the old request and old buffer map still frozen. It
does not start an unaccepted pending request. At idle it closes/verifies all
handles and marks the current ordinary request sequence retired so its old
doorbell cannot restart. Only then may the coordinator clear that worker's
bit in its two-bit reset barrier. Both bits must clear before
`SusamuneTransferResumeLegacy` increments the epoch, selects legacy addresses,
initializes both idle services, and publishes CAPABLE. PatchGame calls it
before the entry ACK whether the installed image is old/new or installation
was skipped. Failed close/publication leaves PPC parked. Shared addresses
remain selected during retirement so accepted old operations drain safely.
New PPC attachment then selects the map.

Draining accepted mutations is the simplest reset rule that preserves the
existing file semantics. Ghost save writes a blank inactive envelope, payload,
sync, committed envelope, then sync/close (`SusamuneGhost.c:1935-2029`).
Export and delete have analogous commit phases. State export uses temporary
file/header/sync/close/rename (`SusamuneStateStorage.c:454-478`). TAS publication
and cleanup are in `SusamuneTasStorage.inc:371-425`. Do not erase these phase
variables or call the boot `Init` functions over open handles: both now refuse
nonquiescent reinitialization, and ghost Init clears only its first 64 bytes.
The close wrappers latch failed closes, including stack-local readers and TAS
handles. FatFS can leave an object live when close fails; that failure requires
a full kernel restart and cannot authorize buffer reuse. Handled file-not-found
and write errors with successful closes do not set this latch. The normal
terminal receipt is preserved, and unaccepted sequences are retired privately
without fabricating a receipt. An I/O failure must reach a real closed state; a retirement
timeout leaves PPC parked and memory unavailable, not falsely quiescent.
No “cancelled” result should claim to undo a mutation already committed.

Exact GNU ARM object changes, including retirement and map/dispatch adapters,
are +3,092 initialized/+8 BSS bytes for ghost, +1,444 initialized/+8 BSS for
state, and +4,756 initialized/+200 BSS for the new coordinator. The total is
+9,292 initialized/+216 BSS bytes, measured against HEAD with the production
`-mbig-endian -O2 -std=gnu89` flags in
`build/storage-retirement-audit/coordinator-receipt.json`. The earlier
`receipt.json` records retirement alone. These are object section costs before
linker garbage collection/alignment, not a linked kernel total.

Existing state user cancellation may remain cancellable for import/export/
window/catalog while rename/delete/TAS mutations remain noncancellable. In
the new protocol, cancel changes the central phase for the same ticket; it
does not overwrite the payload or normal request. The state service notices
it between existing slices and calls its normal cleanup/Finish(CANCELLED).
Cancel before dispatch completes without starting payload I/O. A commit
already completed keeps its real result. The caller retains REMOTE ownership
until central DONE, then consumes/discards the result explicitly. Ghost
currently has no user cancel command: preserve its late-result timeout
behavior, and drain it on reset. The executable model permits cancellation
only when the adapter explicitly marks a command cancellable.

## Exact PPC integration points

`ghost_storage.cpp` now claims before export, filename preparation, or
catalog submission. Its per-operation payload selector remains on the shared
stage through timeout, failure, and result consumption. Both the ordinary
receipt and central DONE are required before callbacks run. Import callbacks
copy into existing runtime tracks before `consumed`/`release`; queued follow-up
refreshes cannot recursively claim. Failed publication latches closed, while
transient reads retry without repeating consumer callbacks. `quiet()` includes
preparation and borrowed results but excludes queued refreshes. Passive client
initialization does not activate the map; shared activation refreshes ordinary
backend availability. Dolphin keeps its unavailable ghost-storage behavior.

Nine focused native ghost/client tests cover 23 adversarial cases, alongside
44 existing storage policy/paging tests. All six production PPC object
compiles pass. Console ghost-module growth is 1,688 initialized and 27 BSS
bytes; emulator changes are -68 initialized/-2 BSS bytes. These object deltas
exclude the shared lease foundation and linker padding; see
`build/timewarp-ghost-lease/receipt.json`. No activation hook was added.

| Existing path | Required lease extent |
|---|---|
| `savestate.cpp:1390` saveState, `:493` compressCandidate, `:524` repackRetainedState, `:548` repackForCandidate | Acquire STATE before the first staging write; hold through every candidate/repack pass, bank commit or failure. This path has no ARM request. Use one outer guard so every early return releases. |
| `ghost_storage.cpp:878` saveNew | Acquire GHOST before `Ghost::exportLatest` at `:894`; release on local validation failure, otherwise retain through ordinary request and completion. |
| `ghost_storage.cpp:665` requestIdentity | Acquire before imported filename memcpy at `:687`, including delete requests whose payload is only the leaf. |
| `ghost_storage.cpp:448` beginRefresh and `:758` update | All list/import-scan requests own GHOST because ARM writes the shared page. Preserve refresh flags when acquisition fails; the current update clears them before calling beginRefresh. Background refresh is deferred during state ownership. |
| `ghost_storage.cpp:497` completeRequest | Ordinary pending-command clearing is insufficient. Hold the lease until response validation, adoptCatalog's copy at `:333`, or importPlayback/importObserverTrack completes, including every error/stale-result return. These imports copy into existing ghost runtime banks; no shared payload pointer may escape. |
| `state_storage.cpp:49` submit, `:205` publishExport, `:235` startTapeExport | Acquire/adopt STATE before all header/metadata/name/TAS writes and before tape memcpy at `:246`, not merely at submit. Gate all state commands initially, even those without shared payload, so result metadata has one consistent lifetime. |
| `state_storage.cpp:105` update, `:315` takeResult, `:324` takeProjectResult | Matching ordinary receipt alone is insufficient. Require central DONE too. takeResult returns a borrowed token and retains ownership; add explicit consume/discard. A result copied by value still borrows its metadata/payload. |
| `state_storage.cpp:321` discardCancelledResult | Handle abandoned cancellation tickets after a streaming timeout as well as normal UI cancel. The new cancellation retains the original command identity, so the current command==CANCEL test is insufficient. Preserve the real final status if publication already committed; only discard the borrowed bytes after central DONE. |
| `savestate.cpp:1270` updateDisk | Consume immediately after import validation/bank commit or failure, except deferred SD restore. Store the borrow/owner tokens with sDiskLoadReady. |
| `savestate.cpp:2006` processPendingLoad, `:1738` direct CARD guard | Retain tokens across rendered-frame CARD waits and afterDraw. Release on the 600-frame timeout only when ARM is already done and no borrow remains; release after successful/failed load, including recovery and abandoned pending-load paths. |
| `savestate.cpp:867` waitStateWindow, `:879` readStateWindow, `:1804` streaming restore | Keep the outer STATE lease across validation and commit passes. Consume the previous window only when the decoder no longer references it, then submit a fresh ticket under the same owner. A 15-second timeout sends cancel and retains ownership until retirement; do not release through an outer error guard while REMOTE. |
| `state_storage.cpp:261` tapePayload, `tas_project.cpp:399-438` tape result consumer | Hold through CRC checks and all restoreTake copies; every early failure consumes/discards. Before chaining tape export into projectCommit, finish its borrow but retain/reuse the outer STATE owner. |
| `tas_project.cpp:441` project result handling | Consume the project/metadata borrow before the next request, including beginExports/importTape/planOpen chains and all error returns. |

On Dolphin there is no ARM storage backend. Use the same local owner/borrow
rules with a local-only capability setup; do not wait for an absent ARM or
pretend a console receipt arrived. RAM save/repack and gameplay CARD waits
still need these scopes. Existing CARD and renderer barriers remain intact.
The shared lease does not replace pool-slot ownership, snapshot freeze,
GXDrawDone, or the game's memory-card worker coordination.

## Proof status and next gate

Twelve tests execute the C transitions, with separate PPC/ARM request/response
cache snapshots. They cover local saves with no ARM poll, ghost preparation
and consumption, deferred restore/CARD waits, repeated streaming windows,
cancel before/after worker start, late receipt, dropped control flushes,
wrong worker/session/command, legacy sequence wrap, ticket exhaustion, stale
ghost doorbells, and reinjection from preparation/worker/result/borrowed
phases. Reset publication fails until both workers explicitly report quiet.

`test_storage_retirement.py` now replays every reachable accepted mutation
phase against uninterrupted real-worker traces, including file/directory
close failures and unaccepted doorbells. `test_transfer_coordinator.py`
executes the actual coordinator with each real worker and a bounded peer:
wrong ABI, unfinished activation, stale epoch, withdrawn publication,
opposite-owner dispatch, both-worker quiescence, cancellation, retirement,
failed-close parking, and actual imports crossing the shared-stage boundary
and both reclaimed banks. The existing worker regressions preserve legacy
file semantics. Native fixtures do not prove physical FAT/cache behavior,
Wii reset execution, UI retry fairness, or frozen-input capacity. The next
gates are local RAM-work guard wiring, explicit all-consumer activation,
and final linked timer guards. Do not report the 2 MiB saving as realized
before those gates.

## PPC state result ownership

`StateStorage` passively discovers the lease backend. It never activates it.
Every shared operation claims STATE before writing a tape, name, header,
metadata, or ordinary request. Matching ordinary receipts and central DONE
are both required before payload invalidation and result publication.
`takeResult` and `takeProjectResult` transfer a borrow to the caller; they do
not release the shared window. `quiet()` includes prepared, remote, ready,
borrowed, retained-local, and failed-cleanup states.

Each `Result` carries a four-byte, nonwrapping `ResultToken`. Call
`consumeResult(result)` or `consumeResult(token)` after the last payload or
metadata read. A copied old result cannot consume a later borrow, including
across an idle `init()`. Generation exhaustion fails closed. Consumption
accepts the caller's no-more-reads promise even if publication is temporarily
unavailable; the adapter retries cleanup and remains non-quiet. A permanent
lease failure quarantines the old mapping and token.

`consumeResult(result, true)` retains the outer STATE owner between stream
windows. The next request gets a fresh protocol ticket under that owner.
`releaseOwner()` ends a retained local owner; it cannot cancel or release
remote work. `abandon()` requests cancellation where supported and discards
the eventual real terminal result, including success when a mutation already
committed. Shared cancellation keeps the ordinary sequence/session/command
unchanged. Legacy cancellation keeps its existing CANCEL request behavior.

The savestate manager stores only the four-byte result token for deferred SD
restore. It retains the borrow through afterDraw and rendered-frame CARD
waits, consumes on the 600-frame timeout, and finishes the final window after
restore or RAM recovery. Stream timeouts abandon the pending request and
leave its ownership with the adapter until completion. TAS consumes copied
project results before chaining another request; tape imports hold the borrow
through all CRC checks and recording copies. Tape export consumes with
retained ownership before project commit.

The span adapters now support four pool banks, plus one staging span where
needed. The boot-latched map upgrades only on an idle shared transition.
`stagingSize()` and `archiveCapacity()` follow the global one-way map latch,
so an already acknowledged activation cannot expose the old 4 MiB staging
extent before this adapter's next poll. The legacy archive ceiling and all
emulator backend behavior remain unchanged before activation.

Native evidence includes 26 legacy client tests, eight shared-client tests
covering 17 adversarial cases, 44 TAS tests with an independent borrow
monitor, and the actual savestate completion/queue/streaming functions under
failure and recovery. Tests cover both receipt orders, blocked ghost claims,
preparation before claim, stale result identity, retained streaming owners,
abandoned successful completions, transient and permanent cleanup failure,
sequence wrap, result-generation exhaustion, all four imported banks, CARD
waits, and chained requests. No real Wii execution is implied.

`build/timewarp-state-lease/receipt.json` records all 18 exact-flag PPC object
compiles and source/object hashes. Against the frozen source-build objects,
the three changed modules add 3,184 initialized bytes on console JP or 3,316
on console US/PAL, plus 93 BSS bytes. Emulator variants add 92 initialized
and 58 BSS bytes. These figures include four-bank descriptor growth and the
seven-window checksum bound; they allocate no payload buffer. Final linked
placement and source-owner accounting are checked separately. The existing
128-byte mailbox control allocation is unchanged.

## Shared RAM store admission and recovery

`SavestateManager::initSharedStore()` is an explicit, one-way startup step.
It requires the shared map, initialized metadata, zero lifetime save generation,
empty legacy slot descriptors and metadata, no pending local or disk work, and
quiet ghost/state clients. It then acquires the CODEC lease and requires its
nonzero epoch before clearing the 32 KiB directory left by a previous launch.
There is no late reinterpretation of linear roots. Once the map is shared,
`validStore()` fails closed until the adapter is initialized; readiness itself
is only an initialization latch, so the frame loop does not scan the pool.

The candidate occupies the first `0x2F0000` bytes of shared staging. The final
`0x4E000` bytes serve as the second codec workspace during RAM work, or the
bounded incoming archive window under STATE ownership. RAM Quick encoding
emits blocks directly into the pending root. Deflate fallback measures first,
reserves bounded opaque blocks without releasing an old root, then encodes
and fully validates the candidate before committing. No whole-state temporary
buffer is allocated.

Retained repacking pins its old root during measurement and again during
encoding, allocating only between those borrows. Its external `StoredState`
generation remains unchanged. A shorter compressed stream alone is insufficient:
the commit must also reduce the allocator's physical extent, because replacing
shared Quick blocks with an independent Deflate stream can otherwise increase
memory use. Failed or unhelpful repacks abort while all prior roots remain valid.

Ordinary RAM loads pin the committed root and recheck its exact encoded bytes
and descriptor table before the single writing decode. Candidate admission has
already decoded and validated those immutable bytes. The existing live-video,
game-owner, restore-binding, audio, CARD and graphics protections remain around
the restore.

A streamed direct SD load retains a separately validated RAM recovery root
through both archive passes. Its scoped pin is released on every return. If a
writing pass fails, recovery rechecks the same pin before restoring with the
same owner/copy policy. The shared recovery fixture executes the production
admission and dispatch against real codecs and pool roots, covering success,
I/O failure, changed payload/identity, timeout, incompatible owners, and live
video/replay byte preservation. These native checks do not establish Wii
elapsed time, ARM cache behavior, or the complete shared SD import/export flow.
