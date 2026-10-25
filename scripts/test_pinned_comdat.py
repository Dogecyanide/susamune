"""Reject mismatched discarded COMDAT copies using current compiled source objects."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import struct

from elftools.elf.elffile import ELFFile
import link_pinned_mod as pinned


NAME = ".text.SusamuneTasManifestValidCapacity__FPC19SusamuneTasManifestUi"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-pinned-link/comdat-test")
    parser.add_argument("--name", default=NAME)
    parser.add_argument("--signature")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Private copies must stay in the task build directory")
    source = args.build.resolve()
    partial = source / "susamune_pre_pal.o"
    rows, _, _, objects = pinned.inputs(partial, source, "pal")
    row = next(r for r in rows if r["name"] == args.name and (not args.signature or r["group"] == args.signature))
    result = {"passed": False, "partial_sha256": pinned.file_sha(partial), "negative": {}}
    result["proof"] = pinned.certify_shared_comdat(row, partial, source, "pal", objects)
    destination = folder / "CMakeFiles/susamune_obj_pal.dir/src"
    destination.mkdir(parents=True, exist_ok=True)
    for owner in row["owners"]:
        shutil.copyfile(source / "CMakeFiles/susamune_obj_pal.dir/src" / (owner + ".obj"), destination / (owner + ".obj"))
    path = destination / (row["owners"][-1] + ".obj")
    original = path.read_bytes()
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        group = next(s for s in elf.iter_sections() if s["sh_type"] == "SHT_GROUP"
                     and table.get_symbol(s["sh_info"]).name == row["group"])
        indices = struct.unpack(">" + str(group["sh_size"] // 4) + "I", group.data())[1:]
        index, section = next((i, elf.get_section(i)) for i in indices if elf.get_section(i).name == args.name)
        payload_offset = section["sh_offset"]
        relocation_section = next(s for s in elf.iter_sections() if s["sh_type"] == "SHT_RELA" and s["sh_info"] == index)
        relocation_offset = relocation_section["sh_offset"]
        entries = list(relocation_section.iter_relocations())
        local_symbol = next(i for i, s in enumerate(elf.get_section_by_name(".symtab").iter_symbols())
                            if s["st_info"]["type"] == "STT_SECTION")
    variants = {}
    changed = bytearray(original)
    changed[payload_offset] ^= 1
    variants["discarded_copy_bytes"] = (changed, "copies differ")
    changed = bytearray(original)
    other = next(e for e in entries if e["r_info_sym"] != entries[0]["r_info_sym"])
    struct.pack_into(">I", changed, relocation_offset + 4, (other["r_info_sym"] << 8) | entries[0]["r_info_type"])
    variants["discarded_copy_relocation"] = (changed, "copies differ")
    changed = bytearray(original)
    struct.pack_into(">I", changed, relocation_offset + 4, (local_symbol << 8) | entries[0]["r_info_type"])
    variants["source_local_relocation"] = (changed, "source-local relocation")
    try:
        for name, (data, expected) in variants.items():
            path.write_bytes(data)
            current = deepcopy(objects)
            current[row["owners"][-1]]["sha256"] = pinned.file_sha(path)
            try:
                pinned.certify_shared_comdat(row, partial, folder, "pal", current)
            except ValueError as error:
                if expected not in str(error):
                    raise
                result["negative"][name] = {"rejected": True, "reason": str(error)}
            else:
                raise AssertionError("Mismatched discarded COMDAT was accepted: " + name)
        result["passed"] = True
    finally:
        path.write_bytes(original)
        (folder / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "owners": row["owners"], "negative_tests": len(variants)}))


if __name__ == "__main__":
    main()
