"""Private source-owned pragma-section split and storage-growth linker proof."""
from __future__ import annotations

import argparse
from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil
import sys

from elftools.elf.elffile import ELFFile
import gen_mod_bin
import link_pinned_mod as pinned
import test_pinned_source_build as fixture
import timewarp_linked_budget as budget
import timewarp_timer_guard as timer

ROOT = pinned.ROOT
MIXED = (".foxtrot.text", ".foxtrot.rodata", ".foxtrot.data", ".foxtrot.bss")


def owner_name(section, module):
    return section + ".owner." + module.replace(".", "_")


def split_objects(source, destination, region):
    output = destination / f"CMakeFiles/susamune_obj_{region}.dir/src"
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted((source / f"CMakeFiles/susamune_obj_{region}.dir/src").glob("*.cpp.obj"))
    inventory = []
    for path in paths:
        module = path.name[:-4]
        rows = []
        occurrences = {}
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            before = [(s["sh_type"], s["sh_flags"], s["sh_size"], s.data()) for s in elf.iter_sections()
                      if s["sh_flags"] & 2]
            definitions = {}
            for symbol in elf.get_section_by_name(".symtab").iter_symbols():
                if isinstance(symbol["st_shndx"], int) and symbol["st_size"]:
                    definitions.setdefault(symbol["st_shndx"], []).append(symbol)
            for index, section in enumerate(elf.iter_sections()):
                local_code = (section["sh_flags"] == 6 and definitions.get(index)
                              and all(s["st_info"]["bind"] == "STB_LOCAL" and s["st_info"]["type"] == "STT_FUNC"
                                      for s in definitions[index]))
                if (section.name in MIXED or local_code) and not section["sh_flags"] & 0x200 and section["sh_size"]:
                    ordinal = occurrences.get(section.name, 0)
                    occurrences[section.name] = ordinal + 1
                    rows.append({"index": index, "selector": owner_name(section.name, module) + f".part{ordinal}"})
                    inventory.append({"owner": module, "section": section.name, "name": rows[-1]["selector"],
                                      "size": section["sh_size"], "source_section_index": index,
                                      "source_sha256": pinned.file_sha(path)})
        transformed = output / path.name
        if rows:
            pinned.rename_inputs(path, transformed, rows)
        else:
            shutil.copyfile(path, transformed)
        with transformed.open("rb") as stream:
            after = [(s["sh_type"], s["sh_flags"], s["sh_size"], s.data()) for s in ELFFile(stream).iter_sections()
                     if s["sh_flags"] & 2]
        if before != after:
            raise ValueError("Source section rename changed allocated payload: " + module)
    fixture.partial(destination, region)
    return inventory


def capture(folder, target, region):
    source = ROOT / f"build/baseline-{target}"
    original = source / f"susamune_{region}.o"
    frozen = json.loads(pinned.LAYOUT.read_text())
    baseline = deepcopy(frozen["builds"][f"{target}-{region}"])
    if pinned.file_sha(original) != baseline["source_elf_sha256"]:
        raise ValueError("Immutable baseline ELF identity differs")
    objects, owners = budget.object_inputs(source, region)
    owners["__modules__"] = set(objects)
    linked = budget.LinkedImage(original, owners)
    inventory = split_objects(source, folder, region)
    partial = folder / f"susamune_pre_{region}.o"
    rows, symbols, relocs, _ = pinned.inputs(partial, folder, region)
    addresses = {}
    for contribution in inventory:
        obj = objects[contribution["owner"]]
        definitions = obj["definitions"][contribution["source_section_index"]]
        resolutions = [(s, target) for s in definitions for target in linked.resolve(s)]
        bases = {target["address"] - s["address"] for s, target in resolutions}
        if resolutions and (len(bases) != 1 or len(resolutions) != len(definitions)):
            raise ValueError("Source definitions disagree on their baseline origin: " + contribution["name"])
        contribution["address"] = bases.pop() if bases else 0
        contribution["live"] = bool(resolutions)
        contribution["definitions"] = len(definitions)
        addresses[contribution["name"]] = contribution
    renamed = {r["section"] for r in inventory}
    baseline["sections"] = [s for s in baseline["sections"] if not (s["name"] in renamed and not s["group"])]
    for row in rows:
        if row["name"] not in addresses:
            continue
        contribution = addresses[row["name"]]
        if row["owners"] != [contribution["owner"]] or row["bytes"] != contribution["size"]:
            raise ValueError("Renamed contribution ownership differs: " + row["name"])
        record = {k: v for k, v in row.items() if k not in ("selector", "definitions")}
        record.update(address=contribution["address"], linked_bytes=row["bytes"], live=contribution["live"], cold=False,
                      definition_count=len(row["definitions"]), source_owned=True)
        baseline["sections"].append(record)
    frozen["builds"][f"{target}-{region}"] = baseline
    ownership = folder / "ownership.json"
    ownership.write_text(json.dumps(frozen, separators=(",", ":")) + "\n")
    pinned.plan_sections(rows, symbols, relocs, baseline, [])
    unique = folder / "unique.o"
    pinned.rename_inputs(partial, unique, rows)
    layout = folder / "baseline.ld"
    pinned.write_layout(layout, rows)
    output = folder / "baseline.elf"
    pinned.gnu_link(folder, output, unique, region, layout, ROOT / "toolchain")
    after = pinned.flat_sections(output)
    verified = 0
    for section in pinned.flat_sections(original).values():
        if section["data"] is None:
            continue
        assembled = bytearray(section["size"])
        for part in after.values():
            begin, end = max(section["address"], part["address"]), min(section["address"] + section["size"], part["address"] + part["size"])
            if begin < end and part["data"] is not None:
                assembled[begin - section["address"]:end - section["address"]] = part["data"][begin - part["address"]:end - part["address"]]
        if assembled != section["data"]:
            raise ValueError("Source-owned baseline relink changes bytes: " + section["name"])
        verified += section["size"]
    protection = pinned.verify_protected(output, folder, region, target, baseline, json.loads(timer.BASELINE.read_text()))
    result = {"source_baseline_sha256": pinned.file_sha(original), "contributions": inventory,
              "original_initialized_bytes_identical": verified, "protection": protection,
              "scope": "Address/ownership capture only; no baseline payload is stored in ownership metadata."}
    (folder / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    return ownership, result


def install_private_extensions():
    source = inspect.getsource(pinned.plan_sections)
    old = 'or len(row["definitions"]) != 1 or not row["owners"]):'
    new = 'or (len(row["definitions"]) != 1 and not (old and old.get("source_owned") and row["owners"] == old["owners"] and len(row["owners"]) == 1)) or not row["owners"]):'
    if source.count(old) != 1:
        raise ValueError("Private planner prototype no longer matches the production planner")
    exec(source.replace(old, new), pinned.__dict__)
    source = inspect.getsource(pinned.build)
    old = '''    cursor = plan["hole_begin"]
    for row in rows:
        if row["moved"]:
            cursor = cold.align(cursor, max(4, row["align"]))
            row["address"] = cursor
            cursor += row["linked_bytes"]
'''
    if source.count(old) != 1:
        raise ValueError("Private allocator prototype no longer matches the production allocator")
    pinned.__dict__["private_allocate"] = private_allocate
    exec(source.replace(old, '    cursor = private_allocate(rows, baseline, plan)\n'), pinned.__dict__)


def private_allocate(rows, baseline, plan):
    known = {pinned.key(row): row for row in baseline["sections"]}
    cursor = plan["hole_begin"]
    retired = []
    new_rows = []
    for row in rows:
        if not row["moved"]:
            continue
        old = known.get(pinned.key(row))
        if old is None:
            new_rows.append(row)
            continue
        cursor = pinned.cold.align(cursor, max(4, row["align"]))
        row["address"] = cursor
        cursor += row["linked_bytes"]
        if old["live"]:
            retired.append({"begin": old["address"], "end": old["address"] + old["linked_bytes"],
                            "name": old["name"], "used": 0})
    for row in new_rows:
        placed = False
        for hole in retired:
            address = pinned.cold.align(hole["begin"] + hole["used"], max(4, row["align"]))
            if address + row["linked_bytes"] <= hole["end"]:
                row["address"] = address
                hole["used"] = address + row["linked_bytes"] - hole["begin"]
                placed = True
                break
        if not placed:
            cursor = pinned.cold.align(cursor, max(4, row["align"]))
            row["address"] = cursor
            cursor += row["linked_bytes"]
    private_allocate.receipt = {"retired_ranges": retired, "retired_bytes": sum(h["end"] - h["begin"] for h in retired),
                                "retired_bytes_used": sum(h["used"] for h in retired),
                                "cold_hole_used": cursor - plan["hole_begin"]}
    return cursor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-owned-sections")
    parser.add_argument("--source", type=Path, default=ROOT / "build/timewarp-stream-console")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build/timewarp-owned-sections").resolve()):
        parser.error("Private output must remain in its own build tree")
    folder.mkdir(parents=True, exist_ok=True)
    region, target = "pal", "console"
    ownership, captured = capture(folder / "capture", target, region)
    original = folder / "growth-original"
    fixture.prepare(args.source.resolve(), original, region)
    edits = {
        "state_storage.cpp": "void init() {",
        "savestate.cpp": "bool captureLiveVideo() {",
    }
    for module, anchor in edits.items():
        text = (ROOT / "src" / module).read_text()
        if text.count(anchor) != 1:
            raise ValueError("Growth fixture anchor changed")
        text = text.replace(anchor, anchor + '\n __asm__ volatile(".rept 32\\n nop\\n .endr");')
        fixture.compile_copy(args.source.resolve(), original, region, module, text)
    fixture.compile_copy(args.source.resolve(), original, region, "checksum.cpp", fixture.new_source(), "new_source.cpp")
    split = folder / "growth-split"
    split_objects(original, split, region)
    install_private_extensions()
    arguments = argparse.Namespace(obj=split / f"susamune_pre_{region}.o", objects=split, ownership=ownership,
        kuribo_home=ROOT / "toolchain", vers=region, target=target, work=split / "link",
        elf=split / "susamune_pal.o", out=split / "manifest.json", root=["twp_new_code"])
    pinned.build(arguments)
    receipt = json.loads((split / "link/receipt.json").read_text())
    allocations = receipt["allocations"]
    if not all(any(row["name"].startswith(owner_name(".foxtrot.text", module) + ".") for row in allocations) for module in edits):
        raise ValueError("Real source-owned storage contributions did not grow/move")
    holes = private_allocate.receipt
    new = [r for r in allocations if r["name"].startswith(".twp.new.")]
    if sum(r["linked_bytes"] for r in new) != 256 or not all(any(h["begin"] <= r["address"] < r["address"] + r["linked_bytes"] <= h["end"] for h in holes["retired_ranges"]) for r in new):
        raise ValueError("New source did not occupy the retired original storage range")
    packed = gen_mod_bin.build_mod_bin(json.loads((split / "manifest.json").read_text()), format_version=4, base_dir=split)
    (split / "mod-pal.bin").write_bytes(packed)
    result = {"passed": True, "source_owned_contributions": len(captured["contributions"]),
              "baseline_initialized_bytes_identical": captured["original_initialized_bytes_identical"],
              "growth_protection": receipt["protection"], "allocations": allocations,
              "capacity": holes, "new_source_in_retired_range": 256, "mod_bytes": len(packed),
              "retained_relocation_sites_verified": receipt["retained_relocation_sites_verified"],
              "scope": "Private current-source split/growth proof; production linker and sources unchanged."}
    (folder / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("allocations", "capacity")}))


if __name__ == "__main__":
    main()
