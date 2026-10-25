"""One checked release pipeline for every prototype from PR27 onward."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from gen_mod_bin import build_mod_bin, verified_artifact
from package_launcher import launcher_files
from timewarp_emulator_export import verify_current_inputs
from timewarp_wii_online_probe import installer_checks, kernel_budget, STATE_SHARE_FILES
import timewarp_timer_guard as timer

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ("jp", "us", "pal")


@dataclass(frozen=True)
class Release:
    number: int
    summary: str = "Development prerelease"

    def __post_init__(self):
        if self.number < 27 or self.number > 9999:
            raise ValueError("Use the archived packager for PR26 or earlier")

    @property
    def tag(self):
        return f"pr{self.number}"

    @property
    def version(self):
        return f"3.0.0 Timewarp PR{self.number}"

    @property
    def app(self):
        return f"apps/moonshine_online_prototype_{self.number}"

    def tree(self, target):
        if target not in ("console", "emu"):
            raise ValueError("Unknown build target")
        return ROOT / "build" / f"{self.tag}-{target}"


PROTECTION = dict(timer_symbols_identical=96, protected_string_atoms_identical=5,
                  dependency_anchors_identical=9, retail_hook_writes_identical=34)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sources():
    names = subprocess.check_output([
        "git", "ls-files", "-co", "--exclude-standard", "src", "include", "scripts",
        "data", "doc", "launcher", "tools/state_share", "tools/dolphin_online", "maps", "vendor", "cmake",
        "CMakeLists.txt", "CMakePresets.json", "README.md", "CONTRIBUTING.md"],
        cwd=ROOT, text=True).splitlines()
    return {name: sha((ROOT / name).read_bytes()) for name in sorted(set(names))
            if not name.endswith("nintendont_devkitpro_win32.zip")}


def configure(release, cmake, target):
    ninja = Path(sys.executable).with_name("ninja.exe" if sys.platform == "win32" else "ninja")
    if not ninja.is_file():
        ninja = shutil.which("ninja")
    if not ninja:
        raise ValueError("Run with the build virtualenv Python, or put Ninja on PATH")
    command = [cmake, "-S", str(ROOT), "-B", str(release.tree(target)), "-G", "Ninja",
               "-DCMAKE_MAKE_PROGRAM=" + str(ninja), "-DSUSAMUNE_PYTHON=" + sys.executable,
               "-DVERS=jp;us;pal", "-DIS_EMULATOR=" + ("ON" if target == "emu" else "OFF"),
               "-DLAUNCHER_DEFAULT_SOURCE=sd", "-DLAUNCHER_VERSION=" + release.version]
    for flag in ("ENABLE_COMPRESSED_MOD", "TIMEWARP_PINNED_LINK", "TIMEWARP_SHARED_STORE",
                 "TIMEWARP_HEAP_GAP", "TIMEWARP_QUICK_REPLAY", "TIMEWARP_LIVE_RACING",
                 "VERIFY_TIMEWARP_TIMER"):
        command.append("-D" + flag + "=ON")
    for flag in ("ENABLE_SAVESTATE_DBG", "ENABLE_MEM_DIAGNOSTICS", "ENABLE_DEBUG_WARPS",
                 "LAUNCHER_DISABLE_SUSAMUNE_PATCH"):
        command.append("-D" + flag + "=OFF")
    subprocess.run(command, cwd=ROOT, check=True)


def checked_build(release, target):
    build = release.tree(target)
    baseline = json.loads(timer.BASELINE.read_text())
    timer.verify(baseline, build, target, REGIONS)
    result, mods = {}, {}
    for region in REGIONS:
        manifest_path = build / f"susamune_manifest_{region}.json"
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("target") != target or manifest.get("transport_environment") !=
                ("console" if target == "console" else "dolphin")):
            raise ValueError("Wrong target manifest: " + region)
        proof_bytes = verified_artifact(manifest["pinned_link_receipt"], build, "link receipt")
        proof = json.loads(proof_bytes)
        verify_current_inputs(proof, build, region)
        if proof.get("passed") is not True or proof.get("protection") != PROTECTION:
            raise ValueError("Protected code checks failed: " + region)
        elf = build / f"susamune_{region}.o"
        if sha(elf.read_bytes()) != proof["elf_sha256"]:
            raise ValueError("Linked image differs: " + region)
        packed = build_mod_bin(manifest, format_version=4, base_dir=build)
        if packed != (build / f"mod_{region}.bin").read_bytes():
            raise ValueError("Packed mod differs: " + region)
        result[region] = dict(bytes=len(packed), sha256=sha(packed), protection=proof["protection"],
                              manifest_sha256=sha(manifest_path.read_bytes()),
                              link_receipt_sha256=sha(proof_bytes),
                              remaining_bytes=proof["capacity"]["remaining_bytes"])
        mods[region] = (packed, manifest)
    return result, mods


def build(release, cmake, target, jobs):
    configure(release, cmake, target)
    before = sources()
    targets = ["launcher"] if target == "console" else ["mod_bins", "japanese_ui"]
    command = [cmake, "--build", str(release.tree(target)), "--target", *targets, "--parallel", str(jobs)]
    log_path = release.tree(target) / f"{release.tag}-build.log"
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print(log_path.read_text(encoding="utf-8")[-8000:])
    completed.check_returncode()
    descriptions, _ = checked_build(release, target)
    if before != sources():
        raise ValueError("Sources changed during build; repeat after edits finish")
    save(release.tree(target) / f"{release.tag}-build-receipt.json", dict(
        passed=True, target=target, command=command, sources=before, mods=descriptions,
        scope="Current source build and protected-region checks; no hardware runtime claim"))


def package(release, output):
    if output.exists():
        raise FileExistsError("Package directory is create-only: " + str(output))
    current = sources()
    builds, mods = {}, None
    for target in ("console", "emu"):
        receipt = json.loads((release.tree(target) / f"{release.tag}-build-receipt.json").read_text())
        if receipt.get("passed") is not True or receipt["sources"] != current:
            raise ValueError("Build source receipt is stale: " + target)
        builds[target], checked = checked_build(release, target)
        if builds[target] != receipt["mods"]:
            raise ValueError("Build artifacts differ from source receipt: " + target)
        if target == "console":
            mods = checked
    launcher = release.tree("console") / "launcher"
    boot = launcher / "shared/boot.dol"
    kernel = launcher / "group-arm/kernel/kernel.bin"
    kernel_zip = launcher / "shared/data/kernel.zip"
    with zipfile.ZipFile(kernel_zip) as archive:
        if archive.namelist() != ["kernel.bin"] or archive.read("kernel.bin") != kernel.read_bytes():
            raise ValueError("Packed kernel differs")
    if kernel_zip.read_bytes() not in boot.read_bytes():
        raise ValueError("Launcher does not embed current kernel")
    budget = kernel_budget(launcher / "group-arm/kernel/kernel.elf")
    paths = [release.tree("console") / f"mod_{region}.bin" for region in REGIONS]
    files = launcher_files(boot, paths, source="sd", version=release.version, language="en",
                           japanese_ui=release.tree("console") / "ja_ui.bin")
    files = {name.replace("apps/moonshine_launcher", release.app, 1): data for name, data in files.items()}
    meta = ET.fromstring(files[release.app + "/meta.xml"])
    meta.find("name").text = f"Moonshine Prototype {release.number}"
    meta.find("short_description").text = release.summary
    meta.find("long_description").text = f"JP, US and PAL. See TESTING.txt for PR{release.number} checks and remaining hardware validation."
    files[release.app + "/meta.xml"] = ET.tostring(meta, encoding="utf-8", xml_declaration=True)
    files[release.app + "/TESTING.txt"] = (ROOT / f"doc/{release.tag}-testing.txt").read_bytes()
    files[release.app + "/NEXT-STEPS.txt"] = (ROOT / f"doc/{release.tag}-next-steps.txt").read_bytes()
    files[release.app + "/GHOST-SERVICE-PROPOSAL.txt"] = (ROOT / "doc/ghost-service-proposal.txt").read_bytes()
    files[release.app + "/GHOST-FORMAT.md"] = (ROOT / "doc/ghost_format.md").read_bytes()
    for name in STATE_SHARE_FILES:
        files[release.app + "/State sharing/" + name] = (ROOT / "tools/state_share" / name).read_bytes()
    output.mkdir(parents=True)
    installer = installer_checks(output, mods)
    if sources() != current:
        raise ValueError("Sources changed during packaging")
    archives = {}
    for language, suffix in (("en", ""), ("ja", "-Japanese")):
        variant = dict(files)
        variant[release.app + "/language.txt"] = (language + "\n").encode("ascii")
        archive_path = output / (f"Moonshine-Online-Prototype-{release.number}" + suffix + ".zip")
        with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(variant.items()):
                info = zipfile.ZipInfo(name, (2026, 10, 24, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        with zipfile.ZipFile(archive_path) as archive:
            if (archive.testzip() is not None or set(archive.namelist()) != set(variant) or
                    any(archive.read(name) != data for name, data in variant.items())):
                raise ValueError("Package readback differs")
        digest = sha(archive_path.read_bytes())
        archive_path.with_suffix(".zip.sha256").write_text(digest + "  " + archive_path.name + "\n")
        archives[language] = dict(path=str(archive_path), sha256=digest,
            files={name: dict(bytes=len(data), sha256=sha(data)) for name, data in variant.items()})
        print(str(archive_path))
    save(output / "receipt.json", dict(passed=True, archives=archives,
        builds=builds, kernel_budget=budget, installer=installer, sources=current,
        scope="Source builds, protected-region checks, production installer and ZIP readback; hardware checks pending"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prototype", type=int, required=True)
    parser.add_argument("--summary", default="Development prerelease")
    parser.add_argument("mode", choices=("configure", "build", "package"))
    parser.add_argument("--target", choices=("console", "emu", "all"), default="all")
    parser.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    release = Release(args.prototype, args.summary)
    if args.mode == "package":
        package(release, (args.output or ROOT / "build" / f"{release.tag}-package-release").resolve())
    else:
        for target in (("console", "emu") if args.target == "all" else (args.target,)):
            if args.mode == "configure":
                configure(release, args.cmake, target)
            else:
                build(release, args.cmake, target, args.jobs)


if __name__ == "__main__":
    main()
