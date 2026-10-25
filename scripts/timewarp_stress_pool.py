"""Replay Bianco5/Pinna3 in private multibank and staged allocator proofs."""
import json
from pathlib import Path

import timewarp_multibank_pool as measurement
from test_timewarp_staged_transaction import StageHarness, StagePool

ROOT = measurement.ROOT


def main():
    folder = ROOT / "build/timewarp-staged-transaction/stress"
    folder.mkdir(parents=True, exist_ok=True)
    measurement.INPUTS = (ROOT / "build/timewarp-stress-measure/receipt.json",)
    names = ("scripts/timewarp/state_chunk_pool.h", "scripts/timewarp/state_multibank_memory.h",
             "scripts/timewarp/state_staged_transaction.h", "scripts/timewarp_stress_pool.py",
             "src/qft_timer.cpp")
    before = {name: measurement.sha(ROOT / name) for name in names}
    harness = StageHarness(folder)
    bank_rows, stage_rows = [], []
    try:
        configs, transaction = measurement.banks(harness)
        groups, receipts = measurement.inputs()
        for index, group in enumerate(groups):
            candidate = groups[1 - index]["states"][0]
            for config in configs:
                row = measurement.replay(harness, config, group, [(groups[1 - index]["name"], candidate)])
                bank_rows.append(row)
                print(json.dumps({"multibank_set": group["name"], "layout": config["name"],
                                  "fits": row["all_three_fit"], "extent": row["compacted"]["occupied_extent_bytes"]}), flush=True)
                if not row["all_three_fit"]: continue
                for target in range(3):
                    pool = StagePool(harness, sizes=[b["size"] for b in config["banks"]],
                                     guest_bases=[b["ppc_address"] for b in config["banks"]])
                    for slot, state in enumerate(group["states"]):
                        assert pool.put(slot, state["blocks"], state["expected"][1])
                    expected = pool.states()
                    for after in range(len(candidate["blocks"]) + 1):
                        assert not pool.transaction(target, candidate["blocks"], 99, fail_after=after)
                        assert pool.states() == expected and pool.call("valid")
                        pool.canaries()
                    accepted = pool.transaction(target, candidate["blocks"], candidate["expected"][1])
                    final = list(expected)
                    if accepted: final[target] = candidate["expected"]
                    assert pool.states() == final and pool.call("valid")
                    assert [pool.stage("stGeneration", s) for s in range(3)] == [2 if accepted and s == target else 1 for s in range(3)]
                    pool.canaries()
                    result = {"initial_set": group["name"], "candidate": groups[1 - index]["name"],
                              "target": target, "layout": config["name"], "accepted": accepted,
                              "stage_peak_bytes": pool.stage("stStat", 0), "commit_copied_bytes": pool.stage("stStat", 1),
                              "after": measurement.stats(pool), "abort_boundaries_proved": len(candidate["blocks"]) + 1,
                              "canonical_bytes_tags_generations_correct": True, "canaries_intact": True}
                    stage_rows.append(result)
                    print(json.dumps({k: result[k] for k in ("initial_set", "layout", "target", "accepted", "stage_peak_bytes")}), flush=True)
    finally:
        harness.close()
    assert before == {name: measurement.sha(ROOT / name) for name in names}
    receipt = {"scope": "Private native allocators using exact PPC stress streams. Cross-set replacements measure storage only; no owner-compatible game restore, lease activation or Wii speed claim.",
               "source_sha256": before, "input_receipts": receipts, "bank_layouts": configs,
               "transaction": transaction, "multibank": bank_rows, "staged": stage_rows,
               "base_receipt_sha256": measurement.sha(ROOT / "build/timewarp-staged-transaction/receipt.json")}
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__": main()
