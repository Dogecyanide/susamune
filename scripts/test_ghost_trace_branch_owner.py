"""The shared trace mailbox retains its reply until the exact client consumes it."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
#include "susamune/ghost_trace_branch_io.hxx"
#include "susamune/ghost_trace_branch_owner.hxx"
namespace M=GhostTraceBranchIo;
static MsTraceBranchMailbox box;
static MsTraceLookup result;
static M::Client a,b;
static void flush(void*,const void*,unsigned){}
static void invalidate(void*,void*,unsigned){}
static void ack(M::Client&c){
 box.response={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,c.nonce,c.sequence,0,{0,0,0}};
 result={};result.file={3,0x474d534a,0x200,0,96,0,17,18};
 result.bootNonce=c.nonce;result.sequence=c.sequence;result.nonce=c.fileNonce;result.run=c.run;
}
#define API extern "C" __declspec(dllexport)
API int check(unsigned test){
 GhostTraceBranchOwner::state={};box={};result={};a={};b={};
 box.response={MS_TRACE_BRANCH_MAGIC,MS_TRACE_BRANCH_VERSION,7,0,0,{0,0,0}};
 M::Hooks h={nullptr,&box,&result,flush,invalidate};
 if(!M::configure(a,h,7)||!M::configure(b,h,7)||!M::lookup(a,1,2,0x474d534a))return 1;
 ack(a);
 if(test==0){
  if(M::lookup(b,1,3,0x474d534a))return 2;
  if(M::poll(a)!=M::READY||M::lookup(b,1,3,0x474d534a))return 3;
  if(!M::result(a)||M::result(a)->run!=2||!M::consume(a))return 4;
  return M::lookup(b,1,3,0x474d534a)?0:5;
 }
 if(test==1){
  if(M::poll(a)!=M::READY||!M::consume(a)||!M::erase(b,1,2,17))return 6;
  if(!M::cancel(a)||GhostTraceBranchOwner::claim(&box,7,&a))return 7;
  if(M::cancel(b))return 8;
  ack(b);if(!M::cancel(b))return 9;
  return GhostTraceBranchOwner::claim(&box,7,&a)?0:10;
 }
 box.response.bootNonce=8;M::Client next={};
 if(!M::configure(next,h,8)||!M::lookup(next,1,3,0x474d534a))return 11;
 if(M::cancel(a)||GhostTraceBranchOwner::state.owner!=&next)return 12;
 return 0;
}
'''
class OwnerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-owner-');cls.addClassCleanup(cls.temp.cleanup);p=Path(cls.temp.name)
  (p/'fixture.cpp').write_text(FIXTURE)
  subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2','-I',str(ROOT/'include'),str(p/'fixture.cpp'),str(ROOT/'src/ghost_trace_branch_io.cpp'),'-o',str(p/'fixture.dll')],check=True,env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH']))
  cls.lib=C.CDLL(str(p/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_acknowledged_lookup_cannot_be_overwritten_before_consumption(self):self.assertEqual(self.lib.check(0),0)
 def test_cancel_retains_ownership_until_the_matching_receipt(self):self.assertEqual(self.lib.check(1),0)
 def test_verified_new_boot_invalidates_old_owner_without_aba_release(self):self.assertEqual(self.lib.check(2),0)
if __name__=='__main__':unittest.main()
