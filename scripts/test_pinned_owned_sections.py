"""Real compiled growth and rejection checks for source-owned pinned linking."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import link_pinned_mod as pinned
import pinned_source_sections as owned
import test_pinned_source_build as fixture
import timewarp_timer_guard as timer


def rejects(call, message):
    try:
        call()
    except ValueError as error:
        if message not in str(error):
            raise
        return {"rejected": True, "reason": str(error)}
    raise AssertionError("Expected rejection: " + message)


def invoke(folder, source, module, source_text, expected):
    fixture.prepare(source, folder, "pal")
    fixture.compile_copy(source, folder, "pal", module, source_text)
    return fixture.invoke(folder, "pal", "console", expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=pinned.ROOT / "build/timewarp-stream-console")
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-owned-tests")
    parser.add_argument("--snapshot", type=Path, default=pinned.ROOT)
    args = parser.parse_args()
    source, folder = args.source.resolve(), args.output.resolve()
    if not folder.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Test outputs must remain in the build directory")
    folder.mkdir(parents=True, exist_ok=True)
    before = pinned.file_sha(pinned.ROOT / "src/qft_timer.cpp")
    result = {"passed": False, "negative": {}}
    frozen = json.loads(pinned.LAYOUT.read_text())
    baseline = owned.expand_layout(owned.LAYOUT, pinned.LAYOUT, frozen, "console", "pal", timer.BASELINE)
    partial, proof = owned.prepare(source, folder / "inputs", "pal", pinned.ROOT / "toolchain")
    rows, _, _, _ = pinned.inputs(partial, folder / "inputs", "pal")
    owned.verify_parts(rows, proof, baseline)
    changed = deepcopy(proof)
    next(r for r in changed["parts"] if r["name"].startswith(".foxtrot.text.owner.state_storage_cpp"))["owner"] = "savestate.cpp"
    result["negative"]["source_ownership"] = rejects(lambda: owned.verify_parts(rows, changed, baseline), "Source-owned partial contribution differs")
    stale = json.loads(owned.LAYOUT.read_text())
    stale["original_layout_sha256"] = "0" * 64
    stale_path = folder / "stale-ownership.json"
    stale_path.write_text(json.dumps(stale))
    result["negative"]["stale_baseline"] = rejects(
        lambda: owned.expand_layout(stale_path, pinned.LAYOUT, frozen, "console", "pal", timer.BASELINE),
        "does not match the frozen")
    anchor = next(r for r in baseline["sections"] if r["name"].startswith(".foxtrot.text.owner.menu_cpp"))
    moved = {**anchor, "moved": True}
    result["negative"]["anchor_overlap"] = rejects(
        lambda: pinned.allocate_sections([moved], baseline,
            {"hole_begin": baseline["cluster"]["begin"], "hole_end": baseline["cluster"]["end"]}, baseline["anchors"]),
        "overlaps a protected anchor")
    menu = (args.snapshot / "src/menu.cpp").read_text()
    brace = menu.index("{", menu.index("void Menu::drawText("))
    menu = menu[:brace + 1] + '\n __asm__ volatile("nop");' + menu[brace + 1:]
    result["negative"]["compiled_anchor_growth"] = invoke(
        folder / "anchor-growth", source, "menu.cpp", menu, "Protected timer")
    changed_literal = (args.snapshot / "src/qft_timer.cpp").read_text().replace('"QF Sections"', '"Changed QF Sections"')
    result["negative"]["protected_literal"] = invoke(
        folder / "protected-literal", source, "qft_timer.cpp", changed_literal, "lack a protected literal")
    positive = folder / "storage-growth"
    fixture.prepare(source, positive, "pal")
    for module, anchor in (("state_storage.cpp", "void init() {"), ("savestate.cpp", "bool captureLiveVideo() {")):
        text = (args.snapshot / "src" / module).read_text()
        if text.count(anchor) != 1:
            raise ValueError("Source growth anchor changed")
        fixture.compile_copy(source, positive, "pal", module,
            text.replace(anchor, anchor + '\n __asm__ volatile(".rept 32\\n nop\\n .endr");'))
    fixture.compile_copy(source, positive, "pal", "checksum.cpp", fixture.new_source(), "new_source.cpp")
    arguments = argparse.Namespace(obj=fixture.partial(positive, "pal"), objects=positive,
        ownership=pinned.LAYOUT, kuribo_home=pinned.ROOT / "toolchain", vers="pal", target="console",
        work=positive / "link", elf=positive / "retained.elf", out=positive / "manifest.json", root=["twp_new_code"])
    pinned.build(arguments)
    receipt = json.loads((positive / "link/receipt.json").read_text())
    allocations = [r for r in receipt["allocations"] if r["name"].startswith(".twp.new.")]
    retired = receipt["capacity"]["retired_ranges"]
    if sum(r["linked_bytes"] for r in allocations) != 256 or not all(any(
            h["begin"] <= r["address"] < r["address"] + r["linked_bytes"] <= h["end"] for h in retired) for r in allocations):
        raise AssertionError("New code/data did not reuse retired source ranges")
    result["positive"] = {"protection": receipt["protection"], "capacity": receipt["capacity"],
                          "new_source_in_retired_ranges": allocations,
                          "retained_relocation_sites_verified": receipt["retained_relocation_sites_verified"]}
    result["timer_source_unchanged"] = before == pinned.file_sha(pinned.ROOT / "src/qft_timer.cpp")
    result["passed"] = result["timer_source_unchanged"]
    (folder / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "negative_tests": len(result["negative"]),
                      "reused_retired_bytes": 256, "remaining_capacity": receipt["recovered_bytes_remaining"]}))


if __name__ == "__main__":
    main()
