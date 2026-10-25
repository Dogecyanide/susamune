"""Real PPC string splitting, suffix aliases and protected literal checks."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from elftools.elf.elffile import ELFFile

import link_pinned_mod as pinned
import pinned_source_sections as owned
import pinned_string_atoms as strings
import timewarp_timer_guard as timer


SOURCE = r'''
.section .rodata.str1.1,"aMS",@progbits,1
.Llong: .asciz "prefix/suffix"
.Lshort: .asciz "suffix"
.Lother: .asciz "other"
.Lend:
.section .text.reader,"ax",@progbits
.globl reader
.type reader,@function
reader:
 lis 3,(.Llong+7)@ha
 addi 3,3,(.Llong+7)@l
 lis 4,.Lshort@ha
 addi 4,4,.Lshort@l
 blr
.size reader,.-reader
.section .data.pointers,"aw",@progbits
.long .Llong+7
.long .Lother-1
'''


def relocation_strings(path):
    result = []
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name(".symtab")
        for section in elf.iter_sections():
            if section["sh_type"] != "SHT_RELA":
                continue
            for relocation in section.iter_relocations():
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                target = elf.get_section(symbol["st_shndx"])
                offset = symbol["st_value"] + relocation["r_addend"]
                data = target.data()[offset:]
                result.append((elf.get_section(section["sh_info"]).name, relocation["r_offset"],
                               relocation["r_info_type"], data[:data.index(0) + 1]))
    return result


class StringAtomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pinned.ROOT / "build/pr13-string-tests"
        root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=root)
        cls.folder = Path(cls.temporary.name)
        cls.receipt = json.loads(strings.LAYOUT.read_text())
        cls.original = json.loads(pinned.LAYOUT.read_text())["builds"]["console-us"]
        cls.sources = json.loads(owned.LAYOUT.read_text())["builds"]["console-us"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def compile(self, name, source=SOURCE):
        assembly, output = self.folder / (name + ".s"), self.folder / (name + ".o")
        assembly.write_text(source)
        pinned.run([pinned.ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi",
                    "-c", assembly, "-o", output], self.folder)
        return output

    def aliases(self):
        parent, child = b"prefix/suffix\0", b"suffix\0"
        return {strings.atom_name(parent): {"canonical": strings.atom_name(parent), "canonical_offset": 0},
                strings.atom_name(child): {"canonical": strings.atom_name(parent), "canonical_offset": 7}}

    def test_six_protected_inventories_reproduce(self):
        self.assertEqual(strings.capture(), self.receipt)
        for entry in self.receipt["builds"].values():
            self.assertEqual(len(entry["protected_reference_sites"]), 12)
            self.assertEqual(len(entry["protected_atoms"]), 5)

    def test_real_ppc_suffix_and_interior_relocations_keep_exact_text(self):
        path = self.compile("suffix")
        before = relocation_strings(path)
        with path.open("rb") as stream:
            code = ELFFile(stream).get_section_by_name(".text.reader").data()
        inventory = strings.split_object(path, self.aliases())
        self.assertEqual(before, relocation_strings(path))
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            self.assertEqual(code, elf.get_section_by_name(".text.reader").data())
            self.assertEqual({s.name for s in elf.iter_sections() if s["sh_flags"] & 0x22 == 0x22},
                             {strings.atom_name(b"prefix/suffix\0"), strings.atom_name(b"other\0")})
        self.assertEqual(len(inventory), 3)

    def test_shared_atoms_deduplicate_before_merge_flags_are_cleared(self):
        first, second = self.compile("shared-a"), self.compile("shared-b", SOURCE.replace("reader", "reader_two"))
        proof = {"first.cpp": strings.split_object(first, self.aliases()),
                 "second.cpp": strings.split_object(second, self.aliases())}
        partial = self.folder / "shared.o"
        pinned.run([pinned.ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi",
                    "-nodefaultlibs", "-nostdlib", "-fuse-ld=lld", "-r", first, second, "-o", partial], self.folder)
        atoms = strings.normalize_partial(partial, proof, self.aliases())
        self.assertEqual(len(atoms), 2)
        self.assertTrue(all(row["owners"] == ["first.cpp", "second.cpp"] for row in atoms.values()))
        with partial.open("rb") as stream:
            self.assertTrue(all(s["sh_flags"] == 2 for s in ELFFile(stream).iter_sections() if s.name.startswith(strings.PREFIX)))

    def test_named_string_symbol_metadata_is_preserved(self):
        source = SOURCE.replace('.Llong:', '.local named\n.type named,@object\n.hidden named\nnamed:')
        source = source.replace('.Lshort:', '.size named,.-named\n.Lshort:').replace('.Llong', 'named')
        path = self.compile("named", source)
        with path.open("rb") as stream:
            before = ELFFile(stream).get_section_by_name(".symtab").get_symbol_by_name("named")[0]
            identity = before["st_size"], before["st_info"], before["st_other"]
        strings.split_object(path, self.aliases())
        with path.open("rb") as stream:
            after = ELFFile(stream).get_section_by_name(".symtab").get_symbol_by_name("named")[0]
            self.assertEqual(identity, (after["st_size"], after["st_info"], after["st_other"]))

    def test_true_pool_one_past_and_cross_atom_named_objects_rejected(self):
        path = self.compile("one-past", SOURCE + '\n.long .Lend\n')
        with self.assertRaisesRegex(ValueError, "one-past"):
            strings.split_object(path, self.aliases())
        path = self.compile("cross-object", SOURCE.replace('.Llong:', '.type named,@object\nnamed:\n.Llong:') +
                            '\n.size named,30\n')
        with self.assertRaisesRegex(ValueError, "crosses an atom"):
            strings.split_object(path, self.aliases())

    def test_implicit_addends_and_writable_string_sections_rejected(self):
        for mode in ("implicit", "writable"):
            path = self.compile(mode)
            raw = bytearray(path.read_bytes())
            with path.open("rb") as stream:
                elf = ELFFile(stream)
                for index, section in enumerate(elf.iter_sections()):
                    if mode == "implicit" and section["sh_type"] == "SHT_RELA":
                        struct.pack_into(">I", raw, elf["e_shoff"] + index * 40 + 4, 9)
                        struct.pack_into(">I", raw, elf["e_shoff"] + index * 40 + 36, 8)
                        break
                    if mode == "writable" and section["sh_flags"] == 0x32:
                        struct.pack_into(">I", raw, elf["e_shoff"] + index * 40 + 8, 0x33)
                        break
            path.write_bytes(raw)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                strings.split_object(path, self.aliases())

    def test_new_comdat_function_isolated_from_mixed_mutable_storage(self):
        row = {"index": 1, "name": ".foxtrot.text", "group": "fixture", "bytes": 4, "flags": 0x206,
               "type": "SHT_PROGBITS", "align": 4, "owners": ["menu.cpp"], "sha256": "0" * 64,
               "definitions": [{"name": "fixture", "type": "STT_FUNC", "value": 0, "size": 4}]}
        pinned.plan_sections([row], [{"name": "fixture", "section": 1}], [], {"sections": []}, ["fixture"])
        self.assertTrue(row["moved"])
        row["flags"], row["name"] = 0x203, ".foxtrot.data"
        with self.assertRaisesRegex(ValueError, "Unsupported mixed"):
            pinned.plan_sections([row], [{"name": "fixture", "section": 1}], [], {"sections": []}, ["fixture"])

    def test_ha_carry_nonadjacent_pairs_and_ambiguous_halves(self):
        data = struct.pack(">HHHH", 0x8048, 0xF300, 0x8048, 0xF300)
        sections = {"fixture": {"address": 0x100, "size": len(data), "data": data}}
        refs = [{"site": 0x100, "type": 6}, {"site": 0x104, "type": 6},
                {"site": 0x102, "type": 4}, {"site": 0x106, "type": 4}]
        self.assertEqual(strings.decode_target(refs, sections), 0x8047F300)
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            strings.decode_target(refs[:2], sections)
        sections["fixture"]["data"] = data[:-2] + b"\xF2\xFF"
        with self.assertRaisesRegex(ValueError, "halves disagree"):
            strings.decode_target(refs, sections)

    def test_proof_rejects_missing_sites_wrong_reader_and_suffix_bounds(self):
        for change in ("missing", "owner", "target", "suffix"):
            bad = deepcopy(self.receipt)
            entry = bad["builds"]["console-us"]
            atom = next(iter(entry["protected_atoms"].values()))
            if change == "missing":
                atom["references"].pop()
            elif change == "owner":
                atom["references"][0]["owner"] = "menu.cpp"
            elif change == "target":
                atom["address"] += 1
            else:
                atom["canonical_offset"] = atom["bytes"]
            path = self.folder / (change + ".json")
            path.write_text(json.dumps(bad))
            with self.subTest(change=change), patch.object(strings, "LAYOUT", path), self.assertRaises(ValueError):
                strings.load(pinned.LAYOUT, owned.LAYOUT, timer.BASELINE, self.original, self.sources, "console-us")

    def test_frozen_literals_and_each_original_reference_remain_verifiable(self):
        entry = self.receipt["builds"]["console-us"]
        sections = pinned.flat_sections(pinned.ROOT / "build/baseline-console/susamune_us.o")
        self.assertEqual(strings.verify_linked(sections, entry), 5)
        atom = next(iter(entry["protected_atoms"].values()))
        bad = deepcopy(sections)
        row = next(s for s in bad.values() if s["address"] <= atom["address"] < s["address"] + s["size"])
        data = bytearray(row["data"])
        data[atom["address"] - row["address"]] ^= 1
        row["data"] = bytes(data)
        with self.assertRaisesRegex(ValueError, "literal bytes"):
            strings.verify_linked(bad, entry)


if __name__ == "__main__":
    unittest.main()
