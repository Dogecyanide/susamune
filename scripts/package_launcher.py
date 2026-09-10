"""Package the built Nintendont loader into the HBC app zip:
apps/moonshine_launcher/{boot.dol, icon.png, meta.xml, mod_<region>.bin...}.

One app serves every supported disc revision. The mod is no longer compiled into
the launcher: each mod_<region>.bin sits next to boot.dol and the loader reads
the one matching the disc it detected (see launcher/loader/source/SusamuneMod.c),
which is why they are packaged here rather than embedded.

meta.xml is rendered from launcher/meta.xml.j2 (jinja2) with the git short hash.

Usage: package_launcher.py --boot-dol boot.dol --out-zip out.zip \
                           [--source di|sd|usb] [--test-log TESTING.md] \
                           [--pattern-test-log PATTERN_TESTING.md] \
                           [--changelog CHANGELOG.md] \
                           [--mod-bins mod_jp.bin ...]
"""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

LAUNCHER_DIR = Path(__file__).resolve().parent.parent / "launcher"
META_TEMPLATE = LAUNCHER_DIR / "meta.xml.j2"
APP_NAME = "apps/moonshine_launcher"
APP_ICON = LAUNCHER_DIR / "icon.png"
MINIZ_LICENSE = LAUNCHER_DIR.parent / "vendor" / "miniz" / "LICENSE"
LZ4_LICENSE = LAUNCHER_DIR.parent / "vendor" / "lz4" / "LICENSE"
DROID_LICENSE = LAUNCHER_DIR.parent / "data" / "fonts" / "Droid-LICENSE.txt"
NOTO_LICENSE = LAUNCHER_DIR / "loader" / "data" / "OFL-NotoSansCJK.txt"
GUIDE_PATHS = {name: LAUNCHER_DIR.parent / "doc" / name
               for name in ("guide-en.md", "guide-ja.md")}


def launcher_files(boot_dol, mod_bins, source="di", version=None,
                   language="en", japanese_ui=None, changelog=None):
    """Build the exact app tree; final release verification lives in package_release."""
    if language not in ("en", "ja") or (language == "ja" and not japanese_ui):
        raise ValueError("Japanese language requires its validated game asset")
    bins = [Path(path) for path in mod_bins]
    regions = sorted(path.stem.split("_", 1)[1] for path in bins)
    if any(region not in ("jp", "us", "pal") for region in regions) or len(set(regions)) != len(regions):
        raise ValueError("Invalid or duplicate mod region")
    files = {
        "boot.dol": Path(boot_dol).read_bytes(),
        "language.txt": (language + "\n").encode("ascii"),
        "icon.png": APP_ICON.read_bytes(),
        "meta.xml": render_meta(source, regions, version).encode("utf-8"),
        "licenses/miniz-LICENSE.txt": MINIZ_LICENSE.read_bytes(),
        "licenses/lz4-LICENSE.txt": LZ4_LICENSE.read_bytes(),
        "licenses/OFL-NotoSansCJK.txt": NOTO_LICENSE.read_bytes(),
        "licenses/Droid-LICENSE.txt": DROID_LICENSE.read_bytes(),
        "licenses/fonts-README.md": (DROID_LICENSE.parent / "README.md").read_bytes(),
        "tools/decode_crash.py": (LAUNCHER_DIR.parent / "scripts/decode_crash.py").read_bytes(),
        **{name: path.read_bytes() for name, path in GUIDE_PATHS.items()},
        **{path.name: path.read_bytes() for path in bins},
    }
    if japanese_ui:
        from gen_japanese_ui import build
        asset = Path(japanese_ui).read_bytes()
        if asset != build()[0]:
            raise ValueError("Japanese UI asset is stale; regenerate it before packaging")
        files["ja_ui.bin"] = asset
    if changelog:
        files["CHANGELOG.md"] = Path(changelog).read_bytes()
    return {f"{APP_NAME}/{name}": data for name, data in files.items()}


def git_version():
    """The tag name if HEAD is exactly at a tag (CI release builds), else the
    short commit hash."""
    repo_dir = str(LAUNCHER_DIR.parent)
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            cwd=repo_dir, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        pass
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_dir, text=True).strip()
    except Exception:
        return "unknown"


def render_meta(source, regions, version=None):
    import jinja2
    template = jinja2.Template(META_TEMPLATE.read_text())
    return template.render(version=version or git_version(), source=source,
                           regions=regions)


def main(argv):
    ap = argparse.ArgumentParser(description="Package the Nintendont launcher HBC app zip.")
    ap.add_argument("--boot-dol", required=True, help="Built loader boot.dol")
    ap.add_argument("--out-zip", required=True, help="Output HBC app zip")
    ap.add_argument("--source", default="di", choices=["di", "sd", "usb"])
    ap.add_argument("--version", help="meta.xml version override")
    ap.add_argument("--test-log", help="tester log to include as TESTING.md")
    ap.add_argument("--pattern-test-log",
                    help="extra pattern tester log to include")
    ap.add_argument("--changelog", help="release notes to include as CHANGELOG.md")
    ap.add_argument("--japanese-ui", help="validated Japanese game catalogue/font asset")
    ap.add_argument("--language", choices=["en", "ja"], default="en",
                    help="Moonshine interface language, independent of game region")
    ap.add_argument("--mod-bins", nargs="*", default=[],
                    help="mod_<region>.bin files to drop into the app dir")
    args = ap.parse_args(argv)
    if args.language == "ja" and not args.japanese_ui:
        ap.error("--language ja requires --japanese-ui")

    files = launcher_files(args.boot_dol, args.mod_bins, args.source, args.version,
                           args.language, args.japanese_ui, args.changelog)
    if args.test_log:
        files[f"{APP_NAME}/TESTING.md"] = Path(args.test_log).read_bytes()
    if args.pattern_test_log:
        files[f"{APP_NAME}/PATTERN_TESTING.md"] = Path(args.pattern_test_log).read_bytes()
    with zipfile.ZipFile(args.out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
