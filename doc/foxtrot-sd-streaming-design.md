# SD restore with a full RAM pool

Direct SD loading currently stages the complete compressed file in the 4 MiB
temporary area and the unused end of the RAM-state pool. Three occupied slots
can leave too little temporary space even though the selected SD file is valid.

The implemented capacity fallback reads through the existing 4 MiB temporary area. It does
not borrow disc, ghost, statistics, or retained-state storage. Archive version 1
and the two retained-pool boundaries remain unchanged.

## Transaction

1. Pin the selected file identity, build/configuration, scene, pool occupancy,
   and slot generations. Read its checked header and metadata.
2. Find an intact RAM slot compatible with the current scene and owner profile.
   Before any live write, compile its restore spans, check its compressed CRC,
   and fully decode it without writes. Its bytes and descriptors remain owned
   throughout the SD transaction.
3. Read and decode the complete SD stream without writes. Validate all framing,
   length and Adler checks. Record a checksum for every fixed 4 MiB window.
4. Recheck current owners, then read the SD windows again. Require the same
   header identity and each window's first-pass checksum before decoding that
   window into live state. Use the existing owner-preserving copy policy.
5. On success, run the existing SD-load finalization. All RAM slots retain their
   bytes, metadata and generations.

Preflight errors leave the current game state unchanged. A second SD read can
fail after some live bytes have changed; a first-pass checksum cannot make an
SD card immutable. In that case restore the prevalidated RAM recovery slot from
its unchanged local bytes and precompiled spans, then finalize that slot and
explicitly report **"SD read failed; restored state N"**. Do not invoke ordinary
load admission against the partially restored world. An impossible failure of
the immutable recovery stream is a broken invariant and cannot resume play.

If no compatible intact recovery slot exists, use the existing fully staged
path where it fits. Capacity refusal remains safe otherwise. Import into a RAM
slot retains its separate capacity check.

## Transport and ownership

Transport version 5 appends a bounded window-read command. Every window is read
from the exact selected archive, with its complete header/metadata checks and
length bounds, into the fixed staging buffer. No request contains a destination
pointer. The worker owns that buffer until a matching session/sequence/command
receipt, including errors and cancellation. The client flushes before handing
over and invalidates only after the matching receipt. The codec consumes one
window before it can be replaced. Existing archive/file operations retain their
checked identities and bounded ARM work slices.

The maximum archive size is already bounded by the retained-pool capacity, so a
fixed five-entry window-checksum array suffices. Codec workspace stays exclusive;
window checksums must not use its borrowed CRC table while a decoder is live.

## Validation

The host harness `test_savestate_streaming.py` compiles the production window
reader, recovery admission and restore dispatch with a reduced temporary window
and a completely occupied three-slot pool. Both zlib and MSL4 restore correctly;
preflight cancellation, malformed streams, changed owners and bad payload CRCs
leave live bytes unchanged. Second-pass I/O failure, changed bytes, changed file
identity and missing receipts restore the prevalidated RAM slot. Every case
checks retained payload bytes, generations, capacity and buffer guards. Separate
codec, client and worker tests exercise their actual production implementations.

These checks do not substitute for a real-console streamed restore. Live build,
timing and console results are recorded separately when available.

The maintained coverage includes:

- Both codec formats decode across arbitrary reader boundaries and reject
  truncated, malformed, appended and bad-Adler input before writes.
- Changed windows, I/O failures and cancellation cannot expose unowned bytes.
- Failures after live writes restore the prevalidated RAM slot and retain all
  three slots byte-for-byte, including generations and ghost prefixes.
- Full-pool valid SD restores succeed without increasing any reserved memory.
- Missing recovery, incompatible owners and ordinary full staging remain safe.
- The runtime load finalization and ordinary QFT formulas remain shared.
