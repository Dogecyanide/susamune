"""Anonymous menu retirement must remain source-owned, immutable and unprotected."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import link_pinned_mod as pinned
import pinned_menu_constants as constants
import pinned_source_sections as owned
import timewarp_timer_guard as timer


class MenuConstantOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads(pinned.LAYOUT.read_text())
        cls.sources = json.loads(owned.LAYOUT.read_text())
        cls.receipt = json.loads(constants.LAYOUT.read_text())
        cls.frozen = json.loads(timer.BASELINE.read_text())
        cls.original = cls.layout["builds"]["console-us"]
        cls.source = cls.sources["builds"]["console-us"]
        cls.protected = list(cls.frozen["builds"]["console-us"]["symbols"].values()) + cls.original["anchors"]
        cls.proofs = cls.receipt["builds"]["console-us"]
        cls.string_name = next(name for name, proof in cls.proofs.items() if proof["kind"] == "padded_string")
        cls.table_name = next(name for name, proof in cls.proofs.items() if proof["kind"] == "string_lookup")

    def test_receipt_reproduces_from_six_hash_locked_artifacts(self):
        self.assertEqual(constants.capture(), self.receipt)
        self.assertEqual({key: len(rows) for key, rows in self.receipt["builds"].items()},
                         {key: 8 for key in self.layout["builds"]})

    def test_ordinary_validation_needs_only_receipts(self):
        with patch.object(constants, "certify", side_effect=AssertionError("ELF capture during ordinary build")):
            for key in self.layout["builds"]:
                target, region = key.split("-")
                baseline = owned.expand_layout(owned.LAYOUT, pinned.LAYOUT, self.layout, target, region, timer.BASELINE)
                self.assertEqual(len(baseline["immutable_menu_constants"]), 8)

    def test_stale_receipt_binding_rejected(self):
        for field in ("original_layout_sha256", "source_ownership_sha256", "timer_baseline_sha256"):
            bad = deepcopy(self.receipt)
            bad[field] = "0" * 64
            with self.subTest(field=field), patch.object(constants, "json") as fake:
                fake.loads.return_value = bad
                with self.assertRaisesRegex(ValueError, "does not match the frozen"):
                    constants.load(constants.LAYOUT, pinned.LAYOUT, owned.LAYOUT, timer.BASELINE,
                                   self.original, self.source, "console-us")

    def test_corrupt_provenance_and_shape_rejected(self):
        values = {"owner": "savestate.cpp", "kind": "mutable", "source_object_sha256": "0" * 64,
                  "partial_sha256": "0" * 64, "linked_sha256": "0" * 64, "source_section_index": 0,
                  "flags": 3, "bytes": 1, "address": 0, "sha256": "0" * 64}
        for field, value in values.items():
            bad = deepcopy(self.proofs)
            bad[self.string_name][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "identity differs"):
                constants.validate(bad, self.original, self.source, self.protected)

    def test_protection_and_reader_evidence_rejected(self):
        values = {"reader_sections": [], "readers": ["unknown"], "incoming_relocations": 0,
                  "pointer_entries": 1, "protected_references": 1, "protected_overlap": True}
        for field, value in values.items():
            bad = deepcopy(self.proofs)
            bad[self.string_name][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "protection differs"):
                constants.validate(bad, self.original, self.source, self.protected)
        for selected in (self.string_name, self.table_name):
            proof = self.proofs[selected]
            reader = next(r for r in self.original["sections"] if r["index"] == proof["reader_sections"][0])
            for address in (proof["address"], reader["address"]):
                with self.subTest(address=address), self.assertRaisesRegex(ValueError, "protection differs"):
                    constants.validate(self.proofs, self.original, self.source,
                                       self.protected + [{"address": address, "size": 1}])

    def candidate(self, name):
        proof = self.proofs[name]
        old = next(r for r in self.original["sections"] if r["name"] == name and not r["group"])
        reader = next(r for r in self.original["sections"] if r["index"] == proof["reader_sections"][0])
        table = proof["kind"] == "string_lookup"
        facts = {"source_matches": 1, "source_definitions": [], "source_payload_identical": True,
                 "source_section_index": proof["source_section_index"],
                 "source_object_sha256": proof["source_object_sha256"],
                 "partial_sha256": proof["partial_sha256"], "linked_sha256": proof["linked_sha256"],
                 "incoming": [{"owners": reader["owners"], "definition_count": 1, "flags": reader["flags"],
                               "single_symbol": reader["single_symbol"], "source": reader["index"],
                               "type": 4, "target_offset": 0}],
                 "data": bytes(old["bytes"]) if table else b"Label\0" + bytes(old["bytes"] - 6),
                 "outgoing": ([{"type": 1, "offset": offset, "readonly_string_target": True}
                               for offset in range(0, old["bytes"], 4)] if table else []),
                 "protected_overlap": False, "protected_reader": False, "protected_references": False}
        return {**deepcopy(old), "sha256": constants.sha(facts["data"])}, facts

    def test_capture_rejects_mutable_named_merged_or_ambiguous_data(self):
        for field, value in (("flags", 3), ("flags", 0x12), ("definition_count", 1),
                             ("owners", ["menu.cpp"]), ("group", "named"), ("cold", True)):
            old, facts = self.candidate(self.string_name)
            old[field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "immutable menu"):
                constants.verify_candidate(old, facts)
        for field, value in (("source_matches", 2), ("source_definitions", ["mutable"]),
                             ("source_payload_identical", False)):
            old, facts = self.candidate(self.string_name)
            facts[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "ambiguous"):
                constants.verify_candidate(old, facts)

    def test_capture_rejects_unknown_writers_and_protected_refs(self):
        for field, value in (("owners", ["menu.cpp", "qft_timer.cpp"]), ("owners", ["qft_timer.cpp"]),
                             ("type", 10), ("target_offset", 4), ("flags", 3)):
            old, facts = self.candidate(self.string_name)
            facts["incoming"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "unproven reader"):
                constants.verify_candidate(old, facts)
        for field in ("protected_overlap", "protected_reader", "protected_references"):
            old, facts = self.candidate(self.string_name)
            facts[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "protected"):
                constants.verify_candidate(old, facts)

    def test_capture_rejects_nontext_and_incomplete_or_writable_lookups(self):
        old, facts = self.candidate(self.string_name)
        facts["data"] = b"A\0B\0" + bytes(old["bytes"] - 4)
        old["sha256"] = constants.sha(facts["data"])
        with self.assertRaisesRegex(ValueError, "non-padding"):
            constants.verify_candidate(old, facts)
        for change in ("missing", "writable", "relocation", "nonzero", "reader"):
            old, facts = self.candidate(self.table_name)
            if change == "missing":
                facts["outgoing"].pop()
            elif change == "writable":
                facts["outgoing"][0]["readonly_string_target"] = False
            elif change == "relocation":
                facts["outgoing"][0]["type"] = 10
            elif change == "nonzero":
                facts["data"] = b"a" + facts["data"][1:]
            else:
                facts["incoming"][0]["single_symbol"] = "unrelated__MenuFv"
            with self.subTest(change=change), self.assertRaises(ValueError):
                constants.verify_candidate(old, facts)

    def test_only_verified_missing_constants_can_retire(self):
        old = next(r for r in self.original["sections"] if r["name"] == self.string_name and not r["group"])
        baseline = {"sections": [deepcopy(old)]}
        with self.assertRaisesRegex(ValueError, "Required fixed input disappeared"):
            pinned.plan_sections([], [], [], baseline, [])
        verified = owned.expand_layout(owned.LAYOUT, pinned.LAYOUT, self.layout, "console", "us", timer.BASELINE)
        baseline = {"sections": [next(r for r in verified["sections"] if r["name"] == self.string_name)]}
        pinned.plan_sections([], [], [], baseline, [], protected=self.protected)
        self.assertEqual(baseline["retired_missing"][0]["name"], self.string_name)
        with self.assertRaisesRegex(ValueError, "overlaps a protected anchor"):
            pinned.plan_sections([], [], [], baseline, [], protected=[{"address": old["address"], "size": 1}])


if __name__ == "__main__":
    unittest.main()
