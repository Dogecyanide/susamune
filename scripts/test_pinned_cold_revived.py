"""Newly reachable Dolphin CPU functions cannot retire an existing memory span."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import pinned_cold_extensions as extensions
import pinned_source_sections as owned
import link_pinned_mod as pinned
ROOT = Path(__file__).resolve().parents[1]

def fixture():
    name = 'exportLatest__5GhostFPvUlUcPCcPUlPUl'
    prior = dict(name='.text.'+name, group='', live=False, cold=False, flags=6,
                 type='SHT_PROGBITS', owners=['ghost.cpp'], definition_count=1,
                 single_symbol=name, address=0, linked_bytes=1836, sha256='old')
    function = dict(name=name, owner='ghost.cpp', old_address=0x80520000, size=2088)
    row = dict(name=prior['name'], group='', live=True, cold=False, moved=True,
               flags=6, type='SHT_PROGBITS', owners=['ghost.cpp'], bytes=2088,
               sha256='new', analysis_address=function['old_address'],
               definitions=[dict(name=name,type='STT_FUNC',value=0,size=2088)])
    return [row], [function], dict(sections=[prior])

class RevivedTests(unittest.TestCase):
    def test_unlinked_baseline_becomes_new_cpu_input(self):
        rows, funcs, baseline = fixture()
        extensions.mark_inputs(rows, funcs, baseline, target='emu')
        self.assertTrue(rows[0]['cold_new'])
        self.assertFalse(rows[0]['moved'])
        self.assertEqual(rows[0]['cold_revived']['prior_sha256'], 'old')
        self.assertNotIn('cold_extension', rows[0])

    def test_linked_mixed_mutable_or_unknown_baseline_rejected(self):
        for change in ({'live':True},{'address':0x80420000},{'cold':True},
                       {'flags':7},{'definition_count':2},{'owners':['other.cpp']},
                       {'single_symbol':'wrong'}):
            rows, funcs, baseline = fixture();baseline['sections'][0].update(change)
            with self.assertRaises(ValueError):
                extensions.mark_inputs(rows, funcs, baseline, target='emu')

    def test_current_owner_boundaries_and_protection_enforced(self):
        for change in ({'owners':['other.cpp']},{'bytes':2084},{'flags':7}):
            rows, funcs, baseline = fixture();rows[0].update(change)
            with self.assertRaises(ValueError):
                extensions.mark_inputs(rows, funcs, baseline, target='emu')
        rows, funcs, baseline = fixture()
        with self.assertRaises(ValueError):
            extensions.mark_inputs(rows, funcs, baseline,[dict(address=0x80520000,size=4)],'emu')
        with self.assertRaises(ValueError):
            extensions.mark_inputs(rows, funcs, baseline, target='console')

    def test_native_storage_placement_does_not_change_console_selectors(self):
        native=extensions.selectors('emu');console=extensions.selectors('console')
        for owner,names in extensions.EMULATOR_EXISTING_MODULES.items():
            self.assertTrue(names <= native[owner])
            self.assertFalse(names & console.get(owner,frozenset()))

    def test_all_three_dolphin_baselines_agree(self):
        data=json.loads((ROOT/'doc/timewarp-pinned-layout.json').read_text())
        for region in ('jp','us','pal'):
            baseline=owned.expand_layout(owned.LAYOUT,pinned.LAYOUT,data,'emu',region,pinned.timer.BASELINE)
            for owner,names in extensions.REVIVED_EMULATOR_MODULES.items():
                for name in names:
                    old=next(r for r in baseline['sections'] if r.get('single_symbol')==name or r['name']=='.text.'+name+'.owner.'+owner.replace('.','_')+'.part0')
                    self.assertFalse(old['live']);self.assertEqual(old['address'],0)
                    self.assertEqual(old['owners'],[owner]);self.assertEqual(old['definition_count'],1)
                    rows,funcs,_=fixture();rows[0].update(name=old['name'],owners=[owner])
                    rows[0]['definitions'][0]['name']=name;funcs[0].update(name=name,owner=owner)
                    extensions.mark_inputs(rows,funcs,dict(sections=[old]),target='emu')

if __name__ == '__main__':unittest.main()
