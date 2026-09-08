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
            "void update(Menu *menu, TMarioGamePad *pad) override", "void changeState(Menu *menu, int direction)"))
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
 SlotInfo slots[3];u32 active;bool busy;int selections,clears;u32 clearTarget,clearGeneration;
 u32 activeSlot()const{return active;}SlotInfo slotInfo(u32 i)const{return slots[i];}
 bool selectSlot(u32 i){if(busy||i>=3)return false;active=i;selections++;return true;}
 bool clearSlot(u32 i,u32 generation){clearTarget=i;clearGeneration=generation;
  if(busy||i>=3||!slots[i].valid||slots[i].generation!=generation)return false;
  slots[i].valid=false;clears++;return true;}
};
static SavestateManager manager;SavestateManager*gSavestateMgr=&manager;
'''
        body = r'''
class SavestatesTab {public:
 enum {ROW_ACTIVE,ROW_CLEAR,ROW_RNG,ROW_FEEDBACK,ROW_EDITOR,ROW_COUNT};
 SavestatesTab():mSel(0),mConfirmClear(false),mClearSlot(0),mClearGeneration(0){focus();}
 STATE_METHODS
 u8 mSel;bool mConfirmClear;u32 mClearSlot,mClearGeneration;RawPromptInput mInput;
};
STARTS
enum{kBindSectionCount=sizeof(kBindSectionStarts)/sizeof(kBindSectionStarts[0])};
class BindsTab {public:BIND_METHODS int mSel;};
static void reset(){
 memset(&manager,0,sizeof(manager));gSavestateMgr=&manager;gCreationExtras.edit=false;gSettings.cycles=0;
 for(unsigned i=0;i<3;i++)manager.slots[i]={true,1,2,11+i,100};
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
        for row in range(5):
            self.assertEqual(self.lib.navigation(row, 1), (row + 1) % 5)
            self.assertEqual(self.lib.navigation(row, -1), (row - 1) % 5)

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
