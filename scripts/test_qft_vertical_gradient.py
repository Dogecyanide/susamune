"""Exercise the shared text renderer's QFT-only vertical palette."""

import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class VerticalGradientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="qft-gradient-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        creation = (ROOT / "src/creation.cpp").read_text()
        qft = (ROOT / "src/qft_display.cpp").read_text()
        source = r'''
typedef unsigned char u8;typedef unsigned short u16;typedef short s16;
struct Color {u8 r,g,b,a;Color(u8 r=0,u8 g=0,u8 b=0,u8 a=0):r(r),g(g),b(b),a(a){}};
struct CreationStyle {u16 x,y;u8 scale,textA,bgR,bgG,bgB,bgA,textBrightness,padding;};
enum {SETTING_QFT_VERTICAL_GRADIENT};
struct Settings {bool vertical;bool getBool(int)const{return vertical;}}gSettings;
struct QftDisplay {
 u8 mTextRgb[9][3];bool verticalGradient(const u8(*)[3])const;
} gQftDisplay;
struct Menu {
 int flat=0,vertical=0,arrows=0,centre=0;Color top,bottom;
 static int textWidth(const char*s,int size){int n=0;while(*s++)n++;return n*size/2;}
 void drawText(const char*,int,int,int,int,Color c){flat++;top=bottom=c;}
 void drawTextVertical(const char*,int,int,int,Color a,Color b){vertical++;top=a;bottom=b;}
 void fillPoly(const s16*p,int,Color){arrows++;centre=p[4];}
};
'''
        source += "\n".join(function(creation, name) for name in ("clampi", "lit", "glyphBytes"))
        source += function(qft, "QftDisplay::verticalGradient")
        source += "namespace Creation {" + function(creation, "drawTextLine") + "}\n"
        source += r'''
extern "C" __declspec(dllexport) void run(int enabled,int own,int selected,int*out){
 gSettings.vertical=enabled;
 for(unsigned i=0;i<9;i++)for(unsigned c=0;c<3;c++)gQftDisplay.mTextRgb[i][c]=10+i*10+c;
 const u8 ends[2][3]={{20,40,60},{200,120,80}};
 for(unsigned c=0;c<3;c++){gQftDisplay.mTextRgb[0][c]=ends[0][c];gQftDisplay.mTextRgb[8][c]=ends[1][c];}
 u8 foreign[9][3];for(unsigned i=0;i<9;i++)for(unsigned c=0;c<3;c++)foreign[i][c]=gQftDisplay.mTextRgb[i][c];
 CreationStyle style={10,30,100,203,0,0,0,128,150,2};Menu menu;
 Creation::drawTextLine(&menu,style,own?gQftDisplay.mTextRgb:foreign,9,"123",10,30,20,6,false,(u16)selected);
 int values[]={menu.flat,menu.vertical,menu.arrows,menu.centre,
  menu.top.r,menu.top.g,menu.top.b,menu.top.a,menu.bottom.r,menu.bottom.g,menu.bottom.b,menu.bottom.a};
 for(unsigned i=0;i<12;i++)out[i]=values[i];
}
'''
        path = work / "gradient.cpp"
        path.write_text(source, encoding="ascii")
        library = work / "gradient.dll"
        subprocess.run([
            str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
            "-O2", str(path), "-o", str(library),
        ], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)

    def draw(self, enabled=True, own=True, selected=0xffff):
        result = (C.c_int * 12)()
        self.lib.run(enabled, own, selected, result)
        return list(result)

    def test_vertical_uses_endpoints_brightness_and_alpha_in_one_run(self):
        result = self.draw()
        self.assertEqual(result[:3], [0, 1, 0])
        self.assertEqual(result[4:], [30, 60, 90, 203, 255, 180, 120, 203])

    def test_other_displays_and_horizontal_mode_keep_character_colours(self):
        for enabled, own in ((False, True), (True, False)):
            result = self.draw(enabled, own)
            self.assertEqual(result[:3], [3, 0, 0])
            self.assertEqual(result[4:8], result[8:])

    def test_selected_character_keeps_its_preview_arrow(self):
        result = self.draw(selected=7)
        self.assertEqual(result[:4], [0, 3, 1, 25])
        self.assertEqual(result[4:], [30, 60, 90, 203, 255, 180, 120, 203])


if __name__ == "__main__":
    unittest.main()
