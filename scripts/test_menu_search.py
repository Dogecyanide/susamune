"""Exercise the real search matcher, controller keyboard and action release gate."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class MenuSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-search-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / "src/menu_search.inc").read_text()
        keyboard = (ROOT / "src/creation_extras.cpp").read_text()
        header = (ROOT / "include/susamune/menu_search.hxx").read_text()
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        state = function(header, "namespace MenuSearch")
        matcher = source[source.index("static char lower"):source.index("\nenum Kind")]
        methods = "\n".join(function(source, signature) for signature in (
            "bool Menu::searchActive() const",
            "void Menu::openSearch()",
            "void Menu::cacheSearch(bool recount)",
            "void Menu::updateSearch(TMarioGamePad *pad)",
        ))
        code = r'''
using u8=unsigned char;using u16=unsigned short;using u32=unsigned;
extern "C" void *memset(void *p,int c,decltype(sizeof(0)) n){
 volatile unsigned char *b=(unsigned char*)p;for(decltype(n)i=0;i<n;++i)b[i]=c;return p;
}
extern "C" void *memcpy(void *p,const void *q,decltype(sizeof(0)) n){
 volatile unsigned char *b=(unsigned char*)p;const unsigned char*a=(const unsigned char*)q;
 for(decltype(n)i=0;i<n;++i)b[i]=a[i];return p;
}
struct JUTGamePad {
 enum {A=0x100,B=0x200,X=0x400,Y=0x800,Z=0x10,START=0x1000,L=0x40,R=0x20};
 struct Status {u16 mButton;};static Status mPadStatus[1];
};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad:JUTGamePad {
 enum {DPAD_LEFT=1,DPAD_RIGHT=2,DPAD_DOWN=4,DPAD_UP=8,
       CSTICK_UP=0x10000,CSTICK_DOWN=0x20000};
 u32 nav=0;
};
constexpr u16 SUSAMUNE_BIND_BUTTON_MASK=0x1f7f;
int wrap(int value,int count){return (value+count)%count;}
int listScrollStart(int selected,int count,int visible){
 if(count<=visible)return 0;int first=selected-visible/2;
 if(first<0)first=0;if(first>count-visible)first=count-visible;return first;
}
#define SEARCH_CODE(name)
''' + raw + state + r'''
namespace MenuSearch {
''' + matcher + r'''
}
struct Runtime{MenuSearch::State search;}sMenuRuntime;
const char gCreationSymbols[]="0123456789.,:;!?+-*/()[]{}<>_=@#$%";
const char gCreationLettersLower[33]="abcdefghijklmnopqrstuvwxyz012345";
const char gCreationLettersUpper[33]="ABCDEFGHIJKLMNOPQRSTUVWXYZ012345";
''' + function(keyboard, "bool updateCreationKeyboardButtons(") + r'''
struct Menu {
 bool available=true;int opened=-1,opens=0;unsigned rowCount=4,visits=0;
 bool searchAvailable()const{return available&&!searchActive();}
 bool searchActive()const;void openSearch();void updateSearch(TMarioGamePad*);void cacheSearch(bool);
 u32 navigationInput(TMarioGamePad *p){return p->nav;}
 bool searchEntry(unsigned index,MenuSearch::Entry&entry,bool open=false) {
  ++visits;
  static const MenuSearch::Entry rows[]={
   {"Save to","Practice","Savestates",nullptr},
   {"Factory reset","Practice","Helpers",nullptr},
   {"Value gap","Display","Metadata","Layout"},
   {"Fast text","System","Button binds","Practice codes"}
  };
  if(index==MenuSearch::kCollectResults){
   unsigned match=0;
   for(unsigned i=0;i<rowCount;++i)MenuSearch::collect(sMenuRuntime.search,rows[i%4],i,match);
   sMenuRuntime.search.count=match;return false;
  }
  if(index>=rowCount)return false;entry=rows[index%4];
  if(open){opened=index;++opens;}return true;
 }
};
''' + methods + r'''
static Menu menu;
static void frame(unsigned buttons,unsigned nav=0){
 JUTGamePad::mPadStatus[0].mButton=buttons;
 TMarioGamePad pad;pad.nav=nav;
 if(menu.searchActive())menu.updateSearch(&pad);
}
static void pulse(unsigned buttons,unsigned nav=0){frame(buttons,nav);frame(0);}
#define API extern "C" __declspec(dllexport)
API int match(const char *query,const char *label,const char *section,const char *group,const char *page){
 return MenuSearch::matches(query,{label,section,group,page});
}
API void reset(unsigned openingHeld){
 menu=Menu{};sMenuRuntime={};JUTGamePad::mPadStatus[0].mButton=openingHeld;menu.openSearch();
}
API void tick(unsigned buttons,unsigned nav){frame(buttons,nav);}
API void press(unsigned buttons,unsigned nav){pulse(buttons,nav);}
API void query(const char *text){
 auto&s=sMenuRuntime.search;s.length=0;while(text[s.length])++s.length;
 memcpy(s.query,text,s.length+1);
}
API const char* text(){return sMenuRuntime.search.query;}
API unsigned mode(){return sMenuRuntime.search.mode;}
API unsigned count(){return sMenuRuntime.search.count;}
API unsigned selected(){return sMenuRuntime.search.selected;}
API int opened(){return menu.opened;}
API int opens(){return menu.opens;}
API unsigned visits(){return menu.visits;}
API void rows(unsigned count){menu.rowCount=count;}
API unsigned first(){return sMenuRuntime.search.first;}
API unsigned result(unsigned row){return sMenuRuntime.search.results[row].index;}
API unsigned storage(){return sizeof(MenuSearch::State);}
'''
        path = Path(cls.temp.name)
        (path / "test.cpp").write_text(code)
        dll = path / "search.dll"
        built = subprocess.run([str(ROOT / "toolchain/clang++.exe"), "-std=c++17", "-shared",
                        "--target=x86_64-pc-windows-msvc", "-nostdlib", "-fuse-ld=lld",
                        "-Wl,/noentry", "-fno-rtti", "-fno-exceptions", "-O2",
                        "-Wno-unknown-pragmas", str(path / "test.cpp"), "-o", str(dll)],
                       capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stdout + built.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.match.argtypes = [C.c_char_p] * 5
        cls.lib.query.argtypes = [C.c_char_p]
        cls.lib.text.restype = C.c_char_p

    def setUp(self):
        self.lib.reset(0)

    def test_keywords_use_label_and_path_without_values(self):
        args = (b"Value gap", b"Display", b"Metadata", b"Layout")
        for query in (b"value", b"VALUE", b"metadata gap", b"  gap\tDISPLAY  ", b""):
            self.assertTrue(self.lib.match(query, *args), query)
        for query in (b"value missing", b"gapgap", b"null", b"40"):
            self.assertFalse(self.lib.match(query, *args), query)
        self.assertTrue(self.lib.match(b"save", b"Save to", b"Practice", None, None))
        self.assertFalse(self.lib.match(b"states", b"Save to", b"Practice", None, None))

    def test_keyboard_is_release_gated_bounded_and_clearable(self):
        self.lib.reset(0x800)
        self.lib.tick(0x100, 0)
        self.assertEqual(self.lib.text(), b"")
        self.lib.tick(0, 0)
        self.lib.press(0x100, 0)
        self.assertEqual(self.lib.text(), b"a")
        self.lib.press(0x200, 0)
        self.assertEqual(self.lib.text(), b"")
        for _ in range(40):
            self.lib.press(0x100, 0)
        self.assertEqual(self.lib.text(), b"a" * 31)
        self.lib.press(0x10, 0)
        self.assertEqual(self.lib.text(), b"")
        self.assertLessEqual(self.lib.storage(), 296)

    def test_select_opens_once_and_waits_for_release(self):
        self.lib.query(b"factory")
        self.lib.press(0x1000, 0)
        self.assertEqual((self.lib.mode(), self.lib.count()), (2, 1))
        self.lib.tick(0x100, 0)
        self.assertEqual((self.lib.opened(), self.lib.opens(), self.lib.mode()), (1, 1, 3))
        for _ in range(8):
            self.lib.tick(0x100, 0)
        self.assertEqual((self.lib.opens(), self.lib.mode()), (1, 3))
        self.lib.tick(0, 0)
        self.assertEqual(self.lib.mode(), 0)

    def test_results_wrap_edit_and_cancel_without_action(self):
        self.lib.press(0x1000, 0)
        self.assertEqual(self.lib.count(), 4)
        self.lib.press(0, 0x10000)
        self.assertEqual(self.lib.selected(), 3)
        self.lib.press(0, 0x20000)
        self.assertEqual(self.lib.selected(), 0)
        self.lib.press(0x200, 0)
        self.assertEqual(self.lib.mode(), 1)
        self.lib.query(b"nothing")
        self.lib.press(0x1000, 0)
        self.assertEqual(self.lib.count(), 0)
        self.lib.press(0x100, 0)
        self.assertEqual(self.lib.opens(), 0)
        self.lib.tick(0x1400, 0)
        self.assertEqual(self.lib.mode(), 3)
        self.lib.tick(0, 0)
        self.assertEqual(self.lib.mode(), 0)
        self.assertEqual(self.lib.opens(), 0)

    def test_large_catalogue_scans_once_and_scroll_keeps_exact_routes(self):
        self.lib.rows(1024)
        self.lib.query(b"fast text")
        self.lib.press(0x1000, 0)
        self.assertEqual((self.lib.count(), self.lib.visits()), (256, 1))
        self.assertEqual([self.lib.result(i) for i in range(6)], [3, 7, 11, 15, 19, 23])
        self.lib.press(0, 0x10000)
        self.assertEqual((self.lib.selected(), self.lib.first(), self.lib.visits()), (255, 250, 2))
        self.assertEqual(self.lib.result(5), 1023)
        self.lib.press(0x100, 0)
        self.assertEqual((self.lib.opened(), self.lib.opens()), (1023, 1))


if __name__ == "__main__":
    unittest.main()
