"""Literal hardware observations must preserve pending RNG chronology."""
from pathlib import Path
import ctypes as C,os,subprocess,tempfile,unittest,struct
ROOT=Path(__file__).resolve().parents[1]
def function(text,start):
 at=text.index(start);opening=text.index('{',at);depth=1;i=opening+1
 while depth:
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[at:i]+'\n'
class LiteralCalls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-literal-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  source=(ROOT/'src/ghost_trace.cpp').read_text();code=r"""
#include <cstring>
#include "susamune/ghost_trace.h"
static bool enabled=true,capturing=true;static unsigned kinds[8],lengths[8],count;static unsigned char records[8][800];
static bool OSDisableInterrupts(){bool old=enabled;enabled=false;return old;}static void OSRestoreInterrupts(bool old){enabled=old;}
struct State {unsigned rngCount,rngNames,rngFirst,rngLast,rngCaller[64];unsigned char rngIndex[512];bool ending;};static State s;
static bool recording(){return capturing;}
static void append(unsigned k,const void*p,unsigned n){kinds[count]=k;lengths[count]=n;std::memcpy(records[count++],p,n);}
"""
  code+=''.join(function(source,name) for name in ('void flushRandom() {','void literalCall(','void random('))
  code+=r"""
extern "C" {
__declspec(dllexport) void run(unsigned hardware,unsigned active){s={};count=0;enabled=true;capturing=active;unsigned seed=0x12345678;
 random(0x80012340,(seed>>16)&32767,seed);
 if(hardware)literalCall(0x8002a1d8,1,seed);else random(0x80012344,0xdeadbeef,seed);
 seed=seed*1103515245u+12345u;random(0x80012340,(seed>>16)&32767,seed);flushRandom();}
__declspec(dllexport) unsigned info(unsigned n){return n==0?count:n==1?enabled:kinds[n-2];}
__declspec(dllexport) const void* data(unsigned n){return records[n];}
}
"""
  (d/'probe.cpp').write_text(code);env=dict(os.environ);env['PATH']='C:/msys64/mingw64/bin;'+env.get('PATH','');r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2','-I',str(ROOT/'include'),str(d/'probe.cpp'),'-o',str(d/'probe.dll')],env=env,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  cls.lib=C.CDLL(str(d/'probe.dll'));cls.lib.data.restype=C.c_void_p;cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_hardware_literal_stays_between_rng_blocks(self):
  self.lib.run(1,1);self.assertEqual([self.lib.info(i) for i in range(5)],[3,1,18,15,18]);self.assertEqual(struct.unpack('>3I',C.string_at(self.lib.data(1),12)),(0x8002a1d8,1,0x12345678))
 def test_nonstandard_random_return_keeps_original_order(self):
  self.lib.run(0,1);self.assertEqual([self.lib.info(i) for i in range(5)],[3,1,18,15,18]);self.assertEqual(struct.unpack('>3I',C.string_at(self.lib.data(1),12))[1],0xdeadbeef)
 def test_inactive_recorder_emits_nothing(self):
  self.lib.run(1,0);self.assertEqual(self.lib.info(0),0);self.assertEqual(self.lib.info(1),1)
if __name__=='__main__':unittest.main()
