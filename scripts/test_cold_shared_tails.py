"""Shared cold stubs preserve the existing absolute-call ABI."""
from copy import deepcopy
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

from elftools.elf.elffile import ELFFile

import link_pinned_mod as pinned
import timewarp_cold_cluster as cold
from test_pinned_cold_target_identity import fixture, read_branch


ROOT = Path(__file__).resolve().parents[1]


def execute(memory, start, registers):
    state = dict(registers, pc=start)
    for _ in range(5):
        word = memory[state["pc"]]
        opcode, rt, ra = word >> 26, word >> 21 & 31, word >> 16 & 31
        immediate = word & 65535
        signed = immediate - 65536 if immediate & 32768 else immediate
        state["pc"] += 4
        if opcode in (14, 15):
            assert rt == 12 and ra in (0, 12)
            state["r12"] = ((state["r12"] if ra else 0) +
                            (signed << 16 if opcode == 15 else signed)) & 0xFFFFFFFF
        elif opcode == 24:
            assert rt == ra == 12
            state["r12"] |= immediate
        elif opcode == 18:
            assert word & 3 == 0
            delta = word & 0x03FFFFFC
            if delta & 0x02000000:
                delta -= 0x04000000
            state["pc"] = (state["pc"] - 4 + delta) & 0xFFFFFFFF
        elif word == 0x7D8903A6:
            state["ctr"] = state["r12"]
        elif word == 0x4E800420:
            state["pc"] = state["ctr"]
            return state
        else:
            raise AssertionError(hex(word))
    raise AssertionError("Did not reach bctr")


def words(data, base=0):
    return {base + i: struct.unpack_from(">I", data, i)[0] for i in range(0, len(data), 4)}


REGISTERS = dict(r0=0xFFFFFFFF, r12=0x12345678, ctr=0x87654321,
                 lr=0x80423344, cr=0xFEDCBA98, xer=0xE0000000)


class SharedTailTests(unittest.TestCase):
    def compare(self, target, registers):
        data, definitions, _ = cold.outbound_gates({target: "gate"}, {}, True)
        actual = execute(words(data), definitions[0][1], registers)
        expected = execute(words(cold.veneer(target)), 0, registers)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["r12"], target)
        self.assertEqual(actual["ctr"], target)
        self.assertEqual(actual["pc"], target)
        for key in ("r0", "lr", "cr", "xer"):
            self.assertEqual(actual[key], registers[key])

    def test_aligned_low_halves_carry_and_wraparound_preserve_machine_state(self):
        for high in (0, 1, 0x7FFF, 0x8000, 0xFFFE, 0xFFFF):
            for low in range(0, 65536, 4):
                self.compare(high << 16 | low, REGISTERS)
        randomizer = random.Random(17)
        for _ in range(10000):
            registers = {key: randomizer.getrandbits(32) for key in REGISTERS}
            self.compare(randomizer.getrandbits(30) << 2, registers)

    def test_shared_branches_are_aligned_relative_nonlinking_and_bounded(self):
        source = 0x02000000
        for delta in (-0x02000000, 0, 0x01FFFFFC):
            entry = cold.shared_gate_entry(0x80008000, source, source + 4 + delta)
            word = struct.unpack_from(">I", entry, 4)[0]
            self.assertEqual(word & 0xFC000003, 0x48000000)
            self.assertEqual(word & 0x03FFFFFC, delta & 0x03FFFFFC)
        for delta in (-0x02000004, 0x02000000, 2):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                cold.shared_gate_entry(0x80008000, source, source + 4 + delta)
        for target in (-4, 0x100000000, 0x80000001):
            with self.subTest(target=target), self.assertRaises(ValueError):
                cold.shared_gate_entry(target, source, source + 8)
        with self.assertRaises(ValueError):
            cold.shared_gate_entry(0x80000000, source + 1, source + 8)

    def test_grouped_payload_resolves_allocated_targets_and_shares_only_high_words(self):
        targets = (0x80000000, 0x80007FFC, 0x80008000, 0x8000FFFC, 0xFFFF8000, 0xFFFFFFFC)
        gates = {i * 4: "gate_" + str(i) for i in range(len(targets))}
        allocated = dict(zip(gates, targets))
        data, definitions, count = cold.outbound_gates(gates, allocated, True)
        self.assertEqual(count, 3)
        self.assertEqual(len(data), len(targets) * 8 + count * 12)
        for (name, offset, size), target in zip(definitions, targets):
            self.assertEqual(size, 8)
            self.assertEqual(cold.shared_gate_target(data, offset), target)
            self.assertEqual(execute(words(data), offset, REGISTERS)["pc"], target)

    def test_tail_and_entry_corruption_are_rejected(self):
        data, _, _ = cold.outbound_gates({0x80008000: "gate"}, {}, True)
        for offset, mask in ((0, 1 << 16), (4, 1), (4, 2), (8, 1 << 16), (12, 1), (16, 1)):
            damaged = bytearray(data)
            value = struct.unpack_from(">I", damaged, offset)[0]
            struct.pack_into(">I", damaged, offset, value ^ mask)
            with self.subTest(offset=offset, mask=mask), self.assertRaises(ValueError):
                cold.shared_gate_target(damaged, 0)
        for branch in (0x49FFFFFC, 0x4A000000):
            damaged = bytearray(data)
            struct.pack_into(">I", damaged, 4, branch)
            with self.assertRaises(ValueError):
                cold.shared_gate_target(damaged, 0)
        for offset in (-4, 1, len(data) - 4):
            with self.assertRaises(ValueError):
                cold.shared_gate_target(data, offset)

    def test_linked_internal_identity_and_external_gate_proofs(self):
        functions, targets = fixture()
        originals = deepcopy(functions)
        records = [dict(r) for f in originals for r in f["relocations"]]
        rows = [dict(moved=True, analysis_address=old, address=new, linked_bytes=4)
                for old, new in targets.items()]
        base = 0x91E3F0A0
        with tempfile.TemporaryDirectory(prefix="shared-gates-", dir=ROOT / "build") as temporary:
            folder = Path(temporary)
            receipt = cold.link_cold(folder, functions, base, "shared", targets, shared_tails=True)
            payload = (folder / "cold-shared.bin").read_bytes()
            moved = {f["old_address"]: f["cold_address"] for f in functions}
            external_gate = None
            for function, original in zip(functions, originals):
                for relocation in original["relocations"]:
                    offset = relocation["site"] - original["old_address"]
                    site = function["cold_address"] + offset
                    branch = read_branch(payload, site - base, site)
                    target = relocation["target"]
                    if target in moved:
                        self.assertEqual(branch, moved[target])
                    else:
                        actual = execute(words(payload, base), branch, REGISTERS)
                        self.assertEqual(actual["pc"], targets.get(target, target))
                        external_gate = branch - base
            with patch.object(cold, "final_relocations", return_value=records):
                self.assertEqual(pinned.verify_cold_branches(
                    Path("mock"), payload, base, rows, functions, shared_tails=True), 7)
                damaged = bytearray(payload)
                damaged[external_gate + 3] ^= 4
                with self.assertRaisesRegex(ValueError, "Cold external branch changed"):
                    pinned.verify_cold_branches(Path("mock"), damaged, base, rows, functions,
                                                shared_tails=True)
            self.assertTrue(receipt["all_function_bytes_verified"])
            self.assertTrue(receipt["all_gates_verified"])
            self.assertEqual(receipt["outbound_gate_format"], "shared-high-v1")

    def test_default_incoming_stubs_keep_the_original_sixteen_bytes(self):
        gates = {0x91E3F0A0: "incoming_a", 0x91E48000: "incoming_b"}
        with tempfile.TemporaryDirectory(prefix="incoming-gates-", dir=ROOT / "build") as temporary:
            path = Path(temporary) / "incoming.o"
            cold.write_object(path, [], gates)
            with path.open("rb") as stream:
                elf = ELFFile(stream)
                self.assertEqual(elf.get_section_by_name(".text.gates").data(),
                                 b"".join(cold.veneer(target) for target in gates))
                sizes = {s.name: s["st_size"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
                self.assertEqual([sizes[name] for name in gates.values()], [16, 16])


if __name__ == "__main__":
    unittest.main()
