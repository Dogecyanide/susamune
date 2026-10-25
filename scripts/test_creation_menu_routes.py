"""Execute production Creation navigation and editor-routing methods."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class CreationMenuRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        src = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        creation = src[src.index("class CreationTab final"):]
        methods = "\n".join(function(creation, signature).replace(" override", "")
                            for signature in ("void focus() override", "bool back() override",
                                "void update(Menu *menu, TMarioGamePad *pad) override",
                                "int pageFirst() const", "int pageEnd() const",
                                "void moveSelection(", "void activate(",
                                "static int groupCount(", "static int groupPage(", "static int pageGroup(",
                                "static int inputRow(", "static int metadataRow(",
                                "static int extraRow(", "static int rowSetting(", "static int rowFavorite("))
        rows = function(creation, "enum Row") + ";"
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        movement = function(src, "const u8 kDisplayMovementSettings[]") + ";"
        movement_method = function(src, "bool hasMovementEditors() const")
        shim = r'''
#include "susamune/settings_list.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
#define ID(name,key) name,
enum SettingId { SUSAMUNE_SETTING_LIST(ID) SETTING_COUNT, SETTING_BUTTSLIDE_DISPLAY = SETTING_COUNT };
#undef ID
enum { SUSAMUNE_CREATION_TIMER_BG=1,SUSAMUNE_CREATION_TIMER_LABEL=2 };
#define SUSAMUNE_GLYPH_SLASH "/"
struct JUTGamePad { enum {A=0x100,B=0x200,X=0x400};struct Status{u16 mButton;};static Status mPadStatus[1]; };
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad { enum{CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8};u32 nav; };
struct Menu { u32 navigationInput(TMarioGamePad *pad) {return pad->nav;} };
int wrap(int value,int count) {return (value+count)%count;}
static int owner,row,direction,actions;
void hit(int o,int r,int d=1) {owner=o;row=r;direction=d;++actions;}
struct Editor {
    bool active=false;int id;
    bool editing() {return active;}
    void updateEditor(TMarioGamePad*) {}
    void beginEditor() {hit(id,99);}
    void toggleLeadingZero() {hit(id,98);}
    void adjustMenuRow(int r,int d) {hit(id,r,d);}
};
namespace FinishBreakdown { bool editing(){return false;} void updateEditor(Menu*,TMarioGamePad*){} void beginEditor(){hit(7,99);} }
struct InputDisplay:Editor {enum{MENU_ROW_COUNT=6};};
struct MetadataDisplay:Editor {enum{FIELD_COUNT=11};static constexpr int menuRowCount(){return 21;} };
struct CreationExtras:Editor {
    enum{MENU_ROW_COUNT=25};
    void beginNativeTimerEditor(){hit(4,100);}
    void beginTimerCharacterEditor(){hit(4,101);}
    void beginColorEditor(int c,int,const char*){hit(4,102+c);}
    void toggleTimerLabel(){hit(4,105);}
    void beginHealthEditor(bool air){hit(4,air?107:106);}
    void beginWallkickEditor(){hit(4,108);}
    void beginRolloutEditor(){hit(4,109);}
    void beginDustEditor(){hit(4,110);}
    void beginPracticeDisplayEditor(unsigned display){hit(4,113+display);}
    void beginSavestateFeedbackEditor(){hit(4,111);}
    void beginRecentIlEditor(){hit(4,112);}
};
Editor gQftDisplay;InputDisplay gInputDisplay;MetadataDisplay gMetadataDisplay;CreationExtras gCreationExtras;
struct Settings{void cycle(int id,int d){hit(5,id,d);}static bool favoriteable(int id){return id>=0;}}gSettings;
void toggleMenuFavorite(Menu*,int id){hit(6,id);}
void reset() {owner=row=direction=actions=0;JUTGamePad::mPadStatus[0].mButton=0;
    gQftDisplay.id=1;gInputDisplay.id=2;gMetadataDisplay.id=3;gCreationExtras.id=4;}
'''
        shim += "namespace DisplayFavorites {" + function(src[src.index("namespace DisplayFavorites"):], "enum Item") + ";}"
        shim += "const int kDisplayFavoriteFirst=SETTING_COUNT+1;"
        more = r'''
class CreationTab {
public:
    CreationTab():mSel(0),mPage(0){mInput.begin(JUTGamePad::A | JUTGamePad::X);}
ROWS
METHODS
    u8 mSel,mPage;RawPromptInput mInput;
};
MOVEMENT
class CategorySettingsTab {
public:
    bool display;int mMode;struct Page{const u8 *ids;}page;
    bool isDisplay()const{return display;}
    const Page&currentPage()const{return page;}
MOVEMENT_METHOD
};
extern "C" __declspec(dllexport) int pageCount() { return CreationTab::PAGE_COUNT; }
extern "C" __declspec(dllexport) int groupCount() { return CreationTab::GROUP_COUNT; }
extern "C" __declspec(dllexport) int groupItems(int group) { return CreationTab::groupCount(group); }
extern "C" __declspec(dllexport) int groupPage(int group,int item) { return CreationTab::groupPage(group,item); }
extern "C" __declspec(dllexport) int pageGroup(int page) { return CreationTab::pageGroup(page); }
extern "C" __declspec(dllexport) int separatorSetting() { return SETTING_NATIVE_TIMER_DECIMAL_SEPARATOR; }
extern "C" __declspec(dllexport) int rowCount() { return CreationTab::ROW_COUNT; }
extern "C" __declspec(dllexport) int headerRow(int which) {
    const int rows[]={CreationTab::ROW_QFT_HEADER,CreationTab::ROW_INPUT_HEADER,
        CreationTab::ROW_METADATA_HEADER,CreationTab::ROW_EXTRAS_FIRST,
        CreationTab::ROW_EXTRAS_FIRST+10,CreationTab::ROW_EXTRAS_FIRST+20};
    return rows[which];
}
extern "C" __declspec(dllexport) int rootAction(int page,int nav,int held,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};tab.mSel=page;pad.nav=nav;
    JUTGamePad::mPadStatus[0].mButton=(u16)held;tab.update(&menu,&pad);
    out[0]=tab.mPage;out[1]=tab.mSel;return actions;
}
extern "C" __declspec(dllexport) int range(int page,int end) {
    CreationTab tab;tab.mPage=page+1;return end?tab.pageEnd():tab.pageFirst();
}
extern "C" __declspec(dllexport) int groupAction(int group,int item,int nav,int held,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};
    tab.mPage=CreationTab::PAGE_COUNT+group+1;tab.mSel=item;pad.nav=nav;
    JUTGamePad::mPadStatus[0].mButton=(u16)held;tab.update(&menu,&pad);
    out[0]=tab.mPage;out[1]=tab.mSel;return actions;
}
extern "C" __declspec(dllexport) int route(int page,int local,int nav,int held,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};
    tab.mPage=page+1;tab.mSel=tab.pageFirst()+local;pad.nav=nav;
    JUTGamePad::mPadStatus[0].mButton=(u16)held;tab.update(&menu,&pad);
    out[0]=owner;out[1]=row;out[2]=direction;out[3]=tab.mSel-tab.pageFirst();return actions;
}
extern "C" __declspec(dllexport) int entry(int page,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};
    const int group=tab.pageGroup(page);tab.mPage=CreationTab::PAGE_COUNT+group+1;
    while(tab.groupPage(group,tab.mSel)!=page)++tab.mSel;
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;tab.update(&menu,&pad);
    for(int i=0;i<20;i++)tab.update(&menu,&pad);
    out[0]=actions;out[1]=tab.mPage;
    JUTGamePad::mPadStatus[0].mButton=0;tab.update(&menu,&pad);
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;tab.update(&menu,&pad);
    out[2]=actions;out[3]=owner;out[4]=row;
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::B;
    bool back=tab.back();out[5]=tab.mPage;out[6]=tab.mSel;
    for(int i=0;i<20;i++)tab.update(&menu,&pad);
    out[7]=actions;return back;
}
extern "C" __declspec(dllexport) int movementPage(int display,int mode,int same) {
    static const u8 other[]={0};CategorySettingsTab tab;
    tab.display=display!=0;tab.mMode=mode;tab.page.ids=same?kDisplayMovementSettings:other;
    return tab.hasMovementEditors();
}
'''.replace("MOVEMENT_METHOD", movement_method).replace("MOVEMENT", movement)
        more = more.replace("ROWS", rows).replace("METHODS", methods)
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        file = Path(cls.folder.name) / "creation.cpp"
        file.write_text(shim + raw + more, encoding="ascii")
        dll = file.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(file), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def route(self, page, local, nav=0, held=0x100):
        out = (C.c_int * 4)()
        count = self.lib.route(page, local, nav, held, out)
        return count, list(out)

    def test_eighteen_item_pages_expose_every_action_once_and_no_headers(self):
        self.assertEqual(self.lib.pageCount(), 18)
        ranges = [range(self.lib.range(p, 0), self.lib.range(p, 1)) for p in range(18)]
        self.assertEqual([len(rows) for rows in ranges],
                         [3, 7, 7, 21, 9, 3, 3, 3] + [2] * 8 + [10, 2])
        exposed = [row for rows in ranges for row in rows]
        headers = {self.lib.headerRow(i) for i in range(6)}
        self.assertEqual(len(exposed), len(set(exposed)))
        self.assertEqual(set(exposed), set(range(self.lib.rowCount())) - headers)
        for page, rows in enumerate(ranges):
            for local in range(len(rows)):
                self.assertEqual(self.route(page, local)[0], 1, (page, local))

    def test_breakdown_toggle_and_editor_are_adjacent(self):
        self.assertEqual(self.route(17, 0)[1][0], 5)
        self.assertEqual(self.route(17, 1)[1][:2], [7, 99])
        self.assertEqual(self.route(17, 1, held=0x400)[0], 0)

    def test_native_timer_controls_remain_together(self):
        self.assertEqual(self.route(1, 0)[1][0], 5)
        for local, action in ((1, 100), (2, 101), (4, 103), (5, 104), (6, 105)):
            self.assertEqual(self.route(1, local)[1][:2], [4, action])
        self.assertEqual(self.route(1, 3)[1][:2], [5, self.lib.separatorSetting()])

    def test_health_air_custom_words_and_notification_editors(self):
        for page, local, row in ((4, 7, 106), (4, 8, 107), (16, 0, 19), (16, 4, 23)):
            count, out = self.route(page, local)
            self.assertEqual((count, out[:3]), (1, [4, row, 1]))
        for page in range(5, 8):
            for local in range(3):
                self.assertEqual(self.route(page, local)[1][:2], [4, 9 + (page - 5) * 3 + local])
        for page, row in enumerate((108, 113, 114, 115, 109, 110, 111, 112), start=8):
            self.assertEqual(self.route(page, 1)[1][:2], [4, row])

    def test_metadata_visibility_and_style_share_page_with_all_twenty_one_actions(self):
        expected = [0, 14, 13, 20, 16, 19, 17, 18] + list(range(1, 13)) + [15]
        for local, row in enumerate(expected):
            self.assertEqual(self.route(3, local)[1][:3], [3, row, 1])

    def test_display_visibility_and_style_are_adjacent(self):
        for page, local, owner, action in ((2, 0, 2, 0), (2, 1, 2, 4),
                                         (3, 0, 3, 0), (3, 1, 3, 14)):
            self.assertEqual(self.route(page, local)[1][:2], [owner, action])
        self.assertEqual(self.route(0, 0)[1][0], 5)
        self.assertEqual(self.route(0, 1)[1][:2], [1, 99])
        for page in range(8, 16):
            self.assertEqual(self.route(page, 0)[1][0], 5)
            self.assertEqual(self.route(page, 1)[1][0], 4)

    def test_x_shines_display_options_without_toggling_or_opening_editor(self):
        for page, local in ((0, 0), (0, 2), (1, 0), (1, 3), (1, 6),
                            (2, 0), (2, 2), (2, 3), (2, 4), (2, 6), (3, 0),
                            (3, 2), (3, 4), (3, 15), (3, 17), (3, 5),
                            (5, 2), (6, 2), (7, 2), (8, 0), (11, 0),
                            (16, 6), (16, 9), (17, 0)):
            count, out = self.route(page, local, held=0x400)
            self.assertEqual((count, out[0]), (1, 6), (page, local))
        for page, local in ((0, 1), (1, 1), (2, 1), (2, 5), (3, 1), (3, 20),
                            (4, 7), (5, 0), (5, 1), (8, 1), (16, 0), (17, 1)):
            self.assertEqual(self.route(page, local, held=0x400)[0], 0, (page, local))

    def test_new_metadata_geometry_has_bidirectional_controls_without_opening_editors(self):
        for local, row in ((3, 20), (4, 16), (5, 19), (6, 17), (7, 18)):
            for nav, direction in ((4, -1), (8, 1)):
                self.assertEqual(self.route(3, local, nav, 0), (1, [3, row, direction, local]))
        for local in (0, 20):
            self.assertEqual(self.route(3, local, 4, 0)[0], 0)

    def test_navigation_wraps_within_each_item_page(self):
        for page in range(18):
            count = self.lib.range(page, 1) - self.lib.range(page, 0)
            self.assertEqual(self.route(page, 0, 1, 0)[1][3], count - 1)
            self.assertEqual(self.route(page, count - 1, 2, 0)[1][3], 0)

    def test_held_A_enters_item_only_and_back_keeps_selected_item(self):
        for page in range(18):
            out = (C.c_int * 8)()
            self.assertEqual(self.lib.entry(page, out), 1)
            self.assertEqual(list(out[:3]), [0, page + 1, 1])
            group = self.lib.pageGroup(page)
            items = [self.lib.groupPage(group, i) for i in range(self.lib.groupItems(group))]
            self.assertEqual(list(out[5:]), [19 + group, items.index(page), 1])

    def test_root_groups_do_not_toggle_or_edit_and_navigation_wraps(self):
        out = (C.c_int * 2)()
        for group in range(4):
            self.assertEqual(self.lib.rootAction(group, 0, 0x400, out), 0)
            self.assertEqual(list(out), [0, group])
            self.assertEqual(self.lib.rootAction(group, 0, 0x100, out), 0)
            self.assertEqual(list(out), [19 + group, 0])
        self.assertEqual(self.lib.rootAction(0, 1, 0, out), 0)
        self.assertEqual(list(out), [0, 3])
        self.assertEqual(self.lib.rootAction(3, 2, 0, out), 0)
        self.assertEqual(list(out), [0, 0])

    def test_groups_cover_all_items_once_and_preserve_item_routes(self):
        self.assertEqual(self.lib.groupCount(), 4)
        out = (C.c_int * 2)()
        pages = []
        for group in range(4):
            count = self.lib.groupItems(group)
            for item in range(count):
                page = self.lib.groupPage(group, item)
                pages.append(page)
                self.assertEqual(self.lib.pageGroup(page), group)
                self.assertEqual(self.lib.groupAction(group, item, 0, 0x100, out), 0)
                self.assertEqual(list(out), [page + 1, self.lib.range(page, 0)])
            self.assertEqual(self.lib.groupAction(group, 0, 1, 0, out), 0)
            self.assertEqual(list(out), [19 + group, count - 1])
            self.assertEqual(self.lib.groupAction(group, count - 1, 2, 0, out), 0)
            self.assertEqual(list(out), [19 + group, 0])
        self.assertEqual(sorted(pages), list(range(18)))

    def test_movement_editors_follow_the_settings_list_after_page_reordering(self):
        for mode in range(1, 8):
            self.assertEqual(self.lib.movementPage(1, mode, 1), 1)
            self.assertEqual(self.lib.movementPage(1, mode, 0), 0)
            self.assertEqual(self.lib.movementPage(0, mode, 1), 0)
        self.assertEqual(self.lib.movementPage(1, 0, 1), 0)


if __name__ == "__main__":
    unittest.main()
