"""Copy Moonshine files between Dolphin and ordinary folders while Dolphin is closed."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from setup_dolphin_data import BLOCK, REGIONS, identity, private_write
from validate_ghost import validate_ghost, validate_imported_ghost

KINDS = (("ghosts", re.compile(rb"ms_(?:p[0-35]_[0-9a-f]{16}|import_[0-9a-f]{16})$")),
         ("states", re.compile(rb"ms_state_[0-9]{8}$")),
         ("tas", re.compile(rb"ms_t[0-9]{8}_(?:project|s[0-9]{8})$")))
MAX_GCI = 64 + 2043 * BLOCK

def read_gci(path):
    if path.is_symlink() or not 64 < path.stat().st_size <= MAX_GCI:
        raise ValueError("Unsupported save file: " + str(path))
    raw = path.read_bytes()
    owner, name = identity(raw)
    if owner not in {v[1] + b"SU" for v in REGIONS.values()}:
        return None
    kind = next((kind for kind, pattern in KINDS if pattern.fullmatch(name)), None)
    return (owner, name, kind, raw) if kind else None

def scan(folder):
    rows = {}
    for path in sorted(folder.glob("*.gci")):
        item = read_gci(path)
        if item:
            key = item[:2]
            if key in rows: raise ValueError("Duplicate save identity: " + str(path))
            rows[key] = (*item, path)
    return rows

def check_room(directory, additions):
    files = list(directory.glob("*.gci"));blocks = 0
    for path in files:
        raw = path.read_bytes();identity(raw);blocks += (len(raw)-64)//BLOCK
    if len(files)+len(additions) > 127 or blocks+sum((len(raw)-64)//BLOCK for raw in additions) > 2043:
        raise ValueError("Dolphin virtual card is full; archive unused files before importing")

def export_files(data, output):
    if output.exists(): raise FileExistsError(output)
    planned = []
    for region, (_, game, directory) in REGIONS.items():
        for owner, name, kind, raw, path in scan(data / directory).values():
            if owner != game + b"SU": raise ValueError("Save in the wrong regional folder: " + str(path))
            planned.append((Path(directory) / kind / (name.decode("ascii") + ".gci"), raw))
    # Only the explicit ghost/state/TAS namespaces are portable; credentials and seeds never enter this list.
    output.mkdir(parents=True)
    manifest = {"version": 1, "files": []}
    for relative, raw in planned:
        private_write(output / relative, raw)
        manifest["files"].append({"path": relative.as_posix(), "sha256": hashlib.sha256(raw).hexdigest()})
    private_write(output / "moonshine-files.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return len(planned)

def import_files(data, source):
    manifest = source / "moonshine-files.json"
    if manifest.stat().st_size > 128 * 1024: raise ValueError("Oversized file manifest")
    document = json.loads(manifest.read_text())
    if document.get("version") != 1 or not isinstance(document.get("files"), list) or len(document["files"]) > 381:
        raise ValueError("Unsupported file manifest")
    existing = {directory: scan(data / directory) for _, _, directory in REGIONS.values()}
    planned, seen = [], set()
    for row in document["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or len(relative.parts) != 3 or any(p in (".", "..") for p in relative.parts):
            raise ValueError("Invalid portable file path")
        directory, kind, leaf = relative.parts
        if directory not in existing: raise ValueError("Unknown game region")
        path = source / relative
        if source.resolve() not in path.resolve().parents: raise ValueError("File outside its bundle")
        item = read_gci(path)
        if not item: raise ValueError("Private or unrecognized file in bundle")
        owner, name, actual_kind, raw = item
        game = next(game for _, game, d in REGIONS.values() if d == directory)
        if actual_kind != kind or owner != game + b"SU" or leaf != name.decode("ascii") + ".gci" or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("Portable file differs from its manifest")
        key = (directory, owner, name)
        if key in seen: raise ValueError("Duplicate portable file")
        seen.add(key)
        old = existing[directory].get((owner, name))
        if old:
            if old[3] != raw: raise ValueError("Conflicting save; neither copy replaced: " + leaf)
            continue
        destination = data / directory / (owner[:4].decode() + "-" + leaf)
        if destination.exists(): raise FileExistsError(destination)
        planned.append((destination, raw))
    # Preflight the complete bundle before writing any new file.
    for directory in existing:
        check_room(data / directory, [raw for path, raw in planned if path.parent == data / directory])
    for path, raw in planned: private_write(path, raw)
    return len(planned)

def wrap(region, name, payload):
    if len(name) > 31: raise ValueError("Filename is too long")
    header = bytearray(64);header[:6] = REGIONS[region][1] + b"SU";header[6] = 255
    header[8:8+len(name)] = name
    blocks = (len(payload) + BLOCK - 1) // BLOCK
    struct.pack_into(">IIHHBBHHHI", header, 40, 0, 0xffffffff, 0, 0, 4, 0, 0, blocks, 0xffff, 0xffffffff)
    return bytes(header) + payload + bytes(blocks * BLOCK - len(payload))

def import_ghost(data, region, source):
    if source.stat().st_size > 4 * 1024 * 1024: raise ValueError("Oversized ghost")
    payload = source.read_bytes()
    validate_imported_ghost(payload, running_region=REGIONS[region][0]-1)
    name = ("ms_import_" + hashlib.sha256(payload).hexdigest()[:16]).encode()
    _, game, directory = REGIONS[region]
    raw = wrap(region, name, payload)
    old = scan(data / directory).get((game+b"SU", name))
    if old:
        if old[3][64:64+len(payload)] != payload: raise ValueError("Conflicting ghost; existing file preserved")
        return old[4]
    path = data / directory / (game.decode()+"-"+name.decode()+".gci")
    check_room(data / directory, [raw])
    private_write(path, raw);return path

def export_ghost(source, destination):
    item = read_gci(source)
    if not item or item[2] != "ghosts": raise ValueError("Select a Moonshine ghost GCI")
    payload = item[3][64:]
    if len(payload) < 256: raise ValueError("Truncated ghost")
    size = struct.unpack_from(">I", payload, 8)[0]
    if not 256 <= size <= len(payload): raise ValueError("Invalid ghost length")
    payload = payload[:size];validate_ghost(payload)
    private_write(destination, payload);return destination

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "import"):
        p = sub.add_parser(name);p.add_argument("data", type=Path);p.add_argument("folder", type=Path)
    p = sub.add_parser("import-ghost");p.add_argument("data", type=Path);p.add_argument("region", choices=REGIONS);p.add_argument("ghost", type=Path)
    p = sub.add_parser("export-ghost");p.add_argument("gci", type=Path);p.add_argument("ghost", type=Path)
    a = parser.parse_args()
    if a.command == "export": print("Exported", export_files(a.data, a.folder), "files")
    elif a.command == "import": print("Imported", import_files(a.data, a.folder), "new files")
    elif a.command == "import-ghost": print(import_ghost(a.data, a.region, a.ghost))
    else: print(export_ghost(a.gci, a.ghost))

if __name__ == "__main__":
    try: main()
    except (OSError, ValueError, KeyError, TypeError) as error: raise SystemExit(str(error))
