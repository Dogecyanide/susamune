Moonshine 3.0.0 - Dolphin online companion (Windows)

Use the matching Moonshine Dolphin build and 64-bit Python 3.10 or newer.
The Wii player uses the matching Nintendont build. JP, US and PAL can share
a room; PAL must use 60 Hz. Both players must use the same mod/protocol version.

First extract this entire ZIP. Drag your clean Sunshine ISO onto Apply-ISO.cmd.
It chooses the regional patch and creates a separate "Moonshine PR13.iso"
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
   only 176 KiB beyond retail MEM1 for the two ghost bodies; the game's heap,
   savestate capacity and ghost recording length stay unchanged. The mod
   refuses to allocate those bodies when this memory setup is missing.
2. Boot the Moonshine Dolphin build, then run start-windows.cmd. Keep its
   window open. It discovers the running Dolphin and prints the game region.
   With multiple Dolphins, run: python bridge.py --pid PROCESS_ID
   In the mod menu, open Ghosts > Ghost visuals and set Ghost display to On
   and Ghost appearance to Mario. Use Mario for session racing and online
   players: Shadow Mario and Piantissimo need assets this standalone package
   cannot supply outside the stages that already contain them.
3. In Online, enter the same relay server address and port as the Wii player.
   One player creates a room; the other joins its six-digit room code.
   The companion opens its own outbound UDP socket on a free local port.
   A local relay on the same PC can therefore keep its normal server port.
4. Disconnect in Online before closing the companion. If Dolphin or the
   companion restarts, reconnect the companion and create or join a new room.

The companion is required for Dolphin networking. It uses no administrator
features or third-party Python packages, changes no Dolphin settings, and
writes only the small networking mailbox owned by this mod. It carries UDP
packets; each machine still simulates its own player. The relay and peer
session checks are identical to the Wii path.

Pausing Dolphin stops the heartbeat. After three seconds the companion
retires its socket; resume emulation and reconnect Online. Dolphin savestate
rewinds likewise retire a detected old session. Moonshine's own savestates
do not rewind this mailbox.

Ghost bodies require the included physical-memory settings because Dolphin's
CPU-only fake memory is not visible to the graphics processor. The existing
MEM1 attachment heap is retained. Stage-local Shadow/Piantissimo availability
still follows the standalone Dolphin asset path.

Dolphin supports session ghost recording and racing against your last
attempt or success. Saved-file ghost libraries, file import and Watch with
timeline/split alignment require the Wii storage backend and are unavailable
in this package. Those menu entries reporting unavailable is expected.
