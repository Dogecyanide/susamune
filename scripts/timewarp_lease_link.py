"""Retain the unwired lease API in a private pinned link; never replace normal outputs."""
import argparse
import hashlib
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
import link_pinned_mod as pinned

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-lease-link")
    parser.add_argument("--targets", nargs="+", choices=("console", "emu"), default=["console", "emu"])
    parser.add_argument("--regions", nargs="+", choices=("jp", "us", "pal"), default=["jp", "us", "pal"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"scope": "Private retention of every production lease API; no consumer calls, boot, ARM installation or Wii runtime proof", "builds": {}}
    for target in args.targets:
        source = ROOT / f"build/timewarp-lease-{target}"
        for region in args.regions:
            obj = source / f"susamune_pre_{region}.o"
            with obj.open("rb") as stream:
                elf = ELFFile(stream)
                roots = sorted(s.name for s in elf.get_section_by_name(".symtab").iter_symbols()
                    if s["st_info"]["bind"] == "STB_GLOBAL" and s["st_info"]["type"] == "STT_FUNC"
                    and "__13TransferLeaseF" in s.name and isinstance(s["st_shndx"], int))
            if len(roots) != 13:
                raise ValueError(f"Expected the 13 public lease functions, found {roots}")
            folder = args.output / f"{target}-{region}"
            folder.mkdir(parents=True, exist_ok=True)
            options = argparse.Namespace(obj=obj, objects=source, ownership=pinned.LAYOUT,
                kuribo_home=ROOT / "toolchain", vers=region, target=target, work=folder / "link",
                elf=folder / f"susamune_{region}.o", out=folder / "manifest.json", root=roots)
            pinned.build(options)
            receipt = json.loads((options.work / "receipt.json").read_text())
            lease = [row for row in receipt["allocations"] if "transfer_lease.cpp" in row["owners"]]
            if not lease or any(row["owners"] != ["transfer_lease.cpp"] for row in lease):
                raise ValueError("Lease allocation ownership is missing or mixed")
            with options.elf.open("rb") as stream:
                elf = ELFFile(stream)
                sections = list(elf.iter_sections())
                totals = {"code": 0, "rodata": 0, "data": 0, "bss": 0}
                for row in lease:
                    section = next(s for s in sections if s["sh_addr"] == row["address"] and s["sh_flags"] & 2)
                    kind = "bss" if section["sh_type"] == "SHT_NOBITS" else (
                        "code" if section["sh_flags"] & 4 else "data" if section["sh_flags"] & 1 else "rodata")
                    totals[kind] += row["linked_bytes"]
            report["builds"][f"{target}-{region}"] = {"roots": roots, "lease_bytes": totals,
                "lease_allocations": lease, "total_new_source_bytes": receipt["new_source_bytes"],
                "remaining_recovered_bytes": receipt["recovered_bytes_remaining"],
                "timer": receipt["protection"], "receipt": str(options.work / "receipt.json"),
                "receipt_sha256": sha(options.work / "receipt.json")}
            print(f"{target}-{region}: lease {totals}, remaining {receipt['recovered_bytes_remaining']}", flush=True)
    report["sources"] = {str(path.relative_to(ROOT)): sha(path) for path in (
        ROOT / "src/transfer_lease.cpp", ROOT / "include/susamune/transfer_lease.hxx",
        ROOT / "include/susamune/transfer_lease.h", ROOT / "include/susamune/transfer_publication.h",
        ROOT / "scripts/timewarp_lease_link.py")}
    (args.output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
