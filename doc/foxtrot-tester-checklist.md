# Moonshine FOXTROT — latest checks

**V2.3.0 pre-release · Build C34FF061 · Full-level TAS update**

Reuse one TAS that enters another area, such as an approach into a secret. Keep earlier RC1 passes; these four checks cover the new behavior. The full `RC1_TESTING.md` remains available for gaps in the team's coverage.

**Tester / platform / game region / English or Japanese download:**

**Make new SD states and TAS projects with this build.** Older files need their matching older build. Settings, records and ghosts are kept. Dolphin has no launcher SD service; skip the SD steps there.

- [ ] **Record through an area change.** New TAS, record a recognisable opening and save Checkpoint 1 before the entrance. Enter the next area normally and record a little more. The recording and frame count must stay; loading/menu waiting must not add input frames. Checkpoint 1 should say Other area and refuse to load until you return there. Return to the Beginning area and Replay: expect the opening, the same entrance and the recorded continuation.
- [ ] **Save without making a checkpoint.** In the later area, use Save TAS and name it. It should save the whole recording while keeping Checkpoint 1 at its earlier point, with no request for an extra memory slot. Wait for the saved message. A later Save TAS updates the same named project.
- [ ] **Open after one reboot.** Console: reboot and Open the project in the later area. If neither its selected checkpoint nor Beginning matches, Mario must stay where he is and the recording/count must still open. Return to the Beginning area and Open it again: its Beginning or a compatible checkpoint opens paused, while Replay still includes all recorded inputs. Go to Checkpoint 1: the local recording should rewind to that point. Continue to make a different ending, then save it. The earlier full SD copy stays until this new save. No separate state imports.
- [ ] **Shined settings.** Before that reboot, add a newer camera setting to Quick and remove one once. Check Movement speed, Reverse sideways, Look sensitivity and Hide all HUD offer Shined; your old stars must stay. After the same reboot, check the chosen star remains.

The take holds **4096 input frames and 32 area changes**. You do not need to hit both limits. If recording stops unexpectedly, check the existing take/count remains available to save and report the exact message. Standard Moonshine should still be English on JP; Japanese testers can check the new text during the same pass.

For a problem, send **build checksum, route/episode, what you pressed, and the exact message**. A photo or short clip helps.
