"""Execute display-favourite storage and routing without touching game memory."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function
from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class DisplayFavoritesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="display-favorites-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = r'''
#include "susamune/settings.hxx"
static Settings localSettings;
Settings &gSettings=localSettings;
static const int kSettingDescs[SETTING_COUNT]={};
static u8 choiceCount(int){return 2;}
static unsigned lastOwner,lastRow,changes;
static void hit(unsigned owner,unsigned row){lastOwner=owner;lastRow=row;++changes;}
struct InputDisplay {
 static const char*menuRowName(int){return "input";}
 const char*menuRowValue(int)const{return "input";}
 void adjustMenuRow(int row,int){hit(1,row);}
}gInputDisplay;
struct MetadataDisplay {
 enum{FIELD_COUNT=11};
 static const char*menuRowName(int){return "metadata";}
 const char*menuRowValue(int)const{return "metadata";}
 void adjustMenuRow(int row,int){hit(2,row);}
}gMetadataDisplay;
struct CreationExtras {
 static const char*menuRowName(int){return "word";}
 const char*menuRowValue(int)const{return "word";}
 void adjustMenuRow(int row,int){hit(3,row);}
 bool timerLabelVisible()const{return true;}
 void toggleTimerLabel(){hit(5,0);}
}gCreationExtras;
struct QftDisplay {
 bool leadingZero()const{return false;}
 void toggleLeadingZero(){hit(4,0);}
}gQftDisplay;
'''
        source += function_source(ROOT / "src/settings.cpp", "void Settings::set(")
        menu = (ROOT / "src/menu.cpp").read_text()
        source += function(menu, "namespace DisplayFavorites")
        source += r'''
#define API extern "C" __declspec(dllexport)
API void reset(){for(int i=0;i<SETTING_COUNT;++i)gSettings.set((SettingId)i,0);changes=0;}
API unsigned count(){return DisplayFavorites::COUNT;}
API void toggle(unsigned item){DisplayFavorites::toggle(item);}
API unsigned favorite(unsigned item){return DisplayFavorites::favorite(item);}
API unsigned bank(unsigned index){return gSettings.get((SettingId)(SETTING_DISPLAY_FAVORITES_0+index));}
API void restore(unsigned index,unsigned bits){gSettings.set((SettingId)(SETTING_DISPLAY_FAVORITES_0+index),bits);}
API unsigned unrelated(){unsigned sum=0;for(int i=0;i<SETTING_COUNT;++i)
 if(i<SETTING_DISPLAY_FAVORITES_0||i>SETTING_DISPLAY_FAVORITES_3)sum+=gSettings.get((SettingId)i);return sum;}
API unsigned adjust(unsigned item){changes=0;DisplayFavorites::adjust(item,1);return lastOwner*100+lastRow;}
API unsigned actions(){return changes;}
'''
        path = Path(cls.temp.name) / "display.cpp"
        path.write_text(source, encoding="ascii")
        dll = path.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(path), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_every_display_option_has_independent_restorable_bits(self):
        self.lib.reset()
        self.assertEqual(self.lib.count(), 28)
        wanted = {i for i in range(28) if i % 3 != 1}
        for item in wanted:
            self.lib.toggle(item)
        saved = [self.lib.bank(i) for i in range(4)]
        self.assertEqual(self.lib.unrelated(), 0)
        self.lib.reset()
        for index, bits in enumerate(saved):
            self.lib.restore(index, bits)
        self.assertEqual({i for i in range(28) if self.lib.favorite(i)}, wanted)
        for item in wanted:
            self.lib.toggle(item)
        self.assertEqual([self.lib.bank(i) for i in range(4)], [0] * 4)

    def test_all_display_options_route_to_the_owning_live_control(self):
        expected = list(range(100, 104)) + list(range(200, 214)) + list(range(216, 220))
        expected += [311, 314, 317, 400, 500, 220]
        self.assertEqual([self.lib.adjust(i) for i in range(28)], expected)

    def test_invalid_favourites_do_not_touch_storage(self):
        self.lib.reset()
        for item in (28, 29, 255, 0xFFFFFFFF):
            self.lib.toggle(item)
            self.assertFalse(self.lib.favorite(item))
        self.assertEqual([self.lib.bank(i) for i in range(4)], [0] * 4)
        self.assertEqual(self.lib.unrelated(), 0)


if __name__ == "__main__":
    unittest.main()
