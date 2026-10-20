"""Actual numeric-pool growth, immutable protection evidence, and fixed hook gates."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import link_pinned_mod as pinned
import pinned_source_sections as owned
import test_pinned_source_build as fixture
import timewarp_timer_guard as timer


def rejects(call, expected):
    try:
        call()
    except ValueError as error:
        if expected not in str(error):
            raise
        return str(error)
    raise AssertionError("Expected rejection: " + expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=pinned.ROOT / "build/timewarp-owned-snapshot-2/console")
    parser.add_argument("--snapshot", type=Path, default=pinned.ROOT / "build/timewarp-owned-source-snapshot-2")
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-numeric-tests")
    args = parser.parse_args()
    folder, source = args.output.resolve(), args.source.resolve()
    if not folder.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Tests must stay in the build directory")
    folder.mkdir(parents=True, exist_ok=True)
    result = {"passed": False, "negative": {}}
    numeric = json.loads(owned.NUMERIC_LAYOUT.read_text())
    if owned.capture_numeric_pools() != numeric:
        raise ValueError("Stored numeric-pool evidence does not reproduce from immutable originals")
    result["all_six_numeric_inventories_reproduced"] = True
    ownership = json.loads(pinned.LAYOUT.read_text())
    original_path = owned.NUMERIC_LAYOUT
    for label in ("baseline_binding", "missing_pool", "address", "contradictory_protection"):
        altered = deepcopy(numeric)
        pools = altered["builds"]["console-pal"]
        expected = "Numeric pool protection evidence"
        if label == "baseline_binding":
            altered["original_layout_sha256"] = "0" * 64
            expected = "Numeric pools do not match"
        elif label == "missing_pool":
            pools.pop(".rodata.cst4")
            expected = "Numeric pool inventory differs"
        elif label == "address":
            pools[".rodata.cst4"]["address"] += 4
        else:
            pools[".rodata.cst4"]["protected_range_overlap"] = True
        path = folder / (label + ".json")
        path.write_text(json.dumps(altered))
        owned.NUMERIC_LAYOUT = path
        try:
            result["negative"][label] = rejects(lambda: owned.expand_layout(
                owned.LAYOUT, pinned.LAYOUT, ownership, "console", "pal", timer.BASELINE), expected)
        finally:
            owned.NUMERIC_LAYOUT = original_path
    positive = folder / "numeric-growth"
    fixture.prepare(source, positive, "pal")
    text = (args.snapshot / "src/ghost.cpp").read_text()
    text += '\n#pragma clang section text=""\nextern "C" float twp_numeric_fixture() { return 1.35791113f; }\n'
    fixture.compile_copy(source, positive, "pal", "ghost.cpp", text)
    arguments = argparse.Namespace(obj=fixture.partial(positive, "pal"), objects=positive,
        ownership=pinned.LAYOUT, kuribo_home=pinned.ROOT / "toolchain", vers="pal", target="console",
        work=positive / "link", elf=positive / "retained.elf", out=positive / "manifest.json",
        root=["twp_numeric_fixture"])
    pinned.build(arguments)
    receipt = json.loads((positive / "link/receipt.json").read_text())
    if ".rodata.cst4" not in receipt["changed_unprotected_numeric_pools"]:
        raise AssertionError("Actual numeric growth was not exercised")
    sections = pinned.flat_sections(arguments.elf)
    symbols = pinned.symbols_from(arguments.elf)
    if not receipt["fixed_hook_entries"]:
        raise AssertionError("Captured onUpdate growth did not exercise a fixed hook entry")
    broken = deepcopy(sections)
    gate = receipt["fixed_hook_entries"][0]
    selected = next(s for s in broken.values() if s["address"] <= gate["address"] < s["address"] + s["size"])
    data = bytearray(selected["data"])
    data[gate["address"] - selected["address"] + 3] ^= 4
    selected["data"] = bytes(data)
    result["negative"]["changed_hook_gate"] = rejects(lambda: pinned.hook_symbols(symbols,
        receipt["fixed_hook_entries"], broken), "Fixed hook entry does not reach")
    result["positive"] = {k: receipt[k] for k in ("protection", "changed_unprotected_numeric_pools",
        "fixed_hook_entries", "fixed_hook_entry_bytes", "retained_relocation_sites_verified", "recovered_bytes_remaining")}
    result["passed"] = True
    (folder / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["positive"]))


if __name__ == "__main__":
    main()
