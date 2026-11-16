"""Exercise the bounded production reader, including actual Wii capture files."""
import ctypes as C
import os,struct,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
B=0x80000

def fnv(data):
 h=2166136261
 for b in data:h=((h^b)*16777619)&0xffffffff
 return h

def record(frame=1,tick=1,body=b"",kind=99):
 return struct.pack(">HHII",kind,len(body),frame,tick)+body

def capture(chunks,version=3,game=0x474d5350,error=0,compressed=None):
 h=struct.pack(">15I",0x4d535452,version,64,game,17,23,0xd00,0xffff,B,0,0,0,0,0,0)
 out=bytearray(h+struct.pack(">I",fnv(h)))
 for seq,data in enumerate(chunks,1):
  at=0;frames=[]
  while at<len(data):
   _,n,f,t=struct.unpack_from(">HHII",data,at);frames.append(f);at+=12+n
  out+=struct.pack(">8I",23,seq,len(data),fnv(data),frames[0],frames[-1],1 if compressed else 0,0x4000 if compressed else 0)
  if compressed:
   for i in range(0,len(data),0x4000):
    block=data[i:i+0x4000];packed=compressed(block)
    if len(packed)<len(block):out+=struct.pack(">II",len(block),len(packed)|0x80000000)+packed
    else:out+=struct.pack(">II",len(block),len(block))+block
  else:out+=data
 out+=struct.pack(">8I",0x444f4e45,23,len(chunks),len(out),0xffff|(error<<24),0,0,0)
 return bytes(out)

FIXTURE=r"""
#include "susamune/ghost_trace_reader.hxx"
#include "src/state_codec.cpp"
using namespace GhostTraceReader;
static Reader reader;
static unsigned char output[0x80000+64],packed[0x4000+64];
static Read pending;
#define API extern "C" __declspec(dllexport)
API int start(unsigned bytes){memset(output,0xa5,sizeof(output));memset(packed,0xb6,sizeof(packed));return begin(reader,bytes,output+32,0x80000,packed+32,0x4000);}
API int state(){return status(reader);}
API int error(){return reader.error;}
API int next(){return nextRead(reader,pending);}
API unsigned offset(){return pending.offset;}
API unsigned size(){return pending.bytes;}
API void* target(){return pending.destination;}
API int accept(unsigned bytes){return acceptRead(reader,bytes);}
API int release(){return releaseChunk(reader);}
API unsigned chunkSize(){return reader.chunkBytes;}
API void* chunk(){return reader.output;}
API unsigned chunks(){return reader.chunks;}
API unsigned frames(){return reader.frame;}
API unsigned ticks(){return reader.tick;}
API int region(unsigned game){return sameRegion(reader,game);}
API unsigned workspace(){return sizeof(reader)+0x84000;}
API int aliases(){return begin(reader,96,&reader,0x80000,packed+32,0x4000);}
API int guards(){for(unsigned i=0;i<32;++i)if(output[i]!=0xa5||output[32+0x80000+i]!=0xa5||packed[i]!=0xb6||packed[32+0x4000+i]!=0xb6)return 0;return 1;}
API int pack(const char*data,unsigned bytes,char*out,unsigned cap){return LZ4_compress_default(data,out,bytes,cap);}
"""
class ReaderTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix="moonshine-trace-reader-");cls.addClassCleanup(cls.temp.cleanup)
  d=Path(cls.temp.name);(d/'fixture.cpp').write_text(FIXTURE,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++11','-O2','-shared','-static','-I',str(ROOT/'include'),'-I',str(ROOT),str(d/'fixture.cpp'),str(ROOT/'src/ghost_trace_reader.cpp'),'-o',str(d/'reader.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr[:3500])
  cls.lib=C.CDLL(str(d/'reader.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.target.restype=cls.lib.chunk.restype=C.c_void_p
  cls.lib.pack.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
 def pack(self,data):
  out=C.create_string_buffer(len(data)+len(data)//255+32);n=self.lib.pack(data,len(data),out,len(out));self.assertGreater(n,0);return out.raw[:n]
 def feed(self,data,expected=None):
  import io
  return self.read(io.BytesIO(data),len(data),expected)
 def read(self,stream,size,expected=None):
  self.assertEqual(self.lib.start(size),1);actual=[];index=0
  while self.lib.state()==0:
   if not self.lib.next():break
   stream.seek(self.lib.offset());data=stream.read(self.lib.size())
   C.memmove(self.lib.target(),data,len(data))
   if not self.lib.accept(len(data)):break
   if self.lib.state()==1:
    if expected is not None:self.assertEqual(C.string_at(self.lib.chunk(),self.lib.chunkSize()),expected[index])
    actual.append(self.lib.chunkSize());index+=1;self.assertEqual(self.lib.release(),1)
  self.assertEqual(self.lib.guards(),1)
  return self.lib.state(),actual
 def test_raw_versions_and_multiple_chunks(self):
  chunks=[record(1,2,b'first'),record(5,9,b'second')]
  for version in (1,2,3):
   with self.subTest(version=version):self.assertEqual(self.feed(capture(chunks,version),chunks),(2,[len(c) for c in chunks]))
 def test_compressed_blocks_with_record_crossing_block_boundary(self):
  chunks=[b''.join(record(i+1,i+1,b'unchanged world'*32) for i in range(170))]
  data=capture(chunks,compressed=self.pack);self.assertLess(len(data),len(chunks[0]))
  self.assertEqual(self.feed(data,chunks)[0],2)
 def test_random_raw_fallback_and_empty_complete_capture(self):
  chunks=[record(1,1,bytes((i*73+i//251)%256 for i in range(60000)))]
  self.assertEqual(self.feed(capture(chunks,compressed=lambda x:x),chunks)[0],2)
  self.assertEqual(self.feed(capture([])),(2,[]))
 def test_corruption_never_exposes_a_chunk(self):
  data=bytearray(capture([record(1,1,b'payload')]))
  data[108]^=1
  self.assertEqual(self.feed(data),(3,[]));self.assertEqual(self.lib.error(),6)
 def test_bad_headers_bounds_sequence_and_footer(self):
  base=capture([record(1,1,b'payload')])
  for off,value in ((0,0),(4,99),(60,0),(68,3),(72,B+1),(88,7),(92,16),(len(base)-20,0)):
   with self.subTest(offset=off):
    data=bytearray(base);struct.pack_into('>I',data,off,value);self.assertEqual(self.feed(data)[0],3)
 def test_bad_record_size_and_order(self):
  for chunks in ([record(2,2),record(1,3)],[record(2,2),record(3,1)]):self.assertEqual(self.feed(capture(chunks))[0],3)
  data=bytearray(capture([record(1,1,b'x')]))
  struct.pack_into('>H',data,98,65535);struct.pack_into('>I',data,76,fnv(data[96:-32]))
  self.assertEqual(self.feed(data),(3,[]))
 def test_bad_compression_boundaries(self):
  base=capture([record(1,1,b'X'*2000)],compressed=self.pack)
  for raw,stored in ((0,1),(0x4001,2),(2013,2),(2012,0),(2012,0x800007dc),(2012,3)):
   data=bytearray(base);struct.pack_into('>II',data,96,raw,stored)
   self.assertEqual(self.feed(data),(3,[]))
 def test_short_reads_trailing_bytes_and_failed_capture(self):
  base=capture([record(1,1,b'payload')])
  self.assertEqual(self.feed(base[:-1])[0],3)
  self.assertEqual(self.feed(base+b'x')[0],3)
  self.assertEqual(self.feed(capture([record()],error=4)),(3,[]));self.assertEqual(self.lib.error(),8)
 def test_region_identity_is_independent_of_decoder_version(self):
  self.assertEqual(self.feed(capture([record()],game=0x474d534a))[0],2)
  self.assertEqual(self.lib.region(0x474d534a),1)
  self.assertEqual(self.lib.region(0x474d5350),0)
  self.assertEqual(self.lib.region(0x474d5345),0)
 def test_aliased_scratch_is_rejected(self):
  self.assertEqual(self.lib.aliases(),0);self.assertEqual(self.lib.error(),1)
 def test_pending_read_cannot_be_issued_twice(self):
  data=capture([record()]);self.assertEqual(self.lib.start(len(data)),1)
  self.assertEqual(self.lib.next(),1);offset,size,target=self.lib.offset(),self.lib.size(),self.lib.target()
  self.assertEqual(self.lib.next(),0);self.assertEqual(self.lib.state(),0)
  self.assertEqual((self.lib.offset(),self.lib.size(),self.lib.target()),(offset,size,target))
  C.memmove(target,data[offset:offset+size],size);self.assertEqual(self.lib.accept(size),1)
 def test_chunk_read_cannot_consume_completion_footer(self):
  data=bytearray(capture([record()]))
  struct.pack_into('>I',data,72,44)
  self.assertEqual(self.lib.start(len(data)),1)
  for expected_offset in (0,len(data)-32,64):
   self.assertEqual(self.lib.next(),1);self.assertEqual(self.lib.offset(),expected_offset)
   part=data[expected_offset:expected_offset+self.lib.size()]
   C.memmove(self.lib.target(),bytes(part),len(part));self.assertEqual(self.lib.accept(len(part)),1)
  self.assertEqual(self.lib.next(),0);self.assertEqual(self.lib.error(),2)
  self.assertEqual(self.lib.guards(),1)
 def test_reserved_capability_high_bits_rejected_and_unknown_optional_allowed(self):
  for caps,expected in ((0x80ffff,2),(0x100ffff,3)):
   data=bytearray(capture([record()]));struct.pack_into('>I',data,28,caps)
   struct.pack_into('>I',data,60,fnv(data[:60]));struct.pack_into('>I',data,len(data)-16,caps&0xffffff)
   self.assertEqual(self.feed(data)[0],expected)
 def test_real_wii_captures(self):
  files=sorted((ROOT/'build/pr48-sd-trace/wii-r9-captures').glob('*.msgt'))
  if not files:self.skipTest('Private Wii captures unavailable')
  for p in files:
   with self.subTest(capture=p.name),p.open('rb') as f:
    state,chunks=self.read(f,p.stat().st_size)
    self.assertEqual(state,2,f'{p.name}: reader error {self.lib.error()}')
    self.assertGreater(len(chunks),0)
if __name__=='__main__':unittest.main()
