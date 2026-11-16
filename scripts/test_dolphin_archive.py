"""Native archives: real CARD jobs, durable IDs, payload verification and interruption."""
from pathlib import Path
import ctypes as C, subprocess, unittest
import test_dolphin_files
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test-dolphin-archive'
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  test_dolphin_files.Tests.setUpClass();OUT.mkdir(parents=True,exist_ok=True)
  base=(ROOT/'build/test-dolphin-files/fixture.cpp').read_text()
  source=(ROOT/'native/dolphin_https/archive.cpp').read_text().replace('#include "archive_tas.inc"',(ROOT/'native/dolphin_https/archive_tas.inc').read_text())
  source=source.replace('reinterpret_cast<SusamuneStateStorageMailbox *>(SUSAMUNE_DOLPHIN_STATE_STORAGE_PPC_BASE)','&box')
  source=source.replace('reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_SNAPSHOT_PPC_BASE)','pool')
  source=source.replace('reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE)','extra')
  source=source.replace('reinterpret_cast<unsigned char *>(SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE)','staging')
  shim=r"""
#include "susamune/dolphin_storage_api.hxx"
#include "susamune/state_storage.h"
static SusamuneStateStorageMailbox box;
static unsigned char pool[SUSAMUNE_STATE_POOL_SIZE],extra[SUSAMUNE_STATE_POOL_EXTRA_SIZE],staging[SUSAMUNE_STATE_STAGING_SIZE];
static unsigned seq;
extern "C" void MoonshineNativeInit(){}
static const DolphinStorageHost host={DolphinFiles::read,DolphinFiles::write,DolphinFiles::create,DolphinFiles::remove,DolphinFiles::take,
 nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,nullptr,DolphinFiles::list,nullptr};
"""+source+r"""
extern "C" {
__declspec(dllexport) void archiveReset(){reset();s={};seq=0;initialize(&host,1);}
__declspec(dllexport) void archiveRestart(){s={};DolphinFiles::initialized=false;DolphinFiles::init();initialize(&host,1);}
__declspec(dllexport) unsigned field(unsigned n){return n==0?box.response.status:n==1?box.response.resultId:n==2?box.header.headerCrc:n==3?box.catalog.count:n==4?box.catalog.nextId:n==5?box.catalog.more:n==6?s.phase:box.response.ackSeq;}
__declspec(dllexport) const char *resultName(){return box.resultName;}
__declspec(dllexport) void submit(unsigned command,unsigned id,unsigned crc,unsigned size,unsigned offset,unsigned window){box.request={++seq,command,id,77,offset,size,crc,window};box.tasRequest={};}
__declspec(dllexport) void prepare(unsigned size,unsigned offset){
 memset(pool,0,sizeof(pool));memset(extra,0,sizeof(extra));memset(staging,0,sizeof(staging));
 for(unsigned i=0;i<size;++i){unsigned char b=(i*13+17)&255;StatePoolMemoryCopyIn(&s.memory,offset+i,&b,1);}
 auto &h=box.header;h={};h.magic=SUSAMUNE_STATE_ARCHIVE_MAGIC;h.version=1;h.headerSize=sizeof(h);h.metadataSize=128;h.packedSize=size;h.rawSize=size;h.gameId=s.game;h.configId=s.config;h.buildCrc=123;h.snapshotVersion=7;h.sceneKey=0x102;
 strcpy(h.name,"Practice");memset(box.metadata,0x73,h.metadataSize);h.metadataCrc=SusamuneStateCrc(box.metadata,h.metadataSize);h.headerCrc=SusamuneStateHeaderCrc(&h);
}
__declspec(dllexport) void setName(const char *n){memset(box.requestName,0,32);strncpy(box.requestName,n,31);}
__declspec(dllexport) int archiveStep(){update();DolphinFiles::perform(sector);return box.response.ackSeq==box.request.seq;}
__declspec(dllexport) int payload(unsigned size,unsigned offset){for(unsigned i=0;i<size;++i){unsigned char b;if(i<sizeof(staging))b=staging[i];else StatePoolMemoryCopyOut(&s.memory,offset+i-sizeof(staging),&b,1);if(b!=((i*13+17)&255))return 0;}return 1;}
__declspec(dllexport) void corrupt(unsigned id,unsigned offset){char n[32];filename(id,n);for(auto &f:files)if(f.used&&!strcmp(f.entry.mFilename,n))f.data[offset]^=1;}
__declspec(dllexport) void forgetCounter(){for(auto &f:files)if(f.used&&!strcmp(f.entry.mFilename,kCounters))f.used=false;}
__declspec(dllexport) void corruptCounter(){for(auto &f:files)if(f.used&&!strcmp(f.entry.mFilename,kCounters))f.data[s.counterBank*8192+4]^=1;}
__declspec(dllexport) void stopAtPayload(){for(unsigned i=0;i<3000&&s.phase!=PAYLOAD;++i){update();DolphinFiles::perform(sector);}}

static SusamuneTasManifest testProject;
__declspec(dllexport) void newProject(unsigned id){testProject={};auto &p=testProject;p.magic=SUSAMUNE_TAS_MAGIC;p.version=SUSAMUNE_TAS_VERSION;p.projectId=id;p.gameId=s.game;p.buildCrc=123;p.configId=s.config;p.sceneKey=0x102;p.startKey[0]=7;strcpy(p.name,"My TAS");}
__declspec(dllexport) void exportPart(unsigned role,unsigned generation,unsigned checksum){
 prepare(1000,0);
 if(role==3){auto &h=box.header;h.snapshotVersion=SUSAMUNE_TAS_TAPE_SNAPSHOT;h.metadataSize=sizeof(SusamuneTasTakeData);h.packedSize=h.rawSize=20;
 auto &t=*reinterpret_cast<SusamuneTasTakeData *>(box.metadata);t={};t.version=1;t.frames=1;t.startScene=0x102;t.originKey[0]=7;
 memset(staging,0,20);h.metadataCrc=SusamuneStateCrc(&t,sizeof(t));h.headerCrc=SusamuneStateHeaderCrc(&h);}
 submit(1,0,0,box.header.packedSize,0,0);auto &c=box.tasRequest;c.projectId=testProject.projectId;c.role=role;c.projectGeneration=generation;c.expectedProjectCrc=checksum;c.checksum=SusamuneTasRequestCrc(&c);
}
__declspec(dllexport) void addPart(unsigned role){auto &h=box.header;if(role==3){testProject.tape={box.response.resultId,h.headerCrc,h.packedSize};testProject.tapeFrames=1;}
 else{if(!testProject.components[role].componentId)++testProject.componentCount;testProject.components[role]={box.response.resultId,h.headerCrc,h.packedSize,role?1u:0u,h.sceneKey};}}
__declspec(dllexport) void commitProject(unsigned generation,unsigned previous){testProject.generation=generation;testProject.checksum=SusamuneTasManifestCrc(&testProject);box.tasProject=testProject;submit(10,testProject.projectId,previous,0,0,0);}
__declspec(dllexport) unsigned projectField(unsigned n){return n==0?box.tasProject.checksum:n==1?box.tasProject.generation:box.tasProject.components[0].componentId;}
__declspec(dllexport) void importPart(unsigned role){auto &p=box.tasProject;unsigned id=role==3?p.tape.componentId:p.components[role].componentId;unsigned crc=role==3?p.tape.headerCrc:p.components[role].headerCrc;unsigned size=role==3?p.tape.packedBytes:p.components[role].packedBytes;
 submit(2,id,crc,size,0,0);auto &c=box.tasRequest;c.projectId=p.projectId;c.componentId=id;c.projectGeneration=p.generation;c.role=role;c.expectedProjectCrc=p.checksum;c.checksum=SusamuneTasRequestCrc(&c);}
__declspec(dllexport) void corruptPart(unsigned role){char n[32];partName(testProject.projectId,partId(testProject,role),n);for(auto &f:files)if(f.used&&!strcmp(f.entry.mFilename,n))f.data[96]^=1;}
__declspec(dllexport) void corruptLatestProject(){char n[32];projectName(testProject.projectId,n);for(auto &f:files)if(f.used&&!strcmp(f.entry.mFilename,n))f.data[(1-s.projectBank)*8192+16]^=1;}
__declspec(dllexport) unsigned projectFiles(){unsigned n=0;for(auto &f:files)if(f.used&&!memcmp(f.entry.mFilename,"ms_t",4) && memcmp(f.entry.mFilename,"ms_tls",6))++n;return n;}
__declspec(dllexport) unsigned archives(){unsigned n=0;for(auto &f:files)if(f.used&&fileId(f.entry.mFilename))++n;return n;}
}
"""
  (OUT/'fixture.cpp').write_text(base+'\n'+shim)
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++','-I'+str(ROOT/'include'),str(OUT/'fixture.cpp'),'-o',str(OUT/'archive.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-6000:])
  cls.lib=C.CDLL(str(OUT/'archive.dll'));cls.lib.resultName.restype=C.c_char_p;cls.lib.setName.argtypes=[C.c_char_p]
 def setUp(self):self.lib.archiveReset()
 def finish(self):
  for _ in range(10000):
   if self.lib.archiveStep():return self.lib.field(0)
  self.fail('archive worker stalled in phase '+str(self.lib.field(6)))
 def request(self,cmd,id=0,crc=0,size=0,offset=0,window=0):
  self.lib.submit(cmd,id,crc,size,offset,window);return self.finish()
 def export(self,size=40000,offset=0):
  self.lib.prepare(size,offset);self.assertEqual(self.request(1,size=size,offset=offset),0);return self.lib.field(1),self.lib.field(2)
 def test_restart_import_full_payload_metadata_and_name(self):
  id,crc=self.export();self.lib.archiveRestart();self.assertEqual(self.request(3),0);self.assertEqual(self.lib.field(3),1)
  self.assertEqual(self.request(2,id,crc,40000),0);self.assertTrue(self.lib.payload(40000,0));self.assertEqual(self.lib.resultName(),b'Practice')
 def test_window_and_payload_corruption(self):
  id,crc=self.export();self.assertEqual(self.request(7,id,crc,40000,100,8000),0)
  self.lib.corrupt(id,96+128+9000);self.assertEqual(self.request(2,id,crc,40000),3)
 def test_staging_tail_and_split_source_banks(self):
  for size,offset in ((4200000,0),(40000,0x1000000-20000)):
   self.lib.archiveReset();id,crc=self.export(size,offset);self.assertEqual(self.request(2,id,crc,size,222),0);self.assertTrue(self.lib.payload(size,222))
 def test_rename_identity_and_delete_do_not_reuse_ids(self):
  id,crc=self.export();self.lib.setName(b'Renamed');self.assertEqual(self.request(5,id,crc),0);self.assertEqual(self.lib.resultName(),b'Renamed')
  self.assertEqual(self.request(6,id,crc^1),7);self.assertEqual(self.request(6,id,crc),0);self.lib.archiveRestart();nextid,_=self.export();self.assertGreater(nextid,id)
 def test_cancel_during_new_file_removes_only_partial(self):
  self.export();self.lib.prepare(40000,0);self.lib.submit(1,0,0,40000,0,0);self.lib.stopAtPayload();self.assertEqual(self.request(4),6);self.assertEqual(self.lib.archives(),1)
 def test_failed_payload_is_not_published(self):
  self.export();self.lib.prepare(40000,0);self.lib.submit(1,0,0,40000,0,0);self.lib.stopAtPayload();self.lib.setFault(2);self.assertEqual(self.finish(),2);self.assertEqual(self.lib.archives(),1)
 def test_damaged_latest_id_journal_fails_closed(self):
  self.export();self.export();self.lib.corruptCounter();self.lib.archiveRestart();self.lib.prepare(100,0);self.assertEqual(self.request(1,size=100),3)
 def test_catalog_paging(self):
  for i in range(10):self.export(100)
  self.assertEqual(self.request(3),0);self.assertEqual(self.lib.field(3),8);last=self.lib.field(4);self.assertEqual(self.lib.field(5),1)
  self.assertEqual(self.request(3,last),0);self.assertEqual(self.lib.field(3),2);self.assertEqual(self.lib.field(5),0)
 def test_wrong_size_or_stale_identity_cannot_import(self):
  id,crc=self.export();self.assertEqual(self.request(2,id,crc,40001),7);self.assertEqual(self.request(2,id,crc^1,40000),7)
 def project(self):
  self.lib.setName(b'My TAS');self.assertEqual(self.request(8),0);id=self.lib.field(1);self.lib.newProject(id)
  for role in (0,3):
   self.lib.exportPart(role,0,0);self.assertEqual(self.finish(),0);self.lib.addPart(role)
  self.lib.commitProject(1,0);self.assertEqual(self.finish(),0);return id,self.lib.projectField(0)
 def test_imported_project_reserves_component_ids_without_local_journal(self):
  self.project();self.lib.forgetCounter();self.lib.archiveRestart();id,crc=self.export();self.assertEqual(id,3)
 def test_project_commit_restart_read_and_tape_import(self):
  id,crc=self.project();self.lib.archiveRestart();self.assertEqual(self.request(11),0);self.assertEqual(self.lib.field(3),1)
  self.assertEqual(self.request(9,id,crc),0);self.assertEqual(self.lib.projectField(1),1)
  self.lib.importPart(0);self.assertEqual(self.finish(),0);self.assertTrue(self.lib.payload(1000,0))
  self.lib.importPart(3);self.assertEqual(self.finish(),0)
 def test_corrupt_component_cannot_replace_committed_project(self):
  id,crc=self.project();self.lib.exportPart(0,1,crc);self.assertEqual(self.finish(),0);self.lib.addPart(0);self.lib.corruptPart(0)
  self.lib.commitProject(2,crc);self.assertEqual(self.finish(),3)
  self.lib.archiveRestart();self.assertEqual(self.request(9,id,crc),0);self.assertEqual(self.lib.projectField(1),1)
 def test_project_stale_export_and_commit(self):
  id,crc=self.project();self.lib.exportPart(0,0,0);self.assertEqual(self.finish(),7)
  self.lib.commitProject(2,crc^1);self.assertEqual(self.finish(),7)
 def test_project_rename_and_delete_keeps_unrelated_state(self):
  self.export();id,crc=self.project();self.lib.setName(b'TAS renamed');self.assertEqual(self.request(12,id,crc),0);newcrc=self.lib.projectField(0)
  self.assertEqual(self.lib.projectField(1),2);self.assertEqual(self.request(13,id,newcrc),0);self.assertEqual(self.lib.projectFiles(),0);self.assertEqual(self.lib.archives(),1)
 def test_project_failed_commit_preserves_previous(self):
  id,crc=self.project();self.lib.setName(b'Failed rename');self.lib.setFault(2);self.assertEqual(self.request(12,id,crc),2)
  self.lib.setFault(0);self.lib.archiveRestart();self.assertEqual(self.request(9,id,crc),0)
 def test_corrupt_new_manifest_falls_back_to_complete_previous(self):
  id,crc=self.project();self.lib.setName(b'New');self.assertEqual(self.request(12,id,crc),0);self.lib.corruptLatestProject();self.lib.archiveRestart()
  self.assertEqual(self.request(9,id,crc),0);self.assertEqual(self.lib.projectField(1),1)
if __name__=='__main__':unittest.main()
