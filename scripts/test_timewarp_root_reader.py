"""Focused immutable-root binding and descriptor guards."""
import ctypes as C
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from test_timewarp_chunk_pool import plain
from test_timewarp_staged_transaction import StageHarness, StagePool, Token
from timewarp_root_codec import RootCodec, ppc_budget
from timewarp_multibank_pool import ROOT, sha
from timewarp_state_measure import FRAME, BLOCK_BYTES


class Control(C.Structure):
    _fields_ = [(name, C.c_uint) for name in ("magic", "sequence", "active", "root", "generation", "tag",
                "raw", "packed", "adler", "checksum", "root_signature", "span_count")] + [
                ("candidate", Token), ("table", C.c_void_p)]


class RootReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="timewarp-root-guards-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        (folder / "allocator").mkdir()
        cls.harness = StageHarness(folder / "allocator")
        cls.addClassCleanup(cls.harness.close)
        cls.codec = RootCodec(folder)
        cls.addClassCleanup(cls.codec.close)
        cls.layout = ppc_budget(folder)

    def seeded(self):
        pool = StagePool(self.harness)
        raw = bytes(range(256)) * (BLOCK_BYTES // 256)
        block = plain(raw)
        state = {"raw": raw, "blocks": [block], "expected": (FRAME + block, 19, len(raw))}
        self.assertTrue(pool.put(0, [block], 19))
        return pool, state

    def build(self, pool, state, generation=1, tag=19, crc=None, table=None, size=None):
        packed = state["expected"][0]
        return self.codec.call(pool, "rb", 0, generation, tag, len(state["raw"]), len(packed),
            zlib.adler32(state["raw"]), zlib.crc32(packed) if crc is None else crc, C.byref(pool.token),
            self.codec.table.ptr if table is None else table, self.codec.table.size if size is None else size)

    def check(self, pool, state, sequence):
        return self.codec.call(pool, "rc", sequence, zlib.adler32(state["raw"]), self.codec.table.ptr, self.codec.table.size)

    def test_bad_generation_tag_checksum_and_scratch_refuse_before_writing(self):
        pool, state = self.seeded()
        before = pool.states()
        self.assertFalse(self.build(pool, state, generation=2))
        self.assertFalse(self.build(pool, state, tag=18))
        self.assertFalse(self.build(pool, state, crc=0))
        for table, size in ((0, 9999), (self.codec.table.ptr + 1, 9999),
                            (self.codec.table.ptr, 16), (pool.memory.banks[0], 9999),
                            (C.addressof(pool.memory), 9999), (C.addressof(pool.stage_memory), 9999)):
            self.assertFalse(self.build(pool, state, table=table, size=size))
        self.assertEqual(pool.states(), before)
        pool.canaries()

    def test_mutated_binding_or_table_pointer_fails_before_dereference(self):
        pool, state = self.seeded()
        sequence = self.build(pool, state)
        self.assertTrue(sequence)
        control = Control.from_address(pool.memory.banks[0] + self.layout["reader_control_offset"])
        for field, value in (("root", 9), ("generation", 2), ("tag", 20), ("raw", 1),
                             ("packed", 1), ("adler", 0), ("checksum", 0),
                             ("span_count", 0), ("table", None)):
            old = getattr(control, field)
            setattr(control, field, value)
            self.assertFalse(self.check(pool, state, sequence), field)
            setattr(control, field, old)
        self.assertTrue(self.check(pool, state, sequence))
        self.assertFalse(self.codec.call(pool, "rr", sequence + 1))
        self.assertTrue(self.codec.call(pool, "rr", sequence))
        pool.canaries()

    def test_epoch_and_generation_bind_pending_candidate(self):
        pool, state = self.seeded()
        self.assertTrue(self.codec.guarded_begin(pool, 0))
        self.assertTrue(self.codec.guarded_append(pool, state["blocks"][0]))
        pool.token.epoch += 1
        self.assertFalse(self.codec.borrow(pool, 3, state))
        pool.token.epoch -= 1
        sequence = self.codec.borrow(pool, 3, state)
        self.assertTrue(sequence)
        self.assertFalse(self.codec.guarded_commit(pool, state))
        self.assertTrue(self.codec.call(pool, "rr", sequence))
        self.assertTrue(self.codec.guarded_commit(pool, state))
        self.assertFalse(self.build(pool, state, generation=1))
        new = self.build(pool, state, generation=2)
        self.assertTrue(new)
        self.assertTrue(self.codec.call(pool, "rr", new))
        pool.canaries()


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(RootReaderTests))
    folder = ROOT / "build/timewarp-root-codec"
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {"tests": result.testsRun, "passed": result.wasSuccessful(),
               "source_sha256": {name: sha(ROOT / name) for name in (
                   "scripts/timewarp/state_root_reader.h", "scripts/test_timewarp_root_reader.py",
                   "src/state_codec.cpp", "src/qft_timer.cpp")}}
    (folder / "guards.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
