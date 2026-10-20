"""Numeric protection checks use actual PPC RELA records, including aliases."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from elftools.elf.elffile import ELFFile

import link_pinned_mod as pinned
import pinned_numeric_protection as numeric
import pinned_source_sections as owned
import timewarp_timer_guard as timer


class NumericProtectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = pinned.ROOT / "build/timewarp-pr13-numeric-test"
        folder.mkdir(parents=True, exist_ok=True)
        source, cls.partial = folder / "fixture.s", folder / "fixture.o"
        source.write_text('''
.section .text.timer,"ax",@progbits
.globl fixture_timer
.type fixture_timer,@function
fixture_timer:
lis 3,constant@ha
addi 3,3,constant@l
lis 4,fixture_alias@ha
addi 4,4,fixture_alias@l
lis 5,constant+8@ha
addi 5,5,constant+8@l
.long constant
blr
.size fixture_timer,.-fixture_timer
.section .text.other,"ax",@progbits
blr
.section .rodata.cst4,"aM",@progbits,4
constant:
.long 0x3f800000,0x40000000
.set fixture_alias,constant+4
''')
        subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                        "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(source),
                        "-o", str(cls.partial)], check=True, capture_output=True)
        with cls.partial.open("rb") as stream:
            elf = ELFFile(stream)
            cls.rows = [{"index": index, "name": section.name, "group": "", "live": True,
                         "flags": section["sh_flags"], "address": 0x80400000 + index * 0x1000,
                         "analysis_address": 0x80400000 + index * 0x1000,
                         "linked_bytes": section["sh_size"]}
                        for index, section in enumerate(elf.iter_sections()) if section["sh_flags"] & 2]
            cls.symbols = [{"section": symbol["st_shndx"], "value": symbol["st_value"]}
                           for symbol in elf.get_section_by_name(".symtab").iter_symbols()]
            cls.relocations = [{"section": section["sh_info"], "offset": relocation["r_offset"],
                                "symbol": relocation["r_info_sym"], "type": relocation["r_info_type"],
                                "addend": relocation["r_addend"]}
                               for section in elf.iter_sections() if section["sh_type"] == "SHT_RELA"
                               for relocation in section.iter_relocations()]
        code = next(row for row in cls.rows if row["name"] == ".text.timer")
        cls.protected = [{"address": code["address"], "size": code["linked_bytes"]}]

    def test_frozen_parser_detects_section_alias_and_one_past(self):
        refs = numeric.frozen_references(self.partial, {"sections": self.rows}, self.protected)[".rodata.cst4"]
        self.assertEqual(len(refs), 7)
        self.assertEqual({row["type"] for row in refs}, {1, 4, 6})
        self.assertEqual({row["target_offset"] for row in refs}, {0, 4, 8})

    def test_unprotected_reader_does_not_restrict_numeric_pool(self):
        other = next(row for row in self.rows if row["name"] == ".text.other")
        protected = [{"address": other["address"], "size": other["linked_bytes"]}]
        self.assertEqual(numeric.frozen_references(self.partial, {"sections": self.rows}, protected),
                         {".rodata.cst4": []})
        self.assertEqual(numeric.verify_current(self.rows, self.symbols, self.relocations, protected), 0)

    def test_current_merged_and_owner_isolated_pools_are_rejected(self):
        for isolated in (False, True):
            rows = deepcopy(self.rows)
            if isolated:
                pool = next(row for row in rows if row["name"] == ".rodata.cst4")
                pool.update(flags=2, source_owned_numeric=True)
            with self.subTest(isolated=isolated), self.assertRaisesRegex(ValueError, "Protected source now references"):
                numeric.verify_current(rows, self.symbols, self.relocations, self.protected)

    def test_absolute_pool_alias_is_rejected(self):
        symbols = deepcopy(self.symbols)
        first = self.relocations[0]
        pool = next(row for row in self.rows if row["name"] == ".rodata.cst4")
        symbols[first["symbol"]] = {"section": "SHN_ABS", "value": pool["analysis_address"]}
        with self.assertRaisesRegex(ValueError, "Protected source now references"):
            numeric.verify_current(self.rows, symbols, [first], self.protected)

    def test_frozen_six_build_proofs_reproduce_without_final_relocations(self):
        layout = json.loads(pinned.LAYOUT.read_text())
        frozen = json.loads(timer.BASELINE.read_text())
        receipt = json.loads(owned.NUMERIC_LAYOUT.read_text())
        for key, baseline in layout["builds"].items():
            target, region = key.split("-")
            partial = pinned.ROOT / f"build/baseline-{target}/susamune_pre_{region}.o"
            self.assertEqual(pinned.file_sha(partial), baseline["source_partial_sha256"])
            protected = list(frozen["builds"][key]["symbols"].values()) + baseline["anchors"]
            actual = numeric.frozen_references(partial, baseline, protected)
            expected = {name: row["protected_references"] for name, row in receipt["builds"][key].items()}
            with self.subTest(key=key):
                self.assertEqual(actual, expected)
                self.assertTrue(all(not references for references in actual.values()))


if __name__ == "__main__":
    unittest.main()
