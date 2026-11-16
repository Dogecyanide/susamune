"""Measure lossless input packing and ten-minute budgets; never edits a ghost or map."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import struct
from validate_ghost import validate_ghost

BLOCK = 64

def pack_rows(raw: bytes, stride: int) -> tuple[bytes, list[int]]:
    if not 1 <= stride <= 24 or len(raw) % stride:
        raise ValueError("invalid stride or partial row")
    data = bytearray()
    index = []
    mask_bytes = (stride + 7) // 8
    for start in range(0, len(raw), BLOCK * stride):
        block = raw[start:start + BLOCK * stride]
        previous = bytes(stride)
        delta = bytearray()
        for off in range(0, len(block), stride):
            row = block[off:off + stride]
            mask = sum(1 << i for i in range(stride) if row[i] != previous[i])
            delta += mask.to_bytes(mask_bytes, "big")
            delta += bytes(row[i] for i in range(stride) if mask & (1 << i))
            previous = row
        compact = len(delta) < len(block)
        payload = delta if compact else block
        index.append(len(data))
        data += struct.pack(">HBBH", len(block) // stride, int(compact), stride, len(payload))
        data += payload
    return bytes(data), index

def unpack_rows(data: bytes) -> bytes:
    result = bytearray()
    off = 0
    while off < len(data):
        if len(data) - off < 6:
            raise ValueError("short block")
        count, mode, stride, size = struct.unpack_from(">HBBH", data, off)
        off += 6
        if not 1 <= count <= BLOCK or not 1 <= stride <= 24 or mode > 1 or size > len(data) - off:
            raise ValueError("invalid block")
        end = off + size
        if mode == 0:
            if size != count * stride:
                raise ValueError("raw length")
            result += data[off:end]
            off = end
            continue
        previous = bytearray(stride)
        mask_bytes = (stride + 7) // 8
        for _ in range(count):
            if end - off < mask_bytes:
                raise ValueError("short mask")
            mask = int.from_bytes(data[off:off + mask_bytes], "big")
            off += mask_bytes
            if mask >> stride:
                raise ValueError("invalid mask")
            for i in range(stride):
                if mask & (1 << i):
                    if off == end:
                        raise ValueError("short delta")
                    previous[i] = data[off]
                    off += 1
            result += previous
        if off != end:
            raise ValueError("block trailing data")
    return bytes(result)

def packed_size(raw: bytes, stride: int) -> int:
    packed, index = pack_rows(raw, stride)
    assert unpack_rows(packed) == raw
    # Four-byte directory count and one four-byte offset per block.
    return len(packed) + 4 + 4 * len(index)

def audit_file(path: Path) -> dict:
    data = path.read_bytes()
    ghost = validate_ghost(data)
    result = {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
              "version": ghost["version"], "file_bytes": len(data),
              "duration_qf": ghost["duration_qf"]}
    if ghost["version"] < 5:
        result["input_rows"] = 0
        return result
    # The validator already checked the header extents and the complete file.
    pose_offset, pose_size = struct.unpack_from(">II", data, 196)
    start = pose_offset + pose_size
    if data[start:start + 4] != b"SGTI":
        raise ValueError("unexpected teaching offset")
    count = struct.unpack_from(">I", data, start + 8)[0]
    stride = 16 if ghost["version"] == 5 else 24
    raw = data[start + 32:start + 32 + count * stride]
    encoded_size = packed_size(raw, stride)
    result.update(input_rows=count, input_bytes=len(raw), block_delta_bytes=encoded_size,
                  saved_bytes=len(raw) - encoded_size,
                  saved_percent=round(100 * (1 - encoded_size / len(raw)), 2) if raw else 0)
    return result

def budget() -> dict:
    ticks = 71928 + 1  # Include an observation at both duration endpoints.
    frames = 17983
    capacity = 864000
    candidate = 0x935e0000 - 0x93400000
    def worst(n, stride):
        return n * stride + math.ceil(n / BLOCK) * 10 + 4
    raw = ticks * 24
    indexed = worst(ticks, 24)
    factored = ticks * 16 + frames * 12
    return {"candidate_unclaimed_bytes": candidate, "physical_bytes_reclaimed": 0,
            "input_capacity_per_track": capacity, "tracks_required": 2,
            "ten_minute_qf_observations": ticks,
            "naive_per_track": raw,
            "extra_for_two_naive_tracks": 2 * (raw - capacity),
            "candidate_remainder_naive": candidate - 2 * (raw - capacity),
            "block_codec_worst_per_track": indexed,
            "candidate_remainder_block_codec": candidate - 2 * (indexed - capacity),
            "factored_16_per_tick_12_per_visual_frame": factored,
            "factored_plus_12_per_frame_action_speed": factored + frames * 12,
            "factored_plus_16_per_frame_action_speed_floor": factored + frames * 16,
            "factored_at_36000_visual_frames": ticks * 16 + 36000 * 12,
            "factored_at_36000_with_action_speed": ticks * 16 + 36000 * 24,
            "capacity_each_if_candidate_split_equally": capacity + candidate // 2,
            "existing_transfer_bytes": 0x13e000,
            "v10_noninput_max_file_bytes": 1297936 - capacity,
            "naive_larger_file_bytes": raw + 1297936 - capacity,
            "block_worst_larger_file_bytes": indexed + 1297936 - capacity,
            "expanded_input_total_bytes": capacity * 2 + candidate}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kernel-map", type=Path)
    parser.add_argument("ghosts", nargs="*", type=Path)
    args = parser.parse_args()
    rng = random.Random(47)
    cases = 0
    for stride in (16, 24):
        for n in (0, 1, 63, 64, 65, 36000, 71929):
            for raw in (bytes(n * stride), rng.randbytes(n * stride)):
                size = packed_size(raw, stride)
                assert size <= n * stride + math.ceil(n / BLOCK) * 10 + 4
                cases += 1
    files = []
    for path in args.ghosts:
        try:
            files.append(audit_file(path))
        except Exception as error:
            files.append({"path": str(path), "error": str(error)})
    result = {"scope": "Host-only feasibility experiment. Existing frame data is not evidence of future QF compressibility or Wii CPU cost.",
              "synthetic_roundtrips": cases, "budget": budget(), "files": files}
    if args.kernel_map:
        contents = args.kernel_map.read_bytes()
        sections = {name: (int(address, 16), int(size, 16)) for name, address, size in
                    re.findall(r"^\.(text|rodata|data|bss)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)",
                               contents.decode(), re.MULTILINE)}
        result["kernel"] = {"path": str(args.kernel_map.resolve()), "sha256": hashlib.sha256(contents).hexdigest(),
            "sections": sections,
            "text_hole_bytes": 0x12f60000 - sum(sections["text"]),
            "data_hole_bytes": 0x12fe0000 - sum(sections["bss"]),
            "stack_tail_ungranted_bytes": 0x12ff0000 - 0x12fe4400}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
