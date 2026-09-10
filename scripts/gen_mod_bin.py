"""Pack the mod manifest produced by `link_mod.py launcher` into mod_<vers>.bin,
the file the launcher ships next to boot.dol and loads at runtime.

Format is struct SusamuneModHeader from include/susamune/mod_bin.h: a 32-byte
big-endian header, two segment descriptors and initialized payloads, then
the hook writes. The kernel zeroes each omitted BSS tail without touching the
attachment heap or fixed timer scratch. The writes travel with the code because their addresses are
version-specific -- a blob on its own is not applicable to anything.

Usage: gen_mod_bin.py MANIFEST.json -o mod_jp.bin
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

def shared_int_define(name, header_name="mem2_map.h"):
    header = (Path(__file__).parent.parent / "include" / "susamune" /
              header_name)
    match = re.search(
        r"^#define\s+{}\s+(0x[0-9a-fA-F]+|[0-9]+)u?"
        r"[ \t]*(?://[^\r\n]*)?$".format(
            re.escape(name)),
        header.read_text(), re.M)
    if not match:
        raise RuntimeError("{} not found in {}".format(name, header))
    return int(match.group(1), 0)


# These values define the wire format. Read the shared C header so the host
# packer cannot silently emit a different version or header layout.
MAGIC = shared_int_define("SUSAMUNE_MOD_MAGIC", "mod_bin.h")
VERSION = shared_int_define("SUSAMUNE_MOD_VERSION", "mod_bin.h")
HEADER_SIZE = shared_int_define("SUSAMUNE_MOD_HEADER_SIZE", "mod_bin.h")


# The loader refuses a larger file, so fail the build instead of shipping one
# that cannot be staged. Read the shared C header rather than duplicating it.
STAGING_WINDOW_SIZE = shared_int_define("SUSAMUNE_MEM2_MODBIN_SIZE")
STAGED_FILE_MAX_SIZE = shared_int_define("SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE")
JP_STAGED_FILE_MAX_SIZE = shared_int_define("SUSAMUNE_JP_UI_OFFSET", "japanese_ui.h")
BLOB_MAX_SIZE = shared_int_define("SUSAMUNE_MOD_BLOB_MAX_SIZE", "mod_bin.h")


def build_mod_bin(manifest):
    segments = manifest.get("segments")
    if not isinstance(segments, list) or len(segments) != 2:
        raise ValueError("V3 requires exactly two image segments")
    table = bytearray()
    payload = bytearray()
    memory_size = 0
    for segment, (offset, cap) in zip(segments, ((0, 0x58000), (0x80000, 0x40000))):
        code = bytes.fromhex(segment["code"])
        size = segment["memory_size"]
        if segment["offset"] != offset or type(size) is not int:
            raise ValueError("invalid segment placement")
        if len(code) % 4 or size % 4 or not len(code) <= size <= cap:
            raise ValueError("segment exceeds its permitted MEM1 span")
        table.extend(struct.pack(">4I", offset, len(code), size, 32 + len(payload)))
        payload.extend(code)
        memory_size += size
    code = bytes(table + payload)
    writes = manifest["writes"]
    base = manifest["base_addr"]
    bases = {0x474D534A: 0x80426020, 0x474D5345: 0x80429800, 0x474D5350: 0x80420D60}
    if bases.get(manifest["game_id"]) != base or manifest.get("region_reserve") != 0xC2000:
        raise ValueError("manifest revision or arena reservation mismatch")
    for addr, val in writes:
        if type(addr) is not int or addr % 4 or not 0x80000000 <= addr < base:
            raise ValueError("hook destination is outside retail MEM1")
        if type(val) is not int or not 0 <= val <= 0xFFFFFFFF:
            raise ValueError("invalid hook word")
    body = code + b"".join(struct.pack(">II", addr, val) for addr, val in writes)

    header = struct.pack(
        ">8I",
        MAGIC,
        VERSION,
        manifest["game_id"],
        manifest["base_addr"],
        len(code),
        len(writes),
        manifest.get("region_reserve", 0),
        memory_size,
    )
    assert len(header) == HEADER_SIZE
    total = HEADER_SIZE + len(body)
    if total > STAGED_FILE_MAX_SIZE:
        raise ValueError(
            f"mod bin is {total:#x} bytes, over the {STAGED_FILE_MAX_SIZE:#x} "
            "reset-safe ceiling (see SUSAMUNE_MOD_STAGED_FILE_MAX_SIZE)")
    if total > STAGING_WINDOW_SIZE:
        raise ValueError("mod bin exceeds its MEM2 staging window")
    if manifest["game_id"] == 0x474D534A and total > JP_STAGED_FILE_MAX_SIZE:
        raise ValueError("JP mod bin overlaps the immutable Japanese UI asset")
    return header + body


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="Mod manifest JSON from link_mod.py launcher")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())
    Path(args.output).write_bytes(build_mod_bin(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
