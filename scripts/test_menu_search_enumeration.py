"""Run the production built-in enumerator with bounded fake menu catalogues."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class SearchEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-search-scan-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / "src/menu_search.inc").read_text()
        header = (ROOT / "include/susamune/menu_search.hxx").read_text()
        state = function(header, "namespace MenuSearch")
        matcher = source[source.index("static char lower"):source.index("\nenum Kind")]
        groups = source[source.index("enum Kind"):source.index("#undef SEARCH_GROUP")]
        fields = "tasProject practiceControls savestate misc rng qol iling stageLoader streaking pbSafety timer creation layoutProfiles ui cosmetic binds guide ghosts soundDisplay online settingsHub ilsHub displayHub systemHub".split()
        code = r'''
using u8=unsigned char;using u16=unsigned short;using u32=unsigned;
extern "C" void *memset(void*p,int c,decltype(sizeof(0))n){
 volatile u8*b=(u8*)p;for(decltype(n)i=0;i<n;++i)b[i]=c;return p;
}
extern "C" void *memcpy(void*p,const void*q,decltype(sizeof(0))n){
 volatile u8*b=(u8*)p;const u8*a=(const u8*)q;for(decltype(n)i=0;i<n;++i)b[i]=a[i];return p;
}
struct RawPromptInput {void begin(unsigned){}};
constexpr unsigned SUSAMUNE_BIND_BUTTON_MASK=0x1f7f;
#define SEARCH_CODE(name)
#define ENABLE_DEBUG_WARPS 0
#define TIMEWARP_LIVE_RACING 1
''' + state + r'''
unsigned labels=0,catalogueReads=0;
struct Page {const char*name;int first,count;};
const Page kBindPages[]={{"Page A",0,2},{"Page B",2,2}};
struct Tab {
 enum {PAGE_COUNT=2,GROUP_COUNT=4,MAIN=0,CHECKPOINTS=1,ROW_SD=1,SD_FILES=2,ROW_COUNT=3,
       OPTION_COUNT=2,SAVE_NEW_SELECTION=2,IMPORT_SCAN_SELECTION=6,
       IMPORTED_PAGE_SELECTION=7,CHOICE_VISUALS=1,CHOICE_NONE=0};
 int mPage=0,mSel=0,mMode=0,mSD=0,mSDsel=0,mChoice=0,mTopRow=0;
 using Option=int;static constexpr int OPTION_FAILURE=0;
 bool mPbPage=false,mFailurePage=false,mStreaking=false;
 bool filtered=false;Tab*mParent=nullptr;Tab*child=nullptr;RawPromptInput mPromptInput;
 const char*title(){++labels;return "Menu";}
 void focus(){}void openChild(Tab*t){child=t;}
 void openSearchRow(int row){mSel=row;}
 bool hasPages(){return true;}
 bool isTimer(){return false;}
 static int pageCount(){return 2;}
 const Page*pages(){return kBindPages;}
 int buildList(u8*ids){ids[0]=0;ids[1]=1;return 2;}
 int extraRows(){return 1;}const char*extraRowName(int){++labels;return "Extra";}
 int pageFirst(){return mPage*2;}int pageEnd(){return mPage*2+2;}
 static const char*pageName(int i){++labels;return i?"Page B":"Page A";}
 static const char*groupName(int i){++labels;static const char*names[]={"Timers","Inputs & movement","HUD & messages","Custom text"};return names[i];}
 static const char*rowName(int i,int=0){++labels;return i%2?"Odd row":"Even row";}
 static int bindAt(int i){return i;}
 int rowCount(){return 3;}
 static const char*optionName(int){++labels;return "Option";}
 int optionCount(){return 3;}int optionAt(int i){return i;}
 bool catalogueIncludesEntry(int i){return !filtered || i%2==0;}
 int catalogueFirst(){return filtered?3:20;}
};
using MenuTab=Tab;using CategorySettingsTab=Tab;using CreationTab=Tab;using BindsTab=Tab;
using TasProjectTab=Tab;using PracticeControlsTab=Tab;using SavestatesTab=Tab;
using ILingTab=Tab;using StageLoaderTab=Tab;using PBSafetyTab=Tab;using GhostsTab=Tab;
using GuideTab=Tab;using MenuSoundsDisplayTab=Tab;using OnlineTab=Tab;using NestedMenuTab=Tab;
constexpr int kMenuSettingCount=8,kDisplayFavoriteFirst=100;
using SettingId=int;
bool displayFavoriteId(int){return false;}
namespace DisplayFavorites{const char*name(int){return "Favorite";}}
namespace SectionHistoryDisplay{const char*name(unsigned){return "History";}}
namespace Settings{
 const char*name(int){++labels;return "Setting";}
 int ilPbSettingCount(){return 3;}int ilPbSettingAt(int i){return i;}
}
namespace Binds{const char*name(int){++labels;return "Bind";}}
namespace ILing{
 int count(){return 133;}
 int menuEntryAt(int p){++catalogueReads;return 132-p;}
 const char*label(int i){++labels;return i%2?"Odd IL":"Even IL";}
 const char*menuGroupName(int){return "Level";}
}
namespace GhostVisualMenu{
 const char*kTitle="Ghost visuals";constexpr int kCount=2;
 int kSettings[]={0,1};bool hiddenSelection(int i){return i==1;}
}
struct MenuRuntime {
''' + "\n".join(f"alignas(Tab) u8 {name}[sizeof(Tab)];" for name in fields) + r'''
 MenuSearch::State search;
}sMenuRuntime;
struct Menu {
 Tab*mTabs[8];int mNumTabs=8,mCurTab=0,mTabFirst=0,mCRepeatFrames=0;
 bool searchEntry(unsigned,MenuSearch::Entry&,bool=false);
};
namespace MenuSearch {
''' + matcher + groups + "\n#undef SEARCH_GROUP\n}\n" + function(source, "bool Menu::searchEntry(") + r'''
Tab tops[8];Menu menu;
#define API extern "C" __declspec(dllexport)
API void reset(){
 sMenuRuntime={};menu={};menu.mNumTabs=8;
 for(int i=0;i<8;++i)menu.mTabs[i]=tops+i;
 for(const auto&g:MenuSearch::groups){
  auto*t=reinterpret_cast<Tab*>(reinterpret_cast<u8*>(&sMenuRuntime)+g.offset);
  *t=Tab{};t->mParent=reinterpret_cast<Tab*>(sMenuRuntime.displayHub);
 }
 reinterpret_cast<Tab*>(sMenuRuntime.streaking)->filtered=true;
 labels=catalogueReads=0;
}
API unsigned scan(unsigned first,const char*query){
 auto&s=sMenuRuntime.search;s.first=first;s.visible=0;
 unsigned n=0;while(query[n]&&n<31){s.query[n]=query[n];++n;}s.query[n]=0;
 MenuSearch::Entry entry;menu.searchEntry(MenuSearch::kCollectResults,entry);
 return s.count;
}
API unsigned indexedCount(){
 MenuSearch::Entry entry;unsigned n=0;while(menu.searchEntry(n,entry))++n;return n;
}
API unsigned labelReads(){return labels;}
API unsigned ilReads(){return catalogueReads;}
API unsigned visible(){return sMenuRuntime.search.visible;}
API unsigned index(unsigned row){return sMenuRuntime.search.results[row].index;}
API int same(unsigned row){
 auto&r=sMenuRuntime.search.results[row];MenuSearch::Entry e;
 if(!menu.searchEntry(r.index,e))return 0;
 return e.label==r.entry.label&&e.section==r.entry.section&&e.group==r.entry.group&&e.page==r.entry.page;
}
API int route(unsigned index){
 MenuSearch::Entry entry;return menu.searchEntry(index,entry,true);
}
API int current(){return menu.mCurTab;}
API int loaderSelection(){return reinterpret_cast<Tab*>(sMenuRuntime.stageLoader)->mSel;}
API int streakSelection(){return reinterpret_cast<Tab*>(sMenuRuntime.streaking)->mSel;}
API int creationPage(){return reinterpret_cast<Tab*>(sMenuRuntime.creation)->mPage;}
'''
        path = Path(cls.temp.name)
        (path / "test.cpp").write_text(code)
        dll = path / "search-scan.dll"
        built = subprocess.run([str(ROOT / "toolchain/clang++.exe"), "-std=c++17", "-shared",
                                "--target=x86_64-pc-windows-msvc", "-nostdlib", "-fuse-ld=lld",
                                "-Wl,/noentry", "-fno-rtti", "-fno-exceptions", "-O2",
                                "-Wno-unknown-pragmas", str(path / "test.cpp"), "-o", str(dll)],
                               capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stdout + built.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.scan.argtypes = [C.c_uint, C.c_char_p]

    def setUp(self):
        self.lib.reset()

    def test_full_results_visit_each_catalogue_only_once(self):
        count = self.lib.scan(0, b"")
        new_labels, new_ils = self.lib.labelReads(), self.lib.ilReads()
        self.assertGreater(count, 400)
        self.assertEqual(new_ils, 3 * 133)
        self.lib.reset()
        self.assertEqual(self.lib.indexedCount(), count)
        old_labels, old_ils = self.lib.labelReads(), self.lib.ilReads()
        self.assertGreater(old_labels, new_labels * 100)
        self.assertGreater(old_ils, new_ils * 100)
        print(f"Search work: {count} results; label reads {old_labels}->{new_labels}; "
              f"IL lookups {old_ils}->{new_ils} (same enumerator, indexed vs one pass).")

    def test_paged_and_filtered_results_keep_the_same_builtin_routes(self):
        for query in (b"", b"even il", b"page b", b"ghost visuals", b"no such option"):
            count = self.lib.scan(0, query)
            for first in range(0, count, 6):
                self.assertEqual(self.lib.scan(first, query), count)
                for row in range(self.lib.visible()):
                    self.assertTrue(self.lib.same(row), (query, first, row))
                    self.assertTrue(self.lib.route(self.lib.index(row)))

    def test_loader_routes_skip_user_queue_and_keep_filtered_positions(self):
        count = self.lib.scan(0, b"even il")
        loader, streak = [], []
        for first in range(0, count, 6):
            self.lib.scan(first, b"even il")
            for row in range(self.lib.visible()):
                self.lib.route(self.lib.index(row))
                if self.lib.current() != 2:
                    continue
                # The selected row changes only on the corresponding target.
                if self.lib.loaderSelection() >= 20:
                    loader.append(self.lib.loaderSelection())
                if self.lib.streakSelection() >= 3:
                    streak.append(self.lib.streakSelection())
        self.assertIn(20, loader)
        self.assertIn(152, loader)
        self.assertIn(3, streak)
        self.assertIn(69, streak)

    def test_display_group_search_opens_the_group_not_an_item_editor(self):
        for group, query in enumerate((b"timers", b"inputs & movement", b"hud & messages", b"custom text")):
            self.assertEqual(self.lib.scan(0, query), 1)
            self.assertTrue(self.lib.route(self.lib.index(0)))
            self.assertEqual(self.lib.current(), 5)
            self.assertEqual(self.lib.creationPage(), 3 + group)


if __name__ == "__main__":
    unittest.main()
