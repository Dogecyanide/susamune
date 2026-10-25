# Standalone state sharing

## Native SD discovery (PR11)

Copy a `.mss` file directly into `Moonshine data/states` and refresh the SD state
list. No ZIP/helper is required. Noncanonical ASCII filenames up to 63 characters
are accepted, including `.MSS`. A valid archive header and exact declared length
are required before adoption. The backend assigns an unused numeric identity and
renames the file without changing its contents. Existing `.mss`, `.tmp`, `.used`
and name-sidecar stems are all reserved; an interrupted reservation or failed
rename retains the original file. Do not accept an operating-system overwrite
prompt when copying two identically named files; rename the incoming file first.

Discovery does not claim that the payload is restorable. Ordinary import/load
still checks metadata and packed checksums, snapshot/build compatibility, game
region, launcher configuration, scene, heap address/size and live resource owners.
Snapshot18 files already use a stable restore contract rather than requiring the
same mod binary, so an older compatible build can work without an allowlist edit.
Snapshot17 is refused because it predates removal of private ghost render packets
from the saved native draw graph; those pointers may refer to recycled objects.
Matching outer metadata size is not enough to migrate that graph safely.

Enter the saved stage/scenario before loading: the snapshot contains absolute
pointers into that stage's heap and keeps live DVD/audio/GX owners outside the
snapshot. Automatically entering a stage could reduce navigation, but cannot
guarantee matching heap/resource ownership or replace those checks. This update
does not add automatic stage transitions.

Twenty-two production archive-worker tests cover byte-preserving discovery,
occupied names, cancellation, rename failure, invalid/short files, normal import,
identity checks and bounded storage. Seven split tests and actual PAL PPC/ARM
compiles also pass; evidence is `build/pr11-storage-splits-check/receipt.json`.

## Optional desktop helper

Prototype 10, 2026-10-15. `tools/state_share/` is a Windows PowerShell/.NET
helper with file pickers and drag-and-drop `.cmd` entry points. Users need no
Python installation. Export packages one unchanged `.mss` and a readable
setup note; import copies that state to a fresh decimal `state_XXXXXXXX`
stem under `Moonshine data/states`. No existing file is overwritten. A persistent
`.used` reservation covers interrupted copies, and occupied `.tmp` and rename
sidecar stems are skipped. ZIP entries are read directly, never extracted to
paths supplied by the archive.

The helper accepts the production snapshot version **18** only. The shared
96-byte envelope, declared file length, bounded payload size, game ID, build
contract, scene and checksums are validated. Metadata CRC, payload CRC and
header CRC do not establish a valid inner snapshot by themselves, so the helper
also checks the nested identity, generation, metadata fingerprint, raw/packed
sizes, sequential memory spans, final heap span, and owner-profile identity,
fingerprint, anchor addresses and preserved ranges.

The actual PPC `StoredState` layout was checked by compiling the current
`src/savestate.cpp`, rather than treating the metadata as an opaque blob:

| Field | JP | US / PAL |
|---|---:|---:|
| Region entry capacity | 20 | 18 |
| Metadata bytes | 6960 | 6936 |
| Owner profile offset | 1016 | 992 |
| Generation offset | 6936 | 6912 |
| Metadata fingerprint offset | 6956 | 6932 |

Offsets in this table are relative to the metadata, after the 96-byte
envelope. The owner profile is 5920 bytes. Its FNV-1a fingerprint treats its
own checksum word as zero; the outer metadata FNV-1a excludes its final word.
Packed game-region offsets begin at zero, not the old reserved-header value.

The compiled restore contract allowlist stays consistent with
`state_compatibility.h`; this does not permit snapshot-17 files. The helper
does not relocate pointers, convert regions, rewrite configuration IDs,
decompress or validate game sidecars, or prove that the recipient has matching
live resource owners. All existing console checks still apply. The recipient
uses Y on the SD list and the ordinary Load bind for a direct restore that
keeps the three RAM slots; A remains the explicit import into a RAM slot.

Verification uses the actual PowerShell/.NET helper with synthetic
source-layout fixtures, corrupt envelopes and nested metadata, bounded ZIPs,
occupied filenames and byte-preserving import/export. The version test reads
the current production constant and launcher directory to catch stale helper
assumptions. A copied real Wii snapshot-17 file was correctly refused; no
snapshot-18 capture was available, so successful sharing between
two Wiis is **not yet verified**. Synthetic fixtures are not presented as
captured game states or evidence that every valid scene can restore remotely.
