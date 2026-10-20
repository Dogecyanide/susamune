"""Reproduce ownership of anonymous menu constants from the frozen source ELF."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from elftools.elf.elffile import ELFFile

STRING = re.compile(r"\.rodata\.\.Lstr\.\d+\Z")
TABLE = re.compile(r"\.data\.rel\.ro\.\.Lswitch\.table\.(rowHelp__11CreationTabCFi|selectionHelp__9GhostsTabCFv)(?:\.\d+)?\Z")
ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "doc/timewarp-pinned-menu-constants.json"
IDENTITY = ("name", "type", "flags", "align", "bytes", "sha256", "address", "linked_bytes")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlaps(begin, size, protected):
    return any(begin < p["address"] + p["size"] and p["address"] < begin + size for p in protected)


def verify_candidate(old, facts):
    """Accept only local strings or the two audited string-lookup table kinds."""
    table = TABLE.fullmatch(old["name"])
    string = STRING.fullmatch(old["name"])
    if (not old["live"] or not (table or string) or old["group"] or old.get("cold") or
            old["type"] != "SHT_PROGBITS" or old["flags"] != (3 if table else 2) or
            old.get("definition_count") != 0 or old.get("owners") or not old["bytes"]):
        raise ValueError("Not an anonymous immutable menu constant")
    if (facts["source_matches"] != 1 or facts["source_definitions"] or
            not facts["source_payload_identical"]):
        raise ValueError("Anonymous menu source ownership is ambiguous")
    incoming = facts["incoming"]
    if (not incoming or any(r["owners"] != ["menu.cpp"] or r["definition_count"] != 1 or
            r["flags"] not in (6, 0x206) or not r["single_symbol"] or
            r["type"] not in (4, 6) or r["target_offset"] != 0 or
            table and r["single_symbol"] != table[1] for r in incoming)):
        raise ValueError("Anonymous menu constant has an unproven reader")
    if facts["protected_overlap"] or facts["protected_references"] or facts["protected_reader"]:
        raise ValueError("Anonymous menu constant touches protected code or storage")
    data = facts["data"]
    outgoing = facts["outgoing"]
    if len(data) != old["bytes"] or sha(data) != old["sha256"]:
        raise ValueError("Anonymous menu constant payload differs from its frozen identity")
    if string:
        if outgoing or not data or data[-1] or b"\0" not in data:
            raise ValueError("Anonymous menu string is not immutable text")
        head, tail = data.split(b"\0", 1)
        if not head or any(tail):
            raise ValueError("Anonymous menu string contains non-padding data")
    elif (old["bytes"] % 4 or any(data) or len(outgoing) != old["bytes"] // 4 or
            sorted(r["offset"] for r in outgoing) != list(range(0, old["bytes"], 4)) or
            any(r["type"] != 1 or not r["readonly_string_target"] for r in outgoing)):
        raise ValueError("Anonymous menu table is not a complete readonly string lookup")
    return {
        "kind": "string_lookup" if table else "padded_string",
        "owner": "menu.cpp", "source_object_sha256": facts["source_object_sha256"],
        "source_section_index": facts["source_section_index"],
        "partial_sha256": facts["partial_sha256"], "linked_sha256": facts["linked_sha256"],
        **{k: old[k] for k in IDENTITY},
        "readers": sorted({r["single_symbol"] for r in incoming}),
        "reader_sections": sorted({r["source"] for r in incoming}),
        "incoming_relocations": len(incoming), "pointer_entries": len(outgoing),
        "protected_references": 0, "protected_overlap": False,
    }


def certify(original, partial, image, menu_object, expected_object_sha, protected):
    partial_sha, image_sha, object_sha = (sha(p.read_bytes()) for p in (partial, image, menu_object))
    if (partial_sha != original["source_partial_sha256"] or image_sha != original["source_elf_sha256"] or
            object_sha != expected_object_sha):
        raise ValueError("Immutable menu ownership baseline differs")
    by_index = {r["index"]: r for r in original["sections"]}
    proofs = {}
    with partial.open("rb") as partial_file, menu_object.open("rb") as source_file:
        elf, source = ELFFile(partial_file), ELFFile(source_file)
        symbols = elf.get_section_by_name(".symtab")
        source_symbols = list(source.get_section_by_name(".symtab").iter_symbols())
        source_sections = defaultdict(list)
        for index, section in enumerate(source.iter_sections()):
            source_sections[section.name].append((index, section))
        incoming, outgoing = defaultdict(list), defaultdict(list)
        for section in elf.iter_sections():
            if section["sh_type"] != "SHT_RELA":
                continue
            for relocation in section.iter_relocations():
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                target = symbol["st_shndx"]
                item = {"offset": relocation["r_offset"], "type": relocation["r_info_type"],
                        "target_offset": symbol["st_value"] + relocation["r_addend"], "target": target,
                        "source": section["sh_info"]}
                incoming[target].append(item)
                outgoing[section["sh_info"]].append(item)
        for old in original["sections"]:
            if not old["live"] or not (STRING.fullmatch(old["name"]) or TABLE.fullmatch(old["name"])):
                continue
            matches = source_sections[old["name"]]
            if len(matches) != 1:
                continue
            source_index, source_section = matches[0]
            section = elf.get_section(old["index"])
            readers = []
            for relocation in incoming[old["index"]]:
                reader = by_index.get(relocation["source"], {})
                readers.append({**relocation, "owners": reader.get("owners"),
                                "definition_count": reader.get("definition_count"),
                                "flags": reader.get("flags"), "single_symbol": reader.get("single_symbol")})
            pointers = []
            for relocation in outgoing[old["index"]]:
                valid = False
                if isinstance(relocation["target"], int):
                    target = elf.get_section(relocation["target"])
                    offset = relocation["target_offset"]
                    valid = (target["sh_type"] == "SHT_PROGBITS" and target["sh_flags"] in (2, 0x12, 0x32) and
                             (target.name.startswith(".rodata.str") or STRING.fullmatch(target.name)) and
                             0 <= offset < target["sh_size"] and b"\0" in target.data()[offset:])
                pointers.append({**relocation, "readonly_string_target": valid})
            facts = {
                "source_matches": len(matches), "source_section_index": source_index,
                "source_definitions": [s.name for s in source_symbols if s["st_shndx"] == source_index and
                                       (s.name or s["st_size"] or s["st_info"]["type"] != "STT_SECTION")],
                "source_payload_identical": section.name == old["name"] and
                    all(source_section[k] == section[k] for k in ("sh_type", "sh_flags", "sh_size", "sh_addralign")) and
                    source_section.data() == section.data() and sha(section.data()) == old["sha256"] and
                    section["sh_flags"] == old["flags"] and section["sh_size"] == old["bytes"] and
                    max(1, section["sh_addralign"]) == old["align"],
                "source_object_sha256": object_sha, "partial_sha256": partial_sha, "linked_sha256": image_sha,
                "incoming": readers, "outgoing": pointers, "data": section.data(),
                "protected_overlap": overlaps(old["address"], old["linked_bytes"], protected),
                "protected_reader": any(overlaps(by_index[r["source"]]["address"],
                    by_index[r["source"]]["linked_bytes"], protected) for r in readers if r["source"] in by_index),
                "protected_references": any(overlaps(by_index[r["source"]]["address"] + r["offset"], 1,
                    protected) for r in readers if r["source"] in by_index and by_index[r["source"]]["live"]),
            }
            try:
                proofs[old["name"]] = verify_candidate(old, facts)
            except ValueError:
                # Other anonymous data retains the ordinary fixed-input rule.
                continue
    return proofs


def capture():
    import link_pinned_mod as pinned
    import pinned_source_sections as owned
    import timewarp_timer_guard as timer
    original = json.loads(pinned.LAYOUT.read_text())
    sources = json.loads(owned.LAYOUT.read_text())
    frozen = json.loads(timer.BASELINE.read_text())
    result = {"version": 1, "original_layout_sha256": sha(pinned.LAYOUT.read_bytes()),
              "source_ownership_sha256": sha(owned.LAYOUT.read_bytes()),
              "timer_baseline_sha256": sha(timer.BASELINE.read_bytes()), "builds": {},
              "scope": "Anonymous menu text and string lookup provenance only; no payloads or mutable storage."}
    for key, baseline in original["builds"].items():
        target, region = key.split("-")
        root = ROOT / f"build/baseline-{target}"
        protected = list(frozen["builds"][key]["symbols"].values()) + baseline["anchors"]
        result["builds"][key] = certify(baseline, root / f"susamune_pre_{region}.o",
            root / f"susamune_{region}.o", root / f"CMakeFiles/susamune_obj_{region}.dir/src/menu.cpp.obj",
            sources["builds"][key]["original_object_sha256"]["menu.cpp"], protected)
    return result


def validate(receipt, original, source, protected):
    """Validate capture facts against the existing frozen receipts, without ELF files."""
    by_name = {r["name"]: r for r in original["sections"] if not r["group"]}
    by_index = {r["index"]: r for r in original["sections"]}
    result = {}
    for name, proof in receipt.items():
        old = by_name.get(name)
        table, string = TABLE.fullmatch(name), STRING.fullmatch(name)
        if (not old or not old["live"] or old.get("cold") or old.get("owners") or
                old.get("definition_count") != 0 or not (table or string) or
                old["type"] != "SHT_PROGBITS" or old["flags"] != (3 if table else 2) or
                not old["bytes"] or any(proof.get(k) != old[k] for k in IDENTITY) or
                proof.get("kind") != ("string_lookup" if table else "padded_string") or
                proof.get("owner") != "menu.cpp" or
                proof.get("source_object_sha256") != source["original_object_sha256"]["menu.cpp"] or
                proof.get("partial_sha256") != original["source_partial_sha256"] or
                proof.get("linked_sha256") != original["source_elf_sha256"] or
                not isinstance(proof.get("source_section_index"), int) or proof["source_section_index"] <= 0):
            raise ValueError("Immutable menu ownership identity differs: " + name)
        readers = [by_index.get(index) for index in proof.get("reader_sections", [])]
        if (not readers or any(not r or r.get("owners") != ["menu.cpp"] or
                r.get("definition_count") != 1 or r["flags"] not in (6, 0x206) or
                not r.get("single_symbol") or table and r["single_symbol"] != table[1] or
                overlaps(r["address"], r["linked_bytes"], protected) for r in readers) or
                proof.get("readers") != sorted({r["single_symbol"] for r in readers}) or
                proof.get("incoming_relocations", 0) < len(readers) or
                proof.get("pointer_entries") != (old["bytes"] // 4 if table else 0) or
                table and old["bytes"] % 4 or proof.get("protected_references") != 0 or
                proof.get("protected_overlap") is not False or
                overlaps(old["address"], old["linked_bytes"], protected)):
            raise ValueError("Immutable menu ownership protection differs: " + name)
        result[name] = deepcopy(proof)
    return result


def load(path, ownership_path, source_path, timer_path, original, source, key):
    receipt = json.loads(path.read_text())
    if (receipt.get("version") != 1 or
            receipt.get("original_layout_sha256") != sha(ownership_path.read_bytes()) or
            receipt.get("source_ownership_sha256") != sha(source_path.read_bytes()) or
            receipt.get("timer_baseline_sha256") != sha(timer_path.read_bytes())):
        raise ValueError("Immutable menu ownership does not match the frozen baselines")
    frozen = json.loads(timer_path.read_text())
    protected = list(frozen["builds"][key]["symbols"].values()) + original["anchors"]
    return validate(receipt["builds"][key], original, source, protected)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=LAYOUT)
    parser.add_argument("--verify", action="store_true", help="Reproduce the receipt from hash-locked baseline ELF artifacts")
    args = parser.parse_args()
    if not args.verify and args.output.exists():
        parser.error("Immutable menu ownership capture is create-only")
    receipt = capture()
    if args.verify:
        if receipt != json.loads(args.output.read_text()):
            raise ValueError("Immutable menu ownership evidence does not reproduce")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, separators=(",", ":"))
            stream.write("\n")
    print(json.dumps({key: len(rows) for key, rows in receipt["builds"].items()}))


if __name__ == "__main__":
    main()
