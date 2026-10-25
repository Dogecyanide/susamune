"""Check the exact new defaults contribution with real PowerPC objects."""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import unittest

from elftools.elf.elffile import ELFFile

import link_pinned_mod as pinned
import pinned_header_constants as constants
import pinned_source_sections as owned


class HeaderConstantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = pinned.ROOT / "build/pr14-header-constant-test"
        cls.source = cls.folder / "input"
        objects = cls.source / "CMakeFiles/susamune_obj_jp.dir/src"
        objects.mkdir(parents=True, exist_ok=True)
        for module in sorted(constants.OWNERS):
            assembly = cls.folder / (module + ".s")
            assembly.write_text(f'''
.file "{module}"
.section .text.reader,"ax",@progbits
.type reader,@function
reader:
lis 3,{constants.SYMBOL}@ha
addi 3,3,{constants.SYMBOL}@l
lis 4,{constants.SYMBOL}+8@ha
addi 4,4,{constants.SYMBOL}+8@l
blr
.size reader,.-reader
.section {constants.NAME},"a",@progbits
.type {constants.SYMBOL},@object
{constants.SYMBOL}:
.byte {','.join(map(str, constants.PAYLOAD))}
.size {constants.SYMBOL},.-{constants.SYMBOL}
''')
            subprocess.run([str(pinned.ROOT / "toolchain/clang.exe"),
                            "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", str(assembly),
                            "-o", str(objects / (module + ".obj"))], check=True, capture_output=True)
        cls.object = objects / "finish_breakdown.cpp.obj"

    def check(self, path=None, owner="finish_breakdown.cpp", frozen=()):
        with (path or self.object).open("rb") as stream:
            return constants.validate(ELFFile(stream), owner, set(frozen))

    def mutate(self, label, change):
        data = bytearray(self.object.read_bytes())
        with self.object.open("rb") as stream:
            elf = ELFFile(stream)
            index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == constants.NAME)
            change(data, elf, index)
        path = self.folder / (label + ".o")
        path.write_bytes(data)
        return path

    def test_two_emitting_sources_remain_separate_and_verified(self):
        partial, proof = owned.prepare(self.source, self.folder / "output", "jp", pinned.ROOT / "toolchain",
                                       merge_sources={}, known_sections=set())
        rows, _, _, _ = pinned.inputs(partial, self.folder / "output", "jp")
        owned.verify_parts(rows, proof, {"sections": []})
        parts = [p for p in proof["parts"] if p.get("new_header_constant")]
        self.assertEqual({p["owner"] for p in parts}, constants.OWNERS)
        self.assertEqual(len({p["name"] for p in parts}), 2)
        self.assertTrue(all(p["bytes"] == 9 for p in parts))
        for change in ("owner", "payload", "combined"):
            changed = deepcopy(rows)
            row = next(r for r in changed if r["name"] == parts[0]["name"])
            if change == "owner": row["owners"] = ["qft_timer.cpp"]
            elif change == "payload": row["sha256"] = "0" * 64
            else: row["bytes"] *= 2
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "partial contribution"):
                owned.verify_parts(changed, proof, {"sections": []})

    def test_existing_frozen_or_unknown_owner_is_rejected(self):
        self.assertTrue(self.check())
        for args in ({"owner": "qft_timer.cpp"}, {"frozen": [constants.NAME]}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "new source-local"):
                self.check(**args)

    def test_payload_and_all_section_attributes_are_checked(self):
        def header(offset, value):
            return lambda data, elf, index: struct.pack_into(">I", data, elf["e_shoff"] + index * elf["e_shentsize"] + offset, value)
        changes = [("writable", header(8, 3)), ("group", header(8, 0x202)), ("merge", header(8, 0x12)),
                   ("size", header(20, 8)), ("align", header(32, 4)), ("entsize", header(36, 1)),
                   ("payload", lambda data, elf, index: data.__setitem__(elf.get_section(index)["sh_offset"], 0))]
        for label, change in changes:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "immutable payload"):
                self.check(self.mutate(label, change))

    def test_global_weak_or_extra_alias_is_rejected(self):
        def binding(value):
            def change(data, elf, index):
                symtab = elf.get_section_by_name(".symtab")
                for n, symbol in enumerate(symtab.iter_symbols()):
                    if symbol.name == constants.SYMBOL:
                        data[symtab["sh_offset"] + n * symtab["sh_entsize"] + 12] = value
            return change
        for value in (0x11, 0x21):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "definition changed"):
                self.check(self.mutate("binding" + str(value), binding(value)))
        def alias(data, elf, index):
            symtab = elf.get_section_by_name(".symtab")
            for n, symbol in enumerate(symtab.iter_symbols()):
                if symbol.name == "reader":
                    struct.pack_into(">H", data, symtab["sh_offset"] + n * symtab["sh_entsize"] + 14, index)
        with self.assertRaisesRegex(ValueError, "aliases"):
            self.check(self.mutate("alias", alias))

    def test_only_interior_ha_lo_code_references_are_accepted(self):
        def relocation(field, value):
            def change(data, elf, index):
                rel = elf.get_section_by_name(".rela.text.reader")
                struct.pack_into(">i", data, rel["sh_offset"] + field, value)
            return change
        def rel_type(data, elf, index):
            rel = elf.get_section_by_name(".rela.text.reader")
            data[rel["sh_offset"] + 7] = 1
        def outgoing(data, elf, index):
            rel_index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".rela.text.reader")
            struct.pack_into(">I", data, elf["e_shoff"] + rel_index * elf["e_shentsize"] + 28, index)
        def implicit_addend(data, elf, index):
            rel_index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".rela.text.reader")
            at = elf["e_shoff"] + rel_index * elf["e_shentsize"]
            struct.pack_into(">I", data, at + 4, 9)
            struct.pack_into(">I", data, at + 36, 8)
        def non_code(data, elf, index):
            reader = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text.reader")
            struct.pack_into(">I", data, elf["e_shoff"] + reader * elf["e_shentsize"] + 8, 2)
        for label, change in (("negative", relocation(8, -1)), ("one_past", relocation(8, 9)),
                              ("addr32", rel_type), ("outgoing", outgoing), ("implicit", implicit_addend),
                              ("non_code", non_code), ("unaligned", relocation(0, 1)),
                              ("before_instruction", relocation(0, 0)), ("beyond_code", relocation(0, 22))):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.check(self.mutate(label, change))

    def test_duplicate_named_section_is_rejected(self):
        def duplicate(data, elf, index):
            at = elf["e_shoff"] + index * elf["e_shentsize"]
            name = struct.unpack_from(">I", data, at)[0]
            other = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text.reader")
            struct.pack_into(">I", data, elf["e_shoff"] + other * elf["e_shentsize"], name)
        with self.assertRaisesRegex(ValueError, "new source-local"):
            self.check(self.mutate("duplicate", duplicate))


if __name__ == "__main__":
    unittest.main()
