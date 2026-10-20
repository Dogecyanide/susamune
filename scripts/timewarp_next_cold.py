"""Private CreationEditor cold-code proof; production selectors are unchanged."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile

import gen_mod_bin
import link_pinned_mod as pinned
import timewarp_cold_cluster as cold
import timewarp_linked_budget as budget
import timewarp_timer_guard as timer

ROOT = Path(__file__).resolve().parents[1]


def extract(build, region, sections, relocations, protected):
    objects, owners = budget.object_inputs(build, region)
    owners["__modules__"] = set(objects)
    image = budget.LinkedImage(build / f"susamune_{region}.o", owners)
    obj = objects["creation.cpp"]
    selected = []
    source = build / f"CMakeFiles/susamune_obj_{region}.dir/src/creation.cpp.obj"
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        for index, definitions in obj["definitions"].items():
            matches = [(s, f) for s in definitions for f in image.resolve(s)
                       if "__14CreationEditor" in s["name"] and s["type"] == "STT_FUNC"]
            if not matches:
                continue
            section = elf.get_section(index)
            if len(matches) != 1 or len(definitions) != 1:
                raise ValueError("Editor function shares an input section")
            source_symbol, final = matches[0]
            if source_symbol["address"] or source_symbol["size"] != section["sh_size"] or final["size"] != section["sh_size"]:
                raise ValueError("Editor function boundaries differ")
            function = {"name": source_symbol["name"], "old_address": final["address"],
                        "size": final["size"], "object_section": index, "object_section_name": section.name}
            records = [r for r in relocations if final["address"] <= r["site"] < final["address"] + final["size"]]
            expected = [r for r in obj["relocations"] if r["section"] == index]
            if sorted((r["site"] - final["address"], r["type"]) for r in records) != sorted((r["offset"], r["type"]) for r in expected):
                raise ValueError("Editor object/final relocation inventories differ")
            data = bytearray(section.data())
            for relocation in records:
                cold.apply_relocation(data, relocation["site"] - final["address"], relocation, relocation["site"])
            if data != pinned.range_bytes(sections, final["address"], final["size"]):
                raise ValueError("Current source object does not reconstruct editor bytes")
            sites = {r["site"] for r in records}
            for offset in range(0, len(data), 4):
                word = struct.unpack_from(">I", data, offset)[0]
                opcode = word >> 26
                if opcode not in (16, 18):
                    continue
                if word & 2:
                    raise ValueError("Editor contains an absolute branch")
                mask, sign = (0xFFFC, 0x8000) if opcode == 16 else (0x3FFFFFC, 0x2000000)
                delta = word & mask
                if delta & sign:
                    delta -= sign * 2
                target = final["address"] + offset + delta
                if not final["address"] <= target < final["address"] + final["size"] and final["address"] + offset not in sites:
                    raise ValueError("External editor branch has no authoritative relocation")
            interior = [r for r in relocations if final["address"] < r["target"] < final["address"] + final["size"]]
            if interior:
                function["jump_table"] = cold.audit_jump_table(elf, obj, function, interior, records, relocations, sections, protected)
            function["data"], function["relocations"] = bytes(data), records
            selected.append(function)
    if len(selected) != 7:
        raise ValueError("CreationEditor selector inventory changed")
    return sorted(selected, key=lambda f: f["old_address"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "build/timewarp-pinned-link/source-console")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-next-cold/creation-pal")
    args = parser.parse_args()
    build, folder, region = args.build.resolve(), args.output.resolve(), "pal"
    if not folder.is_relative_to((ROOT / "build/timewarp-next-cold").resolve()):
        parser.error("Private proof output must remain in its own build tree")
    folder.mkdir(parents=True, exist_ok=True)
    source_path = build / f"susamune_{region}.o"
    source_hash = pinned.file_sha(source_path)
    frozen = json.loads(timer.BASELINE.read_text())
    ownership = json.loads(pinned.LAYOUT.read_text())["builds"]["console-pal"]
    protected = list(frozen["builds"]["console-pal"]["symbols"].values()) + ownership["anchors"]
    sections = cold.elf_sections(source_path)
    relocations = cold.final_relocations(source_path)
    functions = extract(build, region, sections, relocations, protected)
    previous = json.loads((build / "pinned-link/pal/receipt.json").read_text())
    previous_cold = (build / "pinned-link/pal/cold-pal.bin").read_bytes()
    new_vma = 0x91E3F0A0 + len(previous_cold)
    linked = cold.link_cold(folder, functions, new_vma, "creation")
    payload = previous_cold + (folder / "cold-creation.bin").read_bytes()
    combined = folder / "combined-cold.bin"
    combined.write_bytes(payload)
    original = source_path.read_bytes()
    patched = bytearray(original)
    allowed = set()
    holes = []
    for function in functions:
        address, size = function["old_address"], function["size"]
        if any(address < p["address"] + p["size"] and p["address"] < address + size for p in protected):
            raise ValueError("Editor relocation overlaps a protected timer/dependency")
        offset = cold.file_offset(sections, address, size)
        patched[offset:offset + size] = cold.veneer(function["cold_address"]) + bytes(size - 16)
        allowed.update(range(offset, offset + size))
        holes.append({"begin": address + 16, "end": address + size, "bytes": size - 16})
        for entry in function.get("jump_table", {}).get("entries", []):
            offset = cold.file_offset(sections, entry["site"], 4)
            if int.from_bytes(original[offset:offset + 4], "big") != entry["target"]:
                raise ValueError("Jump-table source word changed")
            struct.pack_into(">I", patched, offset, function["cold_address"] + entry["target"] - address)
            allowed.update(range(offset, offset + 4))
    if any(a != b and index not in allowed for index, (a, b) in enumerate(zip(original, patched))):
        raise ValueError("Editor proof changed unrelated bytes")
    output = folder / "retained-creation.elf"
    output.write_bytes(patched)
    protection = pinned.verify_protected(output, build, region, "console", ownership, frozen)
    restored_sections = cold.elf_sections(output)
    for function in functions:
        if pinned.range_bytes(restored_sections, function["old_address"], 16) != cold.veneer(function["cold_address"]):
            raise ValueError("Old editor entry veneer differs")
    if payload[:len(previous_cold)] != previous_cold:
        raise ValueError("Existing cold image changed")
    cold_identity = {"vma": 0x91E3F0A0, "size": len(payload), "sha256": pinned.sha(payload)}
    receipt = {"passed": True, "target": "console", "region": "pal", "cold_image": cold_identity,
               "scope": "Private additional-cluster relocation/transport proof; no source allocator integration or runtime claim.",
               "source_elf_sha256": source_hash, "protection": protection,
               "editor_code_bytes": sum(f["size"] for f in functions), "entry_veneer_bytes": 16 * len(functions),
               "new_reusable_mem1_bytes": sum(h["bytes"] for h in holes),
               "combined_reusable_mem1_bytes": previous["recovered_bytes_remaining"] + sum(h["bytes"] for h in holes),
               "holes": holes, "existing_cold_prefix_unchanged": True,
               "cold_append": linked, "outbound_target_count": linked["outbound_gate_count"],
               "functions": [{k: v for k, v in f.items() if k != "data"} for f in functions],
               "rewritten_jump_table_words": sum(len(f.get("jump_table", {}).get("entries", [])) for f in functions),
               "unrelated_bytes_unchanged": True}
    receipt_path = folder / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    manifest = pinned.make_manifest(output, region, "console", combined, cold_identity["vma"], receipt_path)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    packed = gen_mod_bin.build_mod_bin(manifest, format_version=4, base_dir=folder)
    (folder / "mod-pal.bin").write_bytes(packed)
    summary = {"passed": True, "new_reusable_mem1_bytes": receipt["new_reusable_mem1_bytes"],
               "combined_reusable_mem1_bytes": receipt["combined_reusable_mem1_bytes"],
               "new_container_bytes": len(packed), "source_elf_unchanged": source_hash == pinned.file_sha(source_path)}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
