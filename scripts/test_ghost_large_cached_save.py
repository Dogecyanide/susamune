"""Large libraries keep bounded metadata while mutation targets are checked live."""
import ctypes as C
from pathlib import Path
import sys,struct,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import test_ghost_kernel_paging as base
import test_ghost_cached_save as small
import test_ghost_trace_publication as pub
from test_ghost_format import build_ghost
from test_ghost_storage import envelope
from test_ghost_recording import manifest
PERSONAL=base.PERSONAL;AUTO=base.AUTO

def compile_storage(cls,method):method.__func__(cls)

def instrument(fixture):
 fixture=small.instrument(fixture).replace('static int f_open_char(','static bool reuseHoles;\nstatic int f_open_char(')
 old='if(i<0) { if(testCount==FIXTURE_FILES) return FR_DENIED; i=(int)testCount++; copystr(testFiles[i].path,path); }'
 new='if(i<0) { if(reuseHoles)for(u32 j=0;j<testCount;++j)if(!testFiles[j].live){i=(int)j;break;} if(i<0){if(testCount==FIXTURE_FILES)return FR_DENIED;i=(int)testCount++;} copystr(testFiles[i].path,path); }'
 assert old in fixture
 return fixture.replace(old,new)

BRIDGE=small.CachedSaveTests.bridge_source+r'''
__declspec(dllexport) void holes(unsigned value){reuseHoles=value;}
__declspec(dllexport) unsigned fingerprint(void){return ListCache[0].directoryFingerprint;}
__declspec(dllexport) unsigned cacheFirst(void){return ListCache[0].first;}
__declspec(dllexport) unsigned cacheSize(void){return sizeof(struct GhostListCache);}
__declspec(dllexport) void changeFingerprint(unsigned value){ListCache[0].directoryFingerprint=value;}
__declspec(dllexport) void reorder(const char*a,const char*b){int x=lookup(a),y=lookup(b);if(x>=0&&y>=0){struct TestFile t=testFiles[x];testFiles[x]=testFiles[y];testFiles[y]=t;}}
'''
class ProductionRegressionTests(base.GhostKernelPagingTests):
 @classmethod
 def setUpClass(cls):compile_storage(cls,base.GhostKernelPagingTests.setUpClass)

class LargeSaveTests(unittest.TestCase):
 fixture_transform=staticmethod(instrument);bridge_source=BRIDGE
 @classmethod
 def setUpClass(cls):compile_storage(cls,base.GhostKernelPagingTests.setUpClass)
 add=base.GhostKernelPagingTests.add;file=base.GhostKernelPagingTests.file
 request=base.GhostKernelPagingTests.request;page=base.GhostKernelPagingTests.page
 def setUp(self):
  base.GhostKernelPagingTests.setUp(self);self.dll.failDirectoryRead(0);self.dll.holes(0)
  self.dll.erase.argtypes=[C.c_char_p];self.dll.reorder.argtypes=[C.c_char_p,C.c_char_p]
 def populate(self,count,offset=0,profile=0):
  ids=list(range(45))+list(range(48,count+3)) if count>45 else list(range(count))
  for slot in ids:self.add(f'/Moonshine data/ghosts/jp/p{profile}/g{slot:02}a.sgh',envelope(build_ghost(source_profile=profile),profile=profile,slot=slot))
  self.page(offset,profile=profile);return ids
 def save(self,profile=0):
  r=self.request(1,AUTO,profile=profile,payload=build_ghost(ghost_id=123,source_profile=profile));self.assertEqual(r['status'],0);return r
 def test_65_129_257_rows_skip_old_headers_without_capping_library(self):
  for count in (65,129,257):
   self.setUp();ids=self.populate(count);self.assertNotEqual(self.dll.fingerprint(),0)
   self.assertEqual(self.save()['slot'],ids[-1]+1)
   self.assertEqual((self.dll.reads(),self.dll.opens(),self.dll.directoryReads()),(0,3,count+2))
   self.assertEqual(self.page(cached=True)[1:],(count+1,4*(count+1),ids[-1]+2));self.assertEqual(self.dll.opens(),0)
 def test_nonzero_windows_and_partial_tail_keep_rows_and_duration(self):
  for count,offset in ((129,64),(129,128),(257,192),(65,64)):
   self.setUp();ids=self.populate(count,offset);self.assertEqual(self.dll.cacheFirst(),offset)
   self.save();self.assertEqual(self.dll.reads(),0)
   rows,total,duration,nxt=self.page(offset,cached=True)
   self.assertEqual([r[0] for r in rows],(ids+[ids[-1]+1])[offset:offset+16])
   self.assertEqual((total,duration,nxt),(count+1,4*(count+1),ids[-1]+2));self.assertEqual(self.dll.opens(),0)
 def test_cache_size_is_unchanged(self):self.assertEqual(self.dll.cacheSize(),0x3920)
 def test_repeated_appends_update_full_names_witness(self):
  self.populate(65)
  for count in range(66,72):
   self.save();self.assertEqual(self.dll.reads(),0);self.assertEqual(self.page(cached=True)[1],count);self.assertEqual(self.dll.reads(),0)
 def test_missing_uncached_row_forces_fresh_scan(self):
  ids=self.populate(129);self.dll.erase((PERSONAL+f'g{ids[100]:02}a.sgh').encode())
  self.save();self.assertEqual(self.dll.reads(),128);self.assertEqual(self.page(cached=True)[1],129)
 def test_uncached_order_change_forces_fresh_scan(self):
  ids=self.populate(129);self.dll.reorder((PERSONAL+f'g{ids[100]:02}a.sgh').encode(),(PERSONAL+f'g{ids[110]:02}a.sgh').encode())
  self.save();self.assertEqual(self.dll.reads(),129)
 def test_unknown_file_disables_fast_eligibility(self):
  self.populate(65);self.add(PERSONAL+'notes.tmp',b'private');self.save()
  self.assertEqual(self.dll.reads(),65);self.assertEqual(self.dll.fingerprint(),0)
 def test_added_b_name_forces_full_check_then_known_pair_may_reuse_metadata(self):
  self.populate(65);data=envelope(build_ghost(),generation=2);self.add(PERSONAL+'g00b.sgh',data);self.save()
  self.assertGreaterEqual(self.dll.reads(),66);self.assertNotEqual(self.dll.fingerprint(),0)
  self.assertEqual(self.file(PERSONAL+'g00b.sgh'),data);self.save();self.assertEqual(self.dll.reads(),0)
 def test_b_before_a_is_in_full_names_witness_without_reordering_rows(self):
  self.add(PERSONAL+'g00b.sgh',envelope(generation=2,flags=1));ids=self.populate(65)
  self.add(PERSONAL+'g00a.sgh',envelope(build_ghost(),generation=3));self.page()
  self.assertNotEqual(self.dll.fingerprint(),0);self.save();self.assertEqual(self.dll.reads(),0)
  self.assertEqual(self.page(cached=True)[0][0][:2],(0,3))
 def test_removed_a_leaving_b_cannot_pass_the_old_witness(self):
  self.add(PERSONAL+'g00b.sgh',envelope(generation=2,flags=1));self.populate(65)
  self.add(PERSONAL+'g00a.sgh',envelope(build_ghost(),generation=3));self.page()
  self.dll.erase((PERSONAL+'g00a.sgh').encode());r=self.save()
  self.assertGreater(self.dll.reads(),0);self.assertEqual((r['slot'],r['generation']),(0,3))
 def test_changed_b_name_is_detected_even_with_same_slot_count_and_max(self):
  self.add(PERSONAL+'g00b.sgh',envelope(generation=0,flags=1));self.populate(65)
  self.dll.erase((PERSONAL+'g00b.sgh').encode());self.add(PERSONAL+'g67b.sgh',envelope(slot=67,generation=0,flags=1))
  self.save();self.assertGreater(self.dll.reads(),0)
 def test_b_only_or_active_higher_generation_tombstone_disables_fast(self):
  self.add(PERSONAL+'g00b.sgh',envelope(generation=2,flags=1));self.populate(65)
  self.assertEqual(self.dll.fingerprint(),0);r=self.save();self.assertEqual((r['slot'],r['generation']),(0,3))
  self.setUp();self.add(PERSONAL+'g00b.sgh',envelope(build_ghost(),generation=2));self.page()
  self.assertEqual(self.dll.fingerprint(),0);self.save();self.assertGreater(self.dll.reads(),0)
 def test_names_hint_does_not_authorize_loading_changed_bank_headers(self):
  self.populate(65);self.add(PERSONAL+'g00b.sgh',envelope(generation=0,flags=1));self.page()
  self.add(PERSONAL+'g00b.sgh',envelope(version=4));self.save();self.assertEqual(self.dll.reads(),0)
  self.assertEqual(self.request(2,0,generation=1)['status'],-8)
 def test_tombstone_or_unsafe_row_never_gets_a_names_witness(self):
  for data in (b'broken',envelope(slot=70,generation=7,flags=1)):
   self.setUp();self.populate(65);self.add(PERSONAL+'g70a.sgh',data);self.page()
   self.assertEqual(self.dll.fingerprint(),0);self.save();self.assertGreater(self.dll.reads(),0)
 def test_reused_fat_directory_hole_does_not_publish_wrong_order(self):
  self.add(PERSONAL+'deleted.tmp',b'x');self.dll.erase((PERSONAL+'deleted.tmp').encode())
  self.populate(65);self.dll.holes(1);saved=self.save();self.assertEqual(self.dll.reads(),0)
  rows,total,_,_=self.page(cached=True);self.assertGreater(self.dll.reads(),0);self.assertEqual((rows[0][0],total),(saved['slot'],66))
 def test_profile_switch_cannot_borrow_another_profile_witness(self):
  self.populate(65,profile=0);self.populate(65,profile=1)
  self.save(profile=0);self.assertEqual(self.dll.reads(),65)
  self.save(profile=0);self.assertEqual(self.dll.reads(),0)
 def test_corrupt_or_disabled_witness_falls_back(self):
  for value in (0,123):
   self.setUp();self.populate(65);self.dll.changeFingerprint(value);self.save();self.assertEqual(self.dll.reads(),65)
 def test_one_directory_error_retries_original_scan(self):
  self.populate(65);self.dll.failDirectoryRead(17);self.save();self.assertEqual(self.dll.reads(),65)
 def test_target_banks_are_fresh_after_names_verification(self):
  ids=self.populate(65);data=build_ghost();self.dll.submit(1,0,AUTO,data,len(data),0)
  slot=self.dll.stopAtAutoProbe();self.assertEqual(slot,ids[-1]+1);self.add(PERSONAL+f'g{slot:02}a.sgh',b'broken')
  self.assertGreaterEqual(self.dll.run(1000000),0)
  fields=struct.unpack('<IHHIiIIIHH',C.string_at(self.dll.response(),32));self.assertEqual((fields[4],fields[7]),(0,slot+1))
  self.assertEqual(self.file(PERSONAL+f'g{slot:02}a.sgh'),b'broken')
 def test_failed_publication_invalidates_cached_metadata(self):
  self.populate(65);self.dll.writeFailure(164,0)
  self.assertNotEqual(self.request(1,AUTO,payload=build_ghost())['status'],0)
  rows,total,_,_=self.page(64,cached=True);self.assertGreater(self.dll.reads(),0);self.assertEqual(total,66);self.assertTrue(rows[-1][3]&2)

class SourcePublicationTests(pub.PublicationPinTests):
 @classmethod
 def setUpClass(cls):compile_storage(cls,pub.PublicationPinTests.setUpClass)
 def test_65_row_msgt_save_keeps_checked_source_pin(self):
  ids=list(range(45))+list(range(48,68))
  for slot in ids:self.add(PERSONAL+f'g{slot:02}a.sgh',envelope(build_ghost(),slot=slot))
  source=self.source();self.assertEqual(self.request(4,slot=0)['status'],0);self.assertEqual(self.lib.reads(),65)
  saved=self.request(1,payload=manifest(source));self.assertEqual((saved['status'],saved['slot']),(0,68));self.assertLess(self.lib.reads(),12)
  self.assertIsNotNone(self.file(self.pin(68)));self.assertEqual(self.file(PERSONAL+'g68a.sgh')[64:],manifest(source))
 def test_mutated_source_cannot_use_a_warm_large_catalogue(self):
  ids=list(range(45))+list(range(48,68))
  for slot in ids:self.add(PERSONAL+f'g{slot:02}a.sgh',envelope(build_ghost(),slot=slot))
  source=self.source();self.assertEqual(self.request(4,slot=0)['status'],0)
  corrupt=bytearray(source);corrupt[-16]^=1;self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',bytes(corrupt))
  self.assertNotEqual(self.request(1,payload=manifest(source))['status'],0);self.assertIsNone(self.file(self.pin(68)));self.assertIsNone(self.file(PERSONAL+'g68a.sgh'))
if __name__=='__main__':unittest.main()
