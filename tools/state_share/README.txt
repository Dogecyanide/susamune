MOONSHINE STATE SHARING

Windows: no Python or extra installation is needed. Keep all five helper
files together. These tools use Windows PowerShell and .NET already on Windows.

TO SEND A STATE
1. In Moonshine, save the state to SD and give it a recognizable name.
2. Insert the SD into your PC. Open Share a state.cmd.
3. Choose its .mss file from the SD's Moonshine data\states folder.
4. Choose a NEW ZIP filename. Add the level, episode, build and setup notes
   for your friend. Existing ZIP files are never overwritten.
5. Send that ZIP and this helper folder to your friend.

TO RECEIVE A STATE
1. Insert your Wii SD into your PC. Open Import a state.cmd.
2. Choose the received ZIP (or a .mss file), then the SD card's root folder.
   For example, select E:\, not E:\apps or E:\Moonshine data\states.
3. Safely eject the SD, boot Moonshine and enter the matching stage/episode.
4. Refresh the SD states list. Select the new state with Y, then use your
   normal Load bind. This direct load keeps your three RAM states.

You can also drag a .mss or ZIP onto either .cmd file.

IMPORTANT DETAILS
- Use the matching game REGION, compatible Moonshine build, and the same
  launcher/game setup. This does not convert PAL states to JP or US.
- The helper checks file structure and all three integrity checksums. It
  also checks snapshot-18 metadata, including the region's layout, internal
  identity, memory ranges and resource ownership fingerprint. Older snapshot
  versions need the helper and Moonshine build supplied with those versions.
  It cannot prove that your console has the same live resource layout. Moonshine
  still checks the build, region, settings, stage, heap and resource owners.
  If a load is refused, keep the error and ask the sender about their setup.
- A on the SD list imports into your selected Save to RAM slot. Use Y plus
  your Load bind if you want to keep all three existing RAM states.
- The imported file gets an unused filename; the original and all existing
  files stay unchanged. A tiny .used file reserves its number safely.
- The state keeps its original creation name. Later in-game rename sidecars
  are not copied, because they belong to the sender's local file number.
- These tools share standalone .mss states, not whole TAS project folders.
- A setup ID is a fingerprint, not a settings backup. Copying it does not
  configure the recipient's Wii. Ask the sender for the actual settings.

COMMAND-LINE USE (OPTIONAL)
powershell -NoProfile -ExecutionPolicy Bypass -File StateShare.ps1 -Mode Inspect -Path state.mss -Json
powershell -NoProfile -ExecutionPolicy Bypass -File StateShare.ps1 -Mode Export -Path state.mss -Destination new-state.zip -SetupNote "PAL, Pinna 3, 60 Hz"
powershell -NoProfile -ExecutionPolicy Bypass -File StateShare.ps1 -Mode Import -Path new-state.zip -Destination E:\

No network connection or server is used. No console compatibility checks are
disabled. Keep using the helper included with the Moonshine version you run.
