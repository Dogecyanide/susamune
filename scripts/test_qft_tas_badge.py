"""Check production TAS badge layout alongside the QFT and split delta."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class QftTasBadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        source = (ROOT / "src/qft_display.cpp").read_text(encoding="utf-8")
        methods = "\n".join(function(source, name) for name in (
            "clampi", "QftDisplay::beginOverlayFrame", "QftDisplay::draw",
            "QftDisplay::hasAnchor", "QftDisplay::adjacentStyle"))
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-tas-badge-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;",
            encoding="ascii")
        shim = r'''
#define private public
#include "susamune/qft_display.hxx"
#undef private
extern "C" void *memset(void*d,int v,unsigned long long n){u8*p=(u8*)d;while(n--)*p++=(u8)v;return d;}
char *strncpy(char*d,const char*s,unsigned long long n){char*out=d;while(n&&*s){*d++=*s++;n--;}while(n--)*d++=0;return out;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (u8)*a-(u8)*b;}
namespace JUtility {struct TColor {u8 r,g,b,a;TColor(u8 r,u8 g,u8 b,u8 a):r(r),g(g),b(b),a(a){}};}
struct Menu {
 int boxes=0,labels=0,timers=0;
 int bx=0,by=0,bw=0,bh=0,ba=0,tx=0,ty=0,tw=0,th=0,ta=0;
 void fillBox(int x,int y,int w,int h,JUtility::TColor c){boxes++;bx=x;by=y;bw=w;bh=h;ba=c.a;}
 void drawText(const char*t,int x,int y,int w,int h,JUtility::TColor c){labels++;tx=x;ty=y;tw=w;th=h;ta=c.a;}
};
namespace Creation {
 int textWidth(const char*t,int size){int n=0;while(*t++)n++;return n*(size/2);}
 void drawTextBox(Menu*m,const CreationStyle&,const u8(*)[3],u16,const char*,bool,u16){m->timers++;}
}
namespace PracticeSession {bool enabled;bool assisted(){return enabled;}}
struct QftTimer {bool assisted;bool practiceAssisted(){return assisted;}} gQFTTimer;
static bool sAnchorDrawn;static int sAnchorWidth;static char sAnchorText[20];
'''
        fixture = r'''
extern "C" __declspec(dllexport) void run(int x,int y,int scale,int padding,int alpha,int assisted,int timerAssisted,int*out){
 QftDisplay display;memset(&display,0,sizeof(display));
 display.mStyle={(u16)x,(u16)y,(u8)scale,(u8)alpha,0,0,0,128,100,(u8)padding};
 PracticeSession::enabled=assisted;gQFTTimer.assisted=timerAssisted;Menu menu;
 display.beginOverlayFrame();display.draw(&menu,"12:34.567");
 CreationStyle delta;memset(&delta,0,sizeof(delta));
 bool adjacent=display.adjacentStyle("12:34.567","+1.234",&delta);
 int values[]={menu.boxes,menu.labels,menu.timers,menu.bx,menu.by,menu.bw,menu.bh,
  menu.ba,menu.tx,menu.ty,menu.tw,menu.th,menu.ta,sAnchorWidth,adjacent,delta.x,delta.scale};
 for(unsigned i=0;i<sizeof(values)/sizeof(*values);i++)out[i]=values[i];
}
extern "C" __declspec(dllexport) int resetAnchor(){
 QftDisplay display;memset(&display,0,sizeof(display));display.mStyle={16,416,100,255,0,0,0,128,100,2};
 PracticeSession::enabled=true;gQFTTimer.assisted=false;Menu menu;CreationStyle delta;
 display.beginOverlayFrame();display.draw(&menu,"12:34.567");
 if(!display.hasAnchor("12:34.567")||display.hasAnchor("99:99.999"))return 1;
 if(display.adjacentStyle("99:99.999","+1.234",&delta))return 2;
 display.beginOverlayFrame();
 if(display.hasAnchor("12:34.567")||display.adjacentStyle("12:34.567","+1.234",&delta))return 3;
 display.draw(0,"12:34.567");display.draw(&menu,0);
 return display.hasAnchor("12:34.567")?4:0;
}
'''
        (work / "badge.cpp").write_text(shim + methods + fixture, encoding="ascii")
        dll = work / "badge.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                        "-I", str(work), "-I", str(ROOT / "include"),
                        str(work / "badge.cpp"), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.run.argtypes = [C.c_int] * 7 + [C.POINTER(C.c_int)]

    def draw(self, x=16, y=416, scale=100, padding=2, alpha=255, assisted=1, timer_assisted=0):
        out = (C.c_int * 17)()
        self.lib.run(x, y, scale, padding, alpha, assisted, timer_assisted, out)
        return list(out)

    def test_badge_background_stays_inside_screen_at_all_editor_edges(self):
        for x in (0, 320, 640):
            for y in (0, 240, 480):
                for scale in (50, 100, 200):
                    for padding in (0, 2, 16, 255):
                        with self.subTest(x=x, y=y, scale=scale, padding=padding):
                            values = self.draw(x, y, scale, padding)
                            self.assertEqual(values[:3], [1, 1, 1])
                            bx, by, bw, bh = values[3:7]
                            self.assertGreaterEqual(bx, 0)
                            self.assertGreaterEqual(by, 0)
                            self.assertLessEqual(bx + bw, 640)
                            self.assertLessEqual(by + bh, 480)

    def test_badge_uses_qft_opacity_and_reserves_space_before_split_delta(self):
        for alpha in (0, 91, 255):
            for padding in (0, 2, 16, 255):
                with self.subTest(alpha=alpha, padding=padding):
                    values = self.draw(padding=padding, alpha=alpha)
                    self.assertEqual((values[7], values[12]), (alpha, alpha))
                    self.assertEqual(values[14], 1)
                    pad = 0 if padding == 255 else padding
                    self.assertGreater(values[15] - pad, values[3] + values[5])
                    self.assertGreater(values[13], self.draw(padding=padding, assisted=0)[13])

    def test_unassisted_draw_has_no_badge_and_does_not_reserve_its_width(self):
        values = self.draw(assisted=0)
        self.assertEqual(values[:3], [0, 0, 1])
        self.assertEqual(values[13], len("12:34.567") * 10)
        self.assertEqual(values[14], 1)
        self.assertLess(values[15], self.draw()[15])

    def test_qft_assistance_keeps_badge_when_stage_local_assistance_clears(self):
        self.assertEqual(self.draw(assisted=0, timer_assisted=1), self.draw())
        self.assertEqual(self.draw(assisted=1, timer_assisted=1), self.draw())

    def test_right_edge_badge_moves_above_and_hides_delta_without_room(self):
        values = self.draw(640, 416)
        self.assertLess(values[9], 416)
        self.assertEqual(values[13], len("12:34.567") * 10)
        self.assertEqual(values[14], 0)

    def test_anchor_only_applies_to_matching_timer_text_in_current_frame(self):
        self.assertEqual(self.lib.resetAnchor(), 0)


if __name__ == "__main__":
    unittest.main()
