Moonshine PR28 - Linux Dolphin companion

Use matching Wii/Dolphin builds. This companion also works with PR27; it changes no game files
or protocol; a Linux player can use the same codes as Windows and Wii players.

Requirements: native 64-bit Dolphin and 64-bit Python 3.10 or newer. No pip
packages are needed. Native distro packages are the verified process-access
target. The launcher follows wrapper children, including Flatpak, but sandbox
memory permissions and real Flatpak Dolphin gameplay remain unverified.

1. Extract the complete kit. In a terminal, change into its folder.
2. Patch your own clean Sunshine ISO if needed:

   python3 apply_patch.py "/path/to/clean Sunshine.iso"

   It creates a separate " - Moonshine.iso" file and refuses to overwrite it.
   For a companion-only update, your existing patched ISO works unchanged.
   For PR28 game fixes, use this kit's PR28 patches on your clean ISO.
3. Apply the three Dolphin per-game settings in README.txt. Use File > Open
   User Folder to find GameSettings; Linux paths vary by installation.
4. Close any existing Dolphin instance, then launch the game through us:

   bash start-linux.sh --launch dolphin-emu -e "/path/to/patched Sunshine.iso"

   The companion starts Dolphin, waits for Moonshine to boot, then connects.
   Keep the terminal open. You may also omit -e and select the game in Dolphin.
   If the executable is elsewhere, pass its absolute path instead.

   For the Flathub package:

   bash start-linux.sh --launch flatpak run org.DolphinEmu.dolphin-emu -e "/path/to/patched Sunshine.iso"

   The companion waits for Dolphin underneath its launcher. If it reports
   that the application sandbox denied memory access, use a native distro
   Dolphin instead. No sudo, Flatpak overrides or global security changes.
5. Follow the room/code instructions in README.txt. Use PR28 on all players
   when testing PR28 game fixes.
   Disconnect in Online before pressing Ctrl+C to stop the companion.
   Stopping the companion leaves Dolphin open.

Attaching to an already-running Dolphin, when your system permits it:

   bash start-linux.sh
   bash start-linux.sh --pid 12345

Many Linux desktops restrict process memory access to children of the caller.
The --launch method works with that usual policy, without sudo or changing
ptrace_scope. A stricter security policy can still deny it; the error will say
so. Run both programs as your normal user. We do not alter system policies.

Technical notes: /proc/PID/exe verifies the native executable; /proc/PID/mem
provides access only through the existing bounded mod-mailbox interface. A
per-process lock prevents duplicate companions. The UDP logic and ownership,
session-reset and heartbeat checks are the same as Windows.

Validation scope: Linux child-process memory access, mailbox detection, locks
and UDP are covered by automated tests. Real Linux Dolphin/Wii gameplay still
needs a hardware session; no performance or full-distribution claim is made.
