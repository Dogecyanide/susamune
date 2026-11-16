"""Keep the reviewed additional hook separate from frozen layout ownership."""
import hashlib,json,unittest
from pathlib import Path
from link_pinned_mod import check_patch_source
ROOT=Path(__file__).resolve().parents[1]
class ReviewedHookTests(unittest.TestCase):
 def setUp(self):
  self.raw=(ROOT/'scripts/patches.py').read_bytes()
  self.expected=json.loads((ROOT/'doc/timewarp-pinned-layout.json').read_text())['patches_sha256']
  first=self.raw.index(b'    # proc: preserve')
  last=self.raw.index(b'    # CARDMount:',first)
  self.extra=self.raw[first:last]
 def test_exact_reviewed_delta_and_original_both_pass(self):
  self.assertTrue(check_patch_source(self.raw,self.expected))
  original=self.raw.replace(self.extra,b'',1)
  self.assertEqual(hashlib.sha256(original).hexdigest(),self.expected)
  self.assertTrue(check_patch_source(original,self.expected))
 def test_unrelated_hook_or_new_hook_mutation_is_refused(self):
  for old,new in ((b'0x8000561c',b'0x80005620'),(b'0x800f9ea8',b'0x800f9eac'),(b'susamuneSecretIntroMovie',b'susamuneSecretIntroMovix')):
   self.assertIn(old,self.raw)
   self.assertFalse(check_patch_source(self.raw.replace(old,new,1),self.expected))
 def test_duplicate_block_or_unreviewed_append_is_refused(self):
  self.assertFalse(check_patch_source(self.raw+self.extra,self.expected))
  self.assertFalse(check_patch_source(self.raw+b'\nmod_region_size += 32\n',self.expected))
if __name__=='__main__':unittest.main()
