"""Execute the production DI reservation and readers against an owned tail."""
import ctypes as C
from pathlib import Path
import tempfile
import unittest

from timewarp_di_scratch import ROOT, compile_di, fence_experiment, run_requests


class DiScratchPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "toolchain/clang++.exe").exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-di-policy-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.lib, _ = compile_di(Path(cls.temp.name))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def boot(self, mode=0, ciso=0):
        self.lib.setSize(0x80000)
        self.lib.configure(mode, 0, ciso)

    def own_tail(self):
        self.assertTrue(self.lib.publishRuntime())
        self.assertEqual(self.lib.currentLimit(), 0x10000)
        self.lib.claimTail()
        self.assertTrue(self.lib.tailIntact())

    def test_wide_boot_then_serial_fence_and_queued_read(self):
        receipt = fence_experiment(self.lib)
        self.assertTrue(receipt["owned_tail_unchanged"])

    def test_actual_consumer_entry_registers_id_before_self_call_guard(self):
        for consumer in (2, 17):
            self.boot()
            self.assertEqual(self.lib.startDiThread(consumer), consumer)
            self.assertFalse(self.lib.publishRuntime())
            self.assertEqual(self.lib.currentLimit(), 0x80000)
            self.lib.selectThread(0)
            self.own_tail()

    def test_runtime_reads_preserve_tail_across_rounding_and_large_requests(self):
        requests = ((0x400000, 65505), (0x50001F, 65536),
                    (0x6001FF, 65537), (0x800000 - 17, 0x300021))
        for mode in (0, 1, 2, 3):
            with self.subTest(mode=mode):
                self.boot(mode)
                self.own_tail()
                result, _ = run_requests(self.lib, requests, owned_tail=True)
                self.assertEqual(result["patch_calls"], len(requests))
                self.assertEqual(result["ack_calls"], len(requests))

    def test_sparse_ciso_reads_preserve_owned_tail(self):
        for mode in (0, 1):
            with self.subTest(cached=bool(mode)):
                self.boot(mode, ciso=1)
                self.own_tail()
                run_requests(self.lib, ((0x200000 - 17, 0x400031),
                    (0x600000 - 31, 0x300001)), owned_tail=True)

    def test_reopened_iso_and_repeated_reservation_never_widen(self):
        self.boot(1)
        self.own_tail()
        calls = self.lib.fenceStat(4)
        self.lib.reopenCache()
        self.assertTrue(self.lib.publishRuntime())
        self.assertEqual(self.lib.fenceStat(4), calls)
        result, _ = run_requests(self.lib, ((0x400000, 0x20021),), owned_tail=True)
        self.assertEqual(result["chunks"], 3)
        self.assertEqual(self.lib.currentLimit(), 0x10000)

    def test_tail_observer_detects_previously_dispatched_wide_write(self):
        self.boot()
        self.own_tail()
        self.lib.staleWideWrite()
        self.assertFalse(self.lib.tailIntact())


if __name__ == "__main__":
    unittest.main()
