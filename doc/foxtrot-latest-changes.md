# Moonshine Launcher FOXTROT — latest changes

**V2.3.0 pre-release · Build C4AF447B**

- **Records is back on the top row**, between Runs and Ghosts. The shortcut inside Runs remains too.

- **Faster memory saves and loads**, plus less time spent checking SD files. Waits still depend on the scene and state size; please report how they feel on Wii.

- **Save and Load have separate choices.** Under **Practice > Savestates**, Save to chooses the memory slot you write, while Load from chooses what you restore. You can save into State 1 and keep loading State 2. Optional cycle-save and cycle-load shortcuts start unassigned; the older cycle-both shortcut still works.

- **Use an SD file with your normal Load button.** In **SD states**, highlight a file and press **Y**, close the menu, then Load. All three memory slots stay saved. **A** instead imports into the Save to slot, after confirmation, and leaves your Load from choice alone.

- **Name and manage SD states.** Save memory state to SD asks for a name before saving. On an existing file, **Start** renames and **X** asks to delete it. In the name editor, Start finishes and X + Start cancels.

- **Startup text stays visible during the device scan.** Fixed the later storage check clearing its message and showing only the theme while waiting for USB.

- **Magenta Mario colours no longer have red specks.** Fixed a texture-colour rounding problem affecting the cap and shirt. Skin and emblem details keep their existing treatment.

The previous build already received real Wii confirmation for SD restore after reboot, ghost continuation with frame advance, timer alignment and colours surviving reboot. There is no need to repeat the whole old checklist; TESTING.md starts with six checks for this update.

SD states remain specific to the same build, region, launcher setup, level/episode and compatible loaded resources. Loading directly from SD needs temporary space; if your memory states leave too little room, it refuses without deleting them. The files live in `/moonshine_states` on the launcher's device. Standalone Dolphin patches do not provide the SD service.
