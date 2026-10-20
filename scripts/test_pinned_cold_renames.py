"""Signature changes keep exact current ownership and explicit prior retirement."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import pinned_cold_extensions as extensions


ROOT = Path(__file__).resolve().parents[1]


def fixture(current=None):
    current = current or next(iter(extensions.RENAMED_INPUTS['ghost.cpp']))
    previous = extensions.RENAMED_INPUTS['ghost.cpp'][current]
    suffix = '.owner.ghost_cpp.part0'
    prior = dict(name='.text.' + previous + suffix, group='', live=True, cold=False,
                 source_owned=True, flags=6, type='SHT_PROGBITS', owners=['ghost.cpp'],
                 definition_count=1, address=0x80420000, linked_bytes=260, sha256='old')
    function = dict(name=current, owner='ghost.cpp', old_address=0x80520000, size=280)
    row = dict(name='.text.' + current + suffix, group='', live=True, cold=False,
               moved=True, flags=6, type='SHT_PROGBITS', owners=['ghost.cpp'],
               bytes=280, sha256='new', analysis_address=function['old_address'],
               definitions=[dict(name=current, type='STT_FUNC', value=0, size=280)])
    return [row], [function], dict(sections=[prior], retired_missing=[prior])


class ColdRenameTests(unittest.TestCase):
    def test_exact_two_renames_report_the_prior_span_once(self):
        for current in extensions.RENAMED_INPUTS['ghost.cpp']:
            rows, functions, baseline = fixture(current)
            extensions.mark_inputs(rows, functions, baseline)
            self.assertTrue(rows[0]['cold_new'])
            self.assertFalse(rows[0]['moved'])
            self.assertNotIn('cold_extension', rows[0])
            self.assertEqual(rows[0]['cold_renamed']['retired_address'], 0x80420000)
            self.assertEqual(rows[0]['cold_renamed']['retired_bytes'], 260)

    def test_current_mixed_mutable_or_mismatched_identity_rejected(self):
        for mutation in (
            lambda row: row.update(flags=7),
            lambda row: row.update(owners=['other.cpp']),
            lambda row: row.update(name='.text.unrelated.owner.ghost_cpp.part0'),
            lambda row: row['definitions'].append(dict(row['definitions'][0])),
            lambda row: row['definitions'][0].update(value=4),
            lambda row: row['definitions'][0].update(size=276),
        ):
            rows, functions, baseline = fixture()
            mutation(rows[0])
            with self.assertRaises(ValueError):
                extensions.mark_inputs(rows, functions, baseline)

    def test_prior_must_be_exclusively_owned_code_already_retired(self):
        for mutation in (
            lambda prior: prior.update(flags=7),
            lambda prior: prior.update(definition_count=2),
            lambda prior: prior.update(source_owned=False),
            lambda prior: prior.update(owners=['other.cpp']),
            lambda prior: prior.update(cold=True),
            lambda prior: prior.update(live=False),
        ):
            rows, functions, baseline = fixture()
            mutation(baseline['sections'][0])
            with self.assertRaisesRegex(ValueError, 'retired predecessor'):
                extensions.mark_inputs(rows, functions, baseline)
        rows, functions, baseline = fixture()
        baseline['retired_missing'] = []
        with self.assertRaisesRegex(ValueError, 'retired predecessor'):
            extensions.mark_inputs(rows, functions, baseline)
        rows, functions, baseline = fixture()
        rows.append({**deepcopy(baseline['sections'][0]), 'analysis_address': 0x80420000})
        with self.assertRaisesRegex(ValueError, 'retired predecessor'):
            extensions.mark_inputs(rows, functions, baseline)

    def test_old_and_current_protected_ranges_rejected(self):
        for address in (0x80420000, 0x80520000):
            rows, functions, baseline = fixture()
            with self.assertRaisesRegex(ValueError, 'protected anchor'):
                extensions.mark_inputs(rows, functions, baseline, [dict(address=address, size=4)])

    def test_unlisted_signature_has_no_new_owner_permission(self):
        rows, functions, baseline = fixture()
        functions[0]['name'] += 'l'
        rows[0]['definitions'][0]['name'] = functions[0]['name']
        with self.assertRaisesRegex(ValueError, 'ownership changed'):
            extensions.mark_inputs(rows, functions, baseline)

    def test_each_frozen_target_supplies_exact_prior_identity(self):
        receipt = json.loads((ROOT / 'doc/timewarp-pinned-source-owners.json').read_text())
        for build in receipt['builds'].values():
            for current in extensions.RENAMED_INPUTS['ghost.cpp']:
                rows, functions, baseline = fixture(current)
                name = baseline['sections'][0]['name']
                prior = next(row for row in build['sections'] if row['name'] == name)
                baseline = dict(sections=build['sections'], retired_missing=[prior])
                extensions.mark_inputs(rows, functions, baseline)
                self.assertEqual(rows[0]['cold_renamed']['prior_sha256'], prior['sha256'])


if __name__ == '__main__':
    unittest.main()
