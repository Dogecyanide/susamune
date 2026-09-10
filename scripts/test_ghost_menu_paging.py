"""Keep ghost choices attached to files when the visible page changes."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class GhostMenuPagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        text = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        text = text[text.index("class GhostsTab :"):]
        methods = "\n".join(function(text, name) for name in (
            "static bool selectionImported(", "static int selectionSlot(",
            "static const SusamuneGhostSlotInfo *selectionInfo(",
            "static bool captureRef(", "static bool refStillValid(",
            "static bool sameRef(", "static bool loadRef(",
            "static bool copyRefName(", "static int selectionRow(",
            "bool onPageRow() const", "void changePage("))
        rows = function(text, "enum {\n        RANGE_SIZE") + ";"
        ref = function(text, "struct GhostRef") + ";"
        shim = r'''
typedef unsigned char u8;typedef short s16;typedef unsigned u32;
#define SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES 16
#define SUSAMUNE_GHOST_SLOT_PRESENT 1
#define SUSAMUNE_GHOST_SLOT_UNSAFE 2
struct SusamuneGhostSlotInfo {u32 flags;};
namespace GhostStorage {
struct Identity {u32 id,generation;u8 flags,profile;char name[48];};
static u32 first[2],totals[2],requested,loaded[2];static bool requestImported;
static SusamuneGhostSlotInfo info={1};
const SusamuneGhostSlotInfo *slot(int row){return row>=0&&row<16?&info:0;}
const SusamuneGhostSlotInfo *importedSlot(int row){return slot(row);}
bool copyIdentity(bool imported,int row,Identity *out){
    if(!slot(row))return false;out->id=first[imported]+row;out->generation=7;
    out->profile=imported?4:0;out->flags=1;out->name[0]='A'+row;out->name[1]=0;return true;
}
bool identityValid(const Identity &id){return id.flags==1;}
bool sameIdentity(const Identity &a,const Identity &b){return a.id==b.id&&a.profile==b.profile;}
bool load(const Identity &id){loaded[0]=id.id;return true;}
bool loadObserver(const Identity &id,bool secondary){loaded[secondary]=id.id;return true;}
bool copyIdentityName(const Identity &id,char *out,u32 size){if(size<2)return false;out[0]=id.name[0];out[1]=0;return true;}
u32 totalCount(bool imported){return totals[imported];}
u32 pageOffset(bool imported){return first[imported];}
bool refreshPage(bool imported,u32 offset){requestImported=imported;requested=offset;return true;}
}
struct Menu {void toast(const char*){}};
'''
        body = r'''
class GhostsTab {
public:
ROWS
REF
METHODS
static const char *storageStatus(){return "status";}
int mSel;
static int slotDisplayRow(int first,int slot){return first+slot+slot/RANGE_SIZE+1;}
};
extern "C" __declspec(dllexport) int crossPage(int imported,u32 *out){
    using namespace GhostStorage;first[0]=first[1]=0;
    GhostsTab::GhostRef a,b;int row=imported?GhostsTab::IMPORTED_SELECTION_FIRST:GhostsTab::PERSONAL_SELECTION_FIRST;
    bool ok=GhostsTab::captureRef(row,&a);first[imported]=160;
    ok=ok&&GhostsTab::captureRef(row,&b);
    out[0]=GhostsTab::sameRef(a,b);out[1]=GhostsTab::refStillValid(a);
    ok=ok&&GhostsTab::loadRef(a,true,false)&&GhostsTab::loadRef(b,true,true);
    out[2]=loaded[0];out[3]=loaded[1];char name[2];
    ok=ok&&GhostsTab::copyRefName(a,name,2);out[4]=name[0];return ok;
}
extern "C" __declspec(dllexport) int reordered(){
    GhostStorage::first[0]=0;GhostsTab::GhostRef a,b;
    GhostsTab::captureRef(GhostsTab::PERSONAL_SELECTION_FIRST+1,&a);
    GhostStorage::first[0]=1;GhostsTab::captureRef(GhostsTab::PERSONAL_SELECTION_FIRST,&b);
    return GhostsTab::sameRef(a,b);
}
extern "C" __declspec(dllexport) u32 turnPage(int imported,u32 total,u32 offset,int direction,int *out){
    GhostStorage::first[imported]=offset;GhostStorage::totals[imported]=total;
    GhostsTab tab;Menu menu;tab.mSel=imported?GhostsTab::IMPORTED_PAGE_SELECTION:GhostsTab::PERSONAL_PAGE_SELECTION;
    tab.changePage(&menu,direction);*out=GhostStorage::requestImported;return GhostStorage::requested;
}
extern "C" __declspec(dllexport) int selection(int n){return GhostsTab::selectionRow(n);}
extern "C" __declspec(dllexport) int selections(){return GhostsTab::SELECTION_COUNT;}
'''.replace("ROWS", rows).replace("REF", ref).replace("METHODS", methods)
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        file = Path(cls.folder.name) / "ghost_menu.cpp"
        file.write_text(shim + body, encoding="ascii")
        dll = file.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(file), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.turnPage.argtypes = [C.c_int, C.c_uint, C.c_uint, C.c_int, C.POINTER(C.c_int)]
        cls.lib.turnPage.restype = C.c_uint

    def test_watch_two_retains_first_file_after_browsing_another_page(self):
        for imported in (0, 1):
            out = (C.c_uint * 5)()
            self.assertEqual(self.lib.crossPage(imported, out), 1)
            self.assertEqual(list(out), [0, 1, 0, 160, ord("A")])

    def test_same_file_cannot_be_second_ghost_after_rows_reorder(self):
        self.assertEqual(self.lib.reordered(), 1)

    def test_paging_crosses_old_limits_and_wraps_without_integer_overflow(self):
        for imported in (0, 1):
            for total, current, direction, expected in (
                    (0, 0, 1, 0), (1, 0, -1, 0), (100, 0, -1, 96),
                    (100, 16, 1, 32), (100, 96, 1, 0),
                    (0xffffffff, 0, -1, 0xfffffff0), (0xffffffff, 0xfffffff0, 1, 0)):
                destination = C.c_int()
                self.assertEqual(self.lib.turnPage(imported, total, current, direction,
                                                   C.byref(destination)), expected)
                self.assertEqual(destination.value, imported)

    def test_each_selectable_row_has_a_unique_ordered_display_row(self):
        rows = [self.lib.selection(i) for i in range(self.lib.selections())]
        self.assertEqual(rows, sorted(set(rows)))


if __name__ == "__main__":
    unittest.main()
