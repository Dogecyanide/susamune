"""Prove numeric pools have no relocations from protected source bytes."""
from __future__ import annotations

from elftools.elf.elffile import ELFFile


def protected_site(site, protected):
    return any(site < row["address"] + row["size"] and row["address"] < site + 4
               for row in protected)


def frozen_references(partial, baseline, protected):
    # Frozen images omit relocations; only the partial object proves absence.
    rows = {row["index"]: row for row in baseline["sections"]}
    pools = {index: row for index, row in rows.items()
             if row["live"] and row["flags"] == 0x12 and not row["group"]}
    result = {row["name"]: [] for row in pools.values()}
    if len(result) != len(pools):
        raise ValueError("Ambiguous frozen numeric pool identity")
    with partial.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name(".symtab")
        for section in elf.iter_sections():
            if section["sh_type"] not in ("SHT_REL", "SHT_RELA"):
                continue
            source = rows.get(section["sh_info"])
            if not source or not source["live"]:
                continue
            if section["sh_type"] != "SHT_RELA":
                raise ValueError("Protected numeric audit requires explicit relocation addends")
            for relocation in section.iter_relocations():
                site = source["address"] + relocation["r_offset"]
                if not protected_site(site, protected):
                    continue
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                target = symbol["st_shndx"]
                offset = symbol["st_value"] + relocation["r_addend"]
                selected = ([pools[target]] if target in pools else
                            [row for row in pools.values() if target == "SHN_ABS" and
                             row["address"] <= offset <= row["address"] + row["linked_bytes"]])
                for pool in selected:
                    # Conservatively keep all references to the pool, including aliases,
                    # interior offsets and one-past addresses used as range endpoints.
                    result[pool["name"]].append({"site": site, "type": relocation["r_info_type"],
                        "target_section": pool["index"], "target_offset": offset})
    return {name: sorted(references, key=lambda row: (row["site"], row["type"], row["target_offset"]))
            for name, references in result.items()}


def verify_current(rows, symbols, relocations, protected):
    """Run after section planning; final byte guards still check all protected code."""
    by_index = {row["index"]: row for row in rows}
    pools = {index: row for index, row in by_index.items()
             if row["live"] and (row["flags"] == 0x12 or row.get("source_owned_numeric"))}
    checked = 0
    for relocation in relocations:
        source = by_index.get(relocation["section"])
        if not source or not source["live"]:
            continue
        site = source["analysis_address"] + relocation["offset"]
        if not protected_site(site, protected):
            continue
        checked += 1
        symbol = symbols[relocation["symbol"]]
        offset = symbol["value"] + relocation["addend"]
        if (symbol["section"] in pools or symbol["section"] == "SHN_ABS" and
                any(row["analysis_address"] <= offset <= row["analysis_address"] + row["linked_bytes"]
                    for row in pools.values())):
            raise ValueError("Protected source now references a relocatable numeric pool")
    return checked
