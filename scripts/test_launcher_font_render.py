"""Exercise production fallback text and FreeType bitmap sampling with fake GX."""
import ctypes
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
DEVKIT = Path("C:/Users/Dogec/susamune/.worktrees/v2.2-zeta/launcher/nintendont_devkitpro")


class LauncherFontRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" or not DEVKIT.exists():
            raise unittest.SkipTest("Pinned Windows launcher toolchain required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-font-render-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        subprocess.run([str(DEVKIT / "devkitPPC/bin/powerpc-eabi-ar.exe"),
            "x", str(DEVKIT / "libogc/lib/wii/libogc.a"), "console_font_8x16.o"], cwd=work, check=True)
        fontobj = (work / "console_font_8x16.o").read_bytes()
        shoff = struct.unpack_from(">I", fontobj, 32)[0]
        shsize, shnum, names = struct.unpack_from(">HHH", fontobj, 46)
        sections = [struct.unpack_from(">10I", fontobj, shoff+i*shsize) for i in range(shnum)]
        strings = fontobj[sections[names][4]:sections[names][4]+sections[names][5]]
        font = next(fontobj[s[4]:s[4]+s[5]] for s in sections
                    if strings[s[0]:].split(b"\0", 1)[0] == b".data.console_font_8x16")
        assert len(font) == 4096
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-font-render-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        production = (ROOT / "launcher/loader/source/grrlib.c").read_text()
        source = r'''
int _fltused;
typedef unsigned char u8;typedef unsigned u32;typedef int FT_Int;typedef int bool;
#define true 1
#define false 0
#define NULL ((void*)0)
#define GX_POINTS 0
#define GX_VTXFMT0 0
#define GX_TO_ZERO 0
#define GX_TEVSTAGE0 0
#define GX_PASSCLR 0
#define GX_VA_TEX0 0
#define GX_NONE 0
#define GX_PNMTX0 0
#define FT_PIXEL_MODE_GRAY 2
#define FT_PIXEL_MODE_MONO 1
typedef struct {int rows,width,pitch;u8*buffer;u8 pixel_mode;} FT_Bitmap;
typedef struct {void*face;} GRRLIB_ttfFont;
static unsigned pixels,pointSize,textureMode,tevMode;static int px,py;static u8 alpha[16];
static int GXmodelView2D;
void GX_Begin(int a,int b,int c){}
void GX_Position3f32(float x,float y,float z){px=(int)x;py=(int)y;}
void GX_Color4u8(u8 r,u8 g,u8 b,u8 a){if(px>=0&&px<4&&py>=0&&py<4)alpha[py*4+px]=a;pixels++;}
void GX_Color1u32(u32 color){pixels++;}
void GX_End(void){}
void GX_SetPointSize(int size,int unused){pointSize=size;}
void GX_SetNumTevStages(int unused){}
void GX_SetTevOp(int unused,int mode){tevMode=mode;}
void GX_SetVtxDesc(int unused,int mode){textureMode=mode;}
void GX_LoadPosMtxImm(int unused,int unused2){}
int ff_utf8_decode_next(const char**text,u32*out){if(!(unsigned char)**text)return 0;*out=(unsigned char)*(*text)++;return 1;}
'''
        source += "const u8 console_font_8x16[4096]={" + ",".join(map(str, font)) + "};\n"
        source += function(production, "FallbackGlyph") + function(production, "ProcessFallback")
        source += "unsigned ProcessUtf8(int x,int y,GRRLIB_ttfFont*f,const char*s,unsigned z,u32 c,bool d){return ProcessFallback(x,y,s,z,c,d);}\n"
        source += "\n".join(function(production, n) for n in ("GRRLIB_PrintfTTF", "GRRLIB_WidthTTF", "DrawBitmap"))
        source += r'''
__declspec(dllexport) int fallback(void){
 pixels=0;pointSize=0;textureMode=77;tevMode=77;
 if(GRRLIB_WidthTTF(NULL,"Moonshine",16)!=72||pixels)return 1;
 GRRLIB_PrintfTTF(10,20,NULL,"Moonshine",16,0xffffffff);
 return pixels>30&&pointSize==6&&!textureMode&&!tevMode?0:2;
}
__declspec(dllexport) int bitmap(int test){
 unsigned i;u8 gray[8]={255,0,199,199,64,255,199,199};u8 mono[4]={0x80,0xEE,0x40,0xEE};
 FT_Bitmap b={2,2,test==1?-4:4,gray,FT_PIXEL_MODE_GRAY};
 pixels=0;for(i=0;i<16;i++)alpha[i]=0;
 if(test==2){b.pitch=2;b.buffer=mono;b.pixel_mode=FT_PIXEL_MODE_MONO;}
 DrawBitmap(&b,0,0,255,255,255);
 if(test==0)return pixels==3&&alpha[0]==255&&alpha[1]==0&&alpha[4]==64&&alpha[5]==255?0:1;
 if(test==1)return pixels==3&&alpha[0]==64&&alpha[1]==255&&alpha[4]==255&&alpha[5]==0?0:2;
 return pixels==2&&alpha[0]==255&&alpha[1]==0&&alpha[4]==0&&alpha[5]==255?0:3;
}
'''
        cfile = work / "font.c"
        cfile.write_text(source, encoding="ascii")
        library = work / "font.dll"
        subprocess.run([str(ROOT / "toolchain/clang.exe"), "--target=x86_64-pc-windows-msvc",
            "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
            str(cfile), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_missing_ttf_remains_readable_with_matching_width_and_point_state(self):
        self.assertEqual(self.dll.fallback(), 0)

    def test_padded_gray_negative_pitch_and_monochrome(self):
        for case in range(3):
            with self.subTest(case=case):
                self.assertEqual(self.dll.bitmap(case), 0)


if __name__ == "__main__":
    unittest.main()
