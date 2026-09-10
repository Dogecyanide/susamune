"""Shared PPC validators retain the C worker's checks and one emitted definition."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from elftools.elf.elffile import ELFFile
from test_state_pool_memory import Memory
from test_tas_storage_kernel import Component, Project, Tape

ROOT = Path(__file__).resolve().parents[1]
HELPERS = (
    'SusamuneStateCrcUpdate', 'SusamuneStateCrc', 'SusamuneStateNameValid',
    'SusamuneStateGameValid', 'SusamuneTasManifestCrc', 'SusamuneTasManifestValid',
    'StatePoolMemoryBufferValid', 'StatePoolMemoryValid', 'StatePoolMemoryRangeValid',
)
HEADERS = '#include "susamune/state_storage.h"\n#include "susamune/state_pool_memory.h"\n'


class SharedStateHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = ROOT / 'toolchain/clang.exe'
        if not cls.compiler.exists():
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-shared-validators-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)

    def symbols(self, path):
        with path.open('rb') as stream:
            elf = ELFFile(stream)
            return [(s.name, s['st_info']['bind'])
                    for s in elf.get_section_by_name('.symtab').iter_symbols()
                    if s['st_info']['type'] == 'STT_FUNC' and s['st_shndx'] != 'SHN_UNDEF']

    def compile_references(self, suffix, target):
        objects = []
        for unit in ('first', 'second'):
            source = self.folder / f'{unit}.{suffix}'
            source.write_text(HEADERS + f'void (*{unit}[])(void) = {{\n' +
                ',\n'.join(f'(void (*)(void)){name}' for name in HELPERS) + '\n};\n', encoding='ascii')
            obj = source.with_suffix('.o')
            subprocess.run([str(self.compiler), '--target=' + target, '-Oz',
                '-nostdinc++', '-fno-exceptions', '-fno-unwind-tables', '-fdata-sections',
                '-I', str(ROOT / 'include'), '-c', str(source), '-o', str(obj)],
                check=True, capture_output=True, text=True)
            objects.append(obj)
        return objects

    def test_powerpc_translation_units_share_each_validator(self):
        objects = self.compile_references('cpp', 'powerpc-gecko-ibm-kuribo-eabi')
        combined = self.folder / 'shared.o'
        subprocess.run([str(ROOT / 'toolchain/powerpc-eabi-ld.exe'), '-r',
            *(str(p) for p in objects), '-o', str(combined)],
            check=True, capture_output=True, text=True)
        symbols = self.symbols(combined)
        for helper in HELPERS:
            with self.subTest(helper=helper):
                found = [(name, bind) for name, bind in symbols if name.startswith(helper + '__')]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0][1], 'STB_WEAK')

    def test_arm_c_worker_keeps_local_definitions(self):
        for obj in self.compile_references('c', 'armv5te-none-eabi'):
            symbols = dict(self.symbols(obj))
            for helper in HELPERS:
                with self.subTest(unit=obj.name, helper=helper):
                    self.assertEqual(symbols.get(helper), 'STB_LOCAL')

    def test_cpp_and_c_reject_the_same_bad_manifests_and_bank_ranges(self):
        wrappers = r'''
#ifdef __cplusplus
extern "C" {
#endif
__declspec(dllexport) int API_manifest(const struct SusamuneTasManifest*p){return SusamuneTasManifestValid(p);}
__declspec(dllexport) int API_bank(const StatePoolMemory*p){return StatePoolMemoryValid(p);}
__declspec(dllexport) int API_range(const StatePoolMemory*p,unsigned o,unsigned n){return StatePoolMemoryRangeValid(p,o,n);}
#ifdef __cplusplus
}
#endif
'''
        objects = []
        for suffix, prefix in (('c', 'worker'), ('cpp', 'client')):
            source = self.folder / ('host.' + suffix)
            source.write_text(HEADERS + wrappers.replace('API_', prefix + '_'), encoding='ascii')
            obj = source.with_suffix('.obj')
            if suffix == 'cpp': obj = self.folder / 'client.obj'
            subprocess.run([str(self.compiler), '--target=x86_64-pc-windows-msvc', '-Oz',
                '-fno-exceptions', '-I', str(ROOT / 'include'), '-c', str(source), '-o', str(obj)],
                check=True, capture_output=True, text=True)
            objects.append(obj)
        dll = self.folder / 'validation.dll'
        subprocess.run([str(self.compiler), '--target=x86_64-pc-windows-msvc', '-shared',
            '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', *(str(p) for p in objects), '-o', str(dll)],
            check=True, capture_output=True, text=True)
        lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        try:
            for prefix in ('client', 'worker'):
                getattr(lib, prefix + '_manifest').argtypes = [C.c_void_p]
                getattr(lib, prefix + '_bank').argtypes = [C.POINTER(Memory)]
                getattr(lib, prefix + '_range').argtypes = [C.POINTER(Memory), C.c_uint, C.c_uint]
            original = Project(0x4D535450, 2, 17, 1, 0x474D534A, 123, 6789, 0x10203, 1, 2)
            original.name = b'Shared validator'
            original.components[0] = Component(1, 123, 256, 0, original.scene)
            original.components[1] = Component(2, 456, 512, 12, original.scene)
            original.tape = Tape(3, 789, 196)
            original.tapeFrames = 12
            original.start[:] = (0x12345678, 0xABCDEF01)
            original.seal()
            self.assertEqual(lib.client_manifest(C.byref(original)), 1)
            rng = random.Random(983)
            cases = [bytes(original)]
            for offset in range(C.sizeof(original)):
                data = bytearray(bytes(original)); data[offset] ^= rng.randrange(1, 256)
                cases.append(bytes(data))
                modified = Project.from_buffer_copy(data).seal()
                cases.append(bytes(modified))
            for data in cases:
                owner = C.create_string_buffer(data)
                self.assertEqual(lib.client_manifest(owner), lib.worker_manifest(owner))
            top = (1 << (8 * C.sizeof(C.c_void_p))) - 1
            for a, b, first, second in ((0x1000, 0x2000, 128, 64), (0x2000, 0x1000, 128, 64),
                    (0x1000, 0x1040, 128, 64), (0, 0x2000, 128, 64), (top - 15, 0, 32, 0),
                    (0x1000, 0, 128, 0), (0x1000, 0x2000, 0, 64), (0x1000, 0x2000, 0xFFFFFFFF, 64)):
                memory = Memory((C.c_void_p * 2)(a, b), (C.c_uint * 2)(first, second))
                self.assertEqual(lib.client_bank(C.byref(memory)), lib.worker_bank(C.byref(memory)))
                for offset, size in ((0, 0), (0, 1), (127, 65), (192, 0), (192, 1), (0xFFFFFFFF, 1)):
                    self.assertEqual(lib.client_range(C.byref(memory), offset, size),
                                     lib.worker_range(C.byref(memory), offset, size))
        finally:
            FreeLibrary(lib._handle)


if __name__ == '__main__':
    unittest.main()
