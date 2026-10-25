"""Package current three-region PR13 Dolphin exports after the PAL runtime check."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import struct
import zipfile
import zlib

from timewarp_emulator_export import ROOT, digest, plan_dol, read_disc, verify_build
import dolphin_ghost_assets

REGIONS = ("jp", "us", "pal")
PREFIX = "Moonshine_Dolphin_PR13"
FILES = {
    "Apply-ISO.cmd": "tools/dolphin_online/Apply-ISO.cmd",
    "apply_patch.py": "tools/dolphin_online/apply_patch.py",
    "start-windows.cmd": "tools/dolphin_online/start-windows.cmd",
    "bridge.py": "tools/dolphin_online/bridge.py",
    "Dolphin-game-settings.ini": "tools/dolphin_online/Dolphin-game-settings.ini",
    "README.txt": "tools/dolphin_online/README.txt",
    "TESTING.txt": "tools/dolphin_online/TESTING-PR13.txt",
    "licenses/Moonshine-LICENSE.txt": "LICENSE",
    "licenses/miniz-LICENSE.txt": "vendor/miniz/LICENSE",
    "licenses/lz4-LICENSE.txt": "vendor/lz4/LICENSE",
    "licenses/OFL-NotoSansCJK.txt": "launcher/loader/data/OFL-NotoSansCJK.txt",
    "licenses/Droid-LICENSE.txt": "data/fonts/Droid-LICENSE.txt",
    "licenses/fonts-README.md": "data/fonts/README.md",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def checked_patch(data, receipt, region, evidence):
    if (receipt.get("passed") is not True or receipt.get("region") != region or
            digest(data) != receipt.get("patch_sha256") or len(data) < 19 or data[:4] != b"BPS1"):
        raise ValueError("Patch differs from its verified export: " + region)
    source, target, checksum = struct.unpack("<III", data[-12:])
    layout = read_json(ROOT / f"data/iso_layout_{region}.json")
    if (zlib.crc32(data[:-4]) & 0xFFFFFFFF != checksum or
            f"{source:08X}" != layout["source_crc32"] or
            f"{source:08X}" != receipt.get("source_crc32") or
            f"{target:08X}" != receipt.get("target_crc32")):
        raise ValueError("Patch checksums differ: " + region)
    if receipt.get("exporter_sha256") != digest((ROOT / "scripts/timewarp_emulator_export.py").read_bytes()):
        raise ValueError("Patch uses a different exporter: " + region)
    for key, value in evidence.items():
        if receipt.get(key) != value:
            raise ValueError("Patch is not from the current build: " + region + " " + key)


def checked_runtime(receipt, live, pal):
    if receipt.get("error"):
        raise ValueError("PAL runtime check has an error")
    for key in ("ppc_control_and_rx", "ppc_pose", "ppc_stop_restart", "companion_restart"):
        if receipt.get(key) is not True:
            raise ValueError("PAL runtime check is incomplete: " + key)
    runtime = receipt.get("runtime", {})
    for key in ("production_bootstrap_identical", "cold_payload_verified_after_copy", "diagnostic_pad_callbox_separate"):
        if runtime.get(key) is not True:
            raise ValueError("PAL production boot check is incomplete: " + key)
    info = live.get("info", {})
    for key in ("manifest_sha256", "container_sha256", "elf_sha256", "pinned_link_receipt_sha256"):
        if info.get("production_build", {}).get(key) != pal.get(key):
            raise ValueError("PAL runtime check uses a different build: " + key)
    for key in ("bootstrap_sha256", "cold_sha256"):
        if info.get("production_bootstrap", {}).get(key) != pal.get(key):
            raise ValueError("PAL runtime check uses a different payload: " + key)
    if runtime.get("production_bootstrap_sha256") != pal.get("bootstrap_sha256"):
        raise ValueError("PAL in-memory bootstrap differs from this export")


def checked_ghost_visual(receipt, transport_hash, capture):
    if receipt.get("transport_verification_sha256") != transport_hash:
        raise ValueError("Ghost visual check uses a different runtime")
    frames = receipt.get("captures", [])
    if (receipt.get("available") != 1 or receipt.get("playback", {}).get("ok") != 1 or
            receipt.get("model_submitted") is not True or not frames or
            any(frame.get("submitted") != 1 for frame in frames)):
        raise ValueError("Ghost model was not available and submitted")
    visual = receipt.get("visual_inspection", {})
    if visual.get("verified") is not True or visual.get("sha256") != digest(capture):
        raise ValueError("Ghost visual capture differs from its inspection")


def verify_application(iso, build, patch, region, temporary_iso):
    """Use the shipped patcher and compare all unchanged ranges; retain no ISO."""
    if temporary_iso.exists():
        raise FileExistsError("Refusing to replace a patch-verification image")
    manifest, cold, symbols, protected, evidence = verify_build(build, region)
    receipt = read_json(patch.with_suffix(".bps.json"))
    checked_patch(patch.read_bytes(), receipt, region, evidence)
    retail, _, _, _, disc_info = read_disc(iso, region)
    changed, payloads, dol_size, _ = plan_dol(retail, manifest, cold, symbols, protected, dolphin_ghost_assets.extract(iso))
    expected = bytearray(retail + bytes(dol_size - len(retail)))
    for offset, data in [*changed.items(), *payloads]:
        expected[offset:offset + len(data)] = data
    spec = importlib.util.spec_from_file_location("moonshine_packaged_patcher", ROOT / FILES["apply_patch.py"])
    patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    created = False
    try:
        patcher.apply(iso, patch, temporary_iso)
        created = True
        with iso.open("rb") as source, temporary_iso.open("rb") as target:
            target.seek(0x420)
            relocated = struct.unpack(">I", target.read(4))[0]
            if relocated != receipt["relocated_dol_offset"]:
                raise ValueError("Applied boot header differs from the export")
            target.seek(relocated)
            if target.read(dol_size) != expected:
                raise ValueError("Applied DOL differs from the verified production plan")
            for begin, end in ((0, 0x420), (0x424, relocated),
                               (relocated + dol_size, receipt["iso_size"])):
                source.seek(begin)
                target.seek(begin)
                remaining = end - begin
                while remaining:
                    count = min(remaining, 8 * 1024 * 1024)
                    if source.read(count) != target.read(count):
                        raise ValueError("Applied patch changed an original asset/header range")
                    remaining -= count
            target.seek(disc_info["fst_offset"])
            fst_hash = digest(target.read(disc_info["fst_size"]))
            if fst_hash != receipt["fst_sha256"]:
                raise ValueError("Applied patch changed the FST")
        return {"patch_sha256": receipt["patch_sha256"], "target_crc32": receipt["target_crc32"],
                "fst_sha256": fst_hash, "assets_unchanged": True, "dol_matches_plan": True,
                "packaged_patcher_sha256": digest((ROOT / FILES["apply_patch.py"]).read_bytes()),
                "patched_iso_bytes": temporary_iso.stat().st_size}
    finally:
        if created:
            temporary_iso.unlink()


def package_files(build, patches, runtime_dir):
    files = {name: (ROOT / source).read_bytes() for name, source in FILES.items()}
    exports = {}
    for region in REGIONS:
        patch = patches / f"moonshine_{region}.bps"
        data = patch.read_bytes()
        receipt = read_json(patch.with_suffix(".bps.json"))
        *_, evidence = verify_build(build, region)
        checked_patch(data, receipt, region, evidence)
        exports[region] = receipt
        files[f"patches/{patch.name}"] = data
        files[f"verification/{region}-export.json"] = (json.dumps(receipt, indent=2) + "\n").encode()
    runtime_path = runtime_dir / "transport-verification.json"
    live_path = runtime_dir / "live.json"
    runtime, live = read_json(runtime_path), read_json(live_path)
    checked_runtime(runtime, live, exports["pal"])
    visual_path = runtime_dir / "ghost-render-verification.json"
    visual = read_json(visual_path)
    capture_name = visual.get("visual_inspection", {}).get("file", "")
    if not capture_name or Path(capture_name).name != capture_name:
        raise ValueError("Ghost visual capture must be inside the runtime folder")
    checked_ghost_visual(visual, digest(runtime_path.read_bytes()),
                         (runtime_dir / capture_name).read_bytes())
    application_path = patches.parent / "patch-application.json"
    applied = read_json(application_path)
    if applied.get("passed") is not True:
        raise ValueError("Three-region patch application check is incomplete")
    for region in REGIONS:
        row = applied.get("regions", {}).get(region, {})
        for key in ("patch_sha256", "target_crc32", "fst_sha256"):
            if row.get(key) != exports[region].get(key):
                raise ValueError("Applied ISO differs from the export: " + region + " " + key)
        if row.get("assets_unchanged") is not True or row.get("dol_matches_plan") is not True:
            raise ValueError("Applied ISO content check is incomplete: " + region)
        if row.get("packaged_patcher_sha256") != digest(files["apply_patch.py"]):
            raise ValueError("Applied ISO check used a different packaged patcher: " + region)
    proof = {
        "version": 1, "name": PREFIX, "regions": list(REGIONS),
        "scope": "Three verified current regional exports and applied ISO checks; PAL production-bootstrap, local UDP and fresh session Mario ghost rendering. Two-machine Wii/Dolphin gameplay remains a user test.",
        "runtime_receipt_sha256": digest(runtime_path.read_bytes()),
        "ghost_render_receipt_sha256": digest(visual_path.read_bytes()),
        "session_ghost_checks": {"model_available": True, "model_submitted": True,
            "visually_verified": True, "capture_sha256": visual["visual_inspection"]["sha256"]},
        "patch_application_sha256": digest(application_path.read_bytes()),
        "runtime_checks": {key: runtime[key] for key in
            ("ppc_control_and_rx", "ppc_pose", "ppc_stop_restart", "companion_restart")},
        "boot_checks": {key: runtime["runtime"][key] for key in
            ("production_bootstrap_identical", "cold_payload_verified_after_copy",
             "diagnostic_pad_callbox_separate")},
        "patch_application_checks": {region: {key: applied["regions"][region][key] for key in
            ("assets_unchanged", "dol_matches_plan", "patched_iso_bytes", "packaged_patcher_sha256")}
            for region in REGIONS},
        "regions_verified": {region: {key: exports[region][key] for key in
            ("patch_sha256", "source_crc32", "target_crc32", "manifest_sha256", "container_sha256",
             "elf_sha256", "pinned_link_receipt_sha256", "bootstrap_sha256", "cold_sha256")}
             for region in REGIONS},
    }
    files["verification/build.json"] = (json.dumps(proof, indent=2) + "\n").encode()
    return files, proof


def package(build, patches, runtime_dir, output):
    receipt_path = output.with_suffix(output.suffix + ".json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Refusing to replace a package or receipt")
    files, proof = package_files(build, patches, runtime_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(f"{PREFIX}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(output) as archive:
        if set(archive.namelist()) != {f"{PREFIX}/{name}" for name in files}:
            raise ValueError("Package inventory differs")
        for name, data in files.items():
            if archive.read(f"{PREFIX}/{name}") != data:
                raise ValueError("Packaged file differs: " + name)
    result = {**proof, "passed": True, "zip_sha256": digest(output.read_bytes()),
              "zip_bytes": output.stat().st_size, "files": {
                  name: {"sha256": digest(data), "bytes": len(data)} for name, data in sorted(files.items())}}
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = package(args.build.resolve(), args.patches.resolve(), args.runtime_dir.resolve(), args.output.resolve())
    print(f"Wrote {args.output}: {receipt['zip_bytes']} bytes, {len(receipt['files'])} checked files")


if __name__ == "__main__":
    main()
