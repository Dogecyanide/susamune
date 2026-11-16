"""Run the production bounded recorder against owned banks and observer stubs."""
import ctypes as C
import pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class RecordingTests(unittest.TestCase):
 def test_bounded_recording_and_export(self):
  code=r'''#include "susamune/ghost_context.hxx"
#include "susamune/ghost_stage_context.hxx"
#include "susamune/ghost_simulation.hxx"
#include "susamune/checksum.hxx"
#include "Dolphin/mem.h"
extern "C" void*memset(void*p,u32 x,size_t n){u8*a=(u8*)p;while(n--)*a++=(u8)x;return p;}
extern "C" void*memcpy(void*p,const void*q,size_t n){u8*a=(u8*)p;const u8*b=(const u8*)q;while(n--)*a++=*b++;return p;}
extern "C" int memcmp(const void*p,const void*q,size_t n){const u8*a=(const u8*)p,*b=(const u8*)q;while(n--){if(*a!=*b)return *a-*b;++a;++b;}return 0;}
namespace Checksum {u32 crc32(const void*p,u32 n,u32,u32){u32 r=0;const u8*b=(const u8*)p;while(n--)r=r*33+*b++;return r;}}
bool known,loaded;u8 setting;
namespace GhostStageContext {bool restoredStage(){return loaded;}bool sample(Sample*out){if(!known)return false;*out={123,20,24,1,1,0};return true;}}
namespace GhostSimulation {void capture(Snapshot&v){memset(&v,0,sizeof(v));v.bytes[0]=setting;}void readCamera(CameraObservation&v){v={-123,4,4,true,known};}}
#include "GHOST_SOURCE"
alignas(32) u8 banks[2][0x80040],encoded[SUSAMUNE_GHOST_CONTEXT_MAX_SIZE+64];
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
extern "C" __declspec(dllexport) unsigned run(){
 using namespace GhostContext;
 memset(banks,0xa5,sizeof(banks));memset(encoded,0x5a,sizeof(encoded));
 void*b=banks[0]+32;void*c=banks[1]+32;known=true;loaded=false;setting=0;reset(b);reset(c);
 auto*h=(SusamuneGhostContextHeader*)prefix(b);auto*r=(SusamuneGhostContextRecord*)(h+1);
 segment(b,0,20,0,true);CHECK(h->count==1&&r[0].captureQf==20&&r[0].preSetupSeed==123);
 CHECK((r[0].flags&31)==31&&r[0].cameraYaw==-123);CHECK(prefixSize(c)==32);
 beginFrame();input(b,0,20,0);beginFrame();input(b,0,24,1);CHECK(h->count==1);
 beginFrame();beginFrame();input(b,0,28,2);CHECK(h->count==2&&r[1].kind==SUSAMUNE_GHOST_CONTEXT_INPUT_GAP);
 setting=1;beginFrame();input(b,0,32,3);CHECK(h->count==3&&r[2].kind==SUSAMUNE_GHOST_CONTEXT_SETTINGS);
 loaded=true;known=false;restored(b);beginFrame();input(b,0,36,4);
 CHECK(h->count==4&&r[3].kind==SUSAMUNE_GHOST_CONTEXT_RESTORE);
 CHECK(r[3].flags==SUSAMUNE_GHOST_CONTEXT_RESTORED&&!r[3].preSetupSeed&&!r[3].movementTicks&&!r[3].cameraYaw);
 endpoint(b,0,34,4,true);CHECK(h->count==4&&r[3].kind==SUSAMUNE_GHOST_CONTEXT_HELD_END);
 beginFrame();setting=0;input(b,0,34,4);CHECK(h->count==4);
 CHECK(exportInto(encoded+32,b,34,1,3));auto*e=(SusamuneGhostContextHeader*)(encoded+32);auto*er=(SusamuneGhostContextRecord*)(e+1);
 CHECK(e->count==4&&er[0].inputIndex==0&&(er[0].flags&SUSAMUNE_GHOST_CONTEXT_BEFORE_INPUTS));
 CHECK(er[3].inputIndex==3&&e->dataChecksum!=0);
 clearSegment(b,0);CHECK(h->count==0);reset(b);loaded=false;known=true;
 segment(b,0,0,0,false);endpoint(b,0,4,0,false);
 CHECK(r[1].flags==0&&!r[1].preSetupSeed&&!r[1].directorTicks&&!r[1].cameraYaw);
 reset(b);segment(b,0,0,0,false);
 for(u32 i=1;i<300;++i){beginFrame();setting=i&1;input(b,0,i,i);}
 CHECK(h->flags&SUSAMUNE_GHOST_CONTEXT_TRUNCATED);CHECK(h->count==106);
 for(u16 i=1;i<64;++i)segment(b,i,1000+i,300,false);
 CHECK(h->count==169&&prefixSize(b)==SUSAMUNE_GHOST_CONTEXT_MAX_SIZE);
 for(u32 i=0;i<32+SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET;++i)CHECK(banks[0][i]==0xa5);
 for(u32 i=32+SUSAMUNE_GHOST_CONTEXT_BANK_OFFSET+SUSAMUNE_GHOST_CONTEXT_MAX_SIZE+8;i<sizeof(banks[0]);++i)CHECK(banks[0][i]==0xa5);
 CHECK(prefixSize(c)==32);
 for(u32 i=0;i<32;++i)CHECK(encoded[i]==0x5a);
 for(u32 i=32+32+4*96;i<sizeof(encoded);++i)CHECK(encoded[i]==0x5a);
 return 0;
}
'''
  code=code.replace('GHOST_SOURCE',(ROOT/'src/ghost_context.cpp').as_posix())
  with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='context-recorder-') as d:
   folder=pathlib.Path(d);src=folder/'probe.cpp';src.write_text(code);dll=folder/'probe.dll'
   subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-std=c++17','-O2','-fno-builtin','-ffreestanding','-I',str(ROOT/'include'),'-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry',str(src),'-o',str(dll)],check=True,capture_output=True)
   lib=C.CDLL(str(dll))
   try:self.assertEqual(lib.run(),0,'production recorder/canary check line')
   finally:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle))
if __name__=='__main__':unittest.main()
