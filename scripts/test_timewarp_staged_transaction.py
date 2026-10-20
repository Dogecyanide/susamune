"""Private staged-candidate transaction tests and actual-PPC fixture replay."""
from __future__ import annotations

import argparse
import ctypes as C
import json
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from test_timewarp_chunk_pool import DIRECTORY, Harness, Memory, Pool, plain, compressed_marker
from timewarp_multibank_pool import ROOT, MAP_NAMES, banks, inputs, new_pool, stats, sha
from timewarp_state_measure import FRAME, BLOCK_BYTES

MAX_STAGING = 0x2F0000
BASE_RECEIPT = ROOT / "build/timewarp-multibank-pool/validated/receipt.json"


class StageMemory(C.Structure):
    _fields_ = [("pool", C.POINTER(Memory)), ("staging", C.c_void_p), ("size", C.c_uint)]


class Token(C.Structure):
    _fields_ = [(name, C.c_uint) for name in ("epoch", "sequence", "slot", "generation", "tag")]


class StageHarness(Harness):
    def __init__(self, folder):
        extra = r'''
#include "timewarp/state_staged_transaction.h"
#include "susamune/mem2_map.h"
extern "C" {
__declspec(dllexport) int stAttach(TWStageMemory*m,unsigned e){return TWSAttach(m,e);}
__declspec(dllexport) int stValid(TWStageMemory*m){return TWSValid(m);}
__declspec(dllexport) int stBegin(TWStageMemory*m,unsigned s,unsigned g,unsigned t,TWStageToken*k){return TWSBegin(m,s,g,t,k);}
__declspec(dllexport) int stAppend(TWStageMemory*m,TWStageToken*k,const unsigned char*b,unsigned n){return TWSAppend(m,*k,b,n);}
__declspec(dllexport) int stAbort(TWStageMemory*m,TWStageToken*k){return TWSAbort(m,*k);}
__declspec(dllexport) int stPreflight(TWStageMemory*m,TWStageToken*k,unsigned r,unsigned p,unsigned c){return TWSPreflight(m,*k,r,p,c);}
__declspec(dllexport) int stCommit(TWStageMemory*m,TWStageToken*k,unsigned r,unsigned p,unsigned c,unsigned t){return TWSCommit(m,*k,r,p,c,t);}
__declspec(dllexport) unsigned stGeneration(TWStageMemory*m,unsigned i){return TWSControl(m)->generations[i];}
__declspec(dllexport) unsigned stStat(TWStageMemory*m,unsigned i){TWStageControl*c=TWSControl(m);const unsigned a[]={c->stagePeak,c->copiedBytes,c->finalHighWater,c->liveCount,TWS_CONTROL_OFFSET,sizeof(TWStageControl),TWS_INPUT_OFFSET,TWS_INPUT_BYTES,TWS_PLAN_OFFSET,TWS_REFS_OFFSET,TWS_CRC_OFFSET};return a[i];}
__declspec(dllexport) unsigned mapValue(unsigned i){const unsigned values[]={MAP_VALUES};return values[i];}
}
'''.replace("MAP_VALUES", ",".join(MAP_NAMES))
        super().__init__(folder, extra)
        mem, tok, u = C.POINTER(StageMemory), C.POINTER(Token), C.c_uint
        signatures = {"stAttach": [mem, u], "stValid": [mem], "stBegin": [mem, u, u, u, tok],
                      "stAppend": [mem, tok, C.c_void_p, u], "stAbort": [mem, tok],
                      "stPreflight": [mem, tok, u, u, u], "stCommit": [mem, tok, u, u, u, u],
                      "stGeneration": [mem, u], "stStat": [mem, u]}
        for name, args in signatures.items():
            getattr(self.lib, name).argtypes = args
        self.lib.stStat.restype = u


class StagePool(Pool):
    def __init__(self, harness, sizes=None, staging=MAX_STAGING, guest_bases=None):
        super().__init__(harness, sizes=sizes, guest_bases=guest_bases)
        self.stage_backing = (C.c_ubyte * (staging + 96))()
        C.memset(C.addressof(self.stage_backing), 0xBD, C.sizeof(self.stage_backing))
        pointer = (C.addressof(self.stage_backing) + 63) & ~31
        self.stage_memory = StageMemory(C.pointer(self.memory), pointer if staging else 0, staging)
        self.token = Token()
        assert self.stage("stAttach", 73)

    def stage(self, name, *args):
        return getattr(self.harness.lib, name)(C.byref(self.stage_memory), *args)

    def block(self, index):
        chunk = self.directory.chunks[index]
        capacity = sum(self.memory.sizes)
        if chunk.offset >= capacity:
            return C.string_at(self.stage_memory.staging + chunk.offset - capacity, chunk.size)
        return super().block(index)

    def states(self):
        assert self.stage("stValid")
        return [(FRAME + b"".join(self.block(i - 1) for i in s.ids[:s.count]), s.tag, s.raw)
                if s.count else None for s in self.directory.slots[:3]]

    def begin(self, slot, generation=None, tag=None):
        if generation is None: generation = self.stage("stGeneration", slot)
        if tag is None: tag = self.directory.slots[slot].tag
        return self.stage("stBegin", slot, generation, tag, C.byref(self.token))

    def append_stage(self, block):
        buffer = C.create_string_buffer(block)
        return self.stage("stAppend", C.byref(self.token), buffer, len(block))

    def finish(self, blocks, tag, preflight=False, checksum=None):
        raw, packed = sum(struct.unpack_from(">I", b)[0] for b in blocks), 8 + sum(map(len, blocks))
        if checksum is None: checksum = zlib.crc32(FRAME + b"".join(blocks))
        args = [C.byref(self.token), raw, packed, checksum]
        if not preflight: args.append(tag)
        return self.stage("stPreflight" if preflight else "stCommit", *args)

    def abort(self):
        return self.stage("stAbort", C.byref(self.token))

    def transaction(self, slot, blocks, tag, fail_after=None):
        if not self.begin(slot): return False
        for i, block in enumerate(blocks):
            if i == fail_after or not self.append_stage(block):
                assert self.abort()
                return False
        if fail_after == len(blocks) or not self.finish(blocks, tag):
            assert self.abort()
            return False
        return True

    def canaries(self):
        super().canaries()
        if self.stage_memory.size:
            start = C.addressof(self.stage_backing)
            pointer, size = self.stage_memory.staging, self.stage_memory.size
            end = start + C.sizeof(self.stage_backing)
            assert C.string_at(start, pointer - start) == b"\xBD" * (pointer - start)
            assert C.string_at(pointer + size, end - pointer - size) == b"\xBD" * (end - pointer - size)


class StagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-staged-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = StageHarness(cls.temp.name)
        cls.addClassCleanup(cls.harness.close)

    def seeded(self, sizes=None, staging=MAX_STAGING):
        pool = StagePool(self.harness, sizes=sizes, staging=staging)
        for slot in range(3):
            self.assertTrue(pool.put(slot, [compressed_marker(slot + 1), compressed_marker(7)], slot + 10))
        return pool

    def test_staging_migration_preserves_roots_and_publishes_generation_last(self):
        pool = self.seeded((DIRECTORY + 128, 128, 128, 128), 2048)
        expected = pool.states()
        candidate = [compressed_marker(i) for i in range(10, 15)]
        self.assertTrue(pool.begin(1))
        for block in candidate: self.assertTrue(pool.append_stage(block))
        self.assertGreater(pool.stage("stStat", 0), 0)
        self.assertEqual(pool.states(), expected)
        self.assertTrue(pool.finish(candidate, 80, preflight=True))
        self.assertEqual(pool.stage("stGeneration", 1), 1)
        self.assertTrue(pool.finish(candidate, 80))
        expected[1] = (FRAME + b"".join(candidate), 80, len(candidate) * BLOCK_BYTES)
        self.assertEqual(pool.states(), expected)
        self.assertEqual([pool.stage("stGeneration", i) for i in range(3)], [1, 2, 1])
        self.assertTrue(pool.call("valid"))
        pool.canaries()

    def test_abort_every_block_and_completed_candidate_preserves_all_roots(self):
        pool = self.seeded((DIRECTORY + 128, 128, 96, 96), 2048)
        expected = pool.states()
        candidate = [compressed_marker(i) for i in range(10, 15)]
        for target in range(3):
            for after in range(len(candidate) + 1):
                self.assertFalse(pool.transaction(target, candidate, 80, fail_after=after))
                self.assertEqual(pool.states(), expected)
                self.assertTrue(pool.call("valid"))
                self.assertEqual(pool.stage("stGeneration", target), 1)
                pool.canaries()

    def test_insufficient_staging_or_final_capacity_preserves_old_data(self):
        for staging in (0, 64, 2048):
            pool = self.seeded((DIRECTORY + 128, 128, 96, 96), staging)
            expected = pool.states()
            candidate = [compressed_marker(i) for i in range(10, 22)]
            self.assertFalse(pool.transaction(0, candidate, 80))
            self.assertEqual(pool.states(), expected)
            self.assertTrue(pool.call("valid"))
            pool.canaries()

    def test_wrong_generation_tag_token_checksum_and_size_refuse(self):
        pool = self.seeded()
        expected = pool.states()
        self.assertFalse(pool.begin(0, generation=9))
        self.assertFalse(pool.begin(0, tag=99))
        self.assertTrue(pool.begin(0))
        token = Token.from_buffer_copy(pool.token)
        self.assertTrue(pool.append_stage(compressed_marker(20)))
        for field in ("epoch", "sequence", "slot", "generation", "tag"):
            old = getattr(pool.token, field)
            setattr(pool.token, field, old + 1)
            self.assertFalse(pool.append_stage(compressed_marker(21)))
            self.assertFalse(pool.finish([compressed_marker(20)], 80))
            setattr(pool.token, field, old)
        self.assertFalse(pool.finish([compressed_marker(20)], 80, checksum=0))
        self.assertFalse(pool.finish([compressed_marker(20), compressed_marker(21)], 80))
        self.assertEqual(pool.states(), expected)
        self.assertTrue(pool.abort())
        self.assertTrue(pool.begin(0))
        current = pool.token
        pool.token = token
        self.assertFalse(pool.abort())
        pool.token = current
        self.assertTrue(pool.abort())
        pool.canaries()

    def test_corrupt_pending_or_old_payload_fails_full_preflight(self):
        pool = self.seeded((DIRECTORY + 128, 128, 128, 128), 2048)
        expected = pool.states()
        candidate = [compressed_marker(i) for i in range(10, 15)]
        self.assertTrue(pool.begin(0))
        for block in candidate: self.assertTrue(pool.append_stage(block))
        self.assertTrue(pool.finish(candidate, 90, preflight=True))
        for slot in (0, 3):
            chunk = pool.directory.chunks[pool.directory.slots[slot].ids[0] - 1]
            cap = sum(pool.memory.sizes)
            if chunk.offset >= cap: address = pool.stage_memory.staging + chunk.offset - cap
            else:
                offset, bank = chunk.offset, 0
                while offset >= pool.memory.sizes[bank]:
                    offset -= pool.memory.sizes[bank]; bank += 1
                address = pool.memory.banks[bank] + offset
            byte = C.c_ubyte.from_address(address + 8)
            byte.value ^= 1
            self.assertFalse(pool.finish(candidate, 90))
            self.assertEqual(pool.stage("stGeneration", 0), 1)
            byte.value ^= 1
        self.assertTrue(pool.abort())
        self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_hostile_bank_fragments_and_physical_order(self):
        for count in (4, 5):
            pool = StagePool(self.harness, sizes=(DIRECTORY + 160, 96, 224, 128, 160)[:count],
                             staging=1024, guest_bases=(5, 2, 1, 4, 3)[:count])
            expected = [None] * 3
            rng = random.Random(554 + count)
            for _ in range(150):
                target = rng.randrange(3)
                blocks = [struct.pack(">II", BLOCK_BYTES, 8 + value * 5) + bytes([value]) * (8 + value * 5)
                          for value in [rng.randrange(1, 25) for _ in range(rng.randrange(1, 6))]]
                tag = rng.randrange(1, 99999)
                if pool.transaction(target, blocks, tag):
                    expected[target] = (FRAME + b"".join(blocks), tag, len(blocks) * BLOCK_BYTES)
                self.assertEqual(pool.states(), expected)
                self.assertTrue(pool.call("valid"))
                pool.canaries()


def replay(folder):
    folder.mkdir(parents=True, exist_ok=True)
    base = json.loads(BASE_RECEIPT.read_text())
    for name in ("scripts/timewarp/state_chunk_pool.h", "scripts/timewarp/state_multibank_memory.h"):
        assert sha(ROOT / name) == base["source_sha256"][name], "Frozen allocator changed"
    files = ["scripts/timewarp/state_staged_transaction.h", "scripts/test_timewarp_staged_transaction.py",
             "scripts/timewarp/state_chunk_pool.h", "scripts/timewarp/state_multibank_memory.h",
             "src/qft_timer.cpp", "include/susamune/state_pool_memory.h"]
    before = {name: sha(ROOT / name) for name in files}
    harness = StageHarness(folder)
    results = []
    try:
        configs, transaction = banks(harness)
        groups, input_receipts = inputs()
        mixed = next(g for g in groups if g["name"] == "mixed")
        same = next(g for g in groups if g["name"] == "same-level")
        cases = [(mixed, f"late-Gelato-{i + 1}", same["states"][i]) for i in (1, 2)]
        cases += [(group, "next-set-first", groups[(i + 1) % len(groups)]["states"][0])
                  for i, group in enumerate(groups) if group["name"] != "mixed"]
        for group, label, candidate in cases:
            for config in configs[1:]:
                for target in range(3):
                    pool = StagePool(harness, sizes=[b["size"] for b in config["banks"]],
                                     guest_bases=[b["ppc_address"] for b in config["banks"]])
                    for slot, state in enumerate(group["states"]):
                        assert pool.put(slot, state["blocks"], state["expected"][1])
                    expected = pool.states()
                    if group["name"] == "mixed":
                        for after in range(len(candidate["blocks"]) + 1):
                            assert not pool.transaction(target, candidate["blocks"], 99, fail_after=after)
                            assert pool.states() == expected and pool.call("valid")
                            pool.canaries()
                    accepted = pool.transaction(target, candidate["blocks"], candidate["expected"][1])
                    after = list(expected)
                    if accepted: after[target] = candidate["expected"]
                    assert pool.states() == after and pool.call("valid")
                    assert [pool.stage("stGeneration", s) for s in range(3)] == [2 if accepted and s == target else 1 for s in range(3)]
                    pool.canaries()
                    row = {"initial_set": group["name"], "candidate": label, "layout": config["name"],
                           "target": target, "accepted": accepted, "stage_peak_bytes": pool.stage("stStat", 0),
                           "commit_copied_bytes": pool.stage("stStat", 1), "after": stats(pool),
                           "candidate_input": candidate["input"], "all_canonical_streams_and_tags_equal": True,
                           "generations_correct": True, "canaries_intact": True,
                           "abort_boundaries_proved": len(candidate["blocks"]) + 1 if group["name"] == "mixed" else 0}
                    results.append(row)
                    print(json.dumps({k: row[k] for k in ("initial_set", "candidate", "layout", "target", "accepted", "stage_peak_bytes")}), flush=True)
        directory = {"struct_bytes": C.sizeof(pool.directory), "input_table_offset": pool.stage("stStat", 6),
                     "input_table_reserved_bytes": pool.stage("stStat", 7), "plan_offset": pool.stage("stStat", 8),
                     "surviving_refs_offset": pool.stage("stStat", 9), "CRC_table_offset": pool.stage("stStat", 10),
                     "control_offset": pool.stage("stStat", 4), "control_bytes": pool.stage("stStat", 5),
                     "charged_directory_bytes": DIRECTORY}
    finally:
        harness.close()
    assert before == {name: sha(ROOT / name) for name in files}
    receipt = {"scope": "Private native allocator transaction using exact PPC Quick blocks. No production/PPC installation, game restore, I/O, power-failure recovery, lease activation or speed claim.",
               "base_capacity_receipt": {"path": str(BASE_RECEIPT), "sha256": sha(BASE_RECEIPT)},
               "source_sha256": before, "input_receipts": input_receipts, "directory_budget": directory,
               "transaction": transaction, "proof": "Preflight validates all roots, complete candidate CRC, generation/tag, surviving refs and final per-bank placements. Every final destination is at or below its source in a nonoverlapping logical map. Commit repeats preflight then performs source-ordered forward copies with no refusal/I/O path after old-root release, under one exclusive lease; root metadata publishes after moves.",
               "results": results}
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-staged-transaction")
    args, rest = parser.parse_known_args()
    if args.replay:
        folder = args.output.resolve()
        if not folder.is_relative_to((ROOT / "build").resolve()): parser.error("Use private build output")
        replay(folder)
    else:
        unittest.main(argv=[__file__] + rest)
