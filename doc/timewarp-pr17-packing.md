# PR17 outbound cold stubs

Cold code calls retail and retained MEM1 functions through absolute stubs.
The shared-tail form reduces those boot-image bytes while preserving the
existing call ABI and all fixed MEM1 entry stubs.

Each target has an eight-byte entry:

```asm
li      r12, target@l
b       shared_high_tail
```

Targets with the same adjusted high half share a twelve-byte tail:

```asm
addis   r12, r12, target@ha
mtctr   r12
bctr
```

`li` sign-extends its immediate. The tail therefore uses `@ha`, including its
carry, rather than the unadjusted upper half. Addition wraps at 32 bits.
The sequence reaches the same address and leaves r12 and CTR equal to that
address, just like the original `lis; ori; mtctr; bctr` sequence. LR, CR,
XER and r0 remain untouched. It adds one local branch to each outbound call.

The source-call relocation still identifies its original target before
placement. This matters when a retained MEM1 function reuses the numerical
address of an old cold entry. Internal calls continue to point directly to
the relocated function, and external calls resolve through the assigned
MEM1 target.

`write_object` keeps the old sixteen-byte form by default. The pinned linker
explicitly requests shared tails only when building the outbound cold
image. Frozen incoming MEM1 stubs, their sizes and their placement remain
unchanged.

The cold-image proof checks the complete generated stub payload, every
linked function outside its authoritative branch relocations, and each
resolved outbound target. The final branch auditor independently checks
the exact entry/tail instructions and bounded relative branch before
comparing its result with the expected allocated target. The regular
96-symbol, five-string, nine-anchor and 34-hook protections remain required.

The PR16 JP reference has 352 outbound targets using 25 adjusted high
halves: 5,632 bytes become 3,116 bytes, saving 2,516 bytes before image
alignment. This is a reference-image measurement, not the final PR17 budget.

`test_cold_shared_tails.py` covers 108,304 instruction-semantics cases,
including every aligned low half at signed-carry and wraparound boundaries,
randomized incoming registers, branch reach/alignment, malformed entries and
tails, actual linked target identity, and unchanged default incoming stubs.

The metadata editor adds a label and branch to existing global methods.
Its anonymous tables are attributed only to the exact
`menuRowValue`, `adjustMenuRow` and `menuRowName` methods of
`metadata_display.cpp`. The proof requires a complete unique source
function, sole incoming references from that function, complete address
halves, and a table entirely covered by supported relocations. Branch
tables may target only aligned instructions within their own reader.
The label table may target only complete immutable, content-addressed
string atoms. Both partial-link and per-source proofs must agree; protected
baseline readers and tables remain rejected.

The console returns the previously retained Online update method to the
audited cold set, freeing its 2,344-byte MEM1 body. This does not change the
emulator's placement policy or any memory reservation. Final regional
capacity and packed-size measurements are recorded with the build receipt.
