"""Private relocation proof for the released menu COMDAT tail.

No production inputs are edited. Final relocation records must reconstruct
the original object bodies exactly before any cold bytes are emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

from elftools.elf.elffile import ELFFile

import patches
import timewarp_linked_budget as budget
import timewarp_timer_guard as guard

ROOT = Path(__file__).resolve().parents[1]
REL24, LO, HA = 10, 4, 6


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(n, unit=32):
    return (n + unit - 1) & -unit


def run(command, directory):
    result = subprocess.run([str(p) for p in command], cwd=directory,
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def elf_sections(path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        return {s.name: {"address": s["sh_addr"], "size": s["sh_size"],
                         "type": s["sh_type"], "offset": s["sh_offset"],
                         "data": s.data() if s["sh_type"] != "SHT_NOBITS" else None}
                for s in elf.iter_sections() if s["sh_flags"] & 2 and s["sh_size"]}


def final_relocations(path):
    result = []
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for section in elf.iter_sections():
            if section["sh_type"] != "SHT_RELA":
                continue
            source = elf.get_section(section["sh_info"])
            if not source["sh_flags"] & 2:
                continue
            symbols = elf.get_section(section["sh_link"])
            for relocation in section.iter_relocations():
                sym = symbols.get_symbol(relocation["r_info_sym"])
                if sym["st_shndx"] == "SHN_UNDEF":
                    raise ValueError("Unresolved final relocation: " + sym.name)
                result.append({"site": relocation["r_offset"],
                               "type": relocation["r_info_type"],
                               "target": (sym["st_value"] + relocation["r_addend"]) & 0xFFFFFFFF,
                               "symbol": sym.name, "addend": relocation["r_addend"],
                               "section": source.name})
    return result


def private_relink(build, region, directory):
    destination = directory / "baseline-with-relocations.elf"
    command = [ROOT / "toolchain/powerpc-eabi-ld.exe", "-o", destination,
               "-T", build / f"foxtrot_{region}.ld", "-T", ROOT / f"maps/{region}.ld",
               build / f"susamune_pre_{region}.o", "--gc-sections", "--emit-relocs"]
    command += ["--undefined=" + p["sym"] for p in patches.patches
                if p["type"] in (patches.PatchType.B, patches.PatchType.BL)]
    log = run(command, directory)
    original = elf_sections(build / f"susamune_{region}.o")
    emitted = elf_sections(destination)
    if original.keys() != emitted.keys():
        raise ValueError("Private relocation relink changed allocated section set")
    for name, section in original.items():
        check = emitted[name]
        if any(section[k] != check[k] for k in ("address", "size", "type", "data")):
            raise ValueError("Private relocation relink changed allocated section " + name)
    (directory / "relink-command.json").write_text(json.dumps([str(p) for p in command], indent=2) + "\n")
    (directory / "relink.log").write_text(log)
    return destination, original


def veneer(target):
    return struct.pack(">4I", 0x3D800000 | (target >> 16),
                       0x618C0000 | (target & 0xFFFF), 0x7D8903A6, 0x4E800420)


def shared_gate_entry(target, address, tail):
    if type(target) is not int or not 0 <= target <= 0xFFFFFFFF or target & 3 or address & 3:
        raise ValueError("Shared gate target or source is not an aligned PPC address")
    data = bytearray(struct.pack(">2I", 0x39800000 | (target & 0xFFFF), 0x48000000))
    apply_relocation(data, 4, {"type": REL24, "target": tail}, address + 4)
    return bytes(data)


def shared_gate_target(payload, offset):
    if offset & 3 or not 0 <= offset <= len(payload) - 8:
        raise ValueError("Shared gate escaped its payload")
    low, branch = struct.unpack_from(">2I", payload, offset)
    if low & 0xFFFF0000 != 0x39800000 or branch & 0xFC000003 != 0x48000000:
        raise ValueError("Shared gate changed its exact instruction sequence")
    displacement = branch & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    tail = offset + 4 + displacement
    if tail & 3 or not 0 <= tail <= len(payload) - 12:
        raise ValueError("Shared gate tail escaped its payload")
    high, move, jump = struct.unpack_from(">3I", payload, tail)
    if high & 0xFFFF0000 != 0x3D8C0000 or move != 0x7D8903A6 or jump != 0x4E800420:
        raise ValueError("Shared gate tail changed its exact instruction sequence")
    signed_low = (low & 0xFFFF) - (0x10000 if low & 0x8000 else 0)
    return (signed_low + ((high & 0xFFFF) << 16)) & 0xFFFFFFFF


def outbound_gates(gates, external_targets, shared_tails):
    targets = {source: external_targets.get(source, source) for source in gates}
    definitions, code = [], bytearray()
    if not shared_tails:
        for source, name in gates.items():
            definitions.append((name, len(code), 16))
            code.extend(veneer(targets[source]))
        return bytes(code), definitions, 0
    highs = sorted({((target + 0x8000) >> 16) & 0xFFFF for target in targets.values()})
    tails = {high: len(gates) * 8 + i * 12 for i, high in enumerate(highs)}
    for source, name in gates.items():
        target = targets[source]
        definitions.append((name, len(code), 8))
        code.extend(shared_gate_entry(target, len(code), tails[((target + 0x8000) >> 16) & 0xFFFF]))
    for high in highs:
        # li sign-extends the low half; addis uses the matching adjusted high.
        code.extend(struct.pack(">3I", 0x3D8C0000 | high, 0x7D8903A6, 0x4E800420))
    return bytes(code), definitions, len(highs)


def apply_relocation(data, offset, relocation, source_address):
    target, kind = relocation["target"], relocation["type"]
    if kind == REL24:
        word = struct.unpack_from(">I", data, offset)[0]
        if word >> 26 != 18 or word & 2 or target & 3:
            raise ValueError("REL24 is not an aligned relative branch")
        delta = target - source_address
        if not -(1 << 25) <= delta < (1 << 25):
            raise ValueError("REL24 exceeds signed branch range")
        struct.pack_into(">I", data, offset, (word & 0xFC000003) | (delta & 0x03FFFFFC))
    elif kind in (LO, HA):
        value = target & 0xFFFF if kind == LO else ((target + 0x8000) >> 16) & 0xFFFF
        struct.pack_into(">H", data, offset, value)
    else:
        raise ValueError("Unsupported code relocation " + str(kind))


def audit_jump_table(elf, obj, function, interior, records, all_relocs, sections, protected):
    matches = [(i, s) for i, s in enumerate(elf.iter_sections())
               if s.name == ".rodata." + function["name"]]
    if len(matches) != 1:
        raise ValueError("Interior pointers lack one named per-function jump table")
    index, section = matches[0]
    if section["sh_flags"] not in (2, 0x202) or section["sh_size"] % 4:
        raise ValueError("Jump table has unexpected storage flags or size")
    incoming = [r for r in obj["relocations"] if obj["symbols"][r["symbol"]]["section"] == index]
    if not incoming or any(r["section"] != function["object_section"] or
                           r["type"] not in (LO, HA) or r["addend"] & 3 or
                           not 0 <= r["addend"] < section["sh_size"] for r in incoming):
        raise ValueError("Jump table has an unnamed, shared or unrecognized inbound use: " + function["name"])
    sites = {function["old_address"] + r["offset"] for r in incoming}
    addends = {function["old_address"] + r["offset"]: r["addend"] for r in incoming}
    resolved = [r for r in records if r["site"] in sites]
    if len(resolved) != len(incoming) or len({r["target"] - addends[r["site"]] for r in resolved}) != 1:
        raise ValueError("Jump-table address materialization is ambiguous")
    begin = resolved[0]["target"] - addends[resolved[0]["site"]]
    end = begin + section["sh_size"]
    owner = next((s for s in sections.values() if s["data"] is not None and
                  s["address"] <= begin and end <= s["address"] + s["size"]), None)
    if owner is None or any(begin < s["address"] + s["size"] and s["address"] < end for s in protected):
        raise ValueError("Jump table overlaps protected timer storage or an unknown span")
    final_incoming = [r for r in all_relocs if begin <= r["target"] < end]
    if {r["site"] for r in final_incoming} != sites or any(r["target"] != begin + addends[r["site"]] for r in final_incoming):
        raise ValueError("Final jump table has an unexpected inbound pointer")
    entries = sorted((r for r in obj["relocations"] if r["section"] == index), key=lambda r: r["offset"])
    if [r["offset"] for r in entries] != list(range(0, section["sh_size"], 4)):
        raise ValueError("Jump table is not entirely covered by relocations")
    final_entries = [r for r in all_relocs if begin <= r["site"] < end]
    expected_entries = []
    for entry in entries:
        target = obj["symbols"][entry["symbol"]]
        if (entry["type"] != 1 or target["type"] != "STT_SECTION" or
                target["section"] != function["object_section"] or
                not 0 <= entry["addend"] < function["size"] or entry["addend"] & 3):
            raise ValueError("Jump table contains an unrecognized target/addend")
        expected_entries.append({"site": begin + entry["offset"], "type": 1,
                                 "target": function["old_address"] + entry["addend"]})
    if sorted((r["site"], r["type"], r["target"]) for r in final_entries) != sorted((r["site"], r["type"], r["target"]) for r in expected_entries):
        raise ValueError("Original and final jump-table relocations disagree")
    if {r["site"] for r in interior} != {r["site"] for r in expected_entries if r["target"] != function["old_address"]}:
        raise ValueError("Function has interior pointers outside its named table")
    expected_bytes = b"".join(struct.pack(">I", r["target"]) for r in expected_entries)
    offset = begin - owner["address"]
    if owner["data"][offset:offset + section["sh_size"]] != expected_bytes:
        raise ValueError("Jump-table words differ from authoritative targets")
    return {"name": section.name, "object_section": index, "address": begin,
            "size": section["sh_size"], "entries": expected_entries,
            "inbound_sites": sorted(sites), "sole_inbound_owner": function["name"]}


def extract_functions(build, region, relocs, original_sections, linked_receipt, rewrite_tables, timer_receipt, include_tiny=False, input_target="console", source_selectors=None):
    objects, owners = budget.object_inputs(build, region)
    owners["__modules__"] = set(objects)
    image = budget.LinkedImage(build / f"susamune_{region}.o", owners)
    candidates = linked_receipt["relocation_candidates"]
    cluster = next(h for h in candidates["candidate_holes"]
                   if h["span"] == "upper" and h["bytes"] > 60000)
    obj = objects["menu.cpp"]
    path = build / f"CMakeFiles/susamune_obj_{region}.dir/src/menu.cpp.obj"
    selected, rejected = [], []
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for index, definitions in obj["definitions"].items():
            matches = [(s, f) for s in definitions for f in image.resolve(s)
                       if (s["name"] in source_selectors if source_selectors is not None else
                           cluster["begin"] <= f["address"] and
                           f["address"] + f["size"] <= cluster["end"]) and f["size"]]
            if not matches:
                continue
            section = elf.get_section(index)
            if (len(matches) != 1 or len(definitions) != 1 or
                    matches[0][0]["type"] != "STT_FUNC" or matches[0][0]["address"] != 0 or
                    section["sh_flags"] & 7 != 6 or
                    section["sh_size"] != matches[0][0]["size"] or
                    section["sh_size"] != matches[0][1]["size"]):
                raise ValueError("Mixed or ambiguously linked input section " + str(index))
            source, final = matches[0]
            function = {"name": source["name"], "old_address": final["address"],
                        "size": final["size"], "object_section": index,
                        "object_section_name": section.name}
            data = bytearray(section.data())
            records = [r for r in relocs if final["address"] <= r["site"] < final["address"] + final["size"]]
            object_records = [r for r in obj["relocations"] if r["section"] == index]
            if sorted((r["site"] - final["address"], r["type"]) for r in records) != sorted((r["offset"], r["type"]) for r in object_records):
                raise ValueError("Original and emitted relocation sites differ: " + source["name"])
            for r in records:
                apply_relocation(data, r["site"] - final["address"], r, r["site"])
            linked_section = next(s for s in original_sections.values()
                                  if s["address"] <= final["address"] < s["address"] + s["size"])
            offset = final["address"] - linked_section["address"]
            if bytes(data) != linked_section["data"][offset:offset + final["size"]]:
                raise ValueError("Object relocations do not reconstruct baseline: " + source["name"])
            if source_selectors is not None:
                sites = {r["site"] for r in records}
                for position in range(0, len(data), 4):
                    word = struct.unpack_from(">I", data, position)[0]
                    opcode = word >> 26
                    if opcode not in (16, 18):
                        continue
                    if word & 2:
                        raise ValueError("Cold source contains an absolute branch")
                    mask, sign = (0xFFFC, 0x8000) if opcode == 16 else (0x3FFFFFC, 0x2000000)
                    delta = word & mask
                    if delta & sign:
                        delta -= sign * 2
                    target = final["address"] + position + delta
                    if not final["address"] <= target < final["address"] + final["size"] and final["address"] + position not in sites:
                        raise ValueError("External cold source branch lacks a relocation")
            interior = [r for r in relocs if final["address"] < r["target"] < final["address"] + final["size"]]
            if interior and rewrite_tables:
                function["jump_table"] = audit_jump_table(
                    elf, obj, function, interior, records, relocs, original_sections,
                    timer_receipt["builds"][f"{input_target}-{region}"]["symbols"].values())
            if (final["size"] <= 16 and not include_tiny) or (interior and not rewrite_tables):
                function["reason"] = "no saving after 16-byte entry veneer" if not interior else "interior address dependency"
                function["interior_relocations"] = interior
                rejected.append(function)
            else:
                function["data"] = bytes(data)
                function["relocations"] = records
                selected.append(function)
    selected.sort(key=lambda f: f["old_address"])
    if not selected:
        raise ValueError("No eligible individual function sections")
    tiling = selected + rejected
    if source_selectors is not None:
        if len(tiling) != len(source_selectors) or {f["name"] for f in tiling} != set(source_selectors):
            raise ValueError("Cold source selector inventory changed")
        tiling = [{"old_address": r["address"], "size": r["linked_bytes"]} for r in source_selectors.values()]
    cursor = cluster["begin"]
    for function in sorted(tiling, key=lambda f: f["old_address"]):
        if function["old_address"] != cursor:
            raise ValueError("Input functions overlap or leave unattributed cluster bytes")
        cursor += function["size"]
    if cursor != cluster["end"]:
        raise ValueError("Original input functions do not tile the linked cluster")
    return selected, rejected, cluster, sha(path.read_bytes())


def write_object(path, functions, gates, external_targets=None, *, shared_tails=False, extension_names=()):
    """Minimal big-endian PPC ET_REL; LLD applies every moved branch."""
    external_targets = external_targets or {}
    strings = bytearray(b"\0")
    symbols = [b"\0" * 16]
    indices = {}

    def symbol(name, value, size, section):
        index = len(symbols)
        offset = len(strings)
        strings.extend(name.encode() + b"\0")
        symbols.append(struct.pack(">IIIBBH", offset, value, size, 0x12, 0, section))
        indices[name] = index

    code, extension_code = bytearray(), bytearray()
    for n, function in enumerate(functions):
        extension = function["name"] in extension_names
        body = extension_code if extension else code
        function["cold_offset"] = len(body)
        function["cold_extension_span"] = extension
        function["cold_symbol"] = "cold_" + str(n)
        body.extend(function["data"])
        symbol(function["cold_symbol"], function["cold_offset"], function["size"], 6 if extension else 1)
    gate_code, gate_definitions, tail_count = outbound_gates(gates, external_targets, shared_tails)
    for name, offset, size in gate_definitions:
        symbol(name, offset, size, 2)
    moved = {f["old_address"]: f for f in functions}
    relocation_bytes, extension_relocations = bytearray(), bytearray()
    for function in functions:
        for r in function["relocations"]:
            if r["type"] != REL24:
                continue
            target_name = moved[r["target"]]["cold_symbol"] if r["target"] in moved else gates[r["target"]]
            offset = function["cold_offset"] + r["site"] - function["old_address"]
            body = extension_code if function["cold_extension_span"] else code
            relocations = extension_relocations if function["cold_extension_span"] else relocation_bytes
            word = struct.unpack_from(">I", body, offset)[0]
            struct.pack_into(">I", body, offset, word & 0xFC000003)
            relocations.extend(struct.pack(">IIi", offset, indices[target_name] << 8 | REL24, 0))
    # name, type, flags, payload, link, info, alignment, entry size
    sections = [("", 0, 0, b"", 0, 0, 0, 0),
                (".text.cold", 1, 6, bytes(code), 0, 0, 4, 0),
                (".text.gates", 1, 6, bytes(gate_code), 0, 0, 4, 0),
                (".rela.text.cold", 4, 0, bytes(relocation_bytes), 4, 1, 4, 12),
                (".symtab", 2, 0, b"".join(symbols), 5, 1, 4, 16),
                (".strtab", 3, 0, bytes(strings), 0, 0, 1, 0)]
    if extension_code:
        sections.extend(((".text.extension", 1, 6, bytes(extension_code), 0, 0, 4, 0),
                         (".rela.text.extension", 4, 0, bytes(extension_relocations), 4, 6, 4, 12)))
    names = bytearray(b"\0")
    name_offsets = [0]
    for name in [s[0] for s in sections[1:]] + [".shstrtab"]:
        name_offsets.append(len(names))
        names.extend(name.encode() + b"\0")
    sections.append((".shstrtab", 3, 0, bytes(names), 0, 0, 1, 0))
    data = bytearray(b"\0" * 52)
    headers = []
    for number, (_, kind, flags, payload, link, info, alignment, entry_size) in enumerate(sections):
        if number == 0:
            headers.append(b"\0" * 40)
            continue
        data.extend(b"\0" * (align(len(data), max(1, alignment)) - len(data)))
        offset = len(data)
        data.extend(payload)
        headers.append(struct.pack(">10I", name_offsets[number], kind, flags, 0, offset,
                                   len(payload), link, info, alignment, entry_size))
    data.extend(b"\0" * (align(len(data), 4) - len(data)))
    section_offset = len(data)
    data.extend(b"".join(headers))
    ident = b"\x7fELF\x01\x02\x01" + b"\0" * 9
    data[:52] = struct.pack(">16sHHIIIIIHHHHHH", ident, 1, 20, 1, 0, 0, section_offset,
                            0, 52, 0, 0, 40, len(sections), len(sections) - 1)
    path.write_bytes(data)
    return {"bytes": gate_code, "definitions": gate_definitions, "tail_count": tail_count}


def link_cold(directory, functions, base, tag, external_targets=None, *, shared_tails=False,
              extension_base=None, extension_names=(), extension_capacity=0):
    external_targets = external_targets or {}
    moved = {f["old_address"] for f in functions}
    if moved.intersection(external_targets):
        raise ValueError("External target map contains an internal cold function")
    targets = sorted({r["target"] for f in functions for r in f["relocations"]
                      if r["type"] == REL24 and r["target"] not in moved})
    gates = {target: "gate_" + str(n) for n, target in enumerate(targets)}
    obj = directory / "cold-functions.o"
    if bool(extension_names) != (extension_base is not None):
        raise ValueError("Extension function selection and fixed destination must agree")
    if extension_names and not set(extension_names).issubset({f["name"] for f in functions}):
        raise ValueError("Extension selection names an unknown cold function")
    gate_info = write_object(obj, functions, gates, external_targets, shared_tails=shared_tails,
                             extension_names=extension_names)
    layout = directory / f"cold-{tag}.ld"
    extra = (f". = {extension_base:#x}; .extension : {{ *(.text.extension) . = ALIGN(32); }}"
             if extension_names else "")
    main = f". = {base:#x}; .cold : {{ *(.text.cold) *(.text.gates) . = ALIGN(32); }}"
    spans = (extra + main) if extension_names and extension_base < base else (main + extra)
    layout.write_text(f"SECTIONS {{ {spans} }}\n")
    output = directory / f"cold-{tag}.elf"
    log = run([ROOT / "toolchain/ld.lld.exe", "-T", layout, "--emit-relocs", "-o", output, obj], directory)
    (directory / f"cold-{tag}.log").write_text(log)
    sections = elf_sections(output)
    expected_sections = {".cold", ".extension"} if extension_names else {".cold"}
    if set(sections) != expected_sections or sections[".cold"]["address"] != base:
        raise ValueError("Cold image gained unexpected allocated sections")
    payload = sections[".cold"]["data"]
    extension_payload = sections[".extension"]["data"] if extension_names else b""
    if extension_names and (sections[".extension"]["address"] != extension_base or
                            not 0 < len(extension_payload) <= extension_capacity):
        raise ValueError("Menu code extension escaped its fixed destination")
    with output.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
    for f in functions:
        f["cold_address"] = symbols[f["cold_symbol"]]
        expected = bytearray(f["data"])
        for r in f["relocations"]:
            if r["type"] == REL24:
                target = symbols[next(g["cold_symbol"] for g in functions if g["old_address"] == r["target"])] if r["target"] in moved else symbols[gates[r["target"]]]
                apply_relocation(expected, r["site"] - f["old_address"],
                                 {"type": REL24, "target": target}, f["cold_address"] + r["site"] - f["old_address"])
        owner_base, owner_payload = (extension_base, extension_payload) if f["cold_extension_span"] else (base, payload)
        offset = f["cold_address"] - owner_base
        if expected != owner_payload[offset:offset + f["size"]]:
            raise ValueError("Linked cold function differs outside authoritative branches")
    gate_begin = sum(f["size"] for f in functions if not f["cold_extension_span"])
    if payload[gate_begin:gate_begin + len(gate_info["bytes"])] != gate_info["bytes"]:
        raise ValueError("Outbound gate payload changed")
    for target, name in gates.items():
        offset = symbols[name] - base
        expected = external_targets.get(target, target)
        valid = (shared_gate_target(payload, offset) == expected if shared_tails
                 else payload[offset:offset + 16] == veneer(expected))
        if not valid:
            raise ValueError("Outbound gate changed")
    (directory / f"cold-{tag}.bin").write_bytes(payload)
    if extension_names:
        (directory / f"menu-code-{tag}.bin").write_bytes(extension_payload)
    header = struct.pack(">8I", 0x54574343, 1, base, len(payload), len(functions), len(gates),
                         zlib.crc32(payload), 64) + b"\0" * 32
    (directory / f"cold-{tag}.container").write_bytes(header + payload)
    return {"vma": base, "code_bytes": sum(f["size"] for f in functions),
            "extension": ({"vma": extension_base, "bytes": len(extension_payload),
                           "sha256": sha(extension_payload), "functions": sorted(extension_names)}
                          if extension_names else None),
            "outbound_gate_count": len(gates), "outbound_gate_bytes": len(gate_info["bytes"]),
            "outbound_gate_format": "shared-high-v1" if shared_tails else "absolute-v1",
            "outbound_shared_tail_count": gate_info["tail_count"],
            "aligned_payload_bytes": len(payload), "header_bytes": 64,
            "container_bytes": len(header) + len(payload), "payload_sha256": sha(payload),
            "all_function_bytes_verified": True, "all_gates_verified": True,
            "outbound_targets": [external_targets.get(target, target) for target in targets],
            "outbound_source_targets": targets}


def export_spans(directory, original_sections, patched, tag):
    spans = []
    for label, upper in (("low", False), ("upper", True)):
        entries = [s for name, s in original_sections.items() if name.startswith(".foxtrot") == upper]
        begin = min(s["address"] for s in entries)
        initialized_end = align(max(s["address"] + s["size"] for s in entries if s["data"] is not None), 4)
        runtime_end = max(s["address"] + s["size"] for s in entries)
        data = bytearray(initialized_end - begin)
        for section in entries:
            if section["data"] is not None:
                offset = section["address"] - begin
                data[offset:offset + section["size"]] = patched[section["offset"]:section["offset"] + section["size"]]
        path = directory / f"retained-{tag}-{label}.bin"
        path.write_bytes(data)
        spans.append({"path": str(path), "address": begin, "initialized_bytes": len(data),
                      "runtime_bytes": runtime_end - begin, "sha256": sha(data)})
    return spans


def retained_copy(build, region, directory, functions, original_sections, tag, timer_receipt, input_target="console"):
    original = (build / f"susamune_{region}.o").read_bytes()
    patched = bytearray(original)
    touched = set()
    holes = []
    for function in functions:
        section = next(s for s in original_sections.values()
                       if s["address"] <= function["old_address"] < s["address"] + s["size"])
        offset = section["offset"] + function["old_address"] - section["address"]
        size = function["size"]
        patched[offset:offset + 16] = veneer(function["cold_address"])
        patched[offset + 16:offset + size] = b"\0" * (size - 16)
        touched.update(range(offset, offset + size))
        holes.append({"begin": function["old_address"] + 16, "end": function["old_address"] + size,
                      "bytes": size - 16})
        for entry in function.get("jump_table", {}).get("entries", []):
            table_section = next(s for s in original_sections.values()
                                 if s["address"] <= entry["site"] < s["address"] + s["size"])
            table_offset = table_section["offset"] + entry["site"] - table_section["address"]
            if struct.unpack_from(">I", original, table_offset)[0] != entry["target"]:
                raise ValueError("Jump-table patch precondition changed")
            struct.pack_into(">I", patched, table_offset,
                             function["cold_address"] + entry["target"] - function["old_address"])
            touched.update(range(table_offset, table_offset + 4))
    if any(a != b and n not in touched for n, (a, b) in enumerate(zip(original, patched))):
        raise ValueError("Retained ELF changed outside explicitly moved function bodies")
    output = directory / f"retained-{tag}.elf"
    output.write_bytes(patched)
    expected = timer_receipt["builds"][f"{input_target}-{region}"]
    guard.compare(expected["symbols"], guard.linked_symbols(output, expected["globals"]),
                  "private cold-cluster linked bytes/locations")
    spans = export_spans(directory, original_sections, patched, tag)
    table_entries = [entry for f in functions for entry in f.get("jump_table", {}).get("entries", [])]
    return {"elf_sha256": sha(patched), "outside_whitelist_bytes_identical": True,
            "nonmoved_code_identical": True, "rewritten_jump_table_words": len(table_entries),
            "nonmoved_bytes_identical": not table_entries,
            "all_symbol_records_identical": True, "timer_symbols_unchanged": len(expected["symbols"]),
            "initialized_spans": spans,
            "entry_veneer_count": len(functions), "entry_veneer_bytes": len(functions) * 16,
            "reusable_mem1_bytes": sum(h["bytes"] for h in holes), "holes": holes}


def file_offset(sections, address, size):
    matches = [s for s in sections.values() if s["data"] is not None and
               s["address"] <= address and address + size <= s["address"] + s["size"]]
    if len(matches) != 1:
        raise ValueError("Edit does not belong to one initialized section")
    return matches[0]["offset"] + address - matches[0]["address"]


def verify_incoming_word(original, offset, relocation):
    before = original[offset:offset + 4]
    if len(before) != 4 or relocation["site"] & 3:
        raise ValueError("Incoming relocation is not a full aligned word")
    if relocation["type"] == REL24:
        reconstructed = bytearray(before)
        apply_relocation(reconstructed, 0, relocation, relocation["site"])
        if reconstructed != before:
            raise ValueError("Incoming branch record does not match original instruction")
    elif relocation["type"] == 1:
        if struct.unpack(">I", before)[0] != relocation["target"]:
            raise ValueError("Incoming pointer record does not match original word")
    else:
        raise ValueError("Unrecognized incoming relocation type")


def audit_incoming(build, region, functions, cluster, relocs, sections, region_budget, timer_receipt, input_target="console", shared_sites=()):
    objects, owners = budget.object_inputs(build, region)
    owners["__modules__"] = set(objects)
    image = budget.LinkedImage(build / f"susamune_{region}.o", owners)
    entries = {f["old_address"]: f for f in functions}
    tables = {r["site"]: (f, r) for f in functions for r in f.get("jump_table", {}).get("entries", [])}
    fixed = list(timer_receipt["builds"][f"{input_target}-{region}"]["symbols"].values())
    fixed += region_budget["relocation_candidates"]["timer_fixed_target_symbols"]
    original = (build / f"susamune_{region}.o").read_bytes()
    incoming = []
    for r in relocs:
        if not any(f["old_address"] <= r["target"] < f["old_address"] + f["size"] for f in functions):
            continue
        if any(f["old_address"] <= r["site"] < f["old_address"] + f["size"] for f in functions):
            if r["type"] != REL24 or r["target"] not in entries:
                raise ValueError("Unrecognized cold self-reference")
            continue
        if any(r["site"] < s["address"] + s["size"] and s["address"] < r["site"] + 4 for s in fixed):
            raise ValueError("Incoming rewrite touches a protected timer/dependency symbol")
        source = image.at(r["site"])
        if r["site"] in tables:
            function, expected = tables[r["site"]]
            if r["type"] != 1 or r["target"] != expected["target"]:
                raise ValueError("Incoming jump-table record changed")
            kind = "audited-jump-table"
            owner_names = [function["jump_table"]["name"]]
        else:
            if r["target"] not in entries:
                raise ValueError("Incoming unrecognized interior pointer")
            function = entries[r["target"]]
            shared_call = (source and source["attribution"] == "shared" and r["site"] in shared_sites
                           and r["type"] == REL24 and source["kind"] == "code")
            if not source or source["attribution"] != "exclusive" and not shared_call or not source["symbols"]:
                raise ValueError(f"Incoming reference has no unambiguous named owner at {r['site']:#x}: {source}")
            owner_names = source["symbols"]
            if r["type"] == REL24 and source["kind"] == "code":
                kind = "named-call"
            elif r["type"] == 1 and source["kind"] in ("data", "rodata") and all(n.startswith("__vt__") for n in owner_names):
                kind = "named-vtable"
            else:
                raise ValueError("Incoming reference is not a named call or vtable word")
        verify_incoming_word(original, file_offset(sections, r["site"], 4), r)
        incoming.append({**r, "kind": kind, "source_owners": owner_names,
                         "function": function["name"], "function_old_address": function["old_address"],
                         "target_offset": r["target"] - function["old_address"]})
    gate_targets = sorted({r["target"] for r in incoming if r["type"] == REL24})
    island_begin = align(cluster["begin"])
    island_end = island_begin + len(gate_targets) * 16
    hole_begin = align(island_end)
    if hole_begin >= cluster["end"]:
        raise ValueError("Gateway island consumes the cluster")
    return {"incoming": incoming, "gate_targets": gate_targets,
            "island_begin": island_begin, "island_end": island_end,
            "hole_begin": hole_begin, "hole_end": cluster["end"],
            "protected_ranges": fixed}


def retained_consolidated(build, region, directory, functions, sections, tag, timer_receipt, cluster, plan, input_target="console"):
    original_path = build / f"susamune_{region}.o"
    original = original_path.read_bytes()
    patched = bytearray(original)
    touched = set()
    relocated = {f["old_address"]: f["cold_address"] for f in functions}

    def edit(address, data):
        if any(address < s["address"] + s["size"] and s["address"] < address + len(data) for s in plan["protected_ranges"]):
            raise ValueError("Consolidated edit overlaps protected timer/dependency bytes")
        offset = file_offset(sections, address, len(data))
        patched[offset:offset + len(data)] = data
        touched.update(range(offset, offset + len(data)))

    edit(cluster["begin"], b"\0" * cluster["bytes"])
    gateways = {target: plan["island_begin"] + i * 16 for i, target in enumerate(plan["gate_targets"])}
    for target, address in gateways.items():
        edit(address, veneer(relocated[target]))
    patched_sites = []
    for r in plan["incoming"]:
        offset = file_offset(sections, r["site"], 4)
        verify_incoming_word(original, offset, r)
        if r["type"] == REL24:
            data = bytearray(original[offset:offset + 4])
            target = gateways[r["target"]]
            apply_relocation(data, 0, {"type": REL24, "target": target}, r["site"])
        else:
            target = relocated[r["function_old_address"]] + r["target_offset"]
            data = struct.pack(">I", target)
        edit(r["site"], data)
        patched_sites.append({**r, "new_target": target})
    moved_symbols = []
    with original_path.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        for index, symbol in enumerate(table.iter_symbols()):
            address = symbol["st_value"]
            if not cluster["begin"] <= address < cluster["end"]:
                continue
            if address not in relocated or symbol["st_info"]["type"] != "STT_FUNC":
                raise ValueError("Unrecognized interior/alias symbol in consolidated cluster")
            offset = table["sh_offset"] + index * table["sh_entsize"]
            struct.pack_into(">I", patched, offset + 4, relocated[address])
            struct.pack_into(">H", patched, offset + 14, 0xFFF1)
            touched.update(range(offset, offset + table["sh_entsize"]))
            moved_symbols.append({"name": symbol.name, "old_address": address, "cold_address": relocated[address]})
    if len(original) != len(patched) or any(a != b and n not in touched for n, (a, b) in enumerate(zip(original, patched))):
        raise ValueError("Consolidated ELF changed outside its exact whitelist")
    hole_offset = file_offset(sections, plan["hole_begin"], plan["hole_end"] - plan["hole_begin"])
    if any(patched[hole_offset:hole_offset + plan["hole_end"] - plan["hole_begin"]]):
        raise ValueError("Consolidated free region is not empty")
    output = directory / f"retained-{tag}.elf"
    output.write_bytes(patched)
    expected = timer_receipt["builds"][f"{input_target}-{region}"]
    guard.compare(expected["symbols"], guard.linked_symbols(output, expected["globals"]), "consolidated timer")
    spans = export_spans(directory, sections, patched, tag)
    return {"elf_sha256": sha(patched), "outside_whitelist_bytes_identical": True,
            "timer_symbols_unchanged": len(expected["symbols"]), "timer_dependency_bytes_unchanged": True,
            "nonmoved_symbol_records_identical": True, "moved_symbol_records": moved_symbols,
            "initialized_spans": spans, "incoming_patches": patched_sites,
            "incoming_patch_counts": dict(Counter(r["kind"] for r in patched_sites)),
            "gateway_island": {"begin": plan["island_begin"], "end": plan["island_end"],
                               "gateway_count": len(gateways), "bytes": len(gateways) * 16},
            "cluster_alignment_cost": plan["hole_begin"] - cluster["begin"] - len(gateways) * 16,
            "reusable_mem1_bytes": plan["hole_end"] - plan["hole_begin"],
            "cache_line_aligned_reusable_bytes": (plan["hole_end"] & ~31) - plan["hole_begin"],
            "holes": [{"begin": plan["hole_begin"], "end": plan["hole_end"],
                       "bytes": plan["hole_end"] - plan["hole_begin"]}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=("pal", "us", "jp"), default=("pal",))
    parser.add_argument("--target", choices=("console", "emu"), default="console")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--linked-budget", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-cold-cluster")
    parser.add_argument("--cold-offset", type=lambda value: int(value, 0), default=0xA0,
                        help="Payload VMA offset from retained-image base; independent of this private header")
    parser.add_argument("--rewrite-jump-tables", action="store_true",
                        help="Expand only through fully audited per-function CPU jump tables")
    parser.add_argument("--consolidate", action="store_true",
                        help="Replace per-entry veneers with an audited incoming-call island")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.consolidate:
        args.rewrite_jump_tables = True
    args.build = args.build or ROOT / f"build/baseline-{args.target}"
    args.linked_budget = args.linked_budget or ROOT / ("build/timewarp-linked-budget/receipt.json" if args.target == "console" else "build/timewarp-linked-budget/emu-receipt.json")
    directory = args.output.resolve()
    if (not directory.is_relative_to((ROOT / "build").resolve()) or
            directory.is_relative_to(args.build.resolve()) or args.build.resolve().is_relative_to(directory)):
        parser.error("Use a private output directory under this checkout's build directory")
    if args.cold_offset < 0x40 or args.cold_offset & 31:
        parser.error("Cold payload offset must be cache-line aligned and leave header space")
    previous = directory / "receipt.json"
    if previous.exists():
        saved = json.loads(previous.read_text())
        if (bool(saved.get("consolidate")) != args.consolidate or
                bool(saved.get("rewrite_jump_tables")) != args.rewrite_jump_tables or
                saved.get("input_target", "console") != args.target or
                saved.get("cold_offset", args.cold_offset) != args.cold_offset):
            parser.error("Preserve prior variants by choosing a separate output directory")
    baseline = json.loads(guard.BASELINE.read_text())
    guard.verify(baseline, args.build, args.target, args.regions)
    linked = json.loads(args.linked_budget.read_text())
    receipt = {"scope": "Private link/byte proof only. No game boot, reset, multitab gameplay or real-Wii execution is established. Timer and nonmoved symbol records stay fixed. Bytes outside moved bodies and explicitly whitelisted jump-table/call/vtable words stay fixed; zeroed holes require explicit allocation before use. Consolidated moved symbols describe the separate cold ELF using absolute symbol addresses.",
               "script_sha256": sha(Path(__file__).read_bytes()), "cold_offset": args.cold_offset,
               "rewrite_jump_tables": args.rewrite_jump_tables,
               "consolidate": args.consolidate,
               "input_target": args.target,
               "timer_baseline_sha256": sha(guard.BASELINE.read_bytes()),
               "tool_sha256": {name: sha((ROOT / "toolchain" / name).read_bytes())
                               for name in ("powerpc-eabi-ld.exe", "ld.lld.exe")}, "regions": []}
    for region in args.regions:
        target = directory / region
        target.mkdir(parents=True, exist_ok=True)
        emitted, sections = private_relink(args.build, region, target)
        relocations = final_relocations(emitted)
        region_budget = next(r for r in linked["regions"] if r["region"] == region)
        if region_budget["elf_sha256"] != sha((args.build / f"susamune_{region}.o").read_bytes()):
            raise ValueError("Linked budget describes another ELF")
        functions, rejected, cluster, object_sha = extract_functions(
            args.build, region, relocations, sections, region_budget, args.rewrite_jump_tables, baseline, args.consolidate, args.target)
        plan = audit_incoming(args.build, region, functions, cluster, relocations, sections,
                              region_budget, baseline, args.target) if args.consolidate else None
        variants = {}
        placements = [("dolphin-vma", 0x71E3F000 + args.cold_offset)]
        if args.target == "console":
            placements.insert(0, ("console", 0x91E3F000 + args.cold_offset))
        for tag, base in placements:
            cold = link_cold(target, functions, base, tag)
            retained = (retained_consolidated(args.build, region, target, functions, sections, tag, baseline, cluster, plan, args.target)
                        if args.consolidate else retained_copy(args.build, region, target, functions, sections, tag, baseline, args.target))
            variants[tag] = {"cold": cold, "retained": retained}
        row = {"region": region, "baseline_elf_sha256": region_budget["elf_sha256"],
               "prelinked_object_sha256": sha((args.build / f"susamune_pre_{region}.o").read_bytes()),
               "emitted_relocations_elf_sha256": sha(emitted.read_bytes()),
               "source_object_sha256": object_sha, "cluster": cluster, "rejected": rejected,
               "moved_functions": [{k: v for k, v in f.items() if k not in ("data", "relocations", "cold_address")} for f in functions],
               "relocation_types": dict(Counter(str(r["type"]) for f in functions for r in f["relocations"])),
               "variants": variants}
        receipt["regions"].append(row)
        reported = variants.get("console", variants["dolphin-vma"])
        print(json.dumps({"region": region, "moved_functions": len(functions), "kept_hot": len(rejected),
                          "reusable_mem1_bytes": reported["retained"]["reusable_mem1_bytes"],
                          "cold_container_bytes": reported["cold"]["container_bytes"]}), flush=True)
    (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def self_test():
    passed = 0

    def fails(call):
        nonlocal passed
        try:
            call()
        except ValueError:
            passed += 1
            return
        raise AssertionError("Unsafe fixture was accepted")

    branch = bytearray(struct.pack(">I", 0x48000001))
    apply_relocation(branch, 0, {"type": REL24, "target": 0x1000}, 0x1100)
    assert struct.unpack(">I", branch)[0] == 0x4BFFFF01
    passed += 1
    fails(lambda: apply_relocation(bytearray(branch), 0, {"type": REL24, "target": 0x70000000}, 0x80000000))
    fails(lambda: apply_relocation(bytearray(branch), 0, {"type": 99, "target": 0}, 0))
    assert veneer(0x91E3F0A0) == struct.pack(">4I", 0x3D8091E3, 0x618CF0A0, 0x7D8903A6, 0x4E800420)
    passed += 1

    class Section(dict):
        name = ".rodata.test"

    class Elf:
        def __init__(self, flags=2):
            self.section = Section(sh_flags=flags, sh_size=8)

        def iter_sections(self):
            blank = Section()
            blank.name = ""
            return iter((blank, blank, self.section))

    function = {"name": "test", "object_section": 1, "old_address": 0x1000, "size": 32}
    obj = {"symbols": [{"section": 1, "type": "STT_SECTION"}, {"section": 2, "type": "STT_SECTION"}],
           "relocations": [{"section": 1, "offset": 2, "type": HA, "symbol": 1, "addend": 0},
                           {"section": 1, "offset": 6, "type": LO, "symbol": 1, "addend": 0},
                           {"section": 2, "offset": 0, "type": 1, "symbol": 0, "addend": 8},
                           {"section": 2, "offset": 4, "type": 1, "symbol": 0, "addend": 12}]}
    records = [{"site": 0x1002, "type": HA, "target": 0x2000}, {"site": 0x1006, "type": LO, "target": 0x2000}]
    interior = [{"site": 0x2000, "type": 1, "target": 0x1008}, {"site": 0x2004, "type": 1, "target": 0x100C}]
    sections = {".rodata": {"address": 0x2000, "size": 8, "data": struct.pack(">2I", 0x1008, 0x100C)}}
    args = [Elf(), obj, function, interior, records, records + interior, sections, []]
    assert audit_jump_table(*args)["sole_inbound_owner"] == "test"
    passed += 1
    changed = deepcopy(args)
    changed[0] = Elf(3)
    fails(lambda: audit_jump_table(*changed))
    changed = deepcopy(args)
    changed[7] = [{"address": 0x2004, "size": 4}]
    fails(lambda: audit_jump_table(*changed))
    changed = deepcopy(args)
    changed[5].append({"site": 0x3000, "type": HA, "target": 0x2000})
    fails(lambda: audit_jump_table(*changed))
    changed = deepcopy(args)
    changed[1]["relocations"][2]["addend"] = 10
    fails(lambda: audit_jump_table(*changed))
    changed = deepcopy(args)
    changed[6][".rodata"]["data"] = b"\0" * 8
    fails(lambda: audit_jump_table(*changed))
    call_record = {"site": 0x1100, "type": REL24, "target": 0x1000}
    verify_incoming_word(bytes(branch), 0, call_record)
    passed += 1
    fails(lambda: verify_incoming_word(bytes(branch), 0, {**call_record, "target": 0x1004}))
    pointer_record = {"site": 0x2000, "type": 1, "target": 0x1000}
    verify_incoming_word(struct.pack(">I", 0x1000), 0, pointer_record)
    passed += 1
    fails(lambda: verify_incoming_word(struct.pack(">I", 0x1000), 0, {**pointer_record, "target": 0x1004}))
    fails(lambda: verify_incoming_word(struct.pack(">I", 0x1000), 0, {**pointer_record, "type": LO}))
    fails(lambda: verify_incoming_word(struct.pack(">I", 0x1000), 0, {**pointer_record, "site": 0x2002}))
    print(json.dumps({"self_tests_passed": passed}))


if __name__ == "__main__":
    main()
