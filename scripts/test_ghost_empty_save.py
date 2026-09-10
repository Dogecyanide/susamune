"""Empty personal rows use the production save path, without a refresh loop."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class EmptyGhostSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        source = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        source = source[source.index("class GhostsTab :"):]
        methods = "\n".join(function(source, name) for name in (
            "bool isPersonalSlot() const", "int selectedPersonalSlot() const",
            "bool onPageRow() const", "void beginNewSave(",
            "bool isEmptySaveRow() const"))
        activate = function(source, "void activate(Menu *menu)")
        save_route = activate[:activate.index("        if (mSel == INPUTS_ROW)")] + "}"
        rows = function(source, "enum {\n        RANGE_SIZE") + ";"
        shim = r'''
typedef unsigned u32;
#define SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES 16
#define SUSAMUNE_GHOST_SLOT_PRESENT 1
#define SUSAMUNE_GHOST_SLOT_UNSAFE 2
struct SusamuneGhostSlotInfo {u32 flags;};
namespace JUTGamePad {enum {A=1,B=2};}
namespace GhostStorage {
static bool ready,active,haveInfo;static SusamuneGhostSlotInfo info;
bool catalogReady(){return ready;}bool busy(){return active;}
const SusamuneGhostSlotInfo *slot(int row){return haveInfo?&info:0;}
}
namespace Ghost {
static bool recording;
bool copySaveableName(char *name,u32 size,u32 *token){
 if(!recording)return false;name[0]='G';name[1]=0;*token=42;return true;
}
}
struct Menu {int toasts;void toast(const char*){toasts++;}};
struct Prompt {int count,mask;void begin(int buttons){count++;mask=buttons;}};
class GhostsTab {
public:
ROWS
int mSel;bool mConfirmSave;u32 mSaveIdentity;char mSaveName[48];Prompt mPromptInput;
static const char *storageStatus(){return "Busy";}
void changePage(Menu*,int){}
METHODS
ROUTE
};
extern "C" __declspec(dllexport) int run(int selection,int ready,int have,int flags,int busy,int recording){
 GhostStorage::ready=ready;GhostStorage::active=busy;GhostStorage::haveInfo=have;
 GhostStorage::info.flags=flags;Ghost::recording=recording;
 GhostsTab tab;tab.mSel=selection;tab.mConfirmSave=false;tab.mSaveIdentity=0;
 tab.mPromptInput.count=tab.mPromptInput.mask=0;Menu menu;menu.toasts=0;
 tab.activate(&menu);
 if(tab.mConfirmSave)return tab.mSaveIdentity==42&&tab.mPromptInput.count==1&&tab.mPromptInput.mask==3?1:99;
 return menu.toasts?2:0;
}
'''.replace("ROWS", rows).replace("METHODS", methods).replace("ROUTE", save_route)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        (path / "empty.cpp").write_text(shim, encoding="ascii")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(path / "empty.cpp"), "-o", str(path / "empty.dll")], check=True)
        cls.lib = C.CDLL(str(path / "empty.dll"))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.run.argtypes = [C.c_int] * 6
        cls.lib.run.restype = C.c_int

    def test_every_empty_personal_row_opens_save_with_exact_recording(self):
        for row in range(10, 26):
            for have_info in (0, 1):
                self.assertEqual(self.lib.run(row, 1, have_info, 0, 0, 1), 1)

    def test_unscanned_occupied_unsafe_and_imported_rows_do_not_become_saves(self):
        for args in ((10, 0, 0, 0, 0, 1), (10, 1, 1, 1, 0, 1),
                     (10, 1, 1, 2, 0, 1), (28, 1, 0, 0, 0, 1)):
            self.assertEqual(self.lib.run(*args), 0)

    def test_busy_or_missing_recording_reports_without_opening_confirmation(self):
        self.assertEqual(self.lib.run(10, 1, 0, 0, 1, 1), 2)
        self.assertEqual(self.lib.run(10, 1, 0, 0, 0, 0), 2)

    def test_explicit_save_row_does_not_need_a_catalog_scan(self):
        self.assertEqual(self.lib.run(9, 0, 0, 0, 0, 1), 1)


if __name__ == "__main__":
    unittest.main()
