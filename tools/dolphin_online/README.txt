Moonshine 3.0.0 - Dolphin online companion (Windows and Linux)

Use the matching Moonshine Dolphin build and 64-bit Python 3.10 or newer.
Linux users: follow README-LINUX.txt for the launcher and process permissions.
The Wii player uses the matching Nintendont build. JP, US and PAL can share
a room; PAL must use 60 Hz. All players must use the same mod/protocol version.

First extract this entire ZIP. Drag your clean Sunshine ISO onto Apply-ISO.cmd.
It chooses the regional patch and creates a separate " - Moonshine.iso" file
beside the original. Existing files are never replaced. Boot that new copy in
Dolphin. The patcher checks the source, patch and finished ISO checksums.
For a command-line alternative: python apply_patch.py "path to clean.iso"

1. Stop emulation. In Dolphin, choose File > Open User Folder, then open
   GameSettings. Edit GMSJ01.ini (JP), GMSE01.ini (US) or GMSP01.ini (PAL);
   create that file if it is absent. Under its existing [Core] section,
   add or update these three values from Dolphin-game-settings.ini:

   RAMOverrideEnable = True
   MEM1Size = 33554432
   MMU = False

   Add a [Core] section if none exists. Preserve every other setting and
   section; do not replace an existing game-settings file with the sample.
   These values enable 32 MiB physical MEM1 and leave MMU off.
   Keep the disc's original 24 MiB simulated-memory setting. The mod reserves
   less than 320 KiB beyond retail MEM1 for ghost bodies and model resources; the game's heap,
   savestate capacity and ghost recording length stay unchanged. The mod
   refuses to allocate those bodies when this memory setup is missing.
2. Boot the Moonshine Dolphin build, then run start-windows.cmd. Keep its
   window open. It discovers the running Dolphin and prints the game region.
   With multiple Dolphins, run: python bridge.py --pid PROCESS_ID
   Mario, Shadow Mario and Piantissimo are available throughout the game.
   The patch includes checked ghost models from your own disc.
3. In Online, the host selects Room size (2, 3 or 4) before Create room.
   Each guest selects Join room. Everyone gets a 14-character code.
   The host and EACH guest exchange their codes and enter the other person's
   code: the host uses Guest 1 / Guest 2 / Guest 3; guests use Friend's code.
   Guests only exchange codes with the host. Select a connected guest to kick
   them; the host must enter their code again to invite them back.
   If everyone is on the same router, exchange the Same-network codes instead.
   Address discovery still needs internet. Different homes use Your code.
   With Dolphin, enter codes at both ends, including when Dolphin is hosting.
   Keep the companion running. No relay address is entered in this version.
   Direct connections can still fail on restrictive networks; this build
   does not include a fallback relay. Use NAT test to identify that case.
4. Disconnect in Online before closing the companion. If Dolphin or the
   companion restarts, reconnect the companion and create or join a new room.

PR32 writes diagnostic logs automatically beside bridge.py in connection-logs.
The startup message prints the exact filename. Logs summarize packet timing,
queueing, connection changes and group members once per second, capped at 4 MiB
per companion run. Closing the companion flushes the final buffered entries.
Send the latest .log from every player after a bad test. Wii logs are in
/Moonshine data/logs on the launcher's SD/USB device; wait five seconds after
leaving Online before powering off. Logs include network addresses, not room
secrets or raw controller inputs. A logging failure does not stop networking.
Every player needs PR32 (protocol 7), including the new Dolphin patch/companion.

The companion is required for Dolphin networking. It uses no administrator
features or third-party Python packages, changes no Dolphin settings, and
writes only the small networking mailbox owned by this mod. It carries UDP
packets; each machine still simulates its own player. The peer session checks are identical to the Wii path.

Pausing Dolphin stops the heartbeat. After three seconds the companion
retires its socket; resume emulation and reconnect Online. Dolphin savestate
rewinds likewise retire a detected old session. Moonshine's own savestates
do not rewind this mailbox.

Ghost bodies require the included physical-memory settings because Dolphin's
CPU-only fake memory is not visible to the graphics processor. The existing
MEM1 attachment heap is retained. Model resources use the remaining space in
the existing extra-MEM1 model window; pristine copies reuse the former CPU
model heaps. No console reservation or recording/savestate capacity changes.

Dolphin supports session ghost recording and racing against your last
attempt or success. Saved-file ghost libraries, file import and Watch with
timeline/split alignment require the Wii storage backend and are unavailable
in this package. Those menu entries reporting unavailable is expected.
