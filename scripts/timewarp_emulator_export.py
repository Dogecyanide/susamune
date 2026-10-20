"""Export a verified Dolphin cold build as a source-free, fixed-size ISO BPS."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import struct

from dolreader.dol import DolFile
from elftools.elf.elffile import ELFFile
from pyisotools.iso import GamecubeISO

from gen_iso_bps import BpsBuilder, GC_ISO_SIZE, add_operation, align_up, read_crc
from gen_mod_bin import build_mod_bin, verified_artifact
import timewarp_timer_guard as timer

ROOT = Path(__file__).resolve().parents[1]
STAGING = 0x81000000
STAGING_CAPACITY = 0x100000
BOOTSTRAP_OFFSET = 0xBF000
BOOTSTRAP_CAPACITY = 0x400
PREFERRED_DISC_OFFSET = 0x01000000


def digest(data):
    return sha256(data).hexdigest()


def overlaps(a, size, b, length):
    return a < b + length and b < a + size


def branch(site, target, link=False):
    distance = target - site
    if distance & 3 or not -(1 << 25) <= distance < (1 << 25):
        raise ValueError("Startup branch exceeds REL24")
    return 0x48000000 | (distance & 0x03FFFFFC) | int(link)


def build_bootstrap(stub, stage, cold_base, cold_size, hardware, hot_ranges=(), menu_code=None):
    """Return the production shim; no imports, controller hooks or test mailbox."""
    if (any(v & 31 for v in (stub, stage, cold_base, cold_size)) or
            not 32 <= cold_size <= STAGING_CAPACITY or
            not 0x80000000 <= stage < stage + cold_size <= 0x81800000):
        raise ValueError("Invalid early-copy geometry")
    copies = [(stage, cold_base, cold_size)]
    staging_size = cold_size
    if menu_code:
        destination, size = menu_code
        from mod_transport import shared_define
        if (destination != shared_define("SUSAMUNE_MENU_CODE_DOLPHIN_PPC_BASE", "mem2_map.h") or
                not 0 < size <= shared_define("SUSAMUNE_MENU_CODE_SIZE", "mem2_map.h") or size & 31):
            raise ValueError("Invalid menu code copy span")
        copies.append((stage + cold_size, destination, size))
        staging_size += size
    if staging_size > STAGING_CAPACITY or stage + staging_size > 0x81800000:
        raise ValueError("Combined staging exceeds its fixed span")
    words, labels, fixups = [], {}, []

    def emit(*values):
        words.extend(values)

    def load(reg, value):
        emit(0x3C000000 | reg << 21 | value >> 16,
             0x60000000 | reg << 21 | reg << 16 | (value & 0xFFFF))

    def jump(opcode, label):
        fixups.append((len(words), opcode, label))
        emit(0)

    # __init_registers has established r1; preserve every register we touch.
    emit(0x9421FF60, 0x90010004, 0xBC410008, 0x7C0802A6, 0x900100A4,
         0x7C000026, 0x90010084, 0x7C0902A6, 0x90010088,
         0x7C0102A6, 0x9001008C)
    load(3, 0x80000038)
    emit(0x80C30000, 0x80E30004)  # live FST address and size
    load(3, 0x80000000)
    emit(0x7C061840)  # cmplw r6,r3
    jump(0x41800000, "halt")
    emit(0x7D063A14, 0x7C083040)  # add r8,r6,r7; cmplw r8,r6
    jump(0x40810000, "halt")
    load(3, 0x81800000)
    emit(0x7C081840)
    jump(0x41810000, "halt")
    for index, (address, size) in enumerate(((stage, staging_size), *hot_ranges)):
        if not 0x80000000 <= address < address + size <= 0x81800000:
            raise ValueError("Invalid loaded MEM1 span")
        load(3, address + size)
        emit(0x7C033040)
        jump(0x40810000, f"disjoint{index}")
        load(3, address)
        emit(0x7C034040)
        jump(0x41800000, "halt")
        labels[f"disjoint{index}"] = len(words)
    for index, (source, destination, size) in enumerate(copies):
        load(3, source)
        load(4, destination)
        load(5, size // 4)
        emit(0x7CA903A6, 0x38E00000)
        label = f"copy{index}"
        labels[label] = len(words)
        emit(0x80C30000, 0x90C40000, 0x90E30000, 0x38630004, 0x38840004)
        jump(0x42000000, label)
        for prefix, address, opcode in (("flush_code", destination, 0x7C0018AC),
                                       ("flush_stage", source, 0x7C0018AC),
                                       ("invalidate", destination, 0x7C001FAC)):
            load(3, address)
            load(5, size // 32)
            emit(0x7CA903A6)
            label = f"{prefix}{index}"
            labels[label] = len(words)
            emit(opcode, 0x38630020)
            jump(0x42000000, label)
            emit(0x7C0004AC)
    emit(0x4C00012C, 0x8001008C, 0x7C0103A6, 0x80010088, 0x7C0903A6,
         0x80010084, 0x7C0FF120, 0x800100A4, 0x7C0803A6,
         0xB8410008, 0x80010004, 0x382100A0)
    emit(branch(stub + len(words) * 4, hardware))
    labels["halt"] = len(words)
    emit(0x48000000)
    for index, opcode, label in fixups:
        distance = (labels[label] - index) * 4
        if not -32768 <= distance < 32768:
            raise ValueError("Bootstrap conditional branch overflow")
        words[index] = opcode | (distance & 0xFFFC)
    payload = struct.pack(f">{len(words)}I", *words)
    if len(payload) > BOOTSTRAP_CAPACITY:
        raise ValueError("Bootstrap exceeds its validated tail")
    return payload


def verify_build(build, region):
    manifest_path = build / f"susamune_manifest_{region}.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("target") != "emu" or manifest.get("transport_environment") != "dolphin":
        raise ValueError("Exporter requires an explicit Dolphin source build")
    container = build_mod_bin(manifest, format_version=4, base_dir=build)
    if container != (build / f"mod_{region}.bin").read_bytes():
        raise ValueError("Manifest differs from the current packed mod")
    cold = verified_artifact(manifest["cold_image"], build, "cold image")
    proof_bytes = verified_artifact(manifest["pinned_link_receipt"], build, "pinned link receipt")
    proof = json.loads(proof_bytes)
    verify_current_inputs(proof, build, region)
    elf_path = build / f"susamune_{region}.o"
    if digest(elf_path.read_bytes()) != proof.get("elf_sha256"):
        raise ValueError("Current ELF differs from the pinned link receipt")
    frozen = json.loads(timer.BASELINE.read_text())
    if proof.get("timer_baseline_sha256") != digest(timer.BASELINE.read_bytes()):
        raise ValueError("Pinned receipt uses a different timer baseline")
    timer.verify(frozen, build, "emu", [region])
    protected = frozen["builds"][f"emu-{region}"]["symbols"]
    from link_pinned_mod import make_manifest
    cold_path = Path(manifest["cold_image"]["path"])
    if not cold_path.is_absolute():
        cold_path = build / cold_path
    receipt_path = Path(manifest["pinned_link_receipt"]["path"])
    if not receipt_path.is_absolute():
        receipt_path = build / receipt_path
    rebuilt = make_manifest(elf_path, region, "emu", cold_path,
                            manifest["cold_image"]["vma"], receipt_path,
                            proof["fixed_hook_entries"], menu_code=manifest.get("menu_code"))
    for key in ("segments", "writes", "base_addr", "game_id", "memory_size", "region_reserve"):
        if manifest[key] != rebuilt[key]:
            raise ValueError("Manifest is not the current linked ELF: " + key)
    with elf_path.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()
                   if s.name and s["st_shndx"] != "SHN_UNDEF"}
    return manifest, cold, symbols, protected, {
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "container_sha256": digest(container), "elf_sha256": proof["elf_sha256"],
        "pinned_link_receipt_sha256": digest(proof_bytes),
        "timer_baseline_sha256": digest(timer.BASELINE.read_bytes()),
        "protected_symbols_verified": len(protected),
    }


def verify_current_inputs(proof, build, region):
    if proof.get("complete") is not True or proof.get("partial_rebuilt_from_current_objects") is not True:
        raise ValueError("Pinned receipt lacks complete source-build provenance")
    objects = build / f"CMakeFiles/susamune_obj_{region}.dir/src"
    actual = {path.name[:-4]: digest(path.read_bytes()) for path in objects.glob("*.cpp.obj")}
    if not actual or actual != proof.get("source_object_sha256"):
        raise ValueError("Current source objects differ from the pinned link receipt")
    if digest((build / f"susamune_pre_{region}.o").read_bytes()) != proof.get("source_partial_sha256"):
        raise ValueError("Current partial object differs from the pinned link receipt")


def read_disc(path, region):
    layout = json.loads((ROOT / f"data/iso_layout_{region}.json").read_text())
    if path.stat().st_size != GC_ISO_SIZE:
        raise ValueError("Expected an untrimmed, clean GameCube ISO")
    with path.open("rb") as stream:
        source_crc = read_crc(stream, 0, GC_ISO_SIZE)
        if source_crc != int(layout["source_crc32"], 16):
            raise ValueError("ISO checksum does not match the supported clean regional disc")
        stream.seek(0)
        disc_id = stream.read(6)
        if disc_id != {"jp": b"GMSJ01", "us": b"GMSE01", "pal": b"GMSP01"}[region]:
            raise ValueError("Clean ISO has the wrong region")
    disc = GamecubeISO.from_iso(path)
    dol_offset, dol_size = disc.bootheader.dolOffset, disc.dol.size
    fst_offset, fst_size = disc.bootheader.fstOffset, disc.bootheader.fstSize
    fst_reserved = max(fst_size, disc.bootheader.fstMaxSize)
    extents = [(0, 0x2460 + disc.apploader.loaderSize + disc.apploader.trailerSize),
               (dol_offset, dol_size), (fst_offset, fst_reserved)]
    extents.extend((node._fileoffset, node.size) for node in disc.rfiles(includedOnly=True))
    if any(a < 0 or n < 0 or a + n > GC_ISO_SIZE for a, n in extents):
        raise ValueError("Retail disc extent is outside the ISO")
    with path.open("rb") as stream:
        stream.seek(dol_offset)
        retail = stream.read(dol_size)
        stream.seek(fst_offset)
        fst_hash = digest(stream.read(fst_size))
    return retail, dol_offset, extents, source_crc, {
        "source_crc32": f"{source_crc:08X}", "disc_id": disc_id.decode(),
        "fst_offset": fst_offset, "fst_size": fst_size, "fst_reserved_size": fst_reserved,
        "fst_sha256": fst_hash,
        "retail_dol_offset": dol_offset, "retail_dol_sha256": digest(retail),
    }


def plan_dol(retail, manifest, cold, symbols, protected):
    dol = DolFile(BytesIO(retail))
    sections = list(dol.sections)
    ranges = [(s.address, s.size) for s in sections]
    ranges.append((dol.bssAddress, dol.bssSize))
    if any(s.offset < 0x100 or s.offset + s.size > len(retail) for s in sections):
        raise ValueError("Retail DOL section exceeds its source extent")

    def offset(address, size=4):
        matching = [s.offset + address - s.address for s in sections
                    if s.address <= address < address + size <= s.address + s.size]
        if len(matching) != 1:
            raise ValueError("Retail address is not in exactly one DOL section")
        return matching[0]

    base, stub = manifest["base_addr"], manifest["base_addr"] + BOOTSTRAP_OFFSET
    if dol.entryPoint != symbols["__start"]:
        raise ValueError("Unexpected retail entry point")
    boot_site = dol.entryPoint + 4
    for site, target in ((dol.entryPoint, symbols["__init_registers"]),
                         (boot_site, symbols["__init_hardware"])):
        if struct.unpack_from(">I", retail, offset(site))[0] != branch(site, target, True):
            raise ValueError("Retail startup differs from the audited register/hardware calls")
    if len(manifest["segments"]) != 2:
        raise ValueError("Expected exactly two hot image spans")
    images = []
    for segment, (expected, cap) in zip(manifest["segments"], ((0, 0x58000), (0x80000, 0x40000))):
        data, size = bytes.fromhex(segment["code"]), segment["memory_size"]
        if segment["offset"] != expected or size % 4 or len(data) % 4 or not len(data) <= size <= cap:
            raise ValueError("Invalid hot image span")
        if expected and base + expected + size > stub:
            raise ValueError("No unused upper hot tail for the bootstrap")
        images.append((base + expected, bytearray(data + bytes(align_up(size, 32) - len(data)))))
    if len(images) != 2 or not cold or len(cold) % 32 or len(cold) > STAGING_CAPACITY:
        raise ValueError("Invalid hot/cold image geometry")
    menu = verified_artifact(manifest["menu_code"], ROOT, "menu code") if manifest.get("menu_code") else b""
    staged = cold + menu
    if len(staged) > STAGING_CAPACITY:
        raise ValueError("Combined staging exceeds its fixed span")
    menu_copy = (manifest["menu_code"]["vma"], len(menu)) if menu else None
    upper = images[1][1]
    upper.extend(bytes(stub - images[1][0] + BOOTSTRAP_CAPACITY - len(upper)))
    loaded = [(address, len(data)) for address, data in images] + [(STAGING, len(staged))]
    protected_ranges = [(s["address"], s["size"]) for s in protected.values()]
    protected_ranges.append((base + 0x7FFC0, 64))
    for address, size in loaded:
        if any(overlaps(address, size, a, n) for a, n in ranges):
            raise ValueError("Expanded DOL overlaps retail memory")
    for address, size in ((stub, BOOTSTRAP_CAPACITY), (STAGING, len(staged))):
        if any(overlaps(address, size, a, n) for a, n in protected_ranges):
            raise ValueError("Bootstrap/staging overlaps protected timer storage")
    if any(overlaps(a, n, b, m) for i, (a, n) in enumerate(loaded) for b, m in loaded[i + 1:]):
        raise ValueError("Expanded DOL sections overlap")
    shim = build_bootstrap(stub, STAGING, manifest["cold_image"]["vma"], len(cold),
                           symbols["__init_hardware"], loaded[:2], menu_copy)
    at = stub - images[1][0]
    upper[at:at + len(shim)] = shim
    images.append((STAGING, staged))
    changed = {}
    writes = manifest["writes"]
    if len({a for a, _ in writes}) != len(writes) or any(a in (dol.entryPoint, boot_site) for a, _ in writes):
        raise ValueError("Duplicate or conflicting startup hook")
    for address, word in [*writes, (boot_site, branch(boot_site, stub, True))]:
        changed[offset(address)] = struct.pack(">I", word)
    free_text = [i for i in range(7) if not struct.unpack_from(">I", retail, 0x90 + i * 4)[0]]
    free_data = [i for i in range(7, 18) if not struct.unpack_from(">I", retail, 0x90 + i * 4)[0]]
    if len(free_text) < 2 or not free_data:
        raise ValueError("Retail DOL lacks free section slots")
    payloads, cursor = [], len(retail)
    for slot, (address, data) in zip((*free_text[:2], free_data[0]), images):
        aligned = align_up(cursor, 32)
        if aligned != cursor:
            payloads.append((cursor, bytes(aligned - cursor)))
        for table, value in ((0, aligned), (0x48, address), (0x90, len(data))):
            changed[table + slot * 4] = struct.pack(">I", value)
        payloads.append((aligned, bytes(data)))
        cursor = aligned + len(data)
    for name, symbol in protected.items():
        if not symbol.get("sha256"):
            continue
        matching = [bytes(data[symbol["address"] - address:][:symbol["size"]])
                    for address, data in images
                    if address <= symbol["address"] < symbol["address"] + symbol["size"] <= address + len(data)]
        if len(matching) != 1 or digest(matching[0]) != symbol["sha256"]:
            raise ValueError("Export changed protected timer bytes: " + name)
    return changed, payloads, cursor, {
        "bootstrap_address": stub, "bootstrap_bytes": len(shim), "bootstrap_sha256": digest(shim),
        "boot_hook_address": boot_site, "cold_address": manifest["cold_image"]["vma"],
        "cold_bytes": len(cold), "cold_sha256": digest(cold), "staging_address": STAGING,
        "menu_code_bytes": len(menu), "menu_code_sha256": digest(menu),
        "loaded_mem1_spans": [{"address": a, "size": n} for a, n in loaded],
    }


def unused_disc_span(extents, size, iso_size):
    if size <= 0 or any(a < 0 or n < 0 or a + n > iso_size for a, n in extents):
        raise ValueError("Invalid disc extent")
    gaps, cursor = [], 0
    for address, length in sorted(extents):
        begin = align_up(cursor, 32)
        if address - begin >= size:
            gaps.append((begin, address))
        cursor = max(cursor, address + length)
    begin = align_up(cursor, 32)
    if iso_size - begin >= size:
        gaps.append((begin, iso_size))
    for begin, end in gaps:
        if begin <= PREFERRED_DISC_OFFSET and PREFERRED_DISC_OFFSET + size <= end:
            return PREFERRED_DISC_OFFSET, end
    if not gaps:
        raise ValueError("No sufficient unused disc gap for the expanded DOL")
    return gaps[0]


def build_operations(source_offset, retail_size, extents, changed, payloads, dol_size, iso_size=GC_ISO_SIZE):
    target, _ = unused_disc_span(extents, dol_size, iso_size)
    operations = []
    add_operation(operations, 0x420, "literal", struct.pack(">I", target))
    cursor = 0
    for offset, data in sorted(changed.items()):
        if offset < cursor or offset + len(data) > retail_size:
            raise ValueError("Overlapping or out-of-range DOL edit")
        add_operation(operations, target + cursor, "source", source_offset + cursor, offset - cursor)
        add_operation(operations, target + offset, "literal", data)
        cursor = offset + len(data)
    add_operation(operations, target + cursor, "source", source_offset + cursor, retail_size - cursor)
    for offset, payload in payloads:
        add_operation(operations, target + offset, "literal", payload)
    cursor = target
    for operation in operations[1:]:
        if operation["target_offset"] != cursor:
            raise ValueError("Expanded DOL operations are not contiguous")
        cursor += operation["size"]
    if cursor != target + dol_size:
        raise ValueError("Expanded DOL length differs from its sections")
    return operations, target


def encode_patch(source, operations, source_crc, iso_size=GC_ISO_SIZE):
    ranges, cursor = set(), 0
    for op in operations:
        if op["target_offset"] > cursor:
            ranges.add((cursor, op["target_offset"] - cursor))
        if op["kind"] == "source":
            ranges.add((op["value"], op["size"]))
        cursor = op["target_offset"] + op["size"]
    if cursor < iso_size:
        ranges.add((cursor, iso_size - cursor))
    builder = BpsBuilder({(a, n): read_crc(source, a, n) for a, n in sorted(ranges)})
    cursor = 0
    for op in operations:
        builder.source_read(cursor, op["target_offset"] - cursor)
        if op["kind"] == "source":
            builder.source_copy(op["value"], op["size"])
        else:
            builder.target_read(op["value"])
        cursor = op["target_offset"] + op["size"]
    builder.source_read(cursor, iso_size - cursor)
    return builder.encode(iso_size, source_crc), builder.target_crc


def export(iso, build, region, output):
    receipt_path = output.with_suffix(output.suffix + ".json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Refusing to replace an existing patch or receipt")
    manifest, cold, symbols, protected, evidence = verify_build(build, region)
    source_stat = iso.stat()
    retail, source_offset, extents, source_crc, disc_evidence = read_disc(iso, region)
    changed, payloads, size, boot_evidence = plan_dol(retail, manifest, cold, symbols, protected)
    operations, target = build_operations(source_offset, len(retail), extents, changed, payloads, size)
    _, gap_end = unused_disc_span(extents, size, GC_ISO_SIZE)
    with iso.open("rb") as source:
        patch, target_crc = encode_patch(source, operations, source_crc)
    final_stat = iso.stat()
    if (source_stat.st_size, source_stat.st_mtime_ns) != (final_stat.st_size, final_stat.st_mtime_ns):
        raise ValueError("Source ISO changed during export")
    receipt = {"version": 1, "region": region, "passed": True,
               "scope": "Source-free Dolphin ISO export; no runtime or console claim.",
               "iso_size": GC_ISO_SIZE, "target_crc32": f"{target_crc:08X}",
               "relocated_dol_offset": target, "expanded_dol_bytes": size,
               "verified_unused_disc_end": gap_end,
               "patch_bytes": len(patch), "patch_sha256": digest(patch),
               "exporter_sha256": digest(Path(__file__).read_bytes()),
               **evidence, **disc_evidence, **boot_evidence}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(patch)
    with receipt_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, required=True, help="Clean, untrimmed ISO for this region")
    parser.add_argument("--build", type=Path, required=True, help="Current verified IS_EMULATOR build directory")
    parser.add_argument("--region", choices=("jp", "us", "pal"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export(args.iso.resolve(), args.build.resolve(), args.region, args.output.resolve())
    print(f"Wrote {args.output}: {result['patch_bytes']} bytes; FST/assets unchanged")


if __name__ == "__main__":
    main()
