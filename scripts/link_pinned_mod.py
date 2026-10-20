"""Opt-in source linker with protected timer islands and an audited cold menu.

The ownership receipt contains addresses and hashes, never executable payloads.
Every byte shipped by this linker comes from the current partial/source objects.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

from elftools.elf.elffile import ELFFile

from dol_c_kit.devkit_tools import BranchHook
import link_mod
import patches
import pinned_cold_extensions as cold_extensions
import pinned_menu_tables as menu_tables
import pinned_source_sections as owned_inputs
import timewarp_cold_cluster as cold
import timewarp_linked_budget as budget
import timewarp_timer_guard as timer

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "doc/timewarp-pinned-layout.json"
ANALYSIS_BASE = 0x80500000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(path.read_bytes())


def run(argv, folder):
    result = subprocess.run([str(x) for x in argv], cwd=folder, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def key(row):
    return row["name"], row["group"]


def inputs(path, object_build, region):
    objects, owners = budget.object_inputs(object_build, region)
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_type"] != "ET_REL" or elf["e_machine"] != "EM_PPC" or elf.little_endian:
            raise ValueError("Expected a big-endian PPC partial object")
        table = elf.get_section_by_name(".symtab")
        groups = {}
        for section in elf.iter_sections():
            if section["sh_type"] == "SHT_GROUP":
                signature = table.get_symbol(section["sh_info"]).name
                for index in struct.unpack(">" + str(section["sh_size"] // 4) + "I", section.data())[1:]:
                    groups[index] = signature
        definitions = defaultdict(list)
        module = None
        symbols = []
        for index, sym in enumerate(table.iter_symbols()):
            if sym["st_info"]["type"] == "STT_FILE":
                module = sym.name
            definition = {"name": sym.name, "section": sym["st_shndx"], "value": sym["st_value"],
                          "size": sym["st_size"], "type": sym["st_info"]["type"],
                          "bind": sym["st_info"]["bind"], "index": index}
            symbols.append(definition)
            if isinstance(sym["st_shndx"], int) and sym["st_size"]:
                definition["owners"] = ([module] if sym["st_info"]["bind"] == "STB_LOCAL"
                                         else sorted(owners.get(sym.name, ())))
                definitions[sym["st_shndx"]].append(definition)
        rows = []
        for index, section in enumerate(elf.iter_sections()):
            if not section["sh_flags"] & 2:
                continue
            defs = definitions[index]
            rows.append({"index": index, "name": section.name, "group": groups.get(index, ""),
                         "selector": section.name + f".pinned{index}", "bytes": section["sh_size"],
                         "type": section["sh_type"], "flags": section["sh_flags"],
                         "align": max(1, section["sh_addralign"]),
                         "entry_size": section["sh_entsize"],
                         "sha256": sha(section.data()) if section["sh_type"] != "SHT_NOBITS" else None,
                         "definitions": defs,
                         "owners": sorted({owner for d in defs for owner in d["owners"]})})
        if len({key(row) for row in rows}) != len(rows):
            raise ValueError("Allocated section keys are ambiguous")
        relocations = []
        for section in elf.iter_sections():
            if section["sh_type"] == "SHT_RELA":
                relocations.extend({"section": section["sh_info"], "offset": r["r_offset"],
                                    "symbol": r["r_info_sym"], "type": r["r_info_type"],
                                    "addend": r["r_addend"]} for r in section.iter_relocations())
    return rows, symbols, relocations, objects


def rename_inputs(source, destination, rows):
    data = bytearray(source.read_bytes())
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        names = bytearray(elf.get_section(elf["e_shstrndx"]).data())
        for row in rows:
            header = elf["e_shoff"] + row["index"] * elf["e_shentsize"]
            struct.pack_into(">I", data, header, len(names))
            names.extend(row["selector"].encode() + b"\0")
        header = elf["e_shoff"] + elf["e_shstrndx"] * elf["e_shentsize"]
        struct.pack_into(">II", data, header + 16, len(data), len(names))
        data.extend(names)
    destination.write_bytes(data)


def gnu_link(folder, output, obj, region, layout, toolchain, extras=()):
    command = [toolchain / "powerpc-eabi-ld.exe", "-o", output, "-T", layout,
               "-T", ROOT / f"maps/{region}.ld", obj, *extras,
               "--gc-sections", "--emit-relocs", "-Map", output.with_suffix(".map")]
    command += ["--undefined=" + p["sym"] for p in patches.patches
                if p["type"] in (patches.PatchType.B, patches.PatchType.BL)]
    output.with_suffix(".log").write_text(run(command, folder))


def parse_map(path, rows):
    source = path.read_text()
    for row in rows:
        match = re.search(r"^ " + re.escape(row["selector"]) + r"\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+[^\n]+", source, re.M)
        if not match:
            raise ValueError("Link map omitted input " + row["selector"])
        row["address"], row["linked_bytes"] = int(match[1], 16), int(match[2], 16)
        row["live"] = row["address"] >= 0x80000000


def flat_sections(path):
    return cold.elf_sections(path)


def range_bytes(sections, address, size):
    result = bytearray(size)
    coverage = bytearray(size)
    for section in sections.values():
        begin = max(address, section["address"])
        end = min(address + size, section["address"] + section["size"])
        if begin >= end:
            continue
        start, count = begin - address, end - begin
        if any(coverage[start:start + count]):
            raise ValueError("Overlapping linked sections")
        coverage[start:start + count] = b"\1" * count
        if section["data"] is not None:
            offset = begin - section["address"]
            result[start:start + count] = section["data"][offset:offset + count]
    if not all(coverage):
        raise ValueError("Unmapped protected range")
    return bytes(result)


def symbols_from(path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        return {s.name: dict(s.entry) for s in elf.get_section_by_name(".symtab").iter_symbols()
                if s["st_info"]["bind"] != "STB_LOCAL"}


def hook_writes(region, symbols):
    writes = []
    for patch in patches.patches:
        if patch["type"] == patches.PatchType.W32:
            writes.append([patch[region], patch["val"]])
        else:
            hook = BranchHook(patch[region], patch["sym"], patch.get("nop_count", 0),
                              patch["type"] == patches.PatchType.BL)
            hook.resolve(symbols)
            writes.extend([list(row) for row in hook.emit_writes()])
    return writes


def capture_layout(folder, target, region):
    build = ROOT / f"build/baseline-{target}"
    rows, _, _, _ = inputs(build / f"susamune_pre_{region}.o", build, region)
    obj = folder / f"{target}-{region}-input.o"
    rename_inputs(build / f"susamune_pre_{region}.o", obj, rows)
    output = folder / f"{target}-{region}.elf"
    gnu_link(folder, output, obj, region, build / f"foxtrot_{region}.ld", ROOT / "toolchain")
    before, after = flat_sections(build / f"susamune_{region}.o"), flat_sections(output)
    for name, section in before.items():
        if any(section[k] != after[name][k] for k in ("address", "size", "type", "data")):
            raise ValueError("Ownership capture differs from protected linked input")
    parse_map(output.with_suffix(".map"), rows)
    linked_path = ROOT / ("build/timewarp-linked-budget/emu-receipt.json" if target == "emu"
                          else "build/timewarp-linked-budget/receipt.json")
    linked = next((r for r in json.loads(linked_path.read_text())["regions"] if r["region"] == region), None)
    if linked is None:
        linked = budget.analyze(build, region)
    if linked["elf_sha256"] != file_sha(build / f"susamune_{region}.o"):
        raise ValueError("Ownership budget refers to another linked baseline")
    candidates = linked["relocation_candidates"]
    cluster = next(h for h in candidates["candidate_holes"] if h["span"] == "upper" and h["bytes"] > 60000)
    anchors = [x for x in candidates["timer_fixed_target_symbols"] if x["owners"] != ["qft_timer.cpp"]]
    for anchor in anchors:
        anchor["sha256"] = sha(range_bytes(before, anchor["address"], anchor["size"]))
    for row in rows:
        row["cold"] = row["live"] and cluster["begin"] <= row["address"] < cluster["end"]
        if row["cold"] and (len(row["definitions"]) != 1 or row["owners"] != ["menu.cpp"]):
            raise ValueError("Cold ownership is not one menu function")
        if row["cold"]:
            row["cold_symbol"] = row["definitions"][0]["name"]
        row["definition_count"] = len(row["definitions"])
        row["single_symbol"] = row["definitions"][0]["name"] if len(row["definitions"]) == 1 else None
        del row["definitions"]
        del row["selector"]
    return {"source_elf_sha256": file_sha(build / f"susamune_{region}.o"),
            "source_partial_sha256": file_sha(build / f"susamune_pre_{region}.o"),
            "map_sha256": file_sha(ROOT / f"maps/{region}.ld"), "cluster": cluster,
            "sections": rows, "anchors": anchors,
            "fixed_targets": candidates["timer_fixed_target_symbols"],
            "hook_writes": hook_writes(region, symbols_from(output))}


def capture(args):
    folder = args.work.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Ownership capture is create-only; use a new destination")
    result = {"version": 1, "scope": "Frozen ownership and addresses only; no executable payload bytes.",
              "timer_baseline_sha256": file_sha(timer.BASELINE),
              "patches_sha256": file_sha(ROOT / "scripts/patches.py"), "builds": {}}
    for target in ("console", "emu"):
        for region in ("jp", "us", "pal"):
            result["builds"][f"{target}-{region}"] = capture_layout(folder, target, region)
            print(f"Captured {target}-{region}")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, separators=(",", ":"))
        stream.write("\n")


def comdat_identity(path, name, signature):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        signature_indices = set()
        for group in elf.iter_sections():
            if group["sh_type"] == "SHT_GROUP" and table.get_symbol(group["sh_info"]).name == signature:
                words = struct.unpack(">" + str(group["sh_size"] // 4) + "I", group.data())
                signature_indices.update(words[1:])
        matches = [(i, s) for i, s in enumerate(elf.iter_sections()) if s.name == name and i in signature_indices]
        if len(matches) != 1:
            raise ValueError("Shared COMDAT section is ambiguous: " + name)
        index, section = matches[0]
        groups = []
        for group in elf.iter_sections():
            if group["sh_type"] != "SHT_GROUP":
                continue
            words = struct.unpack(">" + str(group["sh_size"] // 4) + "I", group.data())
            if index in words[1:]:
                groups.append((group, words))
        definitions = [s for s in table.iter_symbols() if s["st_shndx"] == index and s["st_size"]]
        if (len(groups) != 1 or groups[0][1][0] != 1
                or table.get_symbol(groups[0][0]["sh_info"]).name != signature
                or [i for i in groups[0][1][1:] if elf.get_section(i)["sh_flags"] & 2] != [index]
                or section["sh_type"] != "SHT_PROGBITS" or section["sh_flags"] != 0x206
                or len(definitions) != 1 or definitions[0].name != signature
                or definitions[0]["st_info"]["bind"] != "STB_WEAK"
                or definitions[0]["st_info"]["type"] != "STT_FUNC"
                or definitions[0]["st_value"] != 0 or definitions[0]["st_size"] != section["sh_size"]):
            raise ValueError("Shared COMDAT is not one complete weak function: " + name)
        relocations = []
        for relocation_section in elf.iter_sections():
            if relocation_section["sh_type"] not in ("SHT_REL", "SHT_RELA") or relocation_section["sh_info"] != index:
                continue
            if relocation_section["sh_type"] != "SHT_RELA":
                raise ValueError("Shared COMDAT requires explicit relocation addends: " + name)
            for relocation in relocation_section.iter_relocations():
                symbol = table.get_symbol(relocation["r_info_sym"])
                # Local/section targets can name different storage in each discarded copy.
                if (not symbol.name or symbol["st_info"]["bind"] not in ("STB_GLOBAL", "STB_WEAK")
                        or symbol["st_info"]["type"] not in ("STT_FUNC", "STT_OBJECT", "STT_NOTYPE")
                        or symbol["st_other"]["visibility"] != "STV_DEFAULT"):
                    raise ValueError("Shared COMDAT has a source-local relocation target: " + name)
                relocations.append({"offset": relocation["r_offset"], "type": relocation["r_info_type"],
                                    "addend": relocation["r_addend"], "symbol": symbol.name})
        return {"name": name, "signature": signature, "bytes": section["sh_size"],
                "align": section["sh_addralign"], "flags": section["sh_flags"],
                "sha256": sha(section.data()),
                "relocations": sorted(relocations, key=lambda r: (r["offset"], r["type"], r["symbol"], r["addend"]))}


def certify_shared_comdat(row, partial, object_build, region, objects):
    expected = comdat_identity(partial, row["name"], row["group"])
    sources = object_build / f"CMakeFiles/susamune_obj_{region}.dir/src"
    for owner in row["owners"]:
        if comdat_identity(sources / (owner + ".obj"), row["name"], row["group"]) != expected:
            raise ValueError("Shared COMDAT copies differ: " + row["name"] + " in " + owner)
    return {**expected, "source_object_sha256": {owner: objects[owner]["sha256"] for owner in row["owners"]}}


def plan_sections(rows, symbols, relocations, baseline, roots, shared_proof=None, protected=()):
    known = {key(row): row for row in baseline["sections"]}
    current = {key(row): row for row in rows}
    baseline["retired_missing"] = []
    for old in baseline["sections"]:
        if old["live"] and key(old) not in current:
            numeric = old["name"] in baseline.get("numeric_pools", {})
            immutable_menu = old.get("immutable_menu_verified", False)
            discarded_comdat = (old["group"] and old["flags"] == 0x206
                               and old.get("definition_count") == 1
                               and old.get("single_symbol") == old["group"])
            if (old.get("cold") or old.get("protected_string") or not (numeric or immutable_menu) and (old["flags"] & 0x10 or len(old["owners"]) != 1 and not discarded_comdat
                    or not old.get("source_owned") and old.get("definition_count") != 1)
                    or "qft_timer.cpp" in old["owners"]):
                raise ValueError("Required fixed input disappeared: " + old["name"])
            begin, end = old["address"], old["address"] + old["linked_bytes"]
            if any(begin < p["address"] + p["size"] and p["address"] < end for p in protected):
                raise ValueError("Missing input overlaps a protected anchor: " + old["name"])
            baseline["retired_missing"].append(old)
    live = {row["index"] for row in rows if known.get(key(row), {}).get("live")}
    by_index = {row["index"]: row for row in rows}
    for name in roots:
        matches = [s for s in symbols if s["name"] == name and isinstance(s["section"], int)]
        if len(matches) != 1:
            raise ValueError("New root is not one defined symbol: " + name)
        live.add(matches[0]["section"])
    edges = defaultdict(set)
    for relocation in relocations:
        target = symbols[relocation["symbol"]]["section"]
        if target in by_index:
            edges[relocation["section"]].add(target)
    pending = list(live)
    while pending:
        for target in edges[pending.pop()] - live:
            live.add(target)
            pending.append(target)
    cursor = ANALYSIS_BASE
    for row in rows:
        old = known.get(key(row))
        row["live"] = row["index"] in live and bool(row["bytes"])
        row["cold"] = bool(old and old.get("cold"))
        row["moved"] = False
        row["address"] = row["analysis_address"] = 0
        row["linked_bytes"] = row["bytes"]
        if not row["live"]:
            continue
        if old and old["live"]:
            if row["flags"] != old["flags"] or row["type"] != old["type"] or row["align"] != old["align"]:
                raise ValueError("Fixed input attributes changed: " + row["name"])
            if row["flags"] & 0x10 and row["sha256"] != old["sha256"]:
                numeric = baseline.get("numeric_pools", {}).get(row["name"])
                if (not numeric or row["flags"] != 0x12 or row["entry_size"] != numeric["entry_size"]
                        or any(old[k] != numeric[k] for k in ("address", "bytes", "sha256"))):
                    raise ValueError("Merged constant/string pool changed; split its ownership first: " + row["name"])
                row["numeric_pool_verified"] = True
            if row["cold"]:
                definitions = row["definitions"]
                if (row["owners"] != ["menu.cpp"] or len(definitions) != 1
                        or definitions[0]["name"] != old["cold_symbol"]
                        or definitions[0]["type"] != "STT_FUNC" or definitions[0]["value"]
                        or definitions[0]["size"] != row["bytes"]):
                    raise ValueError("Audited cold source selector changed: " + old["cold_symbol"])
                row["cold_source_changed"] = row["sha256"] != old["sha256"] or row["bytes"] != old["bytes"]
            if row["bytes"] <= old["bytes"]:
                row["address"] = row["analysis_address"] = old["address"]
                row["linked_bytes"] = old["linked_bytes"] if row["flags"] & 0x10 and not row.get("numeric_pool_verified") else row["bytes"]
                continue
        numeric = row.get("numeric_pool_verified")
        isolated_comdat = (row["group"] and row["flags"] == 0x206 and len(row["definitions"]) == 1 and
            row["definitions"][0]["name"] == row["group"] and row["definitions"][0]["type"] == "STT_FUNC" and
            not row["definitions"][0]["value"] and row["definitions"][0]["size"] == row["bytes"])
        if (row["flags"] & 0x10 and not row.get("source_owned_numeric") and not numeric or row["name"] in (".foxtrot.text", ".foxtrot.rodata", ".foxtrot.data", ".foxtrot.bss") and not row["cold"] and not isolated_comdat
                or (len(row["definitions"]) != 1 and not row.get("source_owned_verified") and not numeric) or not row["owners"] and not numeric):
            raise ValueError("Unsupported mixed/new input growth; split ownership first: " + row["name"])
        if len(row["owners"]) != 1 and not numeric and not row.get("string_atom_verified"):
            if shared_proof is None or not row["group"]:
                raise ValueError("Unsupported shared input growth; certify COMDAT ownership first: " + row["name"])
            row["shared_comdat_proof"] = shared_proof(row)
        if old and old["live"] and "qft_timer.cpp" in old["owners"]:
            raise ValueError("Protected timer input cannot grow")
        cursor = cold.align(cursor, max(4, row["align"]))
        row["analysis_address"] = row["address"] = cursor
        row["moved"] = True
        cursor += row["linked_bytes"]
    if cursor > ANALYSIS_BASE + 0x100000:
        raise ValueError("Analysis allocation exceeds its bounded address space")


def unused_ranges(rows, baseline, protected, region, symbols, relocations, target="console"):
    known = {key(row): row for row in baseline["sections"]}
    incoming = defaultdict(list)
    for relocation in relocations:
        symbol = symbols[relocation["symbol"]]
        incoming[symbol["section"]].append(symbol["value"] + relocation["addend"])
    recovered = []
    for row in rows:
        old = known.get(key(row))
        if (not old or not old["live"] or not row["live"] or row["moved"] or row.get("cold")
                or row.get("cold_extension") or row["flags"] & 0x10
                or row["linked_bytes"] >= old["linked_bytes"]):
            continue
        exclusive = (len(row["owners"]) == 1 and (
            row.get("source_owned_verified") or len(row["definitions"]) == 1))
        if not exclusive or row["owners"] != old["owners"]:
            continue
        if (row["address"] != old["address"] or row["linked_bytes"] != row["bytes"]
                or any(row[k] != old[k] for k in ("flags", "type", "align"))
                or any(d["value"] < 0 or d["value"] + d["size"] > row["bytes"]
                       for d in row["definitions"])):
            raise ValueError("Shrunken input ownership is inconsistent: " + row["name"])
        # Even a one-past-end reference keeps the old suffix unavailable.
        if any(offset < 0 or offset >= row["bytes"] for offset in incoming[row["index"]]):
            continue
        begin, end = old["address"] + row["bytes"], old["address"] + old["linked_bytes"]
        if any(begin < p["address"] + p["size"] and p["address"] < end for p in protected):
            continue
        recovered.append({"begin": begin, "end": end, "name": row["name"],
                          "group": row["group"], "owners": row["owners"], "shrunken_input": True,
                          "old_linked_bytes": old["linked_bytes"], "current_bytes": row["bytes"],
                          "current_sha256": row["sha256"],
                          "incoming_references_checked": len(incoming[row["index"]])})
    if target not in ("console", "emu"):
        raise ValueError("Unknown unused-space target")
    base = patches.base_addr[region]
    # Dolphin's DOL bootstrap and private input probes own the final upper page.
    upper_end = base + patches.mod_upper_offset + patches.mod_upper_size - (0x1000 if target == "emu" else 0)
    spans = ((base, base + patches.mod_mem1_working_cap_size),
             (base + patches.mod_upper_offset, upper_end))
    for begin, end in spans:
        old = [r for r in baseline["sections"] if r["live"] and begin <= r["address"] < end]
        if not old or any(r["address"] + r["linked_bytes"] > end for r in old):
            raise ValueError("Frozen input exceeds its reserved MEM1 span")
        tail = max(r["address"] + r["linked_bytes"] for r in old)
        if tail < end:
            recovered.append({"begin": tail, "end": end, "name": "reserved-span-tail",
                              "reserved_begin": begin, "reserved_end": end,
                              "frozen_input_end": tail})
    for item in recovered:
        begin, end = item["begin"], item["end"]
        if (not any(a <= begin < end <= b for a, b in spans)
                or any(begin < p["address"] + p["size"] and p["address"] < end for p in protected)
                or any(r["live"] and not r["moved"] and not r.get("cold") and not r.get("cold_extension")
                       and begin < r["address"] + r["linked_bytes"] and r["address"] < end for r in rows)):
            raise ValueError("Unused MEM1 range overlaps a live or protected input")
    return recovered


def allocate_sections(rows, baseline, plan, protected, region=None, symbols=(), relocations=(), target="console"):
    protected = list(protected) + [{"address": row["address"], "size": row["bytes"]}
        for row in baseline.get("string_atoms", {}).get("protected_atoms", {}).values()]
    known = {key(row): row for row in baseline["sections"]}
    retired = []
    retired.extend({**row, "immutable_strings": True} for row in baseline.get("retired_string_ranges", []))
    for old in baseline.get("retired_missing", []):
        retired.append({"begin": old["address"], "end": old["address"] + old["linked_bytes"], "name": old["name"], "missing": True})
    for row in rows:
        old = known.get(key(row))
        if not (row["moved"] or row.get("cold_extension")) or not old or not old["live"]:
            continue
        begin, end = old["address"], old["address"] + old["linked_bytes"]
        if any(begin < p["address"] + p["size"] and p["address"] < end for p in protected):
            raise ValueError("Retired input overlaps a protected anchor: " + row["name"])
        begin += 16 if row.get("hook_entry") else 0
        retired.append({"begin": begin, "end": end, "name": row["name"],
                        "cold_extension": bool(row.get("cold_extension"))})
    if region is not None:
        retired.extend(unused_ranges(rows, baseline, protected, region, symbols, relocations, target))
    if any(r["begin"] < p["address"] + p["size"] and p["address"] < r["end"] for r in retired for p in protected):
        raise ValueError("Retired input overlaps a protected anchor")
    ranges = sorted([(plan["hole_begin"], plan["hole_end"])] + [(r["begin"], r["end"]) for r in retired])
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError("Recovered source ranges overlap")
    free = []
    for begin, end in ranges:
        if free and free[-1][1] == begin:
            free[-1] = (free[-1][0], end)
        else:
            free.append((begin, end))
    available = list(free)
    moved = sorted((r for r in rows if r["moved"]), key=lambda r: (-r["linked_bytes"], r["name"], r["group"]))
    for row in moved:
        choices = []
        for index, (begin, end) in enumerate(free):
            address = cold.align(begin, max(1 if row.get("string_atom_verified") else 4, row["align"]))
            if address + row["linked_bytes"] <= end:
                choices.append((end - begin, address, index))
        if not choices:
            raise ValueError("Recovered MEM1 space exhausted or too fragmented for " + row["name"])
        _, address, index = min(choices)
        begin, end = free.pop(index)
        row["address"] = address
        if begin < address:
            free.append((begin, address))
        if address + row["linked_bytes"] < end:
            free.append((address + row["linked_bytes"], end))
        free.sort()
    return {"retired_ranges": retired, "retired_bytes": sum(r["end"] - r["begin"] for r in retired),
            "available_ranges": available, "remaining_ranges": free,
            "allocated_bytes": sum(r["linked_bytes"] for r in moved),
            "remaining_bytes": sum(end - begin for begin, end in free),
            "largest_remaining_range": max((end - begin for begin, end in free), default=0)}


def plan_hook_entries(rows, baseline):
    known = {key(r): r for r in baseline["sections"]}
    hooks = {p["sym"] for p in patches.patches if p["type"] in (patches.PatchType.B, patches.PatchType.BL)}
    entries = []
    for row in rows:
        old = known.get(key(row))
        if not row["moved"] or not old or old.get("single_symbol") not in hooks:
            continue
        if (old["bytes"] < 16 or old["flags"] != 6 or old["group"] or old.get("definition_count") != 1
                or len(row["definitions"]) != 1 or row["definitions"][0]["name"] != old["single_symbol"]
                or row["definitions"][0]["value"] != 0):
            raise ValueError("Grown hook does not own a standalone entry")
        entry = {"symbol": old["single_symbol"], "address": old["address"], "selector": f".pinned.hook.{len(entries)}"}
        row["hook_entry"] = entry
        entries.append(entry)
    baseline["hook_entries"] = entries


def hook_objects(folder, rows, field):
    result = []
    for row in rows:
        entry = row.get("hook_entry")
        if not entry:
            continue
        source = folder / (entry["symbol"] + "-gate-raw.o")
        output = folder / (entry["symbol"] + "-gate.o")
        cold.write_object(source, [], {row[field]: "pinned_hook_" + entry["symbol"]})
        rename_inputs(source, output, [{"index": 2, "selector": entry["selector"]}])
        result.append(output)
    return result


def hook_symbols(symbols, entries, sections=None):
    result = deepcopy(symbols)
    for entry in entries:
        target = symbols[entry["symbol"]]["st_value"]
        if sections is not None and range_bytes(sections, entry["address"], 16) != cold.veneer(target):
            raise ValueError("Fixed hook entry does not reach its current source body")
        result[entry["symbol"]]["st_value"] = entry["address"]
    return result


def write_layout(path, rows, field="address", remove_cold=False, incoming=None, limit=None, allocated_ranges=None):
    lines = ["SECTIONS {"]
    discarded = []
    for row in sorted(rows, key=lambda r: r[field]):
        if not row["live"] or remove_cold and row["cold"]:
            discarded.append(row["selector"])
            continue
        suffix = " (NOLOAD)" if row["type"] == "SHT_NOBITS" else ""
        lines.append(f' .pin{row["index"]} {row[field]:#x}{suffix} : {{ KEEP(*("{row["selector"]}")) }}')
        lines.append(f' ASSERT(SIZEOF(.pin{row["index"]}) == {row["linked_bytes"]}, "input size changed {row["index"]}")')
    if incoming is not None:
        lines.append(f' .incoming {incoming["island_begin"]:#x} : {{ KEEP(*(.text.gates)) }}')
        lines.append(f' ASSERT(SIZEOF(.incoming) == {len(incoming["gate_targets"]) * 16}, "gateway size changed")')
    for row in rows:
        entry = row.get("hook_entry")
        if entry:
            lines.append(f' {entry["selector"]} {entry["address"]:#x} : {{ KEEP(*("{entry["selector"]}")) }}')
            lines.append(f' ASSERT(SIZEOF({entry["selector"]}) == 16, "hook entry size changed")')
    if limit is not None:
        for row in rows:
            if row["moved"]:
                lines.append(f' ASSERT(ADDR(.pin{row["index"]}) + SIZEOF(.pin{row["index"]}) <= {limit:#x}, "recovered space exhausted")')
    if allocated_ranges is not None:
        for row in rows:
            if not row["moved"]:
                continue
            containing = [(a, b) for a, b in allocated_ranges if a <= row[field] < row[field] + row["linked_bytes"] <= b]
            if len(containing) != 1:
                raise ValueError("New allocation is not owned by one recovered range")
            begin, end = containing[0]
            lines.append(f' ASSERT(ADDR(.pin{row["index"]}) >= {begin:#x} && ADDR(.pin{row["index"]}) + SIZEOF(.pin{row["index"]}) <= {end:#x}, "allocation left recovered range")')
    lines.append(" /DISCARD/ : { *(" + " ".join('"' + name + '"' for name in discarded) + ") }")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n")


def verify_protected(output, build, region, target, baseline, frozen):
    expected = frozen["builds"][f"{target}-{region}"]
    timer.compare(expected["symbols"], timer.linked_symbols(output, expected["globals"]), f"pinned {target}-{region}")
    if timer.timer_globals(build, region) != expected["globals"]:
        raise ValueError("Timer source object globals changed")
    sections = flat_sections(output)
    symbols = symbols_from(output)
    for anchor in baseline["anchors"]:
        if symbols[anchor["name"]]["st_value"] != anchor["address"]:
            raise ValueError("Timer dependency address moved: " + anchor["name"])
        if sha(range_bytes(sections, anchor["address"], anchor["size"])) != anchor["sha256"]:
            raise ValueError("Timer dependency bytes changed: " + anchor["name"])
    if hook_writes(region, hook_symbols(symbols, baseline.get("hook_entries", []), sections)) != baseline["hook_writes"]:
        raise ValueError("Existing retail hook writes changed")
    return {"timer_symbols_identical": len(expected["symbols"]),
            "protected_string_atoms_identical": owned_inputs.string_atoms.verify_linked(sections, baseline["string_atoms"]) if "string_atoms" in baseline else 0,
            "dependency_anchors_identical": len(baseline["anchors"]),
            "retail_hook_writes_identical": len(baseline["hook_writes"])}


def relocate_metadata(source, destination, rows, functions, plan):
    data = bytearray(source.read_bytes())
    by_address = {f["old_address"]: f for f in functions}
    by_index = {row["index"]: row for row in rows}
    incoming = {r["site"]: r for r in plan["incoming"]}
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        strings = bytearray(elf.get_section(table["sh_link"]).data())
        symbols = bytearray(table.data())
        removed = {}
        for sym in table.iter_symbols():
            row = by_index.get(sym["st_shndx"])
            if not row or not row["cold"] or sym["st_info"]["type"] != "STT_FUNC":
                continue
            function = by_address.get(row["analysis_address"])
            if (not function or sym.name != function["name"] or sym["st_value"]
                    or sym["st_size"] != function["size"] or row["bytes"] != function["size"]
                    or sym["st_shndx"] in removed):
                raise ValueError("Cold partial-input ownership mismatch")
            removed[sym["st_shndx"]] = function
        if len(removed) != len(functions):
            raise ValueError("Missing cold partial-input section")
        for index, sym in enumerate(table.iter_symbols()):
            if sym["st_shndx"] in removed:
                function = removed[sym["st_shndx"]]
                struct.pack_into(">I", symbols, index * 16 + 4, function["cold_address"] + sym["st_value"])
                struct.pack_into(">H", symbols, index * 16 + 14, 0xFFF1)
                if sym["st_info"]["type"] == "STT_SECTION":
                    struct.pack_into(">I", symbols, index * 16, len(strings))
                    strings.extend(f"pinned_cold_section_{sym['st_shndx']}".encode() + b"\0")
                    symbols[index * 16 + 12] = 0
        gate_indices = {}
        for n, target in enumerate(plan["gate_targets"]):
            gate_indices[target] = len(symbols) // 16
            name_offset = len(strings)
            strings.extend(f"pinned_incoming_{n}".encode() + b"\0")
            symbols.extend(struct.pack(">IIIBBH", name_offset, plan["island_begin"] + 16 * n,
                                       16, 0x12, 0, 0xFFF1))
        seen = set()
        for section in elf.iter_sections():
            if section["sh_type"] != "SHT_RELA" or section["sh_info"] not in by_index:
                continue
            row = by_index[section["sh_info"]]
            if not row["live"] or row["cold"]:
                continue
            for index, relocation in enumerate(section.iter_relocations()):
                site = row["analysis_address"] + relocation["r_offset"]
                if site not in incoming:
                    continue
                expected = incoming[site]
                if relocation["r_info_type"] != expected["type"]:
                    raise ValueError("Incoming relocation type changed")
                seen.add(site)
                if expected["type"] == cold.REL24:
                    struct.pack_into(">Ii", data, section["sh_offset"] + index * 12 + 4,
                                     gate_indices[expected["target"]] << 8 | cold.REL24, 0)
        if seen != incoming.keys():
            raise ValueError("Incoming relocation accounting incomplete")
        for index, section in enumerate(elf.iter_sections()):
            payload = symbols if section.name == ".symtab" else strings if index == table["sh_link"] else None
            if payload is not None:
                data.extend(bytes((-len(data)) & 3))
                header = elf["e_shoff"] + index * elf["e_shentsize"]
                struct.pack_into(">II", data, header + 16, len(data), len(payload))
                data.extend(payload)
            if section["sh_flags"] & 2 and section["sh_type"] != "SHT_NOBITS":
                offset, size = section["sh_offset"], section["sh_size"]
                if data[offset:offset + size] != section.data():
                    raise ValueError("Compiled payload bytes changed before final link")
    destination.write_bytes(data)
    return {"cold_sections": len(removed), "incoming_relocations": len(seen),
            "source_payload_bytes_untouched": True}


def translate(address, rows):
    for row in rows:
        if row["moved"] and row["analysis_address"] <= address < row["analysis_address"] + row["linked_bytes"]:
            return row["address"] + address - row["analysis_address"]
    return address


def verify_relocations(before, after, rows, functions, plan):
    actual = {r["site"]: r for r in cold.final_relocations(after)}
    incoming = {r["site"]: r for r in plan["incoming"]}
    moved = {f["old_address"]: f["cold_address"] for f in functions}
    gates = {target: plan["island_begin"] + 16 * n for n, target in enumerate(plan["gate_targets"])}
    verified = 0
    for relocation in cold.final_relocations(before):
        if any(f["old_address"] <= relocation["site"] < f["old_address"] + f["size"] for f in functions):
            continue
        site = translate(relocation["site"], rows)
        if relocation["site"] in incoming:
            entry = incoming[relocation["site"]]
            target = gates[entry["target"]] if entry["type"] == cold.REL24 else moved[entry["function_old_address"]] + entry["target_offset"]
        else:
            target = translate(relocation["target"], rows)
        if site not in actual or actual[site]["target"] != target or actual[site]["type"] != relocation["type"]:
            raise ValueError(f"Final relocation differs from audited target at {site:#x}")
        verified += 1
    if len(actual) != verified:
        raise ValueError("Final ELF has unexpected relocation sites")
    return verified


def verify_cold_branches(before, payload, base, rows, functions, *, shared_tails=False, extension=None):
    moved = {f["old_address"]: f["cold_address"] for f in functions}
    verified = 0
    for relocation in cold.final_relocations(before):
        if relocation["type"] != cold.REL24:
            continue
        owners = [f for f in functions if
                  f["old_address"] <= relocation["site"] < f["old_address"] + f["size"]]
        if not owners:
            continue
        if len(owners) != 1:
            raise ValueError("Cold branch source ownership is ambiguous")
        owner = owners[0]
        site = owner["cold_address"] + relocation["site"] - owner["old_address"]
        owner_base, owner_payload = (extension if extension and
            extension[0] <= site < extension[0] + len(extension[1]) else (base, payload))
        offset = site - owner_base
        if not 0 <= offset <= len(owner_payload) - 4:
            raise ValueError("Cold branch escaped its payload")
        word = struct.unpack_from(">I", owner_payload, offset)[0]
        if word & 0xFC000002 != 0x48000000:
            raise ValueError("Cold branch instruction changed")
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
        destination = (site + displacement) & 0xFFFFFFFF
        original = relocation["target"]
        if original in moved:
            if destination != moved[original]:
                raise ValueError(f"Cold internal branch changed at {site:#x}")
        else:
            expected = translate(original, rows)
            gate = destination - base
            valid = (cold.shared_gate_target(payload, gate) == expected if shared_tails
                     else 0 <= gate <= len(payload) - 16 and payload[gate:gate + 16] == cold.veneer(expected))
            if not valid:
                raise ValueError(f"Cold external branch changed at {site:#x}: expected {expected:#x}")
        verified += 1
    return verified


def make_manifest(output, region, target, cold_path, cold_vma, receipt_path, hook_entries=(), menu_code=None):
    base = patches.base_addr[region]
    sections = list(flat_sections(output).values())
    ranges = [(base, base + patches.mod_mem1_working_cap_size),
              (base + patches.mod_upper_offset, base + patches.mod_upper_offset + patches.mod_upper_size)]
    if any(not any(a <= s["address"] < s["address"] + s["size"] <= b for a, b in ranges) for s in sections):
        raise ValueError("Linked section lies outside reserved MEM1 spans")
    segments = []
    for begin, end in ranges:
        entries = [s for s in sections if begin <= s["address"] < end]
        memory_end = cold.align(max(s["address"] + s["size"] for s in entries), 4)
        initialized_end = cold.align(max(s["address"] + s["size"] for s in entries if s["data"] is not None), 4)
        data = bytearray(initialized_end - begin)
        occupied = bytearray(memory_end - begin)
        for section in entries:
            offset, size = section["address"] - begin, section["size"]
            if any(occupied[offset:offset + size]):
                raise ValueError("Manifest input sections overlap")
            occupied[offset:offset + size] = b"\1" * size
            if section["data"] is not None:
                data[offset:offset + size] = section["data"]
        segments.append({"offset": begin - base, "memory_size": memory_end - begin, "code": data.hex()})
    data = bytearray(max(s["offset"] + len(s["code"]) // 2 for s in segments))
    for segment in segments:
        payload = bytes.fromhex(segment["code"])
        data[segment["offset"]:segment["offset"] + len(payload)] = payload
    return {"base_addr": base, "size": len(data),
            "memory_size": max(s["offset"] + s["memory_size"] for s in segments),
            "segments": segments, "region_reserve": patches.arena_reserve, "code": data.hex(),
            "writes": hook_writes(region, hook_symbols(symbols_from(output), hook_entries, flat_sections(output))), "game_id": patches.game_id[region],
            "region": patches.region[region], "disc_name": patches.disc_name[region], "target": target,
            "transport_environment": "dolphin" if target == "emu" else "console",
            "cold_image": {"path": str(cold_path.resolve()), "vma": cold_vma,
                           "size": cold_path.stat().st_size, "sha256": file_sha(cold_path)},
            "pinned_link_receipt": {"path": str(receipt_path.resolve()), "sha256": file_sha(receipt_path)},
            **({"menu_code": menu_code} if menu_code else {})}


def build(args):
    obj, object_build = args.obj.resolve(), args.objects.resolve()
    folder = args.work.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.elf.resolve() == folder / f"susamune_{args.vers}.o":
        raise ValueError("Final output must not overwrite the analysis ELF")
    frozen = json.loads(timer.BASELINE.read_text())
    ownership = json.loads(args.ownership.read_text())
    target_key = f"{args.target}-{args.vers}"
    if ownership["version"] != 1 or ownership["timer_baseline_sha256"] != file_sha(timer.BASELINE):
        raise ValueError("Ownership does not match the protected timer baseline")
    if ownership["patches_sha256"] != file_sha(ROOT / "scripts/patches.py"):
        raise ValueError("Hook/reservation source changed; review its fixed ownership contract")
    source_ownership = getattr(args, "source_owners", owned_inputs.LAYOUT)
    baseline = owned_inputs.expand_layout(source_ownership, args.ownership, ownership,
                                             args.target, args.vers, timer.BASELINE)
    if baseline["map_sha256"] != file_sha(ROOT / f"maps/{args.vers}.ld"):
        raise ValueError("Retail symbol map changed")
    timer.compare(frozen["sources"], timer.sources(), "source")
    timer.compare(frozen["builds"][target_key]["layout"], timer.layout(args.vers, args.target), "scratch")
    link_mod.check_shared_layout()
    link_mod.check_arena_reserve(ROOT / f"maps/{args.vers}.ld", patches.base_addr[args.vers])
    current_objects = sorted((object_build / f"CMakeFiles/susamune_obj_{args.vers}.dir/src").glob("*.cpp.obj"))
    rebound = folder / "source-provenance.o"
    run([args.kuribo_home / "clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi",
         "-nodefaultlibs", "-nostdlib", "-fuse-ld=lld", "-r", *current_objects, "-o", rebound], folder)
    if file_sha(rebound) != file_sha(obj):
        raise ValueError("Partial object does not match the current per-source object inventory")
    original_partial_sha256 = file_sha(obj)
    obj, source_proof = owned_inputs.prepare(object_build, folder / "source-owned", args.vers,
        args.kuribo_home, baseline["merge_sources"], {r["name"] for r in baseline["sections"]},
        baseline["immutable_menu_constants"], baseline["string_atoms"])
    object_build = folder / "source-owned"
    rows, symbols, relocs, objects = inputs(obj, object_build, args.vers)
    owned_inputs.verify_parts(rows, source_proof, baseline)
    menu_table_proofs = menu_tables.validate_all(rows, obj, object_build, args.vers,
        list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"], baseline)
    for row in rows:
        if row["name"] in menu_table_proofs:
            row["source_owned_verified"] = True
            owner = menu_table_proofs[row["name"]]["owner"]
            row["source_owner"], row["owners"] = owner, [owner]
    plan_sections(rows, symbols, relocs, baseline, args.root,
                  lambda row: certify_shared_comdat(row, obj, object_build, args.vers, objects),
                  list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"])
    owned_inputs.numeric_protection.verify_current(rows, symbols, relocs,
        list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"])
    plan_hook_entries(rows, baseline)
    unique = folder / "current-input.o"
    rename_inputs(obj, unique, rows)
    analysis_layout = folder / "analysis.ld"
    write_layout(analysis_layout, rows, "analysis_address")
    # The source ownership auditor reads this conventional name, in our own directory.
    analysis = folder / f"susamune_{args.vers}.o"
    source_dir = folder / f"CMakeFiles/susamune_obj_{args.vers}.dir/src"
    source_dir.mkdir(parents=True, exist_ok=True)
    for source in (object_build / f"CMakeFiles/susamune_obj_{args.vers}.dir/src").glob("*.cpp.obj"):
        shutil.copyfile(source, source_dir / source.name)
    gnu_link(folder, analysis, unique, args.vers, analysis_layout, args.kuribo_home, hook_objects(folder, rows, "analysis_address"))
    verify_protected(analysis, folder, args.vers, args.target, baseline, frozen)
    source_sections = flat_sections(analysis)
    final_relocs = cold.final_relocations(analysis)
    region_budget = {"relocation_candidates": {"candidate_holes": [baseline["cluster"]],
                                               "timer_fixed_target_symbols": baseline["fixed_targets"]}}
    functions, rejected, cluster, menu_sha = cold.extract_functions(
        folder, args.vers, final_relocs, source_sections, region_budget, True, frozen, True, args.target,
        {r["cold_symbol"]: r for r in baseline["sections"] if r.get("cold")})
    if rejected or len(functions) != sum(r["cold"] for r in rows):
        raise ValueError("Current cold selectors do not exactly tile the audited cluster")
    for row in rows:
        if row["cold"]:
            row["moved"] = False  # Its frozen range is already in the original menu hole.
    extensions = ([] if getattr(args, "no_cold_extensions", False) else cold_extensions.extract(
        folder, args.vers, source_sections, final_relocs,
        list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"], args.target))
    cold_extensions.mark_inputs(rows, extensions, baseline,
        list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"], args.target)
    extensions = [function for function in extensions if not function.get("retained_mem1")]
    functions.extend(extensions)
    shared_incoming = []
    for relocation in final_relocs:
        if relocation["type"] != cold.REL24 or not any(f["old_address"] == relocation["target"] for f in extensions):
            continue
        sources = [r for r in rows if r["live"] and r["analysis_address"] <= relocation["site"] < r["analysis_address"] + r["linked_bytes"]]
        if len(sources) == 1 and sources[0]["group"] and len(sources[0]["owners"]) > 1:
            row = sources[0]
            if "shared_comdat_proof" not in row:
                row["shared_comdat_proof"] = certify_shared_comdat(row, obj, object_build, args.vers, objects)
            shared_incoming.append(relocation["site"])
    plan = cold.audit_incoming(folder, args.vers, functions, cluster, final_relocs,
                               source_sections, region_budget, frozen, args.target, shared_incoming)
    capacity = allocate_sections(rows, baseline, plan,
                                 list(frozen["builds"][target_key]["symbols"].values()) + baseline["anchors"],
                                 args.vers, symbols, relocs, args.target)
    external_targets = {}
    cold_targets = {f["old_address"] for f in functions}
    for function in functions:
        payload = bytearray(function["data"])
        for relocation in function["relocations"]:
            # Classification uses analysis identity; a reused MEM1 address may
            # equal another function's former cold entry.
            if relocation["type"] == cold.REL24:
                if relocation["target"] not in cold_targets:
                    external_targets[relocation["target"]] = translate(relocation["target"], rows)
                continue
            target = translate(relocation["target"], rows)
            if target != relocation["target"]:
                relocation["target"] = target
                cold.apply_relocation(payload, relocation["site"] - function["old_address"], relocation, relocation["site"])
        function["data"] = bytes(payload)
    extension_names = {f["name"] for f in functions if f["name"] in cold_extensions.MENU_CODE_FUNCTIONS}
    extension_base = link_mod.mem2_hex_define("SUSAMUNE_MENU_CODE_" +
        ("DOLPHIN" if args.target == "emu" else "CONSOLE") + "_PPC_BASE")
    extension_capacity = link_mod.mem2_hex_define("SUSAMUNE_MENU_CODE_SIZE")
    cold_vma = (0x71E3F000 if args.target == "emu" else 0x91E3F000) + 0xC0
    cold_receipt = cold.link_cold(folder, functions, cold_vma, args.vers, external_targets,
                                  shared_tails=True, extension_base=extension_base,
                                  extension_names=extension_names, extension_capacity=extension_capacity)
    cold_path = folder / f"cold-{args.vers}.bin"
    extension_path = folder / f"menu-code-{args.vers}.bin"
    menu_code = {"path": str(extension_path.resolve()), "vma": extension_base,
                 "size": extension_path.stat().st_size, "sha256": file_sha(extension_path)}
    cold_branch_count = verify_cold_branches(analysis, cold_path.read_bytes(), cold_vma, rows, functions,
                                            shared_tails=True, extension=(extension_base, extension_path.read_bytes()))
    modified = folder / "relocated-input.o"
    rewrite = relocate_metadata(unique, modified, rows, functions, plan)
    by_old = {f["old_address"]: f for f in functions}
    gates = folder / "incoming-gates.o"
    cold.write_object(gates, [], {by_old[old]["cold_address"]: "pinned_gateway_" + str(n)
                                for n, old in enumerate(plan["gate_targets"])})
    final_layout = folder / "final.ld"
    write_layout(final_layout, rows, remove_cold=True, incoming=plan, allocated_ranges=capacity["available_ranges"])
    output = args.elf.resolve()
    gnu_link(folder, output, modified, args.vers, final_layout, args.kuribo_home, [gates, *hook_objects(folder, rows, "address")])
    protection = verify_protected(output, folder, args.vers, args.target, baseline, frozen)
    relocated_sites = verify_relocations(analysis, output, rows, functions, plan)
    # Parse final relocations before publishing the receipt or manifest.
    receipt = {"version": 1, "complete": True, "passed": True, "target": args.target, "region": args.vers,
               "source_partial_sha256": original_partial_sha256, "source_object_sha256": source_proof["original_object_sha256"],
               "partial_rebuilt_from_current_objects": True,
               "source_ownership_sha256": file_sha(source_ownership), "source_owned_partial_sha256": file_sha(obj),
               "numeric_merge_ownership_sha256": file_sha(owned_inputs.MERGE_LAYOUT),
               "numeric_pool_ownership_sha256": file_sha(owned_inputs.NUMERIC_LAYOUT),
               "immutable_menu_ownership_sha256": file_sha(owned_inputs.menu_constants.LAYOUT),
               "string_atom_ownership_sha256": file_sha(owned_inputs.string_atoms.LAYOUT),
               "source_string_atoms_verified": len(source_proof["string_atoms"]),
               "menu_jump_table_proofs": menu_table_proofs,
               "retired_immutable_menu_constants": [baseline["immutable_menu_constants"][r["name"]]
                   for r in baseline["retired_missing"] if r.get("immutable_menu_verified")],
               "source_owned_payloads_unchanged": source_proof["allocated_payloads_unchanged"],
               "source_owned_inputs_verified": len(source_proof["parts"]),
               "new_header_constants": [part for part in source_proof["parts"] if part.get("new_header_constant")],
               "source_menu_object_sha256": menu_sha, "ownership_sha256": file_sha(args.ownership),
               "timer_baseline_sha256": file_sha(timer.BASELINE), "protection": protection,
               "cold": cold_receipt, "cold_branch_targets_verified": cold_branch_count,
               "metadata_rewrite": rewrite,
               "recertified_menu_inputs": [{"name": r["name"], "sha256": r["sha256"], "bytes": r["bytes"]}
                                           for r in rows if r.get("cold_source_changed")],
               "cold_extensions": [{k: f[k] for k in ("name", "old_address", "size", "cold_address")} for f in extensions],
               "renamed_cold_inputs": [r["cold_renamed"] for r in rows if r.get("cold_renamed")],
               "new_cold_inputs": [{"name": r["name"], "group": r["group"], "owners": r["owners"],
                                    "symbol": r["definitions"][0]["name"], "bytes": r["bytes"], "sha256": r["sha256"],
                                    "analysis_address": r["analysis_address"], "retired_bytes": 0}
                                   for r in rows if r.get("cold_new")],
               "retained_mem1_cpu_inputs": [{"name": r["name"], "owners": r["owners"],
                                    "symbol": r["definitions"][0]["name"], "bytes": r["bytes"], "sha256": r["sha256"],
                                    "address": r["address"], "analysis_address": r["analysis_address"], "retired_bytes": 0}
                                   for r in rows if r.get("retained_mem1_cpu")],
               "fixed_hook_entries": baseline["hook_entries"], "fixed_hook_entry_bytes": 16 * len(baseline["hook_entries"]),
               "cold_image": {"vma": cold_vma, "size": cold_path.stat().st_size, "sha256": file_sha(cold_path)},
               "menu_code": menu_code,
               "retained_relocation_sites_verified": relocated_sites,
               "gateway_count": len(plan["gate_targets"]), "recovered_begin": plan["hole_begin"],
               "recovered_end": plan["hole_end"], "new_source_bytes": capacity["allocated_bytes"],
               "recovered_bytes_remaining": capacity["remaining_bytes"], "capacity": capacity,
               "allocations": [{k: r[k] for k in ("name", "group", "owners", "address", "analysis_address", "linked_bytes")}
                               for r in rows if r["moved"]],
               "shared_comdat_proofs": [r["shared_comdat_proof"] for r in rows if "shared_comdat_proof" in r],
               "changed_unprotected_numeric_pools": [r["name"] for r in rows if r.get("numeric_pool_verified")],
               "elf_path": str(output), "elf_sha256": file_sha(output),
               "scope": "Fresh source link and relocation proof; target runtime/cold transport capability is a separate gate."}
    receipt_path = folder / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    manifest = make_manifest(output, args.vers, args.target, cold_path, cold_vma, receipt_path, baseline["hook_entries"], menu_code)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{target_key}: {protection['timer_symbols_identical']} timer symbols fixed; "
          f"{len(functions)} cold functions; {receipt['recovered_bytes_remaining']} MEM1 bytes available")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("capture-ownership")
    save.add_argument("--output", type=Path, default=LAYOUT)
    save.add_argument("--work", type=Path, default=ROOT / "build/timewarp-pinned-link/ownership")
    link = commands.add_parser("link")
    link.add_argument("--obj", type=Path, required=True)
    link.add_argument("--objects", type=Path, required=True, help="Build root containing current per-source objects")
    link.add_argument("--ownership", type=Path, default=LAYOUT)
    link.add_argument("--source-owners", type=Path, default=owned_inputs.LAYOUT)
    link.add_argument("--kuribo-home", type=Path, default=ROOT / "toolchain")
    link.add_argument("--vers", choices=("jp", "us", "pal"), required=True)
    link.add_argument("--target", choices=("console", "emu"), required=True)
    link.add_argument("--work", type=Path, required=True)
    link.add_argument("--elf", type=Path, required=True)
    link.add_argument("--out", type=Path, required=True)
    link.add_argument("--root", action="append", default=[], help="Additional new-source test root")
    link.add_argument("--no-cold-extensions", action="store_true", help="Private before/after capacity comparison")
    args = parser.parse_args()
    if args.command == "capture-ownership":
        capture(args)
    else:
        build(args)


if __name__ == "__main__":
    main()
