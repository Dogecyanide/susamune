"""Exercise production SD completion with real codec validation and banked commits."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import zlib

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'src/savestate.cpp'

FIXTURE = r'''
#include "susamune/state_storage.h"
#include "susamune/state_pool_memory.h"
#include "susamune/state_codec.hxx"
typedef unsigned int u32;typedef unsigned char u8;typedef long long OSTime;
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
extern "C" int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const u8*x=(const u8*)a,*y=(const u8*)b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
static int snprintf(char*d,__SIZE_TYPE__ n,const char*,...){if(n)*d=0;return 0;}
static u8 banks[2][50000], staging[4096];alignas(32)static u8 workspace[0x50000];
#undef SUSAMUNE_STATE_STAGING_SIZE
#define SUSAMUNE_STATE_STAGING_SIZE 4096u
static __UINTPTR_TYPE__ kStagingBase=(__UINTPTR_TYPE__)staging;
static StateSlotPool sPool;
static StatePoolMemory sPoolMemory={{banks[0],banks[1]},{50000,50000}};
struct StoredState {u32 generation,rawSize,packedSize,adler32,metadataTag;};
static StoredState sSlots[3],sCandidate,returned;
static u32 sDiskSlot,sDiskGeneration,sDiskPoolUsed,sDiskScene,sDurableSlots;
static OSTime sDiskStarted;static bool sDiskActive;
static const char*sDiskStatus;
static bool candidateMatches,transportBusy,ready;static u32 scene,rebased,cleared,notified,stores;
static bool muted,interrupts;
struct TMarDirector {enum{STATE_NORMAL=4};u32 mCurState;};
static TMarDirector director;static TMarDirector*gpMarDirector=&director;static bool loading;
static bool inLoadTransition(){return loading||!gpMarDirector;}
static u32 archiveSceneKey(){return scene;}
static bool validStore(){return StateSlotPoolValid(&sPool,100000);}
static u32 metadataTag(const StoredState&s){return s.generation^s.rawSize^s.packedSize^s.adler32;}
static u32 nextGeneration(){return 555;}
static bool archiveCandidateMatches(const SusamuneStateArchiveHeader&){return candidateMatches;}
static const char*archiveStatusText(u32){return "rejected";}
static void GXDrawDone(){}
static bool OSDisableInterrupts(){interrupts=true;return true;}
static void OSRestoreInterrupts(bool){interrupts=false;}
static bool muteAudioDma(){muted=true;return true;}
static void unmuteAudioDma(bool){muted=false;}
static void rebaseMissionStopwatch(OSTime){++rebased;}
static void DCStoreRange(void*,u32){++stores;}
static void*codecWorkspace(){return workspace;}
struct Menu{void toast(const char*){++notified;}}menu;static Menu*gMenu=&menu;
namespace PracticeSession{void onSavestateCleared(u32,u32){++cleared;}}
namespace StateStorage{
struct Result{u32 command,status,id;SusamuneStateArchiveHeader header;const void*metadata;};
static Result result;
void update(){}
bool takeResult(Result&out){if(!ready)return false;out=result;ready=false;transportBusy=false;return true;}
bool busy(){return transportBusy;}
}
class SavestateManager{public:enum{kSlotCount=3};static bool diskBusy();void updateDisk();}manager;
'''

EXPORTS = r'''
extern "C" {
__declspec(dllexport) void reset(const void*packed,u32 packedSize,u32 raw,u32 adler,u32 slot){
 memset(banks,0,sizeof(banks));memset(staging,0,sizeof(staging));memset(sSlots,0,sizeof(sSlots));
 for(u32 i=0;i<3;++i){sPool.slots[i]={i*13000,13000};sSlots[i].generation=100+i;
  for(u32 j=0;j<13000;++j)banks[0][i*13000+j]=(u8)(20+i);}
 sPool.used=39000;sDiskSlot=slot;sDiskGeneration=100+slot;sDiskPoolUsed=39000;
 sDiskScene=scene=0x10203;sDiskActive=true;sDiskStarted=17;sDurableSlots=0;
 returned={9,raw,packedSize,adler,0};returned.metadataTag=metadataTag(returned);
 StateStorage::result={};StateStorage::result.command=SUSAMUNE_STATE_CMD_IMPORT;
 StateStorage::result.status=SUSAMUNE_STATE_OK;StateStorage::result.metadata=&returned;
 StateStorage::result.header.metadataSize=sizeof(returned);
 u32 first=packedSize<4096?packedSize:4096;memcpy(staging,packed,first);
 StatePoolMemoryCopyIn(&sPoolMemory,sPool.used,(const u8*)packed+first,packedSize-first);
 candidateMatches=ready=transportBusy=true;rebased=cleared=notified=stores=0;muted=interrupts=false;
}
__declspec(dllexport) void change(u32 which){
 if(which==1)++sSlots[sDiskSlot].generation;
 if(which==2)++scene;
 if(which==3)candidateMatches=false;
 if(which==4)--StateStorage::result.header.metadataSize;
 if(which==5)staging[30]^=0x80;
 if(which==6)StateStorage::result.status=SUSAMUNE_STATE_CANCELLED;
 if(which==7)ready=false;
}
__declspec(dllexport) void tick(){manager.updateDisk();}
__declspec(dllexport) u32 get(u32 key){switch(key){case 0:return sPool.used;case 1:return sDurableSlots;
 case 2:return SavestateManager::diskBusy();case 3:return rebased;case 4:return cleared;
 case 5:return muted||interrupts;case 6:return stores;case 7:return sSlots[sDiskSlot].generation;}return 0;}
__declspec(dllexport) void slotBytes(u32 slot,void*out){StatePoolMemoryCopyOut(&sPoolMemory,sPool.slots[slot].offset,out,sPool.slots[slot].size);}
__declspec(dllexport) u32 slotSize(u32 slot){return sPool.slots[slot].size;}
__declspec(dllexport) u32 admitted(u32 state,u32 busy){director.mCurState=state;loading=busy;
 return admitArchiveStage();}
}
'''


class SavestateArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=ROOT/'toolchain/clang++.exe'
        if not compiler.exists():raise unittest.SkipTest('Bundled host compiler required')
        cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-sd-commit-')
        cls.addClassCleanup(cls.temp.cleanup)
        source=FIXTURE
        for name in ('void poolWriteSpans(', 'void poolReadSpans(', 'void storePool(',
                     'bool archiveStageReady()', 'bool admitArchiveStage()',
                     'bool SavestateManager::diskBusy()', 'void SavestateManager::updateDisk()'):
            source+=function_source(SOURCE,name)
        path=Path(cls.temp.name)/'test.cpp';path.write_text(source+EXPORTS)
        proc=subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-shared','-O2',
            '-fno-builtin','-mno-stack-arg-probe','-nostdlib','-fuse-ld=lld','-Wl,/noentry',
            '-I',str(ROOT/'include'),str(path),str(ROOT/'src/state_codec.cpp'),'-o',str(path.with_suffix('.dll'))],
            capture_output=True,text=True)
        if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
        cls.lib=C.CDLL(str(path.with_suffix('.dll')))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.reset.argtypes=[C.c_void_p]+[C.c_uint]*4
        cls.lib.slotBytes.argtypes=[C.c_uint,C.c_void_p]

    def setupCandidate(self,slot=1):
        self.raw=random.Random(99).randbytes(20000)
        self.packed=zlib.compress(self.raw)
        self.owner=C.create_string_buffer(self.packed)
        self.lib.reset(self.owner,len(self.packed),len(self.raw),zlib.adler32(self.raw),slot)

    def slot(self,index):
        b=C.create_string_buffer(self.lib.slotSize(index));self.lib.slotBytes(index,b);return b.raw

    def test_validated_import_commits_only_pinned_slot_and_marks_durable(self):
        for slot in range(3):
            self.setupCandidate(slot);self.assertEqual(self.lib.get(2),1)
            self.lib.tick()
            self.assertEqual(self.slot(slot),self.packed)
            for other in range(3):
                if other!=slot:self.assertEqual(self.slot(other),bytes([20+other])*13000)
            self.assertEqual(self.lib.get(1),1<<slot)
            self.assertEqual(self.lib.get(7),555)
            self.assertEqual([self.lib.get(i)for i in (2,3,4,5)],[0,1,1,0])

    def test_stale_slot_scene_profile_size_bad_stream_and_cancel_preserve_all_slots(self):
        for fault in range(1,7):
            with self.subTest(fault=fault):
                self.setupCandidate();self.lib.change(fault);self.lib.tick()
                for slot in range(3):self.assertEqual(self.slot(slot),bytes([20+slot])*13000)
                self.assertEqual([self.lib.get(i)for i in (0,1,2,3,4,5,6)],[39000,0,0,1,0,0,0])

    def test_missing_receipt_keeps_pool_owned_without_rebase_or_commit(self):
        self.setupCandidate();self.lib.change(7)
        for _ in range(10):self.lib.tick()
        self.assertEqual([self.lib.get(i)for i in (0,1,2,3,4,5,6)],[39000,0,1,0,0,0,0])

    def test_game_manifest_and_live_profile_checks_precede_decode_and_commit(self):
        check=function_source(SOURCE,'bool archiveCandidateMatches(')
        for condition in ('file.buildCrc != archiveBuildId()', 'file.gameId != archiveGameId()',
                'file.snapshotVersion != kSnapshotVersion', 'file.sceneKey != archiveSceneKey()',
                'sCandidate.metadataTag != metadataTag(sCandidate)', '!validSnapshotRegions(&h, begin, end)',
                '!Ghost::savestateRestoreSpans(sCandidate.ghost, ghost)',
                'StateArchiveProfile::matches(sCandidate.archiveProfile, sLiveArchiveProfile)'):
            self.assertIn(condition,check)
        update=function_source(SOURCE,'void SavestateManager::updateDisk()')
        self.assertLess(update.index('archiveCandidateMatches('),update.index('StateCodec::validate('))
        self.assertLess(update.index('StateCodec::validate('),update.index('StateSlotPoolCommitBanked('))
        self.assertLess(update.index('StateSlotPoolCommitBanked('),update.index('sSlots[sDiskSlot] = sCandidate'))
        load=function_source(SOURCE,'bool SavestateManager::loadSlot(')
        self.assertLess(load.index('StateArchiveProfile::matches('),load.index('StateCodec::decompress('))
        self.assertIn('durable ? StateArchiveProfile::copyGameBytes : nullptr',load)

    def test_sd_admission_requires_normal_play_and_reports_refusal(self):
        for state in range(13):
            self.assertEqual(self.lib.admitted(state,0),int(state==4))
            self.assertEqual(self.lib.admitted(state,1),0)
        admission=function_source(SOURCE,'bool admitArchiveStage()')
        self.assertIn('Return to normal play before using SD states',admission)
        self.assertIn('gMenu->toast(sDiskStatus)',admission)
        for action in ('saveToSD','loadFromSD','refreshSD'):
            code=function_source(SOURCE,f'bool SavestateManager::{action}(')
            self.assertLess(code.index('admitArchiveStage()'),code.index('StateStorage::'))


if __name__=='__main__':unittest.main()
