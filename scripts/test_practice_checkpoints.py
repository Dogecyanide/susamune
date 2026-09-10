"""Exercise the real TAS sidecar capture/restore and branch continuation."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class PracticeCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, name) for name in (
            "bool captureSavestate(", "bool savestateRestoreSpans(",
            "bool copySavestateBytes(", "bool restoreSavestate(", "bool requestContinue()"))
        functions = functions.replace("reinterpret_cast<u32>(gpApplication.mCurrentHeap)",
                                      "static_cast<u32>(reinterpret_cast<size_t>(gpApplication.mCurrentHeap))")
        text = r'''
#include "susamune/practice_session.hxx"
#include "susamune/savestate.hxx"
#include "susamune/mem2_map.h"
extern "C" void *memcpy(void*d,const void*s,size_t n){for(size_t i=0;i<n;++i)((volatile u8*)d)[i]=((const u8*)s)[i];return d;}
extern "C" void *memset(void*d,int v,size_t n){for(size_t i=0;i<n;++i)((volatile u8*)d)[i]=(u8)v;return d;}
const u32 kMaxFrames=4096,kSavedTakeVersion=1;
enum SavedTakeFlags {SAVED_PAD=1,SAVED_RNG=2,SAVED_TAKE=4,SAVED_RECORDING=8,SAVED_PAUSED=16};
struct Frame {SusamunePracticeInput input;u32 fingerprint;};
struct PadHistory {u8 shared[80],controls[80],meaning[0x4c];};
struct Pad {PadHistory history;};
static Pad pad;
static struct {void*mCurrentHeap;Pad*mGamePads[1];} gpApplication;
static struct PracticeSeed {PadHistory pad;u32 generation,stage,heap;bool valid,rngSaved;} sSeeds[3];
static Frame storage[kMaxFrames],*sFrames=storage;
static PadHistory sStatePad,sModalPad;
static bool sModalPadValid;
static u32 sOriginKey[2],sCount,sCursor,sTakePosition,sTapeSeed,sTapeSlot,sTapeHash,sTapeStage,sTapeStart,sStageGeneration,sSteps,sSettingsHash;
static bool sOwnRestoreValid;
static u32 sPendingReleases;
static bool sOwnLoad,sHaveRead,sFrameInjected,sConsumedFrame,sTakeAttached,sPaused,sRecord,sReplay,sPausePending,sStepQueued;
static u16 sStripButtons;
static u32 liveFingerprint,liveSettings;
static bool gameplay,storageReady,rng,observer;
static const char*lastMessage;
static u64 clockValue;
u64 OSGetTime(){return ++clockValue;}
bool normalStage(){return gameplay;}
bool tapeStorageReady(){return storageReady;}
u32 fingerprint(){return liveFingerprint;}
u32 settingsHash(){return liveSettings;}
void capturePad(PadHistory&out,Pad*p){out=p->history;}
void restorePad(const PadHistory&in,Pad*p){p->history=in;}
void message(const char*p){lastMessage=p;}
void invalidate(){}
namespace Ghost {bool observerStatsSuppressed(){return observer;}}
const int SETTING_SAVE_RNG_STATE=1,BIND_SAVESTATE_LOAD=2;
struct JUTGamePad {enum{A=0x100};};
static struct {bool getBool(int){return rng;}} gSettings;
static struct {u16 get(int){return 2;}void suppressUntilRelease(){}} gBinds;
static PracticeSession::SavestateData metadata[3];
static SavestateManager::SlotInfo infos[3];
SavestateManager::SavestateManager(){}
static SavestateManager manager,*gSavestateMgr=&manager;
bool SavestateManager::practiceData(u32 i,PracticeSession::SavestateData*out)const{
    if(i>=3||!infos[i].valid)return false;*out=metadata[i];return true;
}
SavestateManager::SlotInfo SavestateManager::slotInfo(u32 i)const{return i<3?infos[i]:SlotInfo{};}
''' + function_source(production, "u32 hashBytes(") + function_source(production, "bool validSavedTake(") + function_source(production, "bool findTakeStart()") + r'''
void stopTape(const char*){if(sRecord)sTapeHash=hashBytes(2166136261u,sFrames,sCount*sizeof(Frame));sRecord=sReplay=false;}
namespace PracticeSession {
bool available(){return true;}
''' + functions + r'''
}
struct Archive {PracticeSession::SavestateData data;PadHistory pad;Frame frames[kMaxFrames];};
static Archive archives[4];
extern "C" __declspec(dllexport) void reset(){
    memset(storage,0,sizeof(storage));memset(infos,0,sizeof(infos));memset(metadata,0,sizeof(metadata));
    memset(archives,0,sizeof(archives));memset(&pad,0,sizeof(pad));
    sOriginKey[0]=sOriginKey[1]=sCount=sCursor=sTakePosition=sTapeSeed=sTapeSlot=sTapeHash=sTapeStage=sTapeStart=sSteps=0;
    sOwnLoad=sHaveRead=sFrameInjected=sConsumedFrame=sTakeAttached=sPaused=sRecord=sReplay=sPausePending=sStepQueued=false;
    sPendingReleases=0;sOwnRestoreValid=sModalPadValid=false;
    sStageGeneration=1;sSettingsHash=liveSettings=123;liveFingerprint=456;
    gameplay=storageReady=rng=true;observer=false;clockValue=0;lastMessage="";sStripButtons=0;
    gpApplication.mCurrentHeap=(void*)0x80500000;gpApplication.mGamePads[0]=&pad;
}
extern "C" __declspec(dllexport) int save(unsigned i){
    StateCodec::ReadSpan spans[2];if(!PracticeSession::captureSavestate(archives[i].data,spans))return 0;
    if(spans[0].size)memcpy(&archives[i].pad,spans[0].data,spans[0].size);
    if(spans[1].size)memcpy(archives[i].frames,spans[1].data,spans[1].size);
    if(i<3){metadata[i]=archives[i].data;infos[i]={true,2,0,i+1,1000};}return 1;
}
extern "C" __declspec(dllexport) void start(unsigned i){
    sOriginKey[0]=archives[i].data.stateKey[0];sOriginKey[1]=archives[i].data.stateKey[1];
    sTakeAttached=sRecord=true;sCount=sTakePosition=0;sSettingsHash=liveSettings;sTapeStart=liveFingerprint;
}
extern "C" __declspec(dllexport) void append(unsigned value){
    sFrames[sCount].input.buttons=(u16)value;sFrames[sCount].fingerprint=++liveFingerprint;
    ++sCount;sTakePosition=sCount;sTakeAttached=true;
}
extern "C" __declspec(dllexport) int load(unsigned i,unsigned own){
    StateCodec::WriteSpan spans[2];if(!PracticeSession::savestateRestoreSpans(archives[i].data,spans))return 0;
    sOwnLoad=own!=0;
    const void*src[2]={&archives[i].pad,archives[i].frames};
    for(unsigned n=0;n<2;++n)if(spans[n].size&&!PracticeSession::copySavestateBytes(spans[n].data,src[n],spans[n].size))memcpy(spans[n].data,src[n],spans[n].size);
    liveFingerprint=archives[i].data.savedFingerprint;
    if(!own){sRecord=sReplay=false;sTakeAttached=false;}
    bool restored=PracticeSession::restoreSavestate(archives[i].data,i,i<3?i+1:0);sOwnLoad=false;return restored;
}
extern "C" __declspec(dllexport) void config(unsigned key,unsigned value){
    switch(key){case 0:sPaused=value;break;case 1:liveSettings=value;break;
    case 2:observer=value;break;case 3:storageReady=value;break;
    case 4:rng=value;break;case 5:pad.history.meaning[0]=(u8)value;break;
    case 6:archives[1].data.frames=value;break;case 7:archives[1].frames[0].input.buttons^=1;break;
    case 8:sRecord=false;sTapeHash=hashBytes(2166136261u,sFrames,sCount*sizeof(Frame));break;
    case 9:for(unsigned i=0;i<3;++i)infos[i].valid=false;++sStageGeneration;break;
    case 10:metadata[value]=archives[0].data;infos[value]={true,2,0,99,1000};break;
    case 11:sTakePosition=value;break;
    case 12:sTakeAttached=value;break;
    case 13:archives[value].pad.meaning[0]^=1;break;
    case 14:sPendingReleases=value;break;
    case 15:sModalPadValid=true;sModalPad=pad.history;sModalPad.meaning[0]=(u8)value;break;
    }
}
extern "C" __declspec(dllexport) unsigned value(unsigned key){
    switch(key){case 0:return sCount;case 1:return sRecord;case 2:return sPaused;case 3:return pad.history.meaning[0];
    case 4:return sTapeSlot;case 5:return sTapeSeed;case 6:return sTakeAttached;case 7:return sTakePosition;case 8:return sPendingReleases;case 9:return sOwnRestoreValid;default:return 0;}
}
extern "C" __declspec(dllexport) unsigned input(unsigned i){return sFrames[i].input.buttons;}
extern "C" __declspec(dllexport) int resume(){return PracticeSession::requestContinue();}
extern "C" __declspec(dllexport) int origin(){return findTakeStart();}
extern "C" __declspec(dllexport) const char*status(){return lastMessage;}
'''
        source = Path(cls.temp.name) / "checkpoint.cpp"
        source.write_text(text)
        library = source.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.status.restype = C.c_char_p
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self):
        self.lib.reset()

    def checkpoint(self):
        self.assertTrue(self.lib.save(0))
        self.lib.start(0)
        for button in (10, 20, 30): self.lib.append(button)
        self.lib.config(0, 1)
        self.lib.config(5, 77)
        self.assertTrue(self.lib.save(1))

    def test_checkpoint_rewinds_inputs_and_replaces_future(self):
        self.checkpoint()
        for button in (40, 50): self.lib.append(button)
        self.assertTrue(self.lib.load(1, 0))
        self.assertEqual([self.lib.value(i) for i in (0, 1, 2, 3)], [3, 1, 1, 77])
        self.lib.append(99)
        self.assertEqual([self.lib.input(i) for i in range(4)], [10, 20, 30, 99])

    def test_three_checkpoints_keep_independent_prefixes(self):
        self.checkpoint()
        self.lib.append(40)
        self.assertTrue(self.lib.save(2))
        self.lib.load(1, 0)
        self.lib.append(99)
        self.lib.load(2, 0)
        self.assertEqual([self.lib.input(i) for i in range(4)], [10, 20, 30, 40])

    def test_sd_roundtrip_can_resume_without_start_and_relink_imported_start(self):
        self.checkpoint()
        self.lib.save(3)
        self.lib.config(9, 0)
        self.lib.load(3, 0)
        self.assertEqual((self.lib.value(0), self.lib.value(1)), (3, 1))
        self.assertFalse(self.lib.origin())
        self.lib.config(10, 2)
        self.assertTrue(self.lib.origin())
        self.assertEqual((self.lib.value(4), self.lib.value(5)), (2, 99))

    def test_own_start_load_preserves_entire_take(self):
        self.checkpoint()
        self.lib.append(40)
        self.lib.load(1, 1)
        self.assertEqual(self.lib.value(0), 4)
        self.assertEqual(self.lib.input(3), 40)

    def test_stopped_take_can_continue_at_checkpoint_but_not_unrelated_gameplay(self):
        self.checkpoint()
        self.lib.config(8, 0)
        self.lib.save(1)
        self.lib.load(1, 0)
        self.assertFalse(self.lib.value(1))
        self.assertTrue(self.lib.resume())
        self.assertEqual((self.lib.value(1), self.lib.value(2)), (1, 1))
        self.lib.config(12, 0)
        self.assertFalse(self.lib.resume())

    def test_branch_from_partially_played_take_discards_later_inputs(self):
        self.checkpoint()
        self.lib.append(40)
        self.lib.config(8, 0)
        self.lib.config(11, 2)
        self.assertTrue(self.lib.resume())
        self.lib.append(99)
        self.assertEqual(self.lib.value(0), 3)
        self.assertEqual([self.lib.input(i) for i in range(3)], [10, 20, 99])

    def test_changed_settings_stop_automatic_recording_without_losing_saved_take(self):
        self.checkpoint()
        self.lib.config(1, 124)
        self.lib.load(1, 0)
        self.assertEqual((self.lib.value(0), self.lib.value(1), self.lib.value(2)), (3, 0, 1))
        self.assertFalse(self.lib.resume())
        self.lib.config(1, 123)
        self.assertTrue(self.lib.resume())

    def test_bad_pad_alone_refuses_own_start_and_keeps_take_bytes(self):
        self.checkpoint()
        self.lib.append(40)
        self.lib.config(13, 0)
        self.assertFalse(self.lib.load(0, 1))
        self.assertFalse(self.lib.value(9))
        self.assertFalse(self.lib.value(1))
        self.assertTrue(self.lib.value(2))
        self.assertEqual(self.lib.input(3), 40)
        self.assertIn(b"controller history is damaged", self.lib.status())

    def test_bad_pad_without_a_take_is_also_reported(self):
        self.lib.save(0)
        self.lib.config(13, 0)
        self.assertFalse(self.lib.load(0, 0))
        self.assertIn(b"controller history is damaged", self.lib.status())

    def test_checkpoint_saved_from_menu_uses_retained_gameplay_history(self):
        self.checkpoint()
        self.lib.config(15, 88)
        self.lib.config(5, 99)
        self.lib.save(1)
        self.lib.load(1, 0)
        self.assertEqual(self.lib.value(3), 88)

    def test_checkpoint_preserves_pending_release_metadata(self):
        self.checkpoint()
        self.lib.config(14, 0x1abcde)
        self.lib.save(1)
        self.lib.config(14, 0)
        self.assertTrue(self.lib.load(1, 0))
        self.assertEqual(self.lib.value(8), 0x1abcde)
        self.lib.config(14, 0x200000)
        self.assertFalse(self.lib.save(2))

    def test_corrupt_or_oversized_prefix_cannot_resume(self):
        self.checkpoint()
        self.lib.config(6, 4097)
        self.assertFalse(self.lib.load(1, 0))
        self.lib.config(6, 3)
        self.lib.config(7, 0)
        self.lib.load(1, 0)
        self.assertFalse(self.lib.value(1))
        self.assertIn(b"damaged", self.lib.status())


if __name__ == "__main__": unittest.main()
