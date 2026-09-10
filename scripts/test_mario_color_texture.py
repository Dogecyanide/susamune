"""Exercise the production atlas recolour without distributing retail assets."""
import ctypes as C
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block_offset(x, y):
    return ((y // 8) * 32 + x // 8) * 32 + ((y % 8) // 4 * 2 + (x % 8) // 4) * 8


def block_pixels(data, offset):
    a, b = struct.unpack_from('>HH', data, offset)
    def rgb(value):
        return (value >> 11, (value >> 5) & 63, value & 31)
    colors = [rgb(a), rgb(b)]
    if a > b:
        colors += [tuple((2 * colors[0][i] + colors[1][i]) // 3 for i in range(3)),
                   tuple((colors[0][i] + 2 * colors[1][i]) // 3 for i in range(3))]
    else:
        colors += [tuple((colors[0][i] + colors[1][i]) // 2 for i in range(3)), None]
    return [colors[(data[offset + 4 + y] >> (6 - 2 * x)) & 3]
            for y in range(4) for x in range(4)]


class MarioColorTextureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        shim = Path(cls.folder.name) / 'shim.cpp'
        shim.write_text('''#include "susamune/mario_color_texture.hxx"
extern "C" __declspec(dllexport) void recolor(const unsigned char*s,unsigned char*d,
 const unsigned char*c,unsigned mask){MarioColorTexture::recolor(s,d,
 reinterpret_cast<const unsigned char(*)[3]>(c),mask);}
''')
        library = shim.with_suffix('.dll')
        subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared',
                        '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
                        '-fno-builtin', '-I', str(ROOT / 'include'), str(shim),
                        str(ROOT / 'src/mario_color_texture.cpp'), '-o', str(library)],
                       check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.recolor.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_uint]

    def recolor(self, source, mask, colors=None):
        colors = colors or [(255, 255, 255)] * 7
        src = C.create_string_buffer(bytes(source))
        dst = C.create_string_buffer(b'G' * (32768 + 64))
        rgb = C.create_string_buffer(bytes(c for row in colors for c in row))
        self.lib.recolor(src, C.addressof(dst) + 32, rgb, mask)
        self.assertEqual(src.raw[:-1], bytes(source))
        self.assertEqual(dst.raw[:32], b'G' * 32)
        self.assertEqual(dst.raw[32800:32832], b'G' * 32)
        return dst.raw[32:32800]

    def test_original_is_byte_identical(self):
        source = random.Random(28).randbytes(32768)
        self.assertEqual(self.recolor(source, 0), source)

    def test_each_clothing_region_can_be_white_without_touching_skin(self):
        source = bytearray(32768)
        regions = [(224, 180, 0, 0xF800), (72, 172, 1, 0xF800),
                   (48, 104, 2, 0x001F), (140, 184, 3, 0xFFFF),
                   (20, 200, 4, 0xAC40), (196, 104, 6, 0xFC10)]
        skin = [(76, 216), (132, 64), (176, 136)]
        for x, y, _, color in regions:
            struct.pack_into('>HHI', source, block_offset(x, y), color, 0, 0x1B1B1B1B)
        for x, y in skin:
            struct.pack_into('>HHI', source, block_offset(x, y), 0xFC10, 0xDB0B, 0x12345678)
        for x, y, part, _ in regions:
            result = self.recolor(source, 1 << part)
            color = struct.unpack_from('>H', result, block_offset(x, y))[0]
            r, g, b = color >> 11, ((color >> 5) & 63) // 2, color & 31
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 1)
            for sx, sy in skin:
                off = block_offset(sx, sy)
                self.assertEqual(result[off:off + 8], source[off:off + 8])

    def test_shared_shirt_and_overalls_patch_preserves_buttons(self):
        source = bytearray(32768)
        for x, color in [(0, 0xF800), (4, 0x001F), (8, 0xFFE0)]:
            struct.pack_into('>HHI', source, block_offset(x, 12), color, 0, 0)
        result = self.recolor(source, 2, [(0, 255, 0)] * 7)
        self.assertEqual(struct.unpack_from('>H', result, block_offset(0, 12))[0], 0x07E0)
        for x in [4, 8]:
            off = block_offset(x, 12)
            self.assertEqual(result[off:off + 8], source[off:off + 8])

    def test_endpoint_reordering_keeps_pixel_indices(self):
        source = bytearray(32768)
        offset = block_offset(0, 12)
        struct.pack_into('>HHI', source, offset, 0xF800, 0x07E0, 0x1B1B1B1B)
        result = self.recolor(source, 2, [(0, 0, 255)] * 7)
        self.assertEqual(result[offset:offset + 8], bytes.fromhex('07e0001f4e4e4e4e'))

    def test_black_preserves_four_color_mode(self):
        source = bytearray(32768)
        offset = block_offset(140, 184)
        struct.pack_into('>HHI', source, offset, 0xFFFF, 0x7777, 0xFFFFFFFF)
        result = self.recolor(source, 8, [(0, 0, 0)] * 7)
        a, b = struct.unpack_from('>HH', result, offset)
        self.assertGreater(a, b)
        self.assertEqual(block_pixels(result, offset), [(0, 0, 0)] * 16)

    def test_quantized_solid_colors_do_not_sample_a_different_hue(self):
        source = bytearray(32768)
        regions = [(224, 180, 0), (72, 172, 1)]
        # Opaque endpoints share a max channel and quantize to one tint;
        # every original index, including both interpolants, is sampled.
        for x, y, _ in regions:
            struct.pack_into('>HHI', source, block_offset(x, y), 0xF820, 0xF800, 0x1B1B1B1B)
        for color in [(255, 0, 255), (0, 255, 255), (255, 255, 0),
                      (0, 0, 255), (255, 255, 255), (0, 0, 0)]:
            for x, y, part in regions:
                with self.subTest(color=color, part=part):
                    result = self.recolor(source, 1 << part, [color] * 7)
                    offset = block_offset(x, y)
                    a, b = struct.unpack_from('>HH', result, offset)
                    self.assertGreater(a, b)
                    expected = (color[0] * 31 // 255, color[1] * 63 // 255,
                                color[2] * 31 // 255)
                    self.assertEqual(block_pixels(result, offset), [expected] * 16)

    def test_cap_emblem_and_forearm_keep_original_colors(self):
        source = bytearray(32768)
        protected = [(192, 220, 0xFFDD, 0xF79C), (76, 216, 0xFC10, 0xDB0B)]
        for x, y, a, b in protected:
            struct.pack_into('>HHI', source, block_offset(x, y), a, b, 0x1B1B1B1B)
        result = self.recolor(source, 3, [(255, 0, 255)] * 7)
        for x, y, _, _ in protected:
            offset = block_offset(x, y)
            self.assertEqual(result[offset:offset + 8], source[offset:offset + 8])

    def test_alpha_mode_preserves_transparent_pixels(self):
        source = bytearray(32768)
        offset = block_offset(0, 12)
        struct.pack_into('>HHI', source, offset, 0x07E0, 0xF800, 0x1B1B1B1B)
        result = self.recolor(source, 2, [(0, 0, 255)] * 7)
        self.assertEqual(result[offset:offset + 8], bytes.fromhex('001f07e04b4b4b4b'))


if __name__ == '__main__':
    unittest.main()
