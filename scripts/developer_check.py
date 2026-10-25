"""Read-only checkout/toolchain check; run with the build virtualenv Python."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def inspect():
    rows = []

    def add(name, ok, detail, required=True):
        rows.append(dict(name=name, ok=bool(ok), detail=str(detail), required=required))

    add("Python", sys.version_info >= (3, 10), sys.executable + " " + sys.version.split()[0])
    for module in ("elftools", "lz4", "jinja2", "PIL", "dolreader", "pyisotools", "geckolibs"):
        add(module, importlib.util.find_spec(module) is not None, "Python import")
    for name in ("git", "cmake", "ninja"):
        local = Path(sys.executable).with_name(name + (".exe" if os.name == "nt" else ""))
        path = shutil.which(name) or (str(local) if local.is_file() else None)
        if not path and name == "cmake" and os.name == "nt":
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "CMake/bin/cmake.exe"
            if candidate.is_file():
                path = str(candidate)
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10) if path else None
            detail = (path + " | " + result.stdout.splitlines()[0]) if result and result.stdout else "Not found"
            add(name, result is not None and result.returncode == 0, detail)
        except (OSError, subprocess.TimeoutExpired) as error:
            add(name, False, error)
    for relative in ("toolchain/clang.exe", "toolchain/ld.lld.exe",
                     "launcher/nintendont_devkitpro_win32.zip"):
        path = ROOT / relative
        # LFS pointers are text, not a usable archive/toolchain.
        prefix = b""
        if path.is_file():
            with path.open("rb") as source:
                prefix = source.read(80)
        add(relative, bool(prefix) and not prefix.startswith(b"version https://git-lfs"), path)
    for region in ("jp", "us", "pal"):
        path = ROOT / "maps" / (region + ".map")
        add("map " + region, path.is_file(), path)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = inspect()
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{'OK' if row['ok'] else 'MISSING'} {row['name']}: {row['detail']}")
        print("Disc inputs and live Wii/Dolphin behavior are checked separately; nothing was installed.")
    return int(any(row["required"] and not row["ok"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
