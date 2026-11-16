"""Narrow retirement of fixed SGHF-only tables, with timer-anchor protection intact."""
import json,unittest
from copy import deepcopy
import link_pinned_mod as pinned
import pinned_source_sections as owned
import timewarp_timer_guard as timer

class GhostRetirementTests(unittest.TestCase):
 def test_all_six_frozen_layouts_contain_only_the_audited_tables(self):
  frozen=json.loads(pinned.LAYOUT.read_text())
  for target in ('console','emu'):
   for region in ('jp','us','pal'):
    baseline=owned.expand_layout(owned.LAYOUT,pinned.LAYOUT,frozen,target,region,timer.BASELINE)
    found=[r for r in baseline['sections'] if owned.retired_ghost_table(r)]
    self.assertEqual({r['name'] for r in found},set(owned._RETIRED_GHOST_TABLES))
    for row in found:
     for field,value in [('owners',['qft_timer.cpp']),('group','shared'),('flags',0x12),('cold',True),('protected_string',True),('sha256','0'*64),('linked_bytes',0),('name','.rodata.unrelated')]:
      self.assertFalse(owned.retired_ghost_table({**row,field:value}),(target,region,field))
 def test_audited_table_still_cannot_retire_a_protected_address(self):
  name=next(iter(owned._RETIRED_GHOST_TABLES));size,digest=owned._RETIRED_GHOST_TABLES[name]
  row={'name':name,'group':'','owners':[],'flags':2,'cold':False,'live':True,'address':0x80500000,'linked_bytes':size,'sha256':digest}
  baseline={'sections':[row]}
  with self.assertRaisesRegex(ValueError,'overlaps a protected anchor'):
   pinned.plan_sections([],[],[],deepcopy(baseline),[],protected=[{'address':row['address'],'size':4}])

if __name__=='__main__':unittest.main()
