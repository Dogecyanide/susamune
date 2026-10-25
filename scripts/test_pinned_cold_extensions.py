"""Six-target source links and allocation accounting for additional cold editors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import gen_mod_bin
import link_pinned_mod as pinned
import pinned_cold_extensions as extensions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=pinned.ROOT / "build/timewarp-owned-snapshot-2")
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-cold-extension-builds")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not output.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Cold extension fixtures must remain in build")
    previous = json.loads((source / "receipt.json").read_text())
    if not previous["passed"] or len(previous["builds"]) != 6:
        raise ValueError("Complete six-target source baseline is required")
    result = {"passed": False, "source_receipt_sha256": pinned.file_sha(source / "receipt.json"), "builds": []}
    output.mkdir(parents=True, exist_ok=True)
    try:
        for before in previous["builds"]:
            target, region = before["target"], before["region"]
            build = source / target
            folder = output / (target + "-" + region)
            folder.mkdir(parents=True, exist_ok=True)
            arguments = argparse.Namespace(obj=build / f"susamune_pre_{region}.o", objects=build,
                ownership=pinned.LAYOUT, kuribo_home=pinned.ROOT / "toolchain", vers=region, target=target,
                work=folder / "link", elf=folder / "retained.elf", out=folder / "manifest.json", root=[])
            pinned.build(arguments)
            receipt_path = arguments.work / "receipt.json"
            receipt = json.loads(receipt_path.read_text())
            packed = gen_mod_bin.build_mod_bin(json.loads(arguments.out.read_text()), format_version=4, base_dir=folder)
            (folder / "mod.bin").write_bytes(packed)
            old = json.loads(Path(before["receipt"]).read_text())
            gross = sum(f["size"] for f in receipt["cold_extensions"])
            added = gross - sum(f["size"] for f in old.get("cold_extensions", []))
            extra_gates = 16 * (receipt["gateway_count"] - old["gateway_count"])
            extra_island = receipt["recovered_begin"] - old["recovered_begin"]
            actual = receipt["recovered_bytes_remaining"] - old["recovered_bytes_remaining"]
            if (added - extra_island != actual or not -32 < extra_island - extra_gates < 32
                    or len(receipt["cold_extensions"]) != sum(map(len, extensions.selectors(target).values()))):
                raise ValueError("Extension recovery differs from charged code and gateways")
            result["builds"].append({"target": target, "region": region,
                "remaining_before": old["recovered_bytes_remaining"], "remaining_after": receipt["recovered_bytes_remaining"],
                "editor_bytes": gross, "extra_gateway_bytes": extra_gates, "net_recovered": actual,
                "additional_editor_bytes": added,
                "extra_gateway_alignment": extra_island - extra_gates,
                "mod_bytes": len(packed), "cold_bytes": receipt["cold_image"]["size"],
                "protection": receipt["protection"], "relocations_verified": receipt["retained_relocation_sites_verified"],
                "receipt": str(receipt_path), "receipt_sha256": pinned.file_sha(receipt_path)})
            (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
        result["passed"] = True
    finally:
        (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "builds": [{k: r[k] for k in (
        "target", "region", "remaining_before", "remaining_after", "net_recovered", "mod_bytes")} for r in result["builds"]]}))


if __name__ == "__main__":
    main()
