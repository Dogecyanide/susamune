"""Check the capability-selected pool/scratch pair and fixed neighboring owners."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class StateWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT/'toolchain/clang++.exe'
        if not compiler.exists():raise unittest.SkipTest('Bundled host compiler required')
        cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-state-workspace-')
        cls.addClassCleanup(cls.temp.cleanup)
        source=r'''
#include "susamune/susamune_cfg.h"
#include "susamune/state_codec.hxx"
#include "susamune/state_storage.h"
static SusamuneCfg testCfg;
#undef SUSAMUNE_CFG_PPC_PTR
#define SUSAMUNE_CFG_PPC_PTR (&testCfg)
#include "susamune/state_pool_runtime.hxx"
static StatePoolMemory sPoolMemory;
static_assert(SUSAMUNE_STATE_POOL_SIZE==0xFF0000u,"full primary");
static_assert(SUSAMUNE_STATE_POOL_LEGACY_SIZE==0xFA2000u,"legacy primary");
static_assert(SUSAMUNE_STATE_POOL_EXPANDED_SIZE==0x11F0000u,"two-bank capacity");
static_assert(SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE==0x4E000u,"scratch budget");
static_assert(StateCodec::kWorkspaceLimit<=SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE,"codec fits");
static_assert(SUSAMUNE_CONSOLE_STATE_CODEC_PPC_BASE==0x91891000u,"console scratch");
static_assert(SUSAMUNE_DOLPHIN_STATE_CODEC_PPC_BASE==0x71111000u,"Dolphin scratch");
static_assert(SUSAMUNE_CONSOLE_PRACTICE_TAPE_PPC_BASE+SUSAMUNE_PRACTICE_TAPE_SIZE<=SUSAMUNE_CONSOLE_STATE_CODEC_PPC_BASE,"console tape");
static_assert(SUSAMUNE_DOLPHIN_PRACTICE_TAPE_PPC_BASE+SUSAMUNE_PRACTICE_TAPE_SIZE<=SUSAMUNE_DOLPHIN_STATE_CODEC_PPC_BASE,"Dolphin tape");
static_assert(SUSAMUNE_STATE_CODEC_PPC_BASE+SUSAMUNE_STATE_CODEC_WORKSPACE_SIZE<=SUSAMUNE_GHOST_SECONDARY_HEAP_PPC_BASE,"model heap");
static_assert(SUSAMUNE_STATE_STORAGE_VERSION==4u && SUSAMUNE_STATE_ARCHIVE_VERSION==1u,"wire compatibility");
'''+function_source(ROOT/'src/savestate.cpp','void *codecWorkspace()')+r'''
extern "C" {
__declspec(dllexport) void select(unsigned magic,unsigned version,unsigned flags){
 testCfg.magic=magic;testCfg.version=version;testCfg.flags=flags;sPoolMemory=statePoolMemory();}
__declspec(dllexport) void change(unsigned magic,unsigned version,unsigned flags){
 testCfg.magic=magic;testCfg.version=version;testCfg.flags=flags;}
__declspec(dllexport) unsigned value(unsigned key){switch(key){
 case 0:return sPoolMemory.sizes[0];case 1:return sPoolMemory.sizes[1];
 case 2:return (__UINTPTR_TYPE__)sPoolMemory.banks[0];case 3:return (__UINTPTR_TYPE__)codecWorkspace();
 case 4:return SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED;case 5:return SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION;
 case 6:return SUSAMUNE_CFG_MAGIC;case 7:return SUSAMUNE_CFG_VERSION;}return 0;}
__declspec(dllexport) unsigned unknownLayout(){sPoolMemory.sizes[0]=0;return codecWorkspace()==nullptr;}
}
'''
        cls.libs=[]
        for emulator in (0,1):
            path=Path(cls.temp.name)/f'layout{emulator}.cpp';path.write_text(source)
            dll=path.with_suffix('.dll')
            compiled=subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-shared','-Oz',
                '-nostdlib','-fuse-ld=lld','-Wl,/noentry',f'-DIS_EMULATOR={emulator}',
                '-I',str(ROOT/'include'),str(path),'-o',str(dll)],capture_output=True,text=True)
            if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
            lib=C.CDLL(str(dll));cls.libs.append(lib)
            lib.value.argtypes=[C.c_uint];lib.value.restype=C.c_uint
            lib.select.argtypes=lib.change.argtypes=[C.c_uint]*3
            cls.addClassCleanup(lambda handle=lib._handle:C.windll.kernel32.FreeLibrary(C.c_void_p(handle)))
        cls.magic,cls.version,cls.relocated,cls.extra=(cls.libs[0].value(i)for i in (6,7,4,5))

    def test_console_selects_primary_and_workspace_as_one_capability_pair(self):
        lib=self.libs[0]
        for flags in (0,self.extra,self.relocated,self.extra|self.relocated):
            with self.subTest(flags=flags):
                lib.select(self.magic,self.version,flags)
                moved=bool(flags&self.relocated)
                self.assertEqual([lib.value(i)for i in range(4)],
                    [0xFF0000 if moved else 0xFA2000,0x200000 if flags&self.extra else 0,
                     0x91F00000,0x91891000 if moved else 0x92EA2000])

    def test_missing_unknown_and_future_config_never_borrow_the_ghost_gap(self):
        lib=self.libs[0]
        for magic,version in ((0,0),(self.magic,0),(self.magic,self.version+1),(self.magic^1,self.version)):
            lib.select(magic,version,self.relocated|self.extra)
            self.assertEqual([lib.value(i)for i in range(4)],[0xFA2000,0,0x91F00000,0x92EA2000])

    def test_dolphin_uses_separate_full_pool_and_scratch_without_launcher(self):
        lib=self.libs[1]
        for flags in (0,self.extra,self.relocated,self.extra|self.relocated):
            lib.select(0,0,flags)
            self.assertEqual([lib.value(i)for i in range(4)],[0xFF0000,0x200000,0x70000000,0x71111000])

    def test_latched_workspace_never_reinterprets_existing_slots_when_flags_change(self):
        for lib in self.libs:
            for flags in (0,self.extra|self.relocated):
                lib.select(self.magic,self.version,flags)
                before=[lib.value(i)for i in range(4)]
                lib.change(0,0,0 if flags else self.extra|self.relocated)
                self.assertEqual([lib.value(i)for i in range(4)],before)
                self.assertEqual(lib.unknownLayout(),1)

    def test_kernel_publishes_capability_only_after_clearing_stale_boot_config(self):
        init=function_source(ROOT/'launcher/kernel/SusamuneCfg.c','void SusamuneCfgInit(')
        self.assertLess(init.index('memset(cfg, 0, sizeof(struct SusamuneCfg))'),
                        init.index('SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED'))
        self.assertLess(init.index('if (!SusamuneCfgStorageAvailable())'),
                        init.index('SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED'))

    def test_ghost_worker_only_initializes_doorbells_and_uses_separate_payload_bank(self):
        source=(ROOT/'launcher/kernel/SusamuneGhost.c').read_text()
        init=function_source(ROOT/'launcher/kernel/SusamuneGhost.c','void SusamuneGhostInit(')
        self.assertIn('memset((void*)mailbox, 0, SUSAMUNE_GHOST_STORAGE_HEADER_SIZE)',init)
        self.assertNotIn('mailbox->payload',source)
        self.assertIn('SUSAMUNE_GHOST_STORAGE_DATA_PHYS_PTR',source)
        header=(ROOT/'include/susamune/ghost_storage.h').read_text()
        self.assertIn('((volatile unsigned char *)SUSAMUNE_GHOST_FILE_TRANSFER_PHYS_BASE)',header)

    def test_loader_dma_finishes_before_handoff_and_runtime_disc_io_has_another_bank(self):
        read=function_source(ROOT/'launcher/loader/source/dip.c','void ReadRealDisc(')
        self.assertLess(read.index('while(read32(DIP_CONTROL) & 1)'),read.index('memcpy(Buffer,'))
        runtime=(ROOT/'launcher/kernel/RealDI.c').read_text()
        self.assertIn('DISC_DRIVE_BUFFER = (u8*)(NIN_MEM2_DISC_CACHE_PHYS_BASE + 0x800u)',runtime)
        self.assertNotIn('NIN_MEM2_LOADER_DISC',runtime)


if __name__=='__main__':unittest.main()
