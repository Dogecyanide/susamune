"""Compile all regions from a verified source snapshot using actual CMake flags."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import gen_mod_bin
import link_pinned_mod as pinned
import test_pinned_source_build as fixture


def capture_source(destination):
    if destination.exists():
        raise ValueError("Source capture is create-only")
    files = {}
    for directory in ("src", "include", "vendor"):
        for source in sorted((pinned.ROOT / directory).rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(pinned.ROOT)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            target.write_bytes(data)
            files[relative.as_posix()] = pinned.sha(data)
    if any(pinned.file_sha(pinned.ROOT / name) != value for name, value in files.items()):
        raise ValueError("Source changed during snapshot capture")
    receipt = {"passed": True, "files": files, "source_cpp_count": len(list((destination / "src").glob("*.cpp"))),
               "scope": "Exact source, header and vendor snapshot; no source edits."}
    (destination / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def compile_one(entry, snapshot, output, dependencies):
    module = Path(entry["file"]).name
    argv = [x.strip('"') for x in shlex.split(entry["command"], posix=False)]
    original_output = Path(entry["output"])
    relative_output = (original_output.relative_to(Path(entry["directory"]))
                       if original_output.is_absolute() else original_output)
    obj = output / relative_output
    obj.parent.mkdir(parents=True, exist_ok=True)
    argv[argv.index("-o") + 1] = str(obj)
    argv[argv.index("-c") + 1] = str(snapshot / "src" / module)
    for index, word in enumerate(argv):
        if word.startswith("-I"):
            original = Path(word[2:]).resolve()
            argv[index] = "-I" + str(snapshot / original.relative_to(pinned.ROOT))
    argv.append("-I" + str(dependencies / "src"))
    fixture.execute(argv, output)
    return {"file": module, "object": str(obj.relative_to(output)), "sha256": pinned.file_sha(obj)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--capture", action="store_true", help="Create a new immutable snapshot before compiling")
    parser.add_argument("--output", type=Path, default=pinned.ROOT / "build/timewarp-owned-snapshot")
    parser.add_argument("--cmake-prefix", default="timewarp-owned-current")
    parser.add_argument("--no-cold-extensions", action="store_true")
    parser.add_argument("--targets", nargs="+", choices=("console", "emu"), default=("console", "emu"))
    parser.add_argument("--regions", nargs="+", choices=("jp", "us", "pal"), default=("jp", "us", "pal"))
    args = parser.parse_args()
    snapshot, output = args.snapshot.resolve(), args.output.resolve()
    if args.capture:
        if not snapshot.is_relative_to((pinned.ROOT / "build").resolve()):
            raise ValueError("New snapshots must stay in build")
        capture_source(snapshot)
    frozen = json.loads((snapshot / "receipt.json").read_text())
    if not frozen["passed"] or any(pinned.file_sha(snapshot / name) != value for name, value in frozen["files"].items()):
        raise ValueError("Source snapshot identity differs")
    if not output.is_relative_to((pinned.ROOT / "build").resolve()):
        raise ValueError("Outputs must stay inside the build directory")
    output.mkdir(parents=True, exist_ok=True)
    dependencies = output / "dependencies"
    (dependencies / "src").mkdir(parents=True, exist_ok=True)
    vendor_files = {}
    dependency_source = snapshot if (snapshot / "vendor").exists() else pinned.ROOT
    for source in sorted((dependency_source / "vendor").rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(dependency_source)
        destination = dependencies / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        vendor_files[str(relative)] = pinned.file_sha(destination)
    result = {"passed": False, "source_snapshot": str(snapshot),
              "snapshot_receipt_sha256": pinned.file_sha(snapshot / "receipt.json"),
              "vendor_sha256": vendor_files, "builds": []}
    try:
        for target in args.targets:
            configured = pinned.ROOT / "build" / (args.cmake_prefix + "-" + target)
            entries = json.loads((configured / "compile_commands.json").read_text())
            entries = [e for e in entries if (snapshot / "src" / Path(e["file"]).name).exists()]
            entries = [e for e in entries if any(f"susamune_obj_{region}.dir" in e["output"] for region in args.regions)]
            expected_modules = {p.name for p in (snapshot / "src").glob("*.cpp")} - {"debug_warp.cpp", "mem_diagnostics.cpp"}
            if {Path(e["file"]).name for e in entries} != expected_modules:
                raise ValueError("CMake commands do not cover the captured source inventory")
            build = output / target
            build.mkdir(parents=True, exist_ok=True)
            (build / "compile_commands.json").write_text(json.dumps(entries, indent=2) + "\n")
            with ThreadPoolExecutor(max_workers=4) as executor:
                compiled = list(executor.map(lambda entry: compile_one(entry, snapshot, build, dependencies), entries))
            for region in args.regions:
                arguments = argparse.Namespace(obj=fixture.partial(build, region), objects=build,
                    ownership=pinned.LAYOUT, kuribo_home=pinned.ROOT / "toolchain", vers=region, target=target,
                    work=build / "pinned-link" / region, elf=build / f"susamune_{region}.o",
                    out=build / f"manifest-{region}.json", root=[], no_cold_extensions=args.no_cold_extensions)
                pinned.build(arguments)
                receipt_path = arguments.work / "receipt.json"
                receipt = json.loads(receipt_path.read_text())
                packed = gen_mod_bin.build_mod_bin(json.loads(arguments.out.read_text()), format_version=4, base_dir=build)
                (build / f"mod-{region}.bin").write_bytes(packed)
                result["builds"].append({"target": target, "region": region, "protection": receipt["protection"],
                    "receipt": str(receipt_path), "receipt_sha256": pinned.file_sha(receipt_path),
                    "mod_bytes": len(packed), "remaining_bytes": receipt["recovered_bytes_remaining"],
                    "capacity": receipt["capacity"], "numeric_pools": receipt["changed_unprotected_numeric_pools"],
                    "source_objects": [row for row in compiled if f"susamune_obj_{region}.dir" in row["object"]]})
                (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
        result["passed"] = True
    finally:
        (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
