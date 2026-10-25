"""Exercise feature shortcut edges, modal guards and the persisted append-only table."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FeatureBindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "src/feature_binds.cpp").read_text()
        source = source[source.index("namespace FeatureBinds"):]
        binds = (ROOT / "src/binds.cpp").read_text()
        from test_native_timer_creation import function
        edge = function(binds, "Binds::wasPressed")
        shim = r"""
#include "susamune/settings_list.h"
#include "susamune/binds_list.h"
typedef unsigned char u8;typedef unsigned short u16;
#define ID(name,key) name,
enum SettingId{SUSAMUNE_SETTING_LIST(ID) SETTING_COUNT};
enum BindId{SUSAMUNE_BIND_LIST(ID) BIND_COUNT};
#undef ID
struct Binds {u16 mMask[BIND_COUNT],mHeld,mPrevHeld;bool enabled;
 bool live()const{return enabled;}bool wasPressed(BindId)const;}gBinds;
unsigned changes;
struct Settings {u8 values[SETTING_COUNT];
 void cycle(SettingId id,int){values[id]=(values[id]+1)%(id==SETTING_FLUDD_SECRETS?3:id==SETTING_NOZZLE_LOCK?4:2);++changes;}
 static const char*name(SettingId){return "Feature";}const char*valueLabel(SettingId){return "Value";}
}gSettings;
struct Menu{bool visible;bool shown(){return visible;}void toast(const char*){}}menu,*gMenu=&menu;
int snprintf(char*,unsigned,const char*,...){return 0;}
"""
        exports = r"""
#define API extern "C" __declspec(dllexport)
API unsigned count(){return sizeof(FeatureBinds::kFeatureBindSettings);}
API unsigned settings(unsigned row){return FeatureBinds::kFeatureBindSettings[row];}
API unsigned value(unsigned id){return gSettings.values[id];}
API unsigned edge(unsigned row,unsigned held,unsigned before,unsigned assigned,unsigned shown,unsigned allowed){
 for(unsigned i=0;i<BIND_COUNT;++i)gBinds.mMask[i]=0;
 gBinds.mMask[BIND_FEATURE_FAST_TEXT+row]=assigned;gBinds.mHeld=held;gBinds.mPrevHeld=before;
 gBinds.enabled=allowed;menu.visible=shown;changes=0;FeatureBinds::update();return changes;
}
"""
        cls.temp=tempfile.TemporaryDirectory(prefix="feature-binds-")
        cls.addClassCleanup(cls.temp.cleanup)
        path=Path(cls.temp.name)/"fixture.cpp";path.write_text(shim+edge+source+exports)
        dll=path.with_suffix(".dll")
        subprocess.run([str(ROOT/"toolchain/clang++.exe"),"--target=x86_64-pc-windows-msvc","-shared","-nostdlib","-fuse-ld=lld","-Wl,/noentry","-O2","-I",str(ROOT/"include"),str(path),"-o",str(dll)],check=True)
        cls.lib=C.CDLL(str(dll))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_each_feature_uses_one_press_and_remains_silent_unbound_or_owned(self):
        for row in range(self.lib.count()):
            for held,prev,assigned,shown,allowed in ((0,0,0,0,1),(0x100,0x100,0x100,0,1),(0x101,0,0x100,0,1),(0x100,0,0x100,1,1),(0x100,0,0x100,0,0)):
                self.assertEqual(self.lib.edge(row,held,prev,assigned,shown,allowed),0)
            self.assertEqual(self.lib.edge(row,0x100,0,0x100,0,1),1)

    def test_choices_cycle_through_off_and_all_existing_options(self):
        for row,count in ((1,3),(4,4)):
            setting=self.lib.settings(row);start=self.lib.value(setting)
            for n in range(1,count+1):
                self.assertEqual(self.lib.edge(row,0x100,0,0x100,0,1),1)
                self.assertEqual(self.lib.value(setting),(start+n)%count)

    def test_new_binds_are_all_unassigned_and_fit_existing_mailbox(self):
        ids=re.findall(r'X\((BIND_\w+),',(ROOT/'include/susamune/binds_list.h').read_text())
        descs=re.findall(r'^BIND_DESC\(.*?,\s*(.*?)\)$',(ROOT/'src/binds_descs.inc').read_text(),re.M)
        self.assertEqual(len(ids),59);self.assertEqual(len(ids),len(descs))
        self.assertEqual(descs[46:58],['0']*12)
        self.assertEqual((ids[58],descs[58]),('BIND_MENU_SEARCH','kL | kY'))
        self.assertEqual(ids[45],'BIND_SAVESTATE_LOAD_3')
        self.assertEqual(len({self.lib.settings(i) for i in range(self.lib.count())}),12)
        self.assertLessEqual(len(ids),64)

if __name__=='__main__':unittest.main()
