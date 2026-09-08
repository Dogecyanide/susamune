"""Exercise production recording requests against independently replaced slots."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class PracticeSlotSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        production = ROOT / "src/practice_session.cpp"
        seed_match = function_source(production, "bool seedMatches(")
        functions = "\n".join(function_source(production, signature) for signature in (
            "void afterDraw()", "void onSavestateSaved(", "void onSavestateCleared(", "bool requestRecord()",
            "bool requestPlayback()"))
        narrow = "reinterpret_cast<u32>(gpApplication.mCurrentHeap)"
        replacement = "static_cast<u32>(reinterpret_cast<size_t>(gpApplication.mCurrentHeap))"
        source = Path(cls.folder.name) / "seeds.cpp"
        source.write_text(r'''
#include "susamune/savestate.hxx"
#include "susamune/practice_session.hxx"
extern "C" void *memcpy(void *dst,const void *src,size_t n) {
    for(size_t i=0;i<n;++i)((volatile u8*)dst)[i]=((const u8*)src)[i];return dst;
}
struct PadHistory {u8 shared[80],controls[80],meaning[0x4c];};
''' + function_source(production, "struct PracticeSeed {") + r''';
static PracticeSeed sSeeds[SavestateManager::kSlotCount];
struct Pad {PadHistory history;};
static Pad pad;
static struct {void *mCurrentHeap;Pad *mGamePads[1];} gpApplication;
static SavestateManager::SlotInfo infos[3];
static u32 selected,loadedSlot,loadedGeneration,loadCalls;
SavestateManager::SavestateManager() {}
u32 SavestateManager::activeSlot()const{return selected;}
SavestateManager::SlotInfo SavestateManager::slotInfo(u32 slot)const {
    return slot<3?infos[slot]:SlotInfo{};
}
bool SavestateManager::loadSlot(u32 slot,u32 generation) {
    ++loadCalls;loadedSlot=slot;loadedGeneration=generation;
    return slot<3&&infos[slot].valid&&infos[slot].generation==generation;
}
static SavestateManager manager;
static SavestateManager *gSavestateMgr=&manager;
static u32 sStageGeneration,sTapeSeed,sTapeSlot,sLoadSlot,sLoadGeneration;
static u32 sTapeStage,sSettingsHash,sTapeHash,sCount,sCursor;
static bool sRecord,sReplay,sOwnLoad,sHaveRead,sPaused,sFreeCamera;
static u8 sLoadKind;
static u16 sLoadWait;
static SusamunePracticeInput sPhysical;
static struct Frame {u32 words[4];} frames[4],*sFrames=frames;
class Menu {public:bool shown(){return false;}};
static Menu *gMenu;
namespace WarpWheel {bool shown(){return false;}}
namespace StageLoader {bool resultOwnsInput(){return false;}}
namespace Ghost {bool observerStatsSuppressed(){return false;}}
namespace CrashReport {void note(u32,u32,u32){}}
const int SUSAMUNE_CRASH_EVENT_REPLAY=1,CARD_ERROR_BUSY=-1;
static int cardStatus;
static struct Card {int getLastStatus(){return cardStatus;}} card,*gpCardManager=&card;
static struct Binds {void suppressUntilRelease(){}} gBinds;
void capturePad(PadHistory &out,Pad *p){out=p->history;}
void restorePad(const PadHistory &in,Pad *p){p->history=in;}
bool tapeStorageReady(){return true;}
bool normalStage(){return true;}
u32 settingsHash(){return 42;}
u32 hashBytes(u32,const void*,u32){return 42;}
void restoreCamera(){}
void invalidate(){}
void message(const char*){}
void stopTape(const char*){sRecord=sReplay=false;sLoadKind=0;sLoadWait=0;sTapeHash=42;}
''' + seed_match.replace(narrow, replacement) + r'''
namespace PracticeSession {
bool available(){return true;}
''' + functions.replace(narrow, replacement) + r'''
}
extern "C" __declspec(dllexport) void reset() {
    for(u32 i=0;i<3;++i){infos[i]={};sSeeds[i]={};}
    selected=0;loadedSlot=99;loadedGeneration=loadCalls=0;
    sStageGeneration=7;sTapeSeed=sTapeSlot=sLoadSlot=sLoadGeneration=0;
    sCount=sCursor=sTapeStage=sSettingsHash=sTapeHash=0;
    sLoadKind=0;sLoadWait=0;sRecord=sReplay=sOwnLoad=false;
    sPhysical={};cardStatus=0;pad={};
    gpApplication.mCurrentHeap=(void*)0x80500000;gpApplication.mGamePads[0]=&pad;
}
extern "C" __declspec(dllexport) void save(u32 slot,u32 generation,u32 marker) {
    infos[slot]={true,2,0,generation,1234};pad.history.meaning[0]=(u8)marker;
    PracticeSession::onSavestateSaved(slot,generation);
}
extern "C" __declspec(dllexport) void select(u32 slot){selected=slot;}
extern "C" __declspec(dllexport) u32 record(){return PracticeSession::requestRecord();}
extern "C" __declspec(dllexport) u32 replay(){return PracticeSession::requestPlayback();}
extern "C" __declspec(dllexport) void finishTake(){sCount=4;sTapeHash=42;sRecord=false;}
extern "C" __declspec(dllexport) void poll(){PracticeSession::afterDraw();}
extern "C" __declspec(dllexport) void busy(u32 yes){cardStatus=yes?-1:0;}
extern "C" __declspec(dllexport) void clear(u32 slot){infos[slot].valid=false;}
extern "C" __declspec(dllexport) void clearNotify(u32 slot,u32 generation) {
    if(infos[slot].generation==generation)infos[slot].valid=false;
    PracticeSession::onSavestateCleared(slot,generation);
}
extern "C" __declspec(dllexport) void newStage(){++sStageGeneration;}
extern "C" __declspec(dllexport) u32 value(u32 which) {
    switch(which){case 0:return loadCalls;case 1:return loadedSlot;
    case 2:return loadedGeneration;case 3:return pad.history.meaning[0];
    case 4:return sRecord;case 5:return sReplay;case 6:return sCount;
    case 7:return sLoadKind;case 8:return sTapeSlot;case 9:return sTapeSeed;
    default:return 999;}
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self):
        self.lib.reset()

    def test_record_request_pins_slot_through_selection_and_busy_wait(self):
        for slot in range(3):
            self.lib.save(slot, 10 + slot, 70 + slot)
        self.lib.select(1)
        self.assertTrue(self.lib.record())
        self.lib.busy(1)
        self.lib.select(2)
        self.lib.poll()
        self.assertEqual(self.lib.value(0), 0)
        self.lib.busy(0)
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (1, 2, 3, 4, 8, 9)],
                         [1, 11, 71, 1, 1, 11])

    def test_playback_uses_recorded_seed_when_selection_changes(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.finishTake()
        self.lib.save(1, 11, 71)
        self.lib.select(1)
        self.assertTrue(self.lib.replay())
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (1, 2, 3, 5)], [0, 10, 70, 1])

    def test_save_other_slot_keeps_recording_but_replacing_seed_invalidates_it(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.save(2, 11, 71)
        self.assertEqual((self.lib.value(4), self.lib.value(9)), (1, 10))
        self.lib.save(0, 12, 72)
        self.assertEqual([self.lib.value(i) for i in (4, 5, 6, 7, 9)], [0] * 5)
        self.assertFalse(self.lib.replay())

    def test_pending_record_cancelled_only_when_its_seed_is_replaced(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.save(1, 11, 71)
        self.assertEqual(self.lib.value(7), 1)
        self.lib.save(0, 12, 72)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(7)), (0, 0))

    def test_cleared_seed_is_rejected_after_a_playback_request(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.finishTake()
        self.assertTrue(self.lib.replay())
        self.lib.clear(0)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(7)), (1, 0))

    def test_each_slot_has_its_own_pad_seed_and_stage_lifetime(self):
        for slot in range(3):
            self.lib.save(slot, 10 + slot, 70 + slot)
        for slot in (2, 0, 1):
            self.lib.select(slot)
            self.assertTrue(self.lib.record())
            self.lib.poll()
            self.lib.finishTake()
            self.assertEqual(self.lib.value(3), 70 + slot)
        self.lib.newStage()
        self.assertFalse(self.lib.record())
        self.assertFalse(self.lib.replay())

    def test_clear_callback_stops_only_the_matching_seed_generation(self):
        self.lib.save(0, 10, 70)
        self.lib.save(1, 11, 71)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.clearNotify(1, 11)
        self.lib.clearNotify(0, 9)
        self.assertEqual((self.lib.value(4), self.lib.value(9)), (1, 10))
        self.lib.clearNotify(0, 10)
        self.assertEqual([self.lib.value(i) for i in (4, 5, 6, 7, 9)], [0] * 5)


if __name__ == "__main__":
    unittest.main()
