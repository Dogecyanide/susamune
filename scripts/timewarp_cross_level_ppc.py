"""PPC Quick measurements in bounded, independently encoded block batches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from timewarp_state_measure import BLOCK_BYTES, FRAME, POOL_BYTES, PpcQuick, ROOT, measure_set, quick_blocks


class Batched:
    def __init__(self, ppc):
        self.ppc = ppc
        self.evidence = {"batch_raw_bytes": 0x400000, "full_stream_controls": []}

    def encode(self, raw):
        batch = self.evidence["batch_raw_bytes"]
        assert batch % BLOCK_BYTES == 0
        parts = []
        for offset in range(0, len(raw), batch):
            part = raw[offset:offset + batch]
            packed = self.ppc.encode(part)
            quick_blocks(packed, part)
            parts.append(packed[8:])
        packed = FRAME + b"".join(parts)
        quick_blocks(packed, raw)
        if len(raw) <= 0xE80000 and len(packed) <= 0x6F0000:
            whole = self.ppc.encode(raw)
            if whole != packed:
                raise RuntimeError("PPC batched encoding differs from full-stream encoding")
            self.evidence["full_stream_controls"].append({
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "packed_bytes": len(packed), "identical": True})
        return packed


def overlap(result):
    streams, raw_blocks = [], []
    for row in result["slots"]:
        raw = Path(row["raw_path"]).read_bytes()
        packed = Path(row["ppc_quick"]["path"]).read_bytes()
        streams.append(set(quick_blocks(packed, raw)))
        raw_blocks.append([raw[at:at + BLOCK_BYTES] for at in range(0, len(raw), BLOCK_BYTES)])
    independent = sum(sum(map(len, blocks)) for blocks in streams)
    merged = sum(map(len, set.union(*streams)))
    common = set.intersection(*streams)
    at_same_offset = [i for i in range(min(map(len, raw_blocks)))
                      if raw_blocks[0][i] == raw_blocks[1][i] == raw_blocks[2][i]]
    raw_total = sum(row["raw_bytes"] for row in result["slots"])
    return {"cross_slot_savings_after_within_slot_dedup_bytes": independent - merged,
            "within_slot_duplicate_savings_bytes": result["ppc_all_quick_sharing"]["gross_saved_bytes"] - (independent - merged),
            "encoded_blocks_present_in_all_three": len(common),
            "unique_encoded_bytes_present_in_all_three": sum(map(len, common)),
            "pairwise_unique_encoded_overlap_bytes": {
                f"{a + 1}-{b + 1}": sum(map(len, streams[a] & streams[b]))
                for a, b in ((0, 1), (0, 2), (1, 2))},
            "raw_total_bytes": raw_total,
            "same_offset_raw_blocks_identical_in_all_three": len(at_same_offset),
            "same_offset_raw_bytes_identical_in_all_three_per_state": sum(len(raw_blocks[0][i]) for i in at_same_offset),
            "block_bytes": BLOCK_BYTES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/cross-level/current-ppc")
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.is_relative_to(args.captures.resolve()):
        parser.error("Output must stay in task build and outside capture inputs")
    sources = ["src/state_codec.cpp", "vendor/lz4/lz4.c", "vendor/lz4/lz4.h",
               "vendor/lz4/state_lz4_config.h", "scripts/timewarp_state_measure.py",
               "scripts/timewarp_cross_level_ppc.py"]
    receipt = {"scope": "Current production PPC Quick codec applied to same-build historical PAL captures. Exact immutable block sharing; gross savings are before allocator metadata/transactions.",
               "batch_reason": "Quick resets LZ4 per 128KiB block. FourMiB block-aligned batches bound MEM1 output; frame headers are removed only at batch boundaries. Full-stream PPC controls and independent decode verify equality.",
               "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
               "capture_receipt": str((args.captures / "capture-receipt.json").resolve()),
               "pool_bytes": POOL_BYTES, "sets": []}
    try:
        with PpcQuick(args.dolphin, folder / "ppc") as ppc:
            batch = Batched(ppc)
            receipt["runtime"], receipt["batch"] = ppc.evidence, batch.evidence
            for name in ("mixed", "same-level"):
                result = measure_set(name, args.captures / name, POOL_BYTES, None,
                                     batch, folder / "generated")
                for row in result["slots"]:
                    metadata = json.loads(Path(row["raw_path"]).with_suffix(".json").read_text())
                    for key in ("scene_evidence", "area", "episode", "snapshot_version",
                                "metadata_path", "metadata_sha256"):
                        row[key] = metadata[key]
                result["cross_level_overlap"] = overlap(result)
                receipt["sets"].append(result)
                print(json.dumps({"set": name, "total": result["ppc_all_quick_capacity"]["stream_bytes"],
                                  "gross_saved": result["ppc_all_quick_sharing"]["gross_saved_bytes"],
                                  "overlap": result["cross_level_overlap"]}), flush=True)
    finally:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
