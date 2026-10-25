# PR23 guidebook and free-camera follow-up

The guidebook uses three fixed 164-pixel category slots, with 38-pixel icon
boxes and 20-pixel labels. The native hand moves down seven pixels and left
four relative to PR22. Selected Boo and sunglasses alternate between held
poses of the original artwork. Displays & styles groups the existing item
editors under Timers, Inputs & movement, HUD & messages and Custom text.
Search routes keep their existing leaf identities and Back returns to the
containing group. The sidebar's native level-name banner and existing postcard
share the retail world mapping, including secret-area parents. The banner uses
the white uppercase guidebook title artwork rather than typed text. Both images
keep their original proportions inside the sidebar.

The Sunshine timer's append-only Colon/Dot option crops the lower dot of the
native second colon during the existing 3DP draw scope. The minute colon,
retail-owned race/countdown timers, outline and gradient endpoint are retained.
The borrowed pane geometry, bindings and matrix are restored after each draw.

## Camera ownership

PR22's model preview wrapper prevented GhostCamera from recognizing the camera
perform slot. GhostCamera now recognizes that wrapper and delegates through
it. The chain is GhostCamera -> ModelEditorPreview -> PracticeSession -> retail.
An active colour preview takes priority over Recorded Watch; ordinary Watch
and recording still use their existing camera paths. Five focused ownership
checks cover admission, delegation, reinitialization and foreign owners.

## Ricco rendering evidence and limited fix

The private PAL PR22 fixture captured 80 records at native shape draw time for
riccoBasket, riccoArrow, riccoBoatL and SignCross. Indexed model matrices matched
the submitted J3D view times world matrices within 0.00063, and camera view
agreement was within 0.00097. These are CPU submission checks, not observations
of the matrix values ultimately consumed by GX.

The cage and arrow perform two view calculations per displayed frame. Their
retail scene nodes belong to Map Group, visited by preEntry, and also register
with the map-object manager reached through Conductor. Two swaps return to the
same matrix bank used by the preceding draw. Boats and signs in Object Group
have only the Conductor visit in this fixture. Removing native traversal or
running extra view calculations would be inappropriate.

A GXDrawDone barrier now runs before an eligible queued free-camera update,
after last-tick, stage, director, camera and generation checks. This drains the
previous draw before preEntry can reuse its matrix storage. It allocates no
buffers, changes no simulation and is not reached during ordinary gameplay.
It may reduce CPU/GPU overlap while Free camera is active.

An isolated in-memory PR22 PAL A/B probe preserved all volatile registers and
inserted the barrier at the guarded inlined camera-update point. Exact original
function bytes and the unused private shim range were checked. The probe could
be disabled by restoring its single original instruction. Captures are in
build/ricco-freecam-runtime/baseline; they do not establish a complete visual
fix, especially for the single-visit boats and signs. Wii movement/turning in
Ricco remains the required confirmation. Do not describe this as hardware
verified or assume it explains every reported object.

All PR22 release packages and evidence remain intact. PR23 uses separate
build trees and release output. Shared reservations, state capacity and the
protected ordinary timer baseline are unchanged.

## Final additions

Guide titles are half-size I4 captures of the original native lettering. The
internal cache start moves from 0x5B000 to 0x5AE00 within the same borrowed
0x64000-byte game buffer. All 70 region/language/world combinations fit; the
worst cache retains 224 bytes, the largest source archive 416 bytes, and the
Boo extraction workspace 608 bytes. The cache header remains 96 bytes.

The Warp Wheel now shares the complete retail-pad suppression around direct(),
including button meanings, opening and dismissal frames. Its own input update
runs first; native prompts cannot consume the same confirmation.

Sirena pineapple is a live Plaza control using flag 0x1038B and the native
makeObjDead/makeObjAppeared path already used by Sirena Enter. Reappearing
restores the initial position/rotation after detaching any holder. The control
marks the attempt and ghost assisted, changes no mod configuration layout and
lets an IL's next setup retain ownership. Its UI-only ID is outside both stored
settings and display-favourite IDs. It is inactive outside a live Plaza.

Creation, text/numeric keyboards, search and breakdown editors share guidebook
paper, trim, selection and native icons. Full-screen menu-only dialogs inherit
parchment/ink mapping; live preview renderers keep their actual display colours.
