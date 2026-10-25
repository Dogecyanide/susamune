"""Conservative linked MEM1 charge for retaining every public StateStore API."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile
import link_pinned_mod as pinned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=pinned.ROOT / "build/timewarp-owned-snapshot-2/console")
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-store-link-budget")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not output.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Budget output must stay inside build")
    output.mkdir(parents=True, exist_ok=True)
    path = source / "CMakeFiles/susamune_obj_pal.dir/src/state_store.cpp.obj"
    with path.open("rb") as stream:
        roots = sorted(s.name for s in ELFFile(stream).get_section_by_name(".symtab").iter_symbols()
                       if s["st_info"]["bind"] == "STB_GLOBAL" and s["st_info"]["type"] == "STT_FUNC"
                       and s["st_size"] and "__10StateStore" in s.name)
    if not roots:
        raise ValueError("StateStore public source functions missing")
    arguments = argparse.Namespace(obj=source / "susamune_pre_pal.o", objects=source,
        ownership=pinned.LAYOUT, kuribo_home=pinned.ROOT / "toolchain", vers="pal", target="console",
        work=output / "link", elf=output / "retained.elf", out=output / "manifest.json", root=roots)
    pinned.build(arguments)
    receipt = json.loads((arguments.work / "receipt.json").read_text())
    before = json.loads((pinned.ROOT / "build/timewarp-cold-extension-builds/console-pal/link/receipt.json").read_text())
    result = {"passed": True, "scope": "Conservative source-retention budget: all public StateStore functions forced live. Integration caller/context cost is not included.",
              "source_object_sha256": pinned.file_sha(path), "root_count": len(roots), "roots": roots,
              "remaining_before": before["recovered_bytes_remaining"], "remaining_after": receipt["recovered_bytes_remaining"],
              "additional_linked_bytes": before["recovered_bytes_remaining"] - receipt["recovered_bytes_remaining"],
              "protection": receipt["protection"], "receipt_sha256": pinned.file_sha(arguments.work / "receipt.json")}
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "roots"}))


if __name__ == "__main__":
    main()
