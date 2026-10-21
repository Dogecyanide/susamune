"""Pack the mod manifest produced by `link_mod.py launcher` into mod_<vers>.bin,
the file the launcher ships next to boot.dol and loads at runtime.

V3 is the default: a 32-byte big-endian header, two segment descriptors,
initialized payloads and hook writes. Optional V4 compresses the initialized
payloads with independent Quick blocks and validates the complete container
before installation. Both formats preserve the attachment heap and timer scratch.
The hook writes travel with the code because their addresses are version-specific.

Usage: gen_mod_bin.py MANIFEST.json -o mod_jp.bin
"""
import argparse
import hashlib
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
# The Japanese UI asset lives after the patch-file prefix, so JP shares the ceiling.
JP_STAGED_FILE_MAX_SIZE = STAGED_FILE_MAX_SIZE
BLOB_MAX_SIZE = shared_int_define("SUSAMUNE_MOD_BLOB_MAX_SIZE", "mod_bin.h")


def verified_artifact(info, base_dir, label):
    if not isinstance(info, dict) or not isinstance(info.get("path"), str):
        raise ValueError(label + " requires an artifact path")
    path = Path(info["path"])
    if not path.is_absolute():
        if base_dir is None:
            raise ValueError(label + " needs the manifest directory for its relative path")
        path = Path(base_dir) / path
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != info.get("sha256"):
        raise ValueError(label + " artifact checksum mismatch")
    return data


def build_mod_bin(manifest, *, format_version=3, base_dir=None):
    if format_version == 4:
        from mod_transport import ARENA, BASES, GAMES, build_mod_v4, encode_quick
        game = manifest["game_id"]
        if BASES.get(game) != manifest["base_addr"] or manifest.get("region_reserve") != ARENA:
            raise ValueError("manifest revision or arena reservation mismatch")
        segments = []
        for item in manifest["segments"]:
            raw = bytes.fromhex(item["code"])
            segment = dict(offset=item["offset"], memory_size=item["memory_size"], raw=raw)
            if raw:
                packed = encode_quick(raw)
                if len(packed) < len(raw):
                    segment["quick"] = packed
            segments.append(segment)
        cold = cold_vma = None
        flags = 0
        if "cold_image" in manifest or "pinned_link_receipt" in manifest:
            info = manifest.get("cold_image")
            cold = verified_artifact(info, base_dir, "cold image")
            if type(info.get("size")) is not int or info["size"] != len(cold):
                raise ValueError("cold image size mismatch")
            cold_vma = info.get("vma")
            if type(cold_vma) is not int:
                raise ValueError("cold image VMA must be an integer")
            environment = manifest.get("transport_environment")
            if environment not in ("console", "dolphin"):
                raise ValueError("cold image needs an explicit transport environment")
            flags = int(environment == "dolphin")
            proof = json.loads(verified_artifact(manifest.get("pinned_link_receipt"),
                                                base_dir, "pinned link receipt"))
            region = next(name for name, value in GAMES.items() if value == game)
            if (proof.get("passed") is not True or proof.get("region") != region or
                    proof.get("target") != ("emu" if flags else "console") or
                    any(proof.get("cold_image", {}).get(key) != info[key]
                        for key in ("vma", "size", "sha256"))):
                raise ValueError("pinned link receipt does not bind this cold image")
        menu_code = menu_vma = None
        if "menu_code" in manifest:
            info = manifest["menu_code"]
            menu_code = verified_artifact(info, base_dir, "menu code")
            menu_vma = info.get("vma")
            if not cold or proof.get("menu_code") != info:
                raise ValueError("Pinned receipt does not bind this menu code")
        return build_mod_v4(game, segments, manifest["writes"], flags=flags,
                            cold=cold, cold_vma=cold_vma, menu_code=menu_code, menu_vma=menu_vma)
    if format_version != 3:
        raise ValueError("unsupported mod format")
    if "cold_image" in manifest or "pinned_link_receipt" in manifest:
        raise ValueError("cold images require V4 transport")
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
    ap.add_argument("--format", choices=("v3", "v4"), default="v3")
    args = ap.parse_args(argv)

    path = Path(args.manifest).resolve()
    manifest = json.loads(path.read_text())
    Path(args.output).write_bytes(build_mod_bin(manifest, format_version=int(args.format[1:]),
                                              base_dir=path.parent))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
