"""Exercise grouped bind navigation and recorder ownership using production methods."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class BindsMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        menu = (ROOT / "src/menu.cpp").read_text()
        body = menu[menu.index("class BindsTab :"):]
        start = menu.index("struct BindPage")
        tables = menu[start:menu.index("}  // namespace", start)]
        methods = "\n".join(function(body, signature).replace(" override", "") for signature in (
            "bool grabsInput() const", "bool back()", "void update(",
            "static int pageCount()", "BindId selectedBind() const",
            "static BindId bindAt(", "static int displayIndex(",
            "const char *sectionName(", "void jumpSection("))
        cls.ids = re.findall(r"X\((BIND_\w+),", (ROOT / "include/susamune/binds_list.h").read_text())
        source = r'''
#include "susamune/binds_list.h"
typedef unsigned char u8;typedef unsigned u32;
#define ID(name,key) name,
enum BindId{SUSAMUNE_BIND_LIST(ID) BIND_COUNT};
#undef ID
struct TMarioGamePad {enum{CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8,A=16,X=32};
 struct Buttons{u32 mRapidInput;}mButtons;};
struct Menu{u32 navigationInput(TMarioGamePad*p){return p->mButtons.mRapidInput;}};
struct Binds{bool rec;int target,cleared;bool recording(){return rec;}
 void beginRecord(BindId id){rec=true;target=id;}void cancelRecord(){rec=false;}
 void set(BindId id,int){cleared=id;}}gBinds;
int wrap(int value,int count){return (value+count)%count;}
'''
        source += tables + "class BindsTab {public:\n" + methods + "\nu8 mSel,mPage;};\n"
        source += r'''
#define API extern "C" __declspec(dllexport)
API int pages(){return sizeof(kBindPages)/sizeof(kBindPages[0]);}
API int count(int page){return kBindPages[page].count;}
API int route(int page,int row,int clear){
 BindsTab tab;tab.mSel=page;tab.mPage=0;gBinds.rec=false;gBinds.target=gBinds.cleared=-1;
 Menu menu;TMarioGamePad pad={{TMarioGamePad::A}};tab.update(&menu,&pad);
 if(tab.mPage!=page+1||tab.mSel!=0||gBinds.rec)return -10;
 pad.mButtons.mRapidInput=TMarioGamePad::CSTICK_DOWN;
 for(int i=0;i<row;++i)tab.update(&menu,&pad);
 pad.mButtons.mRapidInput=clear?TMarioGamePad::X:TMarioGamePad::A;tab.update(&menu,&pad);
 if(!clear){if(!tab.grabsInput())return -11;
  pad.mButtons.mRapidInput=TMarioGamePad::A;tab.update(&menu,&pad);
  if(tab.mSel!=row)return -12;
  pad.mButtons.mRapidInput=TMarioGamePad::CSTICK_LEFT;tab.update(&menu,&pad);
  if(tab.grabsInput())return -13;}
 if(!tab.back()||tab.mPage||tab.mSel!=page)return -14;
 if(tab.back())return -15;
 return clear?gBinds.cleared:gBinds.target;
}
API int changeGroup(int page,int direction){
 BindsTab tab;tab.mSel=1;tab.mPage=page+1;gBinds.rec=false;
 Menu menu;TMarioGamePad pad={{(u32)(direction<0?TMarioGamePad::CSTICK_LEFT:TMarioGamePad::CSTICK_RIGHT)}};
 tab.update(&menu,&pad);
 if(tab.mSel!=0)return -1;
 return tab.mPage-1;
}
API int index(int id){return BindsTab::displayIndex(id);}
API const char*section(int id){BindsTab tab;return tab.sectionName(id);}
'''
        cls.temp = tempfile.TemporaryDirectory(prefix="binds-menu-")
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name) / "binds.cpp"
        path.write_text(source, encoding="ascii")
        dll = path.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(path), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.lib.section.restype = C.c_char_p
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_each_visible_bind_can_be_recorded_and_cleared_in_one_submenu(self):
        seen = []
        for page in range(self.lib.pages()):
            self.assertLessEqual(self.lib.count(page), 12)
            for row in range(self.lib.count(page)):
                bind = self.lib.route(page, row, 0)
                self.assertGreaterEqual(bind, 0)
                self.assertEqual(self.lib.route(page, row, 1), bind)
                self.assertEqual(self.lib.index(bind), len(seen))
                self.assertEqual(self.lib.section(bind), self.lib.section(self.lib.route(page, 0, 1)))
                seen.append(bind)
        hidden = {self.ids.index("BIND_PRACTICE_SPIN_CW"), self.ids.index("BIND_PRACTICE_SPIN_CCW")}
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), set(range(len(self.ids))) - hidden)

    def test_horizontal_navigation_changes_category_and_wraps(self):
        for page in range(self.lib.pages()):
            for direction in (-1, 1):
                self.assertEqual(self.lib.changeGroup(page, direction), (page + direction) % self.lib.pages())


if __name__ == "__main__":
    unittest.main()
