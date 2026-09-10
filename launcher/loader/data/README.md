# Launcher assets

`font.zip` contains a release-time subset of the pre-V2.2 DejaVu Sans Mono
Bold font. The generator keeps every letter, mark, number, punctuation, space,
and currency mapping that the source font actually contains, plus arrows,
geometric UI glyphs, and the replacement character. It therefore preserves the
source font's text coverage without making false claims for absent scripts or
keeping unrelated mathematical, technical, and decorative symbols resident.
The pre-V2.2 source has no CJK, Thai, or Myanmar mappings. The generated font
keeps 2,373 of its 3,069 cmap entries, including its Armenian, Lao, Georgian,
and Arabic presentation-form letters. The TTF is 189,844 bytes instead of
318,392; the embedded ZIP is 117,227 bytes instead of 181,041.

Rebuild it from an unmodified upstream archive with FontTools:

```console
python scripts/subset_launcher_font.py full-font.zip launcher/loader/data/font.zip
```

The source may be either an archive containing exactly one TTF or the TTF
itself. The script preserves font identity and licence records, checks printable
ASCII and both launcher arrow glyphs, verifies every selected codepoint and
advance width, and writes a deterministic archive.

The pre-V2.2 `background.png` was a single-colour 640x480 white image. Moonshine draws
that stock white field and its widescreen side bars as rectangles, avoiding a
1,228,800-byte RGBA texture. A user's `/Moonshine_Theme/background.png` is still decoded
at 1024x480 and rendered through the custom-theme path.


`font_ja.zip` is a static, 400-weight subset of the official
[Noto Sans Mono CJK JP variable TrueType font](https://github.com/notofonts/noto-cjk/blob/main/Sans/Variable/TTF/Mono/NotoSansMonoCJKjp-VF.ttf).
It covers printable ASCII, both controller arrows, and the Japanese launcher
catalog: 286 codepoints, 99,772 TTF bytes and 64,912 ZIP bytes. The original
English font stays active until JP is selected; the Japanese face is loaded
once on demand and freed before its backing buffer at launcher shutdown.
The SIL Open Font License is retained in `OFL-NotoSansCJK.txt` and must ship
with the launcher. Source SHA-256:
`9a91b2f42ad958fd4295586809f85366f0afa020b85ac70b39916c25bc5cda15`.

Regenerate with FontTools installed using
`scripts/build_launcher_japanese_font.py NotoSansMonoCJKjp-VF.ttf`.
The generator keeps the font's naming/license records and removes variable
font tables so the existing minimal TrueType renderer remains sufficient.
