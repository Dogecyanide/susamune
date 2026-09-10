# Moonshine V2.3.0 — Frame By Frame

Frame By Frame adds precise practice controls, editable TAS projects, three
savestate slots and more ways to make Moonshine look the way you want.

## Frame controls and TAS projects

- Pause gameplay and advance one frame at a time while holding the inputs you
  want Mario to perform. Jump-dives work with Advance, even when another
  shortcut uses the same buttons.
- Dialogue bubbles and text advance with each step instead of continuing
  while gameplay is paused.
- The QFT stops while practice is paused and advances with each step. Assisted
  attempts show TAS and do not earn ordinary PBs.
- New TAS captures a Beginning. Two checkpoints let you rewind and replace a
  continuation. Saving over a checkpoint asks for confirmation.
- Save and open named TAS projects on SD, including their input recording,
  Beginning and checkpoints. Checkpoint actions have optional shortcuts,
  unassigned by default, with rebinding available beside each action.
- Record and replay inputs through area changes, introductions and movies,
  including cutscene skip presses. Loading waits do not consume input frames.
- Replay continues after a diagnostic mismatch and shows a small DESYNC
  warning. The larger recording/replay banner can be hidden.

## Savestates

- Three compressed memory slots share a 17.94 MiB pool. Save and Load can use
  separate slots and separate cycle shortcuts.
- Name states before saving them to SD. Browse, rename, delete, import or
  select a file to load directly, including after a reboot into a compatible
  setup.
- Hold the Load shortcut to stay paused on the restored frame; release it to
  continue. An existing practice pause stays paused.
- Faster compression, restoration and cache handling reduce save/load waits.
  If needed, retained states can be compressed more tightly to make room.
  A capacity failure keeps the existing states.
- Ghost recordings can continue from a restored checkpoint, keeping the
  earlier level recording and marking the result TAS.

## Free camera and ghosts

- Use free camera during practice pause, frame advance and Ghost Watch.
  Movement speed and look sensitivity have independent 0.25x–4x controls.
- Reverse sideways movement if preferred, recenter the camera, or hide all
  game and Moonshine HUD elements for filming.
- Display a ghost's recorded inputs, including both ghosts when using Watch2.
  Turning ghost display off also hides its input display.
- Personal and imported ghost libraries now page through files on storage;
  the old 45/12-file and ten-hour library limits are removed.
- Compatible exported ghosts carry split timestamps for racing against their
  deltas, including across supported game regions.

## Runs and layout

- Expanded hand-authored splits cover 132 routes and 495 timed segments,
  including course reds, 100-coin routes, boss hits and Plaza objectives.
- Choose the starting episode for supported Full Reds, Hidden and 100-coin
  ILs instead of being locked into one route.
- Records returns as a top-level tab. More named settings can be Shined,
  and the layout editor is divided into smaller sections.
- The Sunshine timer has full positioning and styling controls, with
  Original or Custom appearance for the whole timer or individual elements.
- Metadata gains horizontal spacing, row spacing, fields-per-row and compact
  value-width controls.
- Colour the normal health counter and underwater air counter independently.
- Use the Creation editor for Mario's seven clothing/accessory parts and ten
  FLUDD/water targets. Original and Custom choices are separate for each part.
  Hold Y while adjusting RGB for steps of one.

## Launcher and languages

- Faster startup checks the remembered game first and loads other storage
  when needed. Themes use `/Moonshine_Theme` at the SD root; the launcher
  creates the folder if it is missing.
- A selectable guide is included in the launcher and works offline.
- **English** and **日本語版** are separate downloads. The English download
  keeps Moonshine menus English for JP, US and PAL Sunshine.
- The Japanese download provides Japanese launcher menus and Japanese
  Moonshine menus for JP Sunshine. US/PAL Moonshine menus, the embedded guide
  body and some status messages remain English. Its default flag background
  is included only in that download; no music is bundled.
- The final memory cleanup frees another 5,952 bytes of mod MEM1 capacity
  without reducing savestate capacity.

## Updating

Copy the ZIP's `apps` folder to the SD root and replace the Moonshine app
files. Keep `susamune.ini`, records, ghosts, achievements and playlists.
The Japanese ZIP also includes `Moonshine_Theme`; skip that folder if you
want to keep your current background.

Create new states and TAS projects for this build. Older states and projects
need their matching build and setup; they are not automatically converted.
SD state and TAS file menus require the Wii launcher. Dolphin downloads use
BPS patches for your own clean retail ISO and do not include that storage
service.

A TAS holds up to 4096 input frames and 32 area/movie transitions. Individual
ghost recordings still have their recording limit. Three savestates share
memory, so especially large states may not all fit. State restoration still
requires the correct area and compatible setup; it does not warp you there.

See [the English guide](guide-en.md) or [日本語ガイド](guide-ja.md) for controls
and detailed instructions.
