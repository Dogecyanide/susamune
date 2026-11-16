"""Lossless changed-word records against real captured bytes and corrupt masks."""
import ctypes as C,importlib.util,os,random,struct,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DeltaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='trace-delta-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  (folder/'test.c').write_text('#include "susamune/ghost_trace_codec.h"\n__declspec(dllexport) unsigned encode(unsigned char*d,const unsigned char*a,const unsigned char*b,unsigned n){return MsTraceWordDelta(d,a,b,n);}',encoding='utf-8')
  subprocess.run([str(ROOT/'toolchain/clang.exe'),'--target=x86_64-pc-windows-msvc','-O2','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-I',str(ROOT/'include'),str(folder/'test.c'),'-o',str(folder/'test.dll')],check=True,capture_output=True)
  cls.lib=C.CDLL(str(folder/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.encode.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint]
  spec=importlib.util.spec_from_file_location('trace_reader',ROOT/'tools/ghost_trace/inspect_trace.py');cls.reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.reader)
 def roundtrip(self,a,b):
  n=len(a);out=C.create_string_buffer(b'Z'*560);size=self.lib.encode(C.byref(out,16),a,b,n);self.assertEqual(out.raw[:16],b'Z'*16);self.assertEqual(out.raw[16+n:],b'Z'*(560-16-n)+b'\0')
  states={};literal=struct.pack('>4I',0x80010000,0,n,n)+a;self.reader.apply_blob(literal,2,states,3)
  record=struct.pack('>4I',0x80010000,0,n,n|(0x80000000 if size else 0))+(out.raw[16:16+size] if size else b)
  self.reader.apply_blob(record,2,states,3);self.assertEqual(bytes(states[3][1]),b);return size
 def test_changed_words_roundtrip_and_output_bounds(self):
  rng=random.Random(428)
  for n in (4,12,128,256,300,372,512):
   a=rng.randbytes(n)
   for changes in (0,1,n//8,n//4):
    b=bytearray(a)
    for _ in range(changes):i=rng.randrange(n//4)*4;b[i:i+4]=rng.randbytes(4)
    self.roundtrip(a,bytes(b))
 def test_literal_fallback_and_nan_bits(self):
  self.assertEqual(self.roundtrip(bytes(512),bytes([255])*512),0)
  a=bytes(512);b=struct.pack('>4I',0x7fc01234,0xff800000,0x80000000,0x7fffffff)+a[16:]
  self.assertLess(self.roundtrip(a,b),512)
 def test_rejects_delta_without_baseline_and_excess_bits(self):
  with self.assertRaisesRegex(ValueError,'baseline'):self.reader.apply_blob(struct.pack('>5I',0x80010000,0,4,0x80000004,1)+bytes(4),2,{},3)
  states={};self.reader.apply_blob(struct.pack('>4I',0x80010000,0,4,4)+bytes(4),2,states,3)
  with self.assertRaisesRegex(ValueError,'mask exceeds'):self.reader.apply_blob(struct.pack('>5I',0x80010000,0,4,0x80000004,2)+bytes(4),2,states,3)
 def test_existing_wii_v1_files_remain_readable(self):
  captures=ROOT/'build/pr48-sd-trace/wii-captures'
  for p in captures.glob('*.msgt'):
   with self.subTest(file=p.name):self.assertTrue(self.reader.inspect(p)['complete'])
if __name__=='__main__':unittest.main()
