The Japanese game UI uses a subset of Droid Sans Japanese, distributed under
the Apache License 2.0. `Droid-LICENSE.txt` is preserved from Dolphin's font
distribution. The input `droid-japanese.yay` is Dolphin's `Sys/GC/font_japanese.bin`;
the generator downsamples only the required glyphs to a 16-pixel, four-shade atlas.

The glyph order in `droid-japanese-codepoints.json` follows the Shift-JIS table in
[Dolphin's gc-font-tool.cpp](https://github.com/dolphin-emu/dolphin/blob/master/docs/gc-font-tool.cpp)
(Dolphin contributors and James Cowgill, GPL-2.0-or-later). The font file is from
[Dolphin's font resources](https://github.com/dolphin-emu/dolphin/tree/master/Data/Sys/GC).

Build the bounded catalogue and subset with `scripts/gen_japanese_ui.py`.
No retail Sunshine font or IPL image is included in the output.
