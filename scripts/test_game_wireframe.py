"""Exercise the production mesh packet parser and edge emitter on the host."""
import ctypes as C
import _ctypes
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def descriptor(lo=3 << 9, hi=0, a=1 | (4 << 1) | (4 << 10), b=0, c=0):
    data = b''.join(bytes((8, reg)) + struct.pack('>I', value)
                    for reg, value in zip((0x50, 0x60, 0x70, 0x80, 0x90), (lo, hi, a, b, c)))
    return data + bytes(0xc0 - len(data))


def packet(primitive, vertices):
    return bytes((primitive,)) + struct.pack('>H', len(vertices)) + b''.join(vertices)


def packets(data, stride):
    pos = 0
    while pos < len(data):
        primitive = data[pos]
        pos += 1
        if not primitive:
            continue
        count = struct.unpack_from('>H', data, pos)[0]
        pos += 2
        vertices = [data[pos + i * stride:pos + (i + 1) * stride] for i in range(count)]
        pos += count * stride
        yield primitive, vertices
    assert pos == len(data)


def line_edges(data, stride):
    result = set()
    for primitive, vertices in packets(data, stride):
        assert primitive in (0xa8, 0xb0)
        pairs = zip(vertices[::2], vertices[1::2]) if primitive == 0xa8 else zip(vertices, vertices[1:])
        result.update(tuple(sorted(pair)) for pair in pairs)
    return result


def strip_edges(vertices):
    result = set()
    for i in range(len(vertices) - 2):
        a, b, c = vertices[i:i + 3]
        result.update(tuple(sorted(pair)) for pair in ((a, b), (b, c), (c, a)))
    return result


class GameWireframeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-wireframe-', dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        cpp = Path(cls.temp.name) / 'wireframe.cpp'
        fifo = (ROOT / 'src/game_wireframe.cpp').read_text().split('struct Fifo {', 1)[1].split('\n};', 1)[0]
        for width in (8, 16, 32):
            fifo = fifo.replace(f'*reinterpret_cast<volatile u{width} *>(0xCC008000)', f'port{width}')
        fifo = fifo.replace('reinterpret_cast<u32>(data)', 'reinterpret_cast<unsigned long long>(data)')
        fifo = fifo.replace('*reinterpret_cast<const u32 *>(data)', 'alignedWord(data)')
        cpp.write_text(r'''
#include "susamune/game_wireframe_geometry.h"
using namespace GameWireframeGeometry;
Byte output[20*1024*1024]; unsigned written;
unsigned preambles, badWordReads; const Byte *sourceBegin, *sourceEnd;
using u32=unsigned;using u16=unsigned short;using u8=unsigned char;
template<unsigned Width>struct Port {
 void operator=(unsigned value){for(unsigned i=Width;i;i-=8)output[written++]=value>>(i-8);}
};
Port<8>port8;Port<16>port16;Port<32>port32;
void GXBegin(unsigned primitive,unsigned,unsigned count){++preambles;port8=primitive;port16=count;}
unsigned alignedWord(const Byte*p){
 if((reinterpret_cast<unsigned long long>(p)&3)||p<sourceBegin||p+4>sourceEnd){++badWordReads;return 0;}
 return read32(p);
}
struct Fifo {
''' + fifo + r'''
};
struct Sink {
 void bytes(const Byte*p,unsigned n){while(n--)output[written++]=*p++;}
 void begin(unsigned primitive,unsigned count){
  output[written++]=primitive; output[written++]=count>>8; output[written++]=count;
 }
};
#define API extern "C" __declspec(dllexport)
API unsigned stride(const Byte*p,unsigned n){return descriptorStride(p,n);}
API unsigned convert(const Byte*p,unsigned n,unsigned stride,unsigned budget){
 written=0;unsigned bytes=0;
 if(!validate(p,n,stride,budget,&bytes))return 0;
 Sink sink;emit(p,n,stride,sink);
 if(written!=bytes)__builtin_trap();
 return written;
}
API const Byte*result(){return output;}
API unsigned count(){return written;}
API unsigned preambleCount(){return preambles;}
API unsigned badReads(){return badWordReads;}
API unsigned fifoConvert(const Byte*p,unsigned n,unsigned stride,unsigned budget){
 written=preambles=badWordReads=0;sourceBegin=p;sourceEnd=p+n;unsigned bytes;
 if(!validate(p,n,stride,budget,&bytes))return 0;
 Fifo sink;emit(p,n,stride,sink);return written;
}
API unsigned fifoCopy(const Byte*p,unsigned n){
 written=preambles=badWordReads=0;sourceBegin=p;sourceEnd=p+n;
 Fifo sink;sink.bytes(p,n);return written;
}
''')
        dll = cpp.with_suffix('.dll')
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                        '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-fno-builtin',
                        '-O2', '-I', str(ROOT / 'include'), str(cpp), '-o', str(dll)],
                       capture_output=True, text=True,
                       env={**os.environ, 'TEMP': cls.temp.name, 'TMP': cls.temp.name})
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.lib.result.restype = C.c_void_p
        cls.lib.stride.argtypes = [C.c_char_p, C.c_uint]
        cls.lib.convert.argtypes = [C.c_char_p, C.c_uint, C.c_uint, C.c_uint]
        cls.lib.fifoConvert.argtypes = cls.lib.convert.argtypes
        cls.lib.fifoCopy.argtypes = [C.c_void_p, C.c_uint]
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))

    def convert(self, data, stride=1, budget=16 * 1024 * 1024):
        size = self.lib.convert(data, len(data), stride, budget)
        return C.string_at(self.lib.result(), size)

    def test_triangles_strips_fans_and_quads_follow_topology(self):
        vertices = [bytes((i,)) for i in range(6)]
        for primitive, count, indices in (
                (0x90, 6, [0, 1, 1, 2, 2, 0, 3, 4, 4, 5, 5, 3]),
                (0xa0, 5, [0, 1, 1, 2, 2, 0, 0, 2, 2, 3, 3, 0, 0, 3, 3, 4, 4, 0]),
                (0x80, 4, [0, 1, 1, 2, 2, 3, 3, 0])):
            with self.subTest(primitive=hex(primitive)):
                self.assertEqual(self.convert(packet(primitive, vertices[:count])),
                                 packet(0xa8, [vertices[i] for i in indices]))

    def test_strip_paths_preserve_exact_edges_including_small_and_degenerate_inputs(self):
        for count in (3, 4, 5, 6, 7, 8, 17, 257):
            for repeated in (False, True):
                vertices = [bytes((7, i % (3 if repeated else 251), 42, i % 2)) for i in range(count)]
                converted = self.convert(packet(0x98, vertices), 4)
                with self.subTest(count=count, repeated=repeated):
                    self.assertEqual(line_edges(converted, 4), strip_edges(vertices))
                    self.assertEqual(len(converted), 4 * 4 + 3 if count == 3 else 2 * count * 4 + 9)
                    self.assertLess(len(converted), (count - 2) * 6 * 4 + 3)

    def test_lines_points_and_matrix_attribute_bytes_are_preserved(self):
        vertices = [bytes((7, i, 42, 80 + i, 0, 2)) for i in range(4)]
        source = packet(0x90, vertices[:3]) + bytes(3) + packet(0xb0, vertices)
        source += packet(0xa8, vertices) + packet(0xb8, vertices)
        expected = packet(0xa8, [vertices[i] for i in (0, 1, 1, 2, 2, 0)])
        expected += packet(0xb0, vertices) + packet(0xa8, vertices) + packet(0xb8, vertices)
        self.assertEqual(self.convert(source, 6), expected)

    def test_indexed_descriptor_includes_skinning_and_nbt3(self):
        lo = 0x101 | (3 << 9) | (2 << 11) | (3 << 13)
        hi = 2 | (3 << 14)
        a = 1 | (4 << 1) | (1 << 9) | (4 << 10) | (5 << 14) | (1 << 31)
        data = descriptor(lo, hi, a)
        self.assertEqual(self.lib.stride(data, len(data)), 2 + 2 + 3 + 2 + 1 + 2)

    def test_direct_descriptor_covers_colour_packing_and_all_texcoords(self):
        lo = 0x1ff | (1 << 9) | (1 << 11) | (1 << 13) | (1 << 15)
        hi = 0x5555
        a = 1 | (4 << 1) | (1 << 9) | (3 << 10) | (1 << 14) | (5 << 18) | (1 << 21) | (4 << 22)
        b = sum((1 | (2 << 1)) << shift for shift in (0, 9, 18, 27))
        c = sum((1 | (1 << 1)) << shift for shift in (5, 14, 23))
        data = descriptor(lo, hi, a, b, c)
        self.assertEqual(self.lib.stride(data, len(data)), 9 + 12 + 18 + 3 + 4 + 8 + 4 * 4 + 3 * 2)

    def test_actual_j3d_array_and_xf_command_shape(self):
        data = descriptor()[:12] + b'\x10\x00\x00\x10\x08\x00\x00\x00\x00'
        data += b''.join(bytes((8, reg)) + struct.pack('>I', 0x12345678)
                         for i in range(12) for reg in (0xa0 + i, 0xb0 + i))
        data += descriptor()[12:30]
        data += bytes(0xc0 - len(data))
        self.assertEqual(self.lib.stride(data, len(data)), 2)

    def test_descriptor_rejects_unknown_or_truncated_commands_and_formats(self):
        good = descriptor()
        cases = [good[:-1], good + b'\0', bytes(0xc0), b'\x61' + good[1:],
                 good[:1] + b'\x71' + good[2:], descriptor(0),
                 descriptor(a=7 << 1), descriptor(a=(4 << 1) | (1 << 31)),
                 good[:-3] + b'\x08\x50\0', good[:-5] + b'\x10' + bytes(4)]
        for data in cases:
            with self.subTest(data=data[:16].hex()):
                self.assertEqual(self.lib.stride(data, len(data)), 0)

    def test_entire_list_validates_before_any_output(self):
        triangle = packet(0x90, [b'a', b'b', b'c'])
        for tail in (b'\x90', b'\x90\0\x03ab', b'\x08\x50\0\0\0\0',
                     packet(0x91, [b'a', b'b', b'c']), packet(0x90, [b'a'] * 4)):
            self.assertEqual(self.convert(triangle + tail), b'')
            self.assertEqual(self.lib.count(), 0)

    def test_input_stride_and_expansion_budget_bounds(self):
        triangle = packet(0x90, [b'a', b'b', b'c'])
        self.assertEqual(len(self.convert(triangle, budget=9)), 9)
        for data, stride, budget in ((triangle, 1, 8), (triangle, 0, 100),
                                    (triangle, 161, 1000), (bytes(1024 * 1024 + 1), 1, 100),
                                    (b'', 1, 100), (bytes(32), 1, 100)):
            self.assertEqual(self.convert(data, stride, budget), b'')

    def test_large_strip_preserves_edges_across_fifo_batch_boundaries(self):
        vertices = [struct.pack('>H', i) for i in range(65535)]
        converted = self.convert(packet(0x98, vertices), 2)
        paths = list(packets(converted, 2))
        self.assertEqual([len(v) for _, v in paths], [60000, 5536, 32768, 32767])
        self.assertTrue(all(mode == 0xb0 for mode, _ in paths))
        self.assertEqual(paths[0][1][-1], paths[1][1][0])
        self.assertEqual(line_edges(converted, 2), strip_edges(vertices))
        self.assertEqual(len(converted), (65535 * 2 + 1) * 2 + 12)

    def test_strip_expansion_budget_matches_every_batch_boundary(self):
        for count in (3, 4, 59999, 60000, 60001, 65535):
            data = packet(0x98, [b'x'] * count)
            expected = (4 + 3 if count == 3 else 2 * count + (count > 60000) + 9 + 3 * (count > 60000))
            self.assertEqual(len(self.convert(data, budget=expected)), expected)
            self.assertEqual(self.convert(data, budget=expected - 1), b'')

    def test_production_fifo_preamble_once_and_full_validation_before_headers(self):
        source = packet(0x98, [bytes((i,)) * 7 for i in range(8)])
        source += packet(0x90, [b'abcdefg', b'hijklmn', b'opqrstu'])
        expected = self.convert(source, 7)
        size = self.lib.fifoConvert(source, len(source), 7, len(expected))
        self.assertEqual(C.string_at(self.lib.result(), size), expected)
        self.assertEqual(self.lib.preambleCount(), 1)
        self.assertEqual(self.lib.badReads(), 0)
        malformed = source + b'\x90\0\x03a'
        self.assertEqual(self.lib.fifoConvert(malformed, len(malformed), 7, 10000), 0)
        self.assertEqual(self.lib.preambleCount(), 0)

    def test_production_fifo_aligned_bulk_and_short_unaligned_copies_are_exact(self):
        storage = C.create_string_buffer(bytes(range(128)))
        for offset in range(4):
            for count in range(66):
                size = self.lib.fifoCopy(C.addressof(storage) + offset, count)
                self.assertEqual(C.string_at(self.lib.result(), size), bytes(range(offset, offset + count)))
                self.assertEqual(self.lib.badReads(), 0)


if __name__ == '__main__':
    unittest.main()
