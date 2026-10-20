"""Check bounded incremental Quick encoding against the production stream API."""
import ctypes as C
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from test_state_codec import Guarded, Span, Result, reference_quick_frame
from timewarp_chunk_codec import Codec, ROOT

Emit = C.CFUNCTYPE(C.c_bool, C.c_void_p, C.POINTER(Span))


class QuickBlocksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="quick-blocks-")
        cls.addClassCleanup(cls.folder.cleanup)
        folder = Path(cls.folder.name)
        source = folder / "blocks.cpp"
        source.write_text('#include "' + (ROOT / 'src/state_codec.cpp').as_posix() + '"\n' + r'''
extern "C" {
__declspec(dllexport) void blocks(void*w,unsigned ws,const StateCodec::ReadSpan*s,unsigned n,
 const StateCodec::WriteSpan*d,unsigned dn,StateCodec::QuickBlock emit,void*ctx,StateCodec::Result*r) {
 *r=StateCodec::compressQuickBlocks(w,ws,s,n,d,dn,emit,ctx);
}
__declspec(dllexport) void whole(void*w,unsigned ws,const StateCodec::ReadSpan*s,unsigned n,
 const StateCodec::WriteSpan*d,unsigned dn,StateCodec::Result*r) {
 *r=StateCodec::compress(w,ws,s,n,d,dn,false,true);
}
}
''')
        cls.codec = Codec(folder, source)
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.codec.lib._handle)))
        common = [C.c_void_p, C.c_uint, C.POINTER(Span), C.c_uint, C.POINTER(Span), C.c_uint]
        cls.codec.lib.blocks.argtypes = common + [Emit, C.c_void_p, C.POINTER(Result)]
        cls.codec.lib.whole.argtypes = common + [C.POINTER(Result)]

    def encode(self, raw, cuts=(), reject=None, destinations=None):
        source = Guarded(len(raw))
        C.memmove(source.ptr, raw, len(raw))
        boundaries = [0, *cuts, len(raw)]
        spans = (Span * (len(boundaries) - 1))(*[
            Span(source.ptr + a, b - a) for a, b in zip(boundaries, boundaries[1:])])
        output = Guarded(len(raw) + 8 * ((len(raw) + 0x1ffff) // 0x20000) + 8)
        target = (Span * 1)(Span(output.ptr, output.size))
        baseline = Result()
        self.codec.lib.whole(self.codec.work.ptr, self.codec.work.size, spans, len(spans),
                             target, 1, C.byref(baseline))
        self.assertEqual(baseline.status, 0)
        blocks, written = [], 8

        @Emit
        def emit(context, encoded):
            nonlocal written
            data = C.string_at(encoded[0].data, encoded[0].size) + C.string_at(encoded[1].data, encoded[1].size)
            self.assertEqual(encoded[0].size, 8)
            self.assertLessEqual(encoded[1].size, 0x20000)
            blocks.append(data)
            if reject == len(blocks) - 1:
                return False
            C.memmove(output.ptr + written, data, len(data))
            written += len(data)
            return True

        expected = output.data()[:baseline.compressed]
        C.memset(output.ptr, 0xA7, output.size)
        C.memmove(output.ptr, b'MSL4\0\2\0\0', 8)
        result = Result()
        dest = destinations(source, output, spans) if destinations else target
        self.codec.lib.blocks(self.codec.work.ptr, self.codec.work.size, spans, len(spans),
                              dest, len(dest), emit, None, C.byref(result))
        self.assertEqual(source.data(), raw)
        self.assertTrue(source.guards() and output.guards() and self.codec.work.guards())
        return result, blocks, output.data()[:written], expected

    def test_exact_streams_at_block_and_span_boundaries(self):
        rng = random.Random(314159)
        for size in (1, 65535, 65536, 0x1ffff, 0x20000, 0x20001, 0x40000 + 83):
            for raw in (bytes(size), rng.randbytes(size), (b"Sunshine-Timewarp" * ((size + 15) // 16))[:size]):
                cuts = [size // 3, size // 2] if size > 2 else []
                with self.subTest(size=size, prefix=raw[:4]):
                    result, blocks, packed, expected = self.encode(raw, cuts)
                    self.assertEqual(result.status, 0)
                    self.assertEqual((result.raw, result.compressed, result.adler),
                                     (size, len(packed), zlib.adler32(raw)))
                    self.assertEqual(packed, expected)
                    self.assertEqual(reference_quick_frame(packed, size), raw)

    def test_refusal_stops_immediately_and_does_not_report_partial_as_complete(self):
        raw = random.Random(86).randbytes(0x40000 + 23)
        for reject in range(3):
            result, blocks, _, _ = self.encode(raw, reject=reject)
            self.assertEqual((result.status, result.raw, result.compressed, result.adler), (3, len(raw), 0, 0))
            self.assertEqual(len(blocks), reject + 1)

    def test_unsafe_destinations_rejected_before_callback(self):
        for destination in (
            lambda s, o, d: (Span * 1)(Span(s.ptr, s.size)),
            lambda s, o, d: (Span * 1)(Span(self.codec.work.ptr, 32)),
            lambda s, o, d: (Span * 1)(Span(C.addressof(d), C.sizeof(d))),
            lambda s, o, d: (Span * 2)(Span(o.ptr, 64), Span(o.ptr + 32, 64)),
            lambda s, o, d: (Span * 1)(Span(None, 0)),
        ):
            result, blocks, _, _ = self.encode(bytes(200), destinations=destination)
            self.assertEqual(result.status, 1)
            self.assertEqual(blocks, [])


if __name__ == '__main__':
    unittest.main()
