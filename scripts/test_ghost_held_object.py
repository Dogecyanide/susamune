"""Run production held-object model selection against retail actor identities."""
import ctypes
import _ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class HeldObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-held-object-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        source = (ROOT / "src/ghost_model.cpp").read_text()
        code = r'''
using u16=unsigned short;using u32=unsigned;
namespace JGadget {
struct TList_pointer_void {
 using iterator=void**;void**first;void**last;
 iterator begin(){return first;}iterator end(){return last;}
};
}
struct J3DModel {};
struct MActor {J3DModel*mModel;};
struct THitActor {u32 mObjectID;u16 mKeyCode;};
struct TLiveActor:THitActor {MActor*mActorData;};
struct TResetFruit:TLiveActor {enum {COCONUT=0x40000390u,BANANA=0x40000394u};};
struct TIdxGroupObj {JGadget::TList_pointer_void mViewObjList;};
struct Strategy {TIdxGroupObj*mEnemyGroup;TIdxGroupObj*mObjectGroup;};
Strategy*gpStrategy;
'''
        for name in ("kRedPepperObjectId", "kJumpBaseObjectId"):
            code += re.search(r"const u32 " + name + r"\s*=.*?;", source)[0] + "\n"
        for name in ("isSupportedFruit", "heldFruitSource", "heldJumpBaseSource"):
            code += function(source, name) + "\n"
        code += r'''
extern "C" __declspec(dllexport) int lookup(unsigned id,int jump,int failure) {
 J3DModel model;MActor data={&model};
 TLiveActor wrongId={{id^0x100,0x1720},&data};
 TLiveActor wrongKey={{id,0x1721},&data};
 TLiveActor correct={{id,0x1720},&data};
 void*rows[]={nullptr,&wrongId,&wrongKey,&correct};
 TIdxGroupObj populated={{rows,rows+4}},empty={{rows,rows}};
 Strategy strategy={jump?&empty:&populated,jump?&populated:&empty};
 gpStrategy=&strategy;
 if(failure==1)gpStrategy=nullptr;
 if(failure==2){strategy.mEnemyGroup=nullptr;strategy.mObjectGroup=nullptr;}
 if(failure==3)correct.mKeyCode=0x1721;
 if(failure==4)correct.mActorData=nullptr;
 if(failure==5)data.mModel=nullptr;
 if(failure==6){strategy.mEnemyGroup=jump?&populated:&empty;strategy.mObjectGroup=jump?&empty:&populated;}
 return (jump?heldJumpBaseSource(id,0x1720):heldFruitSource(id,0x1720))==&model;
}
'''
        cpp, dll = directory / "test.cpp", directory / "test.dll"
        cpp.write_text(code)
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                                 "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry",
                                 "-std=c++17", "-O2", str(cpp), "-o", str(dll)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = ctypes.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.lookup.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int]
        cls.lib.lookup.restype = ctypes.c_int

    def test_six_retail_fruits_include_recorded_red_pepper(self):
        for object_id in range(0x40000390, 0x40000396):
            with self.subTest(object_id=hex(object_id)):
                self.assertEqual(self.lib.lookup(object_id, 0, 0), 1)
        for object_id in (0, 0x4000038F, 0x40000396, 0x80000395):
            self.assertEqual(self.lib.lookup(object_id, 0, 0), 0)

    def test_pepper_requires_matching_identity_group_and_live_model(self):
        for failure in range(1, 7):
            with self.subTest(failure=failure):
                self.assertEqual(self.lib.lookup(0x40000395, 0, failure), 0)

    def test_jump_base_keeps_separate_exact_id_and_object_group(self):
        self.assertEqual(self.lib.lookup(0x40000017, 1, 0), 1)
        self.assertEqual(self.lib.lookup(0x40000395, 1, 0), 0)
        for failure in range(1, 7):
            self.assertEqual(self.lib.lookup(0x40000017, 1, failure), 0)


if __name__ == "__main__":
    unittest.main()
