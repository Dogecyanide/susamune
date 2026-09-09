# Moonshine Launcher FOXTROT — latest changes

**V2.3.0 pre-release · Build 00B63258**

- **Read the guide in the launcher.** Choose **Guide** before launching Sunshine. Pick a topic with Up/Down and A, scroll with Up/Down, or move a page with Left/Right. B goes back. It works without opening a separate file.

- **Input replay starts more reliably.** Fixed problems restoring its starting inputs and stopping a recording from the menu. Opening the menu now stops Mario immediately. The page shows **Starting** while it waits, and messages distinguish changed settings, damaged recordings and a replay that no longer matches the game. Replay remains experimental.

- **Less waiting for savestates.** Saving uses a faster format when it fits, with tighter compression available automatically when space is crowded. Loading and moving saved states also do less work. A save that cannot fit still keeps every previous state.

- **A little more state space:** reclaimed **320 KiB** for the three memory slots without taking more memory from Sunshine's game heap.

For input replay, turn **Save RNG state** On and make a new memory state during gameplay. Choose **Record from savestate**, then release the A button used to confirm. Open the menu to stop and keep the take, then choose **Replay recorded inputs**. Keep that starting state; after importing an SD state, load it and make a new memory save before recording inputs.

SD states and the earlier load-time improvements have already received positive Wii feedback. **TESTING.md starts with only four checks for this update.** Keep successful earlier results; no full retest is needed.

**Make fresh SD states for this build.** They remain specific to their build, game region, setup and level/episode. Direct SD loads still preserve the three memory slots and may refuse if temporary space is too full. Standalone Dolphin patches do not provide the SD service.
