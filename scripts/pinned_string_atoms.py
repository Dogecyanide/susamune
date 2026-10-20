"""Source-derived string atoms with frozen protected literal addresses."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "doc/timewarp-pinned-string-atoms.json"
PREFIX = ".twp.string."


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atom_name(data):
    return PREFIX + sha(data)


def symbol_name(name):
    return "__twp_string_" + name[len(PREFIX):]


def atoms(data):
    result = []
    begin = 0
    while begin < len(data):
        end = data.find(b"\0", begin)
        if end < 0:
            raise ValueError("Unterminated allocated string atom")
        result.append((begin, data[begin:end + 1]))
        begin = end + 1
    return result


def locate(entries, offset, size=0):
    matches = [(begin, data) for begin, data in entries if begin <= offset < begin + len(data)]
    if len(matches) != 1 or size and offset + size > matches[0][0] + len(matches[0][1]):
        raise ValueError("String reference crosses an atom or is one-past the pool")
    return matches[0]


def string_sections(elf):
    result = {}
    for index, section in enumerate(elf.iter_sections()):
        if section["sh_flags"] & 0x22 != 0x22:
            continue
        if (section["sh_type"] != "SHT_PROGBITS" or section["sh_flags"] != 0x32 or
                section["sh_entsize"] != 1 or section["sh_addralign"] != 1):
            raise ValueError("Unsupported allocated string section attributes")
        result[index] = atoms(section.data())
    return result


def protected_rows(original, frozen):
    return [{**value, "name": key.split(":", 1)[1], "owners": ["qft_timer.cpp"]}
            for key, value in frozen["symbols"].items()] + original["anchors"]


def decode_target(records, image_sections):
    import link_pinned_mod as pinned
    values = defaultdict(set)
    for record in records:
        width = 4 if record["type"] == 1 else 2
        if record["type"] not in (1, 4, 5, 6):
            raise ValueError("Unsupported protected string relocation")
        values[record["type"]].add(int.from_bytes(pinned.range_bytes(image_sections, record["site"], width), "big"))
    if any(len(v) != 1 for v in values.values()):
        raise ValueError("Protected string address halves disagree")
    targets = set(values[1])
    if values[4] and (values[5] or values[6]):
        low = next(iter(values[4]))
        if values[5]:
            targets.add(next(iter(values[5])) << 16 | low)
        if values[6]:
            targets.add(((next(iter(values[6])) << 16) + (low if low < 0x8000 else low - 0x10000)) & 0xFFFFFFFF)
    if len(targets) != 1:
        raise ValueError("Protected string address lacks an unambiguous full relocation")
    target = targets.pop()
    if (values[4] and values[4] != {target & 0xFFFF} or
            values[5] and values[5] != {target >> 16} or
            values[6] and values[6] != {((target + 0x8000) >> 16) & 0xFFFF}):
        raise ValueError("Protected string relocation bytes disagree")
    return target


def capture_build(original, source_receipt, frozen, root, region):
    import link_pinned_mod as pinned
    partial, image = root / f"susamune_pre_{region}.o", root / f"susamune_{region}.o"
    if sha(partial.read_bytes()) != original["source_partial_sha256"] or sha(image.read_bytes()) != original["source_elf_sha256"]:
        raise ValueError("String atom frozen image identity differs")
    protected = protected_rows(original, frozen)
    by_index = {row["index"]: row for row in original["sections"]}
    image_sections = pinned.flat_sections(image)
    references = defaultdict(list)
    with partial.open("rb") as stream:
        elf = ELFFile(stream)
        pools = string_sections(elf)
        symbols = elf.get_section_by_name(".symtab")
        for section in elf.iter_sections():
            source = by_index.get(section["sh_info"]) if section["sh_type"] == "SHT_RELA" else None
            if not source or not source["live"]:
                continue
            for relocation in section.iter_relocations():
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                if symbol["st_shndx"] not in pools:
                    continue
                site = source["address"] + relocation["r_offset"]
                readers = [row for row in protected if row["address"] <= site < row["address"] + row["size"]]
                if not readers:
                    continue
                if len(readers) != 1:
                    raise ValueError("Protected string reader is ambiguous")
                offset = symbol["st_value"] + relocation["r_addend"]
                locate(pools[symbol["st_shndx"]], offset)
                references[(symbol["st_shndx"], offset)].append({
                    "site": site, "type": relocation["r_info_type"], "reader": readers[0]})
        pool_rows = [by_index[index] for index in pools if by_index[index]["live"]]
    records = {}
    for relocation_group in references.values():
        target = decode_target(relocation_group, image_sections)
        for reference in relocation_group:
            reader = reference["reader"]
            if len(reader["owners"]) != 1:
                raise ValueError("Protected string reader needs unique source ownership")
            module = reader["owners"][0]
            path = root / f"CMakeFiles/susamune_obj_{region}.dir/src" / (module + ".obj")
            object_sha = sha(path.read_bytes())
            if object_sha != source_receipt["original_object_sha256"][module]:
                raise ValueError("Protected string source object identity differs")
            with path.open("rb") as stream:
                elf = ELFFile(stream)
                symbols = elf.get_section_by_name(".symtab")
                functions = [s for s in symbols.iter_symbols() if s.name == reader["name"] and s["st_size"] == reader["size"]]
                if len(functions) != 1:
                    raise ValueError("Protected string source reader is ambiguous")
                function = functions[0]
                source_offset = function["st_value"] + reference["site"] - reader["address"]
                matches = [r for section in elf.iter_sections() if section["sh_type"] == "SHT_RELA" and
                           section["sh_info"] == function["st_shndx"] for r in section.iter_relocations()
                           if r["r_offset"] == source_offset and r["r_info_type"] == reference["type"]]
                if len(matches) != 1:
                    raise ValueError("Protected string source relocation differs")
                relocation = matches[0]
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                strings = string_sections(elf)
                if symbol["st_shndx"] not in strings:
                    raise ValueError("Protected source relocation does not target immutable strings")
                offset = symbol["st_value"] + relocation["r_addend"]
                begin, data = locate(strings[symbol["st_shndx"]], offset)
                address = target - (offset - begin)
                if pinned.range_bytes(image_sections, address, len(data)) != data:
                    raise ValueError("Protected source literal does not reconstruct linked bytes")
                name = atom_name(data)
                row = records.setdefault(name, {"name": name, "address": address, "bytes": len(data), "sha256": sha(data),
                    "references": [], "data": data})
                if row["address"] != address:
                    raise ValueError("Identical protected strings have incompatible addresses")
                row["references"].append({"reader": reader["name"], "owner": module, "reader_address": reader["address"],
                    "reader_size": reader["size"], "reader_sha256": reader["sha256"], "site": reference["site"],
                    "type": reference["type"], "target": target, "atom_offset": offset - begin,
                    "source_object_sha256": object_sha, "source_section_index": symbol["st_shndx"], "source_atom_offset": begin})
    for record in records.values():
        containers = [other for other in records.values() if other["address"] <= record["address"] and
                      record["address"] + record["bytes"] <= other["address"] + other["bytes"]]
        parent = max(containers, key=lambda row: row["bytes"])
        delta = record["address"] - parent["address"]
        if parent["data"][delta:delta + record["bytes"]] != record["data"]:
            raise ValueError("Protected string suffix overlap differs")
        record["canonical"] = parent["name"]
        record["canonical_offset"] = delta
    canonical = [row for row in records.values() if row["canonical"] == row["name"]]
    for a in canonical:
        for b in canonical:
            if a is not b and a["address"] < b["address"] + b["bytes"] and b["address"] < a["address"] + a["bytes"]:
                raise ValueError("Protected string atoms overlap without a suffix relation")
    for record in records.values():
        del record["data"]
        record["references"].sort(key=lambda row: row["site"])
    return {"source_partial_sha256": original["source_partial_sha256"], "source_elf_sha256": original["source_elf_sha256"],
            "pools": [{k: row[k] for k in ("name", "address", "bytes", "linked_bytes", "sha256", "flags", "align")} for row in pool_rows],
            "protected_reference_sites": sorted([r["site"], r["type"], r["target"]] for atom in records.values() for r in atom["references"]),
            "protected_atoms": records}


def capture():
    import link_pinned_mod as pinned
    import pinned_source_sections as owned
    import timewarp_timer_guard as timer
    original, sources, frozen = (json.loads(path.read_text()) for path in (pinned.LAYOUT, owned.LAYOUT, timer.BASELINE))
    result = {"version": 1, "original_layout_sha256": sha(pinned.LAYOUT.read_bytes()),
              "source_ownership_sha256": sha(owned.LAYOUT.read_bytes()), "timer_baseline_sha256": sha(timer.BASELINE.read_bytes()),
              "scope": "Protected immutable literal provenance and addresses only; all payloads come from current source objects.", "builds": {}}
    for key, baseline in original["builds"].items():
        target, region = key.split("-")
        result["builds"][key] = capture_build(baseline, sources["builds"][key], frozen["builds"][key], ROOT / f"build/baseline-{target}", region)
    return result


def split_object(path, protected):
    """Split source strings before -r; preserve code bytes and relocation meaning."""
    raw = bytearray(path.read_bytes())
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_type"] != "ET_REL" or elf["e_machine"] != "EM_PPC" or elf.little_endian:
            raise ValueError("String splitting needs a big-endian PPC source object")
        strings = string_sections(elf)
        if not strings:
            return []
        sections = list(elf.iter_sections())
        if any(section["sh_type"] == "SHT_REL" for section in sections):
            raise ValueError("String splitting requires explicit relocation addends")
        fixed_payloads = {index: (section["sh_type"], section["sh_flags"], section["sh_size"],
                          None if section["sh_type"] == "SHT_NOBITS" else section.data())
                          for index, section in enumerate(sections) if section["sh_flags"] & 2 and index not in strings}
        headers = [list(struct.unpack_from(">10I", raw, elf["e_shoff"] + index * 40)) for index in range(len(sections))]
        shstr = elf["e_shstrndx"]
        names = bytearray(sections[shstr].data())
        symidx = next(i for i, section in enumerate(sections) if section.name == ".symtab")
        symbols = list(sections[symidx].iter_symbols())
        symdata = bytearray(sections[symidx].data())
        stridx = sections[symidx]["sh_link"]
        symnames = names if stridx == shstr else bytearray(sections[stridx].data())
        payloads, inventory, atom_symbols, atom_sections = {}, [], {}, {}

        def append_symbol(name, section, size):
            index = len(symdata) // 16
            offset = len(symnames)
            symnames.extend(symbol_name(name).encode() + b"\0")
            symdata.extend(struct.pack(">IIIBBH", offset, 0, 0, 0x20 if section else 0x10, 0, section))
            return index

        for index, entries in strings.items():
            for begin, data in entries:
                name = atom_name(data)
                alias = protected.get(name, {})
                canonical = alias.get("canonical", name)
                if name == canonical and name not in atom_sections:
                    section_index = len(headers)
                    name_offset = len(names)
                    names.extend(name.encode() + b"\0")
                    headers.append([name_offset, 1, 0x32, 0, 0, len(data), 0, 0, 1, 1])
                    payloads[section_index] = data
                    atom_sections[name] = section_index
                inventory.append({"name": name, "canonical": canonical,
                    "canonical_offset": alias.get("canonical_offset", 0), "bytes": len(data), "sha256": sha(data),
                    "source_section_index": index, "source_offset": begin})
            headers[index][2] &= ~2
            headers[index][4] = headers[index][5] = 0
        for entry in inventory:
            name = entry["canonical"]
            if name not in atom_symbols:
                section_index = atom_sections.get(name, 0)
                atom_symbols[name] = append_symbol(name, section_index, headers[section_index][5] if section_index else 0)
        for index, symbol in enumerate(symbols):
            if symbol["st_shndx"] not in strings or symbol["st_info"]["type"] == "STT_SECTION":
                continue
            begin, data = locate(strings[symbol["st_shndx"]], symbol["st_value"], symbol["st_size"])
            name = atom_name(data)
            if protected.get(name, {}).get("canonical", name) != name:
                raise ValueError("Named string object cannot become an external suffix alias")
            struct.pack_into(">I", symdata, index * 16 + 4, symbol["st_value"] - begin)
            struct.pack_into(">H", symdata, index * 16 + 14, atom_sections[name])
        for index, section in enumerate(sections):
            if section["sh_type"] != "SHT_RELA":
                continue
            changed = bytearray(section.data())
            for position, relocation in enumerate(section.iter_relocations()):
                symbol = symbols[relocation["r_info_sym"]]
                if symbol["st_shndx"] not in strings:
                    continue
                if relocation["r_info_type"] not in (1, 4, 5, 6):
                    raise ValueError("Unsupported string atom relocation type")
                target = symbol["st_value"] + relocation["r_addend"]
                begin, data = locate(strings[symbol["st_shndx"]], target)
                name = atom_name(data)
                alias = protected.get(name, {})
                canonical = alias.get("canonical", name)
                addend = target - begin + alias.get("canonical_offset", 0)
                struct.pack_into(">Ii", changed, position * 12 + 4,
                                 atom_symbols[canonical] << 8 | relocation["r_info_type"], addend)
            payloads[index] = bytes(changed)
        payloads[symidx], payloads[stridx], payloads[shstr] = bytes(symdata), bytes(symnames), bytes(names)
        for index, data in payloads.items():
            alignment = max(1, headers[index][8])
            raw.extend(bytes((-len(raw)) % alignment))
            headers[index][4], headers[index][5] = len(raw), len(data)
            raw.extend(data)
        raw.extend(bytes((-len(raw)) % 4))
        offset = len(raw)
        raw.extend(b"".join(struct.pack(">10I", *header) for header in headers))
        struct.pack_into(">I", raw, 32, offset)
        struct.pack_into(">H", raw, 48, len(headers))
    path.write_bytes(raw)
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for index, expected in fixed_payloads.items():
            section = elf.get_section(index)
            actual = (section["sh_type"], section["sh_flags"], section["sh_size"],
                      None if section["sh_type"] == "SHT_NOBITS" else section.data())
            if actual != expected:
                raise ValueError("String split changed a non-string allocated payload")
    return inventory


def normalize_partial(path, objects, protected):
    expected = {}
    for module, inventory in objects.items():
        for atom in inventory:
            if atom["canonical"] != atom["name"]:
                continue
            record = expected.setdefault(atom["name"], {"name": atom["name"], "bytes": atom["bytes"],
                "sha256": atom["sha256"], "owners": []})
            if any(record[k] != atom[k] for k in ("bytes", "sha256")):
                raise ValueError("String atom identity collision")
            if module not in record["owners"]:
                record["owners"].append(module)
    if any(row["canonical"] not in expected for row in protected.values()):
        raise ValueError("Current source objects lack a protected literal")
    raw = bytearray(path.read_bytes())
    seen = set()
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for index, section in enumerate(elf.iter_sections()):
            if not section.name.startswith(PREFIX):
                if section["sh_flags"] & 0x22 == 0x22 and section["sh_size"]:
                    raise ValueError("Unsplit allocated shared string pool remains")
                continue
            row = expected.get(section.name)
            if (not row or section.name in seen or section["sh_flags"] != 0x32 or
                    section["sh_size"] != row["bytes"] or sha(section.data()) != row["sha256"] or
                    section["sh_entsize"] != 1 or section["sh_addralign"] != 1):
                raise ValueError("Partial linker changed a source string atom")
            seen.add(section.name)
            struct.pack_into(">I", raw, elf["e_shoff"] + index * elf["e_shentsize"] + 8, 2)
            struct.pack_into(">I", raw, elf["e_shoff"] + index * elf["e_shentsize"] + 36, 0)
    if seen != expected.keys():
        raise ValueError("Partial linker omitted source string atoms")
    path.write_bytes(raw)
    return expected


def verify_current(rows, atoms_proof):
    current = {row["name"]: row for row in rows if row["name"].startswith(PREFIX)}
    if current.keys() != atoms_proof.keys():
        raise ValueError("Current string atom inventory differs")
    for name, proof in atoms_proof.items():
        row = current[name]
        if (row["group"] or row["type"] != "SHT_PROGBITS" or row["flags"] != 2 or row["align"] != 1 or
                row["entry_size"] or any(row[k] != proof[k] for k in ("bytes", "sha256")) or
                not set(row["owners"]).issubset(proof["owners"])):
            raise ValueError("Current string atom source ownership differs")
        row["owners"] = sorted(proof["owners"])
        row["string_atom_verified"] = row["source_owned_verified"] = True


def load(ownership_path, source_path, timer_path, original, sources, key):
    receipt = json.loads(LAYOUT.read_text())
    if (receipt.get("version") != 1 or receipt.get("original_layout_sha256") != sha(ownership_path.read_bytes()) or
            receipt.get("source_ownership_sha256") != sha(source_path.read_bytes()) or
            receipt.get("timer_baseline_sha256") != sha(timer_path.read_bytes())):
        raise ValueError("String atom ownership does not match frozen baselines")
    entry = receipt["builds"][key]
    frozen = json.loads(timer_path.read_text())["builds"][key]
    protected = protected_rows(original, frozen)
    readers = {row["name"]: row for row in protected}
    pools = {row["name"]: row for row in original["sections"] if row["live"] and row["flags"] & 0x22 == 0x22}
    if ({row["name"] for row in entry["pools"]} != pools.keys() or
            any(entry[k] != original[k] for k in ("source_partial_sha256", "source_elf_sha256"))):
        raise ValueError("String atom pool identity differs")
    for pool in entry["pools"]:
        if any(value != pools[pool["name"]].get(key) for key, value in pool.items()):
            raise ValueError("String atom pool layout differs")
    atoms_proof = entry["protected_atoms"]
    sites = sorted([r["site"], r["type"], r["target"]] for atom in atoms_proof.values() for r in atom["references"])
    if (sites != entry["protected_reference_sites"] or len({site[0] for site in sites}) != len(sites)):
        raise ValueError("Protected string relocation inventory differs")
    for name, atom in atoms_proof.items():
        parent = atoms_proof.get(atom["canonical"])
        if (name != atom["name"] or name != PREFIX + atom["sha256"] or not parent or
                parent["canonical"] != parent["name"] or len(atom["sha256"]) != 64 or
                atom["bytes"] <= 0 or atom["canonical_offset"] < 0 or
                atom["address"] != parent["address"] + atom["canonical_offset"] or
                atom["canonical_offset"] + atom["bytes"] != parent["bytes"] or
                not any(row["address"] <= atom["address"] < atom["address"] + atom["bytes"] <= row["address"] + row["linked_bytes"] for row in entry["pools"]) or
                not atom["references"]):
            raise ValueError("Protected string atom bounds or suffix identity differs")
        for reference in atom["references"]:
            reader = readers.get(reference["reader"])
            if (not reader or reader["owners"] != [reference["owner"]] or
                    any(reference["reader_" + key] != reader[key] for key in ("address", "size", "sha256")) or
                    not reader["address"] <= reference["site"] < reader["address"] + reader["size"] or
                    reference["source_object_sha256"] != sources["original_object_sha256"].get(reference["owner"]) or
                    reference["source_section_index"] <= 0 or reference["source_atom_offset"] < 0 or
                    reference["type"] not in (1, 4, 5, 6) or not 0 <= reference["atom_offset"] < atom["bytes"] or
                    reference["target"] != atom["address"] + reference["atom_offset"]):
                raise ValueError("Protected string reference identity differs")
    return entry


def expand(baseline, entry):
    pools = {row["name"] for row in entry["pools"]}
    baseline["sections"] = [row for row in baseline["sections"] if row["name"] not in pools or row["group"]]
    baseline["string_atoms"] = entry
    kept = [row for row in entry["protected_atoms"].values() if row["canonical"] == row["name"]]
    retired = []
    for pool in entry["pools"]:
        cursor, end = pool["address"], pool["address"] + pool["linked_bytes"]
        for atom in sorted(kept, key=lambda row: row["address"]):
            if not pool["address"] <= atom["address"] < end:
                continue
            if atom["address"] < cursor:
                raise ValueError("Protected string canonical ranges overlap")
            if cursor < atom["address"]:
                retired.append({"begin": cursor, "end": atom["address"], "name": pool["name"]})
            cursor = atom["address"] + atom["bytes"]
        if cursor < end:
            retired.append({"begin": cursor, "end": end, "name": pool["name"]})
    baseline["retired_string_ranges"] = retired
    for atom in kept:
        baseline["sections"].append({"name": atom["name"], "group": "", "address": atom["address"],
            "bytes": atom["bytes"], "linked_bytes": atom["bytes"], "sha256": atom["sha256"],
            "type": "SHT_PROGBITS", "flags": 2, "align": 1, "entry_size": 0,
            "owners": sorted({r["owner"] for r in atom["references"]}), "live": True, "cold": False,
            "protected_string": True, "definition_count": 1, "single_symbol": symbol_name(atom["name"])})


def verify_linked(sections, entry):
    import link_pinned_mod as pinned
    for atom in entry["protected_atoms"].values():
        if sha(pinned.range_bytes(sections, atom["address"], atom["bytes"])) != atom["sha256"]:
            raise ValueError("Protected string literal bytes or address changed")
        grouped = defaultdict(list)
        for reference in atom["references"]:
            grouped[reference["target"]].append(reference)
        for target, references in grouped.items():
            if decode_target(references, sections) != target:
                raise ValueError("Protected string reference target changed")
    return len(entry["protected_atoms"])


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=LAYOUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.verify:
        parser.error("String atom capture is create-only")
    result = capture()
    if args.verify:
        if result != json.loads(args.output.read_text()):
            raise ValueError("Frozen string atom evidence does not reproduce")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, separators=(",", ":"))
            stream.write("\n")
    print(json.dumps({key: len(row["protected_atoms"]) for key, row in result["builds"].items()}))


if __name__ == "__main__":
    main()
