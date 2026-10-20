"""Count actual retained local helper copies, without inferring inlined savings."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile
import link_pinned_mod as pinned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    groups = defaultdict(list)
    with args.elf.open("rb") as stream:
        elf = ELFFile(stream)
        module = ""
        for symbol in elf.get_section_by_name(".symtab").iter_symbols():
            if symbol["st_info"]["type"] == "STT_FILE":
                module = symbol.name
            if (symbol["st_info"]["type"] == "STT_FUNC" and symbol["st_info"]["bind"] == "STB_LOCAL"
                    and symbol["st_size"] and symbol.name.startswith(("TW", "StatePool", "StateSlotPool"))):
                groups[symbol.name].append({"module": module, "bytes": symbol["st_size"], "address": symbol["st_value"]})
    duplicates = [{"name": name, "copies": rows, "total_bytes": sum(r["bytes"] for r in rows),
                   "excess_over_largest_copy": sum(r["bytes"] for r in rows) - max(r["bytes"] for r in rows)}
                  for name, rows in groups.items() if len(rows) > 1]
    duplicates.sort(key=lambda r: -r["excess_over_largest_copy"])
    result = {"scope": "Actual linked out-of-line local copies only. This is a duplicate-byte inventory, not proven obtainable savings; inlined checks are excluded.",
              "elf_sha256": pinned.file_sha(args.elf), "duplicates": duplicates,
              "excess_bytes": sum(r["excess_over_largest_copy"] for r in duplicates)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
