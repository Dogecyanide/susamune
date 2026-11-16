"""Bounded memory scanners and the monitor's production-protocol peer."""
import json, os, struct, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/memory_monitor'))
from monitor import NativePeer, decode_report, apply_measurement
from build_peer import build

SCAN=r"""
#include "susamune/memory_telemetry_scan.h"
#include <map>
#include <cassert>
#include <cstdio>
int main(){
 std::map<unsigned,unsigned>w;unsigned reads=0;
 auto read=[&](unsigned a){assert(MemoryReadable(a,4));++reads;return w[a];};
 const unsigned root=0x80010000,a=0x80010100,b=0x80010200,cap=0xf2ffe0;
 w[root]=0x01010000;w[root+8]=0x10000;w[root+16]=cap;MemoryPoolSample out;
 assert(MemoryWaveSample(root,read,out)&&out.used==0&&out.largestFree==cap);
 w[root]=0x01010002;w[root+20]=a;w[a+8]=0x11000;w[a+16]=0x2000;w[a+24]=root;w[a+28]=b;
 w[b+8]=0x16000;w[b+16]=0x1000;w[b+24]=root;
 assert(MemoryWaveSample(root,read,out)&&out.used==0x3000&&out.tailExtent==0x7000&&out.largestFree==cap-0x7000);
 w[b+28]=a;assert(!MemoryWaveSample(root,read,out));w[b+28]=0;
 w[b+24]=0;assert(!MemoryWaveSample(root,read,out));w[b+24]=root;
 w[b+16]=0xffffffff;assert(!MemoryWaveSample(root,read,out));w[b+16]=0x1000;
 w[root]=0x01010081;assert(!MemoryWaveSample(root,read,out));w[root]=0x01010002;
 w[root+20]=0x90000000;assert(!MemoryWaveSample(root,read,out));w[root+20]=a;
 assert(!MemoryWaveSample(0xffffffff,read,out));
 w.clear();const unsigned manager=0x80011000,list=0x80012000;
 w[manager + 0x60]=0x4000;w[manager + 0x64]=0xf40000;w[manager + 0x68]=0xf44000;w[manager + 0x6c]=0xbc000;
 w[list]=a+4;w[list+4]=b+4;w[list+8]=2;
 w[a+4]=a;w[a+8]=list;w[a+16]=b+4;w[a+20]=0xf44000;
 w[b+4]=b;w[b+8]=list;w[b+12]=a+4;w[b+20]=0xf44000;w[b+24]=0x4000;w[b+28]=0xb8000;
 assert(MemoryArchiveSample(manager,list,read,out)&&out.used==0x4000&&out.largestFree==0xb8000);
 w[b+12]=0;assert(!MemoryArchiveSample(manager,list,read,out));w[b+12]=a+4;
 w[b+28]++;assert(!MemoryArchiveSample(manager,list,read,out));w[b+28]--;
 w[list+8]=3;assert(!MemoryArchiveSample(manager,list,read,out));w[list+8]=2;
 w[b+16]=a+4;assert(!MemoryArchiveSample(manager,list,read,out));w[b+16]=0;
 w.clear();const unsigned heap=0x80018000,base=0x80020000,vt=0x803d78f0;
 w[heap]=vt;w[heap+0x30]=base;w[heap+0x34]=base+0x1000;w[heap+0x38]=0x1000;
 w[heap+0x74]=base;w[heap+0x78]=base+0x200;w[base+4]=0x100;w[base+12]=base+0x200;
 w[base+0x204]=0x200;w[base+0x208]=base;
 assert(MemoryExpSample(heap,vt,read,out)&&out.used==0xd00&&out.largestFree==0x200);
 w[base+0x20c]=base;assert(!MemoryExpSample(heap,vt,read,out));w[base+0x20c]=0;
 w[base+0x204]=0xffffffff;assert(!MemoryExpSample(heap,vt,read,out));
 assert(!MemoryExpSample(heap,vt+4,read,out));
 printf("Valid pools, gaps, cycles, bad owners, overflow and out-of-range pointers checked (%u reads).\n",reads);
}
"""
class TelemetryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='memory-monitor-',dir=ROOT/'build');cls.addClassCleanup(cls.tmp.cleanup);cls.work=Path(cls.tmp.name)
  cls.lib=build(cls.work/('peer.dll' if sys.platform=='win32' else 'peer.so'))
 def test_bounded_scanners(self):
  source=self.work/'scan.cpp';source.write_text(SCAN);exe=self.work/'scan.exe'
  compiler='C:/msys64/mingw64/bin/g++.exe' if sys.platform=='win32' else 'g++';env=os.environ.copy()
  if sys.platform=='win32':env['PATH']='C:/msys64/mingw64/bin;'+env['PATH']
  subprocess.run([compiler,'-std=c++17','-O2','-I',str(ROOT/'include'),str(source),'-o',str(exe)],check=True,env=env)
  subprocess.run([str(exe)],check=True,env=env)
 def connect(self):
  h=NativePeer(self.lib,host=True,pin=3456,nonce=(1,2));g=NativePeer(self.lib,host=False,pin=3456,nonce=(3,4),remote=('192.168.2.2',48223))
  self.addCleanup(h.close);self.addCleanup(g.close);return h,g
 def pump(self,h,g,ms,drop=False):
  h.tick(ms);g.tick(ms)
  for a,b,source in ((h,g,('192.168.2.2',48223)),(g,h,('192.168.2.40',48222))):
   for data,to in a.outgoing():
    if not drop:b.receive(data,source,ms)
 def test_handshake_retransmission_and_all_pages(self):
  h,g=self.connect()
  for ms in range(0,1200,10):self.pump(h,g,ms,ms<300)
  self.assertEqual((h.state(),g.state()),(4,4))
  pages=[(0x4d4d5431,1,0x02030100,7,0xf2ffe0,0x800000,0x72ffe0,0x800000,0xbc000,0x60000,0x5c000,0x60000,0x1000000,0x200000,128,1200),
         (0x4d4d5432,2,0x02030100,3,23461888,8000000,4000000,4000000,0,7000000,20000,30000,40000,50000,0,2000),
         (0x4d4d5433,3,0x02030100,7,0x1000000,0xe00000,0x100000,0,0x400000,0x300000,0x80000,0,0x151800,0x20000,128,3000),
         (0x4d4d5434,4,0x02030100,1,11,0,0x1e0000,0x60000,0x4000,0x240000,3,0,0,0,2,4000),
         (0x4d4d5435,5,0x02030100,1,2,0,10000,9000,1000,2000,50,130,230,20,0x4ff,5000)]
  ms=1200
  for page in pages:
   raw=struct.pack('>16I',*page);sent=False;got=None
   for _ in range(200):
    if not sent:sent=bool(g.dll.mm_test_report(g.handle,raw))
    self.pump(h,g,ms);ms+=10
    if (got:=h.report()) is not None:break
   self.assertTrue(sent);self.assertEqual(got,raw);self.assertEqual(decode_report(got)['page'],page[0]-0x4d4d5431)
  self.assertEqual(h.name(),'Probe test Wii')
 def test_bad_reports_are_rejected(self):
  good=[0x4d4d5431,1,0x02030100,1,100,40,60,40,0,0,0,0,0,0,0,0]
  self.assertEqual(decode_report(struct.pack('>16I',*good))['audio']['free'],60)
  for index,value in ((0,0),(2,0xff000000),(3,128),(4,0),(5,101),(6,61),(7,39)):
   bad=good.copy();bad[index]=value
   with self.subTest(index=index),self.assertRaises(ValueError):decode_report(struct.pack('>16I',*bad))
  with self.assertRaises(ValueError):decode_report(b'bad')
 def test_receiver_aggregates_partial_pages_without_losing_other_pools(self):
  state={"latest":None,"pages_seen":{},"last_received":None,"samples":0,"observed_peaks":{},"stage_peaks":{},"history":[],"invalid_pool_samples":0}
  common={"region":"PAL","area":2,"episode":4,"level":"Bianco 5","received_unix":1000}
  pages=[{"page":0,"audio":{"used":10},"archives":None,"stage":{"used":20}},
         {"page":1,"states":{"used":30},"ghosts":{}},
         {"page":2,"root":{"used":40},"system":None,"audio_mem1":{"used":50}}]
  for i,page in enumerate(pages):apply_measurement(state,{**common,**page},i*100)
  self.assertEqual(state["samples"],3);self.assertEqual(len(state["pages_seen"]),3)
  self.assertEqual(len(state["history"]),1);self.assertEqual(state["invalid_pool_samples"],2)
  self.assertEqual(state["observed_peaks"],{"audio":10,"stage":20,"states":30,"root":40,"audio_mem1":50})
  self.assertEqual(state["latest"]["audio"]["used"],10)
  self.assertEqual(state["stage_peaks"]["PAL:2:4"]["states"],30)
 def test_reservation_report_states_and_corruption(self):
  good=[0x4d4d5434,4,0x02030100,1,11,0,0x1e0000,0x60000,0x4000,0x240000,3,0,0,0,2,4000]
  p=decode_report(struct.pack('>16I',*good))["memory_test"]
  self.assertEqual(p["status"],"Checks passing");self.assertEqual(p["passes"],3)
  self.assertFalse(p["capture_available"])
  for flags,error,label in ((0,1,"Launcher grant unavailable"),(1,4,"Waiting for native ARAM space"),(19,7,"Memory pattern mismatch")):
   case=good.copy();case[4]=flags;case[5]=error
   self.assertEqual(decode_report(struct.pack('>16I',*case))["memory_test"]["status"],label)
  for index,value in ((4,32),(5,8),(6,0),(7,0),(8,0x240001),(9,0x230000),(14,3)):
   bad=good.copy();bad[index]=value
   with self.subTest(index=index),self.assertRaises(ValueError):decode_report(struct.pack('>16I',*bad))

 def test_wrong_peer_cannot_inject(self):
  h,g=self.connect()
  for ms in range(0,1000,10):self.pump(h,g,ms)
  self.assertEqual(h.receive(b'anything',('192.168.2.99',48222),1010),0)
  self.assertIsNone(h.report())

if __name__=='__main__':unittest.main()
