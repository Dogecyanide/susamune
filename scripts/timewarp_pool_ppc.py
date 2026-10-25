"""Execute the actual producer, staged pool and reader in an owned game-free PPC DOL."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

from elftools.elf.elffile import ELFFile
from timewarp_cold_pilot import Pilot
from timewarp_state_measure import ROOT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(folder, source=None, include_root=None):
    source = source or ROOT / "scripts/timewarp/ppc_pool_bench.cpp"
    script = folder / "bench.ld"
    script.write_text('ENTRY(_start)\nSECTIONS { . = 0x80004000; '
        '.text : { *(.text.start) *(.text*) *(.foxtrot.text*) . = ALIGN(32); } '
        '.rodata : { *(.rodata*) *(.foxtrot.rodata*) . = ALIGN(32); } '
        '.data : { *(.data*) *(.foxtrot.data*) *(.got*) . = ALIGN(32); } '
        '.bss : { *(.bss*) *(.foxtrot.bss*) *(COMMON) . = ALIGN(32); } '
        'ASSERT(. < 0x80080000, "bench overlaps captured input") '
        '/DISCARD/ : { *(.eh_frame*) *(.comment*) } }\n')
    obj, elf, dol = [folder / ("bench." + suffix) for suffix in ("o", "elf", "dol")]
    commands = [[ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi", "-O2",
        "-fno-exceptions", "-fno-rtti", "-fno-builtin", "-ffunction-sections", "-fdata-sections",
        "-fno-unwind-tables", "-nostdlib", "-I", include_root or ROOT / "include", "-c", source, "-o", obj],
        [ROOT / "toolchain/ld.lld.exe", "--gc-sections", "-T", script, obj, "-o", elf],
        [sys.executable, ROOT / "scripts/elf2dol.py", elf, dol]]
    for command in commands:
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True)
        if result.returncode: raise RuntimeError(result.stdout + result.stderr)
    with elf.open("rb") as stream:
        sections = [{"name": s.name, "address": s["sh_addr"], "size": s["sh_size"]}
                    for s in ELFFile(stream).iter_sections() if s["sh_flags"] & 2]
    return dol, {"commands": [[str(x) for x in command] for command in commands],
                 "elf_sha256": sha(elf), "dol_sha256": sha(dol), "sections": sections}


class PoolPilot(Pilot):
    MAGIC = b"TWPB"

    def command(self, cmd, slot=0, size=0, tag=0, expected_status=0):
        self.write(self.CONTROL + 48, struct.pack(">3I", slot, size, tag))
        self.write(self.CONTROL + 8, struct.pack(">I", cmd))
        self.sequence += 1
        began = time.perf_counter()
        self.write(self.CONTROL + 4, struct.pack(">I", self.sequence))
        deadline = time.monotonic() + 90
        while struct.unpack(">I", self.read(self.CONTROL + 12, 4))[0] != self.sequence:
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(f"Owned PPC pool command {cmd} timed out")
            time.sleep(0.005)
        elapsed = time.perf_counter() - began
        words = struct.unpack(">23I", self.read(self.CONTROL, 92))
        if words[9] != 1: raise RuntimeError(f"PPC pool canary failed: {words}")
        row = {"command": cmd, "slot": slot, "status": words[4], "host_seconds_to_ack": elapsed,
            "packed": words[5], "raw": words[6], "adler": words[7], "crc": words[8],
            "occupied": words[10], "candidate_blocks": words[15], "stage_peak": words[16],
            "commit_copied_bytes": words[17], "generations": list(words[18:21]),
            "live_blocks": words[21], "aligned_block_bytes": words[22]}
        if words[4] != expected_status: raise RuntimeError(f"Unexpected PPC pool status: {row}")
        return row

    def encoded(self, slot, state):
        offset, parts, rows = 0, [], []
        while offset < len(state["packed"]):
            row = self.command(6, slot, size=offset)
            assert row["raw"] == len(state["packed"])
            parts.append(self.read(self.OUTPUT, row["packed"]))
            offset += row["packed"]; rows.append(row)
        assert b"".join(parts) == state["packed"]
        return {"windows": rows, "packed_bytes": offset, "exact": True}

    def decode(self, slot, state, protected=False):
        row = self.command(7, slot, tag=int(protected))
        expected = bytearray(state["raw"])
        if protected: expected[0x4000d:0x4000d + 31] = b"\xa7" * 31
        assert self.read(self.INPUT, len(expected)) == expected
        return row

    def produce(self, target, state):
        begin = self.command(2, target)
        self.write(self.INPUT, state["raw"])
        encoded = self.command(3, target, len(state["raw"]), state["tag"])
        assert self.read(self.INPUT, len(state["raw"])) == state["raw"]
        assert encoded["packed"] == len(state["packed"])
        candidate = self.encoded(3, state)
        decoded = self.decode(3, state)
        return {"begin": begin, "encode": encoded, "candidate_exact": candidate, "candidate_decode": decoded}


def load_set(receipt, name):
    group = next(g for g in json.loads(receipt.read_text())["sets"] if g["name"] == name)
    states = []
    for index, row in enumerate(group["slots"]):
        raw, packed = Path(row["raw_path"]), Path(row["ppc_quick"]["path"])
        assert sha(raw) == row["raw_sha256"] and sha(packed) == row["ppc_quick"]["sha256"]
        states.append({"raw": raw.read_bytes(), "packed": packed.read_bytes(), "tag": 100 + index,
                       "input": {"raw": str(raw), "raw_sha256": sha(raw), "packed": str(packed), "packed_sha256": sha(packed)}})
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-pool-ppc")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.exists():
        parser.error("Use a new private build directory")
    folder.mkdir(parents=True)
    files = ["src/state_codec.cpp", "src/state_crc.cpp", "include/susamune/state_crc.h",
             "include/susamune/state_crc.hxx", "include/susamune/state_codec.hxx", "scripts/timewarp/ppc_pool_bench.cpp",
             "scripts/timewarp_pool_ppc.py", "src/qft_timer.cpp"]
    files += ["include/susamune/" + name for name in ("state_multibank_memory.h", "state_chunk_pool.h",
        "state_staged_transaction.h", "state_root_reader.h", "state_quick_producer.hxx")]
    before = {name: sha(ROOT / name) for name in files}
    report = {"scope": "Actual production PPC encoder, staged allocator and immutable-root decoder in a private standalone Dolphin DOL. Real four-bank lengths and logical order at isolated fake-VMEM addresses, not Wii mappings, ARM cache ownership, game restore or Wii timing.",
              "source_sha256": before, "sets": [], "replacements": [],
              "banks": [(0x70010000,0xff0000),(0x71800000,0x200000),(0x71100000,0xc2000),(0x71b00000,0x13e000)],
              "staging": (0x71200000,0x2f0000),
              "timing_limit": "Host wall time until an owned Dolphin command acknowledges, including poll latency; isolated algorithm only, unlimited emulation speed and no gameplay."}
    pilot = None
    try:
        dol, report["build"] = build(folder)
        pilot = PoolPilot(args.dolphin, folder, dol, report, 1)
        report["runtime"] = pilot.evidence
        mixed_receipt = ROOT / "build/cross-level/current-ppc/receipt.json"
        noki_receipt = ROOT / "build/timewarp-noki1-measure/receipt.json"
        mixed = load_set(mixed_receipt, "mixed")
        noki = load_set(noki_receipt, "noki1")
        gelato = load_set(mixed_receipt, "same-level")
        report["inputs"] = {str(p): sha(p) for p in (mixed_receipt, noki_receipt)}
        with pilot:
            assert struct.unpack(">I", pilot.read(pilot.CONTROL + 16, 4))[0] == 0
            for label, states in (("noki1", noki), ("mixed", mixed)):
                pilot.command(1)
                saves = []
                for slot, state in enumerate(states):
                    row = pilot.produce(slot, state)
                    row["commit"] = pilot.command(4)
                    row["all_prior_exact"] = [pilot.encoded(i, prior) for i, prior in enumerate(states[:slot + 1])]
                    saves.append(row)
                    print(json.dumps({"PPC_save": label, "slot": slot, "occupied": row["commit"]["occupied"],
                                      "encode_host_seconds": row["encode"]["host_seconds_to_ack"]}), flush=True)
                decodes = [{"ordinary": pilot.decode(i, state), "protected": pilot.decode(i, state, True)}
                           for i, state in enumerate(states)]
                report["sets"].append({"name": label, "inputs": [s["input"] for s in states], "saves": saves, "decodes": decodes})
            # Every replacement starts with the same three exact mixed roots.
            for target, candidate in ((0, gelato[1]), (1, gelato[2]), (2, gelato[1])):
                if target:
                    pilot.command(1)
                    for slot, state in enumerate(mixed):
                        pilot.produce(slot, state); pilot.command(4)
                row = pilot.produce(target, candidate)
                row["all_old_exact_before_commit"] = [pilot.encoded(i, state) for i, state in enumerate(mixed)]
                row["abort"] = pilot.command(5)
                row["all_old_exact_after_abort"] = [pilot.encoded(i, state) for i, state in enumerate(mixed)]
                row["retry"] = pilot.produce(target, candidate)
                row["commit"] = pilot.command(4)
                final = list(mixed); final[target] = candidate
                row["all_final_exact"] = [pilot.encoded(i, state) for i, state in enumerate(final)]
                row["all_final_decode"] = [pilot.decode(i, state, i == target) for i, state in enumerate(final)]
                report["replacements"].append({"target": target, "candidate": candidate["input"], "proof": row})
                print(json.dumps({"PPC_replacement": target, "occupied": row["commit"]["occupied"],
                                  "stage_peak": row["commit"]["stage_peak"]}), flush=True)
        assert before == {name: sha(ROOT / name) for name in files}
        report["passed"] = True
    finally:
        if pilot and pilot.process and pilot.process.poll() is None: pilot.__exit__()
        (folder / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
