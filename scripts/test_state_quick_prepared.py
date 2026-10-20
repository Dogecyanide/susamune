"""New admission and selective Quick replay checks; no existing suite reruns."""
import ctypes as C
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from test_state_codec import Guarded, Span, Result, QUICK_BLOCK, reference_quick_frame
from timewarp_chunk_codec import Codec, ROOT


WRAPPER = r'''
extern "C" {
__declspec(dllexport) unsigned preparedSize(){return sizeof(StateCodec::PreparedQuickSource);}
__declspec(dllexport) int prepare(void*w,unsigned wn,const StateCodec::ReadSpan*s,unsigned sn,
 const StateCodec::WriteSpan*d,unsigned dn,void*p,unsigned off,unsigned len){
 return StateCodec::prepareQuickSource(w,wn,s,sn,d,dn,*(StateCodec::PreparedQuickSource*)p,{off,len});}
__declspec(dllexport) unsigned block(void*w,const void*p,unsigned index,unsigned char*d,unsigned*stats){
 StateCodec::PreparedQuickBlock b;
 StateCodec::encodePreparedQuickBlock(w,*(const StateCodec::PreparedQuickSource*)p,index,b);
 for(unsigned i=0;i<8;++i)d[i]=b.header[i];
 for(unsigned i=0;i<b.payloadBytes;++i)d[8+i]=b.payload[i];
 stats[0]=b.rawBytes;stats[1]=b.adler32;return 8+b.payloadBytes;}
__declspec(dllexport) void ordinary(void*w,unsigned wn,const StateCodec::ReadSpan*s,unsigned sn,
 const StateCodec::WriteSpan*d,unsigned dn,unsigned off,unsigned len,StateCodec::Result*r){
 *r=StateCodec::compress(w,wn,s,sn,d,dn,false,true,{off,len});}
}
'''


class PreparedQuickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='timewarp-prepared-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = folder / 'prepared.cpp'
        source.write_text('#include "' + (ROOT / 'src/state_codec.cpp').as_posix() + '"\n' + WRAPPER)
        cls.codec = Codec(folder, source)
        cls.addClassCleanup(cls.codec.close)
        cls.lib = cls.codec.lib
        p, u, spans = C.c_void_p, C.c_uint, C.POINTER(Span)
        cls.lib.preparedSize.restype = u
        cls.lib.prepare.argtypes = [p, u, spans, u, spans, u, p, u, u]
        cls.lib.block.argtypes = [p, p, u, p, C.POINTER(u)]
        cls.lib.block.restype = u
        cls.lib.ordinary.argtypes = [p, u, spans, u, spans, u, u, u, C.POINTER(Result)]

    def test_selective_replay_matches_complete_quick_stream(self):
        random_bytes = random.Random(503).randbytes(QUICK_BLOCK)
        for raw, cuts, gap in (
            (random_bytes * 3 + b'end', (0, 23, QUICK_BLOCK - 1, QUICK_BLOCK - 1,
                QUICK_BLOCK + 3, 2 * QUICK_BLOCK + 7), (QUICK_BLOCK - 5, QUICK_BLOCK + 19)),
            (b'allocated data' * 5000, (), (0, 0)),
            (random_bytes[:65500], (7, 65500), (15, 312)),
            (b'x', (0, 1), (0, 1)),
        ):
            with self.subTest(bytes=len(raw), gap=gap):
                points = [0, *cuts, len(raw)]
                owners = [C.create_string_buffer(raw[a:b]) for a, b in zip(points, points[1:])]
                source = (Span * len(owners))(*(Span(C.addressof(p), b-a)
                    for p, a, b in zip(owners, points, points[1:])))
                before = [p.raw for p in owners]
                descriptors = bytes(source)
                work = Guarded(self.lib.workspace())
                prepared = Guarded(self.lib.preparedSize())
                output = Guarded(len(raw) + 4096)
                dest = (Span * 1)(Span(output.ptr, output.size))
                result = Result()
                self.lib.ordinary(work.ptr, work.size, source, len(source), dest, 1, *gap, C.byref(result))
                self.assertEqual(result.status, 0)
                expected = output.data()[:result.compressed]
                C.memset(work.ptr, 0xa7, work.size)
                self.assertEqual(self.lib.prepare(work.ptr, work.size, source, len(source),
                    dest, 1, prepared.ptr, *gap), 0)
                self.assertEqual(work.data(), b'\xa7' * work.size)
                saved_prepared = prepared.data()
                count = (len(raw) + QUICK_BLOCK - 1) // QUICK_BLOCK
                blocks = [None] * count
                block_output = Guarded(QUICK_BLOCK + 8)
                canonical = raw[:gap[0]] + bytes(gap[1]) + raw[sum(gap):]
                for index in list(reversed(range(count))) + [0, count - 1]:
                    C.memset(work.ptr, 0x5c, work.size)
                    stats = (C.c_uint * 2)()
                    size = self.lib.block(work.ptr, prepared.ptr, index, block_output.ptr, stats)
                    block = block_output.data()[:size]
                    if blocks[index] is not None:
                        self.assertEqual(block, blocks[index])
                    blocks[index] = block
                    part = canonical[index * QUICK_BLOCK:(index + 1) * QUICK_BLOCK]
                    self.assertEqual(tuple(stats), (len(part), zlib.adler32(part)))
                stream = struct.pack('>II', 0x4d534c34, QUICK_BLOCK) + b''.join(blocks)
                self.assertEqual(stream, expected)
                self.assertEqual(reference_quick_frame(stream, len(raw)), canonical)
                self.assertEqual([p.raw for p in owners], before)
                self.assertEqual(bytes(source), descriptors)
                self.assertEqual(prepared.data(), saved_prepared)
                self.assertTrue(all(g.guards() for g in (work, output, prepared, block_output)))

    def test_refusal_precedes_all_writes(self):
        work = Guarded(self.lib.workspace())
        prepared = Guarded(self.lib.preparedSize())
        source_bytes, output = Guarded(64), Guarded(512)
        source = (Span * 1)(Span(source_bytes.ptr, 64))
        dest = (Span * 1)(Span(output.ptr, output.size))
        for off, length, size, target in (
            (65, 0, work.size, prepared.ptr),
            (63, 2, work.size, prepared.ptr),
            (0, 0xffffffff, work.size, prepared.ptr),
            (0, 0, 1, prepared.ptr),
            (0, 0, work.size, source_bytes.ptr),
            (0, 0, work.size, output.ptr),
            (0, 0, work.size, work.ptr),
            (0, 0, work.size, C.addressof(source)),
            (0, 0, work.size, C.addressof(dest)),
        ):
            with self.subTest(off=off, length=length, size=size, target=target):
                before = [g.data() for g in (work, prepared, source_bytes, output)]
                descriptors = bytes(source), bytes(dest)
                self.assertNotEqual(self.lib.prepare(work.ptr, size, source, 1,
                    dest, 1, target, off, length), 0)
                self.assertEqual([g.data() for g in (work, prepared, source_bytes, output)], before)
                self.assertEqual((bytes(source), bytes(dest)), descriptors)
        # Admission does not dereference source bytes; fake bounded storage checks
        # the maximum recipe count without allocating or compressing a 32 MiB input.
        fake = (Span * 1)(Span(0x10000000, 0x2000001))
        self.assertNotEqual(self.lib.prepare(work.ptr, work.size, fake, 1,
            dest, 1, prepared.ptr, 0, 0), 0)
        fake[0].size -= 1
        self.assertEqual(self.lib.prepare(work.ptr, work.size, fake, 1,
            dest, 1, prepared.ptr, 0, 0), 0)
        self.assertTrue(all(g.guards() for g in (work, prepared, source_bytes, output)))


if __name__ == '__main__':
    unittest.main()
