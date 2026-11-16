"""Guest read dispatch restarts the optional-background idle interval."""
from pathlib import Path
import ctypes as C,os,subprocess,tempfile,unittest
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class DiscDispatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='ms-di-idle-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  code=r"""
using u32=unsigned;unsigned ticks,DILastReadTick,calls,flushed;int DI_Handle=7,DI_MessageQueue=9;struct Msg{int result;}DI_CallbackMsg;
#define HW_TIMER 0
unsigned read32(unsigned){return ticks;}
void DIFinishAsync(){ticks+=100;}
void sync_after_write(void*,unsigned n){flushed=n;}
void IOS_IoctlAsync(int handle,unsigned mode,void*offset,unsigned unused,void*buffer,unsigned bytes,int queue,Msg*msg){
 if(handle==7&&mode==3&&offset==(void*)0x2000&&unused==0&&buffer==(void*)0x8000&&bytes==4096&&queue==9&&msg==&DI_CallbackMsg&&msg->result==-1&&DILastReadTick==ticks)++calls;
}
"""
  code+=function((ROOT/'launcher/kernel/DI.c').read_text(),'DiscReadAsync')
  code+=r"""
#define API extern "C" __declspec(dllexport)
API unsigned dispatch(unsigned now){ticks=now;DILastReadTick=calls=flushed=0;DiscReadAsync(0x8000,0x2000,4096,3);return calls==1&&flushed==32&&DILastReadTick==now+100;}
"""
  (d/'test.cpp').write_text(code)
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2',str(d/'test.cpp'),'-o',str(d/'test.dll')],capture_output=True,text=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.lib.dispatch.argtypes=[C.c_uint];cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_timestamp_follows_old_completion_and_preserves_new_request(self):
  for now in (0,3000,0xffffffd0):self.assertEqual(self.lib.dispatch(now),1)
if __name__=='__main__':unittest.main()
