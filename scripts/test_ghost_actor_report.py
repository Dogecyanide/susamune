"""Failure actor rows preserve the same ordered, deduplicated world witness."""
import ctypes as C,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DRIVER=r"""
#include "susamune/ghost_world_witness.h"
#include <cstring>
namespace W=GhostWorldWitness;
static unsigned char memory[0x4000],output[4*256+64];static unsigned scratch[16],count,reads;
static W::Record original,snapshot;
static void put(unsigned at,unsigned v){for(unsigned i=0;i<4;++i)memory[at+i]=v>>(24-8*i);}
static bool read(void*,unsigned p,void*out,unsigned n){if(p<0x80010000u||p-0x80010000u>sizeof(memory)-n)return false;std::memcpy(out,memory+p-0x80010000u,n);if(n==0xf4)++reads;return true;}
static void list(unsigned at,unsigned node,unsigned manager){put(at+4,manager?1:0);put(at+8,0x80010000+(manager?node:at+8));put(at+12,0x80010000+(manager?node:at+8));if(manager){put(node,0x80010000+at+8);put(node+4,0x80010000+at+8);put(node+8,0x80010000+manager);}}
extern "C" {
__declspec(dllexport) void reset(){std::memset(memory,0,sizeof(memory));std::memset(output,0xa5,sizeof(output));count=reads=0;
 list(0x120,0x200,0x300);list(0x110,0x220,0x300);list(0x130,0,0);
 put(0x310,2);put(0x314,2);put(0x318,0x80010400);put(0x400,0x80011000);put(0x404,0x80012000);
 for(unsigned p=0x1000;p<=0x2000;p+=0x1000){memory[p+8]=0x12;memory[p+9]=0x34;put(p+0x4c,0x08000004);for(unsigned i=0;i<3;++i)put(p+0x24+i*4,0x3f800000);put(p+0xf0,1);}
 original=W::capture({nullptr,read},0x80010100,scratch,16);reads=0;}
__declspec(dllexport) unsigned take(unsigned capacity){snapshot=W::captureSnapshot({nullptr,read},0x80010100,scratch,16,output+32,capacity,count);return snapshot.status;}
__declspec(dllexport) unsigned value(unsigned key){return key==0?count:key==1?reads:key==2?snapshot.hash:key==3?original.hash:snapshot.count;}
__declspec(dllexport) int guards(unsigned capacity){for(unsigned i=0;i<32;++i)if(output[i]!=0xa5)return 0;for(unsigned i=32+capacity*256;i<sizeof(output);++i)if(output[i]!=0xa5)return 0;return 1;}
__declspec(dllexport) int rows(){for(unsigned i=0;i<count;++i){const unsigned char*r=output+32+i*256;unsigned address=0x80011000+i*0x1000;for(unsigned n=0;n<4;++n)if(r[n]!=((address>>(24-8*n))&255))return 0;if(std::memcmp(r+8,memory+0x1000+i*0x1000,0xf4))return 0;for(unsigned n=252;n<256;++n)if(r[n])return 0;}return 1;}
}
"""
class ActorReportTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='actor-report-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name);(d/'driver.cpp').write_text(DRIVER)
  env=dict(os.environ);env['PATH']='C:/msys64/mingw64/bin;'+env.get('PATH','')
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2','-I',str(ROOT/'include'),str(d/'driver.cpp'),str(ROOT/'src/ghost_world_witness.cpp'),'-o',str(d/'driver.dll')],capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  cls.lib=C.CDLL(str(d/'driver.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.value.restype=C.c_uint
 def setUp(self):self.lib.reset()
 def test_duplicate_registrations_emit_one_row_and_same_hash(self):
  self.assertEqual(self.lib.take(4),0);self.assertEqual(self.lib.value(0),2);self.assertEqual(self.lib.value(1),2);self.assertEqual(self.lib.value(2),self.lib.value(3));self.assertTrue(self.lib.rows());self.assertTrue(self.lib.guards(4))
 def test_short_output_is_bounded_and_reports_partial_snapshot(self):
  self.assertNotEqual(self.lib.take(1),0);self.assertEqual(self.lib.value(0),1);self.assertTrue(self.lib.guards(1));self.assertTrue(self.lib.rows())
 def test_zero_capacity_does_not_write_output(self):
  self.assertNotEqual(self.lib.take(0),0);self.assertEqual(self.lib.value(0),0);self.assertTrue(self.lib.guards(0))
if __name__=='__main__':unittest.main()
