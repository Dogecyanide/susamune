"""Prove menu COMDAT jump-table ownership with real PPC object mutations."""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import unittest

from elftools.elf.elffile import ELFFile

import link_pinned_mod as pinned
import pinned_menu_tables as tables


class MenuTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = pinned.ROOT / "build/timewarp-pr13-menu-table-test"
        source_dir = cls.folder / "CMakeFiles/susamune_obj_jp.dir/src"
        source_dir.mkdir(parents=True, exist_ok=True)
        cls.source = source_dir / "menu.cpp.obj"
        assembly = cls.folder / "fixture.s"
        assembly.write_text('''
.file "menu.cpp"
.section .text.fixture_menu,"axG",@progbits,fixture_menu,comdat
.balign 4
.weak fixture_menu
.type fixture_menu,@function
fixture_menu:
lis 3,.Ltable@ha
addi 3,3,.Ltable@l
blr
.size fixture_menu,.-fixture_menu
.section .rodata.fixture_menu,"aG",@progbits,fixture_menu,comdat
.balign 4
.Ltable:
.long fixture_menu+4,fixture_menu+8
''')
        subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                        "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(assembly),
                        "-o", str(cls.source)], check=True, capture_output=True)
        cls.rows, _, _, _ = pinned.inputs(cls.source, cls.folder, "jp")
        baseline = deepcopy(cls.rows)
        for row in baseline:
            row.update(live=True, address=0x80400000 + row["index"] * 0x1000, linked_bytes=row["bytes"],
                       definition_count=len(row["definitions"]),
                       single_symbol=row["definitions"][0]["name"] if len(row["definitions"]) == 1 else None)
        cls.baseline = {"sections": baseline}
        cls.name, cls.signature = ".rodata.fixture_menu", "fixture_menu"

    def proof(self, partial=None, rows=None, protected=(), baseline=None):
        return tables.validate_all(rows or self.rows, partial or self.source, self.folder, "jp", protected,
                                   baseline or self.baseline)

    def mutate(self, label, change):
        data = bytearray(self.source.read_bytes())
        with self.source.open("rb") as stream:
            change(data, ELFFile(stream))
        path = self.folder / (label + ".o")
        path.write_bytes(data)
        return path

    def test_current_source_table_and_self_targets_are_certified(self):
        proof = self.proof()[self.name]
        self.assertEqual(proof["owner"], "menu.cpp")
        self.assertEqual([row["target_offset"] for row in proof["outgoing"]], [4, 8])
        self.assertEqual({row["type"] for row in proof["incoming"]}, {4, 6})

    def test_current_reader_ownership_must_be_unique(self):
        rows = deepcopy(self.rows)
        reader = next(row for row in rows if row["name"] == ".text.fixture_menu")
        reader["owners"].append("qft_timer.cpp")
        self.assertEqual(self.proof(rows=rows), {})

    def test_protected_frozen_table_or_reader_is_rejected(self):
        for row in self.baseline["sections"]:
            if row["name"] in (self.name, ".text.fixture_menu"):
                with self.subTest(name=row["name"]), self.assertRaisesRegex(ValueError, "protected or unknown"):
                    self.proof(protected=[{"address": row["address"], "size": row["bytes"]}])

    def test_mutable_payload_and_external_target_are_rejected(self):
        def writable(data, elf):
            index = next(i for i, section in enumerate(elf.iter_sections()) if section.name == self.name)
            struct.pack_into(">I", data, elf["e_shoff"] + index * elf["e_shentsize"] + 8, 0x203)
        def payload(data, elf):
            data[elf.get_section_by_name(self.name)["sh_offset"]] = 1
        def external(data, elf):
            section = elf.get_section_by_name(".rela" + self.name)
            struct.pack_into(">i", data, section["sh_offset"] + 8, 12)
        for label, mutation, message in (("writable", writable, "immutable"),
                                         ("payload", payload, "immutable"),
                                         ("one_past_reader", external, "interior self")):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                self.proof(partial=self.mutate(label, mutation))

    def test_source_payload_mismatch_is_rejected(self):
        def change(data, elf):
            section = elf.get_section_by_name(".text.fixture_menu")
            data[section["sh_offset"] + 3] ^= 1
        with self.assertRaisesRegex(ValueError, "differs from its current source"):
            self.proof(partial=self.mutate("reader_changed", change))

    def test_cold_group_reader_does_not_depend_on_text_section_spelling(self):
        def rename(data, elf):
            names = elf.get_section(elf["e_shstrndx"])
            at = names.data().index(b".text.fixture_menu\0")
            replacement = b".foxtrot.text\0"
            data[names["sh_offset"] + at:names["sh_offset"] + at + len(replacement)] = replacement
        proof = tables.inspect(self.mutate("cold_reader", rename), self.name, self.signature)
        self.assertEqual(len(proof["outgoing"]), 2)

    def test_missing_duplicate_and_unsupported_relocations_are_rejected(self):
        original = tables.inspect(self.source, self.name, self.signature)
        for change in ("missing", "duplicate", "unaligned", "foreign_type", "one_past", "half"):
            facts = deepcopy(original)
            if change == "missing": facts["outgoing"].pop()
            elif change == "duplicate": facts["outgoing"][1]["offset"] = 0
            elif change == "unaligned": facts["outgoing"][0]["target_offset"] = 1
            elif change == "foreign_type": facts["incoming"][0]["type"] = 1
            elif change == "one_past": facts["incoming"][0]["target_offset"] = facts["bytes"]
            else: facts["incoming"].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                tables.verify_references(facts)

    def test_explicit_new_wireframe_reader_uses_same_proof_without_broadening_owners(self):
        signature = "edgeVertices__21GameWireframeGeometryFUiUi"
        source_dir = self.folder / "wireframe/CMakeFiles/susamune_obj_jp.dir/src"
        source_dir.mkdir(parents=True, exist_ok=True)
        assembly = self.folder / "wireframe.s"
        assembly.write_text((self.folder / "fixture.s").read_text().replace("menu.cpp", "game_wireframe.cpp")
                            .replace("fixture_menu", signature))
        source = source_dir / "game_wireframe.cpp.obj"
        subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                        "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(assembly),
                        "-o", str(source)], check=True, capture_output=True)
        build = self.folder / "wireframe"
        rows, _, _, _ = pinned.inputs(source, build, "jp")
        proof = tables.validate_all(rows, source, build, "jp", [], {"sections": []})
        self.assertEqual(proof[".rodata." + signature]["owner"], "game_wireframe.cpp")
        reader = next(row for row in rows if row["name"] == ".text." + signature)
        with self.assertRaisesRegex(ValueError, "already exists"):
            tables.validate_all(rows, source, build, "jp", [], {"sections": [reader]})
        reader["owners"] = ["unreviewed.cpp"]
        self.assertEqual(tables.validate_all(rows, source, build, "jp", [], {"sections": []}), {})

    def test_exact_metadata_global_reader_retains_source_and_frozen_protection_checks(self):
        signature = "menuRowValue__15MetadataDisplayCFi"
        build = self.folder / "metadata"
        source_dir = build / "CMakeFiles/susamune_obj_jp.dir/src"
        source_dir.mkdir(parents=True, exist_ok=True)
        assembly = self.folder / "metadata.s"
        text = (self.folder / "fixture.s").read_text()
        text = text.replace("menu.cpp", "metadata_display.cpp").replace("fixture_menu", signature)
        text = text.replace('"axG",@progbits,' + signature + ',comdat', '"ax",@progbits')
        text = text.replace('"aG",@progbits,' + signature + ',comdat', '"a",@progbits')
        assembly.write_text(text.replace(".weak ", ".global "))
        source = source_dir / "metadata_display.cpp.obj"
        subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                        "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(assembly),
                        "-o", str(source)], check=True, capture_output=True)
        rows, _, _, _ = pinned.inputs(source, build, "jp")
        frozen = deepcopy(rows)
        for row in frozen:
            row.update(live=True, address=0x80400000 + row["index"] * 0x1000,
                       linked_bytes=row["bytes"], definition_count=len(row["definitions"]),
                       single_symbol=row["definitions"][0]["name"] if len(row["definitions"]) == 1 else None)
        baseline = {"sections": frozen}
        proof = tables.validate_all(rows, source, build, "jp", [], baseline)
        self.assertEqual(proof[".rodata." + signature]["owner"], "metadata_display.cpp")
        for row in frozen:
            if row["name"] in (".rodata." + signature, ".text." + signature):
                with self.subTest(name=row["name"]), self.assertRaisesRegex(ValueError, "protected or unknown"):
                    tables.validate_all(rows, source, build, "jp",
                                        [{"address": row["address"], "size": row["bytes"]}], baseline)
        reader = next(row for row in rows if row["name"] == ".text." + signature)
        reader["owners"] = ["unreviewed.cpp"]
        self.assertEqual(tables.validate_all(rows, source, build, "jp", [], baseline), {})
        with self.assertRaisesRegex(ValueError, "COMDAT"):
            tables.inspect(source, ".rodata." + signature, signature)

    def test_metadata_labels_only_point_to_complete_immutable_string_atoms(self):
        signature = "menuRowName__15MetadataDisplayFi"
        name = ".data.rel.ro..Lswitch.table." + signature
        build = self.folder / "metadata-labels"
        source_dir = build / "CMakeFiles/susamune_obj_jp.dir/src"
        source_dir.mkdir(parents=True, exist_ok=True)
        assembly = build / "fixture.s"
        atom = ".twp.string." + tables.sha(b"Value gap\0")
        assembly.write_text(f'''
.file "metadata_display.cpp"
.section .text.{signature},"ax",@progbits
.balign 4
.global {signature}
.type {signature},@function
{signature}:
lis 3,.Ltable@ha
addi 3,3,.Ltable@l
blr
.size {signature},.-{signature}
.section {name},"aw",@progbits
.balign 4
.Ltable:
.long .Llabel,.Llabel
.section {atom},"aMS",@progbits,1
.Llabel:
.asciz "Value gap"
''')
        source = source_dir / "metadata_display.cpp.obj"
        subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                        "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(assembly),
                        "-o", str(source)], check=True, capture_output=True)
        rows, _, _, _ = pinned.inputs(source, build, "jp")
        proof = tables.validate_all(rows, source, build, "jp", [], {"sections": []})
        self.assertEqual(len(proof[name]["string_targets"]), 2)
        parsed = tables.catalog(source)
        table_index = next(i for i, r in parsed[0].items() if r["name"] == name)
        target = parsed[4][table_index][0]["target"]
        for change in ("writable", "interior", "missing_nul", "wrong_hash"):
            changed = deepcopy(parsed)
            if change == "writable":
                changed[0][target]["sh_flags"] |= 1
            elif change == "interior":
                changed[4][table_index][0]["target_offset"] = 4
            elif change == "missing_nul":
                changed[0][target]["data"] = b"Value gap"
            else:
                changed[0][target]["name"] = ".twp.string.unreviewed"
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "immutable string atom"):
                tables.inspect(source, name, signature, changed, comdat=False, string_table=True)


if __name__ == "__main__":
    unittest.main()
