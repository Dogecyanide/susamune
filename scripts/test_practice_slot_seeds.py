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
#include "susamune/binds.hxx"
extern "C" void *memcpy(void *dst,const void *src,size_t n) {
    for(size_t i=0;i<n;++i)((volatile u8*)dst)[i]=((const u8*)src)[i];return dst;
}
struct PadHistory {u8 shared[80],controls[80],meaning[0x4c];};
''' + "struct PracticeSeed {PadHistory pad;u32 stage;}" + r''';
static PracticeSeed sSeeds[SavestateManager::kSlotCount];
struct Pad {PadHistory history;};
static Pad pad;
static struct {void *mCurrentHeap;Pad *mGamePads[1];} gpApplication;
static SavestateManager::SlotInfo infos[3];
enum {SAVED_PAD=1,SAVED_RNG=2,SAVED_PAUSED=16};
static PracticeSession::SavestateData meta[3];
static u32 sOriginKey[2],sTakePosition;
static bool sTakeAttached,sOwnRestoreValid,restorePadValid;
static u32 selected,loadedSlot,loadedGeneration,loadCalls;
SavestateManager::SavestateManager() {}
u32 SavestateManager::activeSlot()const{return selected;}
SavestateManager::SlotInfo SavestateManager::slotInfo(u32 slot)const {
    return slot<3?infos[slot]:SlotInfo{};
}
bool SavestateManager::loadSlot(u32 slot,u32 generation) {
    ++loadCalls;loadedSlot=slot;loadedGeneration=generation;sOwnRestoreValid=restorePadValid;
    if(slot<3)pad.history=sSeeds[slot].pad;
    return slot<3&&infos[slot].valid&&infos[slot].generation==generation;
}
static SavestateManager manager;
static SavestateManager *gSavestateMgr=&manager;
static u32 sStageGeneration,sTapeSeed,sTapeSlot,sLoadSlot,sLoadGeneration;
static u32 sTapeStage,sSettingsHash,sTapeHash,sCount,sCursor;
static bool sRecord,sReplay,sOwnLoad,sHaveRead,sPaused,sFreeCamera,sPausePending,sStepQueued;
static u8 sLoadKind;
static u8 sMenuAction;
static u16 sLoadWait,sStartRelease,sStripButtons,sPriorButtons;
static u32 sTapeStart;
bool SavestateManager::practiceData(u32 slot,PracticeSession::SavestateData*out)const {
    if(slot>=3||!infos[slot].valid||sSeeds[slot].stage!=sStageGeneration)return false;
    *out=meta[slot];return true;
}
static SusamunePracticeInput sPhysical;
static struct Frame {u32 words[4];} frames[4],*sFrames=frames;
static bool menuOpen,wheelOpen,promptOpen,resultOpen,diskActive,rngSaved;
class Menu {public:bool shown(){return menuOpen;}};
static Menu menu,*gMenu=&menu;
struct JUTGamePad {enum {A=0x100};};
namespace WarpWheel {bool shown(){return wheelOpen;}bool promptPending(){return promptOpen;}}
namespace StageLoader {bool resultOwnsInput(){return resultOpen;}}
namespace Ghost {bool observerStatsSuppressed(){return false;}}
namespace CrashReport {void note(u32,u32,u32){}}
const int SUSAMUNE_CRASH_EVENT_REPLAY=1,CARD_ERROR_BUSY=-1;
static int cardStatus;
static struct Card {int getLastStatus(){return cardStatus;}} card,*gpCardManager=&card;
static u16 recordBind,replayBind;
static struct TestBinds {
    void suppressUntilRelease(){}
    u16 get(BindId id){return id==BIND_PRACTICE_RECORD?recordBind:replayBind;}
} testBinds;
#define gBinds testBinds
static const int SETTING_SAVE_RNG_STATE=1;
static struct TestSettings {bool getBool(int){return rngSaved;}} gSettings;
void capturePad(PadHistory &out,Pad *p){out=p->history;}
void restorePad(const PadHistory &in,Pad *p){p->history=in;}
bool tapeStorageReady(){return true;}
bool normalStage(){return true;}
static u32 currentHash,currentFingerprint,tapeHash;
u32 settingsHash(){return currentHash;}
u32 fingerprint(){return currentFingerprint;}
u32 hashBytes(u32,const void*,u32){return tapeHash;}
bool SavestateManager::diskBusy(){return diskActive;}
void restoreCamera(){}
void invalidate(){}
static const char *lastMessage;
void message(const char *text){lastMessage=text;}
void stopTape(const char *reason){sRecord=sReplay=false;sLoadKind=0;sLoadWait=sStartRelease=0;
    sTapeHash=42;if(reason)message(reason);}
''' + function_source(production, "void queueTapeLoad(") + r'''
''' + seed_match.replace(narrow, replacement) + function_source(production, "bool findTakeStart()") + r'''
namespace PracticeSession {
bool available(){return true;}
''' + functions.replace(narrow, replacement) + r'''
}
extern "C" __declspec(dllexport) void reset() {
    for(u32 i=0;i<3;++i){infos[i]={};sSeeds[i]={};meta[i]={};}
    sOriginKey[0]=sOriginKey[1]=sTakePosition=0;sTakeAttached=false;sPaused=false;
    selected=0;loadedSlot=99;loadedGeneration=loadCalls=0;
    sStageGeneration=7;sTapeSeed=sTapeSlot=sLoadSlot=sLoadGeneration=0;
    sCount=sCursor=sTapeStage=sSettingsHash=sTapeHash=0;
    sLoadKind=0;sLoadWait=0;sRecord=sReplay=sOwnLoad=false;
    sPhysical={};cardStatus=0;pad={};rngSaved=restorePadValid=true;
    menuOpen=wheelOpen=promptOpen=resultOpen=diskActive=false;
    sPausePending=sStepQueued=false;sMenuAction=0;sStartRelease=sStripButtons=sPriorButtons=0;
    currentHash=tapeHash=42;currentFingerprint=123;recordBind=4;replayBind=8;
    sTapeStart=0;lastMessage="";
    gpApplication.mCurrentHeap=(void*)0x80500000;gpApplication.mGamePads[0]=&pad;
}
extern "C" __declspec(dllexport) void save(u32 slot,u32 generation,u32 marker) {
    infos[slot]={true,2,0,generation,1234};pad.history.meaning[0]=(u8)marker;
    sSeeds[slot].pad=pad.history;sSeeds[slot].stage=sStageGeneration;
    meta[slot]={};meta[slot].flags=SAVED_PAD|(rngSaved?SAVED_RNG:0);meta[slot].stateKey[1]=generation;
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
extern "C" __declspec(dllexport) void config(u32 which,u32 value) {
    switch(which) {
    case 0:menuOpen=value!=0;break;case 1:sPhysical.buttons=(u16)value;break;
    case 2:sPausePending=value!=0;sStepQueued=value!=0;sMenuAction=(u8)value;break;
    case 3:currentHash=value;break;case 4:currentFingerprint=value;break;
    case 5:rngSaved=value!=0;break;case 6:diskActive=value!=0;break;
    case 7:promptOpen=value!=0;break;case 8:sPhysical.error=(s8)value;break;
    case 9:tapeHash=value;break;case 10:restorePadValid=value!=0;break;
    }
}
extern "C" __declspec(dllexport) const char *status(){return lastMessage;}
extern "C" __declspec(dllexport) u32 value(u32 which) {
    switch(which){case 0:return loadCalls;case 1:return loadedSlot;
    case 2:return loadedGeneration;case 3:return pad.history.meaning[0];
    case 4:return sRecord;case 5:return sReplay;case 6:return sCount;
    case 7:return sLoadKind;case 8:return sTapeSlot;case 9:return sTapeSeed;
    case 10:return sPausePending;case 11:return sStepQueued;case 12:return sMenuAction;
    case 13:return sPaused;case 14:return sStartRelease;
    default:return 999;}
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.status.restype = C.c_char_p
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

    def test_restored_game_cannot_start_record_or_replay_with_bad_controller_history(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.config(10, 0)
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (4, 5, 7, 13)], [0, 0, 0, 1])
        self.lib.config(10, 1)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.finishTake()
        self.assertTrue(self.lib.replay())
        self.lib.config(10, 0)
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (4, 5, 7, 13)], [0, 0, 0, 1])

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

    def test_replacing_start_preserves_editing_but_disables_replay_until_reimport(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.save(2, 11, 71)
        self.assertEqual((self.lib.value(4), self.lib.value(9)), (1, 10))
        self.lib.save(0, 12, 72)
        self.assertEqual([self.lib.value(i) for i in (4, 5, 6, 7, 9)], [1, 0, 0, 0, 0])
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
        self.assertEqual([self.lib.value(i) for i in (4, 5, 6, 7, 9)], [1, 0, 0, 0, 0])

    def make_take(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.lib.finishTake()

    def test_menu_start_releases_only_confirming_A(self):
        self.lib.save(0, 10, 70)
        self.lib.config(0, 1)
        self.lib.config(1, 0x120)  # A confirms; R is prepared gameplay input.
        self.assertTrue(self.lib.record())
        self.lib.config(0, 0)
        self.lib.poll()
        self.assertEqual(self.lib.value(0), 0)
        self.lib.config(1, 0x20)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(4)), (1, 1))

    def test_shortcut_start_accepts_held_gameplay_button(self):
        self.lib.save(0, 10, 70)
        self.lib.config(1, 0x104)
        self.assertTrue(self.lib.record())
        self.lib.poll()
        self.assertEqual(self.lib.value(0), 0)
        self.lib.config(1, 0x100)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(4)), (1, 1))

    def test_start_takes_over_buffered_pause_and_queued_step(self):
        self.lib.save(0, 10, 70)
        self.lib.config(2, 1)
        self.assertTrue(self.lib.record())
        self.assertEqual([self.lib.value(i) for i in (10, 11, 12)], [0] * 3)
        self.lib.config(2, 1)  # A later stray pause must not survive the reload.
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (10, 11, 12)], [0] * 3)

    def test_rng_disabled_seed_requires_resave_even_if_option_is_now_on(self):
        self.lib.config(5, 0)
        self.lib.save(0, 10, 70)
        self.lib.config(5, 1)
        self.assertFalse(self.lib.record())
        self.assertIn(b"Save RNG state", self.lib.status())
        self.lib.save(0, 11, 70)
        self.assertTrue(self.lib.record())

    def test_start_waits_for_SD_or_confirmation_without_losing_request(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        for gate in (6, 7):
            self.lib.config(gate, 1)
            self.lib.poll()
            self.assertEqual((self.lib.value(0), self.lib.value(7)), (0, 1))
            self.lib.config(gate, 0)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(4)), (1, 1))

    def test_disconnect_cancels_wait_without_reloading(self):
        self.lib.save(0, 10, 70)
        self.assertTrue(self.lib.record())
        self.lib.config(8, 1)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(7)), (0, 0))
        self.assertIn(b"disconnected", self.lib.status())

    def test_settings_and_damaged_take_have_distinct_refusals(self):
        self.make_take()
        self.lib.config(3, 77)
        self.assertFalse(self.lib.replay())
        self.assertIn(b"Settings changed", self.lib.status())
        self.lib.config(3, 42)
        self.lib.config(9, 77)
        self.assertFalse(self.lib.replay())
        self.assertIn(b"damaged", self.lib.status())
        self.assertEqual(self.lib.value(0), 1)

    def test_settings_changed_while_start_pending_prevent_reload(self):
        self.make_take()
        self.assertTrue(self.lib.replay())
        self.lib.config(3, 77)
        self.lib.poll()
        self.assertEqual((self.lib.value(0), self.lib.value(7)), (1, 0))
        self.assertIn(b"Settings changed", self.lib.status())

    def test_different_restored_start_pauses_before_first_input(self):
        self.make_take()
        self.assertTrue(self.lib.replay())
        self.lib.config(4, 124)
        self.lib.poll()
        self.assertEqual([self.lib.value(i) for i in (0, 5, 7, 13)], [2, 0, 0, 1])
        self.assertIn(b"Replay start differs", self.lib.status())


if __name__ == "__main__":
    unittest.main()
