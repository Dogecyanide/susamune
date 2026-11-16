"""Final boot ownership and actual five-bank cache layout; no hardware access."""
from pathlib import Path
import os,re,subprocess,tempfile,unittest
import test_launcher_iso_cache as cache
ROOT=Path(__file__).resolve().parents[1]
CODE=r"""
#include "susamune/disc_cache_memory.h"
#include <cassert>
int main(){
 MoonshineGhostMemoryProof boot={{MOONSHINE_GHOST_MEMORY_MAGIC,1,17,0x003a1820,0,0x4000000,0x4000000,0x90000800,0x935e0000,0x935e0000,0x93600000,0x93600000,0x933e0000,0x93400000,0x474d5350,0}};
 boot.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&boot);
 MoonshineCacheMemoryProof p={{MS_CACHE_PROOF_MAGIC,1,17,0x474d5350,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID,0x90002000,0x933e0000,0x93400000}};
 auto valid=[&](MoonshineCacheMemoryProof q){q.word[MCP_CHECKSUM]=MoonshineCacheMemoryChecksum(&q);return MoonshineCacheMemoryProofValid(&q,&boot,0x474d5350,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID);};
 p.word[MCP_CHECKSUM]=MoonshineCacheMemoryChecksum(&p);assert(valid(p));
 for(unsigned i=0;i<16;++i){auto q=p;q.word[i]^=1;assert(!MoonshineCacheMemoryProofValid(&q,&boot,0x474d5350,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID));}
 for(unsigned i=8;i<15;++i){auto q=p;q.word[i]=1;assert(!valid(q));}
 for(unsigned low: {0u,0x80002000u,0x900007ffu,0x93030001u,0xffffffffu}){auto q=p;q.word[MCP_LOW]=low;assert(!valid(q));}
 for(unsigned high:{0u,0x93374fffu,0x9337ffffu,0x933e0001u,0xffffffffu}){auto q=p;q.word[MCP_HIGH]=high;assert(!valid(q));}
 for(unsigned nonce:{0u,16u,18u}){auto q=p;q.word[MCP_NONCE]=nonce;assert(!valid(q));}
 for(unsigned field:{MCP_MAGIC,MCP_ABI,MCP_GAME,MCP_LAYOUT,MCP_IPC_HIGH}){auto q=p;q.word[field]=0;assert(!valid(q));}
 assert(!MoonshineCacheMemoryProofValid(&p,nullptr,0x474d5350,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID));
 assert(!MoonshineCacheMemoryProofValid(nullptr,&boot,0x474d5350,NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID));
 auto q=p;q.word[MCP_LOW]=0x93030000;q.word[MCP_HIGH]=0x93380000;assert(valid(q));
 boot.word[MGM_PLATFORM]=1;boot.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&boot);assert(!valid(p));
}
"""
class CacheMemoryTests(unittest.TestCase):
 def test_proof_rejects_live_loader_allocations_stale_boots_and_corruption(self):
  with tempfile.TemporaryDirectory(prefix='cache-proof-') as tmp:
   p=Path(tmp);(p/'proof.cpp').write_text('#include <initializer_list>\n'+CODE)
   env=os.environ.copy();env['PATH']='C:/msys64/mingw64/bin;'+env['PATH']
   subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-I',str(ROOT/'include'),str(p/'proof.cpp'),'-o',str(p/'proof.exe')],check=True,env=env)
   subprocess.run([str(p/'proof.exe')],check=True,env=env)

class ActualBanksTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  text=(ROOT/'include/susamune/mem2_map.h').read_text()
  cls.banks=[tuple(int(v,16) for v in pair) for pair in re.findall(r'X\((0x13[0-9A-Fa-f]+)u, (0x[0-9A-Fa-f]+)u\)',text)]
  assert len(cls.banks)==5 and sum(size for _,size in cls.banks)==0x1fd000
  # Guard every physical island separately, including the holes between islands.
  cursor=32;rows=[];limits=[];guards=[0]
  for _,size in cls.banks:
   rows.append(f'X(extraMemory+{cursor}, {size}u)');limits.append((cursor,cursor+size));guards.append(cursor+size);cursor+=size+32
  source=cache.FIXTURE.replace('extraMemory[0x180000+128]',f'extraMemory[{cursor}]')
  a=source.index('#ifdef TEST_EXTRA_CACHE');z=source.index('#include "ISOCacheBanks.h"',a)
  source=source[:a]+'#define NIN_MEM2_DISC_CACHE_EXTRA_BANKS(X) '+' '.join(rows)+'\n#define NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID 0x123u\n#define NIN_MEM2_DISC_CACHE_EXTRA_OWNERS_RETIRED 1\n'+source[z:]
  a=source.index(' bool inExtra=');z=source.index(' if(inExtra)',a)
  source=source[:a]+' bool inExtra='+ ' || '.join(f'(out>=extraMemory+{lo}&&out<=extraMemory+{hi}&&length<=(u32)(extraMemory+{hi}-out))' for lo,hi in limits)+';\n'+source[z:]
  exports=cache.EXPORTS
  a=exports.index(' extraMemory[i]!=');z=exports.index('return 0;}',a)
  exports=exports[:a]+' '+ '||'.join(f'extraMemory[{pos}+i]!=0xC7' for pos in guards)+')'+exports[z:]
  old=(cache.FIXTURE,cache.EXPORTS);cache.FIXTURE=source;cache.EXPORTS=exports
  try:cache.LauncherIsoCacheTests.setUpClass.__func__(cls)
  finally:cache.FIXTURE,cache.EXPORTS=old
 read=cache.LauncherIsoCacheTests.read
 def test_physical_banks_exclude_launcher_game_and_driver_owners(self):
  owners=[(0x10000000,0x3030000),(0x13100000,0x50000),(0x13160000,0x20),
          (0x131c0000,0x4000),(0x13200000,0x80000),(0x13280000,0x33000),
          (0x132c0000,0x10000),(0x132f0000,0x10000),(0x133f1000,0x3000),
          (0x13400000,0x1e0000),(0x135e0000,0xa20000)]
  for base,size in self.banks:
   self.assertEqual((base|size)&31,0)
   for other,n in owners:self.assertTrue(base+size<=other or other+n<=base,(hex(base),hex(other)))
  for index,(base,size) in enumerate(self.banks):
   for other,n in self.banks[index+1:]:self.assertTrue(base+size<=other or other+n<=base)
 def test_exact_capacity_all_bank_edges_and_reused_data(self):
  self.lib.reset(0,0);self.assertEqual(self.lib.admit(0x123),1);self.lib.setup()
  self.assertEqual(self.lib.bankCount(),6);self.assertEqual(self.lib.extraBytes(),0x1fd000)
  reads=[];offset=0x100000
  for size in [0x300000]+[size for _,size in self.banks]:
   while size:
    length=min(size,0x10000);self.read(offset,length);reads.append((offset,length));size-=length;offset+=0x20000
  before=self.lib.get(0)
  for offset,length in reads:self.read(offset,length)
  self.assertEqual(self.lib.get(0),before)
  # Force wrapping, then check the remaining islands and all canaries.
  self.read(0x5000000,0x10000)
  before=self.lib.get(0)
  for offset,length in reads[48:]:self.read(offset,length)
  self.assertEqual(self.lib.get(0),before)
 def test_random_reads_across_every_bank_preserve_native_output(self):
  import random
  self.lib.reset(0,0);self.assertEqual(self.lib.admit(0x123),1);self.lib.setup()
  rng=random.Random(66)
  for _ in range(300):self.read(rng.randrange(0x1000000),rng.choice((33,511,0x4000,0x10000,0x60000,0xd0000,0x300001)))
if __name__=='__main__':unittest.main()
