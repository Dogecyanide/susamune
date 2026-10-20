"""Direct two-part admission, refusal, alias and callback boundary checks."""
import ctypes as C
from pathlib import Path
import random
import tempfile
import unittest

from test_state_codec import Span, Result
from test_timewarp_chunk_pool import DIRECTORY, plain
from test_timewarp_staged_transaction import StageHarness, StagePool
from timewarp_pool_producer import ProducerCodec


class ProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="state-producer-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        (folder / "allocator").mkdir()
        cls.harness = StageHarness(folder / "allocator")
        cls.addClassCleanup(cls.harness.close)
        cls.codec = ProducerCodec(folder)
        cls.addClassCleanup(cls.codec.close)

    def seeded(self, sizes=None, staging=0x2f0000):
        pool = StagePool(self.harness, sizes=sizes, staging=staging)
        for slot in range(3): assert pool.put(slot, [plain(bytes([slot + 1]) * 64)], slot + 10)
        return pool

    def test_direct_producer_candidate_and_all_callback_aborts(self):
        raw = random.Random(891).randbytes(0x40000 + 31)
        pool = self.seeded()
        old = pool.states()
        for stop in range(3):
            self.assertTrue(self.codec.guarded_begin(pool, 1))
            result, calls, state = self.codec.encode(pool, raw, 44, stop)
            self.assertEqual(result.status, 3)
            self.assertEqual(calls, stop + 1)
            self.assertIsNone(state)
            self.assertEqual(pool.states(), old)
            self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))
            self.assertEqual(pool.states(), old)
        self.assertTrue(self.codec.guarded_begin(pool, 1))
        result, calls, state = self.codec.encode(pool, raw, 44)
        self.assertEqual(result.status, 0)
        self.codec.decode(pool, 3, state, test_guards=True)
        self.assertTrue(self.codec.guarded_commit(pool, state))
        self.codec.decode(pool, 1, state, test_guards=True)
        expected = list(old); expected[1] = state["expected"]
        self.assertEqual(pool.states(), expected)

    def test_parts_and_contiguous_append_share_exact_hash_and_descriptor(self):
        block = plain(bytes(range(256)) * 2)
        pool = self.seeded()
        self.assertTrue(pool.put(0, [block], 40))
        self.assertTrue(self.codec.guarded_begin(pool, 1))
        old_id = pool.directory.slots[0].ids[0]
        before = pool.directory.high_water
        self.assertTrue(self.codec.parts(pool, block))
        self.assertEqual(pool.directory.slots[3].ids[0], old_id)
        self.assertEqual(pool.directory.high_water, before)
        self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))

    def test_hash_collision_cannot_share_different_bytes(self):
        pool = self.seeded()
        self.assertTrue(self.codec.guarded_begin(pool, 1))
        old_id = pool.directory.slots[0].ids[0]
        candidate = plain(bytes([87]) * 64)
        value = 2166136261
        for byte in candidate: value = ((value ^ byte) * 16777619) & 0xffffffff
        pool.directory.chunks[old_id - 1].hash = value
        self.assertTrue(self.codec.parts(pool, candidate))
        self.assertNotEqual(pool.directory.slots[3].ids[0], old_id)
        self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))
        pool.canaries()

    def test_invalid_parts_and_pool_or_stage_alias_refuse_without_changes(self):
        pool = self.seeded()
        self.assertTrue(self.codec.guarded_begin(pool, 0))
        block = plain(bytes(64))
        header, payload = C.create_string_buffer(block[:8]), C.create_string_buffer(block[8:])
        before = C.string_at(pool.memory.banks[0], DIRECTORY)
        for h, hn, p, pn in ((header, 7, payload, 64), (header, 8, payload, 0),
                            (header, 8, payload, 65), (None, 8, payload, 64),
                            (header, 8, pool.memory.banks[0], 64),
                            (pool.stage_memory.staging, 8, payload, 64)):
            self.assertFalse(self.codec.call(pool, "parts", C.byref(pool.token), h, hn, p, pn))
            self.assertEqual(C.string_at(pool.memory.banks[0], DIRECTORY), before)
        self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))

    def test_full_pool_and_final_capacity_refuse_without_releasing_old_roots(self):
        for staging in (0, 2048):
            pool = self.seeded([DIRECTORY + 320, 32, 32, 32], staging)
            old = pool.states()
            self.assertTrue(self.codec.guarded_begin(pool, 2))
            result, _, state = self.codec.encode(pool, random.Random(817).randbytes(1024), 45)
            if staging:
                self.assertEqual(result.status, 0)
                self.assertFalse(self.codec.guarded_commit(pool, state))
            else:
                self.assertEqual(result.status, 3)
            self.assertEqual(pool.states(), old)
            self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))
            self.assertEqual(pool.states(), old)
            pool.canaries()

    def test_workspace_aliasing_adapter_is_rejected_before_writes(self):
        pool = self.seeded()
        self.assertTrue(self.codec.guarded_begin(pool, 0))
        raw = C.create_string_buffer(bytes(64))
        source = (Span * 1)(Span(C.addressof(raw), 64))
        result, calls = Result(), C.c_uint()
        before = bytes(pool.stage_memory)
        self.codec.call(pool, "produce", C.byref(pool.token), C.addressof(pool.stage_memory),
                        self.codec.work.size, source, 1, 0xffffffff, C.byref(result), C.byref(calls))
        self.assertEqual(result.status, 1)
        self.assertEqual(bytes(pool.stage_memory), before)
        self.assertTrue(self.codec.call(pool, "gx", C.byref(pool.token)))


if __name__ == "__main__": unittest.main()
