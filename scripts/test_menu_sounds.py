"""Exercise menu sounds and Display-root shortcuts without leaking modal input."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class MenuSoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled host compiler required")
        cls.folder = tempfile.TemporaryDirectory(prefix="moonshine-menu-sounds-")
        cls.addClassCleanup(cls.folder.cleanup)
        menu = (ROOT / "src/menu.cpp").read_text()
        nested = menu[menu.index("class NestedMenuTab final"):]
        methods = "\n".join(function(nested, signature) for signature in (
            "void focus() override",
            "void update(Menu *menu, TMarioGamePad *pad) override",
        ))
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        wrapper = (ROOT / "src/menu_sounds.inc").read_text()
        wrapper = wrapper[wrapper.index("class MenuSoundsDisplayTab"):
                          wrapper.index("static_assert")]
        policy = function((ROOT / "src/menu_sounds.cpp").read_text(),
                          "Cue choose(const Transition &t)")
        code = r'''
#include "susamune/menu_sounds.hxx"
struct JUTGamePad {
 enum { A=0x100,B=0x200,X=0x400,Y=0x800,Z=0x10,START=0x1000 };
 struct Status {u16 mButton;}; static Status mPadStatus[1];
};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad {
 enum { CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8 };
 u32 rapid=0,pressed=0;
};
struct Menu {u32 navigationInput(TMarioGamePad *pad){return pad->rapid;}};
int wrap(int value,int count){return (value+count)%count;}
enum { SETTING_MENU_SOUNDS, ROW_H=24, SUSAMUNE_CREATION_MENU_BG=3 };
struct Settings {
 bool enabled=true;
 static const char *name(int){return "Menu sounds";}
 const char *valueLabel(int){return enabled?"On":"Off";}
 void cycle(int,int){enabled=!enabled;}
} gSettings;
struct CreationExtras {
 bool active=false;u16 confirmation=0;
 unsigned begins=0,updates=0,draws=0,first=99,count=99;
 const char *title=nullptr;
 bool editing()const{return active;}
 void beginColorEditor(int slot,int slots,const char *name) {
  active=true;confirmation=0;++begins;first=slot;count=slots;title=name;
 }
 void updateEditor(TMarioGamePad *pad) {
  ++updates;
  if(confirmation) {
   if(pad->pressed&JUTGamePad::A){active=false;confirmation=0;}
   else if(pad->pressed&JUTGamePad::B)confirmation=0;
  } else if(pad->pressed&(JUTGamePad::A|JUTGamePad::B))
   confirmation=(u16)(pad->pressed&(JUTGamePad::A|JUTGamePad::B));
 }
 void drawEditor(Menu*){++draws;}
}gCreationExtras;
unsigned rowCount,selectedRow;
const char *firstRow;
void drawValueRow(Menu*,int,int,int,const char *name,const char*,bool selected,bool,bool) {
 if(!rowCount)firstRow=name;
 if(selected)selectedRow=rowCount;
 ++rowCount;
}
void drawHelpLine(Menu*,int,int,int,int,const char*){}
struct MenuTab {
 virtual const char *title() const {return "Child";}
 virtual const char *summary() const {return "Child help";}
 virtual bool grabsInput() const {return false;}
 virtual bool suppressesBinds() const {return false;}
 virtual bool fullScreen() const {return false;}
 virtual bool favoriteHint() const {return false;}
 virtual void focus(){}
 virtual bool back(){return false;}
 virtual void update(Menu*,TMarioGamePad*){}
 virtual void draw(Menu*,int,int,int,int){}
};
''' + raw + r'''
class NestedMenuTab final : public MenuTab {
public:
 MenuTab *mChildren[5];
 u8 mCount=5,mSel=0; s8 mPage=-1;
 bool mChildEntryWait=false; RawPromptInput mNavInput;
 MenuTab *current()const{return mPage<0?nullptr:mChildren[mPage];}
 bool grabsInput()const override{return current()&&current()->grabsInput();}
 bool suppressesBinds()const override{return current()&&current()->suppressesBinds();}
 bool fullScreen()const override{return current()&&current()->fullScreen();}
 bool favoriteHint()const override{return current()&&current()->favoriteHint();}
 void jumpRootSection(int){}
 void draw(Menu *m,int x,int y,int w,int h)override{if(current())current()->draw(m,x,y,w,h);}
METHODS
};
''' .replace("METHODS", methods) + wrapper + r'''
namespace MenuSounds {
POLICY
}
struct Child:MenuTab {
 unsigned edits=0,favorites=0,draws=0;
 bool editor=false;
 bool favoriteHint()const override{return true;}
 bool fullScreen()const override{return editor;}
 bool back()override{if(editor){editor=false;return true;}return false;}
 void update(Menu*,TMarioGamePad*)override{
  if(JUTGamePad::mPadStatus[0].mButton==JUTGamePad::A){++edits;editor=true;}
  if(JUTGamePad::mPadStatus[0].mButton==JUTGamePad::X)++favorites;
 }
 void draw(Menu*,int,int,int,int)override{++draws;}
};
static void frame(MenuSoundsDisplayTab &display,Menu &menu,u16 buttons,u32 rapid=0) {
 const u16 previous=JUTGamePad::mPadStatus[0].mButton;
 JUTGamePad::mPadStatus[0].mButton=buttons;TMarioGamePad pad;
 pad.rapid=rapid;pad.pressed=buttons&~previous;
 display.update(&menu,&pad);
}
static void pulse(MenuSoundsDisplayTab &display,Menu &menu,u16 buttons,u32 rapid=0) {
 frame(display,menu,buttons,rapid);frame(display,menu,0);
}
#define API extern "C" __declspec(dllexport)
API unsigned choose(unsigned shownBefore,unsigned shownAfter,unsigned changed,
 unsigned nav,unsigned enabled,unsigned recording,unsigned pressed) {
 return MenuSounds::choose({(bool)shownBefore,(bool)shownAfter,(bool)changed,
  (bool)nav,(bool)enabled,(bool)recording,(u16)pressed});
}
API unsigned routes() {
 unsigned result=0;
 for(unsigned target=0;target<5;++target) {
  JUTGamePad::mPadStatus[0].mButton=0;Menu menu;NestedMenuTab parent;Child children[5];
  for(unsigned i=0;i<5;++i)parent.mChildren[i]=&children[i];
  MenuSoundsDisplayTab display(&parent);display.focus();
  rowCount=0;selectedRow=99;display.draw(&menu,0,0,600,300);
  if(rowCount!=7||selectedRow!=0||firstRow[0]!='M')return 0;
  for(unsigned i=0;i<target+2;++i)pulse(display,menu,0,TMarioGamePad::CSTICK_DOWN);
  pulse(display,menu,JUTGamePad::A);
  if(parent.mPage!=(int)target||children[target].edits)return 0;
  frame(display,menu,0);
  pulse(display,menu,JUTGamePad::A);
  if(children[target].edits!=1||!display.fullScreen()||!display.favoriteHint())return 0;
  pulse(display,menu,JUTGamePad::X);
  if(children[target].favorites!=1)return 0;
  display.draw(&menu,0,0,600,300);
  if(children[target].draws!=1)return 0;
  pulse(display,menu,JUTGamePad::B);
  if(parent.mPage!=(int)target||children[target].editor)return 0;
  pulse(display,menu,JUTGamePad::B);
  if(parent.mPage!=-1)return 0;
  result|=1u<<target;
 }
 return result;
}
API unsigned toggle() {
 JUTGamePad::mPadStatus[0].mButton=0;Menu menu;NestedMenuTab parent;Child children[5];
 for(unsigned i=0;i<5;++i)parent.mChildren[i]=&children[i];
 MenuSoundsDisplayTab display(&parent);display.focus();gSettings.enabled=true;
 frame(display,menu,JUTGamePad::A);
 for(unsigned i=0;i<20;++i)frame(display,menu,JUTGamePad::A);
 if(gSettings.enabled||parent.mPage!=-1)return 0;
 frame(display,menu,0);pulse(display,menu,JUTGamePad::A);
 return gSettings.enabled&&parent.mPage==-1;
}
API unsigned background(unsigned cancel) {
 JUTGamePad::mPadStatus[0].mButton=0;Menu menu;NestedMenuTab parent;Child children[5];
 for(unsigned i=0;i<5;++i)parent.mChildren[i]=&children[i];
 gCreationExtras=CreationExtras{};gSettings.enabled=true;
 MenuSoundsDisplayTab display(&parent);display.focus();
 pulse(display,menu,0,TMarioGamePad::CSTICK_DOWN);
 rowCount=0;selectedRow=99;display.draw(&menu,0,0,600,300);
 if(rowCount!=7||selectedRow!=1)return 0;
 frame(display,menu,JUTGamePad::A);
 if(!display.grabsInput()||!display.suppressesBinds()||!display.fullScreen()||
    !gCreationExtras.editing()||gCreationExtras.begins!=1||gCreationExtras.updates||
    gCreationExtras.first!=SUSAMUNE_CREATION_MENU_BG||gCreationExtras.count!=1||
    !gCreationExtras.title||gCreationExtras.title[0]!='M'||parent.mPage!=-1)return 0;
 for(unsigned i=0;i<20;++i)frame(display,menu,JUTGamePad::A);
 if(!gCreationExtras.active||gCreationExtras.confirmation)return 0;
 frame(display,menu,0);
 pulse(display,menu,0,TMarioGamePad::CSTICK_DOWN);
 if(display.mTopRow!=1||parent.mSel||parent.mPage!=-1)return 0;
 rowCount=0;display.draw(&menu,0,0,600,300);
 if(rowCount||gCreationExtras.draws!=1||children[0].draws)return 0;
 pulse(display,menu,cancel?JUTGamePad::B:JUTGamePad::A);
 if(!display.grabsInput()||!gCreationExtras.confirmation)return 0;
 frame(display,menu,JUTGamePad::A);
 if(display.grabsInput()||display.suppressesBinds()||display.fullScreen()||
    gCreationExtras.active||display.mTopRow!=1||parent.mPage!=-1)return 0;
 for(unsigned i=0;i<20;++i)frame(display,menu,JUTGamePad::A);
 if(gCreationExtras.begins!=1||!gSettings.enabled)return 0;
 frame(display,menu,0);
 pulse(display,menu,0,TMarioGamePad::CSTICK_DOWN);
 pulse(display,menu,JUTGamePad::A);
 return parent.mPage==0&&!children[0].edits&&gCreationExtras.begins==1;
}
''' .replace("POLICY", policy)
        source = Path(cls.folder.name) / "test.cpp"
        source.write_text(code)
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc",
                                 "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry",
                                 "-fno-rtti", "-fno-exceptions", "-O2",
                                 "-I", str(ROOT / "include"), str(source),
                                 "-o", str(source.with_suffix(".dll"))],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(source.with_suffix(".dll")))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_only_accepted_navigation_and_option_changes_make_sound(self):
        choose = self.lib.choose
        self.assertEqual(choose(1, 1, 1, 1, 1, 0, 0), 1)
        self.assertEqual(choose(1, 1, 1, 0, 1, 0, 0x100), 2)
        self.assertEqual(choose(1, 1, 1, 0, 1, 0, 0x200), 3)
        self.assertEqual(choose(0, 1, 1, 0, 1, 0, 0x1800), 2)
        self.assertEqual(choose(1, 0, 1, 0, 1, 0, 0x1800), 3)
        for args in ((1,1,0,1,1,0,0), (1,1,0,0,1,0,0x100),
                     (1,1,1,0,1,0,0), (1,1,1,1,0,0,0),
                     (1,1,1,1,1,1,0), (0,0,1,1,1,0,0)):
            self.assertEqual(choose(*args), 0, args)

    def test_display_children_keep_editor_back_and_favourite_routes(self):
        self.assertEqual(self.lib.routes(), 31)

    def test_top_toggle_changes_once_per_press_without_entering_child(self):
        self.assertEqual(self.lib.toggle(), 1)

    def test_background_editor_owns_input_and_returns_after_keep_or_cancel(self):
        for cancel in (0, 1):
            with self.subTest(cancel=cancel):
                self.assertEqual(self.lib.background(cancel), 1)


if __name__ == "__main__":
    unittest.main()
