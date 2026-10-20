"""Certify current compiler jump tables owned by one audited source function."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import struct

from elftools.elf.elffile import ELFFile


NEW_READERS = {"game_wireframe.cpp": {"edgeVertices__21GameWireframeGeometryFUiUi"}}
NON_COMDAT_READERS = {"metadata_display.cpp": {
    "menuRowValue__15MetadataDisplayCFi", "adjustMenuRow__15MetadataDisplayFii",
}}
STRING_READERS = {"metadata_display.cpp": {"menuRowName__15MetadataDisplayFi"}}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def overlaps(row, protected):
    return row.get("live", False) and any(
        row["address"] < item["address"] + item["size"] and
        item["address"] < row["address"] + row["linked_bytes"] for item in protected)


def catalog(path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        symbol_table = elf.get_section_by_name(".symtab")
        symbols = [{"name": symbol.name, "section": symbol["st_shndx"], "value": symbol["st_value"],
                    "size": symbol["st_size"], "bind": symbol["st_info"]["bind"],
                    "type": symbol["st_info"]["type"], "visibility": symbol["st_other"]["visibility"]}
                   for symbol in symbol_table.iter_symbols()]
        sections, groups, definitions = {}, defaultdict(list), defaultdict(list)
        incoming, outgoing = defaultdict(list), defaultdict(list)
        for symbol in symbols:
            if symbol["name"] or symbol["size"] or symbol["type"] != "STT_SECTION":
                definitions[symbol["section"]].append(symbol)
        for index, section in enumerate(elf.iter_sections()):
            sections[index] = {"name": section.name, **dict(section.header),
                               "data": section.data() if section["sh_flags"] & 2 and
                               section["sh_type"] == "SHT_PROGBITS" else b""}
            if section["sh_type"] == "SHT_GROUP":
                words = struct.unpack(">" + str(section["sh_size"] // 4) + "I", section.data())
                groups[symbols[section["sh_info"]]["name"]].append(words)
            elif section["sh_type"] == "SHT_REL":
                raise ValueError("Menu jump-table proof requires explicit addends")
            elif section["sh_type"] == "SHT_RELA":
                for relocation in section.iter_relocations():
                    symbol = symbols[relocation["r_info_sym"]]
                    record = {"offset": relocation["r_offset"], "type": relocation["r_info_type"],
                              "target_offset": symbol["value"] + relocation["r_addend"],
                              "source": section["sh_info"], "target": symbol["section"]}
                    incoming[symbol["section"]].append(record)
                    outgoing[section["sh_info"]].append(record)
        return sections, groups, definitions, incoming, outgoing


def inspect(path, name, signature, parsed=None, *, comdat=True, string_table=False):
    sections, groups, definitions, all_incoming, all_outgoing = parsed or catalog(path)
    if comdat:
        selected = groups.get(signature, [])
        if len(selected) != 1 or selected[0][0] != 1:
            raise ValueError("Menu jump table requires one COMDAT group")
        allocated = [(index, sections[index]) for index in selected[0][1:] if sections[index]["sh_flags"] & 2]
    else:
        allocated = [(index, section) for index, section in sections.items()
                     if section["name"] in (name, ".text." + signature)]
    if len(allocated) != 2 or sum(section["name"] == name for _, section in allocated) != 1:
        raise ValueError("Menu jump-table group has other allocated storage")
    table_index, table = next((index, section) for index, section in allocated if section["name"] == name)
    function_index, function = next((index, section) for index, section in allocated if section["name"] != name)
    prefix = ".data.rel.ro..Lswitch.table." if string_table else ".rodata."
    if (string_table and comdat or name != prefix + signature or table["sh_type"] != "SHT_PROGBITS" or
            table["sh_flags"] != (3 if string_table else 0x202 if comdat else 2) or table["sh_addralign"] != 4 or table["sh_entsize"] or
            not table["sh_size"] or table["sh_size"] % 4 or any(table["data"]) or definitions[table_index] or
            function["sh_type"] != "SHT_PROGBITS" or function["sh_flags"] != (0x206 if comdat else 6) or
            function["sh_addralign"] != 4 or len(definitions[function_index]) != 1):
        raise ValueError("Menu jump-table or reader shape is not immutable and unique")
    definition = definitions[function_index][0]
    if (definition["name"] != signature or definition["bind"] != ("STB_WEAK" if comdat else "STB_GLOBAL") or
            definition["type"] != "STT_FUNC" or definition["value"] or
            definition["size"] != function["sh_size"] or definition["visibility"] != "STV_DEFAULT"):
        raise ValueError("Menu jump-table reader is not one complete function with its audited binding")
    incoming, outgoing = all_incoming[table_index], all_outgoing[table_index]
    if any(row["source"] != function_index for row in incoming):
        raise ValueError("Menu jump table has an external reader")
    if not string_table and any(row["target"] != function_index for row in outgoing):
        raise ValueError("Menu jump table targets another function or storage")
    targets = []
    if string_table:
        for row in sorted(outgoing, key=lambda row: row["offset"]):
            target = sections.get(row["target"])
            if (not target or target["sh_type"] != "SHT_PROGBITS" or
                    (target["sh_flags"], target["sh_entsize"]) not in ((0x32, 1), (2, 0)) or
                    row["target_offset"] or not target["data"] or
                    target["data"].find(b"\0") != len(target["data"]) - 1 or
                    target["name"] != ".twp.string." + sha(target["data"])):
                raise ValueError("Menu string table target is not one immutable string atom")
            targets.append({"offset": row["offset"], "name": target["name"],
                            "bytes": target["sh_size"], "sha256": sha(target["data"])})
    normalize = lambda rows: sorted(({key: row[key] for key in ("offset", "type", "target_offset")}
                                     for row in rows), key=lambda row: row["offset"])
    facts = {"name": name, "signature": signature, "bytes": table["sh_size"],
             "flags": table["sh_flags"], "align": table["sh_addralign"], "sha256": sha(table["data"]),
             "reader_bytes": function["sh_size"], "reader_sha256": sha(function["data"]),
             "incoming": normalize(incoming), "outgoing": normalize(outgoing)}
    verify_references(facts)
    if string_table:
        facts["string_targets"] = targets
    return facts


def verify_references(facts):
    incoming, outgoing = facts["incoming"], facts["outgoing"]
    halves = defaultdict(set)
    for row in incoming:
        if (row["type"] not in (4, 5, 6) or row["offset"] % 4 != 2 or
                not 0 <= row["offset"] < facts["reader_bytes"] - 1 or
                row["target_offset"] % 4 or not 0 <= row["target_offset"] < facts["bytes"]):
            raise ValueError("Menu jump-table reader has an unsupported relocation")
        halves[row["target_offset"]].add(row["type"])
    if not halves or any(4 not in types or not types & {5, 6} for types in halves.values()):
        raise ValueError("Menu jump-table reader lacks complete address halves")
    if (len(outgoing) != facts["bytes"] // 4 or
            [row["offset"] for row in outgoing] != list(range(0, facts["bytes"], 4)) or
            any(row["type"] != 1 or row["target_offset"] % 4 or
                not 0 <= row["target_offset"] < facts["reader_bytes"] for row in outgoing)):
        raise ValueError("Menu jump table is not a complete set of interior self targets")


def validate_all(rows, partial, object_build, region, protected, baseline):
    frozen = {(row["name"], row["group"]): row for row in baseline["sections"]}
    proofs = {}
    partial_catalog, source_catalogs = catalog(partial), {}
    for row in rows:
        comdat = bool(row["group"])
        string_table = row["name"].startswith(".data.rel.ro..Lswitch.table.")
        prefix = ".data.rel.ro..Lswitch.table." if string_table else ".rodata."
        signature = row["group"] if comdat else row["name"].removeprefix(prefix)
        if row["name"] != prefix + signature:
            continue
        readers = [candidate for candidate in rows if candidate["group"] == row["group"] and
                   candidate["flags"] == (0x206 if comdat else 6) and len(candidate["definitions"]) == 1 and
                   candidate["definitions"][0]["name"] == signature]
        if len(readers) != 1 or len(readers[0]["owners"]) != 1:
            continue
        reader = readers[0]
        owner = reader["owners"][0]
        approved = STRING_READERS if string_table else NON_COMDAT_READERS
        if (string_table and comdat or not comdat and signature not in approved.get(owner, set()) or
                comdat and owner != "menu.cpp" and signature not in NEW_READERS.get(owner, set())):
            continue
        old_reader = frozen.get((reader["name"], row["group"]))
        table_flags = 3 if string_table else 0x202 if comdat else 2
        if (row["definitions"] or row["owners"] or row["flags"] != table_flags or
                row["type"] != "SHT_PROGBITS" or len(reader["definitions"]) != 1 or
                reader["definitions"][0]["name"] != signature):
            raise ValueError("Current menu jump-table ownership is ambiguous")
        old = frozen.get((row["name"], row["group"]))
        if comdat and owner != "menu.cpp" and (old or old_reader):
            raise ValueError("New audited jump-table identity already exists in the frozen layout")
        if (old and (not old_reader or old["flags"] != table_flags or old["type"] != "SHT_PROGBITS" or
                old.get("definition_count") != 0 or old["owners"] or overlaps(old, protected)) or
                old_reader and (old_reader["owners"] != [owner] or
                old_reader.get("single_symbol") != signature or overlaps(old_reader, protected))):
            raise ValueError("Frozen menu jump table or reader touches protected or unknown ownership")
        actual = inspect(partial, row["name"], signature, partial_catalog, comdat=comdat, string_table=string_table)
        source = object_build / f"CMakeFiles/susamune_obj_{region}.dir/src/{owner}.obj"
        if owner not in source_catalogs:
            source_catalogs[owner] = catalog(source)
        original = inspect(source, row["name"], signature, source_catalogs[owner], comdat=comdat, string_table=string_table)
        if actual != original or any(actual[key] != row[key] for key in ("bytes", "flags", "align", "sha256")):
            raise ValueError("Menu jump table differs from its current source object")
        proofs[row["name"]] = {**actual, "owner": owner, "source_object_sha256": sha(source.read_bytes())}
    return proofs
