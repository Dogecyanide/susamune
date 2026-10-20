"""Exercise the live presentation timeline and the actual renderer selector."""
import ctypes as C
import _ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LiveGhostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="live-ghost-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / "src/live_ghost.cpp").read_text()
        header = (ROOT / "include/susamune/ghost.hxx").read_text()
        visual = header[header.index("struct VisualState {"):header.index("void init();")]
        code = r'''
using u8=unsigned char;using s16=short;using u16=unsigned short;
using u32=unsigned;using s32=int;using u64=unsigned long long;using f32=float;
extern "C" int _fltused=0;
extern "C" void* memset(void*p,int c,unsigned long long n){auto*b=(u8*)p;while(n--)*b++=(u8)c;return p;}
extern "C" void* memcpy(void*p,const void*q,unsigned long long n){auto*b=(u8*)p;auto*a=(const u8*)q;while(n--)*b++=*a++;return p;}
#include "susamune/ghost_format.h"
#include "susamune/ghost_fludd.h"
#include "susamune/live_race_wire.h"
#include "susamune/practice_input.h"
namespace Ghost {
'''
        code += visual + r'''
bool preparation,watch;
bool observerPreparing(){return preparation;}
bool observerStatsSuppressed(){return watch;}
bool visualState(VisualState*out){out->x=-1;return true;}
bool secondaryVisualState(VisualState*out){out->x=-2;return true;}
}
namespace LiveGhost {bool setName(const char*,unsigned);bool submit(const Ghost::VisualState&,u32,u32,u32,u32,const SusamunePracticeInput* = nullptr);}
'''
        code += source[source.index("namespace LiveGhost {"):source.index("void drawName(")]
        code += "}\nnamespace Ghost {\n"
        code += function((ROOT / "src/ghost.cpp").read_text(), "renderVisualState")
        code += r'''
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
static Ghost::VisualState pose(float x){Ghost::VisualState p={};p.x=x;p.visible=true;return p;}
static bool close(float a,float b){return a>b-.01f&&a<b+.01f;}
#define API extern "C" __declspec(dllexport)
API unsigned stateBytes(){return sizeof(LiveGhost::State);}
API unsigned scenario(unsigned test){
 using namespace LiveGhost;
 reset();Ghost::preparation=Ghost::watch=false;
 Ghost::VisualState p=pose(0),q=pose(100),out={};
 if(test==0){
  p.yaw=32000;q.yaw=-32000;p.animationPhase=4000;q.animationPhase=200;
  CHECK(submit(p,1,100,9,1000));CHECK(submit(q,2,200,9,1100));
  tick(1100,true);CHECK(LiveGhost::visualState(&out));CHECK(close(out.x,20));
  CHECK(out.yaw==32307);CHECK(out.animationPhase==4059);CHECK(out.visualQf==2);
  const auto copy=out;CHECK(LiveGhost::visualState(&out));CHECK(out.x==copy.x&&out.visualQf==copy.visualQf&&out.recordingToken==copy.recordingToken);
  tick(1350,true);CHECK(LiveGhost::visualState(&out)&&out.x==100);
  tick(1351,true);CHECK(!LiveGhost::visualState(&out));
  tick(1200,false);CHECK(!LiveGhost::visualState(&out));
  reset();CHECK(submit(p,1,100,9,1000));CHECK(submit(q,2,200,9,1100));
  tick(1180,true);CHECK(LiveGhost::visualState(&out)&&out.x==100);
  q=pose(150);CHECK(submit(q,3,250,9,1220));tick(1220,true);
  CHECK(LiveGhost::visualState(&out)&&out.x==100&&out.visualQf==12);
 }else if(test==1){
  CHECK(submit(p,10,100,9,1000));CHECK(!submit(q,9,200,9,1100));
  CHECK(!submit(q,11,99,9,1100));CHECK(!submit(q,11,100,9,1100));
  CHECK(!submit(q,11,200,9,999));CHECK(!submit(q,100,200,8,1100));
  tick(1000,true);CHECK(LiveGhost::visualState(&out)&&out.x==0);const u32 token=out.recordingToken;
  CHECK(submit(q,0,1,10,1100));CHECK(LiveGhost::visualState(&out)&&out.x==0);
  tick(1100,true);CHECK(LiveGhost::visualState(&out)&&out.x==100&&out.recordingToken!=token);
  CHECK(!submit(p,100,300,9,1110));
 }else if(test==2){
  CHECK(submit(p,0xffffffffu,0xfffffff0u,0xffffffffu,0xfffffff0u));
  CHECK(submit(q,0,0x20,0xffffffffu,0x20));
  tick(0x70,true);CHECK(LiveGhost::visualState(&out)&&out.x==100&&out.visualQf==5);
  CHECK(submit(p,0,4,0,0x80));tick(0x80,true);CHECK(LiveGhost::visualState(&out)&&out.x==0);
  tick(0x80+251,true);CHECK(!LiveGhost::visualState(&out));
 }else if(test==3){
  CHECK(submit(p,1,100,1,1000));union{u32 u;float f;}bits={0x7fc00000u};
  q.x=bits.f;CHECK(!submit(q,2,200,1,1100));bits.u=0x7f800000u;
  q.x=bits.f;CHECK(!submit(q,2,200,1,1100));q=pose(1000001);CHECK(!submit(q,2,200,1,1100));
  q=pose(1);q.animationId=336;CHECK(!submit(q,2,200,1,1100));
  q=pose(1);q.animationPhase=4096;CHECK(!submit(q,2,200,1,1100));
  q=pose(1);q.yoshi=6;CHECK(!submit(q,2,200,1,1100));
  q=pose(1);q.yoshi=1;CHECK(!submit(q,2,200,1,1100));
  q.animationId=0xb6;CHECK(submit(q,2,200,1,1100));
  q=pose(1);q.fludd.mode=15;CHECK(!submit(q,3,300,1,1200));
  q=pose(1);q.fludd.power=1;CHECK(!submit(q,3,300,1,1200));
  tick(1100,true);CHECK(LiveGhost::visualState(&out));CHECK(out.animationId==0);
 }else if(test==4){
  CHECK(submit(p,1,100,1,1000));tick(1000,true);CHECK(LiveGhost::visualState(&out));u32 token=out.recordingToken;
  q=pose(1001);CHECK(submit(q,2,150,1,1050));tick(1050,true);
  CHECK(LiveGhost::visualState(&out)&&out.x==1001&&out.visualQf==0&&out.recordingToken!=token);
  token=out.recordingToken;CHECK(submit(q,3,1200,1,2100));tick(2100,true);
  CHECK(LiveGhost::visualState(&out)&&out.recordingToken!=token);
  CHECK(setName("1234567890123456",16));CHECK(!setName("12345678901234567",17));
  CHECK(!setName("bad\nname",8));CHECK(!setName(nullptr,1));CHECK(!setName("",0));
 }else if(test==5){
  CHECK(submit(q,1,100,1,1000));tick(1000,true);
  CHECK(Ghost::renderVisualState(0,&out)&&out.x==-1);
  CHECK(Ghost::renderVisualState(1,&out)&&out.x==100);
  Ghost::preparation=true;CHECK(Ghost::renderVisualState(1,&out)&&out.x==-2);
  Ghost::preparation=false;Ghost::watch=true;CHECK(Ghost::renderVisualState(1,&out)&&out.x==-2);
  Ghost::watch=false;tick(1251,true);CHECK(!Ghost::renderVisualState(1,&out));
  CHECK(!Ghost::renderVisualState(2,&out));CHECK(!Ghost::renderVisualState(1,nullptr));
 }else if(test==6){
  SusamunePracticeInput first={},second={},input={};
  first.buttons=0x100;first.stickX=-80;first.substickY=37;first.triggerR=160;
  second.buttons=0x200;second.stickX=80;second.substickY=-37;second.triggerR=255;
  CHECK(submit(p,1,100,1,1000,&first));CHECK(submit(q,2,200,1,1100,&second));
  tick(1100,true);CHECK(inputState(&input));CHECK(input.buttons==0x100&&input.stickX==-80&&input.substickY==37&&input.triggerR==160);
  tick(1180,true);CHECK(inputState(&input));CHECK(input.buttons==0x200&&input.stickX==80&&input.substickY==-37&&input.triggerR==255);
  tick(1351,true);CHECK(!inputState(&input));tick(1200,false);CHECK(!inputState(&input));
  CHECK(submit(q,1,1,2,1400));tick(1400,true);CHECK(inputState(&input)&&input.buttons==0&&input.stickX==0&&input.triggerR==0);
  q.visible=false;CHECK(submit(q,2,2,2,1500,&first));tick(1580,true);CHECK(!inputState(&input));
  CHECK(!inputState(nullptr));
 }else if(test==7){
  SusamunePracticeInput input={};input.buttons=0x80;CHECK(!submit(p,1,100,1,1000,&input));
  input.buttons=0x8000;CHECK(!submit(p,1,100,1,1000,&input));input.buttons=0x1f7f;
  input.error=-1;CHECK(!submit(p,1,100,1,1000,&input));input.error=0;input.flags=1;
  CHECK(!submit(p,1,100,1,1000,&input));input.flags=0;CHECK(submit(p,1,100,1,1000,&input));
  setInputsShown(false);CHECK(!inputsShown());reset();CHECK(!inputsShown());setInputsShown(true);CHECK(inputsShown());
 }
 return 0;
}
'''
        directory = Path(cls.temp.name)
        cpp, dll = directory / "test.cpp", directory / "test.dll"
        cpp.write_text(code)
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-ffast-math",
                        "-I", str(ROOT / "include"), str(cpp), "-o", str(dll)],
                       capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))

    def test_timeline_and_input_boundaries(self):
        self.assertLess(self.lib.stateBytes(), 2048)
        for number, name in enumerate(("interpolation/stale", "ordering/scene", "wrap",
                                       "invalid poses", "teleport/name", "Watch provider",
                                       "matching input timeline", "input validation and toggle")):
            with self.subTest(name=name):
                self.assertEqual(self.lib.scenario(number), 0, "C++ assertion line")


if __name__ == "__main__":
    unittest.main()
