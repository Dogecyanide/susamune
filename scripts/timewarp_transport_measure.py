"""Measure lossless retained-image compression without changing a mod format.

Actual PPC Quick compression is used only as a candidate boot transport codec.
These artifacts are measurements, never replacement launcher mod files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from timewarp_state_measure import PpcQuick, quick_blocks

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def segments(data):
    if len(data) < 64:
        raise ValueError("Truncated mod image")
    magic, version, game, base, code_bytes, writes, reserve, memory = struct.unpack_from(">8I", data)
    if version != 3 or code_bytes < 32 or len(data) != 32 + code_bytes + writes * 8:
        raise ValueError("Expected exact V3 mod image")
    result, cursor = [], 32
    for index, (expected_offset, cap) in enumerate(((0, 0x58000), (0x80000, 0x40000))):
        offset, initialized, runtime, payload = struct.unpack_from(">4I", data, 32 + index * 16)
        if (offset != expected_offset or payload != cursor or not 0 < initialized <= runtime <= cap or
                initialized % 4 or runtime % 4 or initialized > code_bytes - payload):
            raise ValueError("Invalid V3 segment")
        result.append((offset, runtime, data[32 + payload:32 + payload + initialized]))
        cursor += initialized
    if cursor != code_bytes or sum(item[1] for item in result) != memory:
        raise ValueError("Invalid segment totals")
    return result, {"magic": magic, "game_id": game, "base": base, "reserve": reserve,
                    "hooks_bytes": writes * 8, "metadata_bytes": 64}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "build/baseline-console")
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-transport-measure")
    parser.add_argument("--image-root", type=Path,
                        help="Encode private retained-*.bin images in regional subdirectories")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = {"scope": "Exact PPC compression and independent byte reconstruction of unchanged released MEM1 initialization payloads; no loader integration or boot/reset timing.",
               "limits": "Executable cold bytes must remain uncompressed. New descriptors, gateways, decoder code, checksums and alignment are not included in the capacity estimate.",
               "regions": []}
    with PpcQuick(args.dolphin, args.output / "ppc") as ppc:
        if args.image_root:
            images = sorted(args.image_root.glob("*/retained-*.bin"))
            if not images:
                raise ValueError("No retained image payloads found")
            receipt["scope"] = "Exact PPC compression and independent reconstruction of private relocated MEM1 initialization payloads; no loader integration or boot/reset timing."
            receipt["images"] = []
            for path in images:
                raw = path.read_bytes()
                packed = ppc.encode(raw)
                quick_blocks(packed, raw)
                output = args.output / path.parent.name / (path.stem + ".ppc-quick")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(packed)
                if path.read_bytes() != raw:
                    raise RuntimeError("Relocated payload changed during measurement")
                receipt["images"].append({"region": path.parent.name,
                    "source": str(path.resolve()), "initialized_bytes": len(raw),
                    "raw_sha256": sha(raw), "packed": str(output.resolve()),
                    "quick_bytes": len(packed), "quick_sha256": sha(packed),
                    "decoded_exact": True})
                print(f"{path.parent.name}/{path.name}: {len(raw):,} -> {len(packed):,} bytes")
            receipt["ppc_execution"] = ppc.evidence
        for region in ("jp", "us", "pal"):
            if args.image_root:
                break
            path = args.build / f"mod_{region}.bin"
            data = path.read_bytes()
            spans, metadata = segments(data)
            rows = []
            for index, (offset, runtime, raw) in enumerate(spans):
                packed = ppc.encode(raw)
                quick_blocks(packed, raw)
                output = args.output / f"{region}-segment{index}.ppc-quick"
                output.write_bytes(packed)
                rows.append({"offset": offset, "initialized_bytes": len(raw),
                             "runtime_bytes": runtime, "quick_bytes": len(packed),
                             "raw_sha256": sha(raw), "quick_sha256": sha(packed),
                             "decoded_exact": True})
            size = metadata["metadata_bytes"] + metadata["hooks_bytes"] + sum(r["quick_bytes"] for r in rows)
            row = {"region": region, "mod_sha256": sha(data), "original_file_bytes": len(data),
                   "segments": rows, "compressed_payload_plus_old_envelope_bytes": size,
                   "gross_transport_saving_bytes": len(data) - size,
                   "old_envelope_only_headroom_to_jp_prefix_bytes": 0x86000 - size}
            receipt["regions"].append(row)
            print(f"{region}: {len(data):,} -> {size:,} bytes with old envelope; gross saving {len(data) - size:,}")
        receipt["ppc_execution"] = ppc.evidence
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
