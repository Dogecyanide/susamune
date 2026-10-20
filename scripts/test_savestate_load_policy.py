"""Execute ordinary-load routing with instrumented checked/experimental backends."""
import ctypes
from _ctypes import FreeLibrary
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class LoadPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='load-policy-', dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = ROOT / 'src/savestate.cpp'
        load = function_source(source, 'bool SavestateManager::loadSlot(')
        marker = '} else if (TransferLease::sharedMap()) {'
        routing = load.split(marker, 1)[1].split('} else if (packedChecksum(', 1)[0]
        wrappers = '\n'.join(function_source(source, name) for name in (
            'bool SavestateManager::loadOrdinarySlot(', 'bool SavestateManager::loadState('))
        cpp = r'''
typedef unsigned int u32;
static bool sOrdinaryRamLoad, durable, failEarly, failRestore;
static unsigned checked, experimental, sdLoads;
enum {SETTING_EXPERIMENTAL_RAM_LOAD, SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE=0x4e000};
static struct Settings {bool enabled; bool getBool(int)const{return enabled;}} gSettings;
static struct {unsigned id,headerCrc,packedSize;} sSelectedSD;
static unsigned sLoadSlot,sSharedStore,sLiveArchiveProfile,copyStateBytes,directStateBytes;
static struct Header {unsigned region_count;} header,*h=&header;
static unsigned destinations;
static void *codecWorkspace(){return 0;}
namespace Ghost {enum {kSavestateSpanCount=2};}
namespace PracticeSession {enum {kSavestateSpanCount=3};}
namespace StateStore {
struct Identity {};
template<class... T> int restoreSlotExperimental(T...){++experimental;return !failRestore;}
template<class... T> int restoreSlot(T...){++checked;return !failRestore;}
}
static StateStore::Identity sharedIdentity(unsigned){return {};}
struct SavestateManager {
 struct Info {unsigned generation;};
 Info slotInfo(unsigned){return {7};}
 bool beginSDLoad(unsigned,unsigned,unsigned,bool){++sdLoads;return true;}
 bool loadState(); bool loadOrdinarySlot(u32,u32); bool loadSlot(u32,u32);
};
bool SavestateManager::loadSlot(u32 slot,u32 expectedGeneration){
 if(failEarly)return false;
 int restored=0;
''' + routing + r'''
 return restored!=0;
}
''' + wrappers + r'''
extern "C" __declspec(dllexport) unsigned run(unsigned mode,unsigned enabled,
 unsigned isDurable,unsigned sd,unsigned failure){
 sOrdinaryRamLoad=false;durable=isDurable;gSettings.enabled=enabled;
 failEarly=failure==1;failRestore=failure==2;
 checked=experimental=sdLoads=0;sSelectedSD.id=sd;
 SavestateManager manager;
 bool ok=mode==0?manager.loadSlot(0,7):mode==1?manager.loadOrdinarySlot(0,7):manager.loadState();
 return checked|(experimental<<4)|(sdLoads<<8)|(sOrdinaryRamLoad?0x1000:0)|(ok?0x10000:0);
}
'''
        wrapper = folder / 'policy.cpp'
        wrapper.write_text(cpp)
        library = folder / 'policy.dll'
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-std=c++17', '-O2', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
            '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry',
            str(wrapper), '-o', str(library)], check=True,
            env={**os.environ, 'TMP': str(folder), 'TEMP': str(folder)})
        cls.lib = ctypes.CDLL(str(library))
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)
        cls.lib.run.argtypes = [ctypes.c_uint] * 5
        cls.lib.run.restype = ctypes.c_uint

    def test_only_enabled_ordinary_ram_uses_experimental_backend(self):
        for mode in (0, 1, 2):
            for enabled in (0, 1):
                for durable in (0, 1):
                    expected = 0x10 if mode != 0 and enabled and not durable else 1
                    self.assertEqual(self.lib.run(mode, enabled, durable, 0, 0), 0x10000 | expected)

    def test_selected_sd_keeps_its_checked_import_path(self):
        self.assertEqual(self.lib.run(2, 1, 0, 123, 0), 0x10100)

    def test_failed_loads_clear_the_ordinary_marker(self):
        self.assertEqual(self.lib.run(1, 1, 0, 0, 1), 0)
        self.assertEqual(self.lib.run(1, 1, 0, 0, 2), 0x10)


if __name__ == '__main__':
    unittest.main()
