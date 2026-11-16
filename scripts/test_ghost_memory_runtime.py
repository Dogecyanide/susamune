"""Run production ownership/pattern logic in an isolated host address space."""
from pathlib import Path
import os,re,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
PREFIX=r"""
#include <windows.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "susamune/ghost_memory.hxx"
#include "susamune/susamune_cfg.h"
#include "susamune/memory_telemetry_scan.h"
#define SUSAMUNE_MEM1_ADDR(jp,us,pal) pal
static bool mapping=true,stageReady=true,wrongAllocation=false;
static unsigned allocations=0,stores=0,invalidates=0,irqDepth=0;
struct TMarDirector { unsigned _260; };
namespace RetailInput { const TMarDirector *stageDirector() { static TMarDirector d={1};return stageReady?&d:nullptr; } }
bool OSDisableInterrupts(){assert(!irqDepth);irqDepth=1;return true;}
void OSRestoreInterrupts(bool){assert(irqDepth);irqDepth=0;}
void DCStoreRange(void*,unsigned){++stores;}
void DCInvalidateRange(void*,unsigned){++invalidates;}
unsigned &W(unsigned p){return *reinterpret_cast<unsigned*>(static_cast<uintptr_t>(p));}
constexpr unsigned manager=0x80010000,heap=0x80020000,owner=0x80030000,list=0x803fba30;
class JKRExpHeap { public: unsigned getFreeSize(){assert(!irqDepth);const auto p=(unsigned)(uintptr_t)this;return W(p+0x74)?W(W(p+0x74)+4):0;} };
constexpr unsigned empty=0x80041000,hud=0x80042000,guide=0x80044000,block=0x80043000;
class JKRAramHeap { public: enum EAllocMode { HEAD,TAIL };void *alloc(unsigned bytes,EAllocMode mode){
 assert(!irqDepth&&bytes==0x60000&&mode==TAIL);++allocations;
 const unsigned last=W(list+4)-4;assert(W(last+28)>=bytes);
 W(block+4)=block;W(block+8)=list;W(block+12)=last+4;W(block+16)=0;
 W(block+20)=wrongAllocation?0xf90000:0xfa0000;W(block+24)=bytes;W(block+28)=0;
 W(last+28)-=bytes;W(last+16)=block+4;W(list+4)=block+4;++W(list+8);
 return reinterpret_cast<void*>(static_cast<uintptr_t>(block));
} };
"""
TEST=r"""
void map(unsigned base,unsigned size){void*p=VirtualAlloc((void*)(uintptr_t)base,size,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(p==(void*)(uintptr_t)base);}
void setup(){
 memset((void*)0x80000000,0,0x1800000);memset((void*)SUSAMUNE_GHOST_RECORD_PPC_BASE,0,0x80000);
 memset((void*)0x933f0000,0xa5,0x200000);memset((void*)0x90f90000,0xa5,0x80000);
 memset((void*)SUSAMUNE_MEM2_CFG_PPC_BASE,0,0x10000);
 auto *cfg=SUSAMUNE_CFG_PPC_PTR;cfg->magic=SUSAMUNE_CFG_MAGIC;cfg->version=SUSAMUNE_CFG_VERSION;cfg->flags=MOONSHINE_GHOST_MEMORY_FLAG;
 MoonshineGhostMemoryProof p={{MOONSHINE_GHOST_MEMORY_MAGIC,1,17,0x003a1820,0,0x4000000,0x4000000,0x90000800,0x935e0000,0x935e0000,0x93600000,0x93600000,0x933e0000,0x93400000,0x474d5350,0}};
 p.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&p);memcpy((void*)MOONSHINE_GHOST_PROOF_PPC_BASE,&p,sizeof(p));
 W(0x80405908)=manager;W(0x80405870)=hud;W(0x80405878)=guide;
 W(manager+0x60)=0x4000;W(manager+0x64)=0xf40000;W(manager+0x68)=0xf44000;W(manager+0x6c)=0xbc000;W(manager+0x78)=heap;
 W(heap+0x30)=owner;W(owner)=0x803d78f0;W(owner+0x30)=0x80050000;W(owner+0x34)=0x80051000;W(owner+0x38)=0x1000;
 W(owner+0x74)=W(owner+0x78)=0x80050000;W(0x80050004)=0xff0;
 const unsigned blocks[3]={empty,hud,guide},sizes[3]={0,94304,234848};unsigned at=0xf44000;
 for(unsigned i=0;i<3;++i){auto b=blocks[i];W(b+4)=b;W(b+8)=list;W(b+12)=i?blocks[i-1]+4:0;W(b+16)=i<2?blocks[i+1]+4:0;W(b+20)=at;W(b+24)=sizes[i];at+=sizes[i];W(b+28)=i==2?0x1000000-at:0;}
 W(list)=empty+4;W(list+4)=guide+4;W(list+8)=3;allocations=stores=invalidates=irqDepth=0;mapping=stageReady=true;wrongAllocation=false;
}
unsigned error(){unsigned s[11];GhostMemory::status(s);return s[1];}
void canaries(){for(auto p:{0x933ffffcu,0x935e0000u,0x90f9fffcu,0x91000000u})assert(W(p)==0xa5a5a5a5);}
int main(){
 map(0x80000000,0x1800000);map(SUSAMUNE_GHOST_RECORD_PPC_BASE,0x80000);map(SUSAMUNE_MEM2_CFG_PPC_BASE,0x10000);
 map(0x933f0000,0x200000);map(0x90f90000,0x80000);
 setup();SUSAMUNE_CFG_PPC_PTR->flags=0;GhostMemory::init();GhostMemory::update();assert(error()==1&&!allocations&&!stores);canaries();
 setup();W(MOONSHINE_GHOST_PROOF_PPC_BASE+8)^=1;GhostMemory::init();GhostMemory::update();assert(error()==2&&!allocations&&!stores);
 setup();mapping=false;GhostMemory::init();GhostMemory::update();assert(error()==3&&!allocations&&!stores);
 setup();stageReady=false;GhostMemory::init();GhostMemory::update();assert(!allocations&&!stores);
 stageReady=true;W(owner+0x74)=W(owner+0x78)=0;GhostMemory::update();assert(error()==4&&!allocations&&!stores);
 setup();wrongAllocation=true;GhostMemory::init();GhostMemory::update();assert(error()==5&&allocations==1&&!stores&&!GhostMemory::ready());canaries();
 setup();GhostMemory::init();for(unsigned i=0;i<432;++i)GhostMemory::update();unsigned s[11];GhostMemory::status(s);
 assert(GhostMemory::ready()&&s[6]==2&&allocations==1&&stores==144&&invalidates>144);canaries();
 assert(GhostMemory::primary(0)==(void*)0x93408000&&GhostMemory::tail(1)==(void*)0x90fd0000&&!GhostMemory::primary(2));
 GhostMemory::init();assert(GhostMemory::ready()&&allocations==1);for(unsigned i=0;i<288;++i)GhostMemory::update();assert(allocations==1);canaries();
 W(0x93400000)^=1;GhostMemory::update();assert(error()==7&&!GhostMemory::ready());GhostMemory::status(s);assert(s[7]==0x93400000&&s[8]!=s[9]);
 auto oldStores=stores;for(unsigned i=0;i<500;++i)GhostMemory::update();assert(stores==oldStores);canaries();
 setup();GhostMemory::init();GhostMemory::update();W(0x80405908)=0;GhostMemory::update();assert(error()==6&&!GhostMemory::ready());canaries();
 puts("Host lifecycle: rejected grants, native ownership, two full passes, reset adoption, corruption and ownership-loss stop passed.");
}
"""
class RuntimeTests(unittest.TestCase):
 def test_claim_and_pattern_lifecycle(self):
  source=(ROOT/'src/ghost_memory.cpp').read_text()
  source=re.sub(r'^#include[^\n]*\n','',source,flags=re.M)
  start=source.index('bool mapped(');end=source.index('\n#endif',start)
  source=source[:start]+'bool mapped(unsigned,unsigned) { return mapping; }'+source[end:]
  with tempfile.TemporaryDirectory(prefix='memory-runtime-',dir=ROOT/'build') as d:
   d=Path(d);cpp=d/'runtime.cpp';cpp.write_text(PREFIX+'\n'+source+'\n'+TEST,encoding='utf-8');exe=d/'runtime.exe'
   env=os.environ.copy();env['PATH']='C:/msys64/mingw64/bin;'+env['PATH']
   subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-fpermissive','-DIS_EMULATOR=0','-DTIMEWARP_QF_MEMORY=1','-DTIMEWARP_QF_MEMORY_PILOT=1','-I',str(ROOT/'include'),str(cpp),'-o',str(exe)],check=True,env=env)
   subprocess.run([str(exe)],check=True,env=env)
if __name__=='__main__':unittest.main()
