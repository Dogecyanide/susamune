"""Exercise native CARD file jobs and audited deletion against a fault-injectable card."""
from pathlib import Path
import ctypes as C
import os,re,struct,hashlib,hmac,subprocess,unittest
import test_dolphin_https
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test-dolphin-files'
class Result(C.Structure):_fields_=[('error',C.c_int32),('bytes',C.c_uint32)]
class Entry(C.Structure):_fields_=[('name',C.c_char*32),('bytes',C.c_uint32),('index',C.c_uint32)]

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUT.mkdir(parents=True,exist_ok=True)
  os.environ['PATH']='C:/msys64/mingw64/bin'+os.pathsep+os.environ.get('PATH','')
  source=(ROOT/'src/dolphin_files.cpp').read_text()
  source='\n'.join(l for l in source.splitlines() if not l.startswith('#include'))
  source=source.replace('Work &s=*reinterpret_cast<Work *>(kBase);','Work s;')
  entropy=(ROOT/'native/dolphin_https/entropy.cpp').read_text()
  entropy=entropy[entropy.index('namespace DolphinEntropy {'):len(entropy)]
  entropy=entropy.replace('NativeStorage::region','SUSAMUNE_GAME_VERSION')
  entropy=entropy.replace('Work &s=*reinterpret_cast<Work *>(DOLPHIN_ENTROPY_WORK_BASE);','Work s;')
  deletion=(ROOT/'src/dolphin_card.cpp').read_text()
  deletion=deletion[deletion.index('s32 remove(const char *name)'):]
  deletion=deletion[:deletion.rindex('#endif')]
  shim=r"""
#include <cstring>
#include <vector>
#include <algorithm>
#include "Dolphin/CARD.h"
#include "susamune/dolphin_files.hxx"
#include "susamune/dolphin_https.h"
#include "susamune/ghost_service.h"
static const DolphinHttpsApi *httpsApi;
namespace DolphinHttps {const DolphinHttpsApi *api(){return httpsApi;}}
#define IS_EMULATOR 1
#define SUSAMUNE_GAME_VERSION 1
struct File { CARDDirEntry entry;std::vector<unsigned char> data;bool used=false; };
static File files[127];
static int fault=0,reads=0,writes=0,scanned=0,reclaimed=0,locked=0,published=0,waited=0;
static alignas(32) unsigned char sector[8192];
static CARDDirEntry directoryCopy[127];
static bool own(const File &f){return f.entry.mGameCode==0x474d534a && f.entry.mCompany==0x5355;}
extern "C" {
s32 CARDOpen(s32,const char *name,CARDFileInfo *f){
 for(int i=0;i<127;++i)if(files[i].used && own(files[i]) && !strcmp(files[i].entry.mFilename,name)){
  f->mChannel=1;f->mFileNo=i;f->mOffset=0;f->mLength=-999;return 0;}
 return -4;
}
s32 CARDClose(CARDFileInfo *f){f->mChannel=-1;return 0;}
s32 CARDCreate(s32 c,const char *name,s32 size,CARDFileInfo *f){
 CARDFileInfo check;if(!CARDOpen(c,name,&check))return -7;
 for(int i=0;i<127;++i)if(!files[i].used){files[i].used=true;files[i].entry={};
  files[i].entry.mGameCode=0x474d534a;files[i].entry.mCompany=0x5355;
  strcpy(files[i].entry.mFilename,name);files[i].data.assign(size,0xa5);return CARDOpen(c,name,f);}
 return -8;
}
s32 CARDGetStatus(s32,s32 index,CARDStat *out){
 ++scanned;if(index<0 || index>=127)return -128;
 const auto &f=files[index];if(!f.used)return -4;if(!own(f))return -10;
 memset(out,0,sizeof(*out));memcpy(out->mFilename,f.entry.mFilename,32);
 out->mLength=f.data.size();out->mGameCode=f.entry.mGameCode;out->mCompany=f.entry.mCompany;return 0;
}
s32 CARDRead(CARDFileInfo *f,void *out,u32 size,u32 offset){
 ++reads;if(fault==1)return -5;
 auto &v=files[f->mFileNo].data;if(size!=8192 || offset+size>v.size())return -11;
 memcpy(out,v.data()+offset,size);f->mLength=size;return 0;
}
s32 CARDWrite(CARDFileInfo *f,void *in,u32 size,u32 offset){
 ++writes;if(fault==2)return -5;
 auto &v=files[f->mFileNo].data;if(size!=8192 || offset+size>v.size())return -11;
 memcpy(v.data()+offset,in,size);f->mLength=size;return 0;
}
s32 CARDCheck(s32){++reclaimed;return fault==5?-5:0;}
}
namespace DolphinCard {
static s32 acquire(void **p){locked=1;*p=files;for(int i=0;i<127;++i)directoryCopy[i]=files[i].entry;return 0;}
static s32 release(void *,s32 r){locked=0;return r;}
static CARDDirEntry *directory(void *){return directoryCopy;}
static s32 publish(){++published;if(fault==3)return -5;for(int i=0;i<127;++i){files[i].entry=directoryCopy[i];if(directoryCopy[i].mGameCode==0xffffffff)files[i].used=false;}return 0;}
static s32 wait(){++waited;locked=0;return fault==4?-5:0;}
"""+deletion+source+'\n'+entropy+r"""
extern "C" {
__declspec(dllexport) void reset(){for(auto &f:files)f=File{};fault=reads=writes=scanned=reclaimed=locked=published=waited=0;DolphinFiles::initialized=false;DolphinFiles::init();DolphinEntropy::initialized=false;}
__declspec(dllexport) unsigned create(const char *n,unsigned size){return DolphinFiles::create(n,size);}
__declspec(dllexport) unsigned read(const char *n,void *p,unsigned size,unsigned off){return DolphinFiles::read(n,p,size,off);}
__declspec(dllexport) unsigned write(const char *n,void *p,unsigned size,unsigned off){return DolphinFiles::write(n,p,size,off);}
__declspec(dllexport) unsigned list(void *p,unsigned size){return DolphinFiles::list((DolphinFiles::Entry *)p,size);}
__declspec(dllexport) unsigned remove(const char *n){return DolphinFiles::remove(n);}
__declspec(dllexport) int take(unsigned ticket,DolphinFiles::Result *r){return DolphinFiles::take(ticket,r);}
__declspec(dllexport) int pending(){return DolphinFiles::pending();}
__declspec(dllexport) void step(){DolphinFiles::perform(sector);}
__declspec(dllexport) void setApi(const DolphinHttpsApi *p){httpsApi=p;}
__declspec(dllexport) int entropyBegin(){return DolphinEntropy::begin();}
__declspec(dllexport) void entropyStep(){DolphinEntropy::update();}
__declspec(dllexport) int entropyTake(void *p){return DolphinEntropy::take(p);}
__declspec(dllexport) void setFault(int f){fault=f;}
__declspec(dllexport) int count(int which){return which==0?reads:which==1?writes:which==2?scanned:which==3?reclaimed:which==4?published:which==5?waited:locked;}
__declspec(dllexport) void seed(int index,int foreign,unsigned bytes){auto &f=files[index];f.used=true;f.entry={};f.entry.mGameCode=foreign?0x474d5345:0x474d534a;f.entry.mCompany=0x5355;strcpy(f.entry.mFilename,"ms_seed");f.data.assign(bytes,0x3c);}
}
"""
  # Standard host syntax; production's sector uses the game's existing aligned buffer.
  shim=shim.replace('static alignas(32)','alignas(32) static')
  (OUT/'fixture.cpp').write_text(shim)
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++','-I'+str(ROOT/'include'),str(OUT/'fixture.cpp'),'-o',str(OUT/'files.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.dll_dir=os.add_dll_directory('C:/msys64/mingw64/bin')
  cls.lib=C.CDLL(str(OUT/'files.dll'))
  for n in ('create','remove'):getattr(cls.lib,n).argtypes=[C.c_char_p]+([C.c_uint] if n=='create' else [])
  for n in ('read','write'):getattr(cls.lib,n).argtypes=[C.c_char_p,C.c_void_p,C.c_uint,C.c_uint]
  cls.api=test_dolphin_https.build();cls.lib.setApi.argtypes=[C.c_void_p];cls.lib.setApi(C.byref(cls.api))
  cls.lib.entropyTake.argtypes=[C.c_void_p]
  cls.lib.list.argtypes=[C.c_void_p,C.c_uint];cls.lib.take.argtypes=[C.c_uint,C.POINTER(Result)]
 def setUp(self):self.lib.reset()
 def finish(self,ticket):
  self.assertGreater(ticket,0)
  for i in range(4096):
   if not self.lib.pending():break
   self.lib.step()
  self.assertFalse(self.lib.pending());r=Result();self.assertEqual(self.lib.take(ticket,C.byref(r)),1);return r
 def create(self,name=b'ms_test',size=16384):self.assertEqual(self.finish(self.lib.create(name,size)).error,0)
 def test_bounds_names_and_busy_ownership(self):
  for n in (b'',b'm',b'ms_',b'../save',b'ms_A',b'ms_'+b'a'*29):self.assertEqual(self.lib.create(n,8192),0)
  for size in (0,8191,16777217):self.assertEqual(self.lib.create(b'ms_test',size),0)
  ticket=self.lib.create(b'ms_test',8192);self.assertEqual(self.lib.create(b'ms_other',8192),0)
  self.lib.step();r=Result();self.assertEqual(self.lib.take(ticket+1,C.byref(r)),0)
  self.assertEqual(self.lib.create(b'ms_other',8192),0);self.assertEqual(self.lib.take(ticket,C.byref(r)),1)
  self.assertEqual(self.lib.take(ticket,C.byref(r)),0)
 def test_partial_cross_sector_write_preserves_surroundings(self):
  self.create();data=C.create_string_buffer(b'hello moonshine')
  r=self.finish(self.lib.write(b'ms_test',data,15,8187));self.assertEqual((r.error,r.bytes),(0,15))
  out=C.create_string_buffer(16384);r=self.finish(self.lib.read(b'ms_test',out,16384,0))
  self.assertEqual((r.error,r.bytes),(0,16384));self.assertEqual(out.raw,b'\xa5'*8187+b'hello moonshine'+b'\xa5'*(16384-8202))
 def test_full_sector_write_avoids_read_and_fileinfo_length_is_not_file_size(self):
  self.create();out=C.create_string_buffer(b'x'*8192)
  self.assertEqual(self.finish(self.lib.write(b'ms_test',out,8192,8192)).error,0)
  self.assertEqual(self.lib.count(0),0)
  self.assertEqual(self.finish(self.lib.read(b'ms_test',out,8192,8192)).error,0)
  self.assertEqual(out.raw[:8192],b'x'*8192)
 def test_directory_skips_foreign_files_and_stops_at_127(self):
  self.lib.seed(0,1,8192);self.lib.seed(126,0,8192);out=(Entry*127)()
  r=self.finish(self.lib.list(out,127));self.assertEqual((r.error,r.bytes),(0,1))
  self.assertEqual((out[0].name,out[0].index),(b'ms_seed',126));self.assertEqual(self.lib.count(2),127)
 def test_io_error_bounds_and_malformed_lengths(self):
  self.create();data=C.create_string_buffer(16)
  self.assertEqual(self.finish(self.lib.read(b'ms_test',data,16,16380)).error,-11)
  self.lib.setFault(1);self.assertEqual(self.finish(self.lib.read(b'ms_test',data,16,0)).error,-5)
  self.lib.reset();self.lib.seed(0,0,9000)
  self.assertEqual(self.finish(self.lib.read(b'ms_seed',data,16,0)).error,-11)
 def test_delete_publishes_directory_before_reclaim_and_preserves_other_files(self):
  self.create();self.create(b'ms_other');r=self.finish(self.lib.remove(b'ms_test'));self.assertEqual(r.error,0)
  self.assertEqual([self.lib.count(i) for i in (3,4,5,6)],[1,1,1,0])
  out=C.create_string_buffer(8);self.assertEqual(self.finish(self.lib.read(b'ms_test',out,8,0)).error,-4)
  self.assertEqual(self.finish(self.lib.read(b'ms_other',out,8,0)).error,0)
 def test_delete_failures_do_not_free_blocks_before_commit(self):
  for failure in (3,4):
   self.lib.reset();self.create();self.lib.setFault(failure)
   self.assertEqual(self.finish(self.lib.remove(b'ms_test')).error,-5)
   self.assertEqual(self.lib.count(3),0);self.assertEqual(self.lib.count(6),0)
 def setupEntropy(self):
  self.create(b'ms_tls_seed');seed=bytes(range(32));new=hmac.digest(seed,b'Moonshine Dolphin seed v1','sha256')
  for i,value in enumerate((seed,new)):
   header=struct.pack('<4I',0x4d535345,1,i+1,1)+value
   record=header+hashlib.sha256(header).digest()[:16]
   data=C.create_string_buffer(record);self.assertEqual(self.finish(self.lib.write(b'ms_tls_seed',data,64,i*8192)).error,0)
  return new
 def runEntropy(self):
  self.assertEqual(self.lib.entropyBegin(),1);out=C.create_string_buffer(32)
  for i in range(100):
   self.lib.entropyStep()
   result=self.lib.entropyTake(out)
   if result!=1:return result,out.raw
   self.lib.step()
  self.fail('entropy operation did not complete')
 def test_entropy_commits_next_seed_before_exposing_randomness(self):
  seed=self.setupEntropy();result,value=self.runEntropy();self.assertEqual(result,0)
  self.assertEqual(value,hmac.digest(seed,b'Moonshine Dolphin TLS v1','sha256'))
  seed=hmac.digest(seed,b'Moonshine Dolphin seed v1','sha256')
  self.lib.setApi(C.byref(self.api));result,value=self.runEntropy();self.assertEqual(result,0)
  self.assertEqual(value,hmac.digest(seed,b'Moonshine Dolphin TLS v1','sha256'))
 def test_entropy_rejects_damaged_copy_and_failed_commit(self):
  for corrupt in (False,True):
   self.lib.reset();self.setupEntropy()
   if corrupt:
    data=C.create_string_buffer(b'x');self.finish(self.lib.write(b'ms_tls_seed',data,1,0))
   else:self.lib.setFault(2)
   result,value=self.runEntropy();self.assertEqual(result,-23);self.assertEqual(value,bytes(32))
 def test_entropy_waits_for_readback_verification(self):
  self.setupEntropy();self.assertEqual(self.lib.entropyBegin(),1);out=C.create_string_buffer(32)
  writes=self.lib.count(1)
  for i in range(20):
   self.lib.entropyStep();self.assertEqual(self.lib.entropyTake(out),1);self.lib.step()
   if self.lib.count(1)>writes:break
  self.lib.setFault(1)
  for i in range(10):
   self.lib.entropyStep();result=self.lib.entropyTake(out)
   if result!=1:break
   self.lib.step()
  self.assertEqual(result,-23);self.assertEqual(out.raw,bytes(32))
 def test_regional_internal_addresses_match_retail_maps(self):
  text=(ROOT/'src/dolphin_card.cpp').read_text()
  symbols={'Get':'__CARDGetControlBlock','Put':'__CARDPutControlBlock','Dir':'__CARDGetDirBlock','Update':'__CARDUpdateDir','Sync':'__CARDSync','Callback':'__CARDSyncCallback'}
  sections=re.findall(r'constexpr u32 (.*?);',text,re.S)
  for region,section in zip(('jp','us','pal'),sections):
   table=(ROOT/'maps'/f'{region}.map').read_text()
   for short,symbol in symbols.items():
    address=int(re.search(r'k'+short+r'=(0x[0-9a-f]+)',section)[1],16)
    actual=int(re.search(r'^\s+[0-9a-f]{8}\s+[0-9a-f]{6}\s+([0-9a-f]{8})\s+4 '+symbol+r'\s',table,re.M)[1],16)
    self.assertEqual(address,actual)
if __name__=='__main__':unittest.main()
