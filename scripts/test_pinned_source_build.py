"""Integration fixtures for the optional source linker; production sources stay untouched."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import link_pinned_mod as pinned

ROOT = Path(__file__).resolve().parents[1]


def execute(argv, folder):
    result = subprocess.run([str(x) for x in argv], cwd=folder, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def compile_copy(source_build, build, region, module, text, output_module=None):
    entry = next(e for e in json.loads((source_build / "compile_commands.json").read_text())
                 if f"susamune_obj_{region}.dir" in e["output"] and e["file"].endswith("/" + module))
    name = output_module or module
    source = build / "src" / name
    source.parent.mkdir(exist_ok=True)
    source.write_text(text)
    argv = [x.strip('"') for x in shlex.split(entry["command"], posix=False)]
    argv[argv.index("-c") + 1] = str(source)
    output = build / f"CMakeFiles/susamune_obj_{region}.dir/src/{name}.obj"
    argv[argv.index("-o") + 1] = str(output)
    argv.extend(["-I", str(ROOT / "src")])
    # Compile dependency files belong to the private fixture too.
    if "-MF" in argv:
        argv[argv.index("-MF") + 1] = str(output.with_suffix(".d"))
    execute(argv, build)


def partial(build, region):
    output = build / f"susamune_pre_{region}.o"
    execute([ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi",
             "-nodefaultlibs", "-nostdlib", "-fuse-ld=lld", "-r",
             *sorted((build / f"CMakeFiles/susamune_obj_{region}.dir/src").glob("*.cpp.obj")),
             "-o", output], build)
    return output


def prepare(source, folder, region):
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"CMakeFiles/susamune_obj_{region}.dir/src"
    destination.mkdir(parents=True, exist_ok=True)
    for path in (source / f"CMakeFiles/susamune_obj_{region}.dir/src").glob("*.cpp.obj"):
        shutil.copyfile(path, destination / path.name)


def invoke(folder, region, target, expect_error=None):
    arguments = argparse.Namespace(obj=partial(folder, region), objects=folder,
        ownership=pinned.LAYOUT, kuribo_home=ROOT / "toolchain", vers=region, target=target,
        work=folder / "link", elf=folder / f"susamune_{region}.o", out=folder / "manifest.json", root=[])
    try:
        pinned.build(arguments)
    except ValueError as error:
        if expect_error is None or expect_error not in str(error):
            raise
        return {"rejected": True, "reason": str(error)}
    if expect_error is not None:
        raise AssertionError("Expected rejection: " + expect_error)
    return json.loads((folder / "link/receipt.json").read_text())


def new_source(size=128):
    return '''extern "C" {
__attribute__((used, section(".twp.new.data"))) volatile unsigned char twp_new_data[%d] = { 1 };
__attribute__((naked, used, section(".twp.new.text"))) void twp_new_code() {
    __asm__ volatile("lis 3, twp_new_data@ha\\n lbz 3, twp_new_data@l(3)\\n .rept 29\\n nop\\n .endr\\n blr");
}
}
''' % size


CHECKSUM_ANCHOR = "u32 crc32(const void *data, u32 size, u32 zeroOffset, u32 zeroSize) {"


def grown_checksum():
    source = (ROOT / "src/checksum.cpp").read_text()
    return ('extern "C" void twp_new_code();\n' + source.replace(CHECKSUM_ANCHOR,
        CHECKSUM_ANCHOR + '\n    __asm__ volatile(".rept 64\\n nop\\n .endr");\n    twp_new_code();'))


def positive(root, target, region):
    source = root / f"source-{target}"
    folder = root / "growth" / f"{target}-{region}"
    prepare(source, folder, region)
    compile_copy(source, folder, region, "checksum.cpp", grown_checksum())
    compile_copy(source, folder, region, "checksum.cpp", new_source(), "new_source.cpp")
    receipt = invoke(folder, region, target)
    allocations = receipt["allocations"]
    if not any(row["name"] == ".text.crc32__8ChecksumFPCvUlUlUl" and row["linked_bytes"] > 136 for row in allocations):
        raise AssertionError("Existing function did not grow into recovered space")
    if sum(row["linked_bytes"] for row in allocations if row["name"].startswith(".twp.new.")) != 256:
        raise AssertionError("New code/data are not exactly 256 bytes")
    execute([sys.executable, ROOT / "scripts/gen_mod_bin.py", folder / "manifest.json",
             "-o", folder / "mod.bin", "--format", "v4"], ROOT)
    return {"target": target, "region": region, "protection": receipt["protection"],
            "new_source_bytes": receipt["new_source_bytes"], "allocations": allocations,
            "mod_bytes": (folder / "mod.bin").stat().st_size,
            "receipt": str(folder / "link/receipt.json")}


def negative(root):
    source = root / "source-console"
    results = {}
    folder = root / "negative/mixed-growth"
    prepare(source, folder, "pal")
    menu = (ROOT / "src/menu.cpp").read_text()
    start = menu.index("void Menu::drawText(")
    brace = menu.index("{", start)
    compile_copy(source, folder, "pal", "menu.cpp", menu[:brace + 1] + '\n __asm__ volatile("nop");' + menu[brace + 1:])
    results["protected_mixed_section_growth"] = invoke(folder, "pal", "console", "Protected timer")

    folder = root / "negative/protected-literal"
    prepare(source, folder, "pal")
    source_text = (ROOT / "src/qft_timer.cpp").read_text().replace('"QF Sections"', '"Changed QF Sections"')
    compile_copy(source, folder, "pal", "qft_timer.cpp", source_text)
    results["protected_literal_change"] = invoke(folder, "pal", "console", "lack a protected literal")

    folder = root / "negative/exhausted"
    prepare(source, folder, "pal")
    compile_copy(source, folder, "pal", "checksum.cpp", grown_checksum())
    compile_copy(source, folder, "pal", "checksum.cpp", new_source(70000), "new_source.cpp")
    results["hole_exhaustion"] = invoke(folder, "pal", "console", "Recovered MEM1 space exhausted")

    folder = root / "negative/stale-partial"
    prepare(source, folder, "pal")
    stale = partial(folder, "pal")
    compile_copy(source, folder, "pal", "checksum.cpp", grown_checksum())
    args = argparse.Namespace(obj=stale, objects=folder, ownership=pinned.LAYOUT,
        kuribo_home=ROOT / "toolchain", vers="pal", target="console", work=folder / "link",
        elf=folder / "susamune_pal.o", out=folder / "manifest.json", root=[])
    try:
        pinned.build(args)
    except ValueError as error:
        if "Partial object does not match" not in str(error):
            raise
        results["stale_partial"] = {"rejected": True, "reason": str(error)}
    else:
        raise AssertionError("Stale partial object was accepted")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "build/timewarp-pinned-link")
    parser.add_argument("--regions", nargs="+", choices=("jp", "us", "pal"), default=("jp", "us", "pal"))
    parser.add_argument("--targets", nargs="+", choices=("console", "emu"), default=("console", "emu"))
    parser.add_argument("--skip-negative", action="store_true")
    parser.add_argument("--only-negative", action="store_true")
    args = parser.parse_args()
    folder = args.root.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Fixtures must remain under this checkout's build directory")
    before = pinned.file_sha(ROOT / "src/qft_timer.cpp")
    results = json.loads((folder / "source-tests.json").read_text()) if args.only_negative else {"positive": []}
    results["passed"] = False
    try:
        if not args.only_negative:
            with ThreadPoolExecutor(max_workers=2) as executor:
                jobs = [executor.submit(positive, folder, target, region) for target in args.targets for region in args.regions]
                for job in jobs:
                    results["positive"].append(job.result())
        if not args.skip_negative:
            results["negative"] = negative(folder)
        results["passed"] = True
    finally:
        results["timer_source_unchanged"] = before == pinned.file_sha(ROOT / "src/qft_timer.cpp")
        (folder / "source-tests.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
