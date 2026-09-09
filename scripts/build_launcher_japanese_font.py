#!/usr/bin/env python3
"""Subset an official Noto Sans Mono CJK JP variable TTF for launcher text."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]


def build(source, destination):
    catalog = (ROOT / "launcher/loader/source/SusamuneTextData.inc").read_text(encoding="utf-8")
    strings = [json.loads(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', catalog)]
    required = set(range(0x20, 0x7f)) | {0x25c0, 0x25b6}
    required.update(ord(c) for text in strings for c in text if ord(c) >= 0x20)
    font = TTFont(source, recalcTimestamp=False)
    missing = required - set(font.getBestCmap())
    if missing:
        raise ValueError(f"Source font lacks {sorted(missing)}")
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.notdef_glyph = options.notdef_outline = options.recommended_glyphs = True
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=required)
    sub.subset(font)
    font = instantiateVariableFont(font, {"wght": 400}, inplace=True)
    data = io.BytesIO()
    font.save(data)
    checked = TTFont(io.BytesIO(data.getvalue()))
    assert required <= set(checked.getBestCmap())
    assert "glyf" in checked and "fvar" not in checked and "gvar" not in checked
    assert len(data.getvalue()) < 512 * 1024
    info = zipfile.ZipInfo("font.ttf", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(info, data.getvalue())
    print(f"Japanese launcher: {len(required)} codepoints; {len(data.getvalue())} TTF bytes; {destination.stat().st_size} ZIP bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?",
                        default=ROOT / "launcher/loader/data/font_ja.zip")
    args = parser.parse_args()
    build(args.source, args.destination)
