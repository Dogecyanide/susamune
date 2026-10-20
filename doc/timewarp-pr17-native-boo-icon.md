# PR17 native Boo tab icon

Ghosts uses the Boo symbol from the selected game's own
`data/scene/casino0.szs`, `mapobj/srotdram.bmd`, texture `L_srotdram00`.
The bottom 128×128 tile of that 128×512 CMPR texture is reduced to a
32×32 RGB5A3 BTI; the cream matte is transparent. White/blue body pixels
remain opaque. No native artwork is added to the release package.

JP, US and PAL have different casino archives but the exact same 51,104-byte
model (CRC32 `C3886E6E`). The bounded production decoder validates Yaz0
distances, output sizes, RARC tables/member extents, the complete model CRC,
and the BMD texture header before publishing any output. It stops after
the selected model, so it does not promise to validate unused archive data.
Read failure, unexpected modified art or malformed data leaves a blank
Ghosts icon, with its label intact; the attempt is not repeated every frame.

The one-time read occurs on the main thread after the first normal, fully
set-up stage, while state/ghost storage work is idle. It does not execute
inside the renderer, a vtable callback, or with interrupts disabled.
`GXDrawDone` precedes borrowing the checked `mGame6Data+0x48000..+0x5b000`
upload gap. The decoder occupies 76,704 of its existing 77,824 bytes and
uses no heap. Once RARC metadata is consumed, it becomes a 20 KiB read
buffer. The immutable icon cache is then uploaded again and GX texture
cache invalidated. The ordinary native-guide and savestate cache recovery
path also restores Boo when that upload area is overwritten.

The controller is reduced from 120×104 to 60×52 with alpha-weighted 2×2
filtering. Controller, glasses, Boo and their cache header total 12,224
bytes in the existing 28,928-byte presentation backup. Reservations,
collision spill storage, game archive extents and guide suffix remain
unchanged.

`scripts/test_menu_native_icon.py` compiles the production decoder for the
host. With `--iso-root`, the three private retail fixtures produce identical
2,080-byte Boo BTIs (SHA-256
`928ee3d4968fc2633d051e42136e2db9cf339c79f98dc093e003d5b8245bcb60`).
They require 64/64/65 bounded reads and 1,135,616/1,135,616/1,136,640 input
bytes for JP/US/PAL respectively. Tests also cover malformed metadata,
bad Yaz0 references, short buffers, truncated/failed reads, altered model
checksums and output/workspace canaries. Private previews and the receipt
live under `build/pr17-native-icon-research/extraction-proof`.
These are source/work-count checks; they establish neither Wii elapsed
time nor the combined build's on-console appearance.
