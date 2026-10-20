"""Reject stale patches and incomplete production runtime evidence."""
import copy
import json
import struct
import unittest
import zlib

from gen_iso_bps import BpsBuilder
import package_timewarp_dolphin as package


class DolphinPackageTests(unittest.TestCase):
    def patch_fixture(self):
        builder = BpsBuilder({})
        builder.target_read(b"synthetic mod payload")
        layout = package.read_json(package.ROOT / "data/iso_layout_pal.json")
        data = builder.encode(layout["iso_size"], int(layout["source_crc32"], 16))
        evidence = {"manifest_sha256": "current-manifest", "container_sha256": "current-container"}
        receipt = {"passed": True, "region": "pal", "patch_sha256": package.digest(data),
                   "source_crc32": layout["source_crc32"], "target_crc32": f"{builder.target_crc:08X}",
                   "exporter_sha256": package.digest((package.ROOT / "scripts/timewarp_emulator_export.py").read_bytes()),
                   **evidence}
        return data, receipt, evidence

    def test_export_receipt_cannot_bless_a_different_current_build(self):
        data, receipt, evidence = self.patch_fixture()
        package.checked_patch(data, receipt, "pal", evidence)
        with self.assertRaisesRegex(ValueError, "current build"):
            package.checked_patch(data, receipt, "pal", dict(evidence, container_sha256="new-container"))
        with self.assertRaisesRegex(ValueError, "different exporter"):
            package.checked_patch(data, dict(receipt, exporter_sha256="old-exporter"), "pal", evidence)

    def test_rehashed_patch_still_requires_its_bps_and_disc_checksums(self):
        data, receipt, evidence = self.patch_fixture()
        changed = bytearray(data)
        changed[-4] ^= 1
        with self.assertRaisesRegex(ValueError, "checksums"):
            package.checked_patch(changed, dict(receipt, patch_sha256=package.digest(changed)), "pal", evidence)
        changed = bytearray(data)
        struct.pack_into("<I", changed, len(changed) - 12, 0x12345678)
        struct.pack_into("<I", changed, len(changed) - 4, zlib.crc32(changed[:-4]))
        with self.assertRaisesRegex(ValueError, "checksums"):
            package.checked_patch(changed, dict(receipt, patch_sha256=package.digest(changed)), "pal", evidence)

    def runtime_fixture(self):
        pal = {key: key + "-current" for key in ("manifest_sha256", "container_sha256", "elf_sha256",
               "pinned_link_receipt_sha256", "bootstrap_sha256", "cold_sha256")}
        runtime = {"production_bootstrap_identical": True, "cold_payload_verified_after_copy": True,
                   "diagnostic_pad_callbox_separate": True, "production_bootstrap_sha256": pal["bootstrap_sha256"]}
        receipt = {"runtime": runtime, "ppc_control_and_rx": True, "ppc_pose": True,
                   "ppc_stop_restart": True, "companion_restart": True}
        live = {"info": {"production_build": pal, "production_bootstrap": pal}}
        return receipt, live, pal

    def test_runtime_requires_actual_boot_copy_and_bidirectional_transport(self):
        receipt, live, pal = self.runtime_fixture()
        package.checked_runtime(receipt, live, pal)
        for key in ("ppc_control_and_rx", "ppc_pose", "ppc_stop_restart", "companion_restart"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "incomplete"):
                package.checked_runtime(dict(receipt, **{key: False}), live, pal)
        old = copy.deepcopy(live)
        old["info"]["production_build"]["elf_sha256"] = "old-elf"
        with self.assertRaisesRegex(ValueError, "different build"):
            package.checked_runtime(receipt, old, pal)
        old = copy.deepcopy(receipt)
        old["runtime"]["cold_payload_verified_after_copy"] = False
        with self.assertRaisesRegex(ValueError, "boot check is incomplete"):
            package.checked_runtime(old, live, pal)

    def test_ghost_render_requires_matching_runtime_and_inspected_model_capture(self):
        capture = b"native frame fixture"
        receipt = {"transport_verification_sha256": "current-transport", "available": 1,
                   "playback": {"ok": 1}, "model_submitted": True,
                   "captures": [{"submitted": 1}], "visual_inspection": {
                       "verified": True, "sha256": package.digest(capture)}}
        package.checked_ghost_visual(receipt, "current-transport", capture)
        with self.assertRaisesRegex(ValueError, "different runtime"):
            package.checked_ghost_visual(receipt, "old-transport", capture)
        with self.assertRaisesRegex(ValueError, "not available"):
            package.checked_ghost_visual(dict(receipt, model_submitted=False), "current-transport", capture)
        with self.assertRaisesRegex(ValueError, "capture differs"):
            package.checked_ghost_visual(receipt, "current-transport", b"different frame")


if __name__ == "__main__":
    unittest.main()
