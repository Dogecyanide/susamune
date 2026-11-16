"""Prepare a private Moonshine data folder for standard Dolphin; no resident helper."""
from __future__ import annotations
import argparse
import hashlib
import hmac
import os
from pathlib import Path
import struct
import time

REGIONS = {"jp": (1, b"GMSJ", "JPN"), "us": (2, b"GMSE", "USA"), "pal": (3, b"GMSP", "EUR")}
BLOCK = 8192
SEED_NAME = b"ms_tls_seed"


def identity(data: bytes):
    if len(data) < 64:
        raise ValueError("Truncated GCI header")
    blocks = struct.unpack_from(">H", data, 56)[0]
    if not 0 < blocks <= 2043 or len(data) != 64 + blocks * BLOCK:
        raise ValueError("Invalid GCI length")
    return data[:6], data[8:40].split(b"\0", 1)[0]


def private_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def derive(seed: bytes):
    return hmac.new(seed, b"Moonshine Dolphin seed v1", hashlib.sha256).digest()


def record(seed: bytes, generation: int, region: int):
    header = struct.pack(">4I", 0x4D535345, 1, generation, region) + seed
    return header + hashlib.sha256(header).digest()[:16]


def seed_gci(region: str, seed: bytes | None = None):
    number, game, _ = REGIONS[region]
    seed = os.urandom(32) if seed is None else seed
    if len(seed) != 32:
        raise ValueError("Seed must contain 32 bytes")
    header = bytearray(64)
    header[:6] = game + b"SU"
    header[6] = 0xFF
    header[8:8 + len(SEED_NAME)] = SEED_NAME
    struct.pack_into(">IIHHBBHHHI", header, 40, max(0, int(time.time()) - 946684800),
                     0xFFFFFFFF, 0, 0, 4, 0, 0, 2, 0xFFFF, 0xFFFFFFFF)
    payload = bytearray(BLOCK * 2)
    payload[:64] = record(seed, 1, number)
    payload[BLOCK:BLOCK + 64] = record(derive(seed), 2, number)
    return bytes(header + payload)


def validate_seed(data: bytes, region: str):
    number, game, _ = REGIONS[region]
    if identity(data) != (game + b"SU", SEED_NAME) or len(data) != 64 + BLOCK * 2:
        raise ValueError("Unexpected Moonshine security file")
    records = [data[64 + i * BLOCK:128 + i * BLOCK] for i in range(2)]
    for row in records:
        magic, version, generation, stored_region = struct.unpack_from(">4I", row)
        if (magic, version, stored_region) != (0x4D535345, 1, number) or not 0 < generation < 0xFFFFFFFE or \
                not hmac.compare_digest(row[48:64], hashlib.sha256(row[:48]).digest()[:16]):
            raise ValueError("Damaged Moonshine security file; it was left unchanged")
    older, newer = sorted(records, key=lambda row: struct.unpack_from(">I", row, 8)[0])
    if struct.unpack_from(">I", newer, 8)[0] != struct.unpack_from(">I", older, 8)[0] + 1 or \
            not hmac.compare_digest(newer[16:48], derive(older[16:48])):
        raise ValueError("Moonshine security copies disagree; they were left unchanged")


def prepare(data: Path, source: Path | None = None):
    """Copy existing Moonshine files before making missing regional security files."""
    data = data.resolve()
    pending = []
    for region, (_, game, directory) in REGIONS.items():
        target = data / directory
        target.mkdir(parents=True, exist_ok=True)
        existing = {}
        for path in target.glob("*.gci"):
            raw = path.read_bytes()
            key = identity(raw)
            if key in existing:
                raise ValueError("Duplicate GCI identity in " + str(target))
            existing[key] = (path, raw)
        # Custom folders use JPN; older default GC folders may still use JAP.
        origins = [data / "JAP"] if region == "jp" else []
        if source:
            origins.append(source.resolve() / directory)
            if region == "jp":
                origins.append(source.resolve() / "JAP")
        for origin in dict.fromkeys(origins):
            if (origin / "Card B").is_dir():
                origin /= "Card B"
            for path in origin.glob("*.gci"):
                raw = path.read_bytes()
                key = identity(raw)
                if key[0] != game + b"SU":
                    continue
                if key in existing:
                    if existing[key][1] != raw:
                        raise ValueError("Conflicting save; neither copy was replaced: " + str(path))
                    continue
                destination = target / path.name
                if destination.exists() or any(p == destination for p, _ in pending):
                    raise ValueError("Destination filename is already occupied: " + str(destination))
                existing[key] = (destination, raw)
                pending.append((destination, raw))
        key = (game + b"SU", SEED_NAME)
        if key in existing:
            validate_seed(existing[key][1], region)
        else:
            pending.append((target / (game.decode() + "-Moonshine-security.gci"), seed_gci(region)))
    for path, raw in pending:
        private_write(path, raw)
    return data


def core_options(text: str, values: dict[str, str]):
    lines = text.splitlines(keepends=True)
    begin = next((i for i, line in enumerate(lines) if line.strip() == "[Core]"), None)
    if begin is None:
        return text.rstrip() + "\n\n[Core]\n" + "".join(k + " = " + v + "\n" for k, v in values.items())
    end = next((i for i in range(begin + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    kept = [line for line in lines[begin + 1:end] if line.split("=", 1)[0].strip() not in values]
    return "".join(lines[:begin + 1] + [line.rstrip("\r\n") + "\n" for line in kept] +
                   [k + " = " + v + "\n" for k, v in values.items()] + lines[end:])


def configure(user: Path, data: Path):
    path = user / "Config" / "Dolphin.ini"
    previous = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    value = (data.resolve() / "USA").as_posix()
    if any(c in value for c in "\r\n"):
        raise ValueError("Invalid data folder path")
    updated = core_options(previous, {"SlotB": "8", "GCIFolderBPath": value, "GCIFolderBPathOverride": ""})
    if updated == previous:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name("Dolphin.before-moonshine-" + str(time.time_ns()) + ".ini")
    if path.exists():
        private_write(backup, path.read_bytes())
    staged = path.with_name("Dolphin.moonshine-" + str(time.time_ns()) + ".tmp")
    private_write(staged, updated.encode("utf-8"))
    os.replace(staged, path)


def configure_games(user: Path):
    values = {"RAMOverrideEnable": "True", "MEM1Size": "33554432", "MMU": "False", "SerialPort1": "12"}
    for game in ("GMSJ01", "GMSE01", "GMSP01"):
        path = user / "GameSettings" / (game + ".ini")
        previous = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        updated = core_options(previous, values)
        if previous == updated: continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists(): private_write(path.with_name(game + ".before-moonshine-" + str(time.time_ns()) + ".ini"), path.read_bytes())
        staged = path.with_name(game + ".moonshine-" + str(time.time_ns()) + ".tmp")
        private_write(staged, updated.encode("utf-8"));os.replace(staged, path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user", type=Path, required=True, help="Dolphin user folder (contains Config)")
    p.add_argument("--data", type=Path, required=True, help="Dedicated Moonshine data folder")
    p.add_argument("--from-folder", type=Path, help="Existing Moonshine data or Dolphin GC folder")
    p.add_argument("--dolphin-closed", action="store_true", help="Confirm Dolphin is fully closed before changing storage")
    a = p.parse_args()
    if not a.dolphin_closed:
        p.error("Close Dolphin first, then run again with --dolphin-closed")
    folder = prepare(a.data, a.from_folder or a.user / "GC")
    configure(a.user, folder)
    configure_games(a.user)
    print("Moonshine data is ready in " + str(folder))
    print("Keep this folder private: it also holds your settings and account link. Share individual ghosts only.")


if __name__ == "__main__":
    main()
