"""Replay exact PPC streams through the private, discontiguous block allocator."""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import zlib

from test_timewarp_chunk_pool import DIRECTORY, Harness, Pool
from timewarp_state_measure import quick_blocks

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (ROOT / "build/timewarp-state-measure/ppc-receipt.json",
          ROOT / "build/cross-level/current-ppc/receipt.json")
MAP_NAMES = (
    "SUSAMUNE_MEM2_SNAPSHOT_PPC_BASE", "SUSAMUNE_MEM2_SNAPSHOT_SIZE",
    "SUSAMUNE_STATE_POOL_EXTRA_PPC_BASE", "SUSAMUNE_STATE_POOL_EXTRA_SIZE",
    "SUSAMUNE_STATE_STAGING_PPC_BASE", "SUSAMUNE_STATE_STAGING_SIZE",
    "SUSAMUNE_GHOST_FILE_TRANSFER_PPC_BASE", "SUSAMUNE_GHOST_FILE_TRANSFER_SIZE",
    "NIN_MEM2_DI_SCRATCH_PPC_BASE", "NIN_MEM2_DI_SCRATCH_SIZE",
    "NIN_MEM2_DI_SCRATCH_RUNTIME_SIZE", "SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE",
    "SUSAMUNE_CONSOLE_STATE_CODEC_PPC_BASE",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def banks(harness):
    harness.lib.mapValue.argtypes = [C.c_uint]
    harness.lib.mapValue.restype = C.c_uint
    values = {name: harness.lib.mapValue(i) for i, name in enumerate(MAP_NAMES)}
    a, sa, b, sb, staging, ss, ghost, sg, di, sd, runtime, work, codec = values.values()
    shared = ss + sg - 0x200000
    proposed = [(a, sa), (b, sb), (staging + shared, ss - shared), (ghost, sg),
                (di + runtime, sd - runtime)]
    assert [size for _, size in proposed] == [0xFF0000, 0x200000, 0xC2000, 0x13E000, 0x70000]
    assert shared == 0x33E000 and shared - work == 3080192
    ranges = proposed + [(staging, shared), (di, runtime), (codec, work)]
    for i, (base, size) in enumerate(ranges):
        assert base % 32 == size % 32 == 0
        assert all(base + size <= other or other + length <= base for other, length in ranges[:i])
    configs = [{"name": name, "banks": [{"ppc_address": address, "physical_address": address - 0x80000000,
                                            "size": size} for address, size in proposed[:count]],
                "capacity_bytes": sum(size for _, size in proposed[:count])}
               for name, count in (("current-two", 2), ("shared-transfer-four", 4), ("plus-DI-tail-five", 5))]
    return configs, {"compiled_constants": values, "shared_transaction_address": staging,
                    "shared_transaction_bytes": shared, "second_codec_workspace_bytes": work,
                    "candidate_staging_after_second_workspace_bytes": shared - work,
                    "primary_codec_workspace_address": codec,
                    "scope": "Proposed banks require exclusive permanent pool ownership after acknowledged lease activation. DI tail additionally requires the one-way runtime cap. No bank is activated by this harness."}


def inputs():
    sets, files = [], []
    for path in INPUTS:
        source = json.loads(path.read_text())
        files.append({"path": str(path), "sha256": sha(path)})
        for group in source["sets"]:
            states = []
            for row in group["slots"]:
                encoded_path, raw_path = Path(row["ppc_quick"]["path"]), Path(row["raw_path"])
                encoded, raw = encoded_path.read_bytes(), raw_path.read_bytes()
                assert hashlib.sha256(encoded).hexdigest() == row["ppc_quick"]["sha256"]
                assert hashlib.sha256(raw).hexdigest() == row["raw_sha256"]
                blocks = quick_blocks(encoded, raw)
                tag = zlib.crc32(row["raw_sha256"].encode())
                states.append({"blocks": blocks, "expected": (encoded, tag, len(raw)), "raw": raw,
                               "input": {"path": str(encoded_path), "sha256": row["ppc_quick"]["sha256"],
                                         "raw_path": str(raw_path), "raw_sha256": row["raw_sha256"],
                                         "packed_bytes": len(encoded), "raw_bytes": len(raw)}})
            sets.append({"name": group["name"], "states": states})
            print(json.dumps({"validated_actual_PPC_streams": group["name"]}), flush=True)
    return sets, files


def new_pool(harness, config):
    return Pool(harness, sizes=[b["size"] for b in config["banks"]],
                guest_bases=[b["ppc_address"] for b in config["banks"]])


def stats(pool):
    result = pool.stats()
    cursor, used = 0, []
    for i in range(pool.memory.count):
        size = pool.memory.sizes[i]
        chunks = [d for d in pool.directory.chunks if d.refs and cursor <= d.offset < cursor + size]
        rounded = sum((d.size + 31) & ~31 for d in chunks)
        directory = DIRECTORY if i == 0 else 0
        extent = max(0, min(size, pool.directory.high_water - cursor))
        used.append({"logical_bank": i, "payload_bytes": sum(d.size for d in chunks),
                     "aligned_block_bytes": rounded, "directory_bytes": directory,
                     "occupied_extent_bytes": extent,
                     "tail_and_fragment_bytes": extent - rounded - directory,
                     "outside_extent_bytes": size - extent})
        cursor += size
    result["banks"] = used
    return result


def attempt(pool, slot, candidate):
    before = pool.states()
    assert pool.call("begin", slot)
    accepted = True
    peak = pool.directory.high_water
    appended = 0
    for block in candidate["blocks"]:
        if not pool.append(block):
            accepted = False
            break
        appended += 1
        peak = max(peak, pool.directory.high_water)
    _, tag, raw = candidate["expected"]
    if accepted:
        assert pool.call("commit", raw, len(candidate["expected"][0]), tag)
    else:
        assert pool.call("abortSave")
    after = list(before)
    if accepted:
        after[slot] = candidate["expected"]
    assert pool.states() == after
    assert pool.call("compact")
    assert pool.states() == after
    pool.canaries()
    return {"accepted": accepted, "candidate_blocks_appended": appended,
            "candidate_blocks": len(candidate["blocks"]), "peak_extent_bytes": peak,
            "all_old_slots_preserved_on_refusal": not accepted,
            "other_slots_and_metadata_preserved": True, "after": stats(pool)}


def independent_placement(pool, states):
    cursor, rounded = DIRECTORY, 0
    for slot, state in enumerate(states):
        for index, block in enumerate(state["blocks"]):
            size = (len(block) + 31) & ~31
            offset = pool.call("placement", cursor, size)
            if offset == 0xFFFFFFFF:
                return {"fits": False, "refused_slot": slot, "refused_block": index,
                        "extent_before_refusal_bytes": cursor}
            cursor = offset + size
            rounded += size
    return {"fits": True, "occupied_extent_bytes": cursor,
            "bank_boundary_waste_bytes": cursor - DIRECTORY - rounded,
            "remaining_bytes": sum(pool.memory.sizes) - cursor}


def replay(harness, config, group, extra_candidates):
    pool = new_pool(harness, config)
    states = group["states"]
    admitted = [attempt(pool, i, state) for i, state in enumerate(states)]
    fits = all(a["accepted"] for a in admitted)
    compacted = stats(pool)
    expected = pool.states()
    checks = []
    for target in range(3):
        candidate = states[(target + 1) % 3]
        for after in (0, len(candidate["blocks"]) // 2, len(candidate["blocks"]) - 1):
            assert not pool.put(target, candidate["blocks"], 999, fail_after=after)
            assert pool.states() == expected
            assert pool.call("compact") and pool.states() == expected
            pool.canaries()
        if admitted[target]["accepted"]:
            result = attempt(pool, target, states[target])
            assert result["accepted"] and pool.states() == expected
            checks.append({"target": target, "same_stream_replacement": result})
    replacements = []
    if fits:
        for label, candidate in extra_candidates:
            for target in range(3):
                # Each replacement starts from the same three committed states.
                pool = new_pool(harness, config)
                for slot, state in enumerate(states):
                    assert attempt(pool, slot, state)["accepted"]
                result = attempt(pool, target, candidate)
                final_states = list(states)
                final_states[target] = candidate
                final_pool = new_pool(harness, config)
                final_admission = [attempt(final_pool, slot, state)["accepted"] for slot, state in enumerate(final_states)]
                published = {b for s in states for b in s["blocks"]}
                novel = set(candidate["blocks"]) - published
                replacements.append({"candidate": label, "target": target, **result,
                                     "additional_unique_blocks": len(novel),
                                     "additional_unique_payload_bytes": sum(map(len, novel)),
                                     "additional_aligned_payload_bytes": sum((len(b) + 31) & ~31 for b in novel),
                                     "final_set_fits_when_created_in_empty_pool": all(final_admission),
                                     "final_empty_pool_extent_bytes": final_pool.directory.high_water})
    return {"set": group["name"], "layout": config["name"],
            "inputs": [s["input"] for s in states], "slot_admissions": admitted,
            "all_three_fit": fits, "compacted": compacted,
            "independent_blocks_without_sharing": independent_placement(pool, states),
            "canonical_stream_bytes_and_metadata_tags_equal": True,
            "every_input_independently_decoded": True, "canaries_intact": True,
            "injected_abort_preserves_slots": True, "same_stream_replacements": checks,
            "additional_captured_replacements": replacements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-multibank-pool")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()):
        parser.error("Use a private build output directory")
    folder.mkdir(parents=True, exist_ok=True)
    tracked = ["scripts/timewarp/state_chunk_pool.h", "scripts/timewarp/state_multibank_memory.h",
               "scripts/test_timewarp_chunk_pool.py", "scripts/timewarp_multibank_pool.py",
               "include/susamune/state_pool_memory.h", "include/susamune/state_slot_pool.h",
               "include/susamune/mem2_map.h", "scripts/timewarp/transfer_lease.h", "src/qft_timer.cpp"]
    before = {name: sha(ROOT / name) for name in tracked}
    extra = '\n#include "susamune/mem2_map.h"\nextern "C" __declspec(dllexport) unsigned mapValue(unsigned i){const unsigned values[]={' + ','.join(MAP_NAMES) + '};return values[i];}\n'
    harness = Harness(folder, extra)
    results = []
    try:
        configs, transaction = banks(harness)
        groups, input_receipts = inputs()
        same = next(g for g in groups if g["name"] == "same-level")
        for group in groups:
            extras = [(f"same-level-slot{i + 1}", same["states"][i]) for i in (1, 2)] if group["name"] == "mixed" else []
            for config in configs:
                result = replay(harness, config, group, extras)
                results.append(result)
                print(json.dumps({"set": group["name"], "layout": config["name"],
                                  "fits": result["all_three_fit"],
                                  "extent": result["compacted"]["occupied_extent_bytes"],
                                  "remaining": result["compacted"]["free_tail_bytes"]}), flush=True)
    finally:
        harness.close()
    assert before == {name: sha(ROOT / name) for name in tracked}, "Inputs changed during measurement"
    receipt = {"scope": "Native C allocator over exact PPC-produced Quick blocks. This measures bank-aware capacity and in-memory publication, not PPC allocator speed, whole-game restore, full StoredState ownership, SD transfer, or lease activation.",
               "source_sha256": before, "input_receipts": input_receipts,
               "bank_layouts": configs, "transient_transaction_separate_from_pool": transaction,
               "policy": "Keep all three committed roots through candidate acquisition. Refuse and abort without reclaiming old roots; compact only under exclusive ownership.",
               "results": results}
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
