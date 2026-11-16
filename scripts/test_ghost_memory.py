"""Admission checks for the proposed extra ghost memory; no hardware writes."""
from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
CODE=r"""
#include "susamune/ghost_memory.h"
#include <cassert>
#include <cstdio>
int main(){
 MoonshineGhostMemoryProof p={{MOONSHINE_GHOST_MEMORY_MAGIC,1,17,0x003a1820,0,0x4000000,0x4000000,0x90000800,0x935e0000,0x935e0000,0x93600000,0x93600000,0x933e0000,0x93400000,0x474d5350,0}};
 p.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&p);assert(MoonshineGhostMemoryProofValid(&p,0x474d5350));
 for(unsigned i=0;i<16;++i){auto bad=p;bad.word[i]^=1;assert(!MoonshineGhostMemoryProofValid(&bad,0x474d5350));}
 for(unsigned i=3;i<15;++i){auto bad=p;bad.word[i]=0;bad.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&bad);if(i!=MGM_PLATFORM)assert(!MoonshineGhostMemoryProofValid(&bad,0x474d5350));}
 auto bad=p;bad.word[MGM_PLATFORM]=1;bad.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&bad);assert(!MoonshineGhostMemoryProofValid(&bad,0x474d5350));
 bad=p;bad.word[MGM_ARENA_HIGH]=0x93400000;bad.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&bad);assert(!MoonshineGhostMemoryProofValid(&bad,0x474d5350));
 assert(!MoonshineGhostMemoryProofValid(nullptr,0x474d5350));assert(!MoonshineGhostMemoryProofValid(&p,0x474d534a));
 assert(MoonshineGhostMemoryBat(0x90001fff,0x10000002,0x93400000,0x1e0000));
 assert(MoonshineGhostMemoryBat(0x90001fff,0x10000002,0x90fa0000,0x60000));
 assert(!MoonshineGhostMemoryBat(0x90001ffd,0x10000002,0x93400000,0x1e0000));
 assert(!MoonshineGhostMemoryBat(0x90001fff,0x10000003,0x93400000,0x1e0000));
 assert(!MoonshineGhostMemoryBat(0x90001fff,0x00000002,0x93400000,0x1e0000));
 assert(!MoonshineGhostMemoryBat(0x900003ff,0x10000002,0x93400000,0x1e0000));
 assert(!MoonshineGhostMemoryBat(0x90001fff,0x10000002,0xfffffff0,64));
 assert(!MoonshineGhostMemoryBat(0x90001fff,0x10000002,0x93400000,0));
 assert(!MoonshineGhostMemoryBat(0x9000000b,0x10000002,0x90000000,0x10000));
 static_assert(MOONSHINE_GHOST_QF_BANK_BYTES>=6u*36000u+13u*71929u+32u,"ten-minute raw fallback must fit");
 static_assert(MOONSHINE_GHOST_MEMORY_RUNTIME_OFFSET==0x7f600u,"physical runtime location");
 static_assert(MOONSHINE_GHOST_PROOF_OFFSET==0x7e8a0u,"physical proof location");
 puts("Memory proof, stale/malformed claims, BAT bounds/permissions and layout checks passed.");
}
"""
class GhostMemoryTests(unittest.TestCase):
 def test_admission_and_layout(self):
  with tempfile.TemporaryDirectory(prefix='ghost-memory-',dir=ROOT/'build') as d:
   d=Path(d);source=d/'memory.cpp';source.write_text(CODE);exe=d/'memory.exe';env=os.environ.copy();env['PATH']='C:/msys64/mingw64/bin;'+env['PATH']
   subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-DIS_EMULATOR=0','-I',str(ROOT/'include'),str(source),'-o',str(exe)],check=True,env=env)
   subprocess.run([str(exe)],check=True,env=env)
if __name__=='__main__':unittest.main()
