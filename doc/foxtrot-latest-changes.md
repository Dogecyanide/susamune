# Moonshine Launcher FOXTROT — latest changes

**V2.3.0 pre-release · Build 08BDB4CD**

- **Choose the episode for more ILs.** In **Runs > ILs**, press **Z** on a supported row, choose an episode with the C-stick, then press A to keep it. This covers the seven main-course 100-coin ILs, Gelato/Noki/Pianta Hidden and all ten Full Reds. Choices survive reboot and stay separate for JP, US and PAL.

- **Hold Load until you are ready.** Keep your Load shortcut held after a state restores, then release it to move. If practice pause was already on, it stays on after release.

- **The new handmade splits are here.** The remaining routes and Full Reds gain their requested checkpoints, with up to eight segments including the finish. Earlier attempt counts stay; segment records carry forward wherever the same checkpoints still define them. TESTING.md has a grouped reference so you can pick your own levels.

- **SD loads can work with three full memory slots.** A matching memory state provides a recovery point when the SD file is too large to stage at once. All three saved slots remain intact. If an SD read fails partway through, the game restores that recovery state and reports its slot. If neither a suitable recovery state nor enough temporary space is available, it refuses safely.

- **Less repeated reading while launching Sunshine.** The launcher reads its two character assets in larger batches, keeping the same file checks. We still need real-console feedback on the difference in startup time.

Use the complete package and make fresh SD states: they remain specific to their build, game region, setup and level/episode. Standalone Dolphin patches do not provide the SD service.

**Only four focused checks are requested in TESTING.md.** The route tables are there to divide split testing among volunteers. Keep previous successful results; there is no request to retest everything.
