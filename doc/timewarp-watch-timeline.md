# Watch timeline

While Watch is active, select its target row in Ghosts to open the timeline.
Entering pauses the watched scene without selecting an unsought checkpoint.
Left/right moves one quarter-frame; up/down moves 120 quarter-frames. L/R
immediately jumps both ghosts to their own matching checkpoint and holds them
there. With no checkpoint selected, R chooses the first and L the last. X and Y
both re-jump the selected checkpoint, or the first if none was selected.
Neither ghost keeps its previous lead into the comparison. Z clears alignment.
A resumes both from the held poses and closes the menu; B returns to Ghosts
while paused. Paused Watch models remain enabled behind the menu and are visible
when the panel is closed. A rejected split cannot resume an unrelated position:
choose a matching checkpoint or deliberately scrub the timeline first.
The existing Watch exit action still ends the session.

The bar follows ghost 1's recorded timeline. Checkpoint times and differences
remain the original elapsed times even when the playback positions are aligned.
After alignment, both advance by the same elapsed time from their respective
checkpoints. Ghost 2 uses its own constant QF offset for poses, FLUDD,
attachments and recorded controller samples. Each runner retains its recorded
speed. The recorded camera follows ghost 1.

Alignment requires the same nonzero split schema, route and endpoint, plus the
same segment index and complete scene identity. Watch 2 retains its existing
requirement for matching scene itineraries. A missing or incompatible checkpoint
shows `--`; recordings without checkpoint data still support timeline seeking.
The pair's playable range is checked before either cursor changes. Rejected
alignment leaves both poses and the playback clock untouched.

Seeking never restores world state. Moving within the current scene changes
only the Watch presentation clock and cursors. Moving to another recorded scene
uses the existing guarded Watch warp, then holds the requested pose after setup.
Unrecorded loading gaps snap forward to the next scene. Existing world actors
are not reconstructed at their historical positions. A private director-counter
clock lets a scrubbed Watch resume even after the race QFT has stopped; the race
QFT and normal racing clock are unchanged. Watch exits clear the pause state.

On a seek, private water is rebuilt from at most 280 preceding QFs in four-QF
steps, using recorded origins rather than current rendered nozzle joints.
Particles remain an approximation, including ground queries against the current
scene. The rebuild allocates nothing, emits no gameplay water and consumes no
game RNG. Existing ghost capacity, storage formats, reservations and snapshot
layouts are unchanged.

Focused verification uses the production selection controls, clocks, split
matching, pose samplers, visual states, model preparation and CALC/ENTRY path in
`test_ghost_scrub.py`. Retail rendering boundaries are stubbed on the host; the
production model code writes the checked matrices. The tests rewind past both
checkpoints, check both signs of the split difference, verify held submitted
positions with the menu open, then resume equal elapsed playback and check the
primary recorded camera time. They also cover guarded scene loading and refusal.
The earlier sampler-only coverage missed the disconnected L/R selection and
the model's menu gate. These tests are not a Wii or Dolphin visual verification.
