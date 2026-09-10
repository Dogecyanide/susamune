"""Check Sunshine's arcade-write refusal and temporary staging ownership."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class StateStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        path = ROOT / "launcher/kernel/DI.c"
        cls.di = path.read_text()
        begin = cls.di.index("if(IsSunshineDIMMWrite(DIcommand))")
        switch = cls.di.index("switch( DIcommand )", begin)
        guard = cls.di[begin:switch]
        default_start = cls.di.index("default:", switch)
        default_end = cls.di.index("case 0xE1:", default_start)
        default = cls.di[default_start:default_end]
        source = r'''
typedef unsigned int u32;typedef unsigned short u16;
static u32 GAME_ID;static u16 GAME_ID6;
static unsigned int shut,registers,arcadeWrites;
#define DI_BASE 0
#define dbgprintf(...) ((void)0)
void memset32(void*,u32,unsigned int){registers++;}
void Shutdown(){shut++;}
'''
        source += function_source(path, "static bool IsSunshineDIMMWrite(")
        source += r'''
extern "C" __declspec(dllexport) unsigned int run(u32 id,u16 maker,u32 DIcommand) {
    GAME_ID=id;GAME_ID6=maker;shut=registers=arcadeWrites=0;u32 i;
'''+ guard + "switch(DIcommand) {\n" + default + r'''
case 0xAA: arcadeWrites++; break;
case 0xA8: break;
}
return shut | (registers<<4) | (arcadeWrites<<8);
}
'''
        shim = Path(cls.folder.name) / "staging.cpp"
        shim.write_text(source, encoding="ascii")
        library = shim.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(shim), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.run.argtypes = [C.c_uint, C.c_ushort, C.c_uint]
        cls.lib.run.restype = C.c_uint

    def test_three_sunshine_discs_reject_before_any_arcade_write(self):
        for game in (0x474D534A, 0x474D5345, 0x474D5350):
            self.assertEqual(self.lib.run(game, 0x3031, 0xAA), 0x11)
            self.assertEqual(self.lib.run(game, 0x3031, 0xA8), 0)

    def test_other_games_and_arcade_commands_keep_existing_behavior(self):
        for game in (0x47475045, 0x4750504A, 0x474C4D4A, 0):
            self.assertEqual(self.lib.run(game, 0x3031, 0xAA), 0x100)
        self.assertEqual(self.lib.run(0x474D5345, 0x3831, 0xAA), 0x100)

    def test_guard_runs_after_command_decode_before_dma_or_dimm_access(self):
        dispatch = self.di[self.di.index("void DIUpdateRegisters("):]
        self.assertLess(dispatch.index("IsSunshineDIMMWrite(DIcommand)"),
                        dispatch.index("switch( DIcommand )"))
        self.assertLess(dispatch.index("switch( DIcommand )"),
                        dispatch.index("case 0xAA:"))
        init = function_source(ROOT / "launcher/kernel/DI.c", "void DIinit(")
        self.assertIn("if (FirstTime)", init)
        self.assertLess(init.index("if (FirstTime)"), init.index("memset32( DIMMMemory"))
        reset = function_source(ROOT / "launcher/kernel/TRI.c", "void TRIReset(")
        self.assertNotIn("DIMM", reset)
        self.assertNotIn("SegaBoot", reset)


if __name__ == "__main__":
    unittest.main()
