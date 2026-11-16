"""Exercise native library transactions using the real CARD job worker."""
from pathlib import Path
import ctypes as C
import os,subprocess,unittest
import test_dolphin_files
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test-dolphin-library'
class Response(C.Structure):
 _fields_=[('magic',C.c_uint),('version',C.c_ushort),('flags',C.c_ushort),('seq',C.c_uint),('status',C.c_int),('bytes',C.c_uint),('generation',C.c_uint),('slot',C.c_uint),('count',C.c_ushort),('profile',C.c_ushort)]
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  test_dolphin_files.Tests.setUpClass();OUT.mkdir(parents=True,exist_ok=True)
  source=(ROOT/'native/dolphin_https/library.cpp').read_text();source='\n'.join(l for l in source.splitlines() if not l.startswith('#include'))
  source=source.replace('NativeStorage::region','SUSAMUNE_GAME_VERSION')
  source=source.replace('Work &s=*reinterpret_cast<Work *>(DOLPHIN_LIBRARY_WORK_BASE);','Work s;')
  source=source.replace('reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE)','transfer')
  source=source.replace('reinterpret_cast<const DolphinWebApi *>(DOLPHIN_WEB_API_BASE)','&webApi')
  a=source.index('    const u32 address=reinterpret_cast<u32>(api->describe);');b=source.index('    if(s.header.fileSize',a);source=source[:a]+source[b:]
  base=(ROOT/'build/test-dolphin-files/fixture.cpp').read_text()
  base=base.replace('static int fault=0,','static int failWriteAt;\nstatic int fault=0,').replace('++writes;if(fault==2)','++writes;if(failWriteAt==writes || fault==2)')
  shim=r"""
#include "susamune/dolphin_ghost_library.hxx"
#include "susamune/dolphin_web_api.h"
#include "susamune/ghost_format.h"
static unsigned char transfer[SUSAMUNE_GHOST_MAX_FILE_SIZE];
static unsigned crc(const void *p,unsigned n){unsigned c=0xffffffff;const auto *b=(const unsigned char*)p;for(unsigned i=0;i<n;++i){c^=b[i];for(int j=0;j<8;++j)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}return c^0xffffffff;}
// Canonical parsing has separate byte-order/format tests; this dependency models checked input.
namespace Ghost{bool inspectFile(const void *p,u32 size,SusamuneGhostFileHeader *out){
 const auto &h=*(const SusamuneGhostFileHeader*)p;
 if(size<256 || h.magic!=SUSAMUNE_GHOST_FILE_MAGIC || h.fileSize!=size || h.payloadChecksum!=crc((const unsigned char*)p+256,size-256))return false;
 *out=h;return true;}}
static int describe(const void *p,unsigned bytes,unsigned profile,unsigned,int imported,SusamuneGhostSlotInfo *out){
 const auto &h=*(const SusamuneGhostFileHeader*)p;if(bytes<256 || h.magic!=SUSAMUNE_GHOST_FILE_MAGIC || (!imported && h.sourceProfile!=profile))return 0;
 memset(out,0,sizeof(*out));out->generation=h.fileChecksum;out->payloadSize=h.fileSize;out->durationQf=h.durationQf;
 out->flags=SUSAMUNE_GHOST_SLOT_PRESENT|(imported?SUSAMUNE_GHOST_SLOT_IMPORTED:0);return 1;}
static const DolphinWebApi webApi={DOLPHIN_WEB_API_MAGIC,3,sizeof(DolphinWebApi),nullptr,nullptr,nullptr,nullptr,describe,nullptr};
"""+source+r"""
static unsigned sequence;
extern "C" {
__declspec(dllexport) void libReset(){reset();DolphinGhostLibrary::initialized=false;sequence=0;failWriteAt=0;}
__declspec(dllexport) void restart(){DolphinGhostLibrary::initialized=false;}
__declspec(dllexport) void prepare(unsigned id,unsigned profile){
 memset(transfer,0,20000);auto &h=*(SusamuneGhostFileHeader*)transfer;h.magic=SUSAMUNE_GHOST_FILE_MAGIC;h.fileSize=20000;h.ghostIdLo=id;h.ghostIdHi=77;h.sourceProfile=profile;h.durationQf=100;
 for(unsigned i=256;i<20000;++i)transfer[i]=(i+id)%251;h.payloadChecksum=crc(transfer+256,20000-256);h.fileChecksum=h.payloadChecksum;}
__declspec(dllexport) int request(unsigned command,unsigned profile,unsigned slot,unsigned generation){
 SusamuneGhostStorageRequest r={};r.requestMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;r.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;r.requestSeq=++sequence;r.command=command;r.profile=profile;r.slot=slot;r.expectedGeneration=generation;r.payloadSize=command==1?20000:0;return DolphinGhostLibrary::begin(r);}
__declspec(dllexport) int run(SusamuneGhostStorageResponse *out){for(unsigned i=0;i<2000;++i){DolphinGhostLibrary::update();DolphinFiles::perform(sector);if(DolphinGhostLibrary::take(out))return i+1;}return 0;}
__declspec(dllexport) unsigned row(unsigned index,int field){auto &e=((SusamuneGhostCatalogPage*)transfer)->entries[index];return field?e.info.generation:e.id;}
__declspec(dllexport) unsigned total(){return ((SusamuneGhostCatalogPage*)transfer)->totalCount;}
__declspec(dllexport) unsigned fileCount(){unsigned n=0;for(const auto &f:files)if(f.used)++n;return n;}
__declspec(dllexport) unsigned diskHash(){unsigned c=0;for(const auto &f:files)if(f.used)c^=crc(f.data.data(),f.data.size());return c;}
__declspec(dllexport) void failWrite(unsigned after){failWriteAt=writes+after;}
__declspec(dllexport) void damage(unsigned index){files[index].data[500]^=1;}
}
"""
  (OUT/'fixture.cpp').write_text(base+'\n'+shim)
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++','-DTIMEWARP_LIVE_RACING=1','-I'+str(ROOT/'include'),str(OUT/'fixture.cpp'),'-o',str(OUT/'library.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-4000:])
  cls.lib=C.CDLL(str(OUT/'library.dll'))
  cls.lib.setApi.argtypes=[C.c_void_p];cls.lib.setApi(C.byref(test_dolphin_files.Tests.api))
 def setUp(self):self.lib.libReset()
 def request(self,command,profile=0,slot=0,generation=0):
  self.assertTrue(self.lib.request(command,profile,slot,generation));r=Response();self.assertTrue(self.lib.run(C.byref(r)));return r
 def save(self,id=1,profile=0):
  self.lib.prepare(id,profile);return self.request(1,profile,0xffffffff)
 def test_save_reopen_catalogue_load_delete(self):
  self.assertEqual(self.save().status,0);self.lib.restart();r=self.request(4);self.assertEqual((r.status,r.count,self.lib.total()),(0,1,1))
  index,gen=self.lib.row(0,0),self.lib.row(0,1)
  r=self.request(2,slot=index,generation=gen);self.assertEqual((r.status,r.bytes),(0,20000))
  self.assertEqual(self.request(3,slot=index,generation=gen).status,0);self.assertEqual(self.request(4).count,0)
 def test_duplicate_save_does_not_overwrite(self):
  self.assertEqual(self.save().status,0);before=self.lib.diskHash();self.assertEqual(self.save().status,-10);self.assertEqual(self.lib.diskHash(),before)
 def test_failed_write_removes_only_new_file(self):
  self.assertEqual(self.save().status,0);before=self.lib.diskHash();self.lib.failWrite(3)
  self.assertNotEqual(self.save(2).status,0);self.assertEqual(self.lib.fileCount(),1);self.assertEqual(self.lib.diskHash(),before)
 def test_stale_generation_cannot_load_or_delete(self):
  self.save();self.request(4);index=self.lib.row(0,0);gen=self.lib.row(0,1)
  self.assertNotEqual(self.request(2,slot=index,generation=gen^1).status,0)
  self.assertNotEqual(self.request(3,slot=index,generation=gen^1).status,0);self.assertEqual(self.lib.fileCount(),1)
 def test_profiles_and_paging_are_independent(self):
  for i in range(19):self.assertEqual(self.save(i+1,i%2).status,0)
  self.assertEqual(self.request(4,profile=0).count,10);self.assertEqual(self.request(4,profile=1).count,9)
  self.assertEqual(self.request(4,profile=0,slot=16).count,0)
 def test_body_damage_rejected_even_with_valid_catalogue_header(self):
  self.save();self.request(4);index,gen=self.lib.row(0,0),self.lib.row(0,1);self.lib.damage(index)
  self.assertEqual(self.request(2,slot=index,generation=gen).status,-4)
 def test_download_uses_same_checked_save_transaction(self):
  self.lib.prepare(5,0);r=self.request(1,profile=4,slot=0xffffffff)
  self.assertEqual(r.status,0);self.assertEqual(self.request(4,profile=4).count,1)
  before=self.lib.diskHash();self.lib.prepare(5,0)
  self.assertEqual(self.request(1,profile=4,slot=0xffffffff).status,-10)
  self.assertEqual(self.lib.diskHash(),before)
if __name__=='__main__':unittest.main()
