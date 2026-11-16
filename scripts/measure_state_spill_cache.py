"""Compare optional save spill-cache work using private real captures, never timings."""
import argparse
import hashlib
import json
from pathlib import Path

from test_state_quick_replay import ReplayTests
from test_state_store import StorePool

ROOT = Path(__file__).resolve().parents[1]
BANKS = [0xFF0000, 0x200000, 0x2C2000, 0x13E000, 0x70000]
STAGING = 0xF0000
EXTRA = 500 * 1024


def measure(captures):
    sources = [(name, (captures / (name + ".raw")).read_bytes(),
                (captures / (name + ".packed")).read_bytes())
               for name in ("gelato8", "bianco5", "noki1")]
    rows = []
    ReplayTests.setUpClass()
    test = ReplayTests()
    try:
        for slot, (name, raw, packed) in enumerate(sources):
            for extra in (0, EXTRA):
                store = StorePool(test.harness, test.codec, BANKS, STAGING)
                for seed, (_, saved_raw, saved_packed) in enumerate(sources):
                    kind = 0 if saved_packed.startswith(b"MSL4") else 1
                    assert store.put(seed, saved_raw, saved_packed, 100 + seed, kind)
                before = store.pool.states()
                status = test.prepare(store, slot, [raw], actual=True, deferred=True, extra=extra)
                row = {"extra_bytes": extra, "stage": name, "initial_status": status,
                       "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
                       "captured_packed_sha256": hashlib.sha256(packed).hexdigest()}
                assert store.pool.states() == before
                if status == 2:
                    row["refined_retained"] = bool(test.refine(store, 7 ^ (1 << slot)))
                    status = test.prepare(store, slot, [raw], actual=True, deferred=True, extra=extra)
                row["status"] = status
                assert status == 0, (name, extra, status)
                keys = ("cached_bytes", "spilled_blocks", "replay_raw_bytes", "moved_bytes",
                        "prepare_encode_calls", "raw_checksum_calls")
                row.update(zip(keys, (test.codec.lib.replayStat(i) for i in range(6))))
                calls = test.codec.lib.replayStat(4)
                test.publish(store, slot)
                row["commit_encode_calls"] = test.codec.lib.replayStat(4) - calls
                row["all_three_roundtrip_and_filters"] = True
                store.guards()
                rows.append(row)
                print(json.dumps(row), flush=True)
        return {"pool_bytes": sum(BANKS), "pool_bank_bytes": BANKS,
                "baseline_candidate_bytes": STAGING, "plan_bytes_host": test.codec.lib.replaySize(),
                "extra_cache_bytes": EXTRA, "rows": rows,
                "scope": "Host work counts and byte-exact protected restores only. No Wii elapsed-time claim. "
                         "Physical extra banks remain unallocated. Same-Wii improvement of at least two game "
                         "frames is required to retain the save allocation."}
    finally:
        ReplayTests.doClassCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=ROOT / "build/pr48-state-overwrite/captures")
    parser.add_argument("--out", type=Path, default=ROOT / "build/pr48-sd-trace/r12-performance/save-spill-candidate.json")
    args = parser.parse_args()
    report = measure(args.captures)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
