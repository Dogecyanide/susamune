# PR22 guidebook polish

Shared 24-pixel list selections now center their 16-pixel text cells. Shorter
fitted labels keep that center. A narrow ochre/cream, clipped-corner border
replaces the flat row fill; the hand points through the row's center. Scroll
arrows occupy a separate right gutter, outside right-aligned values such as
an unassigned bind's `None` label.

Category icons sit beside their labels inside the existing 60-pixel strip.
The artwork fits a 34-pixel box with its original proportions; the icon,
label and selection outline have independent padding. L/R scrolling still
uses the actual category widths.

## Native artwork and ownership

Native texture changes use the guidebook's discrete 90-tick cadence, with
no interpolation. Only the selected category animates; permanent header and
sidebar decorations retain their native cadence. The Shined category uses
`shine_icon.bti` / `shine_get_icon.bti`; System uses the authentic Pianta
`monte_head1.bti` / `monte_head5.bti`; Runs uses `bluecoin_icon.bti` /
`bluecoin_icon2.bti`. Palm, fish, boat and cursor keep their native pairs.
Mario alternates the side-facing `mario_icon.bti` and front-facing
`guide_mario.bti`, both extracted from the user's disc.

Pianta heads are copied from the user's option archive at 24×32. The
controller is captured at 40×36 and the sunglasses at 50×18, each larger
than its displayed artwork. Mario's alternate is captured at 17×22 (exactly
half the native dimensions), occupying 20×24 padded GX tiles. The CPU
backup now uses 12,192 of its existing
12,288 bytes, including the Boo and cache header. Archive members, texture
formats, complete source extents and output capacities are validated before
publication. No heap or memory reservation increases.

The alternate-art upload uses the checked archive gap immediately after the
option upload (`mGame6Data + 0x4B000`). It cannot overlap the guide cache at
`+0x5B000`. A cache tag identifies the uploaded pose; writes wait for GX and
flush CPU/texture caches. The slot is admitted only after the disc decoder
has finished borrowing this gap. Savestate loads preserve the tag alongside
its texture; stage/guide archive replacement naturally forces re-upload.

## Generated artwork

The controller alternate is a built-in image-generation edit using the
decoded native controller as its reference. The selected output is preserved
in `data/menu_icons/controller-pose2.png`. `scripts/build_menu_icon_frames.py`
only crops transparent padding, scales and encodes approved artwork as a
transparent 40×36, 32-colour C8 texture. Its compiled bytes are generated in
`src/menu_icon_frames.cpp`; the PNG is not a runtime dependency.
The exact prompt, reference, output hash and tool provenance are recorded in
`data/menu_icons/provenance.json`. Boo and sunglasses candidates were rejected
by the user and are not compiled or used. Their original native artwork stays
in use. Mario and Pianta use the native pairs shown in the preview.

## Focused validation

The production scaler fixture checks controller/Pianta/sunglasses source
extents, destination guards, transparency and block padding. Private JP, US
and PAL option-archive checks successfully capture all five required native
assets; the proof is `build/pr22-menu/native-art-proof.json`. Mario's guide
capture is checked separately in `build/pr22-menu/mario-native-capture.json`.
The front-facing Mario has no native second frame of its own: all seven guide
archives use one `guide_mario.bti` on their `mi00`–`mi09` location markers.
The menu pairs it with the separate native side-facing drawing. Runtime visual
verification belongs to the combined PR22 build.
