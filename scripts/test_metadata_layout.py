"""Check production metadata packing, colour slots and reserved-byte migration."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class MetadataLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        path = ROOT / "src/metadata_display.cpp"
        source = path.read_text(encoding="utf-8")
        pools = source[source.index("constexpr u8 kTextOffsets[]"):
                       source.index("template <unsigned N>")]
        structs = "\n".join(function_source(path, s) + ";" for s in (
            "struct LayoutOptions", "struct HorizontalMetrics"))
        funcs = "\n".join(function_source(path, s) for s in (
            "inline int clampi(", "LayoutOptions layoutOptions(", "int lineHeight(",
            "int fieldPrecision(", "const u8 *fieldLabelOffsets(",
            "void drawBackground(", "bool horizontalWrap(",
            "HorizontalMetrics horizontalMetrics(", "void drawStandardHorizontal("))
        methods = "\n".join(function_source(path, s) for s in (
            "void MetadataDisplay::adoptStyle(", "void MetadataDisplay::stageStyleInto("))
        shim = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
struct Color { Color(int,int,int,int) {} };
struct CreationStyle { u16 x,y;u8 scale,textA,bgR,bgG,bgB,bgA,textBrightness,padding; };
struct MetadataDisplayLiveCfg { unsigned fieldMask,labelMode; };
struct Values { char text[11][32]; };
static const int kSafeRight=624,kSafeBottom=456;
extern "C" void *memcpy(void *d,const void *s, unsigned long long n) {
    for(unsigned long long i=0;i<n;i++)((char*)d)[i]=((const char*)s)[i];return d;
}
extern "C" void *memset(void *d,int v,unsigned long long n) {
    for(unsigned long long i=0;i<n;i++)((char*)d)[i]=(char)v;return d;
}
int length(const char *s) { int n=0;while(s[n])n++;return n; }
int snprintf(char *out,unsigned cap,const char *,...) {
    __builtin_va_list a;__builtin_va_start(a,cap);
    const char *s=__builtin_va_arg(a,const char*);unsigned n=0;
    while(*s && n+1<cap)out[n++]=*s++;
    if(n+1<cap)out[n++]=':';if(n+1<cap)out[n++]=' ';out[n]=0;
    __builtin_va_end(a);return n;
}
struct Draw { int x,y,width,slot; };
static Draw calls[32];static int count,bgx,bgy,bgw,bgh;
struct Menu {
    static int textWidth(const char *s,int size) {
        int w=0;while(*s) { w+=*s=='1'?size/3:(*s==' '||*s==':'?size/2:size);s++; }return w;
    }
    void fillBox(int x,int y,int w,int h,Color) { bgx=x;bgy=y;bgw=w;bgh=h; }
};
namespace Creation {
int glyphCount(const char *s) { return length(s); }
void drawTextLine(Menu*,const CreationStyle&,const u8(*)[3],int,
    const char *s,int x,int y,int size,u16 slot,bool,u16) {
    calls[count++]={x,y,Menu::textWidth(s,size),slot};
}
}
class MetadataDisplay {
public:
enum {FIELD_X,FIELD_Y,FIELD_Z,FIELD_ANGLE,FIELD_HSPD,FIELD_VSPD,
      FIELD_QF,FIELD_CANGLE,FIELD_INVINC,FIELD_GOOP,FIELD_SPIN,FIELD_COUNT};
CreationStyle mStyle;u8 mTextRgb[SUSAMUNE_METADATA_STYLE_TEXT_SLOTS][3];
u8 mFieldGap,mRowGap,mColumns;bool mCompact,mDirty;
void clampLayout();
void adoptStyle(const volatile SusamuneMetadataStyleCfg*);
void stageStyleInto(volatile SusamuneMetadataStyleCfg*)const;
};
unsigned fieldBit(int i) { return 1u<<i; }
Values editorValues();
void formatValue(char *out,u32 cap,int field,int,const Values &v) {
    unsigned n=0;while(v.text[field][n]&&n+1<cap) { out[n]=v.text[field][n];n++; }out[n]=0;
}
'''
        # This printf shim needs only the prefix format used by layout functions.
        shim = shim.replace('const char *,...)', 'const char *format,...)').replace(
            '__builtin_va_start(a,cap)', '__builtin_va_start(a,format)')
        more = r'''
Values editorValues() {
    Values v={};for(int i=0;i<11;i++)for(int j=0;j<kMaximumValueSlots[i];j++)v.text[i][j]='9';return v;
}
void MetadataDisplay::clampLayout() {
    mFieldGap=(u8)clampi(mFieldGap,0,32);mRowGap=(u8)clampi(mRowGap,0,16);
    mColumns=(u8)clampi(mColumns,0,11);
}
extern "C" __declspec(dllexport) int render(unsigned mask,int editing,int compact,
    int columns,int gap,int rowGap,int size,int x,int y,int digits) {
    Values v=editing?editorValues():Values{};
    if(!editing)for(int i=0;i<11;i++)for(int j=0;j<digits;j++)v.text[i][j]='1';
    MetadataDisplayLiveCfg cfg={mask,0};CreationStyle style={};
    style.x=(u16)x;style.y=(u16)y;style.padding=0;style.bgA=255;
    LayoutOptions options=layoutOptions((u8)gap,(u8)rowGap,(u8)columns,compact!=0);
    count=bgx=bgy=bgw=bgh=0;Menu menu;
    drawStandardHorizontal(&menu,cfg,style,0,v,editing!=0,size,size+3,0xffff,options);
    return count;
}
extern "C" __declspec(dllexport) int get(int index,int field) {
    if(index<0) { int b[]={bgx,bgy,bgw,bgh};return b[field]; }
    int v[]={calls[index].x,calls[index].y,calls[index].width,calls[index].slot};return v[field];
}
extern "C" __declspec(dllexport) unsigned persist(unsigned flags,unsigned a,unsigned b,
    unsigned c,unsigned d,unsigned *out) {
    MetadataDisplay display={};display.mFieldGap=12;
    SusamuneMetadataStyleCfg src={},dst={};
    src.magic=SUSAMUNE_METADATA_STYLE_MAGIC;src.version=SUSAMUNE_METADATA_STYLE_VERSION;
    src.present=(unsigned short)flags;src.reserved0[0]=(u8)a;src.reserved0[1]=(u8)b;
    src.reserved0[2]=(u8)c;src.reserved0[3]=(u8)d;
    display.adoptStyle(&src);display.stageStyleInto(&dst);
    for(int i=0;i<14;i++)out[i]=dst.reserved0[i];
    return dst.present;
}
'''
        file = Path(cls.folder.name) / "metadata.cpp"
        file.write_text(shim + pools + structs + funcs + methods + more, encoding="ascii")
        dll = file.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O1",
                        "-fno-builtin", "-I", str(ROOT / "include"), str(file), "-o", str(dll)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.render.argtypes = [C.c_int] * 10
        cls.lib.get.argtypes = [C.c_int, C.c_int]
        cls.lib.persist.argtypes = [C.c_uint] * 5 + [C.POINTER(C.c_uint)]

    def render(self, mask=2047, editing=0, compact=1, columns=0, gap=12,
               rowGap=0, size=14, x=16, y=112, digits=1):
        count = self.lib.render(mask, editing, compact, columns, gap, rowGap, size, x, y, digits)
        return ([tuple(self.lib.get(i, j) for j in range(4)) for i in range(count)],
                tuple(self.lib.get(-1, j) for j in range(4)))

    def test_requested_columns_and_screen_width_both_wrap(self):
        for columns in range(1, 12):
            calls, bg = self.render(columns=columns, size=7)
            rows = {}
            for item in calls[::2]:rows[item[1]] = rows.get(item[1], 0) + 1
            self.assertLessEqual(max(rows.values()), columns)
            self.assertGreaterEqual(len(rows), math_ceil(11, columns))
            self.assertLessEqual(bg[0] + bg[2], 624)
        calls, bg = self.render(columns=11, size=28, x=600)
        self.assertGreater(len({v[1] for v in calls}), 1)
        self.assertLessEqual(bg[0] + bg[2], 624)

    def test_field_and_row_gaps_match_actual_draw_positions(self):
        for gap in (0, 4, 12, 32):
            calls, bg = self.render(columns=3, gap=gap, rowGap=7, size=7)
            self.assertEqual(calls[2][0] - (calls[1][0] + calls[1][2]), gap)
            self.assertEqual(calls[6][1] - calls[0][1], 17)
            self.assertEqual(max(v[0] + v[2] for v in calls), bg[0] + bg[2])

    def test_compact_widths_preserve_stable_numeric_colour_slots(self):
        compact, compact_bg = self.render(mask=7, columns=3)
        stable, stable_bg = self.render(mask=7, compact=0, columns=3)
        self.assertLess(compact_bg[2], stable_bg[2])
        self.assertEqual([v[3] for v in compact], [v[3] for v in stable])
        hidden, _ = self.render(mask=6, columns=3)
        self.assertEqual([v[3] for v in hidden], [v[3] for v in compact[2:]])
        wider, _ = self.render(mask=7, columns=3, digits=2)
        self.assertEqual(wider[1][3] + 1, compact[1][3])
        self.assertEqual(wider[3][3] + 1, compact[3][3])

    def test_editor_uses_maximum_values_and_reveals_disabled_fields(self):
        compact = self.render(mask=1, editing=1, compact=1)
        stable = self.render(mask=1, editing=1, compact=0)
        self.assertEqual(compact, stable)
        self.assertEqual(len(compact[0]), 22)

    def test_large_actual_values_still_fit_reserved_cells_and_background(self):
        calls, bg = self.render(compact=0, columns=2, digits=20, size=7)
        for i in range(0, len(calls), 2):
            self.assertGreaterEqual(calls[i+1][0], calls[i][0] + calls[i][2])
        self.assertEqual(max(v[0] + v[2] for v in calls), bg[0] + bg[2])

    def test_extreme_row_gap_fits_all_standard_fields_and_empty_mask_is_safe(self):
        calls, bg = self.render(columns=1, rowGap=16, size=28, y=450)
        self.assertEqual(len({v[1] for v in calls}), 11)
        self.assertLessEqual(bg[1] + bg[3], 456)
        calls, bg = self.render(mask=0)
        self.assertEqual(calls, [])
        self.assertEqual(bg[2], 0)

    def test_legacy_presence_defaults_and_new_reserved_bytes_round_trip(self):
        out = (C.c_uint * 14)()
        flags = self.lib.persist(0, 99, 99, 99, 99, out)
        self.assertEqual(list(out[:4]), [12, 0, 0, 0])
        self.assertEqual(flags & 0x3c00, 0x3c00)
        self.lib.persist(0x3c00, 32, 16, 11, 1, out)
        self.assertEqual(list(out[:4]), [32, 16, 11, 1])
        self.assertEqual(list(out[4:]), [0] * 10)
        self.lib.persist(0x3c00, 255, 255, 255, 255, out)
        self.assertEqual(list(out[:4]), [32, 16, 11, 1])


def math_ceil(value, divisor):
    return (value + divisor - 1) // divisor


if __name__ == "__main__":
    unittest.main()
