"""Unused-space recovery must prove ownership before changing placement."""
from copy import deepcopy
import unittest

import link_pinned_mod as pinned
import patches


def fixture():
    base = patches.base_addr["jp"]
    upper = base + patches.mod_upper_offset
    old = [
        dict(name=".text.smaller", group="", address=base, linked_bytes=128,
             bytes=128, live=True, flags=6, type="SHT_PROGBITS", align=4,
             owners=["feature.cpp"]),
        dict(name=".bss.last", group="", address=upper, linked_bytes=64,
             bytes=64, live=True, flags=3, type="SHT_NOBITS", align=4,
             owners=["feature.cpp"]),
    ]
    rows = deepcopy(old)
    for index, row in enumerate(rows):
        row.update(index=index + 1, moved=False, cold=False, sha256="current",
                   definitions=[dict(name=row["name"], value=0, size=row["bytes"])])
    rows[0].update(bytes=80, linked_bytes=80)
    rows[0]["definitions"][0]["size"] = 80
    return rows, dict(sections=old)


def recover(rows, baseline, protected=(), symbols=(), relocations=()):
    return pinned.unused_ranges(rows, baseline, protected, "jp", symbols, relocations)


class UnusedRangeTests(unittest.TestCase):
    def test_suffix_and_span_tails_preserve_existing_caps(self):
        rows, baseline = fixture()
        found = recover(rows, baseline)
        suffix = next(r for r in found if r.get("shrunken_input"))
        self.assertEqual(suffix["end"] - suffix["begin"], 48)
        tails = [r for r in found if "reserved_begin" in r]
        self.assertEqual(len(tails), 2)
        self.assertEqual(tails[0]["end"], patches.base_addr["jp"] + patches.mod_mem1_working_cap_size)
        self.assertEqual(tails[1]["end"], patches.base_addr["jp"] + patches.mod_upper_offset + patches.mod_upper_size)
        self.assertEqual(rows[0]["address"], baseline["sections"][0]["address"])

    def test_protected_suffix_is_not_reclaimed(self):
        rows, baseline = fixture()
        protected = [dict(address=rows[0]["address"] + 96, size=4)]
        self.assertFalse(any(r.get("shrunken_input") for r in recover(rows, baseline, protected)))

    def test_emulator_bootstrap_page_stays_free(self):
        rows, baseline = fixture()
        console = recover(rows, baseline)
        emu = pinned.unused_ranges(rows, baseline, (), "jp", (), (), "emu")
        console_tail = [r for r in console if "reserved_begin" in r][-1]
        emu_tail = [r for r in emu if "reserved_begin" in r][-1]
        self.assertEqual(console_tail["end"] - emu_tail["end"], 0x1000)
        self.assertEqual(emu_tail["end"], patches.base_addr["jp"] + 0xBF000)

    def test_reference_to_tail_or_one_past_end_keeps_suffix(self):
        for offset in (80, 120, -1):
            rows, baseline = fixture()
            symbols = [dict(section=1, value=0)]
            relocations = [dict(symbol=0, addend=offset)]
            with self.subTest(offset=offset):
                found = recover(rows, baseline, symbols=symbols, relocations=relocations)
                self.assertFalse(any(r.get("shrunken_input") for r in found))
        found = recover(rows, baseline, symbols=symbols, relocations=[dict(symbol=0, addend=76)])
        self.assertEqual(next(r for r in found if r.get("shrunken_input"))["incoming_references_checked"], 1)

    def test_shared_merged_cold_and_moved_inputs_are_not_reclaimed_twice(self):
        for kind in ("shared", "merged", "cold", "moved", "extension"):
            rows, baseline = fixture()
            if kind == "shared": rows[0]["owners"].append("other.cpp")
            elif kind == "merged": rows[0]["flags"] |= 0x10
            elif kind == "extension": rows[0]["cold_extension"] = True
            else: rows[0][kind] = True
            with self.subTest(kind=kind):
                self.assertFalse(any(r.get("shrunken_input") for r in recover(rows, baseline)))

    def test_live_or_protected_span_tail_overlap_fails(self):
        for kind in ("live", "protected", "baseline"):
            rows, baseline = fixture()
            tail = baseline["sections"][1]["address"] + 64
            protected = []
            if kind == "live":
                extra = deepcopy(rows[1])
                extra.update(name=".new.fixed", address=tail)
                rows.append(extra)
            elif kind == "protected":
                protected = [dict(address=tail, size=4)]
            else:
                baseline["sections"][1]["linked_bytes"] = patches.mod_upper_size + 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                recover(rows, baseline, protected)

    def test_source_owned_pool_requires_bounded_definitions_and_same_attributes(self):
        rows, baseline = fixture()
        rows[0]["definitions"].append(dict(name="second", value=40, size=40))
        self.assertFalse(any(r.get("shrunken_input") for r in recover(rows, baseline)))
        rows[0]["source_owned_verified"] = True
        self.assertTrue(any(r.get("shrunken_input") for r in recover(rows, baseline)))
        rows[0]["definitions"][1]["size"] += 1
        with self.assertRaises(ValueError):
            recover(rows, baseline)


if __name__ == "__main__":
    unittest.main()
