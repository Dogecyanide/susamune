"""Exercise the actual FLUDD palette conversion with synthetic CMPR blocks."""
import ctypes as C
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def offset(x, y):
    return ((y // 8) * 8 + x // 8) * 32 + ((y % 8) // 4 * 2 + (x % 8) // 4) * 8


class FluddTextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled compiler required')
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        shim = Path(cls.folder.name) / 'shim.cpp'
        shim.write_text('''#include "susamune/fludd_color_texture.hxx"
extern "C" __declspec(dllexport) void recolor(const unsigned char*s,unsigned char*d,
const unsigned char*c,unsigned mask,unsigned part){FluddColorTexture::recolor(s,d,
reinterpret_cast<const unsigned char(*)[3]>(c),mask,part);}
''')
        library = shim.with_suffix('.dll')
        subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared',
                        '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
                        '-fno-builtin', '-I', str(ROOT / 'include'), str(shim),
                        str(ROOT / 'src/fludd_color_texture.cpp'), '-o', str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.recolor.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint, C.c_uint]

    def recolor(self, source, mask, part=0, colors=None):
        src = C.create_string_buffer(bytes(source))
        dst = C.create_string_buffer(b'G' * (4096 + 64))
        colors = colors or [(255, 255, 255)] * 10
        rgb = C.create_string_buffer(bytes(c for color in colors for c in color))
        self.lib.recolor(src, C.addressof(dst) + 32, rgb, mask, part)
        self.assertEqual(src.raw[:-1], bytes(source))
        self.assertEqual(dst.raw[:32] + dst.raw[4128:4160], b'G' * 64)
        return dst.raw[32:4128]

    def test_original_and_unrelated_water_settings_leave_atlas_exact(self):
        source = random.Random(48).randbytes(4096)
        for mask in (0, 1 << 8, 1 << 9):
            self.assertEqual(self.recolor(source, mask), source)

    def test_parts_are_independent_and_nozzles_use_their_own_paint(self):
        source = bytearray(4096)
        blocks = [(40, 56, 0xFFE0), (20, 80, 0xAD75), (40, 12, 0xA200), (12, 36, 0x001F)]
        parts = [0, 1, 2, 3]
        for x, y, color in blocks:
            struct.pack_into('>HHI', source, offset(x, y), color, 0, 0x1B1B1B1B)
        for part in range(4):
            out = self.recolor(source, 1 << part)
            for i, (x, y, _) in enumerate(blocks):
                start = offset(x, y)
                if parts[i] != part:
                    self.assertEqual(out[start:start+8], source[start:start+8])
                else:
                    color = struct.unpack_from('>H', out, start)[0]
                    rgb = (color >> 11, ((color >> 5) & 63) // 2, color & 31)
                    self.assertLessEqual(max(rgb)-min(rgb), 1)
        for nozzle in range(4, 8):
            self.assertEqual(self.recolor(source, 1 << nozzle), source)
            out = self.recolor(source, 1 << nozzle, nozzle)
            self.assertNotEqual(out[offset(40,56):offset(40,56)+8], source[offset(40,56):offset(40,56)+8])

    def test_black_retains_opaque_mode_and_alpha_indices(self):
        source = bytearray(4096)
        struct.pack_into('>HHI', source, offset(40,56), 0xFFE0, 0xADE0, 0x1B1B1B1B)
        struct.pack_into('>HHI', source, offset(40,64), 0xADE0, 0xFFE0, 0xFFFFFFFF)
        out = self.recolor(source, 1, colors=[(0,0,0)]*10)
        a,b = struct.unpack_from('>HH',out,offset(40,56))
        self.assertGreater(a,b)
        self.assertLessEqual(a,1)
        a,b = struct.unpack_from('>HH',out,offset(40,64))
        self.assertLessEqual(a,b)
        self.assertEqual(out[offset(40,64)+4:offset(40,64)+8],b'\xff'*4)


if __name__ == '__main__':
    unittest.main()
