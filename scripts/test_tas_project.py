"""Run the production TAS coordinator against bounded memory and SD fakes."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TasProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / "tas.cpp"
        source.write_text(r"""
#include "susamune/savestate.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/state_storage.hxx"
extern "C" void *memcpy(void*d,const void*s,size_t n){for(size_t i=0;i<n;++i)((volatile u8*)d)[i]=((const u8*)s)[i];return d;}
extern "C" void *memset(void*d,u32 v,size_t n){for(size_t i=0;i<n;++i)((volatile u8*)d)[i]=(u8)v;return d;}
struct SavedFile {PracticeSession::SavestateData data;SusamuneStateArchiveHeader header;};
static SavedFile fileData[32];
static SavestateManager::SlotInfo memory[3];
static PracticeSession::SavestateData stateData[3];
static SavestateManager::TransferResult transfer;
static StateStorage::Result response;
static SusamuneTasManifest published;
static SusamuneStateCatalog catalogData;
static bool transferReady,responseReady,tapeAttached,tapeRecord,tapePause,saveFails,compatible,canStart,readyCheckpoint;
static u32 nextGeneration,exportCount,commitCount,importCount,loadCount,clearCount,failExport,liveFrames,liveKey[2],liveRevision,lastLoaded;
static u32 ordinarySave=2,ordinaryLoad=1;
static const char*runtimeStatus="fixture practice status";
SavestateManager::SavestateManager(){}
static SavestateManager manager;
SavestateManager*gSavestateMgr=&manager;
SavestateManager::SlotInfo SavestateManager::slotInfo(u32 slot)const{return slot<3?memory[slot]:SlotInfo{};}
bool SavestateManager::practiceData(u32 slot,PracticeSession::SavestateData*out)const{if(slot>=3||!memory[slot].valid)return false;*out=stateData[slot];return true;}
bool SavestateManager::diskBusy(){return false;}
const char*SavestateManager::sdStatus()const{return "fake transfer refusal";}
bool SavestateManager::projectCompatible(const SusamuneTasManifest&)const{return compatible;}
bool SavestateManager::saveSlotExplicit(u32 slot,bool rng,bool omit){
 if(saveFails||slot>=3)return false;
 memory[slot]={true,2,0,++nextGeneration,6000};stateData[slot]={};auto&d=stateData[slot];
 d.flags=1|(rng?2:0)|(!omit&&tapeAttached?4:0);d.stateKey[1]=nextGeneration;
 if(d.flags&4){d.frames=liveFrames;d.originKey[0]=liveKey[0];d.originKey[1]=liveKey[1];}return true;
}
bool SavestateManager::clearSlot(u32 slot,u32 gen){if(slot>=3||memory[slot].generation!=gen)return false;memory[slot].valid=false;memory[slot].generation=++nextGeneration;++clearCount;return true;}
bool SavestateManager::exportSlotExplicit(u32 slot,u32 gen,const SusamuneTasRequest*request){
 if(!SusamuneTasRequestValid(request)||!memory[slot].valid||memory[slot].generation!=gen)return false;
 const u32 id=++exportCount;transfer={};transfer.command=SUSAMUNE_STATE_CMD_EXPORT;transfer.id=id;transfer.slot=slot;transfer.generation=gen;
 transfer.status=id==failExport?SUSAMUNE_STATE_IO_ERROR:SUSAMUNE_STATE_OK;
 transfer.header.gameId=0x474D5350;transfer.header.buildCrc=10;transfer.header.configId=20;transfer.header.sceneKey=0x2000000;
 transfer.header.headerCrc=id*11;transfer.header.packedSize=memory[slot].packedBytes;
 fileData[id]={stateData[slot],transfer.header};transferReady=true;return true;
}
bool SavestateManager::importSlotExplicit(u32 slot,u32 gen,u32 id,u32 crc,u32 packed,const SusamuneTasRequest*request,const SusamuneTasManifest*manifest){
 if(!SusamuneTasRequestValid(request)||slot>=3||memory[slot].generation!=gen||id>=32||fileData[id].header.headerCrc!=crc)return false;
 ++importCount;transfer={};transfer.command=SUSAMUNE_STATE_CMD_IMPORT;transfer.id=id;transfer.slot=slot;transfer.header=fileData[id].header;
 const auto &data=fileData[id].data;
 const bool semantic=(data.flags&3)==3 && data.frames==manifest->components[request->role].frames &&
  (request->role ? ((data.flags&4)&&data.originKey[0]==manifest->startKey[0]&&data.originKey[1]==manifest->startKey[1]) :
   (!(data.flags&4)&&data.stateKey[0]==manifest->startKey[0]&&data.stateKey[1]==manifest->startKey[1]));
 if(!semantic){transfer.status=SUSAMUNE_STATE_BAD_FILE;transferReady=true;return true;}
 // Model the full-pool staging refusal unless a destination is already free.
 bool full=true;for(u32 i=0;i<3;++i)full=full&&memory[i].valid;
 if(full){transfer.status=SUSAMUNE_STATE_FULL;}else{
 memory[slot]={true,2,0,++nextGeneration,packed};stateData[slot]=fileData[id].data;transfer.generation=nextGeneration;
 }transferReady=true;return true;
}
bool SavestateManager::takeTransferResult(TransferResult&out){if(!transferReady)return false;out=transfer;transferReady=false;return true;}
bool SavestateManager::loadSlot(u32 slot,u32 gen){if(!memory[slot].valid||memory[slot].generation!=gen)return false;
 ++loadCount;lastLoaded=slot;const auto&d=stateData[slot];tapeAttached=(d.flags&4)!=0;liveFrames=d.frames;
 liveKey[0]=d.originKey[0];liveKey[1]=d.originKey[1];++liveRevision;return true;
}
namespace PracticeSession {
bool projectSavestateMatches(const SavestateData&d,const u32(&key)[2],u32 role,u32 frames){
 return (d.flags&3)==3&&d.frames==frames&&(role?((d.flags&4)&&d.originKey[0]==key[0]&&d.originKey[1]==key[1]):
 (!frames&&!(d.flags&4)&&d.stateKey[0]==key[0]&&d.stateKey[1]==key[1]));}
bool available(){return true;}bool projectAvailable(){return canStart;}bool starting(){return false;}
bool recording(){return tapeRecord;}bool checkpointReady(){return readyCheckpoint&&tapeAttached;}
bool attachedTo(const u32(&key)[2]){return tapeAttached&&key[0]==liveKey[0]&&key[1]==liveKey[1];}
u32 editRevision(){return liveRevision;}
bool requestRecordFrom(u32 slot,u32 gen){if(!memory[slot].valid||memory[slot].generation!=gen)return false;
 tapeAttached=tapeRecord=tapePause=true;liveFrames=0;liveKey[0]=stateData[slot].stateKey[0];liveKey[1]=stateData[slot].stateKey[1];++liveRevision;return true;}
void pauseEditing(){tapeRecord=false;tapePause=true;}
void pauseForCheckpoint(){tapePause=true;}
bool requestBeginning(){return tapeAttached;}bool requestContinue(){tapeRecord=true;return tapeAttached;}
bool requestPlayback(){return tapeAttached;}
const char*status(){return runtimeStatus;}
}
namespace StateStorage {
bool available(){return true;}bool busy(){return false;}
bool projectBegin(const char*){response={};response.command=SUSAMUNE_STATE_CMD_TAS_BEGIN;response.id=7;responseReady=true;return true;}
bool projectRead(u32 id,u32 crc){response={};response.command=SUSAMUNE_STATE_CMD_TAS_READ;response.project=published;
 if(id!=published.projectId||crc!=published.checksum)response.status=SUSAMUNE_STATE_STALE;responseReady=true;return true;}
bool projectCommit(const SusamuneTasManifest&value,u32 old){
 if(!SusamuneTasManifestValid(&value)||old!=published.checksum)return false;
 ++commitCount;published=value;response={};response.command=SUSAMUNE_STATE_CMD_TAS_COMMIT;responseReady=true;return true;
}
bool projectRename(u32 id,u32 crc,const char*name){
 response={};response.command=SUSAMUNE_STATE_CMD_TAS_RENAME;response.id=id;
 if(id!=published.projectId||crc!=published.checksum)response.status=SUSAMUNE_STATE_STALE;
 else {++published.generation;memset(published.name,0,32);for(u32 i=0;name[i]&&i<31;++i)published.name[i]=name[i];
 published.checksum=SusamuneTasManifestCrc(&published);response.project=published;}
 responseReady=true;return true;}
bool projectDelete(u32 id,u32 crc){response={};response.command=SUSAMUNE_STATE_CMD_TAS_DELETE;response.id=id;
 if(id!=published.projectId||crc!=published.checksum)response.status=SUSAMUNE_STATE_STALE;
 else memset(&published,0,sizeof(published));responseReady=true;return true;}
bool projectCatalog(u32){response={};response.command=SUSAMUNE_STATE_CMD_TAS_CATALOG;responseReady=true;return true;}
bool takeProjectResult(Result&out){if(!responseReady)return false;out=response;responseReady=false;return true;}
bool catalogReady(){return true;}const SusamuneStateCatalog&catalog(){return catalogData;}
}
""" + '\n'.join(line for line in (ROOT / 'src/tas_project.cpp').read_text().splitlines() if not line.startswith('#pragma clang section')) + r"""
extern "C" __declspec(dllexport) void reset(){
 memset(memory,0,sizeof(memory));memset(stateData,0,sizeof(stateData));memset(fileData,0,sizeof(fileData));
 memset(&published,0,sizeof(published));memset(&catalogData,0,sizeof(catalogData));
 transferReady=responseReady=tapeAttached=tapeRecord=tapePause=saveFails=false;
 compatible=canStart=readyCheckpoint=true;nextGeneration=100;
 exportCount=commitCount=importCount=loadCount=clearCount=failExport=liveFrames=liveRevision=0;
 liveKey[0]=liveKey[1]=0;lastLoaded=99;ordinarySave=2;ordinaryLoad=1;runtimeStatus="fixture practice status";
 memset(TasProject::sRefs,0,sizeof(TasProject::sRefs));memset(TasProject::sPlan,0,sizeof(TasProject::sPlan));
 memset(&TasProject::sSaved,0,sizeof(TasProject::sSaved));memset(&TasProject::sPending,0,sizeof(TasProject::sPending));
 memset(TasProject::sPublishedKeys,0,sizeof(TasProject::sPublishedKeys));
 TasProject::sSavedRevision=TasProject::sCurrent=0;TasProject::sActive=TasProject::sDirty=TasProject::sCatalogReady=false;
 TasProject::finish("ready");
}
extern "C" __declspec(dllexport) void ordinary(u32 slot){memory[slot]={true,1,2,++nextGeneration,1234};stateData[slot]={};stateData[slot].stateKey[1]=nextGeneration;}
extern "C" __declspec(dllexport) u32 action(u32 code,u32 arg){switch(code){case 0:return TasProject::newProject();case 1:return TasProject::saveCheckpoint(arg);case 2:return TasProject::save("Example TAS");case 3:return TasProject::open(published.projectId,published.checksum);case 4:return TasProject::loadCheckpoint(arg);case 5:return TasProject::continueEditing();case 6:return TasProject::replace(arg,memory[arg].generation);case 7:TasProject::cancelReplacement();return 1;
 case 8:return TasProject::rename(published.projectId,published.checksum,"Renamed TAS");
 case 9:return TasProject::remove(published.projectId,published.checksum);
 case 10:return TasProject::rename(published.projectId,published.checksum^1,"Stale");
 case 11:return TasProject::remove(published.projectId,published.checksum^1);case 12:return TasProject::replay();
 default:return 0;}}
extern "C" __declspec(dllexport) void tick(){TasProject::update();TasProject::afterDraw();}
extern "C" __declspec(dllexport) void append(){++liveFrames;++liveRevision;tapeRecord=true;}
extern "C" __declspec(dllexport) void option(u32 code,u32 value){switch(code){case 0:saveFails=value;break;case 1:failExport=value;break;case 2:compatible=value;break;case 3:canStart=value;break;case 4:readyCheckpoint=value;break;case 5:fileData[published.components[1].componentId].data.originKey[1]=value;break;case 6:memory[TasProject::sRefs[0].slot].packedBytes=value;break;case 7:liveKey[1]=value;break;case 8:runtimeStatus="Playback finished - fingerprints matched";break;}}
extern "C" __declspec(dllexport) u32 value(u32 code){switch(code){case 0:return TasProject::active();case 1:return TasProject::busy();case 2:return TasProject::replacementNeeded();case 3:return exportCount;case 4:return commitCount;case 5:return importCount;case 6:return loadCount;case 7:return clearCount;case 8:return published.generation;case 9:return published.componentCount;case 10:return published.currentRole;case 11:return TasProject::dirty();case 12:return liveFrames;case 13:return ordinarySave;case 14:return ordinaryLoad;case 15:return lastLoaded;case 16:return TasProject::named();default:return 0;}}
extern "C" __declspec(dllexport) u32 generation(u32 slot){return memory[slot].generation;}
extern "C" __declspec(dllexport) u32 role(u32 role){return TasProject::sRefs[role].slot;}
extern "C" __declspec(dllexport) u32 allowed(u32 slot){return TasProject::replacementAllowed(slot);}
extern "C" __declspec(dllexport) const char*status(){return TasProject::status();}
""", encoding="utf-8")
        dll=source.with_suffix('.dll')
        result=subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-O2','-std=c++17','-I',str(ROOT/'include'),str(source),'-o',str(dll)],capture_output=True,text=True)
        if result.returncode: raise AssertionError(result.stderr)
        cls.lib=C.CDLL(str(dll));cls.lib.status.restype=C.c_char_p
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
    def setUp(self): self.lib.reset()
    def finish(self):
        for _ in range(30):
            if not self.lib.value(1) or self.lib.value(2):break
            self.lib.tick()
        self.assertFalse(self.lib.value(1), self.lib.status())
    def new(self): self.assertTrue(self.lib.action(0,0));self.finish()
    def save(self): self.assertTrue(self.lib.action(2,0));self.finish()
    def test_new_captures_beginning_without_touching_other_slots_or_selections(self):
        self.lib.ordinary(0);before=self.lib.generation(0);self.new()
        self.assertEqual(self.lib.role(0),1);self.assertEqual(self.lib.generation(0),before)
        self.assertEqual((self.lib.value(13),self.lib.value(14)),(2,1))
    def test_new_project_reuses_its_own_slots_after_discard(self):
        self.new();self.lib.append();self.lib.action(1,1);self.finish();self.lib.action(1,2);self.finish()
        start=self.lib.role(0);self.new()
        self.assertEqual(self.lib.role(0),start);self.assertEqual(self.lib.value(7),2)
        self.assertFalse(self.lib.value(2))
    def test_new_full_memory_requires_explicit_replacement(self):
        for i in range(3):self.lib.ordinary(i)
        before=[self.lib.generation(i) for i in range(3)]
        self.assertTrue(self.lib.action(0,0));self.assertTrue(self.lib.value(2))
        self.lib.action(7,0);self.assertEqual([self.lib.generation(i) for i in range(3)],before)
        self.lib.action(0,0);self.lib.action(6,2);self.finish()
        self.assertEqual(self.lib.role(0),2)
        self.assertEqual([self.lib.generation(i) for i in range(2)],before[:2])
    def test_beginning_never_follows_an_unrelated_loaded_take(self):
        self.new();self.lib.append();self.lib.option(7,999)
        self.assertFalse(self.lib.action(4,0))
        self.assertEqual(self.lib.value(6),0)

    def test_dirty_checkpoint_survives_lost_beginning_for_discard_warning(self):
        self.new();self.lib.append();self.save();self.lib.append()
        self.lib.ordinary(self.lib.role(0))
        self.assertFalse(self.lib.value(0))
        self.assertTrue(self.lib.value(11))

    def test_checkpoint_cannot_replace_beginning(self):
        self.new();self.assertFalse(self.lib.action(1,0))
        self.lib.ordinary(1);self.lib.ordinary(2);self.lib.action(1,1)
        self.assertTrue(self.lib.value(2));self.assertFalse(self.lib.allowed(0))
    def test_failed_capture_keeps_previous_project_and_memory(self):
        self.new();self.lib.append();self.save();before=[self.lib.generation(i) for i in range(3)]
        self.lib.option(0,1);self.lib.action(1,1);self.finish()
        self.assertEqual([self.lib.generation(i) for i in range(3)],before)
        self.assertTrue(self.lib.value(0));self.assertEqual(self.lib.value(8),1)
    def test_save_publishes_only_after_start_and_checkpoint_exports(self):
        self.new();self.lib.append();self.lib.action(2,0)
        self.lib.tick();self.assertEqual(self.lib.value(4),0)
        self.lib.tick();self.assertEqual(self.lib.value(4),0)
        self.lib.tick();self.assertEqual(self.lib.value(4),0)
        self.finish();self.assertEqual((self.lib.value(3),self.lib.value(9),self.lib.value(10)),(2,2,1))
    def test_runtime_status_follows_playback_completion_but_saved_status_is_kept(self):
        self.new();self.lib.append();self.save()
        saved=self.lib.status();self.lib.option(8,0)
        self.assertEqual(self.lib.status(),saved)
        self.assertTrue(self.lib.action(12,0))
        self.assertIn(b"Playback finished",self.lib.status())

    def test_new_recording_status_updates_after_starting_finishes(self):
        self.new();self.lib.option(8,0)
        self.assertIn(b"Playback finished",self.lib.status())

    def test_repeated_save_reuses_unchanged_beginning(self):
        self.new();self.lib.append();self.save();self.save()
        self.assertEqual(self.lib.value(3),3);self.assertEqual(self.lib.value(8),2)
    def test_repacked_smaller_beginning_is_exported_to_keep_capacity(self):
        self.new();self.lib.append();self.save();self.lib.option(6,3000);self.save()
        self.assertEqual(self.lib.value(3),4)
    def test_failed_export_keeps_previous_published_project(self):
        self.new();self.lib.append();self.save();self.lib.append();self.lib.option(1,3);self.save()
        self.assertEqual(self.lib.value(8),1);self.assertEqual(self.lib.value(4),1);self.assertTrue(self.lib.value(11))
    def test_no_new_frame_after_save_is_not_dirty(self):
        self.new();self.lib.append();self.save();self.assertFalse(self.lib.value(11))
        self.lib.action(5,0);self.assertFalse(self.lib.value(11));self.lib.append();self.assertTrue(self.lib.value(11))
    def test_full_previous_project_releases_only_owned_slots_then_opens(self):
        self.new();self.lib.append();self.lib.action(1,1);self.finish();self.lib.append();self.lib.action(1,2);self.finish();self.save()
        self.assertTrue(self.lib.action(3,0));self.finish()
        self.assertEqual((self.lib.value(7),self.lib.value(5),self.lib.value(6)),(3,3,1))
        self.assertEqual(self.lib.value(15),self.lib.role(2));self.assertEqual(self.lib.value(12),2)
    def test_open_preserves_unrelated_state(self):
        self.lib.ordinary(2);before=self.lib.generation(2);self.new();self.lib.append();self.save();self.lib.action(3,0);self.finish()
        self.assertEqual(self.lib.generation(2),before);self.assertEqual(self.lib.value(7),2)
    def test_wrong_mission_rejected_before_any_ram_change(self):
        self.new();self.lib.append();self.save();before=[self.lib.generation(i) for i in range(3)]
        self.lib.option(2,0);self.lib.action(3,0);self.finish()
        self.assertEqual(self.lib.value(5),0);self.assertEqual(self.lib.value(7),0)
        self.assertEqual([self.lib.generation(i) for i in range(3)],before)
    def test_wrong_checkpoint_origin_never_restores_world(self):
        self.new();self.lib.append();self.save();self.lib.option(5,999);self.lib.action(3,0);self.finish()
        self.assertEqual(self.lib.value(6),0)
    def test_rename_active_project_updates_identity_for_next_save(self):
        self.new();self.lib.append();self.save();self.lib.action(8,0);self.finish()
        self.assertEqual(self.lib.value(8),2);self.save()
        self.assertEqual(self.lib.value(8),3)
        self.assertEqual(self.lib.value(3),3)

    def test_delete_keeps_editor_memory_and_next_save_creates_project(self):
        self.new();self.lib.append();self.save();before=[self.lib.generation(i) for i in range(3)]
        self.lib.action(9,0);self.finish()
        self.assertFalse(self.lib.value(16));self.assertTrue(self.lib.value(0))
        self.assertEqual([self.lib.generation(i) for i in range(3)],before)
        self.save();self.assertEqual(self.lib.value(8),1)

    def test_stale_rename_and_delete_preserve_published_project(self):
        self.new();self.lib.append();self.save()
        for code in (10,11):
            self.lib.action(code,0);self.finish();self.assertEqual(self.lib.value(8),1)
            self.assertTrue(self.lib.value(16))
        self.save();self.assertEqual(self.lib.value(8),2)

    def test_not_ready_scene_or_changed_settings_cannot_create_checkpoint(self):
        self.lib.option(3,0);self.assertFalse(self.lib.action(0,0));self.lib.option(3,1);self.new()
        self.lib.option(4,0);self.assertFalse(self.lib.action(1,1))

if __name__=='__main__':unittest.main()
