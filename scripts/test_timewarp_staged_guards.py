"""Targeted guard tests against the separately recorded staged replay."""
import ctypes as C
import json
from pathlib import Path
import tempfile
import unittest

from test_timewarp_chunk_pool import DIRECTORY, compressed_marker
from test_timewarp_staged_transaction import StageHarness, StagePool, Token
from timewarp_multibank_pool import ROOT, sha
from timewarp_state_measure import FRAME, BLOCK_BYTES


class Guards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-stage-guards-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = StageHarness(cls.temp.name)
        cls.addClassCleanup(cls.harness.close)

    def pool(self):
        pool = StagePool(self.harness, sizes=(DIRECTORY + 128, 128, 128, 128), staging=2048)
        for i in range(3):
            self.assertTrue(pool.put(i, [compressed_marker(i + 1), compressed_marker(7)], i + 10))
        return pool

    def candidate(self, pool):
        blocks = [compressed_marker(i) for i in range(10, 15)]
        self.assertTrue(pool.begin(0))
        for block in blocks: self.assertTrue(pool.append_stage(block))
        return blocks

    def test_staging_overlap_alignment_and_output_descriptor_alias(self):
        pool = self.pool()
        expected = pool.states()
        original = pool.stage_memory.staging
        for bad in (original + 1, pool.memory.banks[0] + 32):
            pool.stage_memory.staging = bad
            self.assertFalse(pool.stage("stValid"))
            self.assertFalse(pool.begin(0, 1, 10))
        pool.stage_memory.staging = original
        for alias in (C.byref(pool.stage_memory), C.byref(pool.memory)):
            self.assertFalse(pool.stage("stBegin", 0, 1, 10, C.cast(alias, C.POINTER(Token))))
        self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_commit_rebuilds_poisoned_plan_and_preserves_reader_table(self):
        pool = self.pool()
        expected = pool.states()
        table = pool.memory.banks[0] + pool.stage("stStat", 6)
        table_size = pool.stage("stStat", 7)
        C.memset(table, 0xDC, table_size)
        blocks = self.candidate(pool)
        self.assertTrue(pool.finish(blocks, 50, preflight=True))
        C.memset(pool.memory.banks[0] + pool.stage("stStat", 8), 0xFF, 4096)
        C.memset(pool.memory.banks[0] + pool.stage("stStat", 9), 0xFF, 2048)
        self.assertTrue(pool.finish(blocks, 50))
        expected[0] = (FRAME + b"".join(blocks), 50, len(blocks) * BLOCK_BYTES)
        self.assertEqual(pool.states(), expected)
        self.assertEqual(C.string_at(table, table_size), b"\xDC" * table_size)
        pool.canaries()

    def test_changed_unreplaced_metadata_and_references_refuse_before_release(self):
        pool = self.pool()
        expected = pool.states()
        blocks = self.candidate(pool)
        slot = pool.directory.slots[1]
        slot.tag ^= 1
        self.assertFalse(pool.finish(blocks, 50))
        self.assertEqual(pool.directory.slots[0].count, 2)
        slot.tag ^= 1
        chunk = pool.directory.chunks[slot.ids[0] - 1]
        chunk.refs += 1
        self.assertFalse(pool.finish(blocks, 50))
        self.assertEqual(pool.directory.slots[0].count, 2)
        chunk.refs -= 1
        self.assertTrue(pool.abort())
        self.assertEqual(pool.states(), expected)
        pool.canaries()

    def test_generation_exhaustion_and_crc_table_corruption_refuse(self):
        pool = self.pool()
        expected = pool.states()
        control = pool.memory.banks[0] + pool.stage("stStat", 4)
        generation = C.c_uint.from_address(control + 5 * 4)
        generation.value = 0xFFFFFFFF
        self.assertFalse(pool.begin(0, 0xFFFFFFFF, 10))
        self.assertEqual(pool.states(), expected)
        generation.value = 1
        blocks = self.candidate(pool)
        table = pool.memory.banks[0] + pool.stage("stStat", 10)
        previous = C.string_at(table, 1024)
        C.memset(table, 0, 1024)
        self.assertFalse(pool.finish(blocks, 50))
        self.assertEqual(pool.directory.slots[0].count, 2)
        C.memmove(table, previous, 1024)
        self.assertTrue(pool.abort())
        self.assertEqual(pool.states(), expected)
        pool.canaries()


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
    folder = ROOT / "build/timewarp-staged-transaction"
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {"tests": result.testsRun, "passed": result.wasSuccessful(),
               "source_sha256": {name: sha(ROOT / name) for name in (
                   "scripts/test_timewarp_staged_guards.py", "scripts/timewarp/state_staged_transaction.h",
                   "scripts/test_timewarp_staged_transaction.py", "src/qft_timer.cpp")}}
    if (folder / "receipt.json").exists(): receipt["staged_replay_receipt_sha256"] = sha(folder / "receipt.json")
    (folder / "guards.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
