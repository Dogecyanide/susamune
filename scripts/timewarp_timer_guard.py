"""Capture/check the released timer source, linked symbols and fixed scratch.

This is a development guard, not permission to regenerate the baseline after
a mismatch. Run with the repository's Python (pyelftools is required).
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "doc/timewarp-timer-baseline.json"
RELEASE = "703b33d948c44138a9a201857254f843121c1d5e"
TIMER_BLOB = "c31dda5ddc9d5b1a0cfc3fd985f8d907fa4f5890"
# Capture anchors from the original six released-source baselines. Verification
# permits unrelated code changes; capture must never bless different artifacts.
RELEASE_ARTIFACTS = {
    "console-jp": ("35339df530a3a7709888d6e18bad432316a570186866e70b750b88b5d73ddd10", "fe4cedc8287f5ada1b60d3962b3ae5a552670ff12cd98cc8f555acf2b7064e92"),
    "console-us": ("28f6f13dc1ba48aa3ba3307c8ab87bf2251da5037978f974efe32a318ab2dd1c", "4f4cd82962fc7ee5e569a011ce421b6e01ace17cc2037f6f98a767fde72f9a8e"),
    "console-pal": ("744fcafbccd72ea38345856de2a810efffebe3fc518406fba90c38a0847532c5", "2389e52045aa88b25106447afe486d69a33a7313207a6df26a8fda0598fca28c"),
    "emu-jp": ("f888a2f921e85900c772f17d207f5fb3e70711c5c338410bdcba39f5726e4f82", "5334d9f2f283c6dfab4f715cf49be11ec79a38bbf125601e8fb86710d7787ee3"),
    "emu-us": ("5fc35e46d531975f171be1fe9c23a013d8d714b0d3200c554f0cabf5ddab0ff6", "2c93bfccddaf0d2d38cfaca0444d9a5da1cdad5e88452a42fb080d8f707b2ffa"),
    "emu-pal": ("6fa24148384d0b3fff0f6ccff71fd7f004fc7e828a1705069f53e630bb5d3eec", "b12157b390ef681f198d462aa94b7401e776fd040029e2873a32c9e40928d871"),
}
INPUT_ROOTS = ("src", "include", "vendor", "maps", "cmake")
RELEASE_INPUTS = (*INPUT_ROOTS, "scripts", "CMakeLists.txt", "CMakePresets.json",
                  ".gitattributes", "toolchain/clang++.exe", "toolchain/ld.lld.exe")
LAYOUT_NAMES = (
    "SUSAMUNE_ADDR_MOD_BASE", "SUSAMUNE_ADDR_MOD_SCRATCH",
    "SUSAMUNE_ADDR_SHINE_TOUCH_FRAME", "SUSAMUNE_ADDR_LAST_SHINE_ID",
    "SUSAMUNE_ADDR_QFT_STATE", "SUSAMUNE_ADDR_QFT_DEATH_QF",
    "SUSAMUNE_ADDR_QFT_PLANT_QF", "SUSAMUNE_ADDR_QFT_TRANSITION_QF",
    "SUSAMUNE_ADDR_QFT_TRANSITION_TARGET", "SUSAMUNE_NATIVE_TIMER_DRAW_PPC_BASE",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release_sources():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != RELEASE:
        raise ValueError("Baseline capture requires the exact protected release HEAD")
    tree = subprocess.check_output(["git", "ls-tree", "-r", "-z", RELEASE, "--", *RELEASE_INPUTS], cwd=ROOT)
    blobs = {}
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        _mode, kind, blob = meta.split()
        if kind != b"blob":
            raise ValueError("Unexpected non-file release input")
        blobs[name.decode("utf-8")] = blob.decode("ascii")
    if not blobs:
        raise ValueError("Release input manifest is empty")
    # Git applies the repository's line-ending rules, including CRLF checkouts.
    paths = sorted(blobs)
    actual = subprocess.check_output(["git", "hash-object", "--stdin-paths"], cwd=ROOT,
                                     input="\n".join(paths) + "\n", text=True).splitlines()
    if len(actual) != len(paths):
        raise ValueError("Incomplete release input hashes")
    changed = [p for p, value in zip(paths, actual) if value != blobs[p]]
    if changed:
        raise ValueError("Capture inputs differ from release: " + ", ".join(changed[:12]))
    added = []
    for folder in INPUT_ROOTS:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.relative_to(ROOT).as_posix() not in blobs:
                added.append(path.relative_to(ROOT).as_posix())
    if added:
        raise ValueError("Unreleased build inputs present: " + ", ".join(sorted(added)[:12]))
    return {"head": head, "input_count": len(blobs), "git_blobs": dict(sorted(blobs.items())),
            "manifest_sha256": digest(json.dumps(blobs, sort_keys=True).encode())}


def build_configuration(build, target):
    cache_path = build / "CMakeCache.txt"
    cache = {}
    for line in cache_path.read_text().splitlines():
        match = re.match(r"([^#/:][^:]*):[^=]+=(.*)$", line)
        if match:
            cache[match[1]] = match[2]
    expected = {"IS_EMULATOR": "ON" if target == "emu" else "OFF",
                "ENABLE_DEBUG_WARPS": "OFF", "ENABLE_MEM_DIAGNOSTICS": "OFF",
                "ENABLE_SAVESTATE_DBG": "OFF", "VERS": "jp;us;pal",
                "CMAKE_GENERATOR": "Ninja", "CMAKE_BUILD_TYPE": ""}
    for key, value in expected.items():
        if cache.get(key) != value:
            raise ValueError(f"Non-release build configuration: {key}")
    for key, value in cache.items():
        flags = re.match(r"CMAKE_(CXX_FLAGS|EXE_LINKER_FLAGS)(_|$)", key) and not key.endswith("-ADVANCED")
        injection = key in ("CMAKE_CXX_COMPILER_LAUNCHER", "CMAKE_PROJECT_INCLUDE",
                            "CMAKE_PROJECT_INCLUDE_BEFORE", "CMAKE_TOOLCHAIN_FILE")
        if value and (flags or injection):
            raise ValueError(f"Non-release build override: {key}")
    for key, expected_path in (("CMAKE_HOME_DIRECTORY", ROOT), ("KURIBO_COMPILER_HOME", ROOT / "toolchain")):
        if key not in cache or Path(cache[key]).resolve() != expected_path.resolve():
            raise ValueError(f"Foreign source/tool configuration: {key}")
    commands = subprocess.check_output([cache["CMAKE_MAKE_PROGRAM"], "-C", str(build),
                                        "-t", "commands", "mod_bins"], text=True)
    if not all(f"-DIS_EMULATOR={int(target == 'emu')}" in line for line in commands.splitlines()
               if "qft_timer.cpp" in line and " -c " in line):
        raise ValueError("Timer compiler commands use a different target")
    if sum("qft_timer.cpp" in line and " -c " in line for line in commands.splitlines()) != 3:
        raise ValueError("Incomplete timer compile commands")
    tools = {}
    for key in ("CMAKE_COMMAND", "CMAKE_MAKE_PROGRAM", "SUSAMUNE_PYTHON", "KURIBO_COMPILER_HOME"):
        paths = [Path(cache[key])] if key != "KURIBO_COMPILER_HOME" else [Path(cache[key]) / exe for exe in ("clang++.exe", "ld.lld.exe")]
        for path in paths:
            tools[str(path.resolve())] = digest(path.read_bytes())
    return {"cache_sha256": digest(cache_path.read_bytes()), "cache": cache,
            "commands_sha256": digest(commands.encode()), "commands": commands.splitlines(), "tools_sha256": tools}


def release_artifacts(build, target):
    artifacts = {}
    for region in ("jp", "us", "pal"):
        names = (f"susamune_{region}.o", f"mod_{region}.bin")
        actual = tuple(digest((build / name).read_bytes()) for name in names)
        if actual != RELEASE_ARTIFACTS[f"{target}-{region}"]:
            raise ValueError(f"Capture artifacts differ from original release baseline: {target}-{region}")
        extra = (f"susamune_pre_{region}.o", f"susamune_manifest_{region}.json",
                 f"CMakeFiles/susamune_obj_{region}.dir/src/qft_timer.cpp.obj")
        artifacts.update({name: digest((build / name).read_bytes()) for name in (*names, *extra)})
    return artifacts


def sources():
    paths = set(ROOT.glob("src/*timer*.cpp")) | set(ROOT.glob("src/**/timer.cpp"))
    paths.add(ROOT / "include/susamune/qft_timer.hxx")
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes().replace(b"\r\n", b"\n"))
            for p in sorted(paths)}


def integer(expression):
    node = ast.parse(re.sub(r"(?<=[0-9a-fA-F])[uUlL]+\b", "", expression), mode="eval").body

    def evaluate(item):
        if isinstance(item, ast.Constant) and type(item.value) is int:
            return item.value
        if isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub)):
            a, b = evaluate(item.left), evaluate(item.right)
            return a + b if isinstance(item.op, ast.Add) else a - b
        raise ValueError("Unexpected scratch address expression")

    return evaluate(node)


def layout(region, target):
    source = ('#include "susamune/addresses.hxx"\n'
              '#include "susamune/mem2_map.h"\nTIMEWARP_LAYOUT_BEGIN\n' +
              "\n".join(LAYOUT_NAMES) + "\nTIMEWARP_LAYOUT_END\n")
    result = subprocess.run([
        str(ROOT / "toolchain/clang++.exe"), "-E", "-P", "-x", "c++",
        "-I", str(ROOT / "include"), f"-DSUSAMUNE_VERSION_{region.upper()}",
        f"-DIS_EMULATOR={int(target == 'emu')}", "-"], input=source,
        text=True, capture_output=True, check=True)
    lines = result.stdout.split("TIMEWARP_LAYOUT_BEGIN\n", 1)[1].split("TIMEWARP_LAYOUT_END", 1)[0]
    values = [integer(line) for line in lines.splitlines() if line.strip()]
    if len(values) != len(LAYOUT_NAMES):
        raise ValueError("Incomplete timer scratch layout")
    return dict(zip(LAYOUT_NAMES, values))


def timer_globals(build, region):
    path = build / f"CMakeFiles/susamune_obj_{region}.dir/src/qft_timer.cpp.obj"
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name(".symtab")
        if elf["e_type"] != "ET_REL" or elf["e_machine"] != "EM_PPC" or table is None:
            raise ValueError("Expected a PowerPC timer object with symbols")
        return sorted(s.name for s in table.iter_symbols()
                      if s["st_info"]["bind"] != "STB_LOCAL" and s["st_size"] and
                      isinstance(s["st_shndx"], int))


def linked_symbols(path, globals_):
    symbols = {}
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf["e_type"] != "ET_EXEC" or elf["e_machine"] != "EM_PPC":
            raise ValueError("Expected a final linked PowerPC ELF")
        table = elf.get_section_by_name(".symtab")
        if table is None:
            raise ValueError("Linked timer symbol table is missing")
        owner = ""
        for symbol in table.iter_symbols():
            kind, binding = symbol["st_info"]["type"], symbol["st_info"]["bind"]
            if kind == "STT_FILE":
                owner = symbol.name
            local = binding == "STB_LOCAL" and owner == "qft_timer.cpp"
            if not (local or binding != "STB_LOCAL" and symbol.name in globals_):
                continue
            if not symbol["st_size"] or not isinstance(symbol["st_shndx"], int):
                continue
            section = elf.get_section(symbol["st_shndx"])
            if not section["sh_flags"] & 2:
                continue
            offset, size = symbol["st_value"] - section["sh_addr"], symbol["st_size"]
            if offset < 0 or offset + size > section["sh_size"]:
                raise ValueError(f"Symbol outside section: {symbol.name}")
            payload = None if section["sh_type"] == "SHT_NOBITS" else digest(section.data()[offset:offset + size])
            key = ("local:" if local else "global:") + symbol.name
            if key in symbols:
                raise ValueError(f"Ambiguous timer symbol: {key}")
            symbols[key] = {"address": symbol["st_value"], "size": size, "sha256": payload}
    if len(symbols) < 50 or not any("sStatusCave" in name for name in symbols):
        raise ValueError("Timer symbols/code caves are missing")
    return dict(sorted(symbols.items()))


def capture(console, emu, destination):
    if destination.exists():
        raise FileExistsError("Refusing to replace the protected timer baseline")
    blob = subprocess.check_output(["git", "hash-object", "src/qft_timer.cpp"], cwd=ROOT, text=True).strip()
    if blob != TIMER_BLOB:
        raise ValueError("Timer source is not the protected release blob")
    provenance = {"sources": release_sources(), "builds": {},
                  "guard_sha256": digest(Path(__file__).read_bytes()), "python": sys.version,
                  "scope": "Released Git inputs and compiler/linker bytes, release configuration, and exact original baseline ELF/mod anchors. Build commands are read without rebuilding. Tool hashes record the remaining local build environment; they are not signed release attestations."}
    receipt = {"schema": 2, "release": RELEASE, "timer_git_blob": TIMER_BLOB,
               "sources": sources(), "builds": {}, "provenance": provenance}
    for target, build in (("console", console), ("emu", emu)):
        provenance["builds"][target] = {"configuration": build_configuration(build, target),
                                        "artifacts_sha256": release_artifacts(build, target)}
        for region in ("jp", "us", "pal"):
            global_names = timer_globals(build, region)
            receipt["builds"][f"{target}-{region}"] = {
                "globals": global_names, "layout": layout(region, target),
                "symbols": linked_symbols(build / f"susamune_{region}.o", global_names),
                "mod_sha256": digest((build / f"mod_{region}.bin").read_bytes()),
            }
    # Never replace an existing baseline, even with an explicit capture command.
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def compare(expected, actual, label):
    if expected != actual:
        keys = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
        raise ValueError(f"Protected timer {label} changed: " + ", ".join(keys[:12]))


def verify(receipt, build, target, regions):
    if receipt.get("release") != RELEASE or receipt.get("timer_git_blob") != TIMER_BLOB:
        raise ValueError("Timer receipt does not identify the protected release")
    compare(receipt["sources"], sources(), "source")
    for region in regions:
        expected = receipt["builds"][f"{target}-{region}"]
        if timer_globals(build, region) != expected["globals"]:
            raise ValueError(f"Protected timer {target}-{region} global symbol set changed")
        compare(expected["layout"], layout(region, target), f"{target}-{region} scratch")
        compare(expected["symbols"], linked_symbols(build / f"susamune_{region}.o", expected["globals"]),
                f"{target}-{region} linked bytes/locations")
        print(f"{target}-{region}: source, {len(expected['symbols'])} symbols and fixed scratch unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("capture")
    save.add_argument("--console-build", type=Path, required=True)
    save.add_argument("--emu-build", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--build", type=Path, required=True)
    check.add_argument("--target", choices=("console", "emu"), required=True)
    check.add_argument("--regions", nargs="+", choices=("jp", "us", "pal"), default=("jp", "us", "pal"))
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.console_build, args.emu_build, args.baseline)
        print(f"Captured protected release timer at {args.baseline}")
    else:
        verify(json.loads(args.baseline.read_text()), args.build, args.target, args.regions)


if __name__ == "__main__":
    main()
