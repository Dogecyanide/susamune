"""Actual library journal and trace-pin backend share the same fault-injected filesystem."""
import ctypes as C,os,re,struct,subprocess,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from test_ghost_kernel_paging import EXPORTS
from test_ghost_trace_storage import ADAPTER
from ghost_trace_publication_fixture import writer_source
from test_ghost_recording import trace,manifest
from test_ghost_format import build_ghost
EXTRA=r'''
__declspec(dllexport) void initAll(void){reset();testAdmit=1;clockTick=closeFailure=renameFailure=0;testProof.word[MGM_NONCE]=0x12345678;GhostTraceStorageInit();memset(&recordingPin,0,sizeof(recordingPin));}
__declspec(dllexport) void step(void){SusamuneGhostService();}
__declspec(dllexport) int pinned(void){return Phase==OP_SAVE_OPEN&&recordingPin.sequence==Request.seq;}
__declspec(dllexport) void changePayload(unsigned value){memset(testPayload,value,256);}
__declspec(dllexport) int discardSource(unsigned begin,unsigned hash){return GhostTraceRetainedDiscard(1234,0x80000001u,hash,begin);}
'''
class PublicationPinTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='pr59-library-pins-');cls.addClassCleanup(cls.temp.cleanup);out=Path(cls.temp.name)
  fixture=(ROOT/'scripts/ghost_kernel_fixture.h').read_text().replace('#define FIXTURE_FILES 60000','#define FIXTURE_FILES 100').replace('#define FIXTURE_WRITES 80','#define FIXTURE_WRITES 32').replace('#define FIXTURE_FILE_BYTES 1400000','#define FIXTURE_FILE_BYTES 8192').replace('f_close(','fixture_close(').replace('f_rename_char(','fixture_rename(')
  source=(P/'launcher/kernel/SusamuneGhost.c').read_text().replace('#include "GhostCanonical.inc"',(ROOT/'launcher/kernel/GhostCanonical.inc').read_text());source=re.sub(r'^#include .*$', '',source,flags=re.M)
  source=source.replace('#define RECORDING_PIN ((struct RecordingPinTransaction*)(MS_TRACE_CONTROL_PHYS+MS_TRACE_LIBRARY_PIN_OFFSET))','static struct RecordingPinTransaction recordingPin;\n#define RECORDING_PIN (&recordingPin)')
  code='#define MOONSHINE_GHOST_TRACE 1\n'+fixture+ADAPTER+'\n#include "susamune/ghost_recording_manifest.h"\n'+writer_source(P)+source+EXPORTS+EXTRA
  (out/'kernel.c').write_text(code);env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  args=['C:/msys64/mingw64/bin/gcc.exe','-shared','-O2','-std=gnu99','-static','-fno-builtin','-DMOONSHINE_GHOST_TRACE=1','-DMS_TRACE_BRANCH_RETENTION_READY=1','-I',str(P/'include'),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/susamune'),'-I',str(ROOT/'scripts'),str(out/'kernel.c'),str(ROOT/'launcher/kernel/GhostTraceCompression.c'),'-o',str(out/'kernel.dll')]
  r=subprocess.run(args,capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(out/'kernel.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.add.argtypes=[C.c_char_p,C.c_void_p,C.c_uint];cls.lib.submit.argtypes=[C.c_uint]*3+[C.c_void_p]+[C.c_uint]*2
  cls.lib.response.restype=cls.lib.payload.restype=C.c_void_p;cls.lib.fileBytes.argtypes=[C.c_char_p,C.POINTER(C.c_uint)];cls.lib.fileBytes.restype=C.c_void_p
 def setUp(self):self.lib.initAll();self.keep=[]
 def add(self,path,data):
  owner=C.create_string_buffer(data);self.keep.append(owner);self.assertGreaterEqual(self.lib.add(path.encode(),owner,len(data)),0)
 def file(self,path):
  size=C.c_uint();p=self.lib.fileBytes(path.encode(),C.byref(size));return C.string_at(p,size.value) if p else None
 def request(self,op,slot=0xffffffff,payload=b'',generation=0):
  self.lib.submit(op,0,slot,payload,len(payload),generation);self.assertGreaterEqual(self.lib.run(5000),0);raw=C.string_at(self.lib.response(),32)
  return dict(status=struct.unpack_from('<i',raw,12)[0],generation=struct.unpack_from('<I',raw,20)[0],slot=struct.unpack_from('<I',raw,24)[0])
 def pin(self,slot,generation=1):return f'/Moonshine data/ghosts/recordings/ref_000004D2_80000001_4C420100_{slot+1:08X}_{generation:08X}.msgb'
 def source(self):
  data=trace();self.add('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt',data);return data
 def test_pin_is_durable_before_library_envelope_publication(self):
  source=self.source();data=manifest(source);self.lib.submit(1,0,0xffffffff,data,len(data),0)
  for _ in range(1000):
   self.lib.step()
   if self.lib.pinned():break
  self.assertTrue(self.lib.pinned());self.assertIsNotNone(self.file(self.pin(0)));self.assertIsNone(self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh'))
  self.assertGreaterEqual(self.lib.run(5000),0);self.assertEqual(self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh')[64:],data)
 def test_late_ppc_payload_change_cannot_change_pinned_descriptor(self):
  source=self.source();data=manifest(source);self.lib.submit(1,0,0xffffffff,data,len(data),0)
  for _ in range(1000):
   self.lib.step()
   if self.lib.pinned():break
  self.lib.changePayload(0x77);self.assertGreaterEqual(self.lib.run(5000),0)
  self.assertEqual(self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh')[64:],data)
 def test_each_library_reference_has_an_exact_independent_pin(self):
  source=self.source();a=self.request(1,payload=manifest(source));b=self.request(1,payload=manifest(source));self.assertEqual(a['status'],0);self.assertEqual(b['status'],0)
  self.assertEqual(self.request(3,slot=a['slot'],generation=a['generation'])['status'],0)
  self.assertIsNone(self.file(self.pin(a['slot'])));self.assertIsNotNone(self.file(self.pin(b['slot'])))
  self.assertEqual(self.request(3,slot=b['slot'],generation=b['generation'])['status'],0);self.assertIsNone(self.file(self.pin(b['slot'])))
 def test_failed_tombstone_keeps_source_pin(self):
  source=self.source();saved=self.request(1,payload=manifest(source));self.lib.writeFailure(0,0)
  self.assertNotEqual(self.request(3,slot=saved['slot'],generation=saved['generation'])['status'],0);self.assertIsNotNone(self.file(self.pin(saved['slot'])))
 def test_pin_write_failure_never_publishes_library_entry(self):
  source=self.source();self.lib.writeFailure(0,0);self.assertNotEqual(self.request(1,payload=manifest(source))['status'],0)
  self.assertIsNone(self.file('/Moonshine data/ghosts/jp/p0/g00a.sgh'));self.assertEqual(self.file('/Moonshine data/ghosts/recordings/trace_000004D2_80000001.msgt'),source)
 def test_streamed_duration_has_no_legacy_quarter_frame_cap(self):
  source=self.source();data=bytearray(manifest(source));end=1000000
  for offset,value in ((52,end),(60,end),(64,end-100)):struct.pack_into('>I',data,offset,value)
  struct.pack_into('>I',data,12,0);struct.pack_into('>I',data,12,zlib.crc32(data));saved=self.request(1,payload=bytes(data));self.assertEqual(saved['status'],0)
  self.assertEqual(self.request(2,slot=saved['slot'],generation=saved['generation'])['status'],0)
 def test_legacy_save_delete_does_not_touch_streamed_pin(self):
  source=self.source();saved=self.request(1,payload=manifest(source));legacy=self.request(1,payload=build_ghost(version=4));self.assertEqual(legacy['status'],0)
  self.assertEqual(self.request(3,slot=legacy['slot'],generation=legacy['generation'])['status'],0);self.assertIsNotNone(self.file(self.pin(saved['slot'])))
if __name__=='__main__':unittest.main()
