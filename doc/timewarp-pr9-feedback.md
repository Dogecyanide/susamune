# Prototype 8 hardware feedback and Prototype 9 scope

PR12 follow-up, 2026-10-15: the user confirms the slowdown toggle bind and
percentage selector work. State sharing and Hoverless split verification are
still pending; a larger paired network test is planned for the weekend.

User-reported Wii Pinna 3 measurements, 2026-10-13:

| Slot | Save | Load |
|---|---:|---:|
| 1 | 0.534 s | 0.233 s |
| 2 | 0.500 s | 0.267 s |
| 3 | 0.533 s | 0.267 s |

The requested targets are strictly below 0.400 s to save and below 0.200 s
to load for all three slots. Loads are measured from timer freeze until the
first frame with Mario visible. A component benchmark is not a hardware
measurement of that whole interval.

The user confirmed Turbo and Rocket ghost playback, the underwater
No Shine Get Animation repair, and adjustable slowdown. Yoshi's animation
still looked wrong, and R+A burst spray still looked like ordinary spray.
No online partner was available for the newer race-flow tests.

The next focused work is savestate cost, exact mounted-Yoshi observations,
accepted burst-spray observations, a digit editor for gameplay speed, and
normal-rate stick-history sampling while slowdown is active. At 100%,
gameplay must retain the original input and spin behaviour. Returning to
100% must discard pending slowdown samples. The existing assisted-attempt
rule remains sticky for the attempt in which slowdown was used.

Requested ghost RNG scope is boss/enemy behaviour during Watch only.
Racing a ghost and live online races must retain each player's own RNG.
Selecting/loading a ghost must not seed the active game. Watch exit must
not leak recorded RNG into subsequent normal gameplay. Reliable boss
reconstruction needs investigation of initial world state and interactions;
a saved random seed alone must not be presented as exact boss replay.

No redundant full regression matrix is requested. Use focused checks for
changed paths, the required protected-timer/region build guards, and a
small Wii follow-up list. The user explicitly requested extra space for
the aggressive encoder. Reclaim 2.44 MiB inside existing MEM2 ownership:
2 MiB from transfer staging and 448 KiB from fenced disc-read scratch.
Keep the MEM1 arena and stack, ISO cache, three savestate slots, and
ten-minute recording capacity unchanged. The resulting 22.375 MiB pool
fits the captured tight set with 291,552 bytes free; this does not establish
capacity for every possible state. See `timewarp-pr9-state-speed.md` and
`timewarp-mem2-audit.md` for exact geometry and component measurements.
