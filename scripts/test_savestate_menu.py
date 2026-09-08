"""Exercise state selection, guarded clearing and stable bind presentation."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class SavestateMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        source = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        state_source = source[source.index("class SavestatesTab :"):]
        state_methods = "\n".join(function(state_source, name).replace(" override", "") for name in (
            "void focus() override", "bool grabsInput() const override", "bool favoriteHint() const override",
            "void update(Menu *menu, TMarioGamePad *pad) override", "void changeState(Menu *menu, int direction)",
            "u32 sdCount() const", "void updateSD(Menu *menu, TMarioGamePad *pad, u16 pressed)"))
        bind_source = source[source.index("class BindsTab :"):]
        bind_methods = "\n".join(function(bind_source, name) for name in (
            "static int visibleCount()", "static BindId bindAt(int row)",
            "static int displayIndex(int id)", "u32 displayMetrics() const", "void jumpSection(int direction)"))
        starts = source[source.index("const u8 kBindSectionStarts[]"):]
        starts = starts[:starts.index("};") + 2]
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        shim = r'''
#include "susamune/binds_list.h"
#include "susamune/settings_list.h"
#include "susamune/state_storage.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
#define ID(name,key) name,
enum BindId {SUSAMUNE_BIND_LIST(ID) BIND_COUNT};
enum SettingId {SUSAMUNE_SETTING_LIST(ID)};
#undef ID
static_assert(BIND_SAVESTATE_SAVE==8&&BIND_SAVESTATE_LOAD==9&&BIND_PRACTICE_SPIN_CCW==30&&BIND_SAVESTATE_CYCLE==31,"bind IDs moved");
const u16 kA=1,kB=2,kX=4,kY=8,kZ=16,kStart=32,kL=64,kR=128,kDLeft=256,kDRght=512,kDUp=1024,kDDown=2048;
#define BIND_DESC(name,mask) (u16)(mask),
static const u16 defaults[]={
#include "binds_descs.inc"
};
#undef BIND_DESC
static_assert(sizeof(defaults)/sizeof(defaults[0])==BIND_COUNT,"bind descriptors drifted");
extern "C" int snprintf(char*out,unsigned long long,const char*,...){out[0]=0;return 0;}
extern "C" void *memset(void*d,int v,unsigned long long n){u8*p=(u8*)d;while(n--)*p++=(u8)v;return d;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*p=(u8*)d;const u8*q=(const u8*)s;while(n--)*p++=*q++;return d;}
struct JUTGamePad {enum {A=0x100,B=0x200,X=0x400};struct Status{u16 mButton;};static Status mPadStatus[1];};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad {enum {CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8};u32 nav;};
int wrap(int value,int count){return (value+count)%count;}
struct Menu {int toasts;u32 navigationInput(TMarioGamePad*p){return p->nav;}void toast(const char*){toasts++;}};
struct Settings {int cycles;bool star;
 void toggleFavorite(SettingId){star=!star;}bool favorite(SettingId){return star;}void cycle(SettingId,int){cycles++;}
}gSettings;
struct Extras {bool edit;bool editing(){return edit;}void updateEditor(TMarioGamePad*){edit=false;}
 void beginSavestateFeedbackEditor(){edit=true;}}gCreationExtras;
struct SavestateManager {
 enum{kSlotCount=3};struct SlotInfo{bool valid;u8 area,episode;u32 generation,packedBytes;};
 SlotInfo slots[3];u32 active;bool busy,available,ready;int selections,clears,exports,imports,refreshes,cancels;
 u32 clearTarget,clearGeneration,importId,importCrc,importSize,after;SusamuneStateCatalog catalog;
 u32 activeSlot()const{return active;}SlotInfo slotInfo(u32 i)const{return slots[i];}
 bool selectSlot(u32 i){if(busy||i>=3)return false;active=i;selections++;return true;}
 bool clearSlot(u32 i,u32 generation){clearTarget=i;clearGeneration=generation;
  if(busy||i>=3||!slots[i].valid||slots[i].generation!=generation)return false;
  slots[i].valid=false;clears++;return true;}
 static bool diskBusy();
 bool sdAvailable()const{return available;}bool sdCatalogReady()const{return ready;}
 const SusamuneStateCatalog&sdCatalog()const{return catalog;}
 const char*sdStatus()const{return "status";}
 bool saveToSD(){if(busy)return false;exports++;busy=true;return true;}
 bool loadFromSD(u32 id,u32 crc,u32 size){if(busy)return false;imports++;importId=id;importCrc=crc;importSize=size;busy=true;return true;}
 bool refreshSD(u32 id=0){if(busy)return false;after=id;refreshes++;busy=true;return true;}
 bool cancelSD(){cancels++;return true;}
};
static SavestateManager manager;SavestateManager*gSavestateMgr=&manager;
bool SavestateManager::diskBusy(){return manager.busy;}
'''
        body = r'''
class SavestatesTab {public:
 enum {ROW_ACTIVE,ROW_CLEAR,ROW_RNG,ROW_FEEDBACK,ROW_EDITOR,ROW_SD,ROW_COUNT};
 enum {SD_ACTIVE,SD_SAVE,SD_REFRESH,SD_NEXT,SD_FILES};
 SavestatesTab():mSel(0),mSDsel(0),mSD(false),mConfirmClear(false),mConfirmLoad(false),mClearSlot(0),mClearGeneration(0){focus();}
 STATE_METHODS
 u8 mSel,mSDsel;bool mSD,mConfirmClear,mConfirmLoad;u32 mClearSlot,mClearGeneration;
 u32 mArchiveId,mArchiveCrc,mArchiveSize;char mArchiveName[32];RawPromptInput mInput;
};
STARTS
enum{kBindSectionCount=sizeof(kBindSectionStarts)/sizeof(kBindSectionStarts[0])};
class BindsTab {public:BIND_METHODS int mSel;};
static void reset(){
 memset(&manager,0,sizeof(manager));gSavestateMgr=&manager;gCreationExtras.edit=false;gSettings.cycles=0;
 for(unsigned i=0;i<3;i++)manager.slots[i]={true,1,2,11+i,100};
 manager.available=true;manager.ready=true;manager.catalog.count=2;manager.catalog.more=1;manager.catalog.nextId=72;
 manager.catalog.entries[0]={51,500,0,0,0,0,41,0,"First"};
 manager.catalog.entries[1]={72,700,0,0,0,0,42,0,"Second"};
 JUTGamePad::mPadStatus[0].mButton=0;
}
static void press(SavestatesTab&t,Menu&m,u16 held,u32 nav=0){
 JUTGamePad::mPadStatus[0].mButton=held;TMarioGamePad pad={nav};t.update(&m,&pad);
}
extern "C" __declspec(dllexport) int selection(int test){
 reset();Menu menu={};
 if(test==3)JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;
 SavestatesTab tab;
 if(test==0){press(tab,menu,0,TMarioGamePad::CSTICK_LEFT);if(manager.active!=2)return 1;
  press(tab,menu,0,TMarioGamePad::CSTICK_RIGHT);if(manager.active)return 2;
  press(tab,menu,JUTGamePad::A);return manager.active==1&&manager.selections==3&&manager.clears==0?0:3;}
 if(test==1){manager.busy=true;press(tab,menu,JUTGamePad::A);return manager.active==0&&menu.toasts==1?0:4;}
 if(test==2){gSavestateMgr=0;press(tab,menu,JUTGamePad::A);return menu.toasts==1?0:5;}
 for(int i=0;i<9;i++)press(tab,menu,JUTGamePad::A);
 if(manager.selections)return 6;
 press(tab,menu,0);press(tab,menu,JUTGamePad::A);
 return manager.selections==1?0:7;
}
extern "C" __declspec(dllexport) int clear(int test){
 reset();SavestatesTab tab;Menu menu={};tab.mSel=1;
 if(test==5)manager.slots[0].valid=false;
 press(tab,menu,JUTGamePad::A);
 if(test==5)return !tab.mConfirmClear&&!manager.clears?0:1;
 if(!tab.grabsInput()||manager.clears)return 2;
 for(int i=0;i<9;i++)press(tab,menu,JUTGamePad::A);
 if(manager.clears)return 3;
 if(test==1)manager.slots[0].generation=91;
 if(test==2)manager.active=1;
 if(test==3)manager.busy=true;
 press(tab,menu,0);press(tab,menu,test==4?JUTGamePad::B:JUTGamePad::A);
 if(tab.mConfirmClear)return 4;
 const bool cleared=test==0||test==2;
 if(manager.clears!=(int)cleared||manager.slots[0].valid==cleared)return 5;
 if(!manager.slots[1].valid||!manager.slots[2].valid)return 6;
 if(test!=4&&(manager.clearTarget!=0||manager.clearGeneration!=11))return 7;
 return 0;
}
extern "C" __declspec(dllexport) int navigation(int row,int direction){
 reset();SavestatesTab tab;Menu menu={};tab.mSel=row;
 press(tab,menu,0,direction<0?TMarioGamePad::CSTICK_UP:TMarioGamePad::CSTICK_DOWN);return tab.mSel;
}
extern "C" __declspec(dllexport) int sdImport(int test){
 reset();SavestatesTab tab;Menu menu={};tab.mSD=true;tab.mSDsel=SavestatesTab::SD_FILES+1;
 if(test==6)manager.slots[0].valid=false;
 press(tab,menu,JUTGamePad::A);
 if(!tab.mConfirmLoad||manager.imports||tab.mArchiveId!=72)return 1;
 for(int i=0;i<9;i++)press(tab,menu,JUTGamePad::A);
 if(manager.imports)return 2;
 manager.catalog.entries[1]={99,900,0,0,0,0,98,0,"Replaced catalogue"};
 if(test==1)manager.active=1;
 if(test==2)manager.slots[0].generation++;
 if(test==3)manager.busy=true;
 press(tab,menu,0);press(tab,menu,test==4?JUTGamePad::B:JUTGamePad::A);
 if(test==3)return manager.imports==0&&manager.cancels==1&&tab.mSD?0:3;
 if(tab.mConfirmLoad)return 4;
 const bool imported=test==0||test==5||test==6;
 if(manager.imports!=(int)imported)return 5;
 if(imported&&(manager.importId!=72||manager.importCrc!=42||manager.importSize!=700))return 6;
 if(test==5){for(int i=0;i<9;i++)press(tab,menu,JUTGamePad::A);if(manager.cancels)return 7;}
 return manager.clears==0&&manager.exports==0?0:8;
}
extern "C" __declspec(dllexport) int sdActions(int test){
 reset();SavestatesTab tab;Menu menu={};tab.mSD=true;
 if(test==0||test==1){tab.mSDsel=SavestatesTab::SD_SAVE;if(test==1)manager.slots[0].valid=false;
  press(tab,menu,JUTGamePad::A);return manager.exports==(test==0)&&!manager.clears?0:1;}
 if(test==2){tab.mSDsel=SavestatesTab::SD_NEXT;press(tab,menu,JUTGamePad::A);
  return manager.refreshes==1&&manager.after==72?0:2;}
 if(test==3){tab.mSDsel=SavestatesTab::SD_REFRESH;press(tab,menu,JUTGamePad::A);
  return manager.refreshes==1&&manager.after==0?0:3;}
 if(test==4){tab.mSDsel=SavestatesTab::SD_NEXT;manager.catalog.more=0;press(tab,menu,JUTGamePad::A);return manager.refreshes?4:0;}
 if(test==5){manager.busy=true;tab.mSDsel=SavestatesTab::SD_SAVE;
  press(tab,menu,JUTGamePad::B,TMarioGamePad::CSTICK_DOWN);
  if(!tab.mSD||manager.cancels!=1||manager.exports||tab.mSDsel!=SavestatesTab::SD_SAVE)return 5;
  manager.busy=false;press(tab,menu,JUTGamePad::B);if(!tab.mSD)return 6;
  press(tab,menu,0);press(tab,menu,JUTGamePad::B);return tab.mSD?7:0;}
 if(test==6){tab.mSDsel=255;manager.catalog.count=0;press(tab,menu,JUTGamePad::A);
  return tab.mSDsel==SavestatesTab::SD_NEXT&&!manager.imports?0:8;}
 if(test==7){manager.catalog.count=999;tab.mSDsel=11;press(tab,menu,0,TMarioGamePad::CSTICK_DOWN);
  return tab.mSDsel==0&&tab.sdCount()==8?0:9;}
 if(test==8){tab.mSD=false;tab.mSel=SavestatesTab::ROW_SD;manager.ready=false;
  press(tab,menu,JUTGamePad::A);if(!tab.grabsInput()||manager.refreshes!=1)return 10;
  for(int i=0;i<9;i++)press(tab,menu,JUTGamePad::A);return manager.cancels?11:0;}
 if(test==9){manager.available=false;tab.mSDsel=SavestatesTab::SD_SAVE;press(tab,menu,JUTGamePad::A);return manager.exports?12:0;}
 if(test==10){gSavestateMgr=0;tab.mSDsel=255;press(tab,menu,JUTGamePad::A);return tab.mSDsel==3?0:13;}
 if(test==11){tab.mSDsel=SavestatesTab::SD_ACTIVE;press(tab,menu,0,TMarioGamePad::CSTICK_LEFT);return manager.active==2?0:14;}
 return 99;
}
extern "C" __declspec(dllexport) int bindOrder(int row){return BindsTab::bindAt(row);}
extern "C" __declspec(dllexport) int bindCount(){return BindsTab::visibleCount();}
extern "C" __declspec(dllexport) int bindDefault(){return defaults[BIND_SAVESTATE_CYCLE];}
extern "C" __declspec(dllexport) int bindIndex(int id){return BindsTab::displayIndex(id);}
extern "C" __declspec(dllexport) u32 bindMetrics(int id){BindsTab tab;tab.mSel=id;return tab.displayMetrics();}
extern "C" __declspec(dllexport) int bindJump(int id,int direction){BindsTab tab;tab.mSel=id;tab.jumpSection(direction);return tab.mSel;}
'''.replace("STATE_METHODS", state_methods).replace("STARTS", starts).replace("BIND_METHODS", bind_methods)
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-state-menu-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "menu.cpp").write_text(shim + raw + body, encoding="ascii")
        dll = work / "menu.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                        "-I", str(ROOT / "include"), "-I", str(ROOT / "src"),
                        str(work / "menu.cpp"), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.bindMetrics.restype = C.c_uint

    def test_selection_wraps_without_saving_or_clearing_and_respects_busy(self):
        for case in range(4):
            with self.subTest(case=case):
                self.assertEqual(self.lib.selection(case), 0)

    def test_clear_is_release_guarded_and_pins_slot_generation(self):
        for case in range(6):
            with self.subTest(case=case):
                self.assertEqual(self.lib.clear(case), 0)

    def test_menu_navigation_remains_in_bounds(self):
        for row in range(6):
            self.assertEqual(self.lib.navigation(row, 1), (row + 1) % 6)
            self.assertEqual(self.lib.navigation(row, -1), (row - 1) % 6)

    def test_sd_import_requires_release_and_pins_file_and_destination(self):
        for case in range(7):
            with self.subTest(case=case):
                self.assertEqual(self.lib.sdImport(case), 0)

    def test_sd_actions_paging_bounds_and_transfer_lock(self):
        for case in range(12):
            with self.subTest(case=case):
                self.assertEqual(self.lib.sdActions(case), 0)

    def test_cycle_bind_is_unassigned_and_grouped_without_changing_ids(self):
        expected = list(range(10)) + [31] + list(range(10, 29))
        actual = [self.lib.bindOrder(row) for row in range(self.lib.bindCount())]
        self.assertEqual(actual, expected)
        self.assertEqual(self.lib.bindDefault(), 0)
        for row, bind in enumerate(expected):
            self.assertEqual(self.lib.bindIndex(bind), row)
        self.assertEqual(self.lib.bindJump(31, 1), 10)
        self.assertEqual(self.lib.bindJump(31, -1), 8)

    def test_bind_scroll_rows_match_rendered_sections(self):
        headers = {0, 7, 8, 10, 14, 15, 21, 23}
        row = 0
        for index in range(self.lib.bindCount()):
            bind = self.lib.bindOrder(index)
            if bind in headers:
                row += 1
            metrics = self.lib.bindMetrics(bind)
            self.assertEqual(metrics & 0xffff, row)
            self.assertEqual(metrics >> 16, self.lib.bindCount() + len(headers))
            row += 1


if __name__ == "__main__":
    unittest.main()
