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

## PR20 Creation controls and compatible storage

Creation opens a display page with its visibility and editor together. The
shared editor groups Position, Size, Colours and Animation; X + C-stick
left/right changes group. C-stick selects/adjusts controls, START selects
the next character or colour stop, and X+A retains exact size entry.
Keep, Cancel and Reset remain explicit confirmed actions beside the live
preview. Custom text now uses the same Flow/Pulse and 8/4/2-second speeds.

Colour stops selects the existing per-character mode or one to five stops.
The saved RGB arrays retain exact stop colours at rounded evenly spaced
indices; interpolation fills the intervening slots. Native SGT stores its
anchors in the six normal-timer digits and derives the four countdown
digits and separators from that palette. It never attempts to fit five
anchors in four countdown slots. Label and streak colours remain separate.

No wire struct or memory reservation grows. QFT `reserved[0]` stores the
stop count and `reserved[1] == 0x47` tags it. Creation's
`reservedAchievement0 == 0xd0 | count` stores native stops. Each custom
word's reserved byte tags with bit 7; bits 0–2 store count, 3–4 motion and
5–6 speed. Missing tags preserve legacy per-character colours, with custom
text animation Off and Normal speed. Invalid counts/modes are ignored.
INI keys are `gradient_stops` in QFT, `native_timer_gradient_stops` in
Creation, and `wordN_gradient_stops`, `wordN_gradient_motion`,
`wordN_gradient_speed` for custom text.

Layout profiles' fixed 142-setting array predates timer gradient settings.
QFT's existing `reservedV1` now carries a `0x47` marker followed by QFT
direction/motion/speed and native direction/motion/speed, so profile capture
and load also preserve those options without changing the profile format.
