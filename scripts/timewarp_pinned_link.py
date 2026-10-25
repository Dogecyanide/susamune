"""Private GNU-linker feasibility; immutable baseline and timer source inputs."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess

from elftools.elf.elffile import ELFFile

import patches
import timewarp_cold_cluster as cold
import timewarp_linked_budget as budget
import timewarp_timer_guard as timer

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "build/baseline-console"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, folder):
    completed = subprocess.run([str(x) for x in argv], cwd=folder,
                               capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return completed.stdout + completed.stderr


def inventory(folder):
    expected = json.loads(timer.BASELINE.read_text())["builds"]["console-pal"]
    timer.compare(expected["symbols"], timer.linked_symbols(BASE / "susamune_pal.o", expected["globals"]), "input")
    objects, owners = budget.object_inputs(BASE, "pal")
    owners["__modules__"] = set(objects)
    image = budget.LinkedImage(BASE / "susamune_pal.o", owners)
    linked = json.loads((ROOT / "build/timewarp-linked-budget/receipt.json").read_text())
    region = next(x for x in linked["regions"] if x["region"] == "pal")
    anchors = [x for x in region["relocation_candidates"]["timer_fixed_target_symbols"]
               if x["owners"] != ["qft_timer.cpp"]]
    if len(anchors) != 9:
        raise ValueError("Timer dependency inventory changed")
    wanted = {"qft_timer.cpp": set()}
    for anchor in anchors:
        for owner in anchor["owners"]:
            wanted.setdefault(owner, set()).add(anchor["name"])
    rows = []
    for module, names in wanted.items():
        obj = objects[module]
        with (BASE / f"CMakeFiles/susamune_obj_pal.dir/src/{module}.obj").open("rb") as stream:
            elf = ELFFile(stream)
            for index, section in enumerate(elf.iter_sections()):
                if not section["sh_flags"] & 2 or not section["sh_size"]:
                    continue
                definitions = obj["definitions"].get(index, [])
                if module != "qft_timer.cpp" and not any(s["name"] in names for s in definitions):
                    continue
                bases = set()
                matched = []
                for definition in definitions:
                    for final in image.resolve(definition):
                        if final["size"] == definition["size"]:
                            bases.add(final["address"] - definition["address"])
                            matched.append(definition["name"])
                rows.append({"module": module, "index": index, "section": section.name,
                    "bytes": section["sh_size"], "flags": section["sh_flags"],
                    "alignment": section["sh_addralign"], "type": section["sh_type"],
                    "candidate_addresses": sorted(bases), "defined_symbols": len(definitions),
                    "matched_symbols": matched, "merge_entries": section["sh_entsize"],
                    "sha256": hashlib.sha256(section.data()).hexdigest()})
    output = folder / "baseline-with-relocations.elf"
    command = [ROOT / "toolchain/powerpc-eabi-ld.exe", "-o", output,
               "-T", BASE / "foxtrot_pal.ld", "-T", ROOT / "maps/pal.ld",
               BASE / "susamune_pre_pal.o", "--gc-sections", "--emit-relocs",
               "-Map", folder / "baseline.map"]
    command += ["--undefined=" + p["sym"] for p in patches.patches
                if p["type"] in (patches.PatchType.B, patches.PatchType.BL)]
    (folder / "baseline-link.log").write_text(run(command, folder))
    original = cold.elf_sections(BASE / "susamune_pal.o")
    rebuilt = cold.elf_sections(output)
    for name, section in original.items():
        if any(section[k] != rebuilt[name][k] for k in ("address", "size", "type", "data")):
            raise ValueError("Relocation/map emission changed baseline bytes")
    fixed = json.loads((ROOT / "build/timewarp-cold-cluster/consolidated/receipt.json").read_text())
    cluster = next(r for r in fixed["regions"] if r["region"] == "pal")
    return {"baseline_elf_sha256": sha(BASE / "susamune_pal.o"),
            "timer_baseline_sha256": sha(timer.BASELINE), "timer_symbols": len(expected["symbols"]),
            "dependency_anchors": anchors, "protected_input_sections": rows,
            "cold_hole": cluster["variants"]["console"]["retained"]["holes"],
            "baseline_relink_allocated_bytes_identical": True}


def compile_sources(folder):
    entries = json.loads((BASE / "compile_commands.json").read_text())
    entries = [e for e in entries if "susamune_obj_pal.dir" in e["output"]]
    output_dir = folder / "fresh/CMakeFiles/susamune_obj_pal.dir/src"
    output_dir.mkdir(parents=True, exist_ok=True)

    def compile_one(entry):
        argv = [x.strip('"') for x in shlex.split(entry["command"], posix=False)]
        source = Path(entry["file"])
        output = output_dir / (source.name + ".obj")
        argv[argv.index("-o") + 1] = str(output)
        log = run(argv, folder)
        if log:
            output.with_suffix(".log").write_text(log)
        return {"source": str(source), "source_sha256": sha(source), "object": str(output),
                "sha256": sha(output), "argv": argv}

    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(compile_one, entries))
    qft = next(x for x in rows if Path(x["source"]).name == "qft_timer.cpp")
    baseline_object = BASE / "CMakeFiles/susamune_obj_pal.dir/src/qft_timer.cpp.obj"
    if qft["sha256"] != sha(baseline_object):
        raise ValueError("Fresh untouched timer compilation differs from baseline object")
    (folder / "fresh/compile-receipt.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def partial_link(folder):
    ninja = (BASE / "build.ninja").read_text()
    block = re.search(r"^build susamune_pre_pal.o:.*\n  LINK_FLAGS = (.*)$", ninja, re.M)
    objects = sorted((folder / "fresh/CMakeFiles/susamune_obj_pal.dir/src").glob("*.obj"))
    if len(objects) != 64:
        raise ValueError("Fresh source object inventory changed")
    output = folder / "fresh/susamune_pre_pal.o"
    run([ROOT / "toolchain/clang++.exe", *shlex.split(block[1]), *objects, "-o", output], folder)
    if sha(output) != sha(BASE / "susamune_pre_pal.o"):
        raise ValueError("Fresh partial link is not baseline-identical")
    return output


def unique_sections(source, destination):
    """Preserve indices, groups and relocations; give allocated inputs stable selectors."""
    data = bytearray(source.read_bytes())
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        offset, stride = elf["e_shoff"], elf["e_shentsize"]
        names = bytearray(elf.get_section(elf["e_shstrndx"]).data())
        rows = []
        for index, section in enumerate(elf.iter_sections()):
            if section["sh_flags"] & 2:
                name = section.name + f".twp{index}"
                struct.pack_into(">I", data, offset + stride * index, len(names))
                names.extend(name.encode() + b"\0")
                rows.append({"index": index, "name": name, "original_name": section.name,
                             "bytes": section["sh_size"], "type": section["sh_type"],
                             "flags": section["sh_flags"]})
        table = offset + stride * elf["e_shstrndx"]
        struct.pack_into(">II", data, table + 16, len(data), len(names))
        data.extend(names)
    destination.write_bytes(data)
    return rows


def gnu_link(folder, stem, inputs, layout):
    command = [ROOT / "toolchain/powerpc-eabi-ld.exe", "-o", folder / (stem + ".elf"),
               "-T", layout, "-T", ROOT / "maps/pal.ld", *inputs,
               "--gc-sections", "--emit-relocs", "-Map", folder / (stem + ".map")]
    command += ["--undefined=" + p["sym"] for p in patches.patches
                if p["type"] in (patches.PatchType.B, patches.PatchType.BL)]
    (folder / (stem + ".log")).write_text(run(command, folder))
    return folder / (stem + ".elf")


def unique_layout(folder):
    source = partial_link(folder)
    renamed = folder / "unique-input.o"
    rows = unique_sections(source, renamed)
    output = gnu_link(folder, "unique-baseline", [renamed], BASE / "foxtrot_pal.ld")
    a, b = cold.elf_sections(BASE / "susamune_pal.o"), cold.elf_sections(output)
    if a != b:
        # File offsets are irrelevant; every allocated address and byte must match.
        for name in a:
            if any(a[name][k] != b[name][k] for k in ("address", "size", "type", "data")):
                raise ValueError("Unique input naming changed allocated section " + name)
    map_text = (folder / "unique-baseline.map").read_text()
    for row in rows:
        match = re.search(r"^ " + re.escape(row["name"]) + r"\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+[^\n]+unique-input.o", map_text, re.M)
        if not match:
            raise ValueError("Unique section missing from map: " + row["name"])
        row["address"], row["linked_bytes"] = int(match[1], 16), int(match[2], 16)
        row["live"] = row["address"] >= 0x80000000
    (folder / "section-ownership.json").write_text(json.dumps(rows, indent=2) + "\n")
    shutil.copyfile(output, folder / "fresh/susamune_pal.o")
    return rows


def pinned_script(path, rows, removed=(), extra=""):
    lines = ["SECTIONS {"]
    for row in sorted(rows, key=lambda x: x["address"]):
        if not row["live"] or row["index"] in removed or not row["linked_bytes"]:
            continue
        suffix = " (NOLOAD)" if row["type"] == "SHT_NOBITS" else ""
        lines.append(f" .pin{row['index']} {row['address']:#x}{suffix} : {{ KEEP(*(\"{row['name']}\")) }}")
        lines.append(f" ASSERT(SIZEOF(.pin{row['index']}) == {row['linked_bytes']}, \"pinned section {row['index']} size changed\")")
    lines.append(extra)
    discarded = [row["name"] for row in rows if not row["live"] or row["index"] in removed]
    lines.append(" /DISCARD/ : { *(" + " ".join('"' + name + '"' for name in discarded) + ") }")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n")


def memory_image(path):
    result = {}
    for section in cold.elf_sections(path).values():
        data = section["data"] if section["data"] is not None else bytes(section["size"])
        for n, byte in enumerate(data):
            address = section["address"] + n
            if address in result:
                raise ValueError("Overlapping output sections")
            result[address] = byte
    return result


def pin_baseline(folder, rows):
    layout = folder / "pinned-baseline.ld"
    pinned_script(layout, rows)
    output = gnu_link(folder, "pinned-baseline", [folder / "unique-input.o"], layout)
    original, linked = memory_image(BASE / "susamune_pal.o"), memory_image(output)
    if any(original.get(a, 0) != linked.get(a, 0) for a in original.keys() | linked.keys()):
        raise ValueError("Pinned final allocated bytes differ")
    expected = json.loads(timer.BASELINE.read_text())["builds"]["console-pal"]
    timer.compare(expected["symbols"], timer.linked_symbols(output, expected["globals"]), "pinned baseline")
    return {"elf": str(output), "all_allocated_bytes_identical": True,
            "live_input_sections": sum(row["live"] for row in rows),
            "protected_timer_symbols": len(expected["symbols"])}


def relocate_inputs(source, destination, rows, functions, plan):
    """Change symbol/relocation metadata only; compiled PPC input bytes are untouched."""
    data = bytearray(source.read_bytes())
    by_name = {f["name"]: f for f in functions}
    by_index = {row["index"]: row for row in rows}
    incoming = {r["site"]: r for r in plan["incoming"]}
    gate_names = {target: "twp_incoming_" + str(n) for n, target in enumerate(plan["gate_targets"])}
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        strings = bytearray(elf.get_section(table["sh_link"]).data())
        symbols = bytearray(table.data())
        removed = {}
        for sym in table.iter_symbols():
            if sym.name in by_name and isinstance(sym["st_shndx"], int):
                function = by_name[sym.name]
                row = by_index[sym["st_shndx"]]
                if row["address"] != function["old_address"] or row["bytes"] != function["size"]:
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
                    strings.extend(f"twp_cold_section_{sym['st_shndx']}".encode() + b"\0")
                    symbols[index * 16 + 12] = 0
        gate_indices = {}
        for n, target in enumerate(plan["gate_targets"]):
            gate_indices[target] = len(symbols) // 16
            name_offset = len(strings)
            strings.extend(gate_names[target].encode() + b"\0")
            symbols.extend(struct.pack(">IIIBBH", name_offset, plan["island_begin"] + 16 * n,
                                       16, 0x12, 0, 0xFFF1))
        rewritten = []
        seen = set()
        for section in elf.iter_sections():
            if section["sh_type"] != "SHT_RELA" or section["sh_info"] not in by_index:
                continue
            row = by_index[section["sh_info"]]
            if not row["live"] or row["index"] in removed:
                continue
            for index, relocation in enumerate(section.iter_relocations()):
                site = row["address"] + relocation["r_offset"]
                if site not in incoming:
                    continue
                expected = incoming[site]
                if relocation["r_info_type"] != expected["type"]:
                    raise ValueError("Incoming relocation type changed")
                seen.add(site)
                if expected["type"] == cold.REL24:
                    entry = section["sh_offset"] + index * 12
                    struct.pack_into(">Ii", data, entry + 4,
                                     gate_indices[expected["target"]] << 8 | cold.REL24, 0)
                    rewritten.append(site)
        if seen != incoming.keys():
            raise ValueError("Incoming section-address mapping incomplete")
        for index, section in enumerate(elf.iter_sections()):
            payload = symbols if section.name == ".symtab" else strings if index == table["sh_link"] else None
            if payload is not None:
                data.extend(bytes((-len(data)) & 3))
                header = elf["e_shoff"] + index * elf["e_shentsize"]
                struct.pack_into(">II", data, header + 16, len(data), len(payload))
                data.extend(payload)
        for index, section in enumerate(elf.iter_sections()):
            if section["sh_flags"] & 2 and section["sh_type"] != "SHT_NOBITS":
                offset, size = section["sh_offset"], section["sh_size"]
                if data[offset:offset + size] != section.data():
                    raise ValueError("Source machine/data bytes changed before final link")
    destination.write_bytes(data)
    return set(removed), {"removed_input_sections": len(removed),
                          "incoming_branch_relocations": len(rewritten),
                          "incoming_relocations_accounted": len(seen),
                          "all_source_allocated_bytes_untouched": True}


def cold_relink(folder, rows):
    linked = json.loads((ROOT / "build/timewarp-linked-budget/receipt.json").read_text())
    region = next(x for x in linked["regions"] if x["region"] == "pal")
    timer_receipt = json.loads(timer.BASELINE.read_text())
    original_sections = cold.elf_sections(BASE / "susamune_pal.o")
    relocs = cold.final_relocations(folder / "unique-baseline.elf")
    functions, rejected, cluster, menu_sha = cold.extract_functions(
        folder / "fresh", "pal", relocs, original_sections, region, True, timer_receipt, True)
    if rejected:
        raise ValueError("Consolidated cluster has rejected functions")
    plan = cold.audit_incoming(folder / "fresh", "pal", functions, cluster, relocs,
                               original_sections, region, timer_receipt)
    cold_folder = folder / "cold"
    cold_folder.mkdir(exist_ok=True)
    cold_receipt = cold.link_cold(cold_folder, functions, 0x91E3F0A0, "pal")
    relocated = folder / "relocated-input.o"
    removed, rewrite = relocate_inputs(folder / "unique-input.o", relocated, rows, functions, plan)
    by_old = {f["old_address"]: f for f in functions}
    gate_obj = folder / "incoming-gates.o"
    cold.write_object(gate_obj, [], {by_old[target]["cold_address"]: "twp_gateway_" + str(n)
                                    for n, target in enumerate(plan["gate_targets"])})
    extra = f" .incoming {plan['island_begin']:#x} : {{ KEEP(*(.text.gates)) }}"
    layout = folder / "pinned-cold.ld"
    pinned_script(layout, rows, removed, extra)
    output = gnu_link(folder, "pinned-cold", [relocated, gate_obj], layout)
    expected = timer_receipt["builds"]["console-pal"]
    timer.compare(expected["symbols"], timer.linked_symbols(output, expected["globals"]), "pinned cold")
    # Independently compare with the already audited relocation result.
    retained = cold.retained_consolidated(folder / "fresh", "pal", cold_folder, functions,
                                         original_sections, "reference", timer_receipt, cluster, plan)
    a, b = memory_image(cold_folder / "retained-reference.elf"), memory_image(output)
    if any(a.get(address, 0) != b.get(address, 0) for address in a.keys() | b.keys()):
        raise ValueError("GNU-linked relocation differs from audited retained image")
    return {"cold": cold_receipt, "rewrite": rewrite, "removed": sorted(removed),
            "plan": plan, "functions": [{k: v for k, v in f.items() if k != "data"} for f in functions],
            "menu_fresh_object_sha256": menu_sha, "retained": retained,
            "elf": str(output), "gnu_link_matches_audited_consolidated_bytes": True}


def compile_fixture(folder, name, source):
    path = folder / (name + ".cpp")
    path.write_text(source)
    entry = next(e for e in json.loads((BASE / "compile_commands.json").read_text())
                 if "susamune_obj_pal.dir" in e["output"] and e["file"].endswith("checksum.cpp"))
    argv = [x.strip('"') for x in shlex.split(entry["command"], posix=False)]
    argv[argv.index("-c") + 1] = str(path)
    output = folder / (name + ".o")
    argv[argv.index("-o") + 1] = str(output)
    (folder / (name + ".log")).write_text(run(argv, folder))
    return output


def verify_fixed(output, receipt):
    expected = json.loads(timer.BASELINE.read_text())["builds"]["console-pal"]
    timer.compare(expected["symbols"], timer.linked_symbols(output, expected["globals"]), "new source")
    original, rebuilt = memory_image(BASE / "susamune_pal.o"), memory_image(output)
    for anchor in receipt["dependency_anchors"]:
        address, size = anchor["address"], anchor["size"]
        if any(original[a] != rebuilt[a] for a in range(address, address + size)):
            raise ValueError("Timer external anchor bytes changed: " + anchor["name"])
    def symbols(path):
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            return {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()
                    if s["st_info"]["bind"] != "STB_LOCAL"}
    before, after = symbols(BASE / "susamune_pal.o"), symbols(output)
    hooks = []
    for patch in patches.patches:
        if patch["type"] in (patches.PatchType.B, patches.PatchType.BL):
            name = patch["sym"]
            if before[name] != after[name]:
                raise ValueError("Retail hook destination moved: " + name)
            hooks.append({"name": name, "address": after[name]})
    return {"timer_symbols_identical": len(expected["symbols"]),
            "dependency_anchor_bytes_identical": 9, "retail_hook_targets_identical": hooks}


def new_source_proofs(folder, receipt):
    rows, relocation = receipt["unique_sections"], receipt["pinned_cold"]
    plan = relocation["plan"]
    hole_begin, hole_end = plan["hole_begin"], plan["hole_end"]
    synthetic = compile_fixture(folder, "synthetic", '''extern "C" {
__attribute__((naked, used, section(".twp.new.text"))) void twp_new_code() {
    __asm__ volatile(".rept 31\\n nop\\n .endr\\n blr");
}
__attribute__((used, section(".twp.new.data"))) volatile unsigned char twp_new_data[128] = { 1 };
}
''')
    with synthetic.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.get_section_by_name(".twp.new.text")["sh_size"] != 128 or elf.get_section_by_name(".twp.new.data")["sh_size"] != 128:
            raise ValueError("Synthetic source is not exactly 256 bytes")
    extra = (f" .incoming {plan['island_begin']:#x} : {{ KEEP(*(.text.gates)) }}\n"
             f" .newtext {hole_begin:#x} : {{ KEEP(*(.twp.new.text)) }}\n"
             f" .newdata {hole_begin + 128:#x} : {{ KEEP(*(.twp.new.data)) }}\n")
    layout = folder / "pinned-new.ld"
    pinned_script(layout, rows, relocation["removed"], extra)
    inputs = [folder / "relocated-input.o", folder / "incoming-gates.o", synthetic]
    output = gnu_link(folder, "pinned-new", inputs, layout)
    synthetic_receipt = verify_fixed(output, receipt)
    synthetic_receipt.update({"elf": str(output), "code_bytes": 128, "data_bytes": 128,
                              "allocation_begin": hole_begin, "allocation_end": hole_begin + 256})
    old, new = memory_image(folder / "pinned-cold.elf"), memory_image(output)
    if any(old.get(a, 0) != new.get(a, 0) for a in old.keys() | new.keys()
           if not hole_begin <= a < hole_begin + 256):
        raise ValueError("Synthetic source changed pre-existing allocated bytes")
    synthetic_receipt["preexisting_bytes_unchanged"] = True

    original_source = (ROOT / "src/checksum.cpp").read_text()
    needle = "u32 crc32(const void *data, u32 size, u32 zeroOffset, u32 zeroSize) {"
    if original_source.count(needle) != 1:
        raise ValueError("Growth fixture source anchor changed")
    grown_source = original_source.replace(needle, needle + '\n    __asm__ volatile(".rept 64\\n nop\\n .endr");')
    grown = compile_fixture(folder, "checksum-growth", grown_source)
    grown_input = folder / "checksum-growth-unique.o"
    grown_rows = unique_sections(grown, grown_input)
    symbol_name = "crc32__8ChecksumFPCvUlUlUl"
    old_row = next(r for r in rows if r["original_name"] == ".text." + symbol_name)
    if old_row["address"] in relocation["cold"]["outbound_targets"]:
        raise ValueError("Growth fixture needs a rebuilt outbound cold gate")
    replacement = bytearray((folder / "relocated-input.o").read_bytes())
    with (folder / "relocated-input.o").open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        matched = 0
        for index, sym in enumerate(table.iter_symbols()):
            if sym.name == symbol_name:
                if sym["st_shndx"] != old_row["index"]:
                    raise ValueError("Growth replacement source section changed")
                offset = table["sh_offset"] + index * 16
                struct.pack_into(">II", replacement, offset + 4, 0, 0)
                struct.pack_into(">H", replacement, offset + 14, 0)
                matched += 1
        if matched != 1:
            raise ValueError("Growth replacement is not a unique global definition")
    replacement_path = folder / "growth-input.o"
    replacement_path.write_bytes(replacement)
    allocation = hole_begin + 256
    growth_sections = []
    for row in grown_rows:
        if not row["bytes"]:
            continue
        if row["type"] != "SHT_PROGBITS":
            raise ValueError("Unexpected growth fixture section")
        allocation = cold.align(allocation, 4)
        extra += f" .growth{row['index']} {allocation:#x} : {{ KEEP(*({row['name']})) }}\n"
        growth_sections.append({**row, "address": allocation})
        allocation += row["bytes"]
    if allocation > hole_end:
        raise ValueError("Growth fixture exceeds recovered hole")
    extra += f' ASSERT(. <= {hole_end:#x}, "new source exceeds recovered hole")\n'
    layout = folder / "pinned-growth.ld"
    pinned_script(layout, rows, relocation["removed"] + [old_row["index"]], extra)
    output = gnu_link(folder, "pinned-growth", [replacement_path, inputs[1], synthetic, grown_input], layout)
    growth_receipt = verify_fixed(output, receipt)
    new_function = next(r for r in growth_sections if r["original_name"] == old_row["original_name"])
    if new_function["bytes"] != old_row["bytes"] + 256:
        raise ValueError("Existing source body did not grow by exactly 256 bytes")
    actual_relocs = cold.final_relocations(output)
    previous_relocs = cold.final_relocations(folder / "pinned-new.elf")
    callers = [r for r in previous_relocs if r["target"] == old_row["address"]]
    if not callers:
        raise ValueError("Growth fixture has no real callers")
    for caller in callers:
        actual = next(r for r in actual_relocs if r["site"] == caller["site"])
        if actual["target"] != new_function["address"] or actual["type"] != caller["type"]:
            raise ValueError("Real growth-fixture caller was not relinked")
    allowed = set(range(old_row["address"], old_row["address"] + old_row["bytes"]))
    allowed.update(range(hole_begin + 256, allocation))
    for caller in callers:
        allowed.update(range(caller["site"], caller["site"] + 4))
    before, after = memory_image(folder / "pinned-new.elf"), memory_image(output)
    if any(before.get(a, 0) != after.get(a, 0) for a in before.keys() | after.keys() if a not in allowed):
        raise ValueError("Source growth changed unrelated allocated bytes")
    growth_receipt.update({"elf": str(output), "original_source_sha256": hashlib.sha256(original_source.encode()).hexdigest(),
        "fixture_source_sha256": sha(folder / "checksum-growth.cpp"), "original_code_bytes": old_row["bytes"],
        "grown_code_bytes": new_function["bytes"], "new_code_address": new_function["address"],
        "real_callers_relinked": len(callers), "extra_rodata_bytes": sum(r["bytes"] for r in growth_sections if not r["flags"] & 4),
        "hole_bytes_consumed_with_synthetic": allocation - hole_begin,
        "hole_bytes_remaining": hole_end - allocation, "unrelated_allocated_bytes_unchanged": True,
        "new_input_sections": growth_sections})
    return {"synthetic_256": synthetic_receipt, "existing_source_growth": growth_receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/timewarp-pinned-link")
    parser.add_argument("--skip-compile", action="store_true")
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / "build/timewarp-pinned-link").resolve()):
        parser.error("Output must remain in the private pinned-link tree")
    folder.mkdir(parents=True, exist_ok=True)
    source_before = sha(ROOT / "src/qft_timer.cpp")
    baseline_before = sha(timer.BASELINE)
    receipt = {"scope": "Private source/object/linker feasibility; no production linker change or runtime claim."}
    try:
        receipt.update(inventory(folder))
        if not args.skip_compile:
            receipt["fresh_compilation"] = compile_sources(folder)
        elif (folder / "fresh/compile-receipt.json").exists():
            receipt["fresh_compilation"] = json.loads((folder / "fresh/compile-receipt.json").read_text())
        receipt["unique_sections"] = unique_layout(folder)
        receipt["pinned_baseline"] = pin_baseline(folder, receipt["unique_sections"])
        receipt["pinned_cold"] = cold_relink(folder, receipt["unique_sections"])
        receipt["new_source_proofs"] = new_source_proofs(folder, receipt)
        receipt["inventory_complete"] = True
    finally:
        receipt["timer_source_unchanged"] = source_before == sha(ROOT / "src/qft_timer.cpp")
        receipt["timer_baseline_unchanged"] = baseline_before == sha(timer.BASELINE)
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
