"""Private receipts over the shared production V4 transport packer.

Header is 16 big-endian words. Words 0..7 retain V3 meanings (version = 4).
Then section count, body CRC32, header CRC32, environment, four zero words.
Header CRC32 treats its own word at +40 as zero. Body CRC32 covers everything
after the header, including descriptors, padding, payloads and hook writes.
Each descriptor is eight words: target, init, memory, payload offset, stored,
kind, stored CRC32, zero. Hot targets are relative; cold target is absolute.
Cold (descriptor 2) is the first payload when present, followed by hot 0/1.
Payload starts, hook start and final file end align to 32 with zero padding.
codeSize ends immediately before hooks; memSize sums only the hot spans.

CRC is not a signature. Immutable exclusive source ownership, caller mapping,
cache maintenance and hardware lifecycle remain integration responsibilities.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from mod_transport import (ROOT, MAGIC, VERSION, HEADER, DESCRIPTOR, RAW, QUICK, XIP,
                           GAMES, BASES, CAPS, align32, stage, build_mod_v4, encode_quick)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_v3(data):
    if len(data) < 64:
        raise ValueError("short V3 file")
    magic, version, game, base, code, count, arena, memory = struct.unpack_from(">8I", data)
    if (magic, version, base, arena) != (MAGIC, 3, BASES.get(game), 0xC2000):
        raise ValueError("unsupported V3 header")
    if code < 32 or len(data) != 32 + code + count * 8:
        raise ValueError("invalid V3 file length")
    cursor, total, segments = 32, 0, []
    for i, (offset, cap) in enumerate(CAPS):
        target, init, mem, payload = struct.unpack_from(">4I", data, 32 + i * 16)
        if target != offset or payload != cursor or init > mem or mem > cap or (init | mem) & 3:
            raise ValueError("invalid V3 segment")
        if init > code - cursor:
            raise ValueError("truncated V3 payload")
        segments.append({"offset": target, "memory_size": mem,
                         "raw": data[32 + payload:32 + payload + init]})
        cursor += init
        total += mem
    if cursor != code or total != memory:
        raise ValueError("invalid V3 totals")
    writes = [struct.unpack_from(">2I", data, 32 + code + i * 8) for i in range(count)]
    for address, _ in writes:
        if address & 3 or not 0x80000000 <= address < base:
            raise ValueError("invalid V3 hook")
    return game, segments, writes


def baseline_inputs(receipt_path):
    receipt = json.loads(receipt_path.read_text())
    for region in receipt["regions"]:
        name = region["region"]
        baseline = (ROOT / f"build/baseline-console/mod_{name}.bin").read_bytes()
        if sha(baseline) != region["mod_sha256"]:
            raise ValueError("baseline provenance mismatch")
        game, segments, writes = read_v3(baseline)
        for index, (segment, evidence) in enumerate(zip(segments, region["segments"])):
            packed = (receipt_path.parent / f"{name}-segment{index}.ppc-quick").read_bytes()
            if sha(segment["raw"]) != evidence["raw_sha256"] or sha(packed) != evidence["quick_sha256"]:
                raise ValueError("PPC stream provenance mismatch")
            segment["quick"] = packed
        yield name, game, segments, writes, baseline


def cold_inputs(cold_receipt_path, transport_receipt_path=None):
    cold_receipt = json.loads(cold_receipt_path.read_text())
    transport = json.loads(transport_receipt_path.read_text()) if transport_receipt_path else None
    images = {(i["region"], Path(i["source"]).stem): i for i in transport["images"]} if transport else {}
    if cold_receipt["cold_offset"] != 0xA0:
        raise ValueError("cold pilot was linked for a different container offset")
    for region in cold_receipt["regions"]:
        name = region["region"]
        baseline = (ROOT / f"build/baseline-console/mod_{name}.bin").read_bytes()
        if sha((ROOT / f"build/baseline-console/susamune_{name}.o").read_bytes()) != region["baseline_elf_sha256"]:
            raise ValueError("cold cluster baseline differs from the console build")
        game, original, writes = read_v3(baseline)
        for tag, flags in (("console", 0), ("dolphin-vma", 1)):
            evidence = region["variants"][tag]
            directory = cold_receipt_path.parent / name
            cold = (directory / f"cold-{tag}.bin").read_bytes()
            if sha(cold) != evidence["cold"]["payload_sha256"]:
                raise ValueError("cold provenance mismatch")
            if sha((directory / f"retained-{tag}.elf").read_bytes()) != evidence["retained"]["elf_sha256"]:
                raise ValueError("retained ELF provenance mismatch")
            segments = []
            for index, label in enumerate(("low", "upper")):
                stem = f"retained-{tag}-{label}"
                span = evidence["retained"]["initialized_spans"][index]
                raw = (directory / f"{stem}.bin").read_bytes()
                if sha(raw) != span["sha256"] or len(raw) != span["initialized_bytes"]:
                    raise ValueError("cold hot-span provenance mismatch")
                if transport:
                    image = images[(name, stem)]
                    packed = (transport_receipt_path.parent / name / f"{stem}.ppc-quick").read_bytes()
                    if (sha(raw) != image["raw_sha256"] or len(raw) != image["initialized_bytes"] or
                            sha(packed) != image["quick_sha256"] or len(packed) != image["quick_bytes"]):
                        raise ValueError("cold compression provenance mismatch")
                else:
                    packed = encode_quick(raw)
                segments.append(dict(offset=span["address"] - BASES[game], raw=raw,
                                     memory_size=span["runtime_bytes"], quick=packed))
            if cold_receipt.get("consolidate"):
                if (evidence["retained"].get("outside_whitelist_bytes_identical") is not True or
                        evidence["retained"].get("timer_dependency_bytes_unchanged") is not True):
                    raise ValueError("consolidated cluster lacks retained-reference proof")
            elif segments[0]["raw"] != original[0]["raw"]:
                raise ValueError("strict cold pilot unexpectedly changes the low hot span")
            encoded = build_mod_v4(game, segments, writes, flags=flags, cold=cold,
                                   cold_vma=evidence["cold"]["vma"])
            yield name, tag, game, flags, segments, encoded, baseline, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-receipt", type=Path, default=ROOT / "build/timewarp-transport-measure/receipt.json")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-mod-v4")
    parser.add_argument("--cold-receipt", type=Path)
    parser.add_argument("--transport-receipt", type=Path)
    parser.add_argument("--host-encode", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.host_encode and (not args.cold_receipt or args.transport_receipt):
        parser.error("host encoding requires a cold receipt and no PPC transport receipt")
    if not args.host_encode and bool(args.cold_receipt) != bool(args.transport_receipt):
        parser.error("cold and transport receipts are required together, or use --host-encode")
    if args.cold_receipt:
        cases = cold_inputs(args.cold_receipt, args.transport_receipt)
    else:
        cases = ((name, None, game, 0, segments, build_mod_v4(game, segments, writes), baseline, None)
                 for name, game, segments, writes, baseline in baseline_inputs(args.input_receipt))
    for name, tag, game, flags, segments, packed, baseline, evidence in cases:
        path = args.output / f"mod_{name}{'-' + tag if tag else ''}.v4-proof"
        path.write_bytes(packed)
        stored = sum(len(s["quick"]) for s in segments)
        cold_bytes = evidence["cold"]["aligned_payload_bytes"] if evidence else 0
        row = dict(region=name, baseline_sha256=sha(baseline), container_sha256=sha(packed),
                   baseline_bytes=len(baseline), v4_bytes=len(packed), hot_stored_bytes=stored,
                   header_descriptors_padding_hooks_bytes=len(packed)-stored-cold_bytes,
                   savings_bytes=len(baseline)-len(packed), cold_present=bool(evidence),
                   cold_bytes=cold_bytes, placement=tag, flags=flags)
        if evidence:
            row.update(cold_vma=evidence["cold"]["vma"],
                       reusable_mem1_bytes=evidence["retained"]["reusable_mem1_bytes"],
                       pilot_scope="Console-baseline code; placement tag is not an IS_EMULATOR build. Link/transport proof only.")
        rows.append(row)
        print(f"{name} {tag or 'hot-only'}: {len(packed):,} bytes; {row['savings_bytes']:,} bytes below V3")
    receipt = dict(scope="Private cold V4 container with deterministic host boot encoding." if args.host_encode else
                        "Private V4 container; baseline hot bytes and actual PPC Quick streams.",
                   limits="No signature, production integration, cache maintenance, actual Wii validation or timing.",
                   input_receipt_sha256=sha(args.input_receipt.read_bytes()),
                   packer_sha256=sha(Path(__file__).read_bytes()),
                   shared_packer_sha256=sha((ROOT / 'scripts/mod_transport.py').read_bytes()), regions=rows)
    if args.cold_receipt:
        receipt.update(cold_receipt_sha256=sha(args.cold_receipt.read_bytes()))
        if args.transport_receipt:
            receipt['transport_receipt_sha256'] = sha(args.transport_receipt.read_bytes())
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
