"""Linked cold calls must retain their original target identity across allocation."""
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import link_pinned_mod as pinned
import timewarp_cold_cluster as cold


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    old_a, old_b, old_c = 0x80410000, 0x80410100, 0x80410200
    external_a, external_alias, external_b = 0x80510000, 0x80510100, 0x80510200
    functions = []
    for name, address, tag, targets in (
        ('caller_a', old_a, 101, (old_c, external_a, external_alias, 0x80001000)),
        ('caller_b', old_b, 202, (old_a, external_b)),
        ('caller_c', old_c, 303, (old_b,)),
    ):
        words = [0x9421FFF0, 0x7C0802A6, 0x90010014]
        records = []
        for target in targets:
            site = address + len(words) * 4
            words.append(0x48000001 | ((target - site) & 0x03FFFFFC))
            records.append({'site': site, 'type': cold.REL24, 'target': target})
        words.extend((0x38600000 | tag, 0x80010014, 0x7C0803A6, 0x38210010, 0x4E800020))
        payload = struct.pack('>' + 'I' * len(words), *words)
        functions.append({'name': name, 'old_address': address, 'size': len(payload),
                          'data': payload, 'relocations': records})
    return functions, {external_a: old_b, external_alias: old_b, external_b: old_a}


def read_branch(payload, offset, site):
    word = struct.unpack_from('>I', payload, offset)[0]
    if word >> 26 != 18 or word & 3 != 1:
        raise AssertionError('Expected a relative BL instruction')
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return (site + displacement) & 0xFFFFFFFF


def read_gate(payload, offset):
    if offset < 0 or offset + 16 > len(payload):
        raise AssertionError('Outbound branch missed its cold-image veneer')
    high, low, move, jump = struct.unpack_from('>4I', payload, offset)
    if (high & 0xFFFF0000 != 0x3D800000 or low & 0xFFFF0000 != 0x618C0000 or
            move != 0x7D8903A6 or jump != 0x4E800420):
        raise AssertionError('Outbound branch called a function instead of an exact veneer')
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def verify_linked_calls(functions, originals, targets, payload, base):
    moved = {f['old_address']: f['cold_address'] for f in functions}
    checked = []
    for linked, original in zip(functions, originals):
        for relocation in original['relocations']:
            offset = relocation['site'] - original['old_address']
            site = linked['cold_address'] + offset
            branch = read_branch(payload, site - base, site)
            target = relocation['target']
            if target in moved:
                if branch != moved[target]:
                    raise AssertionError('Internal call did not use the original cold function identity')
                checked.append(('internal', branch - site))
            else:
                resolved = read_gate(payload, branch - base)
                if resolved != targets.get(target, target):
                    raise AssertionError('Outbound veneer did not use the allocated retained address')
                checked.append(('external', resolved))
    return checked


class ColdTargetIdentityTests(unittest.TestCase):
    def test_internal_and_retained_targets_may_share_the_same_numeric_address(self):
        functions, targets = fixture()
        originals = deepcopy(functions)
        base = 0x71E3F0A0
        with tempfile.TemporaryDirectory(prefix='cold-target-identity-', dir=ROOT / 'build') as temporary:
            folder = Path(temporary)
            cold.link_cold(folder, functions, base, 'identity', external_targets=targets)
            payload = (folder / 'cold-identity.bin').read_bytes()
            checked = verify_linked_calls(functions, originals, targets, payload, base)
        self.assertEqual(len(checked), 7)
        self.assertTrue(any(kind == 'internal' and value > 0 for kind, value in checked))
        self.assertTrue(any(kind == 'internal' and value < 0 for kind, value in checked))
        self.assertEqual(sum(kind == 'external' and value == 0x80410100 for kind, value in checked), 2)
        self.assertIn(('external', 0x80410000), checked)
        self.assertIn(('external', 0x80001000), checked)

    def test_production_auditor_rejects_legacy_premapped_target_payload(self):
        functions, targets = fixture()
        original_records = [dict(r) for f in functions for r in f['relocations']]
        legacy = deepcopy(functions)
        for function in legacy:
            for relocation in function['relocations']:
                relocation['target'] = targets.get(relocation['target'], relocation['target'])
        rows = [dict(moved=True, analysis_address=old, address=new, linked_bytes=4)
                for old, new in targets.items()]
        base = 0x91E3F0A0
        with tempfile.TemporaryDirectory(prefix='cold-target-audit-', dir=ROOT / 'build') as temporary:
            folder = Path(temporary)
            cold.link_cold(folder, functions, base, 'valid', external_targets=targets)
            cold.link_cold(folder, legacy, base, 'legacy')
            with patch.object(cold, 'final_relocations', return_value=original_records):
                self.assertEqual(pinned.verify_cold_branches(
                    Path('mock-analysis.elf'), (folder / 'cold-valid.bin').read_bytes(),
                    base, rows, functions), 7)
                with self.assertRaisesRegex(ValueError, 'Cold external branch changed'):
                    pinned.verify_cold_branches(
                        Path('mock-analysis.elf'), (folder / 'cold-legacy.bin').read_bytes(),
                        base, rows, legacy)


if __name__ == '__main__':
    unittest.main()
