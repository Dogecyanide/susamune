"""Isolated staged PR59 recording ownership and actual ARM journal tests."""
import ctypes as C
import os
from pathlib import Path
import re,struct,subprocess,sys,tempfile,unittest,zlib
ROOT=Path(__file__).resolve().parents[1]
PROPOSED=ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from test_ghost_kernel_paging import EXPORTS
from test_ghost_trace_storage import ADAPTER,writer_source
from test_ghost_trace_reader import capture,record,fnv
from test_ghost_format import build_ghost
LIFECYCLE=r'''
#include "susamune/ghost_recording_lifecycle.hxx"
using namespace GhostRecordingLifecycle;
State state;
#include <cstring>
#include "susamune/ghost_storage.h"
using u32=unsigned;using u16=unsigned short;using u8=unsigned char;using s32=int;
#include "susamune/ghost_catalog_validation.inc"
#define API extern "C" __declspec(dllexport)
API int catalog(const SusamuneGhostSlotInfo*p){SusamuneGhostSlotInfo out;return validateCatalogSlot(*p,&out,false,0x474d534a,0);}
API void init(unsigned caps){GhostRecordingLifecycle::init(state,1234,caps);}
API unsigned arm(){auto*d=GhostRecordingLifecycle::arm(state);return d?d->token:0;}
API unsigned run(unsigned token){auto*d=find(state,token);return d?d->identity.run:0;}
API int captured(unsigned run){return GhostRecordingLifecycle::captured(state,{1234,run});}
API int finish(unsigned owner){return GhostRecordingLifecycle::finish(state,owner);}
API int done(unsigned run){Completion c={{1234,run},4096,1,20,0xfffff,23,45};return completed(state,c);}
API unsigned phase(unsigned token){auto*d=find(state,token);return d?d->phase:99;}
API int protect(unsigned owner,unsigned pb){return GhostRecordingLifecycle::protect(state,owner,pb);}
API unsigned selection(){auto*d=GhostRecordingLifecycle::selection(state);return d?token(*d):0;}
API int save(unsigned token,unsigned seq){return beginSave(state,token,seq);}
API int ack(unsigned seq,int ok){return saveResult(state,seq,ok!=0);}
API int drop(unsigned token){return beginDiscard(state,token);}
API int dropped(unsigned run){return discarded(state,{1234,run});}
API int checkpoint(unsigned token,unsigned generation,int release){auto*d=find(state,token);if(!d)return 0;Checkpoint c={d->identity,generation,20,80,1,64,123};return release?releaseCheckpoint(state,c):retainCheckpoint(state,c);}
'''
def trace(run=0x80000001):
 data=bytearray(capture([record(1,0,bytes(32),2)+record(2,4,bytes(32),2)],game=0x474d534a))
 struct.pack_into('>II',data,16,1234,run);struct.pack_into('>I',data,28,0xfffff);struct.pack_into('>I',data,60,fnv(data[:60]))
 struct.pack_into('>I',data,64,run);struct.pack_into('>I',data,len(data)-28,run);struct.pack_into('>I',data,len(data)-16,0xfffff)
 return bytes(data)
def manifest(source,run=0x80000001):
 p=bytearray(256);struct.pack_into('>IHHI',p,0,0x4d53474d,1,256,256)
 fields={16:1234,20:run,24:0xfffff,32:0x474d534a,52:104,56:100,60:104,64:4,68:2,84:1234,88:run,224:len(source),228:1,232:struct.unpack_from('>I',source,60)[0],236:fnv(source[-32:]),240:0x40000001}
 for at,value in fields.items():struct.pack_into('>I',p,at,value)
 p[37:42]=bytes([0,0,3,2,0]);struct.pack_into('>H',p,42,4);p[44:48]=bytes([2,0,255,0]);p[93]=8;p[95]=1;p[120:128]=b'Bianco 1'
 struct.pack_into('>I',p,12,zlib.crc32(p));return bytes(p)
class RecordingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-recording-');cls.addClassCleanup(cls.temp.cleanup);out=Path(cls.temp.name)
  fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text(encoding='utf-8').replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 256').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 32').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 8192')
  fixture=fixture.replace('f_close(','fixture_close(').replace('f_rename_char(','fixture_rename(')
  source=(PROPOSED/'launcher/kernel/SusamuneGhost.c').read_text(encoding='utf-8').replace('#include "GhostCanonical.inc"',(PROPOSED/'launcher/kernel/GhostCanonical.inc').read_text(encoding='utf-8'))
  source=re.sub(r'^#include .*$', '',source,flags=re.M).replace('#define RECORDING_PIN ((struct RecordingPinTransaction*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_LIBRARY_PIN_OFFSET))','static struct RecordingPinTransaction recordingPin;\n#define RECORDING_PIN (&recordingPin)')
  exports=EXPORTS.replace('SusamuneGhostInit();','SusamuneGhostInit();testAdmit=1;testProof.word[MGM_NONCE]=0x12345678;GhostTraceStorageInit();memset(&recordingPin,0,sizeof(recordingPin));')
  (out/'kernel.c').write_text('#define MOONSHINE_GHOST_TRACE 1\n'+fixture+ADAPTER+'\n#include "susamune/ghost_recording_manifest.h"\n'+writer_source(PROPOSED)+source+exports,encoding='utf-8')
  args=['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-static','-fno-builtin','-DMOONSHINE_GHOST_TRACE=1','-I',str(PROPOSED/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),'-I',str(ROOT/'scripts'),str(out/'kernel.c'),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(out/'kernel.dll')]
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',env=env)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(out/'kernel.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.add.argtypes=[C.c_char_p,C.c_void_p,C.c_uint];cls.lib.submit.argtypes=[C.c_uint]*3+[C.c_void_p]+[C.c_uint]*2
  cls.lib.response.restype=cls.lib.payload.restype=C.c_void_p;cls.lib.fileBytes.argtypes=[C.c_char_p,C.POINTER(C.c_uint)];cls.lib.fileBytes.restype=C.c_void_p
  (out/'lifecycle.cpp').write_text(LIFECYCLE,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++11','-O2','-I',str(PROPOSED/'include'),'-I',str(ROOT/'include'),str(out/'lifecycle.cpp'),'-o',str(out/'lifecycle.dll')],env=env,capture_output=True,text=True,encoding='utf-8')
  if result.returncode:raise RuntimeError(result.stderr)
  cls.flow=C.CDLL(str(out/'lifecycle.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.flow._handle)))
  for name in ('arm','run','selection'):getattr(cls.flow,name).restype=C.c_uint
  cls.flow.catalog.argtypes=[C.c_void_p]
 def setUp(self):self.lib.reset();self.flow.init(15);self.keep=[]
 def add(self,path,data):
  buf=C.create_string_buffer(data);self.keep.append(buf);self.assertGreaterEqual(self.lib.add(path.encode(),buf,len(data)),0)
 def request(self,op,slot=0xffffffff,payload=b'',generation=0):
  self.lib.submit(op,0,slot,payload,len(payload),generation);self.assertGreaterEqual(self.lib.run(5000),0);raw=C.string_at(self.lib.response(),32)
  return {'status':struct.unpack_from('<i',raw,12)[0],'bytes':struct.unpack_from('<I',raw,16)[0],'generation':struct.unpack_from('<I',raw,20)[0],'slot':struct.unpack_from('<I',raw,24)[0]}
 def file(self,path):
  count=C.c_uint();p=self.lib.fileBytes(path.encode(),C.byref(count));return C.string_at(p,count.value) if p else None
 def ready(self,owner=1):
  token=self.flow.arm();run=self.flow.run(token);self.assertNotEqual(token,0);self.assertEqual(self.flow.captured(run),1);self.assertEqual(self.flow.finish(owner),1);self.assertEqual(self.flow.done(run),1);return token,run
 def test_stable_save_ack_does_not_touch_new_attempt(self):
  token,run=self.ready(10);self.assertEqual(self.flow.protect(10,77),1);self.assertEqual(self.flow.selection(),77);self.assertEqual(self.flow.save(77,123),1)
  second=self.flow.arm();self.assertNotEqual(second,token);self.assertEqual(self.flow.ack(124,1),0);self.assertEqual(self.flow.phase(77),5)
  self.assertEqual(self.flow.ack(123,1),1);self.assertEqual(self.flow.phase(token),6);self.assertEqual(self.flow.phase(second),1);self.assertEqual(self.flow.ack(123,1),0)
 def test_save_failure_keeps_pb_and_pending_io_blocks_discard(self):
  token,run=self.ready(10);self.flow.protect(10,77);self.assertEqual(self.flow.save(77,123),1);self.assertEqual(self.flow.drop(77),0);self.assertEqual(self.flow.ack(123,0),1);self.assertEqual(self.flow.selection(),77)
 def test_capacity_never_evicts_unsaved_drafts(self):
  tokens=[self.ready(i+1)[0] for i in range(3)];self.assertEqual(self.flow.arm(),0);self.assertEqual([self.flow.phase(x) for x in tokens],[4,4,4])
  run=self.flow.run(tokens[1]);self.assertEqual(self.flow.drop(tokens[1]),1);self.assertEqual(self.flow.dropped(run+1),0);self.assertEqual(self.flow.dropped(run),1);self.assertNotEqual(self.flow.arm(),0)
 def test_checkpoint_identity_and_retention(self):
  token,run=self.ready();self.assertEqual(self.flow.checkpoint(token,token+1,0),0);self.assertEqual(self.flow.checkpoint(token,token,0),1);self.assertEqual(self.flow.drop(token),0)
  self.assertEqual(self.flow.checkpoint(token,token,1),1);self.assertEqual(self.flow.drop(token),1);self.assertEqual(self.flow.dropped(run),1)
 def test_without_continuation_capability_disabled(self):
  for caps in (0,1,3,7,14):self.flow.init(caps);self.assertEqual(self.flow.arm(),0)
 def test_save_list_load_descriptor_uses_existing_journal(self):
  source=trace();data=manifest(source);self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source);saved=self.request(1,payload=data);self.assertEqual(saved['status'],0)
  envelope=self.file(f'/Moonshine data/ghosts/jp/p0/g{saved["slot"]:02}a.sgh');self.assertEqual(struct.unpack_from('>H',envelope,4)[0],3);self.assertEqual(envelope[64:],data)
  listed=self.request(4,slot=0);self.assertEqual(listed['status'],0);page=C.string_at(self.lib.payload(),listed['bytes']);info=page[36:164]
  self.assertEqual(struct.unpack_from('<H',info,40)[0]&8,8);self.assertEqual(info[54],254);self.assertEqual(self.flow.catalog(info),1)
  loaded=self.request(2,slot=saved['slot'],generation=saved['generation']);self.assertEqual(loaded['status'],0);self.assertEqual(C.string_at(self.lib.payload(),loaded['bytes']),data)
 def test_source_missing_corrupt_or_wrong_identity_never_publishes(self):
  source=trace();data=manifest(source);self.assertNotEqual(self.request(1,payload=data)['status'],0)
  for offset in (0,16,len(source)-32,len(source)-16):
   self.lib.reset();bad=bytearray(source);bad[offset]^=1;self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',bytes(bad));self.assertNotEqual(self.request(1,payload=data)['status'],0)
 def test_save_failure_preserves_other_files(self):
  saved=self.request(1,payload=build_ghost(version=4));self.assertEqual(saved['status'],0);path=f'/Moonshine data/ghosts/jp/p0/g{saved["slot"]:02}a.sgh';before=self.file(path)
  source=trace();self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source);self.lib.writeFailure(64,0)
  self.assertNotEqual(self.request(1,payload=manifest(source))['status'],0);self.assertEqual(self.file(path),before);self.assertEqual(self.file('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt'),source)
 def test_delete_tombstone_retains_shared_source(self):
  source=trace();path='/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt';self.add(path,source);saved=self.request(1,payload=manifest(source));self.assertEqual(saved['status'],0)
  self.assertEqual(self.request(3,slot=saved['slot'],generation=saved['generation'])['status'],0);self.assertEqual(self.file(path),source)
 def test_future_manifest_remains_unsafe_and_cannot_be_reused(self):
  source=trace();data=bytearray(manifest(source));struct.pack_into('>H',data,4,2);struct.pack_into('>I',data,12,0);struct.pack_into('>I',data,12,zlib.crc32(data))
  h=bytearray(64)
  for at,value in {0:0x5347454e,8:1,16:0x474d534a,24:256,28:4,32:zlib.crc32(data)}.items():struct.pack_into('>I',h,at,value)
  struct.pack_into('>HH',h,4,3,64);struct.pack_into('>I',h,36,zlib.crc32(h));envelope=bytes(h+data)
  path='/Moonshine data/ghosts/jp/p0/g00a.sgh';self.add(path,envelope)
  listed=self.request(4,slot=0);self.assertEqual(listed['status'],0);page=C.string_at(self.lib.payload(),listed['bytes'])
  self.assertTrue(struct.unpack_from('<H',page,36+40)[0]&2)
  saved=self.request(1,payload=build_ghost(version=4));self.assertEqual(saved['status'],0);self.assertNotEqual(saved['slot'],0);self.assertEqual(self.file(path),envelope)
 def test_ui_catalog_requires_explicit_streamed_marker(self):
  source=trace();self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source);self.assertEqual(self.request(1,payload=manifest(source))['status'],0)
  listed=self.request(4,slot=0);page=C.string_at(self.lib.payload(),listed['bytes']);info=bytearray(page[36:164]);self.assertEqual(self.flow.catalog(bytes(info)),1)
  for at,value in ((54,10),(48,2),(49,1)):
   altered=bytearray(info);altered[at]=value;self.assertEqual(self.flow.catalog(bytes(altered)),0)
 def test_descriptor_cannot_be_exported_as_smsghost(self):
  source=trace();self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source);saved=self.request(1,payload=manifest(source));self.assertEqual(saved['status'],0)
  self.assertEqual(self.request(5,slot=saved['slot'],generation=saved['generation'])['status'],-5)

 def cached_page(self,offset=0,cached=True):
  self.lib.submit(4,0,offset,b'',0,0);self.lib.requestFlags(int(cached))
  self.assertGreaterEqual(self.lib.run(5000),0)
  response=C.string_at(self.lib.response(),32);self.assertEqual(struct.unpack_from('<i',response,12)[0],0)
  size=struct.unpack_from('<I',response,16)[0];return C.string_at(self.lib.payload(),size)
 def test_committed_save_refresh_reuses_scan_without_directory_io(self):
  source=trace();self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source)
  saved=self.request(1,payload=manifest(source));self.assertEqual(saved['status'],0)
  cached=self.cached_page();self.assertEqual(struct.unpack_from('<I',cached,12)[0],1)
  self.assertEqual(struct.unpack_from('<II',cached,32),(saved['slot'],saved['generation']))
  self.assertEqual((self.lib.reads(),self.lib.opens(),self.lib.directoryReads()),(0,0,0))
  fresh=self.cached_page(cached=False);self.assertGreater(self.lib.directoryReads(),0);self.assertEqual(cached,fresh)
 def test_large_library_save_preserves_checked_page_window(self):
  source=trace();data=manifest(source);self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source)
  first=self.request(1,payload=data);self.assertEqual(first['status'],0)
  original=self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh')
  for slot in list(range(1,45))+list(range(48,130)):
   item=bytearray(original);struct.pack_into('>H',item,22,slot);struct.pack_into('>I',item,40,slot)
   struct.pack_into('>I',item,36,0);struct.pack_into('>I',item,36,zlib.crc32(item[:64]))
   self.add(f'/Moonshine data/ghosts/jp/p0/g{slot:02}a.sgh',bytes(item))
  before=self.cached_page(64,False);total=struct.unpack_from('<I',before,12)[0]
  saved=self.request(1,payload=data);self.assertEqual((saved['status'],saved['slot']),(0,130))
  cached=self.cached_page(64);self.assertEqual(struct.unpack_from('<I',cached,12)[0],total+1)
  self.assertEqual((self.lib.reads(),self.lib.opens(),self.lib.directoryReads()),(0,0,0))
  self.assertEqual(cached,self.cached_page(64,False))
 def test_reused_tombstone_requires_fresh_catalogue_order(self):
  source=trace();data=manifest(source);self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source)
  first=self.request(1,payload=data);self.assertEqual(first['status'],0)
  self.assertEqual(self.request(3,slot=first['slot'],generation=first['generation'])['status'],0)
  saved=self.request(1,payload=data);self.assertEqual(saved['status'],0);self.assertEqual(saved['slot'],first['slot'])
  page=self.cached_page();self.assertGreater(self.lib.directoryReads(),0)
  self.assertEqual(struct.unpack_from('<II',page,32),(saved['slot'],saved['generation']))
 def test_failed_save_does_not_publish_a_new_catalogue_cache(self):
  source=trace();data=manifest(source);self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',source)
  self.assertEqual(self.request(1,payload=data)['status'],0);original=self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh')
  self.lib.writeFailure(64,0);self.assertNotEqual(self.request(1,payload=data)['status'],0)
  self.cached_page();self.assertGreater(self.lib.directoryReads(),0)
  self.assertEqual(self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh'),original)

if __name__=='__main__':unittest.main()
