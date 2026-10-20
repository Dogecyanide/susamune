# PR17 timer gradient animation

The QFT and native SGT editors each expose animation Off/Flow/Pulse and
Slow/Normal/Fast (8/4/2-second cycles). Off is the default. Flow interpolates
cyclically through the chosen colours; Pulse keeps their hue and varies
brightness from 75–100%. Direction remains independently selectable.
Cancel restores direction, animation and speed; resetting one row changes
only that row.

Four settings append at IDs 167–170 within the existing 174-value storage.
Editor and timer object layouts, wire formats and memory reservations do
not grow. Colours are sampled into local draw temporaries, never written
back to the stored palette. Phase comes from OS time, independently of
QFT/SGT counters, slowdown, RNG and savestate clocks.

Native SGT includes separators in each visible digit group's palette but
leaves the TIME image and background streak alone. Both animated directions
use the existing temporary picture-corner path, retaining red-channel
outline/shading and exact pane/TEV restoration. `native_hud_color.cpp` is
unchanged. Off retains the existing run grouping and static gradient path.

Focused host checks pass for Off identity, Flow interpolation/wrap, Pulse
bounds, speed periods, native scope, actual editor keep/cancel/reset and
owner isolation. The existing production draw fixture also passes exact
corner/pane/GX restoration and black-outline checks. Combined linked timer
guards and Wii visual confirmation remain separate integration checks.
