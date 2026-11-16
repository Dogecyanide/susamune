"""Checked negative reference summaries must never weaken source retention."""
import ctypes as C,struct,unittest
from unittest.mock import patch
from pathlib import Path
import test_ghost_trace_publication as publication
from test_ghost_recording import trace,manifest
from test_ghost_trace_reader import fnv
EXTRA=r"""
__declspec(dllexport) void background(unsigned count){while(count--&&GhostTraceBackgroundPending())GhostTraceBackgroundService();}
__declspec(dllexport) unsigned cacheReady(void){return WRITER->references.valid;}
__declspec(dllexport) unsigned cacheFailed(void){return WRITER->references.failed;}
__declspec(dllexport) unsigned cacheAbsent(unsigned nonce,unsigned run){return referenceCacheUnreferenced(nonce,run);}
__declspec(dllexport) unsigned fileOpens(void){return openCalls;}
__declspec(dllexport) void damageCache(void){WRITER->references.bits[0]^=1;}
__declspec(dllexport) void forbidCreates(void){writeCount=FIXTURE_WRITES;}
__declspec(dllexport) unsigned cachePending(void){return referenceCachePending();}
__declspec(dllexport) void discIdle(void){DI_IRQ=pendingDisc=0;DILastReadTick=clockTick-1898437u;}
__declspec(dllexport) void recentDisc(void){DI_IRQ=0;DILastReadTick=clockTick;}
__declspec(dllexport) void queuedDisc(void){pendingDisc=1;}

"""
class ReferenceCacheTests(publication.PublicationPinTests):
 @classmethod
 def setUpClass(cls):
  original_extra=publication.EXTRA;publication.EXTRA+=EXTRA
  read=Path.read_text
  def larger(path,*args,**kwargs):
   text=read(path,*args,**kwargs)
   if path.name=='ghost_kernel_fixture.h':text=text.replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 2048')
   return text
  try:
   with patch.object(Path,'read_text',larger):super().setUpClass()
  finally:publication.EXTRA=original_extra
 def setUp(self):super().setUp();self.lib.discIdle()
 def delete(self,source):
  hash=struct.unpack_from('>I',source,60)[0];result=self.lib.discardSource(1,hash)
  for _ in range(2100):
   if result:return result
   result=self.lib.discardSource(0,hash)
  self.fail('discard did not finish')
 def test_valid_negative_summary_avoids_the_directory_scan(self):
  source=self.source();self.lib.background(100)
  self.assertEqual(self.lib.cacheReady(),1);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),1)
  before=self.lib.directoryReads();self.assertEqual(self.delete(source),1)
  self.assertEqual(self.lib.directoryReads(),before);self.assertIsNone(self.file('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt'))
 def test_actual_saved_library_pin_remains_protected(self):
  source=self.source();self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  self.lib.background(100);self.assertEqual(self.lib.cacheReady(),1)
  self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0);self.assertEqual(self.delete(source),-1)
  self.assertEqual(self.file('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt'),source)
 def test_new_reference_invalidates_a_previously_negative_summary(self):
  source=self.source();self.lib.background(100);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),1)
  self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0);self.assertEqual(self.delete(source),-1)
 def test_corrupt_reference_or_corrupt_summary_never_proves_absence(self):
  source=self.source();self.add('/Moonshine data/ghosts/recordings/broken.msgb',bytes(128));self.lib.background(100)
  self.assertEqual(self.lib.cacheFailed(),1);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0)
  self.assertEqual(self.delete(source),-1)
  self.setUp();source=self.source();self.lib.background(100);self.lib.damageCache()
  self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0)
  before=self.lib.directoryReads();self.assertEqual(self.delete(source),1);self.assertGreater(self.lib.directoryReads(),before)
 def test_more_than_a_thousand_reference_edges_have_no_false_negatives(self):
  source=self.source();self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  template=self.file(self.pin(0));self.assertEqual(len(template),128)
  for i in range(1100):
   data=bytearray(template);struct.pack_into('>II',data,32,5678,0x80000100+i)
   struct.pack_into('>I',data,124,fnv(data[:124]))
   self.add(f'/Moonshine data/ghosts/recordings/test_{i:04}.msgb',bytes(data))
  self.lib.background(2000);self.assertEqual(self.lib.cacheReady(),1)
  for i in range(1100):self.assertEqual(self.lib.cacheAbsent(5678,0x80000100+i),0)
 def test_failed_reference_creation_invalidates_before_filesystem_mutation(self):
  source=self.source();self.lib.background(100);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),1)
  self.lib.forbidCreates();self.assertNotEqual(self.request(1,payload=manifest(source))['status'],0)
  self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0)
  self.lib.background(100);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),1)
 def test_successful_publication_extends_cache_without_background_io(self):
  source=self.source();self.lib.background(100);self.assertEqual(self.lib.cachePending(),0)
  self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  self.assertEqual(self.lib.cachePending(),0);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0)
  before=(self.lib.directoryReads(),self.lib.fileOpens());self.lib.background(100)
  self.assertEqual((self.lib.directoryReads(),self.lib.fileOpens()),before)
  self.assertEqual(self.delete(source),-1)
 def test_successful_release_keeps_a_conservative_summary(self):
  source=self.source();saved=self.request(1,payload=manifest(source));self.lib.background(100)
  self.assertEqual(self.request(3,slot=saved['slot'],generation=saved['generation'])['status'],0)
  self.assertEqual(self.lib.cachePending(),0);self.assertEqual(self.lib.cacheAbsent(1234,0x80000001),0)
  self.assertEqual(self.delete(source),1)
 def test_corrupt_cache_is_not_blessed_by_a_successful_publication(self):
  source=self.source();self.lib.background(100);self.lib.damageCache()
  self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  self.assertEqual(self.lib.cachePending(),1);self.assertEqual(self.lib.cacheAbsent(4321,0x80000022),0)
 def test_background_scan_waits_for_recent_or_just_posted_disc_reads(self):
  self.source();before=(self.lib.directoryReads(),self.lib.fileOpens())
  self.lib.recentDisc();self.lib.background(20);self.assertEqual((self.lib.directoryReads(),self.lib.fileOpens()),before)
  self.lib.discIdle();self.lib.queuedDisc();self.lib.background(20);self.assertEqual((self.lib.directoryReads(),self.lib.fileOpens()),before)
  self.lib.discIdle();self.lib.background(100);self.assertEqual(self.lib.cachePending(),0)
 def test_wrong_source_hash_is_rejected_even_with_a_valid_negative_summary(self):
  source=self.source();self.lib.background(100)
  hash=struct.unpack_from('>I',source,60)[0];self.assertEqual(self.lib.discardSource(1,hash^1),-1)
  self.assertEqual(self.file('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt'),source)
if __name__=='__main__':unittest.main()
