# Moonshine V2.3.1 — Frame By Frame

This update improves free camera and colour editing, quiets a repeated ghost
message, and fixes a crash caused by loading savestates while Sunshine's
background video player is running.

## Free camera

- Choose **Practice > Free camera > Resume gameplay** to run the game at
  normal speed while keeping free camera On. Pause gameplay stops it again.
- Both sticks now follow all directions, including small angles between the
  main directions. A smooth response gives finer control near the centre.
- Diagonal movement stays within the selected speed. Letting go stops the
  camera immediately; movement speed and look sensitivity remain separate.

## Colours

- The shared colour editor now uses **Hue, Saturation and Lightness (HSL)**
  for Mario, FLUDD, timers, inputs, menu colours and other editable overlays.
- Hue chooses the colour; Saturation adjusts its strength; Lightness runs
  from black to white. Hold **Y** for adjustments of one instead of four.
- Existing colours are kept. Original/Custom appearance, individual parts,
  Keep, Discard and Reset remain available.

## Fixes

- Restored Moonshine menu access, skins and display customisation on the
  A/B/C file-select screen when Intro Skip is enabled.
- Savestate loads preserve the background video player's live buffers rather
  than mixing an old saved frame with its current decoding work.
- **Ghost challenger ready** appears once for a retained challenger instead
  of appearing on every level reset.
- Fixed Windows folder handling in the automatic release packaging checks.

## Updating

Replace the Moonshine app files using the **English** or **日本語版** download.
Keep your settings, layout, theme, records, ghosts, achievements and playlists.
Use the launcher and mod files from the same download.

Make new savestates and TAS projects for this build. Keep older states and
projects with their matching version. The SD file menus still require the Wii
launcher; Dolphin uses the matching BPS patch for your own clean ISO.

See [the English guide](guide-en.md) or [日本語ガイド](guide-ja.md) for controls.
