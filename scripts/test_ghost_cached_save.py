"""Cached AUTO saves verify directory names and the exact target before writing."""
import ctypes
import struct
import unittest

import test_ghost_kernel_paging as kernel
from test_ghost_format import build_ghost
from test_ghost_storage import envelope
import test_ghost_trace_publication as publication
from test_ghost_recording import manifest

PERSONAL, AUTO = kernel.PERSONAL, kernel.AUTO


def instrument(fixture):
    fixture = fixture.replace("static int f_readdir(", "static int fixture_readdir(")
    return fixture + r"""
static unsigned failDirectoryAt;
static int f_readdir(DIR *dir,FILINFO *info) {
 if(failDirectoryAt && dirCalls+1==failDirectoryAt) {
  failDirectoryAt=0; ++dirCalls; return FR_DISK_ERR;
 }
 return fixture_readdir(dir,info);
}
"""


class CachedSaveTests(unittest.TestCase):
    fixture_transform = staticmethod(instrument)
    bridge_source = r"""
__declspec(dllexport) void failDirectoryRead(unsigned relative) {
 failDirectoryAt=relative;
}
__declspec(dllexport) int erase(const char *path) { return f_unlink_char(path); }
__declspec(dllexport) unsigned stopAtAutoProbe(void) {
 for(unsigned i=0;i<10000;++i) {
  if(AutoProbe && !DirectoryScan && Phase==OP_SCAN_ENVELOPES) return Request.slot;
  if(!SusamuneGhostPending())return 0xffffffffu;
  SusamuneGhostService();
 }
 return 0xffffffffu;
}
"""
    setUpClass = classmethod(kernel.GhostKernelPagingTests.setUpClass.__func__)
    add = kernel.GhostKernelPagingTests.add
    file = kernel.GhostKernelPagingTests.file
    request = kernel.GhostKernelPagingTests.request
    page = kernel.GhostKernelPagingTests.page

    def setUp(self):
        kernel.GhostKernelPagingTests.setUp(self)
        self.dll.failDirectoryRead(0)
        self.dll.erase.argtypes = [ctypes.c_char_p]

    def populate(self, count):
        ids = list(range(45)) + list(range(48, count+3)) if count > 45 else list(range(count))
        for slot in ids:
            self.add(PERSONAL+f"g{slot:02}a.sgh", envelope(build_ghost(), slot=slot))
        self.page()
        return ids

    def save(self):
        result = self.request(1, AUTO, payload=build_ghost(ghost_id=123))
        self.assertEqual(result["status"], 0)
        return result

    def test_complete_63_row_cache_needs_only_target_and_output_opens(self):
        ids = self.populate(63)
        originals = {slot:self.file(PERSONAL+f"g{slot:02}a.sgh") for slot in ids}
        result = self.save()
        self.assertEqual(result["slot"], 66)
        self.assertEqual((self.dll.reads(), self.dll.opens()), (0, 3))
        self.assertEqual(self.dll.directoryReads(), 65)
        self.assertEqual(self.page(cached=True)[1], 64)
        self.assertEqual((self.dll.reads(), self.dll.opens()), (0, 0))
        for slot, data in originals.items():
            self.assertEqual(self.file(PERSONAL+f"g{slot:02}a.sgh"), data)

    def test_explicit_save_invalidates_the_old_cached_view(self):
        self.populate(2)
        result = self.request(1, 5, payload=build_ghost())
        self.assertEqual((result["status"], result["slot"]), (0, 5))
        self.assertEqual([row[0] for row in self.page(cached=True)[0]], [0, 1, 5])
        self.assertGreater(self.dll.reads(), 0)

    def test_empty_verified_cache_still_probes_both_target_banks(self):
        self.page()
        self.assertEqual(self.save()["slot"], 0)
        self.assertEqual((self.dll.reads(), self.dll.opens()), (0, 3))
        self.assertEqual(self.page(cached=True)[1], 1)

    def test_tombstone_reuse_keeps_its_checked_next_generation(self):
        self.add(PERSONAL+"g00a.sgh", envelope(build_ghost()))
        self.add(PERSONAL+"g01a.sgh", envelope(slot=1, generation=7, flags=1))
        self.add(PERSONAL+"g02a.sgh", envelope(build_ghost(), slot=2))
        self.page()
        result = self.save()
        self.assertEqual((result["slot"], result["generation"]), (1, 8))
        self.assertGreater(self.dll.reads(), 0)

    def test_full_window_reuses_metadata_after_complete_names_check(self):
        self.populate(64)
        self.assertEqual(self.save()["slot"], 67)
        self.assertEqual((self.dll.reads(), self.dll.opens()), (0, 3))
        self.assertEqual(self.page(cached=True)[1], 65)
        self.assertEqual((self.dll.reads(), self.dll.opens()), (0, 0))

    def test_unexpected_row_forces_fresh_headers_before_save(self):
        self.populate(2)
        self.add(PERSONAL+"g02a.sgh", envelope(build_ghost(), slot=2))
        self.assertEqual(self.save()["slot"], 3)
        self.assertEqual(self.dll.reads(), 3)
        self.assertEqual(self.page(cached=True)[1], 4)

    def test_missing_row_forces_fresh_headers_before_save(self):
        self.populate(3)
        self.assertEqual(self.dll.erase((PERSONAL+"g01a.sgh").encode()), 0)
        self.assertEqual(self.save()["slot"], 3)
        self.assertEqual(self.dll.reads(), 2)
        self.assertEqual([r[0] for r in self.page(cached=True)[0]], [0, 2, 3])

    def test_second_bank_forces_fresh_generation_selection(self):
        self.populate(2)
        self.add(PERSONAL+"g00b.sgh", envelope(build_ghost(), generation=2))
        self.assertEqual(self.save()["slot"], 2)
        self.assertGreaterEqual(self.dll.reads(), 3)
        self.assertEqual(self.page(cached=True)[0][0][1], 2)

    def test_unsafe_cached_metadata_is_not_used_to_skip_headers(self):
        self.add(PERSONAL+"g00a.sgh", b"broken")
        self.page()
        self.assertEqual(self.save()["slot"], 1)
        self.assertGreater(self.dll.reads(), 0)
        self.assertEqual(self.file(PERSONAL+"g00a.sgh"), b"broken")

    def test_one_directory_error_retries_the_original_full_scan(self):
        self.populate(3)
        self.dll.failDirectoryRead(2)
        self.assertEqual(self.save()["slot"], 3)
        self.assertEqual(self.dll.reads(), 3)

    def test_target_is_revalidated_after_directory_verification(self):
        self.populate(1)
        payload = build_ghost(ghost_id=123)
        self.dll.submit(1, 0, AUTO, payload, len(payload), 0)
        self.assertEqual(self.dll.stopAtAutoProbe(), 1)
        prior = envelope(build_ghost(ghost_id=456), slot=1)
        self.add(PERSONAL+"g01a.sgh", prior)
        self.assertGreaterEqual(self.dll.run(1000000), 0)
        response = struct.unpack("<IHHIiIIIHH", ctypes.string_at(self.dll.response(), 32))
        self.assertEqual((response[4], response[7]), (0, 2))
        self.assertEqual(self.file(PERSONAL+"g01a.sgh"), prior)

    def test_failed_write_invalidates_fast_cache(self):
        self.populate(2)
        self.dll.writeFailure(64+100, 0)
        self.assertNotEqual(self.request(1, AUTO, payload=build_ghost())["status"], 0)
        rows, total, _, _ = self.page(cached=True)
        self.assertEqual(total, 3)
        self.assertTrue(rows[-1][3] & 2)
        self.assertGreater(self.dll.reads(), 0)


class StreamedCachedSaveTests(unittest.TestCase):
    setUpClass = classmethod(publication.PublicationPinTests.setUpClass.__func__)
    setUp = publication.PublicationPinTests.setUp
    add = publication.PublicationPinTests.add
    file = publication.PublicationPinTests.file
    request = publication.PublicationPinTests.request
    source = publication.PublicationPinTests.source
    pin = publication.PublicationPinTests.pin

    def test_msgt_fast_save_still_publishes_checked_independent_source_pin(self):
        ids = list(range(45)) + list(range(48, 66))
        prior = {}
        for slot in ids:
            path = PERSONAL+f"g{slot:02}a.sgh"
            prior[path] = envelope(build_ghost(), slot=slot)
            self.add(path, prior[path])
        source = self.source()
        self.assertEqual(self.request(4, slot=0)["status"], 0)
        self.assertEqual(self.lib.reads(), 63)
        saved = self.request(1, payload=manifest(source))
        self.assertEqual((saved["status"], saved["slot"]), (0, 66))
        self.assertLess(self.lib.reads(), 12, "source and reference checks remain; old slot headers are reused")
        self.assertIsNotNone(self.file(self.pin(66)))
        self.assertEqual(self.file(PERSONAL+"g66a.sgh")[64:], manifest(source))
        source_hash = struct.unpack_from(">I", source, 60)[0]
        retained = self.lib.discardSource(1, source_hash)
        for _ in range(1000):
            if retained != 0:
                break
            retained = self.lib.discardSource(0, source_hash)
        self.assertEqual(retained, -1)
        self.assertEqual(self.file("/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt"), source)
        for path, data in prior.items():
            self.assertEqual(self.file(path), data)

    def test_bad_source_cannot_be_saved_through_a_valid_metadata_cache(self):
        source = self.source()
        self.assertEqual(self.request(4, slot=0)["status"], 0)
        corrupt = bytearray(source)
        corrupt[60] ^= 1
        self.add("/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt", bytes(corrupt))
        self.assertNotEqual(self.request(1, payload=manifest(source))["status"], 0)
        self.assertIsNone(self.file(PERSONAL+"g00a.sgh"))
        self.assertIsNone(self.file(self.pin(0)))


if __name__ == "__main__":
    unittest.main()
