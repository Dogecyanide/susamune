"""Preserve source ownership before the partial linker combines input sections."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import struct

import pinned_menu_constants as menu_constants
import pinned_string_atoms as string_atoms
import pinned_numeric_protection as numeric_protection
import pinned_header_constants as header_constants

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "doc/timewarp-pinned-source-owners.json"
MERGE_LAYOUT = ROOT / "doc/timewarp-pinned-merge-sources.json"
NUMERIC_LAYOUT = ROOT / "doc/timewarp-pinned-numeric-pools.json"
MIXED = (".foxtrot.text", ".foxtrot.rodata", ".foxtrot.data", ".foxtrot.bss")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def definitions(elf):
    result = {}
    for symbol in elf.get_section_by_name(".symtab").iter_symbols():
        if isinstance(symbol["st_shndx"], int) and symbol["st_size"]:
            result.setdefault(symbol["st_shndx"], []).append({
                "name": symbol.name, "value": symbol["st_value"], "size": symbol["st_size"],
                "bind": symbol["st_info"]["bind"], "type": symbol["st_info"]["type"]})
    return result


def definition_key(row):
    return tuple(row[k] for k in ("name", "value", "size", "bind", "type"))


def prepare(source, destination, region, toolchain, merge_sources=None, known_sections=None, immutable_menu=(), strings=None):
    import link_pinned_mod as pinned
    output = destination / f"CMakeFiles/susamune_obj_{region}.dir/src"
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted((source / f"CMakeFiles/susamune_obj_{region}.dir/src").glob("*.cpp.obj"))
    if not paths or {p.name for p in output.glob("*.cpp.obj")} - {p.name for p in paths}:
        raise ValueError("Source-owned object inventory is missing or stale; use a clean work directory")
    inventory, hashes, string_objects = [], {}, {}
    for path in paths:
        module, renamed, occurrences, original_occurrences = path.name[:-4], [], {}, {}
        unmerged = set()
        hashes[module] = pinned.file_sha(path)
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            symbols = definitions(elf)
            header_inputs = header_constants.validate(elf, module, known_sections)
            allocated = [(s["sh_type"], s["sh_flags"], s["sh_size"], s.data()) for s in elf.iter_sections()
                         if s["sh_flags"] & 2]
            for index, section in enumerate(elf.iter_sections()):
                defs = symbols.get(index, [])
                numeric_ordinal = original_occurrences.get(section.name, 0)
                original_occurrences[section.name] = numeric_ordinal + 1
                new_numeric = (merge_sources is not None and section["sh_flags"] == 0x12
                               and [section.name, numeric_ordinal] not in merge_sources.get(module, []))
                new_rodata = (merge_sources is not None
                              and (module not in merge_sources or known_sections is not None
                                   and section.name not in known_sections or
                                   module == "menu.cpp" and section.name in immutable_menu)
                              and (section["sh_flags"] == 2 and section.name.startswith(".rodata.")
                                   or section["sh_flags"] == 3 and section.name.startswith(".data.rel.ro."))
                              and not defs)
                local_code = (section["sh_flags"] == 6 and defs
                              and all(s["bind"] == "STB_LOCAL" and s["type"] == "STT_FUNC" for s in defs))
                new_header_constant = index in header_inputs
                if (section.name not in MIXED and not local_code and not new_numeric and not new_rodata
                        and not new_header_constant) or section["sh_flags"] & 0x200 or not section["sh_size"]:
                    continue
                if new_numeric:
                    unmerged.add(index)
                ordinal = occurrences.get(section.name, 0)
                occurrences[section.name] = ordinal + 1
                # Jump-table audits bind the compiler's per-function table name.
                name = (section.name if new_rodata else
                        section.name + ".owner." + module.replace(".", "_") + f".part{ordinal}")
                renamed.append({"index": index, "selector": name})
                if strings is not None and section["sh_flags"] & 0x22 == 0x22:
                    continue
                inventory.append({"owner": module, "original_name": section.name, "name": name,
                                  "source_section_index": index, "ordinal": ordinal,
                                  "bytes": section["sh_size"], "type": section["sh_type"],
                                  "flags": section["sh_flags"] & ~0x10 if new_numeric else section["sh_flags"],
                                  "align": max(1, section["sh_addralign"]),
                                  "entry_size": section["sh_entsize"],
                                  "sha256": digest(section.data()) if section["sh_type"] != "SHT_NOBITS" else None,
                                  "new_numeric": bool(new_numeric),
                                  "new_rodata": bool(new_rodata),
                                  "new_header_constant": bool(new_header_constant),
                                  "definitions": defs})
        transformed = output / path.name
        if renamed:
            pinned.rename_inputs(path, transformed, renamed)
        else:
            shutil.copyfile(path, transformed)
        if unmerged:
            # Renaming alone still lets ld reorder/deduplicate each numeric pool.
            data = bytearray(transformed.read_bytes())
            with transformed.open("rb") as stream:
                elf = ELFFile(stream)
                for index in unmerged:
                    header = elf["e_shoff"] + index * elf["e_shentsize"]
                    struct.pack_into(">I", data, header + 8, 2)
            transformed.write_bytes(data)
        with transformed.open("rb") as stream:
            current = [(s["sh_type"], s["sh_flags"], s["sh_size"], s.data()) for s in ELFFile(stream).iter_sections()
                       if s["sh_flags"] & 2]
        with path.open("rb") as stream:
            expected = [(s["sh_type"], s["sh_flags"] & ~0x10 if i in unmerged else s["sh_flags"], s["sh_size"], s.data())
                        for i, s in enumerate(ELFFile(stream).iter_sections()) if s["sh_flags"] & 2]
        if current != expected or [(r[0], r[2], r[3]) for r in current] != [(r[0], r[2], r[3]) for r in allocated]:
            raise ValueError("Source-owned rename changed allocated bytes: " + module)
        if strings is not None:
            string_objects[module] = string_atoms.split_object(transformed, strings["protected_atoms"])
    partial = destination / f"susamune_pre_{region}.o"
    pinned.run([toolchain / "clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi",
                "-nodefaultlibs", "-nostdlib", "-fuse-ld=lld", "-r",
                *sorted(output.glob("*.cpp.obj")), "-o", partial], destination)
    atom_proof = string_atoms.normalize_partial(partial, string_objects, strings["protected_atoms"]) if strings is not None else None
    return partial, {"parts": inventory, "original_object_sha256": hashes, "string_atoms": atom_proof,
                     "string_sources": string_objects, "allocated_payloads_unchanged": True, "partial_sha256": pinned.file_sha(partial)}


def verify_parts(rows, proof, baseline):
    current = {r["name"]: r for r in rows if not r["group"]}
    old = {(r["name"], r["group"]): r for r in baseline["sections"]}
    for part in proof["parts"]:
        row = current.get(part["name"])
        unattributed = part["new_numeric"] or part.get("new_rodata", False)
        if (row is None or row["owners"] not in ([part["owner"]], [] if unattributed else [part["owner"]])
                or any(row[k] != part[k] for k in ("bytes", "type", "flags", "align", "entry_size", "sha256"))
                or sorted(map(definition_key, row["definitions"])) != sorted(map(definition_key, part["definitions"]))):
            raise ValueError("Source-owned partial contribution differs: " + part["name"])
        previous = old.get((part["name"], ""))
        if previous and previous["owners"] != [part["owner"]]:
            raise ValueError("Frozen source ownership differs: " + part["name"])
        row["source_owned_verified"] = True
        row["source_owner"] = part["owner"]
        row["source_owned_numeric"] = part["new_numeric"]
        row["owners"] = [part["owner"]]
    if proof.get("string_atoms") is not None:
        string_atoms.verify_current(rows, proof["string_atoms"])


def expand_layout(path, ownership_path, ownership, target, region, timer_path):
    import link_pinned_mod as pinned
    source = json.loads(path.read_text())
    if (source["version"] != 1 or source["original_layout_sha256"] != pinned.file_sha(ownership_path)
            or source["timer_baseline_sha256"] != pinned.file_sha(timer_path)):
        raise ValueError("Source ownership does not match the frozen layout/timer baseline")
    entry = source["builds"][f"{target}-{region}"]
    baseline = deepcopy(ownership["builds"][f"{target}-{region}"])
    if entry["source_elf_sha256"] != baseline["source_elf_sha256"]:
        raise ValueError("Source ownership names a different baseline image")
    replaced = set(entry["replaced_names"])
    baseline["sections"] = [r for r in baseline["sections"] if r["group"] or r["name"] not in replaced]
    baseline["sections"].extend(entry["sections"])
    merge = json.loads(MERGE_LAYOUT.read_text())
    if merge["source_ownership_sha256"] != pinned.file_sha(path):
        raise ValueError("Numeric merge ownership does not match source ownership")
    baseline["merge_sources"] = merge["builds"][f"{target}-{region}"]
    numeric = json.loads(NUMERIC_LAYOUT.read_text())
    if (numeric["original_layout_sha256"] != pinned.file_sha(ownership_path)
            or numeric["timer_baseline_sha256"] != pinned.file_sha(timer_path)):
        raise ValueError("Numeric pools do not match the frozen layout/timer baseline")
    pools = numeric["builds"][f"{target}-{region}"]
    original_numeric = {r["name"]: r for r in ownership["builds"][f"{target}-{region}"]["sections"]
                        if r["live"] and r["flags"] == 0x12 and not r["group"]}
    if pools.keys() != original_numeric.keys():
        raise ValueError("Numeric pool inventory differs from the frozen layout")
    for name, record in pools.items():
        original = original_numeric[name]
        if (any(record[k] != original[k] for k in ("address", "bytes", "sha256"))
                or record["entry_size"] not in (0, 4, 8, 16, 32)
                or record["unprotected"] != (not record["protected_references"] and not record["protected_range_overlap"])):
            raise ValueError("Numeric pool protection evidence is inconsistent: " + name)
    baseline["numeric_pools"] = {name: record for name, record in pools.items() if record["unprotected"]}
    baseline["immutable_menu_constants"] = menu_constants.load(menu_constants.LAYOUT,
        ownership_path, path, timer_path, ownership["builds"][f"{target}-{region}"], entry, f"{target}-{region}")
    for row in baseline["sections"]:
        if not row["group"] and row["name"] in baseline["immutable_menu_constants"]:
            row["owners"] = ["menu.cpp"]
            row["immutable_menu_verified"] = True
    string_atoms.expand(baseline, string_atoms.load(ownership_path, path, timer_path,
        ownership["builds"][f"{target}-{region}"], entry, f"{target}-{region}"))
    return baseline


def capture_merge_sources():
    import link_pinned_mod as pinned
    source_owners = json.loads(LAYOUT.read_text())
    result = {"version": 1, "source_ownership_sha256": pinned.file_sha(LAYOUT), "builds": {}}
    for key, record in source_owners["builds"].items():
        target, region = key.split("-")
        root = ROOT / f"build/baseline-{target}/CMakeFiles/susamune_obj_{region}.dir/src"
        result["builds"][key] = {}
        for module, expected in record["original_object_sha256"].items():
            path = root / (module + ".obj")
            if pinned.file_sha(path) != expected:
                raise ValueError("Original source object changed: " + module)
            entries, counts = [], {}
            with path.open("rb") as stream:
                for section in ELFFile(stream).iter_sections():
                    ordinal = counts.get(section.name, 0)
                    counts[section.name] = ordinal + 1
                    if section["sh_flags"] == 0x12:
                        entries.append([section.name, ordinal])
            result["builds"][key][module] = entries
    return result


def capture_numeric_pools():
    import link_pinned_mod as pinned
    import timewarp_cold_cluster as cold
    import timewarp_timer_guard as timer
    ownership = json.loads(pinned.LAYOUT.read_text())
    frozen = json.loads(timer.BASELINE.read_text())
    result = {"version": 1, "original_layout_sha256": pinned.file_sha(pinned.LAYOUT),
              "timer_baseline_sha256": pinned.file_sha(timer.BASELINE), "builds": {}}
    for key, baseline in ownership["builds"].items():
        target, region = key.split("-")
        source = ROOT / f"build/baseline-{target}"
        image, partial = source / f"susamune_{region}.o", source / f"susamune_pre_{region}.o"
        if pinned.file_sha(image) != baseline["source_elf_sha256"] or pinned.file_sha(partial) != baseline["source_partial_sha256"]:
            raise ValueError("Numeric pool baseline differs")
        protected = list(frozen["builds"][key]["symbols"].values()) + baseline["anchors"]
        incoming = numeric_protection.frozen_references(partial, baseline, protected)
        result["builds"][key] = {}
        with partial.open("rb") as stream:
            elf = ELFFile(stream)
            for row in baseline["sections"]:
                if not row["live"] or row["flags"] != 0x12 or row["group"]:
                    continue
                begin, end = row["address"], row["address"] + row["linked_bytes"]
                references = incoming[row["name"]]
                overlaps = any(begin < p["address"] + p["size"] and p["address"] < end for p in protected)
                result["builds"][key][row["name"]] = {
                    "address": begin, "bytes": row["bytes"], "sha256": row["sha256"],
                    "entry_size": elf.get_section(row["index"])["sh_entsize"],
                    "unprotected": not references and not overlaps,
                    "protected_references": references, "protected_range_overlap": overlaps}
    return result


def capture_one(folder, target, region):
    import link_pinned_mod as pinned
    import timewarp_linked_budget as budget
    import timewarp_timer_guard as timer
    source = ROOT / f"build/baseline-{target}"
    original = source / f"susamune_{region}.o"
    baseline = deepcopy(json.loads(pinned.LAYOUT.read_text())["builds"][f"{target}-{region}"])
    if pinned.file_sha(original) != baseline["source_elf_sha256"]:
        raise ValueError("Immutable baseline ELF identity differs")
    objects, owners = budget.object_inputs(source, region)
    owners["__modules__"] = set(objects)
    linked = budget.LinkedImage(original, owners)
    partial, proof = prepare(source, folder, region, ROOT / "toolchain")
    rows, symbols, relocs, _ = pinned.inputs(partial, folder, region)
    current = {r["name"]: r for r in rows if not r["group"]}
    records = []
    for part in proof["parts"]:
        defs = objects[part["owner"]]["definitions"][part["source_section_index"]]
        resolutions = [(s, final) for s in defs for final in linked.resolve(s)]
        bases = {final["address"] - s["address"] for s, final in resolutions}
        if resolutions and (len(bases) != 1 or len(resolutions) != len(defs)):
            raise ValueError("Source definitions disagree on their baseline origin: " + part["name"])
        row = current[part["name"]]
        record = {k: v for k, v in row.items() if k not in ("selector", "definitions")}
        record.update(address=bases.pop() if bases else 0, linked_bytes=row["bytes"], live=bool(resolutions),
                      cold=False, definition_count=len(row["definitions"]), source_owned=True)
        records.append(record)
    replaced = sorted({r["original_name"] for r in proof["parts"]})
    baseline["sections"] = [r for r in baseline["sections"] if r["group"] or r["name"] not in replaced] + records
    verify_parts(rows, proof, baseline)
    pinned.plan_sections(rows, symbols, relocs, baseline, [])
    unique, layout, output = folder / "unique.o", folder / "baseline.ld", folder / "baseline.elf"
    pinned.rename_inputs(partial, unique, rows)
    pinned.write_layout(layout, rows)
    pinned.gnu_link(folder, output, unique, region, layout, ROOT / "toolchain")
    after = pinned.flat_sections(output)
    verified = 0
    for section in pinned.flat_sections(original).values():
        if section["data"] is None:
            continue
        assembled = bytearray(section["size"])
        for part in after.values():
            begin = max(section["address"], part["address"])
            end = min(section["address"] + section["size"], part["address"] + part["size"])
            if begin < end and part["data"] is not None:
                assembled[begin - section["address"]:end - section["address"]] = part["data"][begin - part["address"]:end - part["address"]]
        if assembled != section["data"]:
            raise ValueError("Source-owned baseline relink changes bytes: " + section["name"])
        verified += section["size"]
    protection = pinned.verify_protected(output, folder, region, target, baseline, json.loads(timer.BASELINE.read_text()))
    return {"source_elf_sha256": pinned.file_sha(original), "original_object_sha256": proof["original_object_sha256"],
            "replaced_names": replaced, "sections": records, "original_initialized_bytes_identical": verified,
            "protection": protection}


def main():
    import link_pinned_mod as pinned
    import timewarp_timer_guard as timer
    parser = argparse.ArgumentParser(description="Create frozen source ownership without storing executable payloads")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--merge-sources", action="store_true")
    parser.add_argument("--numeric-pools", action="store_true")
    parser.add_argument("--work", type=Path, default=ROOT / "build/timewarp-pinned-source-owners")
    args = parser.parse_args()
    args.output = args.output or (NUMERIC_LAYOUT if args.numeric_pools else MERGE_LAYOUT if args.merge_sources else LAYOUT)
    if args.output.exists():
        parser.error("Source ownership capture is create-only")
    if args.merge_sources or args.numeric_pools:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(capture_numeric_pools() if args.numeric_pools else capture_merge_sources(), stream, separators=(",", ":"))
            stream.write("\n")
        return
    result = {"version": 1, "original_layout_sha256": pinned.file_sha(pinned.LAYOUT),
              "timer_baseline_sha256": pinned.file_sha(timer.BASELINE), "builds": {},
              "scope": "Frozen addresses and source ownership only; no executable or data payloads."}
    for target in ("console", "emu"):
        for region in ("jp", "us", "pal"):
            key = f"{target}-{region}"
            result["builds"][key] = capture_one(args.work.resolve() / key, target, region)
            print(key + ": source-owned baseline bytes identical", flush=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, separators=(",", ":"))
        stream.write("\n")


if __name__ == "__main__":
    main()
