# Native Dolphin transport and parity

PR43 uses standard Dolphin's built-in Broadband Adapter (SerialPort1=12),
not the companion mailbox. `dolphin_bba.cpp` polls the native EXI device;
`dolphin_network.cpp` owns bounded ARP, DHCP and UDP state in the existing
2,784-byte transport window. The user confirmed JP Dolphin/Wii play, controller
input, responsive two-way movement and per-player Mario colours. This does
not establish four-player acceptance or complete file/website parity.

PR45 development adds native TCP (lwIP), certificate-verified HTTPS (BearSSL)
and the Delfino Ghosts browser. DNS uses a separate TCP lookup so Dolphin's
special UDP DNS handling cannot redirect the website query. Browser cancellation
and connection reuse do not shut down an active online room. TLS checks the
hostname, trust chain and date. Entropy comes from a one-time setup seed and a
verified, persistently advanced two-copy record; clocks are not entropy.

`scripts/setup_dolphin_data.py` prepares a private Moonshine data directory and
Slot B GCI Folder configuration. It is an offline setup utility, not a running
companion. Region directories are JPN, USA and EUR; the utility accepts the old
JAP spelling during migration and refuses conflicting saves. Do not distribute
this private directory in a shared ZIP: it contains settings and TLS seed data
and account credentials. Never include `ms_delfino_link` or `ms_tls_seed` in a shared package.

Native storage uses Sunshine's retail CARD functions, with Slot A left for the
normal game save. The worker borrows the existing card workspace under the card
thread's lock and services bounded sectors. The directory is still a virtual
memory card, with its capacity and directory-entry limits; it is not unrestricted
host filesystem access. Ghost files use the same canonical format as Wii,
wrapped in GCI files. Personal and imported libraries have separate namespaces.
Downloads and personal saves share one new-file transaction, commit the header
last, and never overwrite an existing file. Loads revalidate the full file and
reject stale catalogue identities.

The native service image owns TCP/TLS, HTTP, entropy, account and archive workers,
website JSON and shared ghost catalogue
validation in an existing unused Dolphin aperture span. It has checked ABI tables
and a source/compiler/image receipt. The game-side library calls the same
catalogue validator as Wii. Dead-stripped baseline ghost functions newly enabled
on Dolphin have explicit ownership checks; no original linked span is reclaimed
for them. Memory reservations and all 96 protected timer symbols remain fixed.

Evidence is scoped: the user confirmed PR44 cross-network two-player races,
Stageloader progress, colours and about half an hour of stable play. PR45 private
standard-Dolphin runs verified HTTPS browse/next/reopen/filter, native file
create/read/write/list/delete, and an actual 76,800-byte website ghost download.
That ghost appeared in Imported ghosts and loaded through the normal identity
API for racing. It survived restarting Dolphin; first/repeated loads in the fresh
process took 2.09/2.02 seconds. An earlier first load took 75.61 seconds and was
not reproduced on restart; its cause is not established. These are private API
triggered runtime checks, not complete controller-driven menu acceptance. Receipts:
`build/pr45-runtime/native-browser1/browser-verification.json`,
`build/pr45-runtime/native-library1/library-verification.json`, and
`build/pr45-runtime/native-library2/library-verification.json`.

PR45 now implements native device linking and uploads through the same account
protocol as Wii. Each HTTP operation is advanced across frames. Link credentials
live in two verified GCI records; token rotation first commits a tombstone, then
commits and reads back the replacement before continuing. A failed or interrupted
rotation cannot silently reuse the old refresh token. Local protocol tests cover
link polling, descriptions, upload/publish, interruption and journal corruption.
Actual standard Dolphin linked with the user's approval and retained the account
across restart. The user's unchanged PAL Ricco 4 full ghost uploaded and published
in 55.515 seconds; the user confirmed it on the website. The private receipt is
`build/pr45-runtime/native-upload-pal1/approved-upload-verification.json`.
Never include that runtime's credential GCI files in packages.

Native state/TAS storage is implemented in `native/dolphin_https/archive.cpp`
and `archive_tas.inc`. The existing mailbox and canonical metadata/payload
validators are retained. Exports create new files, commit their header last, and
use a persistent ID journal so deletion/restart cannot reuse stale identities.
TAS components are immutable; the inactive project manifest is published only
after checking all referenced component headers, metadata and payload CRCs.
Interrupted publication retains the preceding manifest and its components.
Two manifest generations remain usable; cleanup never deletes a referenced part.
A deletion tombstone is verified before component cleanup. Host fault-injection
tests cover these paths. Actual JP Dolphin exported a 7,129,881-byte state in
229 seconds, imported it in 56 seconds, and restored Mario's saved position after
moving him. The state survived restarting Dolphin. A TAS with a real 55-frame
recording saved, reopened, replayed and finished with matching fingerprints.
Receipts: `native-archive4/archive-verification.json`,
`native-archive5/archive-restart-verification.json` and
`native-archive5/tas-recording-verification.json` under `build/pr45-runtime`.
The earlier zero-frame project correctly refused replay; it is not the replay proof.

`tools/dolphin_online/manage_data.py` exports/imports separate ghost, state and
TAS folders while excluding credentials, entropy seeds and settings. It also
converts canonical `.smsghost` files to/from the GCI wrapper. Run it with Dolphin
closed; no companion remains running. In-game Export help explains that PC file
export uses this tool. Website publication remains an in-game operation.
Whole-bundle preflight checks paths, hashes, identities, conflicts and card limits
before writes. Existing conflicting files are never replaced.

The card has roughly 16 MiB and 127 directory entries per region, shared by these
files. GCI Folder does not bypass emulated card speed/capacity. Large state/TAS
writes can take minutes; a new TAS with the measured 7.1 MB Beginning took 285
seconds. Fast RAM savestates are separate. Archive unused files outside the live
GCI folder, retaining all components belonging to a TAS. This is functional
persistence, not Wii file-speed or capacity parity.

The final packages use `scripts/package_dolphin_native.py`, verify full BPS
application and unchanged retail content, and include only allowlisted tools,
patches, licenses and scoped receipts. Japanese assets replace Dolphin-specific
labels within the unchanged allocation. Setup configures BBA HLE, 32 MiB MEM1 and
Slot B while preserving Slot A and unrelated settings. Neither packages nor
receipts contain private account links or user files.

The final Dolphin Export-help change affects only `src/menu.cpp` and
`src/ghost_storage.cpp`, guarded from console builds. Earlier full storage/upload
runtime receipts remain attached to their original builds. The packaging review
checks every recorded source hash, both reviewed replacements, the unchanged
native image, and the new PAL production boot/export-guidance check. It does not
claim the long archive/upload cycles were repeated after this presentation fix.
The revised Japanese catalogue passes 25 checks and stays 100,608 bytes.

Remaining acceptance: four players, Linux/macOS runtime, and ordinary
controller-driven menu coverage. Personal-save failure/duplicate/stale-identity
paths have host tests; full in-game personal-save acceptance remains separate. Watch was also verified through its
menu-owned preparation/load/start sequence: it reached the downloaded Noki Eel
stage with observer phase 5 and visible playback. Removing the test download
returned the imported catalogue to zero. These receipts are in the same
`native-library2` directory; the current cold image matches the verified runtime.
Four-player acceptance is still pending. Feature coverage must not be described
as identical storage performance or complete platform acceptance.

Protocol references: [DNS wire format](https://www.rfc-editor.org/rfc/rfc1035.html),
[DNS response matching](https://www.rfc-editor.org/rfc/rfc5452.html).

## Historical companion implementation and earlier probes

The following describes the previous companion transport and its evidence;
it is not the current emulator networking path.

`tools/dolphin_online/bridge.py` carries the existing region-independent UDP
protocol between an emulator build and the same relay used by Wii clients.
It discovers a supported running Windows Dolphin process and a checked game
identity at `0x71901000`. The 2,784-byte mailbox ends at `0x71901AE0`, after
the existing settings/hoverless windows and before the extra state pool.
Its C header asserts the bounds and cache-line ownership.

PPC writes the game identity, command, producer/consumer indices, TX slots
and replaceable latest pose. The companion writes its identity, status,
RX slots and diagnostics. Each publication withdraws its generation before
copying, then commits the new non-wrapping generation. Readers reject torn
copies. Both sides reject old epochs and queue counts outside four slots;
the companion verifies the immutable game identity before every write.
The companion accepts incoming UDP only from endpoints it has sent to.
Relay credentials, room generations and peer session checks remain in the
existing native clients. There is no input injection or frame lockstep.

Game and companion heartbeats advance every 100 ms. Three seconds without
progress retires the connection. The game instance binds an attachment to
one boot, and a fresh companion chooses a new nonzero epoch. Publication or
heartbeat rollback retires a detected Dolphin rewind. Startup and restart
do not reuse queued packets. A Windows named mutex excludes a second
companion for one process. Emulator sockets use an ephemeral local port,
allowing a relay or another Dolphin to run on the same PC.

## Graphics storage

Dolphin's CPU fake-VMEM cannot back ghost display lists, vertices or textures:
`MemoryManager::GetSpanForAddress` resolves device accesses only into real
MEM1/EXRAM. The emulator build therefore puts its existing two 90,112-byte
body heaps at `0x81800000` and `0x81816000`; both end at `0x8182C000` inside
the bounded `0x81800000..0x81850000` window. Wii addresses and heap sizes,
the existing MEM1 attachment heap, recording bounds and state pools do not
change.

The user enables 32 MiB physical MEM1 in Dolphin. The disc still requests
24 MiB simulated memory. Retail `Config24MB` narrows DBAT2 to an 8 MiB map
at `0x81000000`, so physical storage alone is insufficient. Before creating
the ghost heaps the emulator checks physical size, simulated size, root
heap end and DBAT2's exact retail mapping, then widens that data map to
16 MiB. The original mapped prefix is unchanged. It does not change an
instruction BAT, the game's arena or simulated-memory word. Unexpected
configurations fail closed before creating these heaps.

Sources:

- [Dolphin memory initialization and device pointer resolution](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/Memmap.cpp)
- [Dolphin physical memory settings](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/Config/MainSettings.cpp)
- `build/reference-sms/libs/dolphin/src/os/OSMemory.c`, `Config24MB`.

## Focused validation

`scripts/test_dolphin_live_transport.py` checks ownership/bounds, torn and
exhausted publications, old epochs, invalid counters, heartbeat retirement,
game identity replacement, latest-pose replacement, foreign UDP senders and
oversized packets. Its loopback test runs the actual C++ JP/PAL relay/session
clients through two companion mailboxes and real UDP sockets, including
two-way poses, departure and stale-session rejection.

`build/timewarp-pr13-memory-probe/receipt.json` records an actual Dolphin
2606a PPC memory probe using an isolated profile and historical PAL fixture.
Physical memory was 32 MiB while simulated memory stayed 24 MiB and the root
heap/arena ended at `0x817FEBE0`. An actual PPC `memset` reached the extra
MEM1 after the checked DBAT2 change. This is CPU/address evidence; it alone
does not establish a rendered ghost or Wii/Dolphin gameplay result.

`build/timewarp-pr13-runtime/run3/transport-verification.json` records the current PAL build
executing its real PPC transport through a local UDP socket: control send and
receive, latest-pose publication, stop/reopen, and companion restart all pass.
The running production bootstrap matches the exporter byte for byte, and the
complete cold payload matches after its early copy. Diagnostic input and
callbox code occupy a separate private section. This is PAL transport/boot
evidence, not a real Wii peer or a standalone Dolphin library-import test.

The same run's `ghost-render-verification.json` binds a fresh session recording,
ordinary same-route promotion, six successful model submissions and the inspected
`session-ghost-4.png`. The image shows a translucent Mario body partly overlapping
the live player in Plaza episode 2. Both ghost heaps use the bounded extra MEM1
window. Choose Mario appearance on standalone Dolphin; the launcher-provided
Shadow/Piantissimo asset bundles are unavailable there. This check does not
cover saved-file Watch, two bodies or a real Wii peer.
