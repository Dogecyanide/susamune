# Pinned source linking

`TIMEWARP_PINNED_LINK=ON` is an opt-in source build. It requires
`ENABLE_COMPRESSED_MOD=ON`; the default linker and default V3 output remain
unchanged. It is a build/transport capability, not a claim of real-Wii execution.

## What is proven

The current integrated editor and wider CPU results are documented in
`doc/timewarp-next-cold.md`: its immutable source capture and six build
receipts include the shared Store/RAM/SD callers and charge their full linked
cost. The original measurements below remain historical reference points.

The six clean builds in `build/timewarp-pinned-link/source-console` and
`source-emu` compile the current source, including the 257-input-span codec
change. All six link and pack successfully. Each checks:

- All 96 protected timer symbols retain their addresses, sizes and bytes.
- The nine named external timer dependencies retain addresses and bytes.
- All 34 existing retail hook writes are unchanged.
- Every retained final relocation matches its audited destination.
- Current per-source objects reproduce the supplied partial object exactly.

The ownership file contains addresses, sizes, owners, selectors and hashes. It
contains no code or data payloads. The build never reads baseline ELF/object
files. Those files are used only by the separate, create-only
`capture-ownership` command. The normal path consumes the freshly compiled
partial object and per-source objects from the current CMake build.

| Target | Region | Cold functions | Available MEM1 bytes |
|---|---|---:|---:|
| Console | JP | 227 | 67,540 |
| Console | US | 227 | 67,528 |
| Console | PAL | 227 | 67,556 |
| Dolphin | JP | 226 | 67,404 |
| Dolphin | US | 226 | 67,392 |
| Dolphin | PAL | 226 | 67,388 |

These holes are inside the existing reserved mod arena. The overall arena
reservation, timer caves/scratch and game heap floor are unchanged. A hole is
usable for new mod source; it is not automatically returned to the game heap.
The 160-byte incoming gateway island is already deducted.

## Source-growth evidence

`scripts/test_pinned_source_build.py` uses private copies of current source and
objects. For every region and target it grows the real `Checksum::crc32` body
from 136 to 468 bytes, adding no-op instructions and a call to a new function.
The new function is exactly 128 bytes and reads a new 128-byte data object.
The ordinary partial link and optional final linker place all 724 bytes inside
the recovered hole. The original checksum table stays at its existing address.
The final linker resolves the real checksum callers and the new code/data
references; all timer, dependency and retail-hook checks still pass.

The earlier PAL-only feasibility receipt remains at
`build/timewarp-pinned-link/receipt.json`. That experiment separately proved a
256-byte allocation and a 136-to-392-byte checksum growth, with a fully charged
duplicate 64-byte table. Its 712-byte allocation is not the later generic
source-build fixture's 724-byte allocation.

The default-OFF PAL ELF and V3 binary are byte-identical to the unchanged direct
`link_mod.py` / `gen_mod_bin.py` path. See
`build/timewarp-pinned-link/cmake-validation.json`.

## Link mechanics

`scripts/link_pinned_mod.py` identifies inputs by original section name plus
COMDAT signature, not by unstable ELF section indices. It assigns unique
selectors before GNU's final link. The original LLD partial-link step is kept;
GNU remains the final MEM1 linker. An analysis link resolves source relocations
and merge-pool offsets before cold code is moved.

The linker keeps established live inputs at their recorded positions. Supported
new or grown source-owned inputs use the recovered interval and explicitly
retired old source ranges. `doc/timewarp-owned-sections.md` describes the
pre-partial ownership split, range accounting and additional guards. The
same rule admits a shared COMDAT only when it is one complete weak function,
with identical bytes, attributes, group signature and named relocation targets
in every current source owner and in the selected partial-link section. Local
or section-relative targets are refused. The receipt records that proof;
discarded copies cannot silently hide different implementations.
The audited cold menu selectors are removed from MEM1. Incoming branches use a
small shared gateway island; vtables and audited CPU jump tables refer to the
new cold function addresses. Cold functions receive outbound far-call gates.
Only symbol and relocation metadata is rewritten before the final GNU link;
compiled input payload bytes are checked unchanged at that step.

Absolute cold section symbols become named `STT_NOTYPE` symbols. Leaving them
as absolute `STT_SECTION` values makes GNU emit unusable null-symbol relocation
records for the jump tables, even when the linked words happen to be correct.
The final relocation audit rejects unresolved records.

The source linker first recreates the partial object from the current source
object inventory. A stale partial object paired with newer objects is refused.
The final manifest is written only after the checks pass.

## Fixed islands and current limits

This is a conservative layout: existing live inputs remain fixed, rather than
packing every unprotected byte again. It supports new/grown isolated function
and data sections. Source-owned mixed contributions can grow if they contain
no protected anchor. Unsplit anonymous string-pool growth remains rejected; numeric
pool changes require explicit proof that no timer/dependency references or
overlaps the pool.

The four ordinary `.foxtrot.text`, `.foxtrot.rodata`, `.foxtrot.data` and
`.foxtrot.bss` inputs previously merged multiple sources during `-r`. In PAL console,
`Menu::drawText` and `Menu::fillBox` share a 9,992-byte per-source section;
`PracticeSession::paused` and `freezeRequested` share a 28,064-byte section.
The opt-in linker now names each source contribution before `-r`. Its companion
ownership metadata pins their original addresses. Non-protected source
contributions can grow independently; any attempted retirement across a
protected timer/dependency range is refused.

The timer's own 57-byte anonymous string input joins a 34,923-byte partial-link
pool, which GNU reduces to 34,466 bytes at `0x804657A8` in PAL console. Keeping
only named timer functions fixed is therefore insufficient. The optional path
pins its five protected literal identities using the source-derived atom audit
described in `timewarp-owned-sections.md`. New numeric inputs from sources that did not
previously contribute to a pool can be isolated and fully charged;
existing numeric changes need the independent unprotected-pool receipt.
Current string atoms are checked before allocation; missing or changed protected
literals remain refused. It never
copies frozen timer machine code into a replacement source.

The named dependency anchors are `branchWord`, `writeGameCode`,
`QftDisplay::draw`, `gQftDisplay`, `Menu::drawText`, `Menu::fillBox`,
`PracticeSession::paused`, `PracticeSession::freezeRequested` and `gSettings`.
The actual mangled names, addresses and byte hashes are in
`doc/timewarp-pinned-layout.json`.

Further allocator work must preserve relocation provenance for unusual
interior/one-past references and aliases. The current complete-target audit
fails closed when it cannot reconstruct the destination. Supporting every
possible source edit is not established by these fixtures.

The original cold menu functions now use their frozen symbol/section ownership
as selectors, so a current whole-function source edit can be recertified without
regenerating the baseline. Every selected input must still contain exactly its
one named menu function. Current object bytes and relocation sites must reproduce
the analysis link, and every external branch must have a relocation. The frozen
ranges must still tile the original menu hole; a larger current function lives
only in the analysis image before moving to MEM2. Its old range is never counted
twice. The receipt lists changed menu inputs and their current hashes.

Test branding has named literal sections in `build_branding.cpp`. Menu and crash
call sites retain their legacy literal arguments because the anonymous source
pool is shared with the pinned timer. The header renderer is outlined to keep
the protected mixed menu input within its original extent. Displayed labels
come from the new module; snapshot and protocol versions are separate.

The optional `state_quick_replay.cpp` registry covers 28 named new CPU
functions when they are live. Each must have one non-COMDAT, nonmixed,
exclusive source definition and no frozen layout entry. The existing audits
check its complete current body and relocation inventory. After certification
it no longer needs a new MEM1 allocation; it never contributes an old range
to retire. Calls use the existing charged 16-byte MEM1 gate island. Shared
copy helpers remain in MEM1, and absent/dead replay code adds no selectors.
The single PAL snapshot-8 relink records all new input hashes and verifies
that its retired-range list exactly matches the pre-relocation checkpoint.

The optional online prototype adds explicit new-module selectors for transport,
session, live presentation and race coordination. These use the same exclusive
whole-function checks; no baseline range is reclaimed twice. Incoming MEM1
and outbound MEM2 bridges still cost 16 bytes per distinct target. Transport's
unavailable Dolphin stubs are excluded from this console inventory. Constants,
state, jump tables and the new menu's COMDAT methods remain in MEM1; the final
link receipt, rather than object totals, determines the remaining free space.

## Transport and export boundary

The manifest records `cold_image` (path, VMA, size, SHA-256),
`pinned_link_receipt` (path, SHA-256), and explicit `transport_environment`.
The proof receipt repeats the cold identity and records `passed`, target and
region. The packer cross-checks these bindings.

Console cold code is linked at `0x91E3F0A0`; true emulator cold code is linked at
`0x71E3F0A0`. Dolphin transport is explicitly flagged and is not accepted by the
console loader. The cold header/descriptor offset is 160 bytes in either case.

With pinned linking enabled, the existing `dol` and `gecko` exports fail before
calling the old linker. They need a verified early cold-copy route and must not
silently overwrite the pinned ELF with a normal linked image. The owned runtime
pilot is separate from this source-build proof. Real-Wii mapping, instruction
cache/reset behavior and runtime performance remain separate gates.

## Reproduction

PR14 adds two narrow current-input proofs. The 9-byte finish-breakdown RGB
defaults from `susamune_cfg.h` are checked against their exact immutable
payload, local-object symbol and interior HA/LO code references in the two
approved source files. Each copy receives a source-owned section before the
partial link; bytes and definitions are checked again afterward. Writable,
grouped, aliased, relocated or previously frozen copies are rejected. This
does not grant general shared-data growth permission.

The new wireframe `edgeVertices` switch table uses the existing COMDAT table
audit under an explicit source/function identity. Its sole complete weak
reader, complete interior self targets and current source-object equality
are required; that new identity must be absent from the frozen layout.
`test_pinned_header_constants.py` and `test_pinned_menu_tables.py` exercise
the positive and rejection paths. No frozen layout or timer receipt changes.

PR14 retains the 64 explicitly inventoried new CPU functions from
`live_race.cpp`, `live_race_session.cpp` and `live_relay.cpp` in existing MEM1
holes. The same sole-source, whole-function, relocation and protected-range
audits run before retention. These functions have no frozen input ranges to
reclaim; their final addresses, sizes and source hashes are recorded in
`retained_mem1_cpu_inputs`. Compressing them with the other initialized MEM1
bytes saves JP boot-file space. All allocator bounds, heap reservations,
regional staging ceilings and runtime codecs remain unchanged.

Configure a fresh Ninja build with `-DVERS="jp;us;pal"`,
`-DTIMEWARP_PINNED_LINK=ON` and `-DENABLE_COMPRESSED_MOD=ON`, then build
`mod_bins`. Select `-DIS_EMULATOR=ON` for the distinct Dolphin target.

Run `scripts/test_pinned_source_build.py` after producing the two private source
build directories named above. Results are retained in
`build/timewarp-pinned-link/source-tests.json`; source files are never modified.
The negative fixtures cover mixed-section growth, merged-string changes,
capacity exhaustion and a stale partial object.

`scripts/test_pinned_comdat.py --build build/timewarp-stream-console` checks
the three-owner TAS capacity helper and rejects a changed discarded copy,
a changed relocation target and a source-local relocation. Its private receipt
is `build/timewarp-pinned-link/comdat-test/receipt.json`.
The six stream foundation builds pass with the 644-byte helper allocated once
per image; see `build/timewarp-pinned-link/comdat-builds.json`.
