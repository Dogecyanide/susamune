"""Replay the production RNG batching logic, including reseeds and interleaved events."""
import ctypes as C,os,struct,subprocess,tempfile,unittest
from pathlib import Path
from test_ghost_trace_startup import function
ROOT=Path(__file__).resolve().parents[1]
class RandomTraceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='trace-rng-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  source=(ROOT/'src/ghost_trace.cpp').read_text(encoding='utf-8');state=source[source.index('struct State {'):source.index('\nstruct Actor {')]
  code='''#include <cstring>
#include "susamune/ghost_trace.h"
struct TMarioGamePad {unsigned char bytes[240];};struct TMarioControllerWork {unsigned char bytes[36];};
struct ContactSample {unsigned role,pointer,valid,reserved;unsigned char triangle[0x48];};struct CameraSample {unsigned pointer,mode,child,valid;unsigned char interpolation[0x48];};
namespace GhostSimulation {struct Snapshot {unsigned char bytes[64];};}
bool irqOn=true;bool OSDisableInterrupts(){bool old=irqOn;irqOn=false;return old;}void OSRestoreInterrupts(bool old){irqOn=old;}
'''+state+'''
State s{};bool bootReady=true;unsigned char buffers[2][MS_TRACE_BUFFER_BYTES];
unsigned char*buffer(unsigned n){return buffers[n];}void flushRandom();
'''
  code+='\n'.join(function(source,n) for n in ('seal','stop','append','flushRandom','recording','random'))
  code+='''
extern "C" {
__declspec(dllexport) void resetRecorder(){s={};s.command=MS_TRACE_START;s.response.phase=MS_TRACE_RECORDING;s.frame=1;s.next=1;irqOn=true;s.hash[0]=s.hash[1]=2166136261u;}
__declspec(dllexport) void emit(unsigned c,unsigned r,unsigned seed){random(c,r,seed);}
__declspec(dllexport) void mark(){unsigned values[2]={0,0};append(MS_TRACE_WORLD_SUMMARY,values,8);}
__declspec(dllexport) void flush(){flushRandom();}
__declspec(dllexport) unsigned length(){return s.used[0];}
__declspec(dllexport) const void *data(){return buffers[0];}
__declspec(dllexport) unsigned interrupts(){return irqOn;}
}
'''
  (folder/'test.cpp').write_text(code,encoding='utf-8');env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static','-I',str(ROOT/'include'),str(folder/'test.cpp'),'-o',str(folder/'test.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(folder/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.data.restype=C.c_void_p;cls.lib.emit.argtypes=[C.c_uint]*3
 def test_exact_calls_reseeds_return_overrides_and_event_order(self):
  self.lib.resetRecorder();expected=[];seed=123
  for i in range(2400):
   if i in (370,1100):seed=0xdeadbeef
   seed=(seed*1103515245+12345)&0xffffffff;caller=0x80010000+4*(i%71);result=(seed>>16)&32767
   if i==1500:result=42
   self.lib.emit(caller,result,seed);expected.append((caller,result,seed))
   if i%199==0:self.lib.mark();expected.append('marker')
   self.assertEqual(self.lib.interrupts(),1)
  self.lib.flush();self.assertEqual(self.lib.interrupts(),1);raw=C.string_at(self.lib.data(),self.lib.length());actual=[];pos=0
  while pos<len(raw):
   kind,n,frame,tick=struct.unpack_from('>HHII',raw,pos);body=raw[pos+12:pos+12+n];pos+=12+n
   if kind==15:actual.append(struct.unpack('>3I',body))
   elif kind==13:actual.append('marker')
   else:
    self.assertEqual(kind,18);seed,last,count,callers=struct.unpack_from('>4I',body);names=struct.unpack_from('>'+str(callers)+'I',body,16)
    for j,index in enumerate(body[16+4*callers:]):
     if j:seed=(seed*1103515245+12345)&0xffffffff
     actual.append((names[index],(seed>>16)&32767,seed))
    self.assertEqual(seed,last);self.assertEqual(n,16+4*callers+count)
  self.assertEqual(actual,expected)
  self.assertLess(len(raw),2400*24)
if __name__=='__main__':unittest.main()
