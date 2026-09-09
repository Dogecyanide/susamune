"""Verify launcher translations, glyph coverage, and lazy font ownership."""
import ctypes as C
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
import zipfile

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "launcher/loader/source/SusamuneTextData.inc"


def translations():
    return [tuple(json.loads(s) for s in pair) for pair in re.findall(
        r'\{("(?:\\.|[^"\\])*"), ("(?:\\.|[^"\\])*")\}', DATA.read_text(encoding="utf-8"))]


def tables(font):
    return {tag: font[offset:offset+size] for tag, _, offset, size in (
        struct.unpack_from(">4sIII", font, 12 + 16*i)
        for i in range(struct.unpack_from(">H", font, 4)[0]))}


def cmap(font):
    data = tables(font)[b"cmap"]
    codepoints = set()
    u16 = lambda offset: struct.unpack_from(">H", data, offset)[0]
    for i in range(u16(2)):
        platform, encoding, offset = struct.unpack_from(">HHI", data, 4+8*i)
        if platform not in (0, 3) or u16(offset) != 4:
            continue
        count = u16(offset+6)//2
        end = offset+14
        start = end+2*count+2
        delta = start+2*count
        ranges = delta+2*count
        for j in range(count):
            first, last = u16(start+2*j), u16(end+2*j)
            if first == 0xffff:
                continue
            shift, distance = u16(delta+2*j), u16(ranges+2*j)
            for point in range(first, last+1):
                glyph = (point+shift)&0xffff if not distance else u16(ranges+2*j+distance+2*(point-first))
                if glyph:
                    codepoints.add(point)
    return codepoints


class LauncherJapaneseContentTests(unittest.TestCase):
    def test_sorted_unique_catalog_preserves_printf_arguments(self):
        pairs = translations()
        self.assertGreaterEqual(len(pairs), 90)
        self.assertEqual([a for a, _ in pairs], sorted(set(a for a, _ in pairs)))
        pattern = r"%(?:[-+ #0]*\d*(?:\.\d+)?[sdu]|%)"
        for english, japanese in pairs:
            with self.subTest(english=english):
                self.assertEqual(re.findall(pattern, english), re.findall(pattern, japanese))

    def test_static_font_covers_every_translation_and_controller_arrow(self):
        with zipfile.ZipFile(ROOT / "launcher/loader/data/font_ja.zip") as archive:
            self.assertEqual(archive.namelist(), ["font.ttf"])
            font = archive.read("font.ttf")
        required = set(range(0x20, 0x7f)) | {0x25c0, 0x25b6}
        required.update(ord(c) for pair in translations() for text in pair for c in text if ord(c) >= 0x20)
        self.assertFalse(required-cmap(font), required-cmap(font))
        self.assertLess(len(font), 128*1024)
        self.assertIn(b"glyf", tables(font))
        self.assertNotIn(b"fvar", tables(font))
        self.assertNotIn(b"gvar", tables(font))

    def test_japanese_static_lines_fit_the_launcher_width(self):
        from PIL import ImageFont
        with zipfile.ZipFile(ROOT / "launcher/loader/data/font_ja.zip") as archive:
            font = ImageFont.truetype(io.BytesIO(archive.read("font.ttf")), 16)
        for english, japanese in translations():
            if "%" not in japanese:
                with self.subTest(english=english):
                    self.assertLessEqual(font.getlength(japanese), 560)

    def test_every_setting_name_and_help_line_has_translation(self):
        menu = (ROOT / "launcher/loader/source/SusamuneMenu.c").read_text()
        source = menu[menu.index("static const char *const kSettingNames"):menu.index("static const char *SettingValue")]
        translated = dict(translations())
        for value in re.findall(r'"([^"\n]*)"', source):
            if value:
                self.assertIn(value, translated)

    def test_locale_changes_after_settings_load_and_version_selection(self):
        main = (ROOT / "launcher/loader/source/main.c").read_text()
        menu = (ROOT / "launcher/loader/source/SusamuneMenu.c").read_text()
        self.assertLess(main.index("SusamuneIniLoad(GetRootDevice())"), main.index("SusamuneTextSetJapanese("))
        version = menu[menu.index("case ROW_VERSION:"):menu.index("case ROW_PATH:")]
        self.assertIn("SusamuneTextSetJapanese(gIni.version == SUSA_VER_JP)", version)
        self.assertIn("ガイド（英語）", dict(translations())["Guide%s"])


class LauncherJapaneseRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-launcher-jp-")
        cls.addClassCleanup(cls.temp.cleanup)
        production = (ROOT / "launcher/loader/source/SusamuneText.c").read_text()
        code = r'''
typedef __SIZE_TYPE__ size_t;typedef int bool;
#define true 1
#define false 0
#define NULL ((void*)0)
typedef struct {int face;}GRRLIB_ttfFont;
typedef struct {const char*english;const char*japanese;}LauncherText;
static unsigned unzipCalls,loads,frees,faceFrees,sequence;static int failUnzip,failFace;
static char bytes[16];static GRRLIB_ttfFont english,ja,*myFont=&english,*sFont;static void*sFontData;static bool sJapanese;
static char font_ja_zip[1];static unsigned font_ja_zip_size=1;
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (unsigned char)*a-(unsigned char)*b;}
bool unzip_data(const void*in,unsigned n,void**out,unsigned*size){unzipCalls++;*out=failUnzip?NULL:bytes;*size=16;return !failUnzip;}
GRRLIB_ttfFont*GRRLIB_LoadTTF(const void*data,unsigned n){loads++;return failFace?NULL:&ja;}
void GRRLIB_FreeTTF(GRRLIB_ttfFont*font){if(font){faceFrees++;sequence=sequence*10+1;}}
void free(void*p){if(p){frees++;sequence=sequence*10+2;}}
'''
        code += DATA.read_text(encoding="utf-8")
        for name in ("SusamuneTextSetJapanese", "SusamuneTextShutdown", "SusamuneText", "SusamuneTextFont"):
            code += function(production, name)
        code += r'''
__declspec(dllexport) void reset(int zip,int face){SusamuneTextShutdown();unzipCalls=loads=frees=faceFrees=sequence=0;failUnzip=zip;failFace=face;}
__declspec(dllexport) const char*translate(unsigned enabled,const char*text){SusamuneTextSetJapanese(enabled);return SusamuneText(text);}
__declspec(dllexport) unsigned stats(unsigned which){switch(which){case 0:return unzipCalls;case 1:return loads;case 2:return frees;case 3:return faceFrees;case 4:return sequence;case 5:return SusamuneTextFont()==&ja;}return 0;}
__declspec(dllexport) void finish(void){SusamuneTextShutdown();}
'''
        source = Path(cls.temp.name) / "text.c"
        source.write_text(code, encoding="utf-8")
        library = source.with_suffix(".dll")
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                                 "-nostdlib", "-fno-builtin", "-O2", "-fuse-ld=lld", "-Wl,/noentry",
                                 str(source), "-o", str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.translate.argtypes = [C.c_uint, C.c_char_p]
        cls.lib.translate.restype = C.c_char_p

    def test_all_catalog_entries_switch_with_region_and_unknown_paths_stay_verbatim(self):
        self.lib.reset(0, 0)
        for english, japanese in translations():
            self.assertEqual(self.lib.translate(0, english.encode()), english.encode())
            self.assertEqual(self.lib.translate(1, english.encode()), japanese.encode())
        self.assertEqual(self.lib.translate(1, b"sd:/custom/game.iso"), b"sd:/custom/game.iso")
        self.assertEqual([self.lib.stats(i) for i in (0, 1, 5)], [1, 1, 1])
        self.lib.finish()
        self.assertEqual([self.lib.stats(i) for i in (2, 3, 4, 5)], [1, 1, 12, 0])

    def test_english_loads_no_extra_font_and_failed_japanese_face_stays_readable(self):
        self.lib.reset(0, 0)
        self.assertEqual(self.lib.translate(0, b"Select"), b"Select")
        self.assertEqual([self.lib.stats(i) for i in (0, 1, 5)], [0, 0, 0])
        for archive, face, expected_frees in ((1, 0, 0), (0, 1, 1)):
            self.lib.reset(archive, face)
            self.assertEqual(self.lib.translate(1, b"Select"), b"Select")
            self.assertEqual(self.lib.stats(5), 0)
            self.assertEqual(self.lib.stats(2), expected_frees)


if __name__ == "__main__":
    unittest.main()
