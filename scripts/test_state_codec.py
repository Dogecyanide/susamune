"""Run the production heapless state codec against bounded host buffers."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SUCCESS, INVALID, WORKSPACE, FULL, CORRUPT, ERROR, COMMIT = range(7)


class Span(C.Structure):
    _fields_ = [("data", C.c_void_p), ("size", C.c_uint)]


class Result(C.Structure):
    _fields_ = [("status", C.c_int), ("compressed", C.c_uint),
                ("raw", C.c_uint), ("adler", C.c_uint)]


class Guarded:
    def __init__(self, size):
        self.size = size
        self.buf = C.create_string_buffer(size + 128)
        C.memset(C.addressof(self.buf), 0xA7, len(self.buf))
        self.ptr = (C.addressof(self.buf) + 63) & ~31

    def data(self):
        return C.string_at(self.ptr, self.size)

    def guards(self):
        before = self.ptr - C.addressof(self.buf)
        return (self.buf.raw[:before] == bytes([0xA7]) * before and
                self.buf.raw[before + self.size:] ==
                bytes([0xA7]) * (len(self.buf) - before - self.size))


class StateCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        shim = Path(cls.folder.name) / "shim.cpp"
        shim.write_text(r'''
#include "susamune/state_codec.hxx"
extern "C" {
void *memcpy(void *d,const void *s,__SIZE_TYPE__ n) {
    unsigned char *o=(unsigned char*)d;const unsigned char *i=(const unsigned char*)s;
    while(n--)*o++=*i++;return d;
}
void *memset(void *d,int b,__SIZE_TYPE__ n) {
    unsigned char *o=(unsigned char*)d;while(n--)*o++=(unsigned char)b;return d;
}
int memcmp(const void *a,const void *b,__SIZE_TYPE__ n) {
    const unsigned char *x=(const unsigned char*)a,*y=(const unsigned char*)b;
    while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;
}
__declspec(dllexport) unsigned int workspace() {return StateCodec::workspaceSize();}
__declspec(dllexport) void pack(void *w,unsigned int ws,const StateCodec::ReadSpan *s,
 unsigned int n,const StateCodec::WriteSpan *d,StateCodec::Result *r) {
 *r=StateCodec::compress(w,ws,s,n,d);
}
__declspec(dllexport) int check(void *w,unsigned int ws,const StateCodec::ReadSpan *s,
 unsigned int n,unsigned int raw,unsigned int adler) {
 return StateCodec::validate(w,ws,s,n,raw,adler);
}
__declspec(dllexport) int unpack(void *w,unsigned int ws,const StateCodec::ReadSpan *s,
 unsigned int n,const StateCodec::WriteSpan *d,unsigned int dn,unsigned int raw,unsigned int adler) {
 return StateCodec::decompress(w,ws,s,n,d,dn,raw,adler);
}
}
''', encoding="ascii")
        library = shim.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-fno-builtin", "-mno-stack-arg-probe", "-I", str(ROOT / "include"),
                        str(shim), str(ROOT / "src/state_codec.cpp"), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.workspace.restype = C.c_uint
        cls.lib.pack.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint,
                                 C.POINTER(Span), C.POINTER(Result)]
        cls.lib.check.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint,
                                  C.c_uint, C.c_uint]
        cls.lib.unpack.argtypes = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint,
                                   C.POINTER(Span), C.c_uint, C.c_uint, C.c_uint]

    def setUp(self):
        self.work = Guarded(self.lib.workspace())
        self.assertLessEqual(self.work.size, 0x50000)

    def tearDown(self):
        self.assertTrue(self.work.guards())

    def source(self, data, cuts=()):
        edges = [0, *cuts, len(data)]
        buffers = [C.create_string_buffer(data[a:b]) for a, b in zip(edges, edges[1:])]
        spans = (Span * len(buffers))(*[Span(C.addressof(b), y - x)
                                      for b, x, y in zip(buffers, edges, edges[1:])])
        spans._owners = buffers
        return spans

    def pack(self, source, capacities=None):
        guards = [Guarded(n) for n in capacities] if capacities is not None else []
        output = (Span * 2)(*[Span(g.ptr, g.size) for g in guards]) if guards else None
        result = Result()
        self.lib.pack(self.work.ptr, self.work.size, source, len(source), output, C.byref(result))
        for guard in guards:
            self.assertTrue(guard.guards())
        return result, b"".join(g.data() for g in guards)

    def decode(self, encoded, raw_size, adler, cuts=(), output_sizes=None):
        source = self.source(encoded, cuts)
        sizes = output_sizes or [raw_size]
        guards = [Guarded(n) for n in sizes]
        output = (Span * len(guards))(*[Span(g.ptr, g.size) for g in guards])
        status = self.lib.unpack(self.work.ptr, self.work.size, source, len(source), output,
                                 len(output), raw_size, adler)
        for guard in guards:
            self.assertTrue(guard.guards())
        return status, b"".join(g.data() for g in guards)

    def test_scatter_compress_two_outputs_and_wrapping_scatter_inflate(self):
        data = (bytes(range(256)) * 4000) + random.Random(57).randbytes(50001)
        source = self.source(data, [0, 1, 7, 32767, 32768, 32769, 70001])
        measured, _ = self.pack(source)
        self.assertEqual((measured.status, measured.raw, measured.adler),
                         (SUCCESS, len(data), zlib.adler32(data)))
        packed, output = self.pack(source, [1, measured.compressed - 1])
        self.assertEqual(packed.status, SUCCESS)
        self.assertEqual(packed.compressed, measured.compressed)
        self.assertEqual(zlib.decompress(output), data)
        status, decoded = self.decode(output, len(data), measured.adler, cuts=[0, 1, 2, 3, 9],
                                      output_sizes=[0, 3, 32765, 1, 55555, len(data) - 88324])
        self.assertEqual((status, decoded), (SUCCESS, data))

    def test_output_full_counts_exact_size_without_touching_guards(self):
        data = random.Random(88).randbytes(100001)
        source = self.source(data, [50000])
        expected, _ = self.pack(source)
        for capacity in (0, 1, 7, expected.compressed - 1):
            packed, _ = self.pack(source, [capacity // 2, capacity - capacity // 2])
            self.assertEqual((packed.status, packed.compressed, packed.adler),
                             (FULL, expected.compressed, zlib.adler32(data)))

    def test_standard_zlib_stream_and_split_header_checksum(self):
        data = b"abc123" * 18000
        encoded = zlib.compress(data, 9)
        for cut in (0, 1, 2, 3, len(encoded) - 4, len(encoded) - 1, len(encoded)):
            status, decoded = self.decode(encoded, len(data), zlib.adler32(data), cuts=[cut])
            self.assertEqual((status, decoded), (SUCCESS, data))

    def test_corruption_truncation_wrong_sizes_and_trailing_data_write_nothing(self):
        data = random.Random(26).randbytes(70003)
        encoded = zlib.compress(data)
        bad = [encoded[:n] for n in (0, 1, 2, 7, len(encoded) // 2, len(encoded) - 1)]
        bad += [encoded + b"\0", encoded + encoded]
        for at in (0, 1, 10, 32768, len(encoded) - 4, len(encoded) - 1):
            changed = bytearray(encoded)
            changed[at] ^= 0x80
            bad.append(bytes(changed))
        for item in bad:
            status, decoded = self.decode(item, len(data), zlib.adler32(data),
                                          output_sizes=[17, len(data) - 17])
            self.assertIn(status, (INVALID, CORRUPT))
            self.assertEqual(decoded, bytes([0xA7]) * len(data))
        for expected, adler in ((len(data) - 1, zlib.adler32(data)),
                                (len(data) + 1, zlib.adler32(data)),
                                (len(data), zlib.adler32(data) ^ 1)):
            status, decoded = self.decode(encoded, expected, adler)
            self.assertEqual(status, CORRUPT)
            self.assertEqual(decoded, bytes([0xA7]) * expected)

    def test_destination_length_mismatch_writes_nothing(self):
        data = b"saved state" * 100
        for capacity in (len(data) - 1, len(data) + 1):
            status, decoded = self.decode(zlib.compress(data), len(data), zlib.adler32(data),
                                          output_sizes=[capacity])
            self.assertEqual((status, decoded), (INVALID, bytes([0xA7]) * capacity))

    def test_arguments_overlap_and_workspace_bounds(self):
        data = b"guard test" * 100
        source = self.source(data)
        result = Result()
        for pointer, size, count, expected in (
                (self.work.ptr + 1, self.work.size, 1, INVALID),
                (self.work.ptr, self.work.size - 1, 1, WORKSPACE),
                (self.work.ptr, self.work.size, 0, INVALID),
                (self.work.ptr, self.work.size, 65, INVALID)):
            self.lib.pack(pointer, size, source, count, None, C.byref(result))
            self.assertEqual(result.status, expected)
        for bad in ((Span * 1)(Span(self.work.ptr, 4)),
                    (Span * 1)(Span(None, 4)),
                    (Span * 1)(Span((1 << (C.sizeof(C.c_void_p) * 8)) - 2, 4)),
                    (Span * 2)(Span(4096, 0xfffffff0), Span(8192, 0x20))):
            self.lib.pack(self.work.ptr, self.work.size, bad, len(bad), None, C.byref(result))
            self.assertEqual(result.status, INVALID)
        for output in ((Span * 2)(Span(source[0].data, 4), Span(None, 0)),
                       (Span * 2)(Span(self.work.ptr, 4), Span(None, 0))):
            self.lib.pack(self.work.ptr, self.work.size, source, len(source), output, C.byref(result))
            self.assertEqual(result.status, INVALID)
        encoded = self.source(zlib.compress(data))
        guard = Guarded(len(data))
        for output in ((Span * 2)(Span(guard.ptr, 600), Span(guard.ptr + 500, 400)),
                       (Span * 1)(Span(encoded[0].data, len(data))),
                       (Span * 1)(Span(self.work.ptr, len(data)))):
            self.assertEqual(self.lib.unpack(self.work.ptr, self.work.size, encoded, 1,
                output, len(output), len(data), zlib.adler32(data)), INVALID)
        self.assertEqual(guard.data(), bytes([0xA7]) * len(data))

    def test_private_real_sunshine_capture_when_available(self):
        path = ROOT / "build/foxtrot-held-input/private-us-bianco-state.bin"
        if not path.exists():
            self.skipTest("Private Sunshine capture is deliberately not distributed")
        data = path.read_bytes()
        source = self.source(data, [448, 0x1000, 0x50000, 0x100000, 0x800000])
        result, _ = self.pack(source)
        self.assertEqual(result.status, SUCCESS)
        packed, encoded = self.pack(source, [result.compressed // 3,
                                            result.compressed - result.compressed // 3])
        self.assertEqual(packed.status, SUCCESS)
        status, decoded = self.decode(encoded, len(data), result.adler,
            cuts=[1, 0x8000, result.compressed // 2],
            output_sizes=[448, 0x50000 - 448, len(data) - 0x50000])
        self.assertEqual((status, decoded), (SUCCESS, data))
        self.assertEqual(zlib.decompress(encoded), data)
        print(f"Private Sunshine sample: raw={len(data)}, deflate={result.compressed}, "
              f"workspace={self.work.size}; one Bianco sample, not an all-scene bound")


if __name__ == "__main__":
    unittest.main()
