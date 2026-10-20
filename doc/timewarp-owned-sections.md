# Source-owned pinned sections

The opt-in linker preserves per-source ownership before the partial link.
This permits storage/TAS source growth without moving the timer or its fixed
dependencies. The default build path is unchanged.

`pinned_source_sections.py` gives unique metadata names to each non-COMDAT
pragma contribution and local static function input. Renaming changes section
headers/string metadata only; it verifies every allocated payload is unchanged.
The ordinary partial link then runs on those current objects. Shared weak
functions retain their COMDAT handling and exact-copy checks.

PAL console has 55 original pragma contributions. Including local functions,
410 source-owned contributions are recorded. Local functions matter because
two files can emit the same header helper name with independent storage;
merging those names again would lose source ownership as consumers grow.

## Frozen evidence and current inputs

`doc/timewarp-pinned-source-owners.json` is a 1,017,155-byte companion to the
original layout receipt. It records addresses, attributes, hashes and source
owners; it contains no executable/data payloads. Its original baseline link
checks pass for all six region/target variants. PAL console reconstructs all
542,527 initialized baseline bytes exactly. The original layout and timer
receipts remain untouched.

Shipping links use current compiled objects only. Before transforming them,
the driver independently reconstructs the original partial object and checks
its identity. After transformation it checks each source contribution against
the new partial object's bytes, attributes, definitions and owner. The
companion metadata supplies addresses, never old code.

All 96 timer symbols, nine named dependencies, 34 retail hook writes and final
relocation targets are still checked. A source input that contains an anchor
cannot be retired. An obsolete input may disappear only when ownership is
unambiguous, it contains no protected range, and it is neither a cold selector
nor a shared merge pool. An obsolete COMDAT can disappear only when the frozen
record proves it was one whole weak function with the same group signature.
The final source link must resolve all remaining references normally.

Grown retail hook bodies retain a 16-byte entry at the original hook target.
That entry is independently checked against the current source body address;
the old entry cost is excluded from its retired range. The manifest uses that
checked entry, preserving the existing retail write. This supports current
`onUpdate` and `onAppInit` growth without weakening the hook comparison.

## Capacity accounting

Cold branch targets retain their analysis-time identity until classification.
The allocated address of a new MEM1 function can equal the former address of a
different function now in MEM2. Translating first and then looking that number
up in the old cold-function map silently calls the wrong function. The linker
therefore carries a separate original-to-final map for outbound veneers;
internal cold calls continue to use original identities. A separate final audit
reads the untouched analysis ELF's relocations, decodes each emitted branch,
and checks either its final cold destination or the exact outbound veneer.
`test_pinned_cold_target_identity.py` covers both address collisions and ordinary
internal/external calls. Timer, anchor, hook and ownership baselines are unchanged.

Moving a grown function or source contribution vacates its old range. The
allocator combines those exact retired ranges with the original cold-menu
hole, refuses overlaps with protected inputs, and fits larger allocations
first. It tracks remaining intervals, including fragmentation. Every final
allocation has a linker assertion bounding it inside an owned interval;
the manifest also refuses overlapping or out-of-reservation sections.

Receipts distinguish allocated bytes, retired bytes, remaining intervals and
the largest remaining interval. `recovered_bytes_remaining` is the sum of the
remaining intervals. It no longer implies one contiguous hole. Counting a
moved source body as entirely new MEM1 consumption would overstate its cost;
counting its old range twice would overstate recovery.

The private predecessor at `build/timewarp-owned-sections/receipt.json`
proved real storage growth and placed 256 bytes of new code/data in retired
storage space. The production-path fixture is
`build/timewarp-owned-tests/receipt.json`; it repeats that reuse with the
current source and checks all protected symbols/relocations. Its source files
are private copies, including the added growth instructions.

## Numeric constants and strings

The four-bank emulator initializer introduced a 32-byte numeric input in both
savestate and state_storage. If merged normally, these enlarge the existing
`.rodata.cst32` pool from 128 to 160 bytes. The original ghost, records and codec
inputs remain unchanged.

`doc/timewarp-pinned-merge-sources.json` records which sources originally
contributed each numeric merge input and binds that inventory to the immutable
source-owner metadata. The preprocessor isolates only new numeric inputs from
new contributors. Both new 32-byte copies are charged, preserving the original
128-byte pool. `timewarp-pinned-numeric-pools.json` also records every original
numeric pool's protected incoming references and overlap. Only a pool proven
unprotected can be reallocated when existing contributors change it. The
inventory, original address/size/hash, entry width and protection flags are
validated against the immutable layout. `.foxtrot.rodata` legitimately has
entry width zero. Unsplit shared string-pool changes still fail closed. No baseline
literal bytes are copied into the new image.

The pending-transfer status string therefore has an explicit source section.
Adding it to the anonymous merged string pool would shift protected timer
literal targets. Named source data can instead be charged to recovered space.

### Anonymous menu constants

`timewarp-pinned-menu-constants.json` adds provenance for eight immutable menu
inputs per target/region: three padded ghost labels, four compiler-generated
Creation help string tables, and the Ghosts help string table. It binds to the
unchanged layout, source-owner and timer receipts and stores no payload bytes.
The source objects, partial objects and linked images must match those existing
hashes when the evidence is captured. Each input has exactly one matching menu
source section, no named definitions, and only menu function readers. String
tables have one relocated readonly string pointer per entry. Neither the
constants nor their readers overlap protected ranges, and no protected
relocation targets them.

Ordinary builds validate this receipt without loading the frozen objects. A
missing proven input may retire its old range; an existing contribution is
verified against the current menu object before it can grow. The receipt in
the completed build names every retired constant and its provenance. Mutable
storage, merged strings, ambiguous ownership, other generated table kinds and
protected references retain the original rejection rules.

Reproduce this evidence with `python scripts/pinned_menu_constants.py --verify`.
Only this audit operation needs `build/baseline-{console,emu}/susamune_pre_<region>.o`,
`susamune_<region>.o` and `CMakeFiles/susamune_obj_<region>.dir/src/menu.cpp.obj`;
each is hash-locked by the existing receipts. The capture command is create-only.
`test_pinned_menu_constants.py` reproduces all six inventories and exercises the
retirement, provenance, protection, mutable-data and malformed-table rejection
paths. This audit does not authorize shared `.rodata.str1.1` changes.

### Protected string atoms

`timewarp-pinned-string-atoms.json` separates the protected literals from the
rest of the original shared string pool. The frozen final images do not carry
relocations, so capture reads the frozen partial relocation sites and decodes
the actual final HA/LO or full address bytes. It groups identical targets rather
than guessing adjacent instruction pairs. Each protected reader and source
literal is checked against the existing source-object hashes and linked bytes.
All six builds have twelve protected reference sites and five literal identities;
one literal is a suffix of another, leaving four separate storage ranges.

The current per-source objects are split into complete NUL-terminated atoms
before partial linking. Content-identical atoms share one section. Source
relocations retain their interior offsets, including terminating NUL targets;
true pool one-past references, implicit addends, cross-atom named objects,
mutable strings and unsupported grouped/width variants fail closed. Existing
named symbol size, type, binding and visibility are preserved. Only metadata
and string section boundaries change; code and other allocated payloads do not.
After exact current atom bytes are verified, merge flags are cleared so the
final linker cannot remerge suffixes and change their addresses.

Protected atoms retain their frozen addresses and their checked suffix aliases.
The other original pool ranges become allocator space for current strings and
other current inputs. Every payload byte comes from current source objects;
no deleted literal is kept as padding. Analysis and final links recheck the
protected strings' exact bytes and all twelve reference targets, alongside the
existing timer symbols, anchors, hooks and capacity ceilings. Ordinary builds
need only the new provenance receipt; `pinned_string_atoms.py --verify` reproduces
it using the same hash-locked baseline artifact paths described above.

`test_pinned_string_atoms.py` exercises real PPC objects with shared strings,
suffix and interior relocations, named aliases, signed HA carry, inconsistent
address halves, bad bounds, mutable/implicit-addend inputs and changed protected
bytes. The numeric-pool audit now proves absence directly from frozen partial
relocations, reproducing the existing receipt without changing it, and rejects
any new protected-to-numeric-pool relocation in the current plan.

## Focused checks

`scripts/test_pinned_owned_sections.py` compiles private real-source fixtures.
It rejects wrong source ownership, stale metadata/baseline binding, retirement
across an actual protected anchor, compiled growth of `Menu::drawText`, and a
changed protected timer literal. Its positive storage fixture verifies relocation
targets and places 128 bytes of code plus 128 bytes of data in retired ranges.

The resumed receipts are `build/timewarp-owned-tests-resumed/receipt.json`,
`build/timewarp-numeric-tests/receipt.json`, and
`build/timewarp-comdat-resumed/receipt.json`. Numeric tests reproduce the six
frozen pool inventories, reject four inconsistent metadata records, and prove
a real changed `ghost.cpp` float constant can link without changing the timer.
A corrupted fixed hook veneer is rejected. COMDAT tests reject a mismatched
discarded body, changed global target and local target; a separate
`build/timewarp-comdat-editor/receipt.json` covers two identically named
`.foxtrot.text` sections distinguished by their group signatures.

`timewarp_source_snapshot.py --capture` creates an immutable `src`, `include`
and `vendor` input tree, checking hashes before and after the copy. Six builds
then compile that capture into private object directories, including the
vendor-relative include paths. Capture 3 incorporates the shared Store/RAM/SD
adapter and the Shined label; it precedes the later capacity-status diagnostic.
It avoids mixing concurrently edited sources into a nominally six-way result.

The later single-PAL checkpoint is
`build/timewarp-integrated-checkpoint-7/receipt.json`. It combines shared Store,
the optional heap-gap prototype, current capacity diagnostics, wide CPU
relocation and `3.0.0 Timewarp` branding. The immutable inputs are
`build/timewarp-integrated-source-snapshot-7`; `compilation.json` records 68
objects reused from byte-identical snapshot-6 inputs and one rebuilt crash
report. Both prototype flags were on for this checkpoint; their defaults
remain off. No other-region or new runtime claim follows from this build.

This PAL image leaves **137,775 bytes (134.55 KiB)** across recovered MEM1
intervals, with a largest interval of 65,060 bytes. That is 6,703 bytes above
the 128 KiB target after the integrated Store/lease/adapters, heap-gap guard and
branding costs. Its 648 relocated functions occupy a 192,960-byte cold payload;
the complete V4 package is 470,112 bytes. All 96 timer symbols, 9 dependency
anchors and 34 retail hook writes match the frozen baseline. Linked new labels
and the enabled prototype flags are recorded separately in `branding.json`.

The heap-gap reader callback uses the header's exact `unsigned int` parameter
types: this PPC ABI's `u32` typedef is `unsigned long`. The mapped retail vtable
declaration has external linkage outside the anonymous namespace.

Snapshot 8 adds the prepared Quick encoder and RAM replacement replay planner.
`build/timewarp-integrated-checkpoint-8/receipt.json` is one fresh PAL compile
and link with shared Store, heap-gap and Quick replay enabled. All 70 object
inputs and all 96/9/34 protected checks pass, with no numeric-pool changes.
The resulting 127,203 usable MEM1 bytes are 3,869 bytes below the 128 KiB goal;
checkpoint 7's larger free total must not be used for the replay-enabled image.
The V4 package is 476,544 bytes. No runtime/SD or other-region work accompanied
this source checkpoint.

The follow-up `build/timewarp-integrated-checkpoint-8-replay-cold/receipt.json`
reuses those exact objects. Its 28 new replay source inputs each contain one
whole, exclusively owned function and have no entry in the frozen layout.
They are removed from new MEM1 allocation after the usual object/analysis
relocation proof. They contribute no retired range. Four added incoming gates
are charged to the existing MEM1 gate island. The receipt proves the entire
retired-range list is unchanged and records every new input's owner, symbol,
size, source hash and zero retired bytes. This recovers 8,188 net bytes,
leaving 135,391 usable bytes, 4,319 above the 128 KiB target. All protected
checks still pass. Default-off or dead replay code does not activate this
optional registry; shared helper bodies are excluded.

Runtime execution, transport capability negotiation and Wii throughput remain
separate gates. These changes reclaim space inside the already reserved mod
arena; they do not lower the game's heap reservation.
