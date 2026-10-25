"""Run the Online menu's production routing with stubbed network side effects."""

import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class OnlineMenuRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows host compiler required")
        source = (ROOT / "src/live_race_menu.inc").read_text()
        enums = "\n".join(function(source, "enum " + name) + ";" for name in ("Row", "Mode", "Section"))
        cls.rows = {name: i for i, name in enumerate(re.findall(r"\b[A-Z][A-Z0-9_]*\b", function(source, "enum Row").split("{", 1)[1]))}
        methods = "\n".join(function(source, signature).replace(" override", "") for signature in (
            "OnlineTab() :", "void openAfterRound()", "void focus() override", "bool back() override",
            "void update(Menu *menu, TMarioGamePad *pad) override", "bool visible(", "int rowAt(",
            "int visibleCount(", "bool normalize(", "void moveSelection(", "void openPage(",
            "void openSearchRow(", "static bool draftTurn(", "bool apply(", "bool enterCode(", "void beginEdit("))
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        fields = source[source.index("    LiveRace::Options mDraft;"):source.index("\n};", source.index("    LiveRace::Options mDraft;"))]
        texts = function(source, "namespace OnlineText")
        style = function((ROOT / "include/susamune/creation.hxx").read_text(), "struct CreationStyle") + ";"
        shim = r'''
#define TIMEWARP_LIVE_RACING 1
#define IS_EMULATOR 0
#include "susamune/live_race.hxx"
#define SUSAMUNE_GLYPH_A "A"
#define SUSAMUNE_GLYPH_B "B"
#define SUSAMUNE_GLYPH_C "C"
#define SUSAMUNE_GLYPH_X "X"
#define SUSAMUNE_GLYPH_Y "Y"
#define SUSAMUNE_GLYPH_SLASH "/"
extern "C" void *memcpy(void *to,const void *from,size_t size) {
    volatile u8 *d=(volatile u8*)to;const volatile u8 *s=(const volatile u8*)from;
    while(size--) *d++=*s++;return to;
}
extern "C" void *memset(void *to,int value,size_t size) {
    volatile u8 *d=(volatile u8*)to;while(size--) *d++=value;return to;
}
size_t strlen(const char *s) {size_t n=0;while(s[n])++n;return n;}
void *operator new(size_t,void *p) {return p;}
struct JUTGamePad {
    enum {A=0x100,B=0x200,X=0x400,Y=0x800,Z=0x10,START=0x1000,L=0x40,R=0x20,
        DPAD_LEFT=1,DPAD_RIGHT=2,DPAD_UP=8,DPAD_DOWN=4};
    struct Status{u16 mButton;};static Status mPadStatus[1];
};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad {enum{CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8};u32 nav;};
struct Menu {u32 navigationInput(TMarioGamePad *p){return p->nav;}void toast(const char*){++toasts;}unsigned toasts;};
static unsigned hits[12], editorResult, lastGuestSlot;
enum {HOST,JOIN,READY,CONFIGURE,NEW_MATCH,ENTER_CODE,NAT,PREFS,DRAFT,INPUTS,FORFEIT_CALL};
int wrap(int value,int count){return (value+count)%count;}
namespace LiveGroupRules {unsigned actor(const State&s){return s.phase==Draft?(s.rotation+s.bans)%s.config.players:Nobody;}}
namespace LiveDraft {u8 currentActor(const State &s){return s.previousWinner;}}
namespace LiveRace {
Status current;Options opts;Prefs preferences;LiveGroupRules::State group;
const LiveGroupRules::State *groupState(){return opts.players>2&&current.active?&group:nullptr;}unsigned groupPlayer(){return 0;}
Status status(){return current;}const Options &options(){return opts;}
const Prefs &prefs(){return preferences;}
bool configure(const Options &o){++hits[CONFIGURE];opts=o;return true;}
bool host(){++hits[HOST];current.active=current.hosting=true;current.setupEditable=false;return true;}
bool join(){++hits[JOIN];current.active=true;current.hosting=false;current.setupEditable=false;return true;}
bool holdingStart(){return false;}
bool forfeit(){++hits[FORFEIT_CALL];current.canForfeit=false;return true;}
bool ready(){++hits[READY];current.localReady=!current.localReady;return true;}
bool newMatch(){++hits[NEW_MATCH];if(!current.hosting||!current.setupEditable)return false;
    current.matchDone=false;current.freeRoam=opts.freeRoam;current.drafting=opts.draft;return true;}
bool chooseDraft(unsigned){++hits[DRAFT];return true;}
void disconnect(){current.active=current.connected=false;current.setupEditable=true;}
void setPrefs(const Prefs &p){++hits[PREFS];preferences=p;}
bool lastFriend(char*){return false;}
const char *enterCode(const char*){++hits[ENTER_CODE];return nullptr;}
const char *enterGuestCode(unsigned slot,const char*){lastGuestSlot=slot;++hits[ENTER_CODE];return nullptr;}
static int connectedGuest=-1;
const char *guestName(unsigned slot){return connectedGuest==(int)slot?"Guest":nullptr;}
bool kickGuest(unsigned slot){++hits[11];lastGuestSlot=slot;connectedGuest=-1;return true;}
}
namespace LiveGhost {bool shown;bool inputsShown(){return shown;}void setInputsShown(bool v){shown=v;++hits[INPUTS];}}
namespace LiveP2P {enum{CODE_CHARS=14,DISPLAY_CHARS=19};char symbol(int at){return 'A'+at;}}
namespace LiveStun {bool start(unsigned){++hits[NAT];return true;}}
namespace StageLoader {int queueCount(){return 3;}bool loadBuiltinPlaylist(int){return true;}bool loadCustomPlaylist(int){return true;}}
namespace ILing {
int count(){return 10;}int menuPositionOf(int n){return n;}int menuEntryAt(int n){return n;}
int jumpMenuGroup(int n,int d){return wrap(n+d*5,10);}bool streakEntrySelectable(int){return true;}
int selectedEpisode(int){return 0;}bool canChooseEpisode(int n){return n==3;}
}
void updateCreationKeyboardButtons(u16,char*,u8&,unsigned,u8&,bool&,u8&){}
STYLE
struct CreationEditor {
    enum {CAP_POSITION=1,CAP_SCALE=2,UPDATE_FINISHED=2,UPDATE_CANCELLED=4};
    bool active;
    void reset(){active=false;}void setScaleLimits(u8,u8){}
    void begin(CreationStyle*,u8(*)[3],u8(*)[3],unsigned,unsigned,const char*,unsigned){active=true;}
    bool editing(){return active;}
    u8 update(TMarioGamePad*,const CreationStyle&,const u8(*)[3]){active=!editorResult;return editorResult;}
};
'''.replace("STYLE", style)
        driver = r'''
class OnlineTab {
public:
ENUMS
METHODS
FIELDS
};
alignas(OnlineTab) static u8 storage[sizeof(OnlineTab)];
static OnlineTab *tab;
static Menu menu;
static TMarioGamePad pad;
extern "C" __declspec(dllexport) void statusBits(unsigned bits) {
    auto &s=LiveRace::current;
    s.active=bits&1;s.connected=bits&2;s.hosting=bits&4;s.matchDone=bits&8;
    s.freeRoam=bits&16;s.drafting=bits&32;s.setupEditable=bits&64;s.racing=bits&128;s.canForfeit=s.racing;
    s.localCode[0]=s.active?'L':0;
}
extern "C" __declspec(dllexport) void optionsBits(unsigned bits) {
    LiveRace::opts.draft=bits&1;LiveRace::opts.freeRoam=bits&2;LiveRace::opts.entry=bits&4?3:0;
    LiveRace::opts.playlist=bits&8;
    LiveRace::opts.players=bits&16?4:2;
    LiveRace::group={};LiveRace::group.config.players=LiveRace::opts.players;LiveRace::group.phase=LiveGroupRules::NeedCandidates;
}
extern "C" __declspec(dllexport) void reset(unsigned status,unsigned opts) {
    memset(&LiveRace::current,0,sizeof(LiveRace::current));memset(&LiveRace::opts,0,sizeof(LiveRace::opts));
    memset(&LiveRace::preferences,0,sizeof(LiveRace::preferences));memset(hits,0,sizeof(hits));
    LiveRace::opts.name[0]='T';LiveRace::opts.bestOf=3;
    statusBits(status);optionsBits(opts);LiveRace::current.draft.phase=LiveDraft::OPENING_HOST_BAN;
    LiveRace::connectedGuest=-1;menu.toasts=0;editorResult=0;pad.nav=0;JUTGamePad::mPadStatus[0].mButton=0;
    tab=new(storage) OnlineTab();
}
extern "C" __declspec(dllexport) void step(unsigned buttons,unsigned nav) {
    JUTGamePad::mPadStatus[0].mButton=buttons;pad.nav=nav;tab->update(&menu,&pad);
}
extern "C" __declspec(dllexport) void select(int section,int row) {tab->mSection=section;tab->mSel=row;}
extern "C" __declspec(dllexport) int rowAt(int section,int index) {tab->mSection=section;return tab->rowAt(index,LiveRace::current);}
extern "C" __declspec(dllexport) int count(int section) {tab->mSection=section;return tab->visibleCount(LiveRace::current);}
extern "C" __declspec(dllexport) unsigned state() {return tab->mSel|(tab->mMode<<8)|(tab->mSection<<16);}
extern "C" __declspec(dllexport) unsigned calls(int action){return hits[action];}
extern "C" __declspec(dllexport) void search(int row){tab->openSearchRow(row);}
extern "C" __declspec(dllexport) void afterRound(){tab->openAfterRound();}
extern "C" __declspec(dllexport) int back(){return tab->back();}
extern "C" __declspec(dllexport) unsigned codeLength(){return tab->mLength;}
extern "C" __declspec(dllexport) unsigned hideScore(){return LiveRace::preferences.hideScore;}
extern "C" __declspec(dllexport) void finishEditor(unsigned result){editorResult=result;}
extern "C" __declspec(dllexport) void connectGuest(int slot){LiveRace::connectedGuest=slot;}
extern "C" __declspec(dllexport) unsigned guestSlot(){return lastGuestSlot;}
'''.replace("ENUMS", enums).replace("METHODS", methods).replace("FIELDS", fields)
        cls.folder = tempfile.TemporaryDirectory()
        path = Path(cls.folder.name) / "online.cpp"
        path.write_text(shim + texts + raw + driver)
        library = path.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fuse-ld=lld", "-Wl,/noentry", "-fno-rtti", "-fno-exceptions", "-O1",
                        "-I" + str(ROOT / "include"), str(path), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))

    @classmethod
    def tearDownClass(cls):
        C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle))
        cls.folder.cleanup()

    def press(self, button=0x100, nav=0):
        self.lib.step(0, 0)
        self.lib.step(button, nav)

    def state(self):
        state = self.lib.state()
        return state >> 16, (state >> 8) & 255, state & 255

    def rows_on(self, section):
        return [self.lib.rowAt(section, i) for i in range(self.lib.count(section))]

    def test_context_lists_are_short_and_mode_specific(self):
        r = self.rows
        self.lib.reset(64, 0)
        self.assertEqual(self.rows_on(0), [r[x] for x in (
            "NAME_ROW", "PLAYERS_ROW", "HOST_ROW", "JOIN_ROW", "RACE_PAGE_ROW", "OPPONENT_PAGE_ROW", "CONNECTION_PAGE_ROW")])
        self.assertEqual(self.rows_on(1), [r[x] for x in ("MODE_ROW", "ENTRY_ROW", "BEST_ROW")])
        self.lib.optionsBits(4)
        self.assertIn(r["EPISODE_ROW"], self.rows_on(1))
        self.lib.optionsBits(1)
        self.assertEqual(self.rows_on(1), [r[x] for x in ("MODE_ROW", "POOL_ROW", "SET_LENGTH_ROW")])
        self.lib.optionsBits(2)
        self.assertEqual(self.rows_on(1), [r["MODE_ROW"]])
        self.lib.statusBits(1 | 2 | 4 | 16 | 64)
        self.assertEqual(self.rows_on(1), [r["MODE_ROW"], r["SETUP_ROW"]])
        self.assertNotIn(r["READY_ROW"], self.rows_on(0))

    def test_every_action_is_reachable_once_and_navigation_wraps(self):
        reached = set()
        for status, opts in ((64, 0), (1, 0), (7, 0), (7, 4), (39, 1), (7, 1), (79, 2), (7, 17), (135, 0)):
            self.lib.reset(status, opts)
            for section in range(4):
                rows = self.rows_on(section)
                self.assertEqual(len(rows), len(set(rows)))
                reached.update(rows)
                self.lib.select(section, rows[0])
                self.lib.step(0, 1)
                self.assertEqual(self.state()[2], rows[-1])
                self.lib.step(0, 2)
                self.assertEqual(self.state()[2], rows[0])
        self.assertEqual(reached, set(range(self.rows["ROW_COUNT"])))

    def test_host_has_three_separate_guest_keyboards(self):
        r = self.rows
        for slot in range(3):
            self.lib.reset(7, 17)
            rows = self.rows_on(0)
            self.assertNotIn(r['FRIEND_ROW'], rows)
            self.assertTrue(all(r[f'GUEST{i}_ROW'] in rows for i in (1, 2, 3)))
            self.lib.select(0, r[f'GUEST{slot+1}_ROW'])
            self.press()
            self.assertEqual(self.state()[1], 2)
            for _ in range(14): self.press()
            self.assertEqual(self.lib.calls(5), 1)
            self.assertEqual(self.lib.guestSlot(), slot)
            self.assertEqual(self.state()[1], 0)

    def test_waiting_for_players_has_no_ban_action(self):
        self.lib.reset(7, 17)
        self.lib.select(0, self.rows['DRAFT_ROW'])
        self.press()
        self.assertEqual(self.state()[1], 4)
        self.press()
        self.assertEqual(self.lib.calls(8), 0)
        self.press(0x200)
        self.assertEqual(self.state()[1], 0)

    def test_create_and_join_dispatch_once_for_a_held_press(self):
        for row, action in (("HOST_ROW", 0), ("JOIN_ROW", 1)):
            self.lib.reset(64, 0)
            self.lib.select(0, self.rows[row])
            for _ in range(12):
                self.lib.step(0x100, 0)
            self.assertEqual(self.lib.calls(action), 1)
            self.assertEqual(self.lib.calls(5), 0)
            if action == 1:
                self.assertEqual(self.state()[1], 2)  # Friend code keyboard.
                self.assertEqual(self.lib.codeLength(), 0)
                self.press()
                self.assertEqual(self.lib.codeLength(), 1)

    def test_ready_has_one_toggle_per_press_and_disappears_when_irrelevant(self):
        self.lib.reset(7, 0)
        self.lib.select(0, self.rows["READY_ROW"])
        for _ in range(12):
            self.lib.step(0x100, 0)
        self.assertEqual(self.lib.calls(2), 1)
        self.press()
        self.assertEqual(self.lib.calls(2), 2)
        for bits in (7 | 8, 7 | 16, 7 | 32, 7 | 128):
            self.lib.statusBits(bits)
            self.lib.step(0, 0)
            self.assertNotEqual(self.state()[2], self.rows["READY_ROW"])
            self.assertNotIn(self.rows["READY_ROW"], self.rows_on(0))

    def test_code_can_be_cancelled_with_partial_text_without_leaving_session(self):
        self.lib.reset(1, 0)
        self.lib.select(0, self.rows["FRIEND_ROW"])
        self.press()
        self.press()
        self.assertEqual(self.lib.codeLength(), 1)
        self.press(0x400)  # X deletes; B always returns home.
        self.assertEqual(self.lib.codeLength(), 0)
        self.press()
        self.press(0x200)
        self.assertEqual(self.state()[:2], (0, 0))
        self.assertEqual(self.lib.codeLength(), 1)
        self.assertIn(self.rows["FRIEND_ROW"], self.rows_on(0))
        self.assertEqual(self.lib.calls(9), 0)

    def test_playlist_picker_returns_to_setup_and_hides_il_only_settings(self):
        self.lib.reset(64, 8)
        self.lib.search(self.rows["ENTRY_ROW"])
        self.press()
        self.assertEqual(self.state()[1], 6)
        self.press(0x200)
        self.assertEqual(self.state(), (1, 0, self.rows["ENTRY_ROW"]))
        for row in ("EPISODE_ROW", "BEST_ROW"):
            self.assertNotIn(self.rows[row], self.rows_on(1))

    def test_entering_pages_consumes_a_and_b_returns_to_opener(self):
        for opener, section in (("RACE_PAGE_ROW", 1), ("OPPONENT_PAGE_ROW", 2), ("CONNECTION_PAGE_ROW", 3)):
            self.lib.reset(64, 0)
            self.lib.select(0, self.rows[opener])
            for _ in range(12):
                self.lib.step(0x100, 0)
            self.assertEqual(self.state()[0], section)
            self.assertEqual(sum(self.lib.calls(i) for i in range(10)), 0)
            self.press(0x200)
            self.assertEqual(self.state(), (0, 0, self.rows[opener]))
            self.lib.step(0x200, 0)
            self.assertEqual(self.state()[0], 0)

    def test_nat_runs_only_from_explicit_connection_action(self):
        self.lib.reset(64, 0)
        self.press(0x400)
        self.assertEqual(self.lib.calls(6), 0)
        self.lib.search(self.rows["NAT_ROW"])
        self.press(0x400)
        self.assertEqual(self.lib.calls(6), 0)
        self.press()
        self.assertEqual(self.lib.calls(6), 1)
        self.lib.statusBits(1)
        self.press()
        self.assertEqual(self.lib.calls(6), 1)

    def test_score_toggle_and_editor_are_independent_and_return_to_display(self):
        self.lib.reset(64, 0)
        self.lib.search(self.rows["SCORE_VISIBLE_ROW"])
        self.press()
        self.assertEqual(self.lib.hideScore(), 1)
        self.assertEqual(self.state()[1], 0)
        self.lib.search(self.rows["SCORE_ROW"])
        self.lib.step(0, 8)
        self.assertEqual(self.lib.hideScore(), 1)
        self.assertEqual(self.state()[1], 0)
        self.press()
        self.assertEqual(self.state()[:2], (2, 5))
        self.lib.finishEditor(4)
        self.lib.step(0, 0)
        self.assertEqual(self.state(), (2, 0, self.rows["SCORE_ROW"]))
        self.assertEqual(self.lib.hideScore(), 1)

    def test_forfeit_requires_confirmation_and_back_keeps_racing(self):
        self.lib.reset(7 | 128, 0)
        self.lib.search(self.rows["FORFEIT_ROW"])
        self.press()
        self.assertEqual(self.lib.calls(10), 0)
        self.press(0x200)
        self.assertEqual(self.lib.calls(10), 0)
        self.press()
        self.press()
        self.assertEqual(self.lib.calls(10), 1)
        self.assertEqual(self.state()[1], 0)

    def test_host_setup_changes_require_apply_and_guests_cannot_mutate(self):
        for status in (3, 7):  # Guest; host with match locked.
            self.lib.reset(status, 0)
            self.lib.search(self.rows["MODE_ROW"])
            self.press()
            self.assertEqual(self.lib.calls(3), 0)
        self.lib.reset(7 | 8 | 64, 0)
        self.lib.search(self.rows["MODE_ROW"])
        self.press()
        self.assertEqual(self.lib.calls(3), 1)
        self.assertEqual(self.lib.calls(4), 0)
        self.lib.search(self.rows["SETUP_ROW"])
        self.press()
        self.assertEqual(self.lib.calls(4), 1)
        self.assertEqual(self.state(), (0, 0, self.rows["DRAFT_ROW"]))
        self.lib.step(0x100, 0)
        self.assertEqual(self.state()[1], 0)
        self.lib.reset(3 | 64, 0)
        self.lib.search(self.rows["SETUP_ROW"])
        self.press()
        self.assertEqual(self.lib.calls(4), 0)

    def test_host_can_kick_selected_guest_only_after_confirmation(self):
        for options, slot in ((0, 0), (16, 2)):
            self.lib.reset(7, options)
            self.lib.connectGuest(slot)
            self.lib.search(self.rows[f"GUEST{slot + 1}_ROW"])
            self.press()
            self.assertEqual(self.state()[1], 8)
            self.assertEqual(self.lib.calls(11), 0)
            self.press(0x200)
            self.assertEqual(self.lib.calls(11), 0)
            self.press()
            self.press()
            self.assertEqual(self.lib.calls(11), 1)
            self.assertEqual(self.state()[1], 0)

    def test_after_round_focuses_next_action_and_search_opens_owners(self):
        for status, mode, row in ((7, 0, "READY_ROW"), (15, 0, "RACE_PAGE_ROW"),
                                  (23, 0, "RACE_PAGE_ROW"), (39, 4, "DRAFT_ROW")):
            self.lib.reset(status, 1 if mode else 0)
            self.lib.afterRound()
            self.assertEqual(self.state(), (0, mode, self.rows[row]))
        for row, page in (("MODE_ROW", 1), ("ENTRY_ROW", 1), ("SCORE_ROW", 2),
                          ("SCORE_VISIBLE_ROW", 2), ("INPUTS_ROW", 2),
                          ("NAT_ROW", 3), ("DIAGNOSTICS_ROW", 3), ("NAME_ROW", 0)):
            self.lib.reset(64, 0)
            self.lib.search(self.rows[row])
            self.assertEqual(self.state(), (page, 0, self.rows[row]))
        self.lib.optionsBits(2)
        self.lib.search(self.rows["ENTRY_ROW"])
        self.assertEqual(self.state(), (1, 0, self.rows["MODE_ROW"]))
        source = (ROOT / "src/menu_search.inc").read_text()
        self.assertIn("case ONLINE: static_cast<OnlineTab *>(tab)->openSearchRow(row);", source)

    def test_il_editor_returns_to_setup_and_dynamic_visibility_normalizes(self):
        self.lib.reset(64, 4)
        self.lib.search(self.rows["ENTRY_ROW"])
        self.press()
        self.assertEqual(self.state()[:2], (1, 3))
        self.press(0x200)
        self.assertEqual(self.state(), (1, 0, self.rows["ENTRY_ROW"]))
        self.lib.search(self.rows["EPISODE_ROW"])
        self.lib.optionsBits(0)
        self.lib.step(0, 0)
        self.assertEqual(self.state()[2], self.rows["MODE_ROW"])
        self.lib.statusBits(7)
        self.lib.select(0, self.rows["FRIEND_ROW"])
        self.lib.step(0x100, 0)
        self.assertEqual(self.state()[2], self.rows["CODE_ROW"])
        self.assertEqual(self.lib.calls(2), 0)
        self.lib.step(0x100, 0)
        self.assertEqual(self.lib.calls(2), 0)
        self.lib.search(self.rows["READY_ROW"])
        self.press()
        self.assertEqual(self.lib.calls(2), 1)


if __name__ == "__main__":
    unittest.main()
